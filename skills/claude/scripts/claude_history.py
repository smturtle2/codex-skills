"""Read Claude replies through the SDK without starting a Claude session.

Liveness belongs to the caller: it must validate the bound live session before
and after calling this module. A reply marker is attribution evidence only; it
does not establish that the caller's task has been fulfilled.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import os
import re
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
    except (TypeError, ValueError) as error:
        raise HistoryError("SDK history contains an unsupported message value") from error
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
    # Tool calls, tool results and thinking are not readable reply text.
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
    """Capture a pre-send baseline using UUIDs and content, never list offsets."""
    records = _read(target)
    fingerprints = {record["uuid"]: record["fingerprint"] for record in records}
    return {
        "version": 1,
        "session_id": target.session_id,
        "cwd": os.fspath(target.cwd),
        "baseline": dict(fingerprints),
        "seen": dict(fingerprints),
        "groups": {group["message_id"]: group["fingerprint"] for group in _groups(records)},
        "last_uuid": records[-1]["uuid"] if records else None,
        "history_gap": False,
    }


def _cursor(target: Target, cursor: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cursor, dict) or cursor.get("version") != 1:
        raise HistoryError("unsupported history cursor")
    if cursor.get("session_id") != target.session_id or cursor.get("cwd") != os.fspath(target.cwd):
        raise HistoryError("history cursor belongs to a different target")
    result = deepcopy(cursor)
    for name in ("baseline", "seen", "groups"):
        mapping = result.setdefault(name, {})
        if not isinstance(mapping, dict) or any(not isinstance(key, str) or
                not isinstance(value, str) for key, value in mapping.items()):
            raise HistoryError(f"invalid {name} fingerprints in history cursor")
    if result.get("last_uuid") is not None and not isinstance(result["last_uuid"], str):
        raise HistoryError("invalid last UUID in history cursor")
    if not isinstance(result.get("history_gap", False), bool):
        raise HistoryError("invalid history gap state in history cursor")
    return result


def _reply(text: str, request_id: str) -> str | None:
    # Anchoring the entire text excludes markers in code fences, block quotes,
    # explanations and ordinary inline examples. Require the exact attribute
    # form sent by the caller, rather than accepting loose XML-like syntax.
    opening = f'<codex-reply request-id="{request_id}">'
    closing = "</codex-reply>"
    pattern = r"\A\s*" + re.escape(opening) + r"(?P<body>[\s\S]*?)" + re.escape(closing) + r"\s*\Z"
    match = re.fullmatch(pattern, text)
    if match is None:
        return None
    body = match.group("body")
    # Two separate reply wrappers are ambiguous, even when they share an ID.
    if closing in body:
        return None
    return body


def _match(groups: list[dict[str, Any]], request_id: str) -> tuple[dict | None, bool]:
    matches = []
    for group in groups:
        body = _reply(group["text"], request_id)
        if body is not None:
            matches.append({**group, "request_id": request_id, "content": body})
    return (matches[0] if len(matches) == 1 else None, len(matches) > 1)


def observe_responses(target: Target, request_id: str, cursor: dict[str, Any],
                      previous_responses: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Observe new/edited readable text and explicitly attributed replies.

    A full current native message group is re-evaluated when any constituent
    changes, allowing partial reply text to become a complete wrapper later.
    The caller owns durable storage of observations and any matched response.
    """
    if not isinstance(request_id, str) or not request_id:
        raise HistoryError("request ID must be a nonempty string")
    updated = _cursor(target, cursor)
    records = _read(target)
    # Persisted observations survive SDK compaction. Latest revision wins for
    # attribution; the caller retains earlier versions as historical evidence.
    candidates = {group["message_id"]: group for group in (previous_responses or [])}
    history_gap = updated.get("history_gap", False)
    if not records:
        # The SDK may return [] during a transient file rewrite. It cannot
        # establish that the saved conversation boundary has disappeared.
        matched, ambiguous = _match(list(candidates.values()), request_id)
        return {"cursor": updated, "responses": [], "matched_response": matched,
                "history_gap": history_gap, "unmatched": any(group["text"] for group in candidates.values()) and matched is None,
                "ambiguous": ambiguous}

    fingerprints = {record["uuid"]: record["fingerprint"] for record in records}
    boundary = updated.get("last_uuid")
    if boundary is not None and boundary not in fingerprints:
        history_gap = True
    touched = {_message_id(record) for record in records
               if record["type"] == "assistant" and updated["seen"].get(record["uuid"]) != record["fingerprint"]}
    post_send = {_message_id(record) for record in records
                 if record["type"] == "assistant" and updated["baseline"].get(record["uuid"]) != record["fingerprint"]}
    responses = []
    for group in _groups(records):
        message_id = group["message_id"]
        if (message_id in touched and updated["groups"].get(message_id) != group["fingerprint"]
                and (group["text"] or message_id in candidates)):
            responses.append(group)
        if message_id in post_send:
            candidates[message_id] = group
        else:
            candidates.pop(message_id, None)
        updated["groups"][message_id] = group["fingerprint"]
    # Retain observations from chains removed by compaction; neither baseline
    # nor previously seen fingerprints is replaced by only the current chain.
    updated["seen"].update(fingerprints)
    updated["last_uuid"] = records[-1]["uuid"]
    updated["history_gap"] = history_gap

    matched, ambiguous = _match(list(candidates.values()), request_id)
    return {"cursor": updated, "responses": responses, "matched_response": matched,
            "history_gap": history_gap, "unmatched": any(group["text"] for group in candidates.values()) and matched is None,
            "ambiguous": ambiguous}
