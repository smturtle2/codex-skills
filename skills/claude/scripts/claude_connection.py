"""One foreground connection owns sending, receiving, records, and shutdown."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import select
import selectors
import signal
import sys
import tempfile
import threading
import time
import uuid

from claude_native import ClaudeError, NativeClient, ReturnInbox, build_frame


MAX_COMMAND_BYTES = 1_000_000
TERMINAL_ERRORS = {"session_unavailable", "unsupported_platform", "unsupported_protocol", "claude_not_found"}
LOCAL_FAILURES = {"record_unavailable", "inbox_unavailable", "worker_failed", "internal_error"}


def error_code(error: Exception) -> str:
    return getattr(error, "code", "record_unavailable")


def _connection_error(error: Exception) -> Exception:
    if isinstance(error, (ClaudeError, OSError)):
        return error
    return ClaudeError("internal_error", f"Unexpected connection error ({type(error).__name__})")


def _save_json(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _owner_channel(request_disconnect):
    """Own signals and terminal settings until all connection cleanup finishes."""
    previous = None
    handlers = {}
    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[number] = signal.getsignal(number)
            signal.signal(number, lambda _number, _frame: request_disconnect())
        if sys.stdin.isatty():
            import termios
            try:
                previous = termios.tcgetattr(sys.stdin.fileno())
                current = deepcopy(previous)
                current[3] &= ~(termios.ECHO | termios.ICANON)
                current[6][termios.VMIN] = 1
                current[6][termios.VTIME] = 0
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, current)
            except (OSError, termios.error):
                request_disconnect()
        yield
    finally:
        if previous is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, previous)
            except (OSError, termios.error):
                pass
        for number, handler in handlers.items():
            signal.signal(number, handler)


class Connection:
    def __init__(self, client: NativeClient, session_id: str, directory: Path | None = None):
        self.client = client
        self.session_id = session_id
        self.connection_id = uuid.uuid4().hex
        self.directory = (directory or Path.cwd() / ".codex-skills" / "claude" / self.connection_id).expanduser().resolve()
        self.stop = threading.Event()
        self.owner_disconnected = False
        self.lock = threading.RLock()
        self.incoming: queue.Queue = queue.Queue()
        self.outgoing: queue.Queue = queue.Queue()
        self.outbox: dict[str, dict] = {}
        self.state: dict = {}
        self.close_reason = "disconnected"
        self.exit_code = 0
        self.output_open = True
        self.output_reader = None
        self.output_pending = bytearray()
        self.emergency_output = bytearray()
        self.journal_end = 0
        self.journal_broken = False
        self.frozen = False
        self.peer_uuids: set[str] = set()

    def _end(self, reason: str, exit_code: int = 0) -> None:
        with self.lock:
            # Local execution/record/cleanup failures take precedence over
            # an earlier normal close or target loss, without changing why
            # shutdown originally began.
            if exit_code == 1:
                self.exit_code = 1
            if not self.stop.is_set():
                self.close_reason = reason
                if self.exit_code != 1:
                    self.exit_code = exit_code
                self.stop.set()

    def _request_owner_disconnect(self) -> None:
        # Signal callbacks must not re-enter locks or threading.Event.set().
        self.owner_disconnected = True

    def _stopping(self) -> bool:
        if self.owner_disconnected:
            self._end("owner_disconnected")
        return self.stop.is_set()

    def _failure(self, error: Exception, **fields) -> None:
        self.incoming.put(("failure", {"error": error, **fields}))
        self._terminate_for(error)

    def _enqueue(self, kind: str, payload: dict) -> None:
        """Closing records ends ordinary event admission, not error reporting."""
        with self.lock:
            if not self.frozen:
                self.incoming.put((kind, payload))

    def _terminate_for(self, error: Exception) -> None:
        self._stopping()
        code = error_code(error)
        if code in TERMINAL_ERRORS:
            self._end(code, 3)
        elif code in LOCAL_FAILURES:
            self._end(code, 1)

    def _worker(self, work) -> None:
        """A worker may not disappear while its owner still reports connected."""
        try:
            work()
        except BaseException as error:
            self._failure(ClaudeError("worker_failed", f"{work.__name__} stopped unexpectedly ({type(error).__name__})"))
        finally:
            if not self._stopping():
                self._failure(ClaudeError("worker_failed", f"{work.__name__} ended unexpectedly"))

    def _publish(self, kind: str, **fields) -> None:
        """Journal an event before publishing the updated connection state."""
        if self.journal_broken:
            raise OSError("Connection event journal is unavailable")
        next_seq = self.state["seq"] + 1
        event = {"type": kind, "seq": next_seq, "connection_id": self.connection_id,
                 "session_id": self.target.session_id, **fields}
        encoded = json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
        try:
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
                self.journal_end = os.fstat(stream.fileno()).st_size
        except OSError:
            self.journal_broken = True
            raise
        # The journal already owns this sequence number even when the later
        # atomic state publication fails. Never allocate it again.
        self.state["seq"] = next_seq
        _save_json(self.directory / "connection.json", self.state)

    def _flush_output(self) -> None:
        """The journal spools output while a slow owner keeps control available."""
        if not self.output_open:
            return
        if self.output_reader is None and self.journal_end:
            self.output_reader = (self.directory / "events.jsonl").open("rb", buffering=0)
        if not self.output_pending:
            remaining = self.journal_end - self.output_reader.tell() if self.output_reader is not None else 0
            if remaining:
                self.output_pending.extend(self.output_reader.read(min(65536, remaining)))
            elif self.emergency_output:
                self.output_pending.extend(self.emergency_output)
                self.emergency_output.clear()
        if self.output_pending:
            try:
                count = os.write(self.output_fd, self.output_pending)
                del self.output_pending[:count]
            except BlockingIOError:
                pass
            except OSError:
                self.output_open = False
                self._end("owner_disconnected")

    def _error(self, error: Exception, **fields) -> None:
        code = error_code(error)
        self._publish("error", error={"code": code, "message": str(error)}, **fields)
        self._terminate_for(error)

    def _handle_error(self, error: Exception) -> None:
        """Owner execution and cleanup failures share one terminal error path."""
        self._stopping()
        error = _connection_error(error)
        code = error_code(error)
        self._end(code, 3 if code in TERMINAL_ERRORS else 1)
        try:
            self._error(error)
        except Exception as record_error:
            self._emergency_error(error)
            self._emergency_error(record_error)

    def _transport(self, message_id: str, state: str) -> None:
        with self.lock:
            if self.frozen:
                raise ClaudeError("connection_closed", "Transmission state is frozen after disconnect")
            if state == "write_started" and self._stopping():
                raise ClaudeError("connection_closed", "The owner connection has closed")
            updated = {**self.outbox, message_id: {**self.outbox[message_id], "transport": state}}
            _save_json(self.directory / "outbox.json", updated)
            self.outbox = updated

    def _send_loop(self) -> None:
        while not self._stopping():
            try:
                message_id = self.outgoing.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._stopping():
                break
            with self.lock:
                message = self.outbox[message_id]["message"]
            try:
                frame = build_frame(self.target, message_id, message, self.inbox.address)
                self.client.send_frame(self.target, frame,
                                       lambda: self._transport(message_id, "write_started"))
                self._transport(message_id, "written")
                self._enqueue("sent", {"uuid": message_id, "transport": "written"})
            except (ClaudeError, OSError) as error:
                with self.lock:
                    transport = self.outbox[message_id]["transport"]
                if transport == "write_started":
                    try:
                        self._transport(message_id, "delivery_unknown")
                        transport = "delivery_unknown"
                    except (OSError, ClaudeError):
                        pass  # Durable write_started already forbids replay.
                self._failure(error, uuid=message_id, transport=transport)

    def _receive_loop(self) -> None:
        while not self._stopping():
            try:
                # Availability belongs to the connection even when Claude
                # sends no messages. No conversation history is read here.
                self.client.validate(self.target)
                event = self.inbox.read_message(timeout=0.5)
                if event is not None:
                    fields = dict(event)
                    self._enqueue(fields.pop("type"), fields)
            except (ClaudeError, OSError) as error:
                self._failure(error)
                if getattr(error, "code", None) in TERMINAL_ERRORS:
                    break
                self.stop.wait(0.5)

    def _command(self, line: bytes) -> None:
        try:
            command = json.loads(line.decode("utf-8"))
            if not isinstance(command, dict):
                raise ValueError("expected an object")
            kind = command.get("type")
            if kind == "disconnect" and set(command) == {"type"}:
                self._end("disconnected")
                return
            if kind != "send" or set(command) - {"type", "message", "uuid"}:
                raise ValueError("expected send or disconnect")
            message = command.get("message")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("message must be nonempty text")
            message.encode("utf-8")
            message_id = str(uuid.UUID(command["uuid"])) if "uuid" in command else str(uuid.uuid4())
        except (UnicodeError, ValueError, TypeError, AttributeError, RecursionError):
            self._error(ClaudeError("invalid_command", "Expected a UTF-8 JSON send or disconnect command"))
            return
        with self.lock:
            saved = self.outbox.get(message_id)
            if saved is not None:
                if saved["message"] != message:
                    self._error(ClaudeError("message_conflict", "This UUID already belongs to different text"), uuid=message_id)
                else:
                    self._publish("sent", uuid=message_id, transport=saved["transport"], replayed=False)
                return
            updated = {**self.outbox, message_id: {"message": message, "transport": "not_sent"}}
            _save_json(self.directory / "outbox.json", updated)
            self.outbox = updated
        self.outgoing.put(message_id)

    def _drain_events(self, *, closing: bool = False) -> None:
        count = 0
        while closing or count < 100:
            count += 1
            if self._stopping() and not closing:
                return
            try:
                kind, payload = self.incoming.get_nowait()
            except queue.Empty:
                return
            if kind == "failure":
                fields = dict(payload)
                self._error(fields.pop("error"), **fields)
            else:
                if kind in {"message", "delivery_status"} and payload.get("source") == "peer":
                    if payload["uuid"] in self.peer_uuids:
                        continue
                    self._publish(kind, **payload)
                    self.peer_uuids.add(payload["uuid"])
                    continue
                self._publish(kind, **payload)

    def _control_loop(self) -> None:
        pending = bytearray()
        discarding = False
        with selectors.SelectSelector() as selector:
            selector.register(sys.stdin.fileno(), selectors.EVENT_READ)
            while not self._stopping():
                self._drain_events()
                self._flush_output()
                if self._stopping():
                    break
                if not selector.select(timeout=0.1):
                    continue
                try:
                    chunk = os.read(sys.stdin.fileno(), 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    self._end("owner_disconnected")
                    break
                if not chunk:
                    self._end("owner_disconnected")
                    break
                parts = chunk.split(b"\n")
                for index, part in enumerate(parts):
                    pending.extend(part)
                    if len(pending) > MAX_COMMAND_BYTES:
                        if not discarding:
                            self._error(ClaudeError("command_too_large", "Command exceeds the 1 MB limit"))
                        discarding = True
                    if index < len(parts) - 1:
                        if not discarding and pending.strip():
                            self._command(bytes(pending))
                        pending.clear()
                        discarding = False
                        if self._stopping():
                            break
                    elif discarding:
                        pending.clear()

    def run(self) -> int:
        self.client._platform()
        try:
            with _owner_channel(self._request_owner_disconnect):
                return self._run()
        except (ClaudeError, OSError):
            raise  # Before records exist, the CLI owns structured error output.
        except Exception as error:
            raise _connection_error(error) from error

    def _run(self) -> int:
        if self._stopping():
            return self.exit_code
        self.target = self.client.bind(self.session_id)
        if self._stopping():
            return self.exit_code
        try:
            self.directory.mkdir(parents=True, mode=0o700)
        except FileExistsError as error:
            raise ClaudeError("connection_conflict", "Use a new directory for each connection; existing records are never restarted") from error
        self.state = {"version": 2, "connection_id": self.connection_id,
                      "target": self.target.to_dict(), "server_pid": os.getpid(),
                      "status": "connecting", "seq": 0}
        threads = []
        output_blocking = None
        try:
            self.output_fd = sys.stdout.fileno()
            output_blocking = os.get_blocking(self.output_fd)
            os.set_blocking(self.output_fd, False)
            _save_json(self.directory / "outbox.json", self.outbox)
            with ReturnInbox(self.target, self.client) as self.inbox:
                if not self._stopping():
                    self.state.update(status="connected", reply_address=self.inbox.address)
                    self._publish("connected", run_dir=str(self.directory), target=self.target.to_dict(),
                                  reply_address=self.inbox.address)
                    for work in (self._send_loop, self._receive_loop):
                        thread = threading.Thread(target=self._worker, args=(work,), daemon=True)
                        threads.append(thread)
                        thread.start()
                    self._control_loop()
        except Exception as error:
            self._handle_error(error)
        finally:
            if not self._stopping():
                self._handle_error(ClaudeError("internal_error", "Connection owner ended without a close request"))
            for thread in threads:
                try:
                    thread.join(timeout=0.2)
                except Exception as error:
                    self._handle_error(error)
            self._close_records()
            if output_blocking is not None:
                try:
                    self._finish_output()
                except Exception as error:
                    self._handle_error(error)
                finally:
                    if self.output_reader is not None:
                        try:
                            self.output_reader.close()
                        except OSError as error:
                            self._handle_error(error)
                    try:
                        os.set_blocking(self.output_fd, output_blocking)
                    except OSError:
                        pass  # The owner's output channel may already be gone.
        return self.exit_code

    def _close_records(self) -> None:
        """Freeze transmissions and finish accepted output despite a failed step."""
        with self.lock:
            self.frozen = True
            self.outbox = {key: {**item, "transport": "delivery_unknown"}
                           if item["transport"] == "write_started" else item
                           for key, item in self.outbox.items()}
            try:
                _save_json(self.directory / "outbox.json", self.outbox)
            except Exception as error:
                self._handle_error(error)
            try:
                self._drain_events(closing=True)
            except Exception as error:
                self._handle_error(error)
            self.state.update(status="closed", reason=self.close_reason)
            try:
                self._publish("closed", reason=self.close_reason)
            except Exception as error:
                self._handle_error(error)
                try:
                    _save_json(self.directory / "connection.json", self.state)
                except Exception as record_error:
                    self._emergency_error(record_error)

    def _finish_output(self) -> None:
        # Shutdown never waits for an absent reader. Unread events remain in
        # the journal even if the owner cannot accept the closing line.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if self.output_open:
                self._flush_output()
            # Ordinary producers were frozen before closed; only late worker
            # failures can arrive now. Record arrivals during the flush before
            # deciding that no output remains.
            self._drain_events(closing=True)
            if not self.output_open:
                break
            remaining = self.journal_end - self.output_reader.tell() if self.output_reader is not None else self.journal_end
            if not self.output_pending and not remaining and not self.emergency_output:
                break
            if self.output_pending:
                select.select([], [self.output_fd], [], max(0, min(0.05, deadline - time.monotonic())))

    def _emergency_error(self, error: Exception) -> None:
        error = _connection_error(error)
        self._terminate_for(error)
        if self.output_open:
            try:
                encoded = json.dumps({"type": "error", "connection_id": self.connection_id,
                                      "session_id": self.target.session_id,
                                      "error": {"code": error_code(error), "message": str(error)}},
                                     ensure_ascii=True) + "\n"
                self.emergency_output.extend(encoded.encode("utf-8"))
            except OSError:
                self.output_open = False
