"""Linux compatibility boundary for an existing Claude Code inbox.

Only `claude agents --json` is executed. Registry/auth/frame/raw-transcript
details are private peerProtocol=1 compatibility, verified with Code 2.1.299.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import unicodedata
import uuid
from typing import Callable


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
            if not all(isinstance(s, str) and s for s in (
                target.cwd, target.proc_start, target.pid_domain, target.inbox, target.version
            )):
                raise ValueError("invalid target fields")
            return target
        except (TypeError, ValueError, AttributeError) as error:
            raise ClaudeError("invalid_request", "Saved target is invalid") from error


def _canonical(path: str | Path) -> str:
    return unicodedata.normalize("NFC", str(Path(path).expanduser().resolve()))


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

    def _read_registry(self, pid: int) -> dict:
        path = self.config_dir / "sessions" / f"{pid}.json"
        try:
            info = path.lstat()
            parent = path.parent.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError("unsafe registry")
            if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
                raise ValueError("unsafe registry directory")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("invalid registry")
            return value
        except (OSError, ValueError, TypeError) as error:
            raise ClaudeError("session_unavailable", "Live session registry is missing or invalid") from error

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

    def _target_from_row(self, row: dict) -> Target:
        try:
            pid = row["pid"]
            if type(pid) is not int or pid <= 0 or row.get("status") not in {"idle", "busy", "waiting"}:
                raise ValueError("not live")
            sid = str(uuid.UUID(row["sessionId"]))
            cwd = _canonical(row["cwd"])
            registry = self._read_registry(pid)
            start, domain = self._process_identity(pid)
            if (registry.get("pid") != pid or registry.get("sessionId") != sid
                    or _canonical(registry.get("cwd", "")) != cwd
                    or registry.get("startedAt") != row.get("startedAt")
                    or registry.get("procStart") != start or registry.get("pidDomain") != domain):
                raise ValueError("identity changed")
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
            return Target(sid, cwd, pid, start, domain, inbox, version, 1, info.st_dev, info.st_ino, self._boot_id())
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ClaudeError("session_unavailable", "Claude session identity is missing or changed") from error

    def list_sessions(self) -> list[dict]:
        result = []
        for row in self._discover():
            # Completed history and exited background rows are never usable targets.
            if type(row.get("pid")) is not int or row.get("status") not in {"idle", "busy", "waiting"}:
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
                and type(row.get("pid")) is int and row.get("status") in {"idle", "busy", "waiting"}]
        if len(rows) != 1:
            raise ClaudeError("session_unavailable", "No unique running Claude session matches this ID")
        return self._target_from_row(rows[0])

    def validate(self, target: Target) -> dict:
        current = self.bind(target.session_id)
        if current != target:
            raise ClaudeError("session_unavailable", "The saved Claude target has changed")
        registry = self._read_registry(target.pid)
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
        started = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(target.inbox)
                # The filesystem path can be replaced between validation and
                # connect. Authenticate the actual local listener before secrets.
                self._check_peer(connection, target.pid)
                self.validate(target)
                if token is not None:
                    connection.sendall((json.dumps({"type": "auth", "token": token}) + "\n").encode())
                before_write()  # Persist the uncertainty boundary BEFORE any user bytes.
                started = True
                connection.sendall(encoded)
                # Plain user frames have no ACK. Closure/write success is not admission.
        except OSError as error:
            code = "delivery_unknown" if started else "session_unavailable"
            message = "Inbox transmission may have occurred" if started else "Cannot reach the live Claude inbox"
            raise ClaudeError(code, message) from error

    def transcript_path(self, target: Target) -> Path:
        # Raw isMeta lookup only. Exact session ID avoids attributing another history.
        projects = self.config_dir / "projects"
        sanitized = re.sub(r"[^a-zA-Z0-9]", "-", target.cwd)
        if len(sanitized) <= 200:
            return projects / sanitized / f"{target.session_id}.jsonl"
        candidates = []
        try:
            for project in projects.iterdir():
                if project.name.startswith(sanitized[:200] + "-") and project.is_dir():
                    candidate = project / f"{target.session_id}.jsonl"
                    if candidate.is_file():
                        candidates.append(candidate)
        except FileNotFoundError:
            pass
        if len(candidates) != 1:
            raise ClaudeError("history_unavailable", "Cannot uniquely locate the target input record")
        return candidates[0]

    def input_observed(self, target: Target, request_id: str) -> bool:
        path = self.transcript_path(target)
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    # Avoid parsing unrelated large payloads whenever possible.
                    if request_id not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue  # A concurrently appended partial line is not evidence.
                    if (isinstance(record, dict) and record.get("uuid") == request_id and record.get("type") == "user"
                            and record.get("sessionId") == target.session_id
                            and not record.get("isSidechain")
                            and isinstance(record.get("message"), dict)
                            and record["message"].get("role") == "user"):
                        return True
        except FileNotFoundError:
            return False
        except (OSError, UnicodeError) as error:
            raise ClaudeError("history_unavailable", "Cannot inspect target input records") from error
        return False
