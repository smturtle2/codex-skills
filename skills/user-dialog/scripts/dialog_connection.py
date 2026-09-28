"""Connect to the existing local app-server that owns the originating thread."""

import json
import os
from pathlib import Path
import stat
import threading
import time
import uuid


class RpcError(ValueError):
    """A server error with enough detail to distinguish rejection from uncertainty."""

    def __init__(self, error):
        self.code = error.get("code")
        self.data = error.get("data")
        super().__init__(error.get("message", "App-server rejected the request"))

    def turn_changed(self):
        message = str(self).lower()
        return any(term in message for term in (
            "no active turn", "noactiveturn", "expectedturnmismatch", "expected turn id",
        ))

    def rejected(self):
        # Internal server errors may occur after a write; never assume rollback.
        return self.code in {-32600, -32601, -32602}


def connection_config():
    home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
    # Preserve the stable control-socket symlink across daemon restarts.
    path = Path(os.environ.get("USER_DIALOG_SOCKET", str(home / "app-server-control/app-server-control.sock")))
    return {"home": str(home), "socket": os.path.abspath(path.expanduser())}


def require_owner(origin):
    thread_id = os.environ.get("CODEX_THREAD_ID")
    session_id = os.environ.get("CODEX_SESSION_ID")
    if not thread_id or thread_id != origin["thread_id"] or session_id and session_id != thread_id:
        raise ValueError("This dialog belongs to a different Codex task")
    config = connection_config()
    if origin.get("transport") != "app-server":
        raise ValueError("Unsupported dialog transport")
    if any(origin.get(key) != config[key] for key in ("home", "socket")):
        raise ValueError("This dialog belongs to a different Codex connection")


class AppServer:
    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.connection = None
        self.sequence = 0

    def __enter__(self):
        require_owner(self.origin)
        try:
            path = self.origin["socket"]
            if not stat.S_ISSOCK(Path(path).stat().st_mode):
                raise ValueError("App-server endpoint is not a Unix socket")
            from websockets.sync.client import unix_connect
            self.connection = unix_connect(path, open_timeout=5, close_timeout=1, max_size=32 * 1024 * 1024)
            self.call("initialize", {"clientInfo": {"name": "user_dialog", "version": "3"},
                                     "capabilities": {"experimentalApi": True}})
            self.connection.send('{"method":"initialized"}')
            self.thread = self.verify()
            return self
        except Exception as error:
            self.__exit__()
            raise ValueError(f"Cannot connect to the originating app-server: {error}. "
                             "Use an existing local server; USER_DIALOG_SOCKET selects its Unix socket.") from error

    def __exit__(self, *args):
        if self.connection is not None:
            self.connection.close()

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response delivery cancelled")

    def call(self, method, params):
        self.check()
        self.sequence += 1
        self.connection.send(json.dumps({"id": self.sequence, "method": method, "params": params}))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.check()
            try:
                result = json.loads(self.connection.recv(timeout=0.1))
            except TimeoutError:
                continue
            if result.get("id") != self.sequence or "method" in result:
                continue
            if "error" in result:
                raise RpcError(result["error"])
            return result["result"]
        raise TimeoutError(f"App-server {method} acknowledgement timed out")

    def verify(self):
        thread = self.call("thread/read", {"threadId": self.origin["thread_id"], "includeTurns": False})["thread"]
        if thread.get("id") != self.origin["thread_id"]:
            raise ValueError("App-server returned a different task")
        cursor, seen = None, set()
        while True:
            params = {"limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            page = self.call("thread/loaded/list", params)
            if self.origin["thread_id"] in page["data"]:
                return thread
            cursor = page.get("nextCursor")
            if cursor is None or cursor in seen:
                raise ValueError("The originating task is not loaded in this server; resume it in its original client")
            seen.add(cursor)

    def active_turn(self):
        page = self.call("thread/turns/list", {"threadId": self.origin["thread_id"],
                                               "limit": 1, "sortDirection": "desc"})
        if not page["data"]:
            return None
        turn = page["data"][0]
        return turn["id"] if turn["status"] == "inProgress" else None


def capture_origin():
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    uuid.UUID(thread_id)
    origin = {"transport": "app-server", "thread_id": thread_id, **connection_config()}
    with AppServer(origin) as server:
        server.active_turn()
        server.call("thread/items/list", {"threadId": thread_id, "limit": 1, "sortDirection": "desc"})
        origin["title"] = server.thread.get("name") or server.thread.get("preview", "")
    return origin
