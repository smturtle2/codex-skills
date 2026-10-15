"""Observe an existing Claude session's ordinary assistant text through the SDK.

The connection owns liveness and durable storage. This module owns its bound
history cursor and emits text changes without relating them to sent messages.
It never starts a Claude session or runs inference.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import os
from typing import Any, Protocol


class Target(Protocol):
    session_id: str
    cwd: str


class HistoryError(RuntimeError):
    """The SDK history or its saved observation cursor cannot be used."""


def get_session_messages(session_id: str, *, directory: str) -> list[Any]:
    """Keep the SDK read boundary importable and replaceable in fixture tests."""
    try:
        from claude_agent_sdk import get_session_messages as read_messages
    except ImportError as error:
        raise HistoryError("claude-agent-sdk is required to read session history") from error
    return read_messages(session_id, directory=directory)


def _fingerprint(value: Any) -> str:
    try:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
        encoded = serialized.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise HistoryError("SDK history contains an unsupported message value") from error
    return hashlib.sha256(encoded).hexdigest()


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _read(target: Target) -> list[dict[str, Any]]:
    """Normalize SDK messages and keep the last snapshot of each UUID."""
    records: dict[str, dict[str, Any]] = {}
    try:
        items = get_session_messages(target.session_id, directory=os.fspath(target.cwd))
    except (OSError, UnicodeError, ValueError) as error:
        raise HistoryError("Cannot read target session history") from error
    for item in items:
        message_type = _field(item, "type")
        if message_type not in {"user", "assistant"}:
            continue
        message_uuid = _field(item, "uuid")
        if not isinstance(message_uuid, str) or not message_uuid:
            raise HistoryError("SDK history contains a message without a UUID")
        session_id = _field(item, "session_id")
        if session_id is not None and session_id != target.session_id:
            raise HistoryError("SDK history belongs to a different session")
        message = _field(item, "message")
        if not isinstance(message, Mapping):
            raise HistoryError("SDK history contains an unsupported message payload")
        record = {"type": message_type, "uuid": message_uuid, "message": dict(message)}
        record["fingerprint"] = _fingerprint(record)
        # Re-inserting preserves the ordering of the latest snapshot, if an
        # SDK implementation ever returns duplicate UUIDs in one observation.
        records.pop(message_uuid, None)
        records[message_uuid] = record
    return list(records.values())


def _text(record: dict[str, Any]) -> str:
    if record["type"] != "assistant":
        return ""
    content = record["message"].get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    # Tool calls, tool results and thinking are not ordinary assistant text.
    return "".join(block["text"] for block in content
                   if isinstance(block, Mapping) and block.get("type") == "text"
                   and isinstance(block.get("text"), str))


def _message_id(record: dict[str, Any]) -> str:
    native_id = record["message"].get("id")
    return native_id if isinstance(native_id, str) and native_id else record["uuid"]


def _merge_snapshots(parts: list[str]) -> str:
    """Join distinct recorded blocks verbatim; UUID normalization handles edits.

    Equal or prefix-related text under different UUIDs can be intentional
    repetition. Text similarity alone is not evidence of duplicate records.
    """
    return "".join(parts)


def _groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["type"] != "assistant":
            continue
        text = _text(record)
        native_id = _message_id(record)
        group = grouped.setdefault(native_id, {"message_id": native_id,
                                               "uuids": [], "parts": []})
        group["uuids"].append(record["uuid"])
        group["parts"].append(text)
    result = []
    for group in grouped.values():
        text = _merge_snapshots(group.pop("parts"))
        group["text"] = text
        # Only the recorded group's content determines readable change.
        group["fingerprint"] = _fingerprint({"message_id": group["message_id"],
                                             "text": text})
        result.append(group)
    return result


def capture_cursor(target: Target) -> dict[str, Any]:
    """Set the connection's initial receive position once, before accepting sends.

    Existing text is already behind the receive position. A later revision of
    an existing native message may still produce its first published event.
    """
    records = _read(target)
    fingerprints = {record["uuid"]: record["fingerprint"] for record in records}
    return {
        "version": 2,
        "session_id": target.session_id,
        "cwd": os.fspath(target.cwd),
        "seen": fingerprints,
        "groups": {group["message_id"]: {"fingerprint": group["fingerprint"], "revision": 0}
                   for group in _groups(records)},
        "last_uuid": records[-1]["uuid"] if records else None,
        "history_gap": False,
    }


def _cursor(target: Target, cursor: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cursor, dict) or cursor.get("version") != 2:
        raise HistoryError("unsupported history cursor")
    if cursor.get("session_id") != target.session_id or cursor.get("cwd") != os.fspath(target.cwd):
        raise HistoryError("history cursor belongs to a different target")
    result = deepcopy(cursor)
    seen = result.get("seen")
    if not isinstance(seen, dict) or any(not isinstance(key, str) or not key or
            not isinstance(value, str) or not value for key, value in seen.items()):
        raise HistoryError("invalid record fingerprints in history cursor")
    groups = result.get("groups")
    if not isinstance(groups, dict):
        raise HistoryError("invalid message groups in history cursor")
    for message_id, group in groups.items():
        if (not isinstance(message_id, str) or not message_id or not isinstance(group, dict)
                or not isinstance(group.get("fingerprint"), str) or not group["fingerprint"]
                or type(group.get("revision")) is not int or group["revision"] < 0):
            raise HistoryError("invalid message group in history cursor")
    if result.get("last_uuid") is not None and (
            not isinstance(result["last_uuid"], str) or not result["last_uuid"]):
        raise HistoryError("invalid last UUID in history cursor")
    if not isinstance(result.get("history_gap"), bool):
        raise HistoryError("invalid history gap state in history cursor")
    return result


def observe_messages(target: Target, cursor: dict[str, Any]) -> dict[str, Any]:
    """Read new or revised assistant text independently of outgoing messages.

    Each emitted event is the complete current text of one native message.id
    group. Its revision increases only when content is published; empty content
    withdraws previously published text. The final constituent's record UUID
    identifies the current snapshot, while message_id identifies its revisions.
    Missing records do not imply a deletion or an empty-text revision.
    """
    updated = _cursor(target, cursor)
    records = _read(target)
    history_gap = updated["history_gap"]
    if not records:
        # The SDK may return [] during a transient file rewrite. It cannot
        # establish that the saved conversation boundary has disappeared.
        return {"cursor": updated, "messages": [], "history_gap": history_gap}

    fingerprints = {record["uuid"]: record["fingerprint"] for record in records}
    boundary = updated.get("last_uuid")
    if boundary is not None and boundary not in fingerprints:
        history_gap = True
    touched = {_message_id(record) for record in records
               if record["type"] == "assistant" and updated["seen"].get(record["uuid"]) != record["fingerprint"]}
    messages = []
    for group in _groups(records):
        message_id = group["message_id"]
        previous = updated["groups"].get(message_id)
        revision = previous["revision"] if previous is not None else 0
        if (message_id in touched and (
                previous is None or previous["fingerprint"] != group["fingerprint"])
                and (group["text"] or revision > 0)):
            revision += 1
            messages.append({"source": "assistant", "uuid": group["uuids"][-1],
                             "message_id": message_id, "content": group["text"],
                             "revision": revision})
        if message_id in touched:
            updated["groups"][message_id] = {"fingerprint": group["fingerprint"], "revision": revision}
    # Keep observed UUIDs and revisions when compaction removes their chain.
    updated["seen"].update(fingerprints)
    updated["last_uuid"] = records[-1]["uuid"]
    updated["history_gap"] = history_gap

    return {"cursor": updated, "messages": messages, "history_gap": history_gap}
