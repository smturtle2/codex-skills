from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType
from urllib.parse import parse_qs, urlparse


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "moru.py"
SPEC = importlib.util.spec_from_file_location("moru", SCRIPT)
assert SPEC and SPEC.loader
moru = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = moru
SPEC.loader.exec_module(moru)


class BridgeHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, bytes, str | None]] = []

    def log_message(self, *_: object) -> None:
        return

    def send_payload(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        BridgeHandler.requests.append(("GET", self.path, b"", self.headers.get("Authorization")))
        path = urlparse(self.path).path
        if path == "/v1/health":
            self.send_payload({"bridge_id": "bridge-a", "running": True})
            return
        if path == "/v1/events":
            self.send_payload(
                {
                    "bridge_id": "bridge-a",
                    "events": [{"id": 7, "type": "chat", "player_uuid": "d290f1ee-6c54-4b01-90e6-d701748f0851"}],
                }
            )
            return
        self.send_payload({"messages": []})

    def do_POST(self) -> None:
        content_length = int(self.headers["Content-Length"])
        body = self.rfile.read(content_length)
        BridgeHandler.requests.append(("POST", self.path, body, self.headers.get("Authorization")))
        self.send_payload({"ok": True, "result": "sent_public"})


class MoruClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BridgeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.profile_path = pathlib.Path(self.temp_dir.name) / "moru.toml"
        self.profile_path.write_text(
            "[bridge]\n"
            f'url = "http://127.0.0.1:{self.server.server_port}"\n'
            'token_env = "TEST_MORU_TOKEN"\n'
            "[context]\n"
            f'server_root = "{self.temp_dir.name}"\n',
            encoding="utf-8",
        )
        self.previous_token = os.environ.get("TEST_MORU_TOKEN")
        os.environ["TEST_MORU_TOKEN"] = "test-token"
        BridgeHandler.requests.clear()

    def tearDown(self) -> None:
        if self.previous_token is None:
            os.environ.pop("TEST_MORU_TOKEN", None)
        else:
            os.environ["TEST_MORU_TOKEN"] = self.previous_token
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def profile(self) -> object:
        return moru.load_profile(str(self.profile_path))

    def test_health_sends_bearer_token(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            moru.command_health(self.profile(), object())
        self.assertEqual(BridgeHandler.requests[0][3], "Bearer test-token")

    def test_wait_persists_event_cursor(self) -> None:
        args = type("Args", (), {"cursor": None, "after": None, "limit": 16, "wait_seconds": 0})()
        with contextlib.redirect_stdout(io.StringIO()):
            moru.command_wait(self.profile(), args)
        cursor = json.loads((self.profile_path.parent / ".moru-cursor.json").read_text(encoding="utf-8"))
        self.assertEqual(cursor, {"bridge_id": "bridge-a", "after": 7})
        query = parse_qs(urlparse(BridgeHandler.requests[0][1]).query)
        self.assertEqual(query["after"], ["0"])

    def test_direct_response_requires_text(self) -> None:
        args = type("Args", (), {"public": None, "direct": "d290f1ee-6c54-4b01-90e6-d701748f0851", "direct_message": None})()
        with self.assertRaisesRegex(moru.MoruError, "require a message"):
            moru.command_respond(self.profile(), args)

    def test_direct_response_encodes_target_and_message(self) -> None:
        args = type(
            "Args",
            (),
            {
                "public": None,
                "direct": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                "direct_message": "Moru: 안녕하세요, 무엇을 도와드릴까요?",
            },
        )()
        with contextlib.redirect_stdout(io.StringIO()):
            moru.command_respond(self.profile(), args)
        request = BridgeHandler.requests[0]
        self.assertEqual(request[0:2], ("POST", "/v1/actions"))
        form = parse_qs(request[2].decode("utf-8"))
        self.assertEqual(form["type"], ["direct"])
        self.assertEqual(form["player_uuid"], [args.direct])
        self.assertEqual(form["message"], [args.direct_message])

    def test_run_command_encodes_exact_console_command(self) -> None:
        args = type("Args", (), {"console_command": "/say Moru is online"})()
        with contextlib.redirect_stdout(io.StringIO()):
            moru.command_run_command(self.profile(), args)
        request = BridgeHandler.requests[0]
        self.assertEqual(request[0:2], ("POST", "/v1/actions"))
        form = parse_qs(request[2].decode("utf-8"))
        self.assertEqual(form["type"], ["command"])
        self.assertEqual(form["command"], [args.console_command])
        self.assertNotIn("message", form)

    def test_run_command_requires_text(self) -> None:
        args = type("Args", (), {"console_command": "   "})()
        with self.assertRaisesRegex(moru.MoruError, "require command text"):
            moru.command_run_command(self.profile(), args)

    def test_snapshot_omits_management_secrets(self) -> None:
        (pathlib.Path(self.temp_dir.name) / "server.properties").write_text(
            "difficulty=hard\nmanagement-server-secret=never-show\nmax-players=10\n", encoding="utf-8"
        )
        args = type("Args", (), {"server_root": None})()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            moru.command_snapshot(self.profile(), args)
        snapshot = json.loads(captured.getvalue())
        self.assertEqual(snapshot["server_properties"], {"difficulty": "hard", "max-players": "10"})


if __name__ == "__main__":
    unittest.main()
