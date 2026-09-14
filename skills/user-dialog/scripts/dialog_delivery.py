"""Pinned-origin desktop delivery via the installed Codex app-tools bridge.

The pipe is an internal desktop interface, discovered per run, never a global
active-window lookup. Unsupported environments fail closed. No CLI resume,
new daemon, title search or most-recent-thread fallback is used.
"""

import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import uuid

from dialog_state import save_state
from dialog_observer import ResponseReader, reader_config, submission_lock

LIMIT = 8 * 1024 * 1024


class Bridge:
    def __init__(self, origin):
        self.origin = origin
        self.tools = {}

    def request(self, method, params):
        path = self.origin["pipe"]
        identity = Path(path).stat()
        if not stat.S_ISSOCK(identity.st_mode) or [identity.st_dev, identity.st_ino] != self.origin["pipe_identity"]:
            raise ValueError("Original app connection changed; automatic rerouting is disabled")
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        if len(payload) > LIMIT:
            raise ValueError("App request is too large")
        def read_exact(connection, size):
            data = bytearray()
            while len(data) < size:
                chunk = connection.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("App connection closed before acknowledgement")
                data.extend(chunk)
            return data
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(30)
            connection.connect(path)
            connection.sendall(struct.pack("<I", len(payload)) + payload)
            length = struct.unpack("<I", read_exact(connection, 4))[0]
            if length > LIMIT:
                raise ValueError("App response is too large")
            result = json.loads(read_exact(connection, length))
        if result.get("id") != 1 or result.get("jsonrpc") != "2.0":
            raise ValueError("Invalid app acknowledgement")
        if "error" in result:
            raise ValueError(result["error"].get("message", "App request rejected"))
        return result["result"]

    def discover(self):
        result = self.request("tools/list", {"threadStartKind": "all"})
        self.tools = {tool["name"]: tool for tool in result["tools"]}
        for name in ("read_thread", "send_message_to_thread"):
            if name not in self.tools:
                raise ValueError(f"App bridge does not provide {name}")

    def call(self, name, arguments, call_id=None):
        tool = self.tools[name]
        result = self.request("tools/call", {
            "arguments": arguments, "namespace": tool["namespace"], "tool": name,
            "threadId": self.origin["thread_id"],
            "turnId": self.origin["turn_id"],
            "callId": call_id or f"dialog-{uuid.uuid4().hex}",
        })
        if not result.get("success"):
            raise ValueError("App tool did not confirm success")
        chunks = [item["text"] for item in result.get("contentItems", []) if item.get("type") == "inputText"]
        # The bridge wraps MCP tool results in text in some desktop versions.
        for text in chunks:
            try:
                value = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and "content" in value:
                if value.get("isError"):
                    raise ValueError("App tool rejected the request")
                for item in value["content"]:
                    if item.get("type") == "text":
                        try:
                            return json.loads(item["text"])
                        except ValueError:
                            pass
            if not isinstance(value, dict) or value.get("error") or value.get("isError") or value.get("success") is False:
                raise ValueError("App did not return a successful structured acknowledgement")
            return value
        raise ValueError("App returned no structured acknowledgement")

    def verify(self):
        args = {"threadId": self.origin["thread_id"], "turnLimit": 1, "includeOutputs": False,
                "maxOutputCharsPerItem": 1}
        if self.origin.get("host_id"):
            args["hostId"] = self.origin["host_id"]
        thread = self.call("read_thread", args).get("thread", {})
        if thread.get("id") != self.origin["thread_id"] or thread.get("kind") != "codex":
            raise ValueError("Original Codex task could not be verified")
        host = thread.get("hostId")
        if not host or self.origin.get("host_id") not in (None, host):
            raise ValueError("Original Codex host does not match")
        return thread


