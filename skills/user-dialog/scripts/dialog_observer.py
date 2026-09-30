"""Match native completed user messages by saved identity and exact text."""

import json
import os
from pathlib import Path
import threading
import time


def matches_response(item, delivery, message):
    content = item.get("content", [])
    return (item.get("type") == "userMessage" and item.get("clientId") == delivery["client_message_id"]
            and len(content) == 1 and content[0].get("type") == "text"
            and content[0].get("text") == message)


class ResponseReader:
    """Match canonical entries from a backend-owned receipt source."""

    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.matches = {}

    def validate(self):
        pass

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response confirmation cancelled")

    def completed_items(self):
        raise NotImplementedError

    def find_response(self, delivery, message):
        for entry in self.completed_items():
            item = entry.get("item", {})
            if (entry.get("threadId") == self.origin["thread_id"]
                    and item.get("id") and entry.get("turnId")
                    and matches_response(item, delivery, message)):
                self.matches[item["id"]] = {"item_id": item["id"], "turn_id": entry["turnId"]}
        if len(self.matches) > 1:
            raise ValueError("Multiple user messages have this response identity")
        return next(iter(self.matches.values()), None)

    def wait(self, delivery, message, timeout=60):
        if not delivery.get("client_message_id"):
            raise ValueError("Missing saved response identity")
        self.validate()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            match = self.find_response(delivery, message)
            if match:
                return match
            self.cancel.wait(0.1)
        raise TimeoutError("The response has not appeared as a native user message yet")


def rollout_source(origin):
    """Use only the native owner's exact path; never search other conversations."""
    value = origin.get("rollout_path")
    if not value or not Path(value).is_absolute():
        raise ValueError("Missing native conversation log path; receipt cannot be recovered")
    path = Path(value).resolve(strict=True)
    with path.open("rb") as stream:
        metadata = json.loads(stream.readline())
        info = os.fstat(stream.fileno())
    if metadata.get("type") != "session_meta" or metadata.get("payload", {}).get("id") != origin["thread_id"]:
        raise ValueError("Conversation log belongs to a different Codex task")
    if metadata["payload"].get("history_mode") != "paginated":
        raise ValueError("This conversation log does not retain canonical user-message identities")
    return path, (info.st_dev, info.st_ino)


class RolloutResponseReader(ResponseReader):
    """Read canonical user items from the exact owner-provided conversation log."""

    def __init__(self, origin, cancel=None):
        super().__init__(origin, cancel)
        self.path, self.identity = rollout_source(origin)
        self.position = 0

    def validate(self):
        path, identity = rollout_source(self.origin)
        if path != self.path or identity != self.identity:
            raise ValueError("The originating conversation log changed")

    def completed_items(self):
        entries = []
        with self.path.open("rb") as stream:
            metadata = os.fstat(stream.fileno())
            identity = (metadata.st_dev, metadata.st_ino)
            if self.identity is not None and (identity != self.identity or metadata.st_size < self.position):
                raise ValueError("The originating conversation log changed during confirmation")
            self.identity = identity
            stream.seek(self.position)
            while True:
                self.check()
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    break
                record = json.loads(line)
                self.position = stream.tell()
                payload = record.get("payload", {})
                if (record.get("type") != "event_msg" or payload.get("type") != "item_completed"
                        or payload.get("thread_id") != self.origin["thread_id"]):
                    continue
                item = payload.get("item", {})
                if item.get("type") == "UserMessage":
                    entries.append({"threadId": payload["thread_id"], "turnId": payload.get("turn_id"),
                                    "item": {"type": "userMessage", "id": item.get("id"),
                                             "clientId": item.get("client_id"), "content": item.get("content", [])}})
        return entries
