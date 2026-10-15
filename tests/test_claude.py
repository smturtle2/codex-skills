"""Six connection contracts using real Linux processes, pipes, and Unix inboxes.

Discovery and SDK reads use fixture data. Shutdown cases also inject faults at
record, socket cleanup, worker, and owner boundaries. Relay processes, pipes,
sockets/peer credentials, cursor, and durable files stay real.
"""
import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import pty
import queue
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import unquote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/claude/scripts"))
import claude
import claude_connection
import claude_history
from claude_native import ClaudeError, NativeClient, build_frame

SESSION_ID = "11111111-1111-4111-8111-111111111111"


def store(path, value):
    temporary = path.with_suffix(".next")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def sdk_message(message_id, text=None, *, record_uuid=None, private=False):
    content = [{"type": "thinking", "thinking": "private reasoning"},
               {"type": "tool_use", "id": "hidden", "name": "Read", "input": {}}] if private else []
    if text is not None:
        content.append({"type": "text", "text": text})
    return {"type": "assistant", "uuid": record_uuid or str(uuid.uuid4()),
            "session_id": SESSION_ID,
            "message": {"id": message_id, "role": "assistant", "content": content}}


def eventually(predicate, description, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError(f"Timed out: {description}")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, IsADirectoryError):
        return {}


def relay_process(root, directory):
    sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
    sys.stdout = open(1, "w", encoding="utf-8", buffering=1, closefd=False)
    faults = read_json(root / "faults.json")
    release, finished = threading.Event(), threading.Event()
    history_calls = 0

    def discover(command, **kwargs):
        if command != ["claude", "agents", "--json"]:
            raise AssertionError(f"Unexpected executable: {command}")
        count = read_json(root / "discovery.json").get("count", 0) + 1
        store(root / "discovery.json", {"count": count})
        if count != 1:
            raise AssertionError("Already bound relay repeated CLI discovery")
        return subprocess.CompletedProcess(command, 0, (root / "rows.json").read_text(), "")

    def history(session_id, *, directory):
        nonlocal history_calls
        history_calls += 1
        if session_id != SESSION_ID or directory != str(root):
            raise AssertionError("SDK history read escaped the exact bound target")
        messages = read_json(root / "history.json")
        control = read_json(root / "history-control.json")
        fault = control.get("fault")
        if faults.get("late") and history_calls > 1:
            store(root / "blocked.json", {})
            if not release.wait(5):
                raise RuntimeError("Final-output barrier was never released")
            if faults["late"] == "target":
                fault = "target_loss"
                control = {"messages": []}
            else:
                return [sdk_message("late", "Output observed after records closed")]
        if fault == "target_loss":
            messages = control["messages"]
            row = read_json(root / "rows.json")[0]
            path = root / "config" / "sessions" / f"{row['pid']}.json"
            store(path, {**read_json(path), "procStart": "stale"})
        elif fault == "unexpected":
            raise RuntimeError("SDK boundary failed unexpectedly")
        return messages

    def wrap(name, replacement):
        original = getattr(claude_connection.Connection, name)
        stack.enter_context(patch.object(claude_connection.Connection, name,
            lambda self, *args, **kwargs: replacement(original, self, *args, **kwargs)))

    def close_records(original, connection):
        if faults.get("record"):
            path = directory / "outbox.json"
            path.unlink()
            path.mkdir()  # The real atomic outbox replacement must fail.
        return original(connection)

    def flush(original, connection):
        if faults.get("late") and connection.state.get("status") == "closed":
            release.set()
            if not finished.wait(3):
                raise RuntimeError("Late worker did not finish")
        return original(connection)

    def worker(original, connection, work):
        try:
            return original(connection, work)
        finally:
            if work.__name__ == "_history_loop":
                finished.set()

    def history_loop(original, connection):
        original(connection)
        if faults.get("late") == "worker":
            raise RuntimeError("History worker failed during final output")

    def control_loop(original, connection):
        if faults.get("main"):
            raise RuntimeError("Owner control loop failed")
        return original(connection)

    def signal_request(original, connection):
        original_set, callback_thread, calls = connection.stop.set, threading.get_ident(), []
        def guarded_set():
            if threading.get_ident() == callback_thread:
                calls.append(True)
            else:
                original_set()  # Concurrent worker checkpoints remain real.
        with patch.object(connection.stop, "set", side_effect=guarded_set):
            original(connection)
        store(root / "signal.json", {"flag": connection.owner_disconnected,
              "event_sets_in_handler": len(calls)})

    inbox_exit = claude_connection.ReturnInbox.__exit__
    inbox_peer = claude_connection.ReturnInbox._peer

    def peer_ready(inbox, connection):
        inbox_peer(inbox, connection)
        if faults.get("inbox"):
            store(root / "active.json", {})

    def close_inbox(inbox, *args):
        active, listener = inbox._active, inbox._listener
        if faults.get("inbox"):
            class CloseFailure:
                def shutdown(self, how):
                    active.shutdown(how)

                def close(self):
                    active.close()
                    raise OSError("Active socket close failed")
            inbox._active = CloseFailure()
        try:
            return inbox_exit(inbox, *args)
        finally:
            if faults.get("inbox"):
                store(root / "cleanup.json", {"active": active.fileno(),
                    "listener": listener.fileno(), "path_exists": inbox._path.exists()})

    with ExitStack() as stack:
        stack.enter_context(patch.object(subprocess, "run", side_effect=discover))
        stack.enter_context(patch.object(claude_history, "get_session_messages", side_effect=history))
        for name, replacement in (("_close_records", close_records), ("_flush_output", flush),
                ("_worker", worker), ("_control_loop", control_loop)):
            wrap(name, replacement)
        if faults.get("late") == "worker":
            # Preserve the worker name for the actual worker-completion barrier.
            original = claude_connection.Connection._history_loop
            def _history_loop(connection):
                history_loop(original, connection)
            stack.enter_context(patch.object(claude_connection.Connection, "_history_loop", _history_loop))
        if faults.get("signal"):
            wrap("_request_owner_disconnect", signal_request)
        stack.enter_context(patch.object(claude_connection.ReturnInbox, "_peer", peer_ready))
        stack.enter_context(patch.object(claude_connection.ReturnInbox, "__exit__", close_inbox))
        code = claude.main(["connect", "--session", SESSION_ID, "--run-dir", str(directory)])
    os._exit(code)


