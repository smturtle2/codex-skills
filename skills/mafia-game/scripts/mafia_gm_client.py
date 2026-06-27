#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_SERVER = "http://127.0.0.1:8790"


def request_json(server: str, method: str, path: str, token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(urllib.parse.urljoin(server.rstrip("/") + "/", path.lstrip("/")), data=data, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GM client for the server-mediated Mafia game")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--session", required=True)
    parser.add_argument("--token", help="GM bearer token")
    parser.add_argument("--create-session", action="store_true")
    parser.add_argument("--user-name", default="You")
    parser.add_argument("--seed")
    parser.add_argument("--state", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-timeout", type=float, default=20.0)
    parser.add_argument("--phase")
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--announce")
    parser.add_argument("--private", nargs=2, metavar=("SEAT", "TEXT"))
    parser.add_argument("--eliminate", metavar="SEAT")
    parser.add_argument("--no-reveal-role", action="store_true")
    parser.add_argument("--game-over", metavar="WINNER")
    parser.add_argument("--note")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.create_session:
            payload: dict[str, Any] = {"session_id": args.session, "user_name": args.user_name}
            if args.seed is not None:
                payload["seed"] = args.seed
            print_json(request_json(args.server, "POST", "/api/session", body=payload))
            return 0
        if not args.token:
            raise RuntimeError("--token is required unless --create-session is used")
        query = urllib.parse.urlencode({"session": args.session})
        if args.state:
            print_json(request_json(args.server, "GET", f"/api/gm/state?{query}", token=args.token))
            return 0
        if args.phase:
            body: dict[str, Any] = {"event_type": "phase_change", "phase": args.phase}
            if args.duration_seconds is not None:
                body["duration_seconds"] = args.duration_seconds
            print_json(request_json(args.server, "POST", f"/api/gm/event?{query}", token=args.token, body=body))
            return 0
        if args.announce:
            print_json(request_json(args.server, "POST", f"/api/gm/event?{query}", token=args.token, body={"event_type": "public_announcement", "text": args.announce}))
            return 0
        if args.private:
            seat, text = args.private
            print_json(request_json(args.server, "POST", f"/api/gm/event?{query}", token=args.token, body={"event_type": "private_notice", "target": seat, "text": text}))
            return 0
        if args.eliminate:
            print_json(
                request_json(
                    args.server,
                    "POST",
                    f"/api/gm/event?{query}",
                    token=args.token,
                    body={"event_type": "eliminate", "target": args.eliminate, "reveal_role": not args.no_reveal_role},
                )
            )
            return 0
        if args.game_over:
            print_json(request_json(args.server, "POST", f"/api/gm/event?{query}", token=args.token, body={"event_type": "game_over", "winner": args.game_over}))
            return 0
        if args.note:
            print_json(request_json(args.server, "POST", f"/api/gm/event?{query}", token=args.token, body={"event_type": "gm_note", "text": args.note}))
            return 0
        if args.watch:
            last_event = 0
            while True:
                watch_query = urllib.parse.urlencode({"session": args.session, "scope": "gm", "after": last_event, "timeout": args.poll_timeout})
                payload = request_json(args.server, "GET", f"/api/events/watch?{watch_query}", token=args.token)
                for event in payload.get("events", []):
                    print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
                    last_event = max(last_event, int(event.get("event_number", 0)))
                if not payload.get("events"):
                    time.sleep(0.2)
        raise RuntimeError("select one GM action")
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"mafia_gm_client: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
