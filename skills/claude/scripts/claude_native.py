"""Linux compatibility boundary for an existing Claude Code inbox.

Only `claude agents --json` is executed. Registry, authentication and native
message frames are private peerProtocol=1 compatibility, inspected in Code
2.1.299. An adapter inbox is never registered as a Claude session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from typing import Callable
from urllib.parse import unquote


class ClaudeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Target:
    session_id: str
    cwd: str
    pid: int
    proc_start: str
    pid_domain: str
    inbox: str
    version: str
    peer_protocol: int
    inbox_dev: int | None = None
    inbox_ino: int | None = None
    boot_id: str | None = None
    started_at: int | float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> Target:
        try:
            target = cls(**value)
            if type(target.pid) is not int or target.pid <= 0:
                raise ValueError("invalid pid")
            if type(target.peer_protocol) is not int or target.peer_protocol != 1:
                raise ValueError("invalid protocol")
            if any(value is not None and (type(value) is not int or value < 0)
                   for value in (target.inbox_dev, target.inbox_ino)):
                raise ValueError("invalid socket identity")
            uuid.UUID(target.session_id)
            if target.boot_id is not None:
                uuid.UUID(target.boot_id)
            if target.started_at is not None and not _valid_started_at(target.started_at):
                raise ValueError("invalid registry start time")
            if not all(isinstance(s, str) and s for s in (
                target.cwd, target.proc_start, target.pid_domain, target.inbox, target.version
            )):
                raise ValueError("invalid target fields")
            return target
        except (TypeError, ValueError, AttributeError) as error:
            raise ClaudeError("invalid_request", "Saved target is invalid") from error


def _canonical(path: str | Path) -> str:
    return unicodedata.normalize("NFC", str(Path(path).expanduser().resolve()))


_LIVE_STATUSES = {"idle", "busy", "shell", "waiting"}


def _valid_started_at(value: object) -> bool:
    # Native vDs accepts finite epoch milliseconds in this range.
    return (type(value) in {int, float} and 0 <= value <= 4_000_000_000_000_000
            and math.isfinite(value))


def _address(path: str | Path) -> str:
    # Code's UK/h serializer percent-encodes UTF-8 bytes outside this alphabet.
    # urllib.quote deliberately leaves '~' unescaped, which native Code does not.
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:_/.\\-"
    return "uds:" + "".join(chr(byte) if byte in safe else f"%{byte:02X}"
                             for byte in str(path).encode("utf-8"))


def build_frame(target: Target, message_id: str, message: str, reply_address: str) -> dict:
    """Wrap caller text in native metadata without prescribing Claude output."""
    try:
        if str(uuid.UUID(message_id)) != message_id:
            raise ValueError("noncanonical message ID")
        if not isinstance(message, str) or not message:
            raise ValueError("empty message")
        message.encode("utf-8")
        path = unquote(reply_address[4:], errors="strict")
        if (not reply_address.startswith("uds:") or not Path(path).is_absolute()
                or not path.endswith(".sock") or _address(path) != reply_address
                or len(reply_address) > 204):
            raise ValueError("invalid return address")
    except (ValueError, TypeError, AttributeError, UnicodeError) as error:
        raise ClaudeError("invalid_request", "Message ID, text or return address is invalid") from error
    return {
        "msgV": 1, "msg_id": message_id,
        "type": "user", "session_id": target.session_id, "uuid": message_id,
        "priority": "next", "from": reply_address,
        "message": {
            "role": "user",
            "content": f'<cross-session-message from="{reply_address}" from-name="Codex">\n'
                       f'{message}\n</cross-session-message>',
        },
    }


class NativeClient:
    def __init__(self, config_dir: str | Path | None = None, cli: str = "claude"):
        self.config_dir = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser().resolve()
        self.cli = cli

    def _platform(self) -> None:
        if sys.platform != "linux":
            raise ClaudeError("unsupported_platform", "This adapter supports local Linux inboxes")

    def _discover(self) -> list[dict]:
        self._platform()
        env = os.environ.copy()
        env["CLAUDE_CONFIG_DIR"] = str(self.config_dir)
        try:
            result = subprocess.run(
                [self.cli, "agents", "--json"], capture_output=True, text=True,
                timeout=10, check=False, env=env,
            )
        except FileNotFoundError as error:
            raise ClaudeError("claude_not_found", "Claude Code CLI is not installed") from error
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
            raise ClaudeError("discovery_failed", "Cannot query existing Claude sessions") from error
        if result.returncode:
            raise ClaudeError("discovery_failed", "Claude session discovery failed")
        try:
            rows = json.loads(result.stdout)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("invalid rows")
            return rows
        except (ValueError, TypeError) as error:
            raise ClaudeError("discovery_failed", "Claude returned an invalid session listing") from error

    def _pid_domain(self, namespace: str | Path) -> str:
        # Native Code 2.1.299 uses machine-id, not the kernel boot UUID.
        try:
            machine = Path("/etc/machine-id").read_text().strip()
        except OSError:
            machine = ""  # The native implementation uses the same fallback.
        return f"linux:{machine}:{os.readlink(namespace)}"

    def _local_pid_domain(self) -> str:
        return self._pid_domain("/proc/self/ns/pid")

    def _boot_id(self) -> str:
        try:
            return str(uuid.UUID(Path("/proc/sys/kernel/random/boot_id").read_text().strip()))
        except (OSError, ValueError) as error:
            raise ClaudeError("session_unavailable", "Cannot identify the current process boot") from error

    def _process_identity(self, pid: int) -> tuple[str, str]:
        try:
            proc = Path("/proc") / str(pid)
            if proc.stat().st_uid != os.getuid():
                raise OSError("different user")
            fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] in {"Z", "X"}:
                raise OSError("process exited")
            start = fields[19]
            domain = self._pid_domain(proc / 'ns/pid')
            if domain != self._local_pid_domain():
                raise OSError("different PID namespace")
            return start, domain
        except (OSError, IndexError, ValueError) as error:
            raise ClaudeError("session_unavailable", "Claude process is no longer available") from error

    def _registry_directory(self) -> Path:
        directory = self.config_dir / "sessions"
        try:
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022):
                raise ValueError("unsafe registry directory")
            return directory
        except (OSError, ValueError) as error:
            raise ClaudeError("session_unavailable", "Live session registry directory is missing or unsafe") from error

    def _read_registry(self, pid: int) -> dict:
        path = self.config_dir / "sessions" / f"{pid}.json"
        # Code publishes registry updates in place. A reader may momentarily
        # see an empty, truncated JSON or partial final UTF-8 sequence; retry
        # only those read states, never unsafe ownership or changed identity.
        for attempt in range(5):
            try:
                directory = self._registry_directory()
                parent = directory.lstat()
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o022):
                    raise ValueError("unsafe registry")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                with os.fdopen(fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                            or opened.st_mode & 0o022
                            or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino)):
                        raise ValueError("registry replaced or unsafe")
                    raw = stream.read(262_145)
                after, parent_after = path.lstat(), directory.lstat()
                if ((info.st_dev, info.st_ino) != (after.st_dev, after.st_ino)
                        or (parent.st_dev, parent.st_ino) != (parent_after.st_dev, parent_after.st_ino)
                        or not stat.S_ISREG(after.st_mode) or after.st_uid != os.getuid()
                        or after.st_mode & 0o022 or not stat.S_ISDIR(parent_after.st_mode)
                        or parent_after.st_uid != os.getuid() or parent_after.st_mode & 0o022
                        or len(raw) > 262_144):
                    raise ValueError("registry replaced or unsafe")
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("invalid registry")
                return value
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                partial_utf8 = isinstance(error, UnicodeDecodeError) and error.reason == "unexpected end of data"
                if attempt == 4 or (isinstance(error, UnicodeDecodeError) and not partial_utf8):
                    raise ClaudeError("session_unavailable", "Live session registry is missing or invalid") from error
                time.sleep(0.01)
            except (OSError, ValueError, TypeError, RecursionError) as error:
                raise ClaudeError("session_unavailable", "Live session registry is missing or invalid") from error
        raise AssertionError("registry retry loop did not return")

    def _check_inbox(self, inbox: str) -> os.stat_result:
        try:
            path = Path(inbox)
            if not path.is_absolute() or path.is_symlink():
                raise ValueError("invalid socket path")
            info, parent = path.lstat(), path.parent.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("socket ownership/type")
            if info.st_mode & 0o022 or parent.st_uid != os.getuid() or parent.st_mode & 0o022:
                raise ValueError("socket permissions")
            return info
        except (OSError, ValueError) as error:
            raise ClaudeError("session_unavailable", "Target inbox is missing or unsafe") from error

    def _check_peer(self, connection: socket.socket, pid: int) -> None:
        peer_pid, peer_uid, _ = struct.unpack(
            "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        )
        if peer_pid != pid or peer_uid != os.getuid():
            raise ClaudeError("session_unavailable", "Inbox listener is not the selected Claude process")

    def _probe_inbox(self, inbox: str, pid: int) -> None:
        # A socket filesystem entry may outlive its listener. Connect without
        # writing any frame to verify reachability and actual listener identity.
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(inbox)
                self._check_peer(connection, pid)
        except OSError as error:
            raise ClaudeError("session_unavailable", "Target inbox has no reachable listener") from error

    def _registry_identity(self, pid: int, registry: dict) -> tuple[str, str, str, str]:
        """Validate one real local registry incarnation without querying the CLI."""
        try:
            if (type(pid) is not int or pid <= 0 or type(registry.get("pid")) is not int
                    or registry["pid"] != pid or registry.get("status") not in _LIVE_STATUSES
                    or not _valid_started_at(registry.get("startedAt"))):
                raise ValueError("not live")
            sid = str(uuid.UUID(registry["sessionId"]))
            cwd_value = registry["cwd"]
            if registry["sessionId"] != sid or not isinstance(cwd_value, str) or not Path(cwd_value).is_absolute():
                raise ValueError("invalid session ID or working directory")
            cwd = _canonical(cwd_value)
            start, domain = self._process_identity(pid)
            if registry.get("procStart") != start or registry.get("pidDomain") != domain:
                raise ValueError("identity changed")
            return sid, cwd, start, domain
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ClaudeError("session_unavailable", "Claude session identity is missing or changed") from error

    def _resolve_target(self, pid: int) -> tuple[Target, dict]:
        registry = self._read_registry(pid)
        sid, cwd, start, domain = self._registry_identity(pid, registry)
        try:
            if type(registry.get("peerProtocol")) is not int or registry["peerProtocol"] != 1:
                raise ClaudeError("unsupported_protocol", "Unsupported Claude inbox protocol")
            inbox = registry["messagingSocketPath"]
            version = registry["version"]
            if not isinstance(inbox, str) or not inbox or not isinstance(version, str) or not version:
                raise ValueError("missing endpoint/version")
            info = self._check_inbox(inbox)
            self._probe_inbox(inbox, pid)
            after_probe = self._check_inbox(inbox)
            if (info.st_dev, info.st_ino) != (after_probe.st_dev, after_probe.st_ino):
                raise ValueError("inbox replaced")
            target = Target(sid, cwd, pid, start, domain, inbox, version, 1,
                            info.st_dev, info.st_ino, self._boot_id(), registry["startedAt"])
            return target, registry
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ClaudeError("session_unavailable", "Claude session identity is missing or changed") from error

    def _ensure_unique_session(self, target: Target) -> None:
        # Resume can create another live process sharing the transcript ID.
        # Only trustworthy local records with matching real process identity
        # count; exited, recycled, foreign-domain and unsafe records do not.
        try:
            paths = list(self._registry_directory().iterdir())
        except OSError as error:
            raise ClaudeError("session_unavailable", "Cannot establish a unique local Claude session") from error
        for path in paths:
            if not re.fullmatch(r"[1-9][0-9]*\.json", path.name):
                continue
            pid = int(path.stem)
            if pid == target.pid:
                continue
            try:
                registry = self._read_registry(pid)
                if registry.get("sessionId") != target.session_id:
                    continue
                self._registry_identity(pid, registry)
            except ClaudeError:
                continue
            raise ClaudeError("session_unavailable", "Another live Claude process shares the selected session ID")
        self._registry_directory()

    def _target_from_row(self, row: dict) -> Target:
        try:
            pid = row["pid"]
            if (type(pid) is not int or pid <= 0 or row.get("status") not in _LIVE_STATUSES
                    or not _valid_started_at(row.get("startedAt"))):
                raise ValueError("not live")
            target, _ = self._resolve_target(pid)
            if (row.get("sessionId") != target.session_id or _canonical(row["cwd"]) != target.cwd
                    or row.get("startedAt") != target.started_at):
                raise ValueError("discovered identity changed")
            self._ensure_unique_session(target)
            return target
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ClaudeError("session_unavailable", "Claude session identity is missing or changed") from error

    def list_sessions(self) -> list[dict]:
        result = []
        for row in self._discover():
            # Completed history and exited background rows are never usable targets.
            if type(row.get("pid")) is not int or row.get("status") not in _LIVE_STATUSES:
                continue
            item = {key: row[key] for key in ("pid", "cwd", "kind", "startedAt", "sessionId", "name", "status", "waitingFor") if key in row}
            try:
                item["target"] = self._target_from_row(row).to_dict()
                item["available"] = True
            except ClaudeError as error:
                item.update(available=False, reason=error.code)
            result.append(item)
        return result

    def bind(self, session_id: str) -> Target:
        try:
            sid = str(uuid.UUID(session_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise ClaudeError("invalid_request", "Session ID must be a UUID") from error
        rows = [row for row in self._discover() if row.get("sessionId") == sid
                and type(row.get("pid")) is int and row.get("status") in _LIVE_STATUSES]
        if len(rows) != 1:
            raise ClaudeError("session_unavailable", "No unique running Claude session matches this ID")
        return self._target_from_row(rows[0])

    def validate(self, target: Target) -> dict:
        self._platform()
        if target.started_at is None:
            raise ClaudeError("session_unavailable", "The Claude target has no bound registry start time")
        current, registry = self._resolve_target(target.pid)
        if current != target:
            raise ClaudeError("session_unavailable", "The saved Claude target has changed")
        self._ensure_unique_session(target)
        return {key: registry[key] for key in ("name", "status", "waitingFor") if key in registry}

    def _peer_token(self, target: Target) -> str | None:
        digest = hashlib.sha256(_canonical(target.inbox).encode()).hexdigest()
        path = self.config_dir / "sessions" / f"{target.pid}.{digest}.key"
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None  # Optional on Linux; no synthetic/foreign token fallback.
        except OSError as error:
            raise ClaudeError("authentication_unavailable", "Cannot read target authentication") from error
        try:
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("unsafe key")
            value = json.loads(path.read_text(encoding="utf-8"))
            token = value["peerToken"]
            if (value.get("procStart") != target.proc_start or value.get("pidDomain") != target.pid_domain
                    or not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token)):
                raise ValueError("invalid key")
            return token
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ClaudeError("authentication_unavailable", "Target authentication is invalid or stale") from error

    def send_frame(self, target: Target, frame: dict, before_write: Callable[[], None]) -> None:
        if frame.get("session_id") != target.session_id or frame.get("type") != "user":
            raise ClaudeError("invalid_request", "Frame does not identify the selected session")
        encoded = (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")
        if len(encoded) > 1_000_000:
            raise ClaudeError("message_too_large", "Serialized message exceeds the adapter's 1 MB limit")
        self.validate(target)
        token = self._peer_token(target)
        try:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except OSError as error:
            raise ClaudeError("session_unavailable", "Cannot open a local inbox connection") from error
        with connection:
            try:
                connection.settimeout(3)
                connection.connect(target.inbox)
                # The filesystem path can be replaced between validation and
                # connect. Authenticate the actual local listener before secrets.
                self._check_peer(connection, target.pid)
                self.validate(target)
                if token is not None:
                    connection.sendall((json.dumps({"type": "auth", "token": token}) + "\n").encode())
            except OSError as error:
                raise ClaudeError("session_unavailable", "Cannot reach the live Claude inbox") from error
            # Storage errors belong to the caller. In particular, an OSError in
            # this callback is not a socket failure and no user bytes were sent.
            before_write()
            try:
                connection.sendall(encoded)
                # Write success alone does not establish receiver admission.
            except OSError as error:
                raise ClaudeError("delivery_unknown", "Inbox transmission may have occurred") from error


_ENVELOPE = re.compile(
    r'^<cross-session-message from="(?P<from>[A-Za-z0-9%:_/.\\-]+)"'
    r'(?: from-session="[A-Za-z0-9_-]{1,80}")?'
    r'(?: hop-chain="[0-9a-f]{24}(?:,[0-9a-f]{24}){0,31}")?'
    r'(?: from-name="[^"<>\n\r]+")?'
    r'(?: from-mode="(?:bypass|prompting)")?'
    r'(?: from-plugin="[^"<>\n\r]+")?>\n'
    r'(?P<body>[\s\S]*)\n</cross-session-message>$'
)
_NATIVE_MESSAGE_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_DELIVERY_STATUSES = {"held", "denied", "expired", "delivered", "refused", "dropped"}
_DROP_REASONS = {"rate-limited", "duplicate", "hop-loop", "hop-runaway", "queue-full"}


def _native_message_id(value: object) -> bool:
    return isinstance(value, str) and _NATIVE_MESSAGE_ID.fullmatch(value) is not None


class ReturnInbox:
    """A real, connection-owned return inbox for the selected live process.

    read_message emits normalized message or delivery_status events, and may
    raise invalid_peer_frame or foreign_peer for a rejected connection; callers
    can report those errors and continue receiving. An
    inbox_unavailable error concerns this listener. session_unavailable means
    the exact bound Claude target failed validation and should end the relay.

    Native hCo trusts a return socket in the target inbox's directory. A unique
    sibling therefore preserves native reply-address handling without creating
    a synthetic Claude registry record. The directory is verified as same-user
    and unwritable by others; the return socket itself is mode 0600. No peer key
    is published: Linux authenticates every inbound connection with SO_PEERCRED.
    An optional native auth preamble is accepted only after that check, ignored
    as redundant and never recorded.
    """
    MAX_BYTES = 1_000_000

    def __init__(self, target: Target, client: NativeClient):
        self.target = target
        self.client = client
        self._path = Path(target.inbox).parent / f"codex-{uuid.uuid4().hex[:16]}.sock"
        self.address = _address(self._path)
        self._listener: socket.socket | None = None
        self._active: socket.socket | None = None
        self._identity: tuple[int, int] | None = None
        self._closed = threading.Event()
        self._lock = threading.Lock()

    def __enter__(self) -> ReturnInbox:
        if self._closed.is_set() or self._listener is not None:
            raise ClaudeError("inbox_unavailable", "Return inbox cannot be reopened")
        self.client.validate(self.target)
        try:
            parent = self._path.parent.lstat()
            if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                    or parent.st_mode & 0o022 or len(os.fsencode(self._path)) > 103
                    or len(self.address) > 204):
                raise ValueError("unsafe or overlong return path")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._listener = listener
            listener.bind(str(self._path))  # Exclusive; never remove an existing path.
            info = self._path.lstat()
            self._identity = info.st_dev, info.st_ino
            self._path.chmod(0o600)
            listener.listen(16)
            self.client.validate(self.target)
            return self
        except ClaudeError:
            self.close()
            raise
        except (OSError, ValueError) as error:
            self.close()
            raise ClaudeError("inbox_unavailable", "Cannot create a private return inbox") from error
        except BaseException:
            self.close()
            raise

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            listener, active = self._listener, self._active
            self._listener = self._active = None
        failure = None
        for connection in (active, listener):
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    connection.close()
                except OSError as error:
                    failure = failure or error
        # A replaced path belongs to someone else, even if it has the same name.
        if self._identity is not None:
            try:
                info = self._path.lstat()
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self._identity:
                    self._path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                failure = failure or error
        if failure is not None:
            raise ClaudeError("inbox_unavailable", "Cannot fully close or remove the return inbox") from failure

    def _peer(self, connection: socket.socket) -> None:
        try:
            pid, uid, _ = struct.unpack("3i", connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        except OSError as error:
            raise ClaudeError("foreign_peer", "Cannot identify the return inbox sender") from error
        if pid != self.target.pid or uid != os.getuid():
            raise ClaudeError("foreign_peer", "Return inbox sender is not the selected Claude process")
        self.client.validate(self.target)

    def _message(self, frame: dict) -> dict | None:
        control = frame.get("type") == "control"
        if control and frame.get("action") != "peer_message_status":
            return None  # Unrelated native controls are not public relay events.
        try:
            message_id = frame["msg_id"]
            if (type(frame.get("msgV")) is not int or frame["msgV"] != 1
                    or not _native_message_id(message_id)
                    or frame.get("from") != _address(self.target.inbox)):
                raise ValueError("invalid native frame metadata")
            if control:
                return self._delivery_status(frame, message_id)
            body = frame["message"]
            if (frame.get("type") != "user" or not isinstance(body, dict)
                    or body.get("role") != "user" or not isinstance(body.get("content"), str)):
                raise ValueError("invalid native user frame")
            envelope = _ENVELOPE.fullmatch(body["content"])
            if envelope is None or envelope["from"] != frame["from"]:
                raise ValueError("invalid native envelope")
            envelope["body"].encode("utf-8")
            return {"type": "message", "source": "peer", "uuid": message_id,
                    "content": envelope["body"]}
        except (KeyError, ValueError, TypeError, AttributeError, UnicodeError) as error:
            raise ClaudeError("invalid_peer_frame", "Return inbox received an invalid native event") from error

    def _delivery_status(self, frame: dict, message_id: str) -> dict:
        """Expose only the known peerProtocol=1 receipt fields, unchanged."""
        status = frame["status"]
        if not isinstance(status, str) or status not in _DELIVERY_STATUSES:
            raise ValueError("invalid delivery status")
        result = {"type": "delivery_status", "source": "peer", "uuid": message_id,
                  "status": status}
        if "status_detail" in frame:
            if status != "expired" or frame["status_detail"] != "refused":
                raise ValueError("invalid delivery status detail")
            result["status_detail"] = frame["status_detail"]
        if "reason" in frame:
            if not isinstance(frame["reason"], str):
                raise ValueError("invalid delivery reason")
            frame["reason"].encode("utf-8")
            result["reason"] = frame["reason"]
        if "orig_msg_id" in frame:
            if not _native_message_id(frame["orig_msg_id"]):
                raise ValueError("invalid original message ID")
            result["orig_msg_id"] = frame["orig_msg_id"]
        if "drop_reason" in frame:
            reason = frame["drop_reason"]
            if status != "dropped" or not isinstance(reason, str) or reason not in _DROP_REASONS:
                raise ValueError("invalid drop reason")
            result["drop_reason"] = reason
        if "dropped_msg_ids" in frame:
            dropped = frame["dropped_msg_ids"]
            # Native 2.1.299 coalesces at most 256 IDs into one drop receipt.
            if (status != "dropped" or not isinstance(dropped, list) or len(dropped) > 256
                    or any(not _native_message_id(value) for value in dropped)):
                raise ValueError("invalid dropped message IDs")
            result["dropped_msg_ids"] = dropped
        return result

    def read_message(self, timeout: float = 0.5) -> dict | None:
        """Read one bounded message or delivery_status event from the bound peer.

        The native sender writes one user/control frame per connection, with an
        optional preceding auth line. Both bytes and elapsed read time are
        bounded, so an incomplete frame cannot hold the receiver indefinitely.
        Closing from another thread interrupts accept or the active read.
        Reachability probes, auth and unrelated control frames are silent;
        malformed peer_message_status notices raise invalid_peer_frame.
        """
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ClaudeError("invalid_request", "Return inbox timeout must be positive")
        with self._lock:
            listener = self._listener
        if self._closed.is_set():
            return None
        if listener is None:
            raise ClaudeError("inbox_unavailable", "Return inbox is not listening")
        connection = None
        try:
            listener.settimeout(timeout)
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                return None
            with self._lock:
                if self._closed.is_set():
                    connection.close()
                    return None
                self._active = connection
            self._peer(connection)
            deadline = time.monotonic() + timeout
            pending = bytearray()
            received = 0
            auth_seen = False
            while not self._closed.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ClaudeError("invalid_peer_frame", "Return inbox frame was incomplete")
                connection.settimeout(remaining)
                try:
                    chunk = connection.recv(min(65536, self.MAX_BYTES + 1 - received))
                except socket.timeout as error:
                    raise ClaudeError("invalid_peer_frame", "Return inbox frame was incomplete") from error
                if not chunk:
                    if not pending:
                        return None  # Native reachability probe, or a control/auth-only connection.
                    raise ClaudeError("invalid_peer_frame", "Return inbox frame lacks its newline")
                received += len(chunk)
                if received > self.MAX_BYTES:
                    raise ClaudeError("invalid_peer_frame", "Return inbox frame exceeds the 1 MB limit")
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, rest = pending.partition(b"\n")
                    pending = bytearray(rest)
                    try:
                        frame = json.loads(line.decode("utf-8"))
                        if not isinstance(frame, dict):
                            raise ValueError("invalid frame object")
                    except (ValueError, UnicodeError, RecursionError) as error:
                        raise ClaudeError("invalid_peer_frame", "Return inbox frame is not UTF-8 JSON") from error
                    if frame.get("type") == "auth":
                        token = frame.get("token")
                        if auth_seen or not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
                            raise ClaudeError("invalid_peer_frame", "Return inbox auth preamble is malformed")
                        auth_seen = True
                        continue
                    message = self._message(frame)
                    if message is not None:
                        self.client.validate(self.target)
                        return message
        except OSError as error:
            if self._closed.is_set():
                return None
            if connection is not None:
                raise ClaudeError("invalid_peer_frame", "Return inbox sender closed an incomplete frame") from error
            raise ClaudeError("inbox_unavailable", "Cannot receive from the return inbox") from error
        finally:
            if connection is not None:
                with self._lock:
                    if self._active is connection:
                        self._active = None
                try:
                    connection.close()
                except OSError as error:
                    raise ClaudeError("inbox_unavailable", "Cannot close the return inbox connection") from error
        return None
