"""Send work to a live Claude inbox and observe replies; never launch a session."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
try:
    import fcntl
except ImportError:  # Unsupported platforms still get a structured error.
    fcntl = None
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

from claude_history import HistoryError, capture_cursor, observe_responses
from claude_native import ClaudeError, NativeClient, Target


def save_request(directory: Path, state: dict) -> None:
    """Publish a complete record, including the pre-write uncertainty boundary."""
    descriptor, temporary = tempfile.mkstemp(prefix=".request-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / "request.json")
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_request(directory: Path) -> dict:
    try:
        state = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError("invalid version")
        uuid.UUID(state["request_id"])
        Target.from_dict(state["target"])
        if not isinstance(state["message"], str) or type(state["expect_reply"]) is not bool:
            raise ValueError("invalid request")
        if state["transport"] not in {"not_sent", "write_started", "written", "delivery_unknown"}:
            raise ValueError("invalid transport")
        if state.get("input") not in {"not_observed", "observed"} or state.get("response") not in {"not_observed", "observed", "unmatched", "ambiguous"}:
            raise ValueError("invalid observation state")
        if not isinstance(state.get("cursor"), dict) or not isinstance(state.get("responses"), list):
            raise ValueError("invalid observations")
        if any(not isinstance(item, dict) or not isinstance(item.get("message_id"), str) for item in state["responses"]):
            raise ValueError("invalid response groups")
        if state.get("matched_response") is not None and not isinstance(state["matched_response"], dict):
            raise ValueError("invalid reply")
        return state
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ClaudeError("invalid_request", "Request record is missing or invalid") from error


@contextmanager
def request_lock(directory: Path, *, create: bool = False):
    if fcntl is None:
        raise ClaudeError("unsupported_platform", "This adapter supports local Linux inboxes")
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    elif not (directory / "request.json").is_file():
        raise ClaudeError("invalid_request", "No saved request in this directory")
    try:
        descriptor = os.open(directory / ".request-lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
    except OSError as error:
        raise ClaudeError("record_unavailable", "Cannot access the request workspace") from error


def build_frame(target: Target, request_id: str, message: str, expect_reply: bool) -> dict:
    content = message
    if expect_reply:
        content += (
            "\n\n<codex-reply-contract>\n"
            "Return your response in your ordinary assistant text here. Wrap the entire reply exactly in "
            f'<codex-reply request-id="{request_id}">...</codex-reply>, replacing ... with your reply. '
            "Do not put the wrapper in a code fence. This tag identifies a reply; it does not specify a task outcome.\n"
            "</codex-reply-contract>"
        )
    return {"type": "user", "session_id": target.session_id, "uuid": request_id,
            "from": "Codex", "message": {"role": "user", "content":
            '<cross-session-message from-name="Codex">\n' + content + "\n</cross-session-message>"}}


def _summary(directory: Path, state: dict, session: dict, responses: list) -> dict:
    return {"available": True, "run_dir": str(directory), "request_id": state["request_id"],
            "target": state["target"], "session": session,
            "transport": state["transport"], "input": state["input"],
            "response": state["response"], "history_gap": state.get("history_gap", False),
            "responses": responses, "matched_response": state.get("matched_response")}


def _observe(directory: Path, state: dict, client: NativeClient) -> dict:
    target = Target.from_dict(state["target"])
    session = client.validate(target)
    if state["input"] != "observed" and client.input_observed(target, state["request_id"]):
        state["input"] = "observed"
    observation = observe_responses(target, state["request_id"], state["cursor"],
                                    previous_responses=state.get("responses", []))
    state["cursor"] = observation["cursor"]
    state["history_gap"] = state.get("history_gap", False) or observation["history_gap"]
    responses = observation["responses"]
    state.setdefault("responses", []).extend(responses)
    matched = observation["matched_response"]
    state["matched_response"] = None
    if state["expect_reply"] and matched is not None:
        state["matched_response"] = matched
        state["response"] = "observed"
    elif observation.get("ambiguous", False):
        state["response"] = "ambiguous"
    elif observation["unmatched"]:
        state["response"] = "unmatched"
    else:
        state["response"] = "not_observed"
    # Cursor and evidence form one staged update. If the target closes here,
    # the error record preserves both without claiming current availability.
    session = client.validate(target)
    state.pop("error", None)
    save_request(directory, state)
    return _summary(directory, state, session, responses)


def _same_request(state: dict, session_id: str, message: str, expect_reply: bool) -> None:
    try:
        session_id = str(uuid.UUID(session_id))
    except (ValueError, TypeError) as error:
        raise ClaudeError("invalid_request", "Session ID must be a UUID") from error
    if (state["target"]["session_id"] != session_id or state["message"] != message
            or state["expect_reply"] != expect_reply):
        raise ClaudeError("request_conflict", "This directory belongs to a different immutable request")


def _record_error(directory: Path, state: dict, error: Exception) -> Exception:
    if isinstance(error, OSError):
        error = ClaudeError("record_unavailable", "Cannot persist updated request evidence")
    error.context = {"run_dir": str(directory), "request_id": state["request_id"],
                     "transport": state["transport"], "input": state["input"], "response": state["response"]}
    state["error"] = {"code": getattr(error, "code", "history_unavailable"), "message": str(error)}
    try:
        save_request(directory, state)
    except OSError as failure:
        record_error = ClaudeError("record_unavailable", "Cannot persist updated request evidence")
        record_error.context = error.context
        raise record_error from failure
    return error


def _observe_saved(directory: Path, state: dict, client: NativeClient) -> dict:
    try:
        return _observe(directory, state, client)
    except (ClaudeError, HistoryError, OSError) as error:
        raise _record_error(directory, state, error)


def _send(args: argparse.Namespace, client: NativeClient) -> dict:
    try:
        message = Path(args.message_file).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ClaudeError("invalid_request", "Cannot read the UTF-8 message file") from error
    if not message.strip():
        raise ClaudeError("invalid_request", "Message must not be empty")
    directory = Path(args.run_dir or Path.cwd() / ".codex-skills" / "claude" / uuid.uuid4().hex).expanduser().resolve()
    if (directory / "request.json").exists():
        with request_lock(directory):
            state = load_request(directory)
            _same_request(state, args.session, message, args.expect_reply)
            return _observe_saved(directory, state, client)

    # No workspace or SDK read is needed when no live target is available.
    target = client.bind(args.session)
    cursor = capture_cursor(target)
    client.validate(target)
    with request_lock(directory, create=True):
        # A simultaneous invocation may already have reserved this same directory.
        if (directory / "request.json").exists():
            state = load_request(directory)
            _same_request(state, args.session, message, args.expect_reply)
            return _observe_saved(directory, state, client)
        request_id = str(uuid.uuid4())
        state = {"version": 1, "request_id": request_id, "target": target.to_dict(),
                 "message": message, "expect_reply": args.expect_reply,
                 "frame": build_frame(target, request_id, message, args.expect_reply),
                 "transport": "not_sent", "input": "not_observed", "response": "not_observed",
                 "cursor": cursor, "responses": [], "matched_response": None, "history_gap": False}
        try:
            save_request(directory, state)
        except OSError as error:
            raise _record_error(directory, state, error)

        def before_write():
            state["transport"] = "write_started"
            save_request(directory, state)

        try:
            client.send_frame(target, state["frame"], before_write)
            state["transport"] = "written"
            save_request(directory, state)
        except (ClaudeError, HistoryError, OSError) as error:
            if state["transport"] == "write_started":
                state["transport"] = "delivery_unknown"
            raise _record_error(directory, state, error)
        return _observe_saved(directory, state, client)


def _inspect(directory: Path, client: NativeClient) -> dict:
    with request_lock(directory):
        state = load_request(directory)
        return _observe_saved(directory, state, client)


def _bounded_timeout(value: str) -> float:
    try:
        number = float(value)
        if not math.isfinite(number) or not 0 <= number <= 60:
            raise ValueError("range")
        return number
    except ValueError as error:
        raise argparse.ArgumentTypeError("Timeout must be between 0 and 60 seconds") from error


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("sessions", help="List existing live session targets")
    send = commands.add_parser("send", help="Save and post one immutable request")
    send.add_argument("--session", required=True, help="Exact live session UUID")
    send.add_argument("--message-file", required=True, help="Caller-authored UTF-8 text")
    send.add_argument("--expect-reply", action="store_true", help="Add a reply attribution contract")
    send.add_argument("--run-dir", help="Request workspace; existing requests are only re-observed")
    for name in ("status", "read", "wait"):
        command = commands.add_parser(name)
        command.add_argument("run_dir")
        if name == "wait":
            command.add_argument("--timeout", type=_bounded_timeout, default=30.0)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        client = NativeClient()
        if args.command == "sessions":
            rows = client.list_sessions()
            available = any(row.get("available", False) for row in rows)
            result = {"available": available, "sessions": rows}
            if not available:
                result["reason"] = "session_unavailable"
        elif args.command == "send":
            result = _send(args, client)
        else:
            directory = Path(args.run_dir).expanduser().resolve()
            if args.command == "wait":
                deadline = time.monotonic() + args.timeout
                while True:
                    result = _inspect(directory, client)
                    if result["matched_response"] is not None:
                        result["timed_out"] = False
                        break
                    if result["response"] == "ambiguous" or result["session"].get("status") == "waiting":
                        result["timed_out"] = False
                        break
                    if result["responses"]:
                        with request_lock(directory):
                            expects_reply = load_request(directory)["expect_reply"]
                        if not expects_reply:
                            result["timed_out"] = False
                            break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result["timed_out"] = True
                        break
                    time.sleep(min(1.0, remaining))
            else:
                result = _inspect(directory, client)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result["available"] else 3
    except (ClaudeError, HistoryError) as error:
        code = getattr(error, "code", "history_unavailable")
        print(json.dumps({"available": False, "reason": code,
                          "error": {"code": code, "message": str(error)},
                          **getattr(error, "context", {})}, ensure_ascii=False))
        return 3 if code in {"session_unavailable", "unsupported_platform", "unsupported_protocol", "claude_not_found"} else 1
    except OSError:
        print(json.dumps({"available": False, "reason": "record_unavailable", "error":
                         {"code": "record_unavailable", "message": "Cannot persist or access request records"}}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
