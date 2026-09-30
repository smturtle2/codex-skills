"""Own discovery, native CLI submission, live receipts and offline recovery."""

from collections import deque
import json
from pathlib import Path
import stat
import subprocess
import threading
import time

from dialog_connection import RpcError, codex_home, require_owner, validate_user_message
from dialog_observer import ResponseReader, RolloutResponseReader

awaits_response = False


def discover():
    """Find the existing native daemon without starting a server."""
    try:
        result = subprocess.run(
            ["codex", "app-server", "daemon", "version"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        locator = json.loads(result.stdout)
        if not isinstance(locator, dict):
            raise ValueError("Native discovery returned an invalid locator")
        socket_path = locator.get("socketPath")
        if (locator.get("status") != "running" or not isinstance(socket_path, str)
                or not Path(socket_path).is_absolute()):
            raise ValueError("Native discovery did not return a running daemon endpoint")
        return {"home": codex_home(), "socket": socket_path}
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise ValueError(f"Cannot locate the existing Codex daemon: {error}") from error


class AppServer:
    """Subscribe to the existing CLI runtime and preserve native completed items."""

    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.connection = None
        self.sequence = 0
        self.items = deque()
        self.thread = {}
        self.rollout_path = None
        self.message_attempted = False

    def __enter__(self):
        require_owner(self.origin)
        try:
            current = discover()
            if current["socket"] != self.origin.get("socket"):
                raise ValueError("The originating daemon endpoint changed")
            path = self.origin["socket"]
            if not stat.S_ISSOCK(Path(path).stat().st_mode):
                raise ValueError("App-server endpoint is not a Unix socket")
            from websockets.sync.client import unix_connect
            self.connection = unix_connect(path, open_timeout=5, close_timeout=1,
                                           max_size=32 * 1024 * 1024)
            initialized = self._request("initialize", {
                "clientInfo": {"name": "user_dialog", "version": "3"},
                "capabilities": {"experimentalApi": True},
            })
            server_home = initialized.get("codexHome")
            if (not isinstance(server_home, str) or not server_home
                    or str(Path(server_home).resolve()) != self.origin["home"]):
                raise ValueError("App-server returned a different Codex home")
            self.connection.send('{"method":"initialized"}')
            self.thread = self._verify_loaded()
            # Native warm rejoin subscribes this helper before returning. No
            # launch configuration or model overrides belong in this request.
            resumed = self._request("thread/resume", {
                "threadId": self.origin["thread_id"], "excludeTurns": True,
            })["thread"]
            if resumed.get("id") != self.origin["thread_id"]:
                raise ValueError("App-server rejoined a different task")
            native_path = resumed.get("path") or self.thread.get("path")
            saved_path = self.origin.get("rollout_path")
            if (saved_path and native_path
                    and Path(saved_path).resolve() != Path(native_path).resolve()):
                raise ValueError("The original conversation log changed")
            self.thread = resumed
            self.rollout_path = native_path or saved_path
            if self.rollout_path:
                self.origin["rollout_path"] = self.rollout_path
            return self
        except Exception as error:
            self.__exit__()
            raise ValueError(f"Cannot attach to the originating Codex daemon: {error}") from error

    def __exit__(self, *args):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response delivery cancelled")

    def _receive(self, timeout):
        packet = json.loads(self.connection.recv(timeout=timeout))
        if packet.get("method") == "item/completed":
            params = packet.get("params", {})
            if (params.get("threadId") == self.origin["thread_id"]
                    and isinstance(params.get("item"), dict) and params.get("turnId")):
                self.items.append({key: params[key] for key in ("threadId", "turnId", "item")})
        return packet

    def _request(self, method, params, before_send=None):
        self.check()
        self.sequence += 1
        request_id = self.sequence
        encoded = json.dumps({"id": request_id, "method": method, "params": params})
        if before_send is not None:
            before_send()
        self.check()
        if method == "turn/start":
            self.message_attempted = True
        self.connection.send(encoded)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.check()
            try:
                packet = self._receive(min(0.1, max(0, deadline - time.monotonic())))
            except TimeoutError:
                continue
            if packet.get("id") != request_id or "method" in packet:
                continue
            if "error" in packet:
                raise RpcError(packet["error"])
            return packet["result"]
        raise TimeoutError(f"App-server {method} acknowledgement timed out")

    def _verify_loaded(self):
        thread = self._request("thread/read", {
            "threadId": self.origin["thread_id"], "includeTurns": False,
        })["thread"]
        if thread.get("id") != self.origin["thread_id"]:
            raise ValueError("App-server returned a different task")
        cursor, seen = None, set()
        while True:
            params = {"limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            page = self._request("thread/loaded/list", params)
            if self.origin["thread_id"] in page["data"]:
                return thread
            cursor = page.get("nextCursor")
            if cursor is None or cursor in seen:
                raise ValueError("The originating task is not loaded in this daemon")
            seen.add(cursor)

    def submit_user_message(self, message, client_id, before_send=None):
        """Use Core's native active/idle admission without a frontend placeholder."""
        validate_user_message(message, client_id)
        return self._request("turn/start", {
            "threadId": self.origin["thread_id"], "clientUserMessageId": client_id,
            "input": [message],
        }, before_send)

    def poll_items(self, timeout=0.25):
        self.check()
        deadline = time.monotonic() + max(0, timeout)
        while not self.items:
            try:
                self._receive(min(0.1, max(0, deadline - time.monotonic())))
            except TimeoutError:
                if time.monotonic() >= deadline:
                    break
            self.check()
            if time.monotonic() >= deadline:
                break
        items = list(self.items)
        self.items.clear()
        return items


class CliReceiptReader(ResponseReader):
    """Consume this helper's native subscription, including items before ACK."""

    def __init__(self, server):
        super().__init__(server.origin, server.cancel)
        self.server = server

    def completed_items(self):
        return self.server.poll_items(timeout=0.25)


def connection(origin, cancel=None):
    return AppServer(origin, cancel)


def capture_origin(origin):
    origin.update(discover())
    with connection(origin) as server:
        origin["title"] = server.thread.get("name") or server.thread.get("preview", "")
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
    """Attach and subscribe before Core admits one ordinary user input."""
    validate_user_message(attempt.message, attempt.client_id)
    with connection(attempt.origin, attempt.cancel) as server:
        reader = CliReceiptReader(server)
        reader.validate()
        server.check()
        try:
            receipt = server.submit_user_message(attempt.message, attempt.client_id, attempt.sending)
        except Exception as error:
            if not server.message_attempted:
                attempt.rejected(error)
                return
            attempt.unknown(error)
        else:
            attempt.accepted(receipt)
        _observe(attempt, reader)


def confirm(attempt):
    """Recover only from the bound canonical log; never reconnect or resume."""
    _observe(attempt, RolloutResponseReader(attempt.origin, attempt.cancel))
