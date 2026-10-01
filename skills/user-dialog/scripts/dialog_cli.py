"""Own discovery, native CLI submission, live receipts and offline recovery."""

from collections import deque
import json
from pathlib import Path
import re
import stat
import subprocess
import threading
import time

from dialog_connection import RpcError, codex_home, require_owner, validate_user_message
from dialog_observer import ResponseReader, RolloutResponseReader, matches_response

kind = "cli_user_message"


def _guard_rejected(error):
    """Recognize only native steer guards that prove input was not admitted."""
    return (isinstance(error, RpcError) and error.code == -32600
            and (str(error) == "no active turn to steer"
                 or re.fullmatch(r"expected active turn id `[^`]+` but found `[^`]+`", str(error))))


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
        self.receipt_callback = None
        self.receipt_poll = None

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
                entry = {key: params[key] for key in ("threadId", "turnId", "item")}
                self.items.append(entry)
                if self.receipt_callback is not None:
                    self.receipt_callback(entry)
        return packet

    def _request(self, method, params, before_send=None):
        self.check()
        self.sequence += 1
        request_id = self.sequence
        encoded = json.dumps({"id": request_id, "method": method, "params": params})
        if before_send is not None:
            before_send()
        self.check()
        if method in {"turn/start", "turn/steer"}:
            self.message_attempted = True
        self.connection.send(encoded)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.check()
            if self.receipt_poll is not None:
                self.receipt_poll()
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

    def submit_user_message(self, message, client_id, before_send=None, on_item=None,
                            on_wait=None, on_not_submitted=None):
        """Steer a verified active turn, or admit idle input in this same task."""
        validate_user_message(message, client_id)
        self.receipt_callback = on_item
        self.receipt_poll = on_wait
        # Refresh only after a proven zero-admission rejection. A UUID is a
        # correlation ID, not native idempotency; unknown outcomes never retry.
        for _ in range(3):
            active_turn = self._active_turn()
            params = {"threadId": self.origin["thread_id"],
                      "clientUserMessageId": client_id, "input": [message]}
            method = "turn/start"
            if active_turn:
                method = "turn/steer"
                params["expectedTurnId"] = active_turn
            try:
                return self._request(method, params, before_send)
            except RpcError as error:
                if method != "turn/steer" or not _guard_rejected(error):
                    raise
                self.message_attempted = False
                if on_not_submitted is not None:
                    # Persist the native zero-admission result before another
                    # read can block or the sender can stop during refresh.
                    on_not_submitted()
        raise ValueError("The active turn kept changing; no response was admitted")

    def _active_turn(self):
        """Read only the original task; expectedTurnId guards subsequent races."""
        thread = self._request("thread/read", {
            "threadId": self.origin["thread_id"], "includeTurns": False,
        })["thread"]
        if thread.get("id") != self.origin["thread_id"]:
            raise ValueError("App-server returned a different task")
        if thread.get("status", {}).get("type") == "idle":
            return None
        if thread.get("historyMode") == "paginated":
            turns = self._request("thread/turns/list", {
                "threadId": self.origin["thread_id"], "limit": 1,
                "sortDirection": "desc",
            })["data"]
        else:
            hydrated = self._request("thread/read", {
                "threadId": self.origin["thread_id"], "includeTurns": True,
            })["thread"]
            if hydrated.get("id") != self.origin["thread_id"]:
                raise ValueError("App-server returned a different task")
            turns = list(reversed(hydrated.get("turns", [])))[:1]
        if turns and turns[0].get("status") == "inProgress":
            active_turn = turns[0].get("id")
            if not isinstance(active_turn, str) or not active_turn:
                raise ValueError("App-server returned an active turn without its identity")
            return active_turn
        return None

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
    """Confirm live receipts and bound canonical items, including before ACK."""

    def __init__(self, server):
        super().__init__(server.origin, server.cancel)
        self.server = server
        self.live_error = None
        self.canonical_error = None
        try:
            self.canonical = RolloutResponseReader(server.origin, server.cancel)
        except (OSError, ValueError):
            # Legacy logs need live native events. Never reconstruct a path by
            # searching other conversations or attaching a different server.
            self.canonical = None

    def completed_items(self):
        entries = []
        if self.live_error is None:
            try:
                entries = self.server.poll_items(timeout=0.25)
            except Exception as error:
                self.live_error = error
        entries.extend(self.canonical_items())
        if self.canonical is None and self.live_error is not None:
            raise self.canonical_error or self.live_error
        return entries

    def canonical_items(self):
        if self.canonical is not None:
            try:
                return self.canonical.completed_items()
            except (OSError, ValueError) as error:
                self.canonical_error, self.canonical = error, None
        return []


def connection(origin, cancel=None):
    return AppServer(origin, cancel)


def capture_origin(origin):
    origin.update(discover())
    with connection(origin) as server:
        origin["title"] = server.thread.get("name") or server.thread.get("preview", "")
        if server.rollout_path:
            origin["rollout_path"] = server.rollout_path
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
        attempt.observed({"kind": kind, **match})


def deliver(attempt):
    """Attach and subscribe before Core admits one ordinary user input."""
    validate_user_message(attempt.message, attempt.client_id)
    attempt.prepare(kind)
    with connection(attempt.origin, attempt.cancel) as server:
        reader = CliReceiptReader(server)
        reader.validate()
        server.check()
        def completed(entry):
            item = entry["item"]
            if (item.get("id") and entry.get("turnId")
                    and matches_response(item, attempt.delivery, attempt.message["text"])):
                attempt.observed({"item_id": item["id"], "turn_id": entry["turnId"], "kind": kind})
        def check_canonical():
            for entry in reader.canonical_items():
                completed(entry)
        try:
            receipt = server.submit_user_message(
                attempt.message, attempt.client_id, before_send=attempt.sending,
                on_item=completed, on_wait=check_canonical,
                on_not_submitted=lambda: attempt.prepare(kind))
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
