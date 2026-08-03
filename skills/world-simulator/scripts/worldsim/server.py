from __future__ import annotations

import json
import mimetypes
import pathlib
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .store import WorldSimError, list_turns, public_state, submit_input


WEB_ROOT = pathlib.Path(__file__).resolve().parents[2] / "assets" / "web"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
}


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _int_query(query: dict[str, list[str]], key: str) -> int | None:
    values = query.get(key)
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError as error:
        raise WorldSimError(f"{key} must be an integer.") from error


def make_handler(session_path: pathlib.Path) -> type[BaseHTTPRequestHandler]:
    asset_root = (session_path / "assets").resolve()

    class WorldHandler(BaseHTTPRequestHandler):
        server_version = "WorldSimulator/1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Any) -> None:
            self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise WorldSimError("Invalid Content-Length.") from error
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WorldSimError("Request body must be a JSON object.") from error
            if not isinstance(payload, dict):
                raise WorldSimError("Request body must be a JSON object.")
            return payload

        def _serve_static(self, relative: str) -> None:
            target = WEB_ROOT / relative
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self._send(HTTPStatus.OK, body, content_type)

        def _serve_session_asset(self, encoded_path: str) -> None:
            relative = urllib.parse.unquote(encoded_path).lstrip("/")
            target = (asset_root / relative).resolve()
            try:
                target.relative_to(asset_root)
            except ValueError as error:
                raise WorldSimError("Invalid session asset path.") from error
            if not target.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Session asset not found."})
                return
            body = target.read_bytes()
            self._send(HTTPStatus.OK, body, mimetypes.guess_type(target.name)[0] or "application/octet-stream")

        def do_GET(self) -> None:
            try:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path in STATIC_FILES:
                    self._serve_static(STATIC_FILES[parsed.path])
                    return
                if parsed.path.startswith("/session-assets/"):
                    self._serve_session_asset(parsed.path.removeprefix("/session-assets/"))
                    return
                if parsed.path == "/api/state":
                    self._send_json(HTTPStatus.OK, public_state(session_path))
                    return
                if parsed.path == "/api/turns":
                    query = urllib.parse.parse_qs(parsed.query)
                    self._send_json(
                        HTTPStatus.OK,
                        list_turns(
                            session_path,
                            before=_int_query(query, "before"),
                            after=_int_query(query, "after"),
                            limit=_int_query(query, "limit") or 30,
                        ),
                    )
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            except WorldSimError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Server error."})

        def do_POST(self) -> None:
            try:
                parsed = urllib.parse.urlparse(self.path)
                payload = self._read_json()
                if parsed.path == "/api/input":
                    text = payload.get("text")
                    if not isinstance(text, str):
                        raise WorldSimError("text must be a string.")
                    self._send_json(HTTPStatus.CREATED, submit_input(session_path, text))
                    return
                if parsed.path == "/api/begin":
                    state = public_state(session_path)
                    if not state["can_begin"]:
                        raise WorldSimError("Finish at least one Studio turn before beginning the adventure.")
                    text = payload.get("text", "Begin the adventure.")
                    if not isinstance(text, str):
                        raise WorldSimError("text must be a string.")
                    self._send_json(HTTPStatus.CREATED, submit_input(session_path, text, kind="begin"))
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            except WorldSimError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Server error."})

    return WorldHandler


def serve(
    session_path: pathlib.Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    server: ThreadingHTTPServer | None = None
    last_error: OSError | None = None
    for candidate in range(port, port + 21):
        try:
            server = ThreadingHTTPServer((host, candidate), make_handler(session_path))
            break
        except OSError as error:
            last_error = error
    if server is None:
        raise WorldSimError(f"Could not bind a local server port: {last_error}")
    url = f"http://{host}:{server.server_address[1]}"
    print(json.dumps({"url": url, "session_path": str(session_path.resolve())}, ensure_ascii=False), flush=True)
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
