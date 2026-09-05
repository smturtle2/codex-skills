"""Persistent state shared by the launcher and GTK process."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def read_state(directory):
    value = json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported dialog state")
    return value


def save_state(directory, state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = encode(state)
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, Path(directory) / "state.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def run_lock(directory, filename=".lock"):
    """Hold an OS-released lock, including after an interrupted launcher."""
    with (Path(directory) / filename).open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("This dialog is already open; retain its existing execution handle") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def finish_state(directory, state, status, values, action=None, error=None):
    response = {"request_id": state["request_id"], "status": status,
                "action": action, "values": values, "run_dir": str(directory)}
    if error is not None:
        response["error"] = error
    encode(response)
    state.update(status=status, response=response)
    save_state(directory, state)
    return response