def foreign_send(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(path)
        try:
            connection.sendall(b'{"type":"control"}\n')
        except OSError:
            pass


class PeerFixture:
    """The parent PID is the selected existing peer; a child runs the relay."""
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="claude-test-")
        self.root = Path(self.temporary.name)
        self.config = self.root / "config"
        (self.config / "sessions").mkdir(parents=True)
        self.inbox = self.root / "peer.sock"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.inbox))
        self.listener.listen(32)
        self.listener.settimeout(0.1)
        pid = os.getpid()
        start = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        machine = Path("/etc/machine-id").read_text().strip()
        domain = f"linux:{machine}:{os.readlink('/proc/self/ns/pid')}"
        self.row = {"pid": pid, "cwd": str(self.root), "sessionId": SESSION_ID,
                    "startedAt": 1, "status": "idle", "name": "Fixture"}
        self.registry = {**self.row, "procStart": start, "pidDomain": domain,
                         "version": "2.1.299", "peerProtocol": 1,
                         "messagingSocketPath": str(self.inbox)}
        self.registry_path = self.config / "sessions" / f"{pid}.json"
        store(self.registry_path, self.registry)
        store(self.root / "rows.json", [self.row])
        store(self.root / "history.json", [])
        self.frames = []
        self.transmissions = 0
        self.transports_at_receive = []
        self.auth = []
        self.errors = queue.Queue()
        self.mode = "read"
        self.held = threading.Event()
        self.release = threading.Event()
        self.closed = threading.Event()
        self.relay = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            while not self.closed.is_set():
                try:
                    connection, _ = self.listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(4)
                    chunks = []
                    first_states = {}
                    while chunk := connection.recv(65536):
                        if not chunks:
                            self.transmissions += 1
                            if self.relay:
                                first_states = {key: item["transport"] for key, item in
                                    read_json(self.relay.directory / "outbox.json").items()}
                        chunks.append(chunk)
                        if self.mode == "cut":
                            self.held.set()
                            connection.shutdown(socket.SHUT_RDWR)
                            break
                        if self.mode == "hold":
                            self.held.set()
                            self.release.wait(8)
                    if self.mode == "cut":
                        continue
                    for line in b"".join(chunks).splitlines():
                        frame = json.loads(line)
                        (self.auth if frame["type"] == "auth" else self.frames).append(frame)
                        if frame["type"] == "user":
                            self.transports_at_receive.append(first_states.get(frame["uuid"]))
        except (OSError, ValueError) as error:
            if not self.closed.is_set():
                self.errors.put(error)

    def client(self):
        return NativeClient(self.config)

    def bind(self):
        with patch.object(subprocess, "run", side_effect=lambda command, **kwargs:
                subprocess.CompletedProcess(command, 0, (self.root / "rows.json").read_text(), "")):
            return self.client().bind(SESSION_ID)

    def start(self, *, drain=True, terminal=False, faults=None):
        if faults:
            store(self.root / "faults.json", faults)
        self.relay = RelayFixture(self, drain=drain, terminal=terminal)
        return self.relay

    def close(self):
        if self.relay:
            self.relay.close()
        self.closed.set()
        self.release.set()
        self.listener.close()
        self.thread.join(1)
        self.temporary.cleanup()


