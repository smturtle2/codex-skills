"""Confirm canonical native inputs using each backend's saved correlation rules."""

import json
import os
from pathlib import Path
import threading
import time
import uuid
import xml.etree.ElementTree as ET


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

    def matches_item(self, entry, delivery, message):
        return matches_response(entry.get("item", {}), delivery, message)

    def find_response(self, delivery, message):
        for entry in self.completed_items():
            item = entry.get("item", {})
            if (entry.get("threadId") == self.origin["thread_id"]
                    and item.get("id") and entry.get("turnId")
                    and self.matches_item(entry, delivery, message)):
                self.matches[item["id"]] = {"item_id": item["id"], "turn_id": entry["turnId"]}
        if len(self.matches) > 1:
            raise ValueError("Multiple native inputs match this saved response")
        return next(iter(self.matches.values()), None)

    def wait(self, delivery, message, timeout=60):
        if not delivery.get("client_message_id"):
            raise ValueError("Missing saved response identity")
        self.validate()
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            self.check()
            match = self.find_response(delivery, message)
            if match:
                return match
            self.cancel.wait(0.1)
        raise TimeoutError("The response has not appeared as a canonical native input yet")


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
        raise ValueError("This conversation log does not retain canonical input identities")
    return path, (info.st_dev, info.st_ino)


class RolloutResponseReader(ResponseReader):
    """Read completed entries from the exact owner-provided conversation log."""

    def __init__(self, origin, cancel=None):
        super().__init__(origin, cancel)
        self.path, self.identity = rollout_source(origin)
        self.position = 0

    def validate(self):
        path, identity = rollout_source(self.origin)
        if path != self.path or identity != self.identity:
            raise ValueError("The originating conversation log changed")

    def records(self):
        with self.path.open("rb") as stream:
            metadata = os.fstat(stream.fileno())
            identity = (metadata.st_dev, metadata.st_ino)
            if identity != self.identity or metadata.st_size < self.position:
                raise ValueError("The originating conversation log changed during confirmation")
            stream.seek(self.position)
            while True:
                self.check()
                start = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    break
                record = json.loads(line)
                self.position = stream.tell()
                yield start, record

    def completed_items(self):
        entries = []
        for start, record in self.records():
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


class RolloutToolResponseReader(RolloutResponseReader):
    """Match a new Desktop delegation after its durable pre-write boundary."""

    def __init__(self, origin, cancel=None):
        super().__init__(origin, cancel)
        self.fence = None

    def latest_turn_id(self):
        """Capture real caller provenance, never manufacture a tool-source turn."""
        self.validate()
        self.position = 0
        latest = None
        turns = set()
        for _, record in self.records():
            payload = record.get("payload", {})
            if (record.get("type") == "turn_context"
                    or record.get("type") == "event_msg" and payload.get("type") == "task_started"):
                turn_id = payload.get("turn_id")
                if isinstance(turn_id, str) and turn_id:
                    try:
                        uuid.UUID(turn_id)
                    except ValueError:
                        continue
                    latest = turn_id
                    turns.add(turn_id)
        supplied = os.environ.get("CODEX_TURN_ID")
        if supplied and supplied not in turns:
            raise ValueError("The caller's turn is not present in its verified native log")
        if not latest:
            raise ValueError("The native conversation log has no genuine caller turn")
        return supplied or latest

    def capture_fence(self):
        self.validate()
        self.position = 0
        existing = []
        for entry in self.completed_items():
            if entry["item"].get("id"):
                existing.append(entry["item"]["id"])
        info = self.path.stat()
        if (info.st_dev, info.st_ino) != self.identity or info.st_size < self.position:
            raise ValueError("The originating conversation log changed before submission")
        # offset is a complete-line boundary; cutoff also excludes a partial
        # record that began before the wire write but finishes after it.
        return {"path": str(self.path), "identity": list(self.identity), "offset": self.position,
                "cutoff": info.st_size, "previous_item_ids": existing}

    def bind_fence(self, delivery):
        fence = delivery.get("fence")
        if not isinstance(fence, dict):
            raise ValueError("Missing saved Desktop confirmation boundary")
        if self.fence == fence:
            return
        if (fence.get("path") != str(self.path) or fence.get("identity") != list(self.identity)
                or not isinstance(fence.get("offset"), int) or fence["offset"] < 0
                or not isinstance(fence.get("cutoff"), int) or fence["cutoff"] < fence["offset"]
                or not isinstance(fence.get("previous_item_ids"), list)
                or any(not isinstance(item_id, str) for item_id in fence["previous_item_ids"])):
            raise ValueError("The saved Desktop confirmation boundary no longer matches its log")
        if self.path.stat().st_size < fence["cutoff"]:
            raise ValueError("The originating conversation log was truncated after submission")
        self.fence = fence
        self.position = fence["offset"]
        self.matches = {}

    def completed_items(self):
        entries = []
        for start, record in self.records():
            payload = record.get("payload", {})
            if record.get("type") != "response_item" or payload.get("type") != "function_call_output":
                continue
            metadata = payload.get("internal_chat_message_metadata_passthrough", {})
            entries.append({"threadId": self.origin["thread_id"], "turnId": metadata.get("turn_id"),
                            "offset": start, "item": {"type": "functionCallOutput", "id": payload.get("id"),
                                "namespace": payload.get("namespace"), "name": payload.get("name"),
                                "output": payload.get("output")}})
        return entries

    def matches_item(self, entry, delivery, message):
        item = entry.get("item", {})
        if (entry["offset"] < self.fence["cutoff"] or item.get("id") in self.fence["previous_item_ids"]
                or item.get("namespace") != "codex_app" or item.get("name") != "send_message_to_thread"
                or not isinstance(item.get("output"), str)):
            return False
        try:
            # Preserve literal CR/CRLF in the saved answer: XML parsers normally
            # normalize those characters even when native output retained them.
            delegation = ET.fromstring(item["output"].replace("\r", "&#13;"))
        except ET.ParseError:
            return False
        sources, inputs = delegation.findall("source_thread_id"), delegation.findall("input")
        return (delegation.tag == "codex_delegation" and len(sources) == len(inputs) == 1
                and not list(sources[0]) and not list(inputs[0])
                and sources[0].text == self.origin["thread_id"] and (inputs[0].text or "") == message)

    def find_response(self, delivery, message):
        self.bind_fence(delivery)
        match = super().find_response(delivery, message)
        return {**match, "kind": "desktop_tool_output"} if match else None
