"""Deliver delegated tool input through the original Desktop app bridge."""

import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import time
import uuid

from dialog_connection import RpcError, codex_home, require_owner, validate_user_message
from dialog_observer import RolloutResponseReader, RolloutToolResponseReader


REQUEST_TIMEOUT = 15
MAX_FRAME_BYTES = 256 * 1024 * 1024
METHOD_VERSIONS = {
    "initialize": 0,
    "thread-owner-discovery": 1,
}

kind = "desktop_tool_output"


def require_desktop_owner(origin):
    require_owner(origin)
    if origin.get("host_id") != "local":
        raise ValueError("Only the originating local desktop host is supported")
    if origin.get("socket") != str(Path(origin["home"]) / "ipc/ipc.sock"):
        raise ValueError("This dialog belongs to a different desktop connection")


class DesktopIpc:
    """Bind one native owner; canonical receipt reading belongs to the observer."""

    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.connection = None
        self.client_id = "initializing-client"
        self.owner_client_id = origin.get("owner_client_id")
        self.rollout_path = origin.get("rollout_path")
        self.thread = {}
        self.buffer = bytearray()

    def __enter__(self):
        require_desktop_owner(self.origin)
        try:
            self.check()
            if not stat.S_ISSOCK(Path(self.origin["socket"]).stat().st_mode):
                raise ValueError("Desktop IPC endpoint is not a Unix socket")
            self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.connection.settimeout(0.1)
            self.connection.connect(self.origin["socket"])
            result = self._request("initialize", {"clientType": "user-dialog"})
            self.client_id = result["result"]["clientId"]
            uuid.UUID(self.client_id)
            self._discover_owner()
            self._read_metadata()
            return self
        except Exception:
            self.__exit__()
            raise

    def __exit__(self, *args):
        # Disconnecting also removes this fresh client's native following state.
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response delivery cancelled")

    def _send(self, packet, before_send=None):
        self.check()
        encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not 0 < len(encoded) <= MAX_FRAME_BYTES:
            raise ValueError("Desktop IPC packet is too large")
        if before_send is not None:
            before_send()
        self.check()
        self.connection.sendall(struct.pack("<I", len(encoded)) + encoded)

    def _receive(self, deadline):
        while True:
            self.check()
            if len(self.buffer) >= 4:
                length = struct.unpack_from("<I", self.buffer)[0]
                if not 0 < length <= MAX_FRAME_BYTES:
                    raise ValueError("Invalid desktop IPC frame length")
                if len(self.buffer) >= length + 4:
                    packet = json.loads(bytes(self.buffer[4:length + 4]))
                    del self.buffer[:length + 4]
                    if not isinstance(packet, dict):
                        raise ValueError("Invalid desktop IPC packet")
                    return packet
            if time.monotonic() >= deadline:
                raise TimeoutError("Desktop IPC acknowledgement timed out")
            try:
                block = self.connection.recv(65536)
            except socket.timeout:
                continue
            if not block:
                raise ConnectionError("Desktop IPC connection closed")
            self.buffer.extend(block)

    def _ignore(self, packet):
        if packet.get("type") == "client-discovery-request":
            # A helper is an honestly initialized client, never a thread owner.
            self._send({"type": "client-discovery-response", "requestId": packet["requestId"],
                        "response": {"canHandle": False}})

    def _request(self, method, params, before_send=None):
        request_id = str(uuid.uuid4())
        packet = {"type": "request", "requestId": request_id,
                  "sourceClientId": self.client_id, "version": METHOD_VERSIONS[method],
                  "method": method, "params": params, "timeoutMs": REQUEST_TIMEOUT * 1000}
        if method != "initialize" and self.owner_client_id is not None:
            packet["targetClientId"] = self.owner_client_id
        self._send(packet, before_send)
        deadline = time.monotonic() + REQUEST_TIMEOUT
        while True:
            response = self._receive(deadline)
            if response.get("type") != "response" or response.get("requestId") != request_id:
                self._ignore(response)
                continue
            if response.get("resultType") == "error":
                # Native errors omit method and handledByClientId. The broker
                # routes the matching request ID back from its pinned target.
                if (response.get("method", method) != method
                        or response.get("handledByClientId", self.owner_client_id) != self.owner_client_id):
                    raise ValueError("Desktop IPC returned a different request owner")
                error = response.get("error")
                raise RpcError({"message": str(error or "Desktop IPC request failed")})
            if response.get("method") != method:
                raise ValueError("Desktop IPC returned a different method")
            if (method != "initialize" and self.owner_client_id is not None
                    and response.get("handledByClientId") != self.owner_client_id):
                raise ValueError("The original desktop conversation owner is unavailable")
            if response.get("resultType") != "success":
                # Even a native error may follow a write. Delivery owns uncertainty.
                raise RpcError({"message": str(response.get("error", "Desktop IPC request failed"))})
            return response

    def _discover_owner(self):
        response = self._request("thread-owner-discovery", {
            "hostId": self.origin["host_id"], "conversationId": self.origin["thread_id"],
        })
        owner = response.get("handledByClientId")
        if (not isinstance(owner, str) or not owner
                or response.get("result", {}).get("supportsUntrustedAppInput") is not True):
            raise ValueError("Desktop IPC did not identify the native conversation owner")
        self.owner_client_id = owner
        self.origin["owner_client_id"] = owner

    def _read_metadata(self):
        self._send({"type": "broadcast", "method": "thread-stream-following-changed",
                    "sourceClientId": self.client_id, "targetClientIds": [self.owner_client_id],
                    "version": 1, "params": {"hostId": self.origin["host_id"],
                    "conversationId": self.origin["thread_id"], "following": True}})
        deadline = time.monotonic() + REQUEST_TIMEOUT
        while True:
            packet = self._receive(deadline)
            params = packet.get("params", {})
            targets = packet.get("targetClientIds")
            if (packet.get("type") != "broadcast" or packet.get("method") != "thread-stream-state-changed"
                    or packet.get("sourceClientId") != self.owner_client_id
                    or not isinstance(params, dict) or params.get("hostId") != self.origin["host_id"]
                    or params.get("conversationId") != self.origin["thread_id"]
                    or targets is not None and self.client_id not in targets):
                self._ignore(packet)
                continue
            change = params.get("change", {})
            if not isinstance(change, dict) or change.get("type") != "snapshot":
                continue
            state = change.get("conversationState")
            if not isinstance(state, dict) or state.get("id") != self.origin["thread_id"]:
                raise ValueError("Desktop metadata belongs to a different task")
            path = state.get("rolloutPath")
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise ValueError("Desktop owner did not provide its conversation log path")
            if self.rollout_path is not None and Path(path).resolve() != Path(self.rollout_path).resolve():
                raise ValueError("The original desktop conversation log changed")
            self.rollout_path = path
            self.origin["rollout_path"] = path
            cwd = state.get("cwd")
            if not isinstance(cwd, str) or not Path(cwd).is_absolute():
                raise ValueError("Desktop owner did not provide its workspace directory")
            self.thread = {"id": state["id"], "name": state.get("title") or "", "cwd": cwd}
            return