class RelayFixture:
    def __init__(self, peer, *, drain, terminal):
        self.peer = peer
        self.directory = peer.root / "connection"
        self.events = []
        self.partial = []
        self.reader = None
        if terminal:
            self.control, input_fd = pty.openpty()
        else:
            input_fd, self.control = os.pipe()
        self.output, output_fd = os.pipe()
        code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                "from test_claude import relay_process; "
                "relay_process(Path(sys.argv[2]), Path(sys.argv[3]))")
        self.process = subprocess.Popen([sys.executable, "-c", code, str(Path(__file__).parent),
            str(peer.root), str(self.directory)], stdin=input_fd, stdout=output_fd,
            env={**os.environ, "CLAUDE_CONFIG_DIR": str(peer.config)})
        os.close(input_fd)
        os.close(output_fd)
        if drain:
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()

    def _read(self):
        with os.fdopen(self.output, "rb", closefd=False) as stream:
            for line in stream:
                try:
                    self.events.append(json.loads(line))
                except ValueError:
                    self.partial.append(line)

    def raw(self, data):
        view = memoryview(data)
        while view:
            view = view[os.write(self.control, view):]

    def command(self, **command):
        self.raw((json.dumps(command, ensure_ascii=False) + "\n").encode())

    def event(self, kind, **fields):
        return eventually(lambda: next((event for event in list(self.events)
            if event.get("type") == kind and all(event.get(k) == v for k, v in fields.items())), None),
            f"{kind} {fields}")

    def connected(self):
        return self.event("connected")

    def journal(self):
        path = self.directory / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def state(self):
        return read_json(self.directory / "connection.json")

    def finish(self, expected=0):
        try:
            self.process.wait(6)
        except subprocess.TimeoutExpired as error:
            raise AssertionError("Relay failed to terminate") from error
        if self.reader:
            self.reader.join(1)
        if self.process.returncode != expected:
            raise AssertionError(f"Relay exit {self.process.returncode}: {self.events}")
        return self.state()

    def close(self):
        if self.control is not None:
            os.close(self.control)
            self.control = None
        self.peer.release.set()
        try:
            self.process.wait(2)
        except subprocess.TimeoutExpired:
            self.process.terminate()  # Only this test-owned relay process.
            self.process.wait(2)
        if self.reader:
            self.reader.join(1)
        os.close(self.output)