def capture_origin():
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    session_id = os.environ.get("CODEX_SESSION_ID", "")
    if not thread_id or session_id and session_id != thread_id:
        raise ValueError("Missing or conflicting originating Codex task identity")
    uuid.UUID(thread_id)
    pipe = os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")
    if not pipe or not hasattr(socket, "AF_UNIX"):
        raise ValueError("This host has no supported Codex desktop message bridge")
    path = Path(pipe).resolve()
    identity = path.stat()
    if not stat.S_ISSOCK(identity.st_mode):
        raise ValueError("Codex bridge path is not a local socket")
    origin = {"thread_id": thread_id, "host_id": None, "pipe": str(path),
              "pipe_identity": [identity.st_dev, identity.st_ino],
              "turn_id": os.environ.get("CODEX_TURN_ID") or f"dialog-origin-{uuid.uuid4().hex}"}
    bridge = Bridge(origin)
    bridge.discover()
    thread = bridge.verify()
    origin.update(host_id=thread["hostId"], title=thread.get("title", ""), reader=reader_config())
    if origin["host_id"] != "local":
        raise ValueError("Response confirmation currently requires a local Codex task")
    return origin


def require_owner(origin):
    if os.environ.get("CODEX_THREAD_ID") != origin["thread_id"]:
        raise ValueError("This dialog belongs to a different Codex task")
    session_id = os.environ.get("CODEX_SESSION_ID")
    if session_id and session_id != origin["thread_id"]:
        raise ValueError("Conflicting Codex task identity")
    if str(Path(os.environ.get("CODEX_APP_TOOLS_PIPE_PATH", "")).resolve()) != origin["pipe"]:
        raise ValueError("This dialog belongs to a different Codex connection")


def observe_response(directory, state, reader):
    delivery = state["delivery"]
    delivery["observation"] = {"status": "waiting"}
    save_state(directory, state)
    try:
        match = reader.wait(delivery["boundary_item_id"], state["message"])
        delivery["observation"] = {"status": "observed", **match}
    except Exception as error:
        delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
    save_state(directory, state)


def confirm_delivery(directory, state, cancel=None):
    """Retry observation only; never call the send tool."""
    delivery = state.get("delivery", {})
    if delivery.get("status") not in {"accepted", "unknown"}:
        return
    try:
        require_owner(state["origin"])
        if "boundary_item_id" not in delivery:
            raise ValueError("This older run has no pre-send history position; it cannot be auto-confirmed")
        with ResponseReader(state["origin"], cancel) as reader:
            observe_response(directory, state, reader)
    except Exception as error:
        delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        save_state(directory, state)


def deliver(directory, state, cancel=None):
    """Persist before sending. An uncertain acknowledgement is never retried."""
    if state.get("delivery", {}).get("status") in {"accepted", "unknown", "sending"}:
        return
    if state.get("status") != "submitted":
        return
    cancel = cancel if cancel is not None else threading.Event()
    try:
        require_owner(state["origin"])
        bridge = Bridge(state["origin"])
        bridge.discover()
        bridge.verify()
        state["origin"].setdefault("reader", reader_config())
        with submission_lock(state["origin"], cancel), ResponseReader(state["origin"], cancel) as reader:
            boundary = reader.bookmark()
            reader.check()
            state["delivery"] = {"status": "sending", "boundary_item_id": boundary}
            save_state(directory, state)
            try:
                receipt = bridge.call("send_message_to_thread", {
                    "threadId": state["origin"]["thread_id"], "hostId": state["origin"]["host_id"],
                    "prompt": state["message"],
                }, f"dialog-submit-{state['request_id']}")
                state["delivery"].update(status="accepted", receipt=receipt)
            except Exception as error:
                # Preserve the bookmark even when the acknowledgement is lost.
                state["delivery"].update(status="unknown", error=str(error))
            save_state(directory, state)
            observe_response(directory, state, reader)
    except Exception as error:
        delivery = state.get("delivery", {})
        if delivery.get("status") in {"sending", "accepted", "unknown"}:
            delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        else:
            state["delivery"] = {"status": "failed", "error": str(error)}
        save_state(directory, state)
