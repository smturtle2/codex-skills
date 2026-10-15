"""Read visible session history once without starting Claude or running inference."""
from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any, Protocol

from claude_native import ClaudeError


class Target(Protocol):
    session_id: str
    cwd: str


class HistoryError(ClaudeError):
    def __init__(self, message: str):
        super().__init__("history_unavailable", message)


def get_session_messages(session_id: str, *, directory: str) -> list[Any]:
    """Import the optional read-only SDK only for an explicit history request."""
    try:
        from claude_agent_sdk import get_session_messages as read_messages
    except ImportError as error:
        raise HistoryError(
            "Session history requires the optional SDK; rerun uv run with --extra history"
        ) from error
    return read_messages(session_id, directory=directory)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _text(message: Mapping) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    # Thinking, tool calls and tool results are not visible conversation text.
    return "".join(block["text"] for block in content
                   if isinstance(block, Mapping) and block.get("type") == "text"
                   and isinstance(block.get("text"), str))


def read_history(target: Target, limit: int = 10) -> dict[str, Any]:
    """Return the latest visible user and assistant records in native order."""
    if type(limit) is not int or limit <= 0:
        raise ClaudeError("invalid_request", "History limit must be a positive integer")
    records: dict[str, dict[str, str]] = {}
    try:
        items = get_session_messages(target.session_id, directory=os.fspath(target.cwd))
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
            content = _text(message)
            message_uuid.encode("utf-8")
            content.encode("utf-8")
            # A later snapshot replaces the UUID even if its visible text is
            # now empty; keep the latest snapshot's native ordering.
            records.pop(message_uuid, None)
            if content:
                records[message_uuid] = {"type": message_type, "uuid": message_uuid,
                                         "content": content}
    except HistoryError:
        raise
    except Exception as error:
        raise HistoryError("Cannot read target session history") from error
    messages = list(records.values())
    return {"type": "history", "session_id": target.session_id,
            "cwd": os.fspath(target.cwd), "limit": limit,
            "messages": messages[-limit:], "truncated": len(messages) > limit}
