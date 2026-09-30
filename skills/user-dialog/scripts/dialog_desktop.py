"""Submit ordinary input through the original desktop conversation owner."""

import copy
import json
from pathlib import Path
import socket
import stat
import struct
import threading
import time
import uuid

from dialog_connection import RpcError, codex_home, require_owner, validate_user_message
from dialog_observer import RolloutResponseReader


REQUEST_TIMEOUT = 15
MAX_FRAME_BYTES = 256 * 1024 * 1024
METHOD_VERSIONS = {
    "initialize": 0,
    "thread-owner-discovery": 1,
    "thread-follower-steer-turn": 1,
}

awaits_response = True


def require_desktop_owner(origin):
    require_owner(origin)
    if origin.get("host_id") != "local":
        raise ValueError("Only the originating local desktop host is supported")
    if origin.get("socket") != str(Path(origin["home"]) / "ipc/ipc.sock"):
        raise ValueError("This dialog belongs to a different desktop connection")


class DesktopIpc:
    """Bind one native owner; canonical receipt reading belongs to the observer."""

    def __init__(self, origin, cancel=None, origin_cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.origin_cancel = origin_cancel
        self.wire_settled = False
        self.message_attempted = False
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
        if (not self.wire_settled and self.origin_cancel is not None
                and self.origin_cancel.is_set()):
            raise InterruptedError("The originating turn is no longer waiting for this dialog")

    def _send(self, packet, before_send=None):
        self.check()
        encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not 0 < len(encoded) <= MAX_FRAME_BYTES:
            raise ValueError("Desktop IPC packet is too large")
        if before_send is not None:
            before_send()
        self.check()
        if packet.get("method") == "thread-follower-steer-turn":
            self.message_attempted = True
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
            raise ValueError("Desktop IPC did not identify an ordinary-input conversation owner")
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

    def submit_user_message(self, message, client_id, before_send=None):
        """Steer the active originating turn; this backend never starts a turn."""
        try:
            validate_user_message(message, client_id)
            self.check()
            inputs = [copy.deepcopy(message)]
            cwd = self.thread["cwd"]
            response = self._request("thread-follower-steer-turn", {
                "conversationId": self.origin["thread_id"], "clientUserMessageId": client_id,
                "input": inputs, "attachments": [], "restoreMessage": {
                    "id": client_id, "text": message["text"], "cwd": cwd,
                    "createdAt": int(time.time() * 1000), "context": {
                        "prompt": message["text"], "workspaceRoots": [cwd], "commentAttachments": []}}},
                before_send)
            return response["result"]["result"]
        finally:
            # The launcher may release the originating tool after this attempt
            # settles. Its lifetime no longer constrains canonical observation.
            self.wire_settled = True


def connection(origin, cancel=None, origin_cancel=None):
    return DesktopIpc(origin, cancel, origin_cancel)


def capture_origin(origin):
    origin.update(host_id="local", socket=str(Path(codex_home()) / "ipc/ipc.sock"))
    with connection(origin) as server:
        origin["title"] = server.thread.get("name") or ""
        RolloutResponseReader(origin, server.cancel).validate()
    return origin


def _observe(attempt, reader):
    attempt.waiting()
    try:
        match = reader.wait(attempt.delivery, attempt.message["text"])
    except Exception as error:
        attempt.unconfirmed(error)
    else:
        attempt.observed(match)


def deliver(attempt):
    """Bind the owner and log before submitting one same-turn ordinary message."""
    validate_user_message(attempt.message, attempt.client_id)
    with connection(attempt.origin, attempt.cancel, attempt.origin_cancel) as server:
        reader = RolloutResponseReader(attempt.origin, attempt.cancel)
        reader.validate()
        server.check()
        try:
            receipt = server.submit_user_message(attempt.message, attempt.client_id, attempt.sending)
        except Exception as error:
            if not server.message_attempted:
                attempt.rejected(error)
                return
            # The native IPC error envelope loses admission information. Never
            # infer replay permission from error text after a message write.
            attempt.unknown(error)
        else:
            attempt.accepted(receipt)
        _observe(attempt, reader)


def confirm(attempt):
    """Read the exact saved canonical log without connecting or sending."""
    require_desktop_owner(attempt.origin)
    _observe(attempt, RolloutResponseReader(attempt.origin, attempt.cancel))