def peer_write(peer, address, content=None, *, message_id=None, raw=None):
    if raw is None:
        source = "uds:" + str(peer.inbox)
        raw = (json.dumps({"msgV": 1, "msg_id": message_id or str(uuid.uuid4()),
            "type": "user", "from": source, "message": {"role": "user",
            "content": f'<cross-session-message from="{source}" from-name="Claude">\n'
                       f'{content}\n</cross-session-message>'}}, ensure_ascii=False) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(4)
        connection.connect(unquote(address[4:]))
        try:
            connection.sendall(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Rejected inbound frames can close before the sender finishes.


def peer_notice(peer, address, *, message_id=None, auth=False, **fields):
    frame = {"msgV": 1, "msg_id": message_id or str(uuid.uuid4()), "type": "control",
             "action": "peer_message_status", "from": "uds:" + str(peer.inbox), **fields}
    prefix = json.dumps({"type": "auth", "token": "a" * 32}) + "\n" if auth else ""
    peer_write(peer, address, raw=(prefix + json.dumps(frame) + "\n").encode())


@unittest.skipUnless(sys.platform == "linux", "Real SO_PEERCRED/proc identity require Linux")
class ClaudeConnectionContracts(unittest.TestCase):
    def peer(self):
        peer = PeerFixture()
        self.addCleanup(peer.close)
        return peer

    def assert_journal(self, relay):
        journal = relay.journal()
        self.assertEqual([event["seq"] for event in journal], list(range(1, len(journal) + 1)))
        self.assertEqual(relay.state()["seq"], len(journal))
        closed = [index for index, event in enumerate(journal) if event["type"] == "closed"]
        self.assertEqual(len(closed), 1)
        self.assertTrue(all(event["type"] == "error" for event in journal[closed[0] + 1:]))
        return journal

    def test_many_to_many_native_and_history_output_survives_followups(self):
        peer = self.peer()
        old = sdk_message("old", "Already present")
        store(peer.root / "history.json", [old])
        relay = peer.start()
        connected = relay.connected()
        address = connected["reply_address"]
        peer_write(peer, address, "Unsolicited progress")
        relay.event("message", content="Unsolicited progress", source="peer")
        tasks = ("Review the implementation.\n한글 <literal>", "Also inspect shutdown.",
                 "Continue using the same context.")
        for text in tasks[:2]:
            relay.command(type="send", message=text)
        eventually(lambda: len(peer.frames) == 2, "two native inputs")
        progress = sdk_message("progress", "한글 progress\n<literal>")
        store(peer.root / "history.json", [old, progress])
        relay.event("message", content="한글 progress\n<literal>", source="assistant")
        relay.command(type="send", message=tasks[2])
        question_id = str(uuid.uuid4())
        peer_write(peer, address, "Which boundary should I focus on?", message_id=question_id)
        relay.event("message", uuid=question_id)
        peer_write(peer, address, "Which boundary should I focus on?", message_id=question_id)
        final = sdk_message("final", "Both instructions converge in this result.")
        store(peer.root / "history.json", [old, progress, final])
        relay.event("message", content="Both instructions converge in this result.")
        eventually(lambda: len(peer.frames) == 3, "follow-up native input")
        eventually(lambda: len(read_json(relay.directory / "outbox.json")) == 3 and
                   all(item["transport"] == "written" for item in
                       read_json(relay.directory / "outbox.json").values()), "three durable writes")
        outbox = read_json(relay.directory / "outbox.json")
        original_id = next(iter(outbox))
        receipts = []
        for status in ("held", "denied", "expired", "delivered", "refused", "dropped"):
            fields = {"status": status, "orig_msg_id": original_id, "reason": "Native reason 한글"}
            if status == "expired":
                fields["status_detail"] = "refused"
            if status == "refused":
                fields["orig_msg_id"] = str(uuid.uuid4())  # No outbox entry is required.
            if status == "dropped":
                fields.update(drop_reason="queue-full", dropped_msg_ids=[original_id, str(uuid.uuid4())])
            receipt_id = str(uuid.uuid4())
            peer_notice(peer, address, message_id=receipt_id, auth=True,
                        secret="Not a public field", **fields)
            receipts.append(relay.event("delivery_status", uuid=receipt_id))
            self.assertEqual(receipts[-1], {"type": "delivery_status", "source": "peer",
                "uuid": receipt_id, "seq": receipts[-1]["seq"], "connection_id": connected["connection_id"],
                "session_id": SESSION_ID, **fields})
        peer_notice(peer, address, message_id=receipt_id, **fields)  # Same receipt is not repeated.
        peer_write(peer, address, "Ordinary peer output after receipts")
        relay.event("message", content="Ordinary peer output after receipts")  # Receive fence before close.
        relay.command(type="disconnect")
        state = relay.finish()
        journal = self.assert_journal(relay)
        messages = [event for event in journal if event["type"] == "message"]
        self.assertEqual(len(messages), 5)
        self.assertEqual([event for event in journal if event["type"] == "delivery_status"], receipts)
        self.assertEqual(read_json(relay.directory / "outbox.json"), outbox)
        self.assertEqual(len([item for item in messages if item.get("uuid") == question_id]), 1)
        self.assertIn(old["uuid"], state["cursor"]["seen"])
        self.assertIn(progress["uuid"], state["cursor"]["seen"])
        self.assertEqual(state["cursor"]["last_uuid"], final["uuid"])
        self.assertEqual([frame["message"]["content"] for frame in peer.frames], [
            f'<cross-session-message from="{address}" from-name="Codex">\n{text}\n</cross-session-message>'
            for text in tasks])
        self.assertTrue(all(frame["from"] == address and frame["session_id"] == SESSION_ID
                            and "codex-reply" not in frame["message"]["content"] for frame in peer.frames))
        self.assertEqual(len(peer.transports_at_receive), 3)
        self.assertTrue(set(peer.transports_at_receive) <= {"write_started", "written"})
        self.assertFalse(Path(unquote(address[4:])).exists())
        self.assertTrue(peer.inbox.exists())
        self.assertFalse(relay.partial)
        self.assertEqual(read_json(peer.root / "discovery.json")["count"], 1)

    def test_exact_existing_target_unavailability_change_and_owner_shutdown(self):
        peer = self.peer()
        target = peer.bind()
        self.assertEqual(target.pid, os.getpid())
        self.assertEqual(target.proc_start, peer.registry["procStart"])
        self.assertEqual(target.boot_id, Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        self.assertEqual(target.started_at, peer.registry["startedAt"])
        peer.registry_path.write_bytes(b'{"sessionId":')
        started = time.monotonic()
        with self.assertRaises(ClaudeError) as caught:
            peer.client().validate(target)
        self.assertEqual(caught.exception.code, "session_unavailable")
        self.assertGreaterEqual(time.monotonic() - started, 0.03, "Partial JSON was not retried")
        self.assertLess(time.monotonic() - started, 1, "Partial registry retry was unbounded")
        store(peer.registry_path, peer.registry)
        store(peer.root / "rows.json", [])
        relay = peer.start()
        relay.finish(expected=3)
        self.assertEqual(relay.events[0]["error"]["code"], "session_unavailable")
        self.assertFalse(relay.directory.exists())
        for cause in ("lost", "session", "replaced", "duplicate", "eof", "pty", "signal", "captured_loss", "worker_failure"):
            with self.subTest(cause=cause):
                peer = self.peer()
                relay = peer.start(terminal=cause == "pty", faults={"signal": cause == "signal"})
                address = relay.connected()["reply_address"]
                if cause == "lost":
                    peer.registry["startedAt"] += 1  # Same live PID/session, different incarnation.
                    store(peer.registry_path, peer.registry)
                elif cause == "session":
                    store(peer.registry_path, {**peer.registry, "sessionId": str(uuid.uuid4())})
                elif cause == "replaced":
                    peer.inbox.unlink()
                    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.addCleanup(replacement.close)
                    replacement.bind(str(peer.inbox))
                    replacement.listen(16)
                elif cause == "duplicate":
                    duplicate = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
                    def stop_duplicate():
                        duplicate.terminate()
                        duplicate.wait(2)
                    self.addCleanup(stop_duplicate)
                    start = Path(f"/proc/{duplicate.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
                    store(peer.config / "sessions" / f"{duplicate.pid}.json",
                          {**peer.registry, "pid": duplicate.pid, "procStart": start})
                elif cause in {"eof", "pty"}:
                    os.close(relay.control)
                    relay.control = None
                elif cause == "signal":
                    relay.process.send_signal(signal.SIGTERM)
                elif cause == "captured_loss":
                    accepted = sdk_message("accepted", "Accepted before the peer disappeared")
                    store(peer.root / "history.json", [accepted])
                    relay.event("message", content="Accepted before the peer disappeared")
                    accepted_cursor = relay.state()["cursor"]
                    captured = sdk_message("last", "Captured before the peer disappeared")
                    store(peer.root / "history-control.json", {"fault": "target_loss",
                        "messages": [accepted, captured]})
                else:
                    store(peer.root / "history-control.json", {"fault": "unexpected"})
                owner_loss = cause in {"eof", "pty", "signal"}
                state = relay.finish(expected=0 if owner_loss else 1 if cause == "worker_failure" else 3)
                self.assertEqual(state["reason"], "owner_disconnected" if owner_loss else
                                 "worker_failed" if cause == "worker_failure" else "session_unavailable")
                self.assertFalse(Path(unquote(address[4:])).exists())
                self.assertTrue(peer.inbox.exists())
                journal = self.assert_journal(relay)
                if cause == "captured_loss":
                    self.assertEqual([event["content"] for event in journal if event["type"] == "message"],
                                     ["Accepted before the peer disappeared"])
                    self.assertEqual(state["cursor"], accepted_cursor)
                    self.assertNotIn(captured["uuid"], state["cursor"]["seen"])
                if cause == "signal":
                    self.assertEqual(read_json(peer.root / "signal.json"), {"flag": True, "event_sets_in_handler": 0})
                self.assertEqual(read_json(peer.root / "discovery.json")["count"], 1)

    def test_prewrite_storage_failure_and_uncertain_write_never_replay(self):
        peer = self.peer()
        target = peer.bind()
        digest = hashlib.sha256(str(peer.inbox.resolve()).encode()).hexdigest()
        key = peer.config / "sessions" / f"{target.pid}.{digest}.key"
        token = "0123456789abcdef0123456789abcdef"
        store(key, {"peerToken": token, "procStart": target.proc_start, "pidDomain": target.pid_domain})
        key.chmod(0o600)
        directory = peer.root / "callback-failure"
        directory.mkdir()
        connection = claude_connection.Connection(peer.client(), SESSION_ID, directory)
        connection.target = target
        connection.state = {"seq": 0}
        message_id = str(uuid.uuid4())
        connection.outbox[message_id] = {"message": "Must not write user bytes", "transport": "not_sent"}
        store(directory / "outbox-before-fault.json", connection.outbox)
        (directory / "outbox.json").mkdir()  # Atomic publication will fail against a real directory.
        frame = build_frame(target, message_id, connection.outbox[message_id]["message"],
                            "uds:" + str(peer.root / "return.sock"))
        with self.assertRaises(OSError) as caught:
            peer.client().send_frame(target, frame, lambda: connection._transport(message_id, "write_started"))
        connection._error(caught.exception, uuid=message_id, transport=connection.outbox[message_id]["transport"])
        self.assertEqual((connection.close_reason, connection.exit_code), ("record_unavailable", 1))
        self.assertEqual(connection.outbox[message_id]["transport"], "not_sent")
        self.assertEqual(read_json(directory / "outbox-before-fault.json"), connection.outbox)
        eventually(lambda: bool(peer.auth), "auth-only native connection")
        self.assertFalse(peer.frames)
        event = json.loads((directory / "events.jsonl").read_text())
        self.assertEqual(event["error"]["code"], "record_unavailable")
        self.assertNotIn(token, json.dumps(event))
        peer = self.peer()
        peer.mode = "cut"
        relay = peer.start()
        relay.connected()
        message_id, text = str(uuid.uuid4()), "x" * 850_000
        relay.command(type="send", uuid=message_id, message=text)
        relay.event("error", uuid=message_id, transport="delivery_unknown")
        before = read_json(relay.directory / "outbox.json")
        self.assertEqual(before[message_id]["transport"], "delivery_unknown")
        relay.command(type="send", uuid=message_id, message=text)
        relay.event("sent", uuid=message_id, transport="delivery_unknown", replayed=False)
        relay.command(type="send", uuid=message_id, message="Changed text")
        eventually(lambda: any(event.get("error", {}).get("code") == "message_conflict"
                              for event in relay.events), "UUID conflict")
        relay.command(type="disconnect")
        relay.finish()
        self.assertEqual(read_json(relay.directory / "outbox.json"), before)
        self.assertEqual(peer.transmissions, 1, "Duplicate UUID caused a second native write")
        self.assertEqual(len([event for event in self.assert_journal(relay)
                              if event["type"] == "error" and event.get("uuid") == message_id]), 2)

    def test_stdout_backpressure_preserves_journal_and_frozen_outbox_on_shutdown(self):
        peer = self.peer()
        peer.mode = "hold"
        relay = peer.start(drain=False)
        eventually(lambda: relay.state().get("status") == "connected", "connected without output reader")
        address = relay.state()["reply_address"]
        text = "Output remains in the journal. " * 15_000
        store(peer.root / "history.json", [sdk_message("large", text)])
        eventually(lambda: relay.state().get("cursor", {}).get("groups", {}).get("large", {}).get("revision") == 1,
                   "journal spooling before cursor publication")
        message_id = str(uuid.uuid4())
        relay.command(type="send", uuid=message_id, message="x" * 850_000)
        self.assertTrue(peer.held.wait(4), "Native socket did not hold an in-flight write")
        eventually(lambda: read_json(relay.directory / "outbox.json").get(message_id, {}).get("transport") == "write_started",
                   "durable prewrite state")
        started = time.monotonic()
        relay.command(type="disconnect")
        state = relay.finish()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual((state["status"], state["reason"]), ("closed", "disconnected"))
        outbox = read_json(relay.directory / "outbox.json")
        self.assertEqual(outbox[message_id]["transport"], "delivery_unknown")
        journal = self.assert_journal(relay)
        self.assertEqual([event["content"] for event in journal if event["type"] == "message"], [text])
        self.assertFalse(Path(unquote(address[4:])).exists())
        self.assertTrue(peer.inbox.exists())

        for cause in ("record", "target_record", "inbox", "main", "late_target", "late_worker"):
            with self.subTest(shutdown=cause):
                peer = self.peer()
                faults = {"record": "record" in cause, "inbox": cause == "inbox", "main": cause == "main"}
                if cause.startswith("late_"):
                    faults["late"] = cause.removeprefix("late_")
                relay = peer.start(faults=faults)
                address = relay.connected()["reply_address"]
                if cause.startswith("late_"):
                    eventually(lambda: (peer.root / "blocked.json").exists(), "in-flight SDK boundary")
                if cause == "inbox":
                    active = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.addCleanup(active.close)
                    active.connect(unquote(address[4:]))
                    active.sendall(b"{")
                    eventually(lambda: (peer.root / "active.json").exists(), "real active return socket")
                if cause == "target_record":
                    store(peer.registry_path, {**peer.registry, "startedAt": 2})
                elif cause != "main":
                    relay.command(type="disconnect")
                state = relay.finish(expected=0 if cause == "late_target" else 1)
                reason = "session_unavailable" if cause == "target_record" else "internal_error" if cause == "main" else "disconnected"
                self.assertEqual(state["reason"], reason)
                journal = self.assert_journal(relay)
                self.assertEqual(next(event["reason"] for event in journal if event["type"] == "closed"), reason)
                errors = [event["error"]["code"] for event in journal if event["type"] == "error"]
                expected_error = {"inbox": "inbox_unavailable", "main": "internal_error",
                    "late_target": "session_unavailable", "late_worker": "worker_failed"}.get(cause, "record_unavailable")
                self.assertIn(expected_error, errors)
                if cause.startswith("late_"):
                    closed_index = next(index for index, event in enumerate(journal) if event["type"] == "closed")
                    self.assertTrue(any(event.get("error", {}).get("code") == expected_error
                                        for event in journal[closed_index + 1:]))
                    self.assertFalse(any(event["type"] == "message" for event in journal))
                if cause == "inbox":
                    self.assertEqual(read_json(peer.root / "cleanup.json"),
                                     {"active": -1, "listener": -1, "path_exists": False})
                self.assertEqual(relay.events, journal, "Caller must drain errors after closed until process exit")
                self.assertFalse(Path(unquote(address[4:])).exists())
                self.assertTrue(peer.inbox.exists())

    def test_assistant_revisions_empty_reads_and_compaction_keep_cursor_evidence(self):
        peer = self.peer()
        target = peer.bind()
        baseline_uuid = str(uuid.uuid4())
        rows = [sdk_message("answer", "Old draft", record_uuid=baseline_uuid)]
        with patch.object(claude_history, "get_session_messages", side_effect=lambda *args, **kwargs: rows):
            cursor = claude_history.capture_cursor(target)
            second = sdk_message("answer", "ha")
            third = sdk_message("answer", "ha")
            hidden = sdk_message("hidden", private=True)
            rows[:] = [sdk_message("answer", "Draft ", record_uuid=baseline_uuid), second, third,
                       hidden]
            result = claude_history.observe_messages(target, cursor)
            self.assertEqual([(event["content"], event["revision"]) for event in result["messages"]], [("Draft haha", 1)])
            cursor = result["cursor"]
            rows[:] = [sdk_message("answer", "Outdated", record_uuid=baseline_uuid),
                       sdk_message("answer", "Final ", record_uuid=baseline_uuid), second, third, hidden]
            result = claude_history.observe_messages(target, cursor)
            self.assertEqual([(event["content"], event["revision"]) for event in result["messages"]], [("Final haha", 2)])
            cursor = result["cursor"]
            rows.clear()
            result = claude_history.observe_messages(target, cursor)
            self.assertEqual(result, {"cursor": cursor, "messages": [], "history_gap": False})
            rows[:] = [sdk_message("answer", record_uuid=baseline_uuid, private=True),
                       sdk_message("answer", record_uuid=second["uuid"], private=True),
                       sdk_message("answer", record_uuid=third["uuid"], private=True), hidden]
            result = claude_history.observe_messages(target, cursor)
            self.assertEqual([(event["content"], event["revision"]) for event in result["messages"]], [("", 3)])
            cursor = result["cursor"]
            self.assertFalse(claude_history.observe_messages(target, cursor)["messages"])
            rows[:] = [sdk_message("replacement", "After compaction")]
            result = claude_history.observe_messages(target, cursor)
            self.assertTrue(result["history_gap"])
            self.assertEqual(result["messages"][0]["content"], "After compaction")
            self.assertEqual(result["cursor"]["groups"]["answer"]["revision"], 3)
            self.assertNotIn("private reasoning", json.dumps(result))
            rows[0]["session_id"] = str(uuid.uuid4())
            with self.assertRaises(claude_history.HistoryError):
                claude_history.observe_messages(target, result["cursor"])

    def test_invalid_owner_frames_and_foreign_peers_do_not_poison_connection(self):
        peer = self.peer()
        relay = peer.start()
        address = relay.connected()["reply_address"]
        relay.raw(b'\xff\n{\n{"type":"send","message":null}\n' + b"x" * 1_000_001 + b"\n")
        eventually(lambda: len([event for event in relay.events if event.get("error", {}).get("code") == "invalid_command"]) == 3,
                   "malformed control rejection")
        eventually(lambda: any(event.get("error", {}).get("code") == "command_too_large" for event in relay.events), "oversized control rejection")
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "from test_claude import foreign_send; foreign_send(sys.argv[2])")
        foreign = subprocess.Popen([sys.executable, "-c", code, str(Path(__file__).parent), unquote(address[4:])])
        self.assertEqual(foreign.wait(3), 0)
        eventually(lambda: any(event.get("error", {}).get("code") == "foreign_peer" for event in relay.events), "foreign PID rejection")
        for raw in (b"\xff\n", b"{\n", b"x" * 1_000_001 + b"\n"):
            peer_write(peer, address, raw=raw)
        eventually(lambda: len([event for event in relay.events if event.get("error", {}).get("code") == "invalid_peer_frame"]) == 3,
                   "malformed peer rejection")
        for fields in ({"status": "unknown"}, {"status": "held", "status_detail": "refused"},
                       {"status": "expired", "orig_msg_id": "invalid"},
                       {"status": "dropped", "drop_reason": "unknown"},
                       {"status": "dropped", "dropped_msg_ids": [None]}):
            peer_notice(peer, address, **fields)
        eventually(lambda: len([event for event in relay.events if event.get("error", {}).get("code") == "invalid_peer_frame"]) == 8,
                   "known malformed receipt rejection")
        peer_notice(peer, address, action="other", auth=True, status="secret")
        peer_write(peer, address, raw=(json.dumps({"type": "auth", "token": "b" * 32}) + "\n").encode())
        relay.command(type="send", message="Still usable after rejected input")
        eventually(lambda: len(peer.frames) == 1, "valid control after rejection")
        peer_write(peer, address, "Still usable after rejected peers")
        relay.event("message", content="Still usable after rejected peers")
        relay.command(type="disconnect")
        relay.finish()
        journal = self.assert_journal(relay)
        self.assertEqual(len([event for event in journal if event["type"] == "message"]), 1)
        self.assertFalse(any(event["type"] == "delivery_status" for event in journal))
        self.assertNotIn("b" * 32, json.dumps(journal))
        self.assertFalse(relay.partial)


if __name__ == "__main__":
    unittest.main()
