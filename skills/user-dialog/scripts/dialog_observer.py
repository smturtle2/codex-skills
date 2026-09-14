"""Read canonical response items through a short-lived, read-only app-server."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET


def reader_config():
    executable = shutil.which(os.environ.get("USER_DIALOG_CODEX", "codex"))
    if not executable:
        raise ValueError("Codex CLI is required for response confirmation; set USER_DIALOG_CODEX")
    return {"executable": str(Path(executable).resolve()),
            "home": str(Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve())}


@contextmanager
def submission_lock(origin, cancel):
    """Serialize popup submissions to the same task, including observation."""
    import fcntl
    key = hashlib.sha256((origin["host_id"] + origin["thread_id"]).encode()).hexdigest()
    directory = Path(origin["reader"]["home"]) / "user-dialog-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / key).open("a+b") as stream:
        while True:
            if cancel.is_set():
                raise InterruptedError("Response confirmation cancelled")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                cancel.wait(0.1)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class ResponseReader:
    def __init__(self, origin, cancel=None):
        self.origin = origin
        self.cancel = cancel if cancel is not None else threading.Event()
        self.process = None
        self.selector = None
        self.buffer = b""
        self.sequence = 0
        self.deadline = time.monotonic() + 60

    def __enter__(self):
        if self.origin["host_id"] != "local":
            raise ValueError("Response confirmation currently requires a local Codex task")
        config = self.origin["reader"]
        environment = dict(os.environ, CODEX_HOME=config["home"])
        self.process = subprocess.Popen([config["executable"], "app-server", "--stdio"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, env=environment)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            self.call("initialize", {"clientInfo": {"name": "user_dialog_reader", "version": "1"},
                                     "capabilities": {"experimentalApi": True}})
            self.process.stdin.write(b'{"method":"initialized"}\n')
            self.process.stdin.flush()
            thread = self.call("thread/read", {"threadId": self.origin["thread_id"],
                                               "includeTurns": False})["thread"]
            if thread.get("id") != self.origin["thread_id"]:
                raise ValueError("Response reader returned a different task")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.selector:
            self.selector.close()
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()

    def call(self, method, params):
        if method not in {"initialize", "thread/read", "thread/items/list"}:
            raise ValueError("The response reader only permits read-only requests")
        self.check()
        self.sequence += 1
        payload = json.dumps({"id": self.sequence, "method": method, "params": params}) + "\n"
        self.process.stdin.write(payload.encode())
        self.process.stdin.flush()
        deadline = min(self.deadline, time.monotonic() + 15)
        while time.monotonic() < deadline:
            self.check()
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                result = json.loads(line)
                if result.get("id") != self.sequence:
                    continue
                if "error" in result:
                    raise ValueError(result["error"].get("message", "Response lookup failed"))
                return result["result"]
            if self.selector.select(0.1):
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise ConnectionError("Response reader closed unexpectedly")
                self.buffer += chunk
                if len(self.buffer) > 32 * 1024 * 1024:
                    raise ValueError("Response lookup exceeded the message size limit")
        raise TimeoutError("Response lookup timed out")

    def check(self):
        if self.cancel.is_set():
            raise InterruptedError("Response confirmation cancelled")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("The response has not appeared in task history yet")

    def page(self, cursor=None, limit=100):
        args = {"threadId": self.origin["thread_id"], "limit": limit, "sortDirection": "desc"}
        if cursor is not None:
            args["cursor"] = cursor
        return self.call("thread/items/list", args)

    def bookmark(self):
        entries = self.page(limit=1)["data"]
        return entries[0]["item"]["id"] if entries else None

    def find_response(self, boundary, message):
        cursor, visited, matches = None, set(), []
        while True:
            page = self.page(cursor)
            for entry in page["data"]:
                item = entry["item"]
                if item["id"] == boundary:
                    return self.unique_match(matches)
                if matches_response(item, self.origin, message):
                    matches.append({"item_id": item["id"], "turn_id": entry["turnId"]})
            cursor = page.get("nextCursor")
            if cursor is None:
                if boundary is not None:
                    raise ValueError("The pre-send history position is no longer available")
                return self.unique_match(matches)
            if cursor in visited:
                raise ValueError("Response lookup returned a repeated cursor")
            visited.add(cursor)

    @staticmethod
    def unique_match(matches):
        if len(matches) > 1:
            raise ValueError("Multiple identical responses found; automatic confirmation is ambiguous")
        return matches[0] if matches else None

    def wait(self, boundary, message):
        self.deadline = time.monotonic() + 60
        while True:
            self.check()
            result = self.find_response(boundary, message)
            if result:
                return result
            self.cancel.wait(0.25)


def matches_response(item, origin, message):
    if (item.get("type") != "functionCallOutput" or item.get("namespace") != "codex_app"
            or item.get("name") != "send_message_to_thread" or not isinstance(item.get("output"), str)):
        return False
    try:
        root = ET.fromstring(item["output"])
    except ET.ParseError:
        return False
    return (root.tag == "codex_delegation"
            and root.findtext("source_thread_id") == origin["thread_id"]
            and root.findtext("input") == message)
