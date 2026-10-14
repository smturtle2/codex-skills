"""Contracts for live inboxes, durable requests, and recorded replies."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/claude/scripts"))
import claude
import claude_history
from claude_native import ClaudeError, NativeClient, Target

SESSION_ID = "11111111-1111-4111-8111-111111111111"
REQUEST_ID = "22222222-2222-4222-8222-222222222222"


def make_target(root):
    return Target(SESSION_ID, str(root), os.getpid(), "fixture", "fixture",
                  str(root / "inbox.sock"), "2.1.299", 1)


def sdk_message(message_id, text=None, *, record_uuid=None, thinking=None, session_id=SESSION_ID):
    content = [{"type": "thinking", "thinking": thinking}] if thinking is not None else []
    if text is not None:
        content.append({"type": "text", "text": text})
    return SimpleNamespace(type="assistant", uuid=record_uuid or str(uuid.uuid4()),
        session_id=session_id, message={"id": message_id, "role": "assistant", "content": content})


def reply(body, request_id=REQUEST_ID):
    return f'<codex-reply request-id="{request_id}">{body}</codex-reply>'

@unittest.skipUnless(sys.platform == "linux", "Linux inbox adapter")
class ClaudeRequestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.target = make_target(self.root)
        self.run_dir = self.root / "run"
        self.message = "한글과 <literal> content stay verbatim.\n"
        self.message_file = self.root / "message.txt"
        self.message_file.write_text(self.message, encoding="utf-8")
        self.messages, self.frames = [], []
        self.native = Mock(spec=NativeClient)
        self.native.bind.return_value = self.target
        self.native.validate.return_value = {"status": "idle"}
        self.native.input_observed.return_value = False
        self.native.send_frame.side_effect = self.post_frame
        self.enterContext(patch.object(claude, "NativeClient", return_value=self.native))
        self.sdk = self.enterContext(patch.object(claude_history, "get_session_messages",
            side_effect=lambda *args, **kwargs: self.messages))

    def post_frame(self, target, frame, before_write):
        before_write()
        self.frames.append(frame)

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = claude.main(list(map(str, args)))
        return code, json.loads(output.getvalue())

    def send(self, *, expect_reply=True, default_dir=False):
        args = ["send", "--session", SESSION_ID, "--message-file", self.message_file]
        if expect_reply:
            args.append("--expect-reply")
        if not default_dir:
            args.extend(["--run-dir", self.run_dir])
        return self.invoke(*args)

    def saved(self):
        return json.loads((self.run_dir / "request.json").read_text(encoding="utf-8"))

    def test_send_input_reply_and_repeated_observation(self):
        def post(target, frame, before_write):
            before_write()
            self.assertEqual(self.saved()["transport"], "write_started")
            self.frames.append(frame)
        self.native.send_frame.side_effect = post
        code, sent = self.send()
        self.assertEqual(code, 0)
        self.assertEqual((sent["transport"], sent["input"], sent["response"]),
                         ("written", "not_observed", "not_observed"))
        self.assertEqual(self.saved()["message"], self.message)
        frame = self.frames[0]
        self.assertEqual((frame["type"], frame["session_id"], frame["from"], frame["message"]["role"]),
                         ("user", SESSION_ID, "Codex", "user"))
        self.assertEqual(frame["uuid"], sent["request_id"])
        self.assertTrue(frame["message"]["content"].startswith('<cross-session-message from-name="Codex">\n' + self.message))
        self.assertTrue(frame["message"]["content"].endswith("\n</cross-session-message>"))
        self.native.input_observed.return_value = True
        _, received = self.invoke("read", self.run_dir)
        self.assertEqual((received["input"], received["response"]), ("observed", "not_observed"))
        self.messages.append(sdk_message("answer", reply("Result", sent["request_id"])))
        _, answered = self.invoke("read", self.run_dir)
        self.assertEqual(answered["matched_response"]["content"], "Result")
        self.assertEqual(len(self.saved()["responses"]), 1)
        _, repeated = self.send()
        self.assertEqual((repeated["request_id"], repeated["responses"]), (sent["request_id"], []))
        self.assertEqual(repeated["matched_response"], answered["matched_response"])
        self.assertEqual(len(self.frames), 1)

    def test_unavailable_target_prevents_send_and_archived_reads(self):
        self.enterContext(patch.object(subprocess, "Popen", side_effect=AssertionError("No launch")))
        unavailable = ClaudeError("session_unavailable", "Target closed")
        self.native.bind.side_effect = unavailable
        code, result = self.send()
        self.assertEqual((code, result["reason"]), (3, "session_unavailable"))
        self.assertFalse(self.run_dir.exists())
        self.sdk.assert_not_called()
        self.native.bind.side_effect = None
        self.send()
        self.sdk.reset_mock()
        self.native.validate.side_effect = unavailable
        for command in ("status", "read", "wait"):
            with self.subTest(command=command):
                args = [command, self.run_dir] + (["--timeout", "0"] if command == "wait" else [])
                code, result = self.invoke(*args)
                self.assertEqual((code, result["reason"]), (3, "session_unavailable"))
                self.assertNotIn("matched_response", result)
        self.sdk.assert_not_called()
        self.assertEqual(len(self.frames), 1)

    def test_saved_request_rejects_changed_task(self):
        self.send()
        original = self.saved()
        self.message_file.write_text("A different task", encoding="utf-8")
        code, result = self.send()
        self.assertEqual((code, result["reason"]), (1, "request_conflict"))
        self.assertEqual(self.saved(), original)
        self.assertEqual(len(self.frames), 1)

    def test_failure_recovery_keeps_context_and_never_reposts(self):
        persist = claude.save_request
        for phase, transport in (("publication", "not_sent"), ("write", "delivery_unknown"),
                                 ("persistence", "written")):
            with self.subTest(phase=phase):
                self.run_dir = self.root / phase
                self.frames.clear()
                def store(directory, state):
                    if phase == "persistence" and state["transport"] == "written":
                        raise OSError("Disk failure after writing")
                    persist(directory, state)
                    if phase == "publication":
                        raise OSError("Failure after atomic publication")
                def post(target, frame, before_write):
                    self.post_frame(target, frame, before_write)
                    if phase == "write":
                        raise ClaudeError("delivery_unknown", "Disconnected during write")
                self.native.send_frame.side_effect = post
                with patch.object(Path, "cwd", return_value=self.root), \
                        patch.object(claude, "save_request", side_effect=store):
                    code, result = self.send(default_dir=phase == "write")
                self.assertNotEqual(code, 0)
                self.run_dir = Path(result["run_dir"])
                self.assertEqual(result["request_id"], self.saved()["request_id"])
                self.assertEqual(result["transport"], transport)
                self.assertEqual((result["input"], result["response"]), ("not_observed", "not_observed"))
                self.native.send_frame.side_effect = self.post_frame
                code, recovered = self.send()
                self.assertEqual((code, recovered["request_id"]), (0, result["request_id"]))
                self.assertEqual(len(self.frames), 0 if phase == "publication" else 1)

    def test_closure_during_read_preserves_evidence_with_cursor(self):
        self.send()
        request_id = self.saved()["request_id"]
        record = sdk_message("answer", reply("Observed result", request_id))
        self.messages.append(record)
        self.native.input_observed.return_value = True
        def read_then_close(*args, **kwargs):
            self.native.validate.side_effect = ClaudeError("session_unavailable", "Closed after read")
            return self.messages
        self.sdk.side_effect = read_then_close
        code, result = self.invoke("read", self.run_dir)
        self.assertEqual((code, result["reason"]), (3, "session_unavailable"))
        saved = self.saved()
        self.assertEqual(saved["cursor"]["last_uuid"], record.uuid)
        self.assertEqual(saved["matched_response"]["content"], "Observed result")
        self.assertEqual(len(saved["responses"]), 1)
        self.assertEqual((saved["input"], saved["response"]), ("observed", "observed"))
        self.assertNotIn("matched_response", result)

    def test_wait_stops_for_reply_conflict_attention_output_or_timeout(self):
        for case in ("reply", "conflict", "attention", "output", "timeout"):
            with self.subTest(case=case):
                self.run_dir = self.root / case
                self.messages.clear()
                self.native.validate.return_value = {"status": "idle"}
                _, sent = self.send(expect_reply=case != "output")
                if case in {"reply", "conflict"}:
                    self.messages.append(sdk_message("one", reply("One", sent["request_id"])))
                if case == "conflict":
                    self.messages.append(sdk_message("two", reply("Two", sent["request_id"])))
                if case == "attention":
                    self.native.validate.return_value = {"status": "waiting"}
                if case == "output":
                    self.messages.append(sdk_message("plain", "Readable answer"))
                with patch.object(claude.time, "sleep", side_effect=AssertionError("Must return")):
                    code, result = self.invoke("wait", self.run_dir, "--timeout", 0 if case == "timeout" else 30)
                self.assertEqual(code, 0)
                self.assertEqual(result["timed_out"], case == "timeout")
                expected = {"reply": "observed", "conflict": "ambiguous", "output": "unmatched"}
                self.assertEqual(result["response"], expected.get(case, "not_observed"))

@unittest.skipUnless(sys.platform == "linux", "Local Unix inbox discovery is Linux-only")
class ClaudeNativeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config = self.root / "config"
        (self.config / "sessions").mkdir(parents=True)
        self.inbox = self.root / "inbox.sock"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.inbox))
        self.listener.listen(64)
        self.listener.settimeout(2)
        self.addCleanup(self.listener.close)
        self.pid = os.getpid()
        stat_text = Path(f"/proc/{self.pid}/stat").read_text()
        self.start = stat_text[stat_text.rfind(")") + 2:].split()[19]
        try:
            machine = Path("/etc/machine-id").read_text().strip()
        except OSError:
            machine = ""
        self.domain = f"linux:{machine}:{os.readlink('/proc/self/ns/pid')}"
        self.row = {"pid": self.pid, "cwd": str(self.root), "sessionId": SESSION_ID,
                    "startedAt": 1, "status": "idle", "kind": "interactive", "name": "Fixture"}
        self.registry = {**self.row, "procStart": self.start, "pidDomain": self.domain,
                         "version": "2.1.299", "peerProtocol": 1,
                         "messagingSocketPath": str(self.inbox)}
        self.registry_path = self.config / "sessions" / f"{self.pid}.json"
        self.write_registry()
        self.rows = [self.row]
        self.cli = self.enterContext(patch.object(subprocess, "run", side_effect=lambda command, **kwargs:
            subprocess.CompletedProcess(command, 0, json.dumps(self.rows), "")))
        self.client = NativeClient(config_dir=self.config)

    def write_registry(self):
        self.registry_path.write_text(json.dumps(self.registry), encoding="utf-8")

    def write_key(self, target, *, stale=False, mode=0o600):
        digest = hashlib.sha256(str(Path(target.inbox).resolve()).encode()).hexdigest()
        path = self.config / "sessions" / f"{target.pid}.{digest}.key"
        token = "0123456789abcdef0123456789abcdef"
        path.write_text(json.dumps({"peerToken": token, "procStart": "stale" if stale else target.proc_start,
                                   "pidDomain": target.pid_domain}), encoding="utf-8")
        path.chmod(mode)
        return token

    def frame(self):
        return {"type": "user", "session_id": SESSION_ID, "uuid": REQUEST_ID, "from": "Codex",
                "message": {"role": "user", "content": "한글 fixture\nsecond line"}}

    def receive(self, target, frame):
        received, errors = [], []
        def serve():
            try:
                while not received:
                    connection, _ = self.listener.accept()
                    with connection:
                        connection.settimeout(2)
                        chunks = []
                        while chunk := connection.recv(65536):
                            chunks.append(chunk)
                    if chunks:  # Nonwriting reachability probes are not transmissions.
                        received.append(b"".join(chunks))
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        before_write = Mock()
        try:
            self.client.send_frame(target, frame, before_write)
        finally:
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "Sender did not close the inbox connection")
        if errors:
            raise errors[0]
        before_write.assert_called_once_with()
        return received[0]

    def test_public_discovery_lists_only_live_rows_and_exposes_unusable_targets(self):
        self.rows.extend([{**self.row, "pid": None, "status": "completed"},
                          {**self.row, "pid": self.pid + 1_000_000}])
        rows = self.client.list_sessions()
        self.assertEqual([row["available"] for row in rows], [True, False])
        self.assertEqual(rows[1]["reason"], "session_unavailable")
        self.assertEqual(self.cli.call_args.args[0], ["claude", "agents", "--json"])
        self.assertEqual(self.cli.call_args.kwargs["env"]["CLAUDE_CONFIG_DIR"], str(self.config))
        self.rows = []
        with self.assertRaises(ClaudeError) as caught:
            self.client.bind(SESSION_ID)
        self.assertEqual(caught.exception.code, "session_unavailable")

    def test_real_process_identity_binds_start_namespace_machine_and_boot(self):
        target = self.client.bind(SESSION_ID)
        self.assertEqual((target.pid, target.proc_start, target.pid_domain),
                         (self.pid, self.start, self.domain))
        self.assertEqual(target.boot_id, Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        self.client.validate(target)
        for field, value in (("procStart", "stale"), ("sessionId", REQUEST_ID)):
            with self.subTest(field=field):
                self.registry[field] = value
                self.write_registry()
                with self.assertRaises(ClaudeError):
                    self.client.bind(SESSION_ID)
                self.registry[field] = self.start if field == "procStart" else SESSION_ID
        self.write_registry()
        changed = Target.from_dict({**target.to_dict(), "boot_id": str(uuid.uuid4())})
        with self.assertRaises(ClaudeError):
            self.client.validate(changed)

    def test_socket_replacement_at_same_path_invalidates_saved_target(self):
        target = self.client.bind(SESSION_ID)
        self.inbox.unlink()
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(replacement.close)
        replacement.bind(str(self.inbox))
        replacement.listen(64)
        current = self.client.bind(SESSION_ID)
        self.assertEqual(current.inbox, target.inbox)
        self.assertNotEqual((current.inbox_dev, current.inbox_ino), (target.inbox_dev, target.inbox_ino))
        with self.assertRaises(ClaudeError):
            self.client.validate(target)

    def test_actual_connected_peer_mismatch_prevents_auth_and_user_bytes(self):
        target = self.client.bind(SESSION_ID)
        with self.listener.accept()[0] as probe:  # Drain the one initial bind probe.
            self.assertEqual(probe.recv(1), b"")
        expected = Target.from_dict({**target.to_dict(), "pid": self.pid + 1})
        token = self.write_key(expected)
        before_write = Mock()
        # Isolate a peer changing after validation; SO_PEERCRED and sending remain real.
        with patch.object(self.client, "validate", return_value={}):
            with self.assertRaises(ClaudeError) as caught:
                self.client.send_frame(expected, self.frame(), before_write)
        with self.listener.accept()[0] as sending_connection:
            self.assertEqual(sending_connection.recv(1), b"")
        self.assertEqual(caught.exception.code, "session_unavailable")
        before_write.assert_not_called()
        self.assertNotIn(token, str(caught.exception))

    def test_utf8_newline_frames_send_with_optional_auth_without_ack(self):
        target = self.client.bind(SESSION_ID)
        frame = self.frame()
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                token = self.write_key(target) if authenticated else None
                raw = self.receive(target, frame)
                self.assertTrue(raw.endswith(b"\n"))
                self.assertIn("한글".encode("utf-8"), raw)
                lines = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
                self.assertEqual(lines, ([{"type": "auth", "token": token}] if token else []) + [frame])
                if token:
                    self.assertNotIn(token, json.dumps(target.to_dict()))

    def test_stale_or_insecure_key_rejects_before_user_write(self):
        target = self.client.bind(SESSION_ID)
        for stale, mode in ((True, 0o600), (False, 0o644)):
            with self.subTest(stale=stale, mode=mode):
                self.write_key(target, stale=stale, mode=mode)
                before_write = Mock()
                with self.assertRaises(ClaudeError) as caught:
                    self.client.send_frame(target, self.frame(), before_write)
                self.assertEqual(caught.exception.code, "authentication_unavailable")
                before_write.assert_not_called()

    def test_raw_input_requires_exact_uuid_session_and_main_user_record(self):
        target = self.client.bind(SESSION_ID)
        path = self.client.transcript_path(target)
        path.parent.mkdir(parents=True)
        valid = {"type": "user", "uuid": REQUEST_ID, "sessionId": SESSION_ID,
                 "isMeta": True, "message": {"role": "user", "content": "Cross-session input"}}
        invalid = [{**valid, "sessionId": REQUEST_ID}, {**valid, "type": "assistant"},
                   {**valid, "isSidechain": True}, {**valid, "uuid": SESSION_ID},
                   {**valid, "message": {"role": "assistant"}}, [REQUEST_ID]]
        path.write_text("\n".join(json.dumps(record) for record in invalid) +
                        f'\n{{"uuid":"{REQUEST_ID}"\n', encoding="utf-8")
        self.assertFalse(self.client.input_observed(target, REQUEST_ID))
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(valid) + "\n")
        self.assertTrue(self.client.input_observed(target, REQUEST_ID))

class ClaudeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.target = make_target(Path(self.enterContext(tempfile.TemporaryDirectory())))
        self.messages = []
        self.sdk = self.enterContext(patch.object(claude_history, "get_session_messages",
            side_effect=lambda *args, **kwargs: self.messages))

    def capture(self):
        self.cursor = claude_history.capture_cursor(self.target)
        self.responses = []

    def observe(self):
        result = claude_history.observe_responses(
            self.target, REQUEST_ID, self.cursor, previous_responses=self.responses)
        self.cursor = result["cursor"]
        self.responses.extend(result["responses"])
        return result

    def test_bound_session_and_baseline_filtering(self):
        self.messages = [sdk_message("old", reply("Already existed"))]
        self.capture()
        self.sdk.assert_called_with(SESSION_ID, directory=self.target.cwd)
        self.messages += [sdk_message("private", thinking=reply("Hidden reasoning")),
                          sdk_message("unrelated", "An unrelated answer")]
        result = self.observe()
        self.assertIsNone(result["matched_response"])
        self.assertTrue(result["unmatched"])
        self.assertEqual([row["text"] for row in result["responses"]], ["An unrelated answer"])
        self.assertNotIn("Hidden reasoning", json.dumps(result))
        self.messages = [sdk_message("foreign", reply("Foreign answer"),
                                     session_id=str(uuid.uuid4()))]
        with self.assertRaises(claude_history.HistoryError):
            self.observe()

    def test_grouped_reply_preserves_literal_body_and_repeated_blocks(self):
        self.capture()
        self.messages = [
            sdk_message("answer", thinking="Hidden reasoning"),
            sdk_message("answer", f'<codex-reply request-id="{REQUEST_ID}">\n한글 응답\n'),
            sdk_message("answer", "ha"), sdk_message("answer", "ha"),
            sdk_message("answer", "\n<literal>\n</codex-reply>"),
        ]
        result = self.observe()
        self.assertEqual(len(result["responses"]), 1)
        self.assertEqual(result["matched_response"]["content"], "\n한글 응답\nhaha\n<literal>\n")
        self.assertNotIn("Hidden reasoning", json.dumps(result))

    def test_marker_examples_cannot_match(self):
        self.capture()
        examples = ["```xml\n" + reply("Example") + "\n```", "> " + reply("Quoted"),
                    "Syntax: " + reply("Example"), reply("Other", str(uuid.uuid4()))]
        self.messages = [sdk_message(f"example-{i}", text) for i, text in enumerate(examples)]
        result = self.observe()
        self.assertIsNone(result["matched_response"])
        self.assertTrue(result["unmatched"])

    def test_revision_lifecycle_updates_and_withdraws_reply(self):
        record_uuid = str(uuid.uuid4())
        self.messages = [sdk_message("answer", "Draft", record_uuid=record_uuid)]
        self.capture()
        self.messages = [sdk_message("answer", "Partial", record_uuid=record_uuid),
                         sdk_message("answer", reply("Final"), record_uuid=record_uuid)]
        final = self.observe()
        self.assertEqual(final["matched_response"]["content"], "Final")
        self.assertEqual(len(final["responses"]), 1)
        self.messages = [sdk_message("answer", thinking="Private replacement",
                                     record_uuid=record_uuid)]
        withdrawn = self.observe()
        self.assertIsNone(withdrawn["matched_response"])
        self.assertEqual([row["text"] for row in withdrawn["responses"]], [""])
        self.assertNotIn("Private replacement", json.dumps(withdrawn))
        again = self.observe()
        self.assertIsNone(again["matched_response"])
        self.assertEqual(again["responses"], [])

    def test_later_second_reply_is_ambiguous(self):
        self.capture()
        self.messages = [sdk_message("one", reply("One"))]
        self.assertEqual(self.observe()["matched_response"]["content"], "One")
        self.messages.append(sdk_message("two", reply("Two")))
        conflict = self.observe()
        self.assertTrue(conflict["ambiguous"])
        self.assertIsNone(conflict["matched_response"])

    def test_empty_read_preserves_evidence_and_replaced_chain_reports_gap(self):
        self.messages = [sdk_message("baseline", "Before the request")]
        self.capture()
        self.messages.append(sdk_message("answer", reply("Observed")))
        self.observe()
        self.messages = []
        empty = self.observe()
        self.assertFalse(empty["history_gap"])
        self.assertEqual(empty["matched_response"]["content"], "Observed")
        self.assertEqual(empty["responses"], [])
        self.messages = [sdk_message("replacement", "After compaction")]
        replaced = self.observe()
        self.assertTrue(replaced["history_gap"])
        self.assertEqual(replaced["matched_response"]["content"], "Observed")


if __name__ == "__main__":
    unittest.main()