def connection(origin, cancel=None):
    return DesktopIpc(origin, cancel)


class Bridge:
    """Call only the inherited, pinned app-tools socket with genuine provenance."""

    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.message_attempted = False
        self.tool = None

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response delivery cancelled")
        require_desktop_owner(self.origin)
        inherited = os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")
        if not inherited or str(Path(inherited).resolve()) != self.origin.get("pipe"):
            raise ValueError("This dialog belongs to a different Desktop tools connection")
        info = Path(self.origin["pipe"]).stat()
        if (not stat.S_ISSOCK(info.st_mode)
                or [info.st_dev, info.st_ino] != self.origin.get("pipe_identity")):
            raise ValueError("The originating Desktop tools connection changed")

    def request(self, method, params, before_send=None, on_wait=None):
        self.check()
        request_id = str(uuid.uuid4())
        data = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method,
                           "params": params}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not 0 < len(data) <= MAX_FRAME_BYTES:
            raise ValueError("Desktop tool request is too large")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(REQUEST_TIMEOUT)
            peer.connect(self.origin["pipe"])
            self.check()
            if before_send is not None:
                before_send()
            self.check()
            if method == "tools/call":
                # Mark uncertainty before sendall: a failing write can be partial.
                self.message_attempted = True
            peer.sendall(struct.pack("<I", len(data)) + data)
            peer.settimeout(0.1)
            deadline, buffer = time.monotonic() + REQUEST_TIMEOUT, bytearray()
            while True:
                # Actual admission is sufficient; no acknowledgement is invented
                # when the canonical item arrives before the RPC response.
                if on_wait is not None and on_wait():
                    return None
                self.check()
                if len(buffer) >= 4:
                    length = struct.unpack_from("<I", buffer)[0]
                    if not 0 < length <= MAX_FRAME_BYTES:
                        raise ValueError("Invalid Desktop tools response frame length")
                    if len(buffer) >= length + 4:
                        response = json.loads(bytes(buffer[4:length + 4]))
                        break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Desktop tool acknowledgement timed out")
                try:
                    block = peer.recv(65536)
                except socket.timeout:
                    continue
                if not block:
                    raise ConnectionError("Desktop tools connection closed before acknowledgement")
                buffer.extend(block)
        if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                or response.get("id") != request_id):
            raise ValueError("Desktop tool returned a different request acknowledgement")
        if "error" in response:
            raise RpcError(response["error"])
        result = response.get("result")
        if not isinstance(result, dict):
            raise ValueError("Desktop tool returned no structured result")
        return result

    def discover(self):
        tools = self.request("tools/list", {"threadStartKind": "all"}).get("tools", [])
        candidates = [tool for tool in tools if isinstance(tool, dict)
                      and tool.get("namespace") == "codex_app"
                      and tool.get("name") == "send_message_to_thread"]
        if len(candidates) != 1:
            raise ValueError("The original Desktop bridge does not provide send_message_to_thread")
        self.tool = candidates[0]

    def submit(self, message, client_id, before_send=None, on_wait=None):
        validate_user_message(message, client_id)
        if self.tool is None:
            raise ValueError("The Desktop message tool has not been discovered")
        source_turn = self.origin.get("source_turn_id")
        if not isinstance(source_turn, str) or not source_turn:
            raise ValueError("Missing captured native source turn")
        result = self.request("tools/call", {
            "callerSource": "codex", "hostId": self.origin["host_id"],
            "namespace": self.tool["namespace"], "tool": self.tool["name"],
            "threadId": self.origin["thread_id"], "turnId": source_turn,
            # This identifies the invocation, not a native deduplication key.
            "callId": client_id, "arguments": {"threadId": self.origin["thread_id"],
                "hostId": self.origin["host_id"], "prompt": message["text"]}}, before_send, on_wait)
        if result is None:
            return None
        if result.get("success") is not True:
            raise ValueError("Desktop message tool did not confirm success")
        values = []
        for chunk in result.get("contentItems", []):
            if not isinstance(chunk, dict) or chunk.get("type") != "inputText":
                continue
            try:
                value = json.loads(chunk["text"])
            except (KeyError, TypeError, ValueError):
                continue
            if isinstance(value, dict) and isinstance(value.get("content"), list):
                if value.get("isError"):
                    raise ValueError("Desktop message tool rejected its request")
                for item in value["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        try:
                            values.append(json.loads(item["text"]))
                        except (KeyError, TypeError, ValueError):
                            pass
            else:
                values.append(value)
        for value in values:
            if (isinstance(value, dict) and value.get("threadId") == self.origin["thread_id"]
                    and not value.get("error") and not value.get("isError")
                    and value.get("success") is not False):
                return value
        raise ValueError("Desktop message tool did not acknowledge the original conversation")


def capture_origin(origin):
    origin.update(host_id="local", socket=str(Path(codex_home()) / "ipc/ipc.sock"))
    inherited = os.environ.get("CODEX_APP_TOOLS_PIPE_PATH")
    if not inherited:
        raise ValueError("Missing inherited Desktop tools connection")
    pipe = Path(inherited).resolve(strict=True)
    info = pipe.stat()
    if not stat.S_ISSOCK(info.st_mode):
        raise ValueError("The inherited Desktop tools endpoint is not a Unix socket")
    origin.update(pipe=str(pipe), pipe_identity=[info.st_dev, info.st_ino])
    with connection(origin) as server:
        origin["title"] = server.thread.get("name") or ""
        reader = RolloutToolResponseReader(origin, server.cancel)
        origin["source_turn_id"] = reader.latest_turn_id()
    Bridge(origin).discover()
    return origin


def _observe(attempt, reader):
    if attempt.delivery.get("observation", {}).get("status") == "observed":
        return
    attempt.waiting()
    try:
        match = reader.wait(attempt.delivery, attempt.message["text"])
    except Exception as error:
        attempt.unconfirmed(error)
    else:
        attempt.observed(match)


def deliver(attempt):
    """Use the app-owned active/idle coordinator, then confirm canonical tool input."""
    validate_user_message(attempt.message, attempt.client_id)
    with connection(attempt.origin, attempt.cancel) as server:
        reader = RolloutToolResponseReader(attempt.origin, attempt.cancel)
        server.check()
    bridge = Bridge(attempt.origin, attempt.cancel)
    bridge.discover()
    attempt.prepare(kind, fence=reader.capture_fence())

    def canonical_admitted():
        try:
            reader.validate()
            match = reader.find_response(attempt.delivery, attempt.message["text"])
        except (OSError, ValueError):
            return False
        if match:
            attempt.observed(match)
            return True
        return False

    try:
        receipt = bridge.submit(attempt.message, attempt.client_id, attempt.sending, canonical_admitted)
    except Exception as error:
        if not bridge.message_attempted:
            attempt.rejected(error)
            return
        # A public tools error cannot establish that admission was rolled back.
        attempt.unknown(error)
    else:
        if receipt is not None:
            attempt.accepted(receipt)
    _observe(attempt, reader)


def confirm(attempt):
    """Recover from the saved native log and boundary without reconnecting or replay."""
    require_desktop_owner(attempt.origin)
    # Earlier saved Desktop attempts submitted ordinary USER input. Recover
    # those through their native identity; never resend them as delegation.
    reader_type = (RolloutToolResponseReader if attempt.delivery.get("kind") == kind
                   or "fence" in attempt.delivery else RolloutResponseReader)
    _observe(attempt, reader_type(attempt.origin, attempt.cancel))
