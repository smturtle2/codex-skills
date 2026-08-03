from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from .server import serve
from .store import (
    DEFAULT_ROOT,
    ID_PATTERN,
    WorldSimError,
    commit_bundle,
    init_session,
    inspect_world,
    new_session_id,
    next_turn_context,
    resolve_session,
    session_status,
    write_active_session,
)


def _add_locator(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT, help="Session root (default: world-runs)")
    parser.add_argument("--session", help="Session ID; defaults to the active session")


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _load_payload(value: str) -> Any:
    if value == "-":
        raw = sys.stdin.read()
    else:
        raw = pathlib.Path(value).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise WorldSimError(f"Invalid TurnBundle JSON: {error}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex-native persistent world simulator")
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="Create or resume a world and run its browser UI")
    start.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    start.add_argument("--session", help="Existing session ID to resume")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=8765)
    start.add_argument("--no-open-browser", action="store_true")

    next_parser = commands.add_parser("next", help="Wait for and claim the next browser input")
    _add_locator(next_parser)
    next_parser.add_argument("--poll", type=float, default=0.5, help="Polling interval in seconds")

    commit = commands.add_parser("commit", help="Atomically commit a TurnBundle JSON file")
    _add_locator(commit)
    commit.add_argument("payload", help="JSON file path, or - for stdin")

    status = commands.add_parser("status", help="Show session metadata and record counts")
    _add_locator(status)

    inspect = commands.add_parser("inspect", help="Inspect full GM-visible world records")
    _add_locator(inspect)
    inspect.add_argument("query", nargs="?", default="")
    return parser


def run(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if args.command == "start":
        root.mkdir(parents=True, exist_ok=True)
        if args.session:
            if not ID_PATTERN.fullmatch(args.session):
                raise WorldSimError("Session IDs must use lowercase letters, digits, and hyphens.")
            session_path = resolve_session(root, args.session)
        else:
            session_path = root / new_session_id(root)
            init_session(session_path)
        write_active_session(root, session_path.name)
        serve(
            session_path,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open_browser,
        )
        return

    session_path = resolve_session(root, args.session)
    write_active_session(root, session_path.name)
    if args.command == "next":
        if args.poll <= 0:
            raise WorldSimError("--poll must be greater than zero.")
        _print_json(next_turn_context(session_path, args.poll))
    elif args.command == "commit":
        _print_json(commit_bundle(session_path, _load_payload(args.payload)))
    elif args.command == "status":
        _print_json(session_status(session_path))
    elif args.command == "inspect":
        _print_json(inspect_world(session_path, args.query))


def main() -> int:
    parser = build_parser()
    try:
        run(parser.parse_args())
        return 0
    except (WorldSimError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
