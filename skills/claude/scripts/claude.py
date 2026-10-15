"""Connect to an already-open Claude Code session; never launch Claude."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from claude_connection import Connection, TERMINAL_ERRORS, error_code
from claude_history import HistoryError
from claude_native import ClaudeError, NativeClient


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("sessions", help="List existing live session targets")
    connect = commands.add_parser("connect", help="Keep a foreground stdin/stdout connection open")
    connect.add_argument("--session", required=True, help="Exact live session UUID")
    connect.add_argument("--run-dir", type=Path, help="New connection record directory")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        client = NativeClient()
        if args.command == "connect":
            return Connection(client, args.session, args.run_dir).run()
        rows = client.list_sessions()
        available = any(row.get("available", False) for row in rows)
        result = {"available": available, "sessions": rows}
        if not available:
            result["reason"] = "session_unavailable"
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
        return 0 if available else 3
    except (ClaudeError, HistoryError, OSError) as error:
        code = error_code(error)
        print(json.dumps({"type": "error", "available": False,
                          "error": {"code": code, "message": str(error)}},
                         ensure_ascii=False, allow_nan=False), flush=True)
        return 3 if code in TERMINAL_ERRORS else 1


if __name__ == "__main__":
    raise SystemExit(main())
