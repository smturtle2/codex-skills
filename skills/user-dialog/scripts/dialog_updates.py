"""Small, file based transport for updates to an open dialog."""

import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

from dialog_delivery import require_owner
from dialog_state import read_state, run_lock


LIMIT = 8 * 1024 * 1024


def _updates(directory):
    path = Path(directory) / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path):
    if path.stat().st_size > LIMIT:
        raise ValueError(f"Update envelope is too large: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid update envelope: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Update envelope must be an object: {path.name}")
    return value


def _uuid(value, field):
    if not isinstance(value, str):
        raise ValueError(f"Update {field} is missing")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"Update {field} is invalid") from error


def _validate_request(value, name="update"):
    _uuid(value.get("command_id"), "command_id")
    if not isinstance(value.get("request_id"), str) or not value["request_id"]:
        raise ValueError(f"Invalid {name} request_id")
    revision = value.get("base_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError(f"Invalid {name} base_revision")
    if "spec" not in value:
        raise ValueError(f"Invalid {name} spec")
    return value


def _validate_result(value, name="update"):
    _uuid(value.get("command_id"), "command_id")
    if not isinstance(value.get("request_id"), str) or not value["request_id"]:
        raise ValueError(f"Invalid {name} request_id")
    if not isinstance(value.get("status"), str) or not value["status"]:
        raise ValueError(f"Invalid {name} status")
    revision = value.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError(f"Invalid {name} revision")
    return value


def _atomic_json(path, value):
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    data = encoded.encode("utf-8")
    if len(data) > LIMIT:
        raise ValueError("Update envelope is too large")
    descriptor, temporary = tempfile.mkstemp(prefix=".update-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_pending(directory):
    """Return validated requests that do not yet have a result."""
    updates = _updates(directory)
    pending = []
    for request_path in sorted(updates.glob("*.request.json"), key=lambda path: path.name):
        result_path = request_path.with_name(request_path.name[:-len(".request.json")] + ".result.json")
        if result_path.exists():
            continue
        pending.append(_validate_request(_read_json(request_path), request_path.name))
    return pending


def write_result(directory, payload, status, revision, error=None):
    """Atomically write the result corresponding to a request payload."""
    payload = _validate_request(dict(payload), "update request")
    if not isinstance(status, str) or not status:
        raise ValueError("Invalid update status")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("Invalid update revision")
    result = {"command_id": payload["command_id"], "request_id": payload["request_id"],
              "status": status, "revision": revision}
    if error is not None:
        result["error"] = str(error)
    _validate_result(result)
    updates = _updates(directory)
    result_path = updates / f"{payload['command_id']}.result.json"
    _atomic_json(result_path, result)
    return result


def _matching_result(updates, command_id, request_id):
    result_path = updates / f"{command_id}.result.json"
    if not result_path.exists():
        return None
    result = _validate_result(_read_json(result_path), result_path.name)
    if result["command_id"] != command_id or result["request_id"] != request_id:
        raise ValueError("Update result identity does not match its request")
    return result


def send_update(directory, spec, expected_revision=None, timeout=10):
    """Queue one update and wait briefly for its exact result."""
    directory = Path(directory)
    initial = read_state(directory)
    if initial.get("status") != "open":
        raise ValueError("Dialog is not open")
    request_id = initial.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("Dialog request_id is missing")
    if initial.get("origin") is not None:
        require_owner(initial["origin"])
    if expected_revision is not None and (
            not isinstance(expected_revision, int) or isinstance(expected_revision, bool)
            or expected_revision < 0):
        raise ValueError("Invalid expected revision")
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Invalid update timeout")

    with run_lock(directory, ".update-lock"):
        state = read_state(directory)
        if state.get("status") != "open" or state.get("request_id") != request_id:
            raise ValueError("Dialog state changed while preparing update")
        base_revision = state.get("revision", 0)
        if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
            raise ValueError("Invalid dialog revision")
        if expected_revision is not None and expected_revision != base_revision:
            raise ValueError("Dialog revision does not match expected revision")
        if read_pending(directory):
            raise ValueError("A previous update is still pending")
        command_id = str(uuid.uuid4())
        payload = {"command_id": command_id, "request_id": request_id,
                   "base_revision": base_revision, "spec": spec}
        _validate_request(payload)
        updates = _updates(directory)
        _atomic_json(updates / f"{command_id}.request.json", payload)
        deadline = time.monotonic() + timeout
        while True:
            result = _matching_result(updates, command_id, request_id)
            if result is not None:
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"command_id": command_id, "request_id": request_id,
                        "status": "queued", "revision": base_revision}
            time.sleep(min(0.05, remaining))
