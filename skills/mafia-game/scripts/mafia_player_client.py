#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_SERVER = "http://127.0.0.1:8790"


def request_json(server: str, method: str, path: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(urllib.parse.urljoin(server.rstrip("/") + "/", path.lstrip("/")), data=data, method=method)
    request.add_header("Accept", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def submit_event(args: argparse.Namespace, body: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({"session": args.session})
    return request_json(args.server, "POST", f"/api/player/event?{query}", args.token, body)


def seat_state(args: argparse.Namespace) -> dict[str, Any]:
    query = urllib.parse.urlencode({"session": args.session, "seat": args.seat})
    return request_json(args.server, "GET", f"/api/seat/state?{query}", args.token)


def living_targets(state: dict[str, Any], include_self: bool = False) -> list[dict[str, Any]]:
    return [
        seat
        for seat in state.get("table", [])
        if seat.get("alive") and (include_self or seat.get("seat_id") != state.get("seat_id"))
    ]


def choose_target(state: dict[str, Any], rng: random.Random, include_self: bool = False) -> dict[str, Any] | None:
    candidates = living_targets(state, include_self=include_self)
    if not candidates:
        return None
    if rng.random() < 0.55:
        return rng.choice(candidates)
    votes: dict[str, int] = {}
    for event in state.get("events", []):
        if event.get("event_type") == "vote":
            target = event.get("payload", {}).get("target")
            if target:
                votes[target] = votes.get(target, 0) + 1
    candidates.sort(key=lambda seat: (votes.get(str(seat.get("seat_id")), 0), rng.random()), reverse=True)
    return candidates[0]


def public_messages(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in state.get("events", [])
        if event.get("event_type") in {"public_message", "public_announcement", "player_attended"}
        and event.get("visibility") == "public"
    ]


def available_night_action(state: dict[str, Any]) -> str | None:
    for action in state.get("allowed_actions", []):
        if str(action).startswith("night_action:"):
            return str(action).split(":", 1)[1]
    return None


def short_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)].rstrip() + "..."


def make_public_message(state: dict[str, Any], rng: random.Random) -> str:
    target = choose_target(state, rng)
    target_name = str(target.get("name")) if target else "누군가"
    persona = state.get("persona_view", {})
    catchphrase = str(persona.get("catchphrase") or "").strip()
    label = str(persona.get("label") or "")
    message_max = int(persona.get("message_max_chars") or 140)
    messages = public_messages(state)
    if len(messages) <= 2:
        templates = [
            f"{catchphrase} 일단 조용한 사람부터 볼게요. {target_name}, 지금 느낌 한 줄만요.",
            f"첫 느낌은 {target_name} 쪽이 비어 보여요. 너무 조용하면 더 봅니다.",
            f"저는 가볍게 시작할게요. {target_name}, 지금 누구 의심해요?",
        ]
    else:
        templates = [
            f"{target_name}, 방금 흐름에서 살짝 빠진 느낌이에요. 한 번만 더 말해줘요.",
            f"{catchphrase} 저는 {target_name} 쪽 반응이 좀 걸려요.",
            f"몰이는 싫은데, 지금은 {target_name} 대답을 더 듣고 싶어요.",
            f"{target_name} 말이 아직 얇아요. 짧게라도 근거 하나 줘요.",
            f"지금 판은 너무 조용해요. 저는 {target_name} 체크해둘게요.",
        ]
    if "장난" in label or "밈" in label:
        templates += [f"{target_name}, 그 침묵 좀 연기 같아요. 아니면 말로 풀어봐요.", f"{catchphrase} 일단 {target_name} 반응 보고 갈게요."]
    elif "조용" in label or "짧게" in label:
        templates += [f"{target_name} 쪽 봅니다.", f"길게 말 안 할게요. {target_name}이 걸려요."]
    elif "말꼬리" in label:
        templates += [f"{target_name}, 방금 표현이 애매했어요. 왜 그렇게 말했어요?", f"저는 {target_name} 말끝이 좀 걸립니다."]
    elif "직진" in label or "급발진" in label:
        templates += [f"저는 {target_name} 의심합니다. 돌려 말 안 할게요.", f"{catchphrase} 지금은 {target_name} 먼저 봐야 해요."]
    elif "중재" in label or "차분" in label:
        templates += [f"잠깐 정리해요. {target_name} 답만 듣고 넘어가죠.", f"{target_name}, 짧게만 답해줘요. 지금 흐름이 꼬였어요."]
    text = rng.choice([template for template in templates if template.strip()])
    return short_text(text, message_max)


def make_mafia_message(state: dict[str, Any], rng: random.Random) -> str:
    target = choose_target(state, rng)
    target_name = str(target.get("name")) if target else "조용한 쪽"
    persona = state.get("persona_view", {})
    message_max = int(persona.get("message_max_chars") or 140)
    return short_text(rng.choice([f"저는 {target_name} 쪽 보고 있어요. 너무 튀지 말고 맞춰가죠.", f"{target_name} 후보 괜찮아 보여요. 공개 채팅에선 살짝만 건드릴게요."]), message_max)


def retry_notice(exc: Exception, failures: int) -> None:
    payload = {"client_status": "retrying", "failure_count": failures, "error": str(exc)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)


def run_watch(args: argparse.Namespace) -> None:
    last_event = 0
    failures = 0
    while True:
        try:
            query = urllib.parse.urlencode(
                {
                    "session": args.session,
                    "scope": "seat",
                    "seat": args.seat,
                    "after": last_event,
                    "timeout": args.poll_timeout,
                }
            )
            payload = request_json(args.server, "GET", f"/api/events/watch?{query}", args.token)
            failures = 0
        except Exception as exc:
            failures += 1
            retry_notice(exc, failures)
            time.sleep(min(10.0, 1.0 + failures))
            continue
        for event in payload.get("events", []):
            print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
            last_event = max(last_event, int(event.get("event_number", 0)))
        if not payload.get("events"):
            time.sleep(0.2)


def run_auto(args: argparse.Namespace) -> None:
    rng = random.Random(f"{args.session}:{args.seat}:{time.time_ns()}")
    phase_key: tuple[str, int, str] | None = None
    spoke_this_phase = False
    voted_this_phase = False
    night_done = False
    mafia_note_done = False
    next_speak_at = 0.0
    last_spoken_event = 0
    failures = 0
    while True:
        try:
            state = seat_state(args)
            failures = 0
        except Exception as exc:
            failures += 1
            retry_notice(exc, failures)
            time.sleep(min(10.0, 1.0 + failures))
            continue

        key = (str(state.get("phase")), int(state.get("day") or 0), str(state.get("phase_started_at") or ""))
        if key != phase_key:
            phase_key = key
            spoke_this_phase = False
            voted_this_phase = False
            night_done = False
            mafia_note_done = False
            last_spoken_event = 0
            next_speak_at = time.monotonic() + rng.uniform(0.5, args.max_delay)

        phase = str(state.get("phase") or "")
        if phase == "setup":
            time.sleep(rng.uniform(1.0, 2.0))
            continue

        try:
            now = time.monotonic()
            if phase == "day":
                should_speak = not spoke_this_phase
                if not should_speak and now >= next_speak_at:
                    should_speak = int(state.get("last_event_number") or 0) > last_spoken_event and rng.random() < 0.45
                    if not should_speak:
                        next_speak_at = now + rng.uniform(args.min_delay, args.max_delay)
                if should_speak:
                    submit_event(args, {"event_type": "public_message", "text": make_public_message(state, rng)})
                    spoke_this_phase = True
                    last_spoken_event = int(state.get("last_event_number") or 0)
                    next_speak_at = now + rng.uniform(args.min_delay * 1.8, args.max_delay * 2.2)
                elif not voted_this_phase:
                    remaining = state.get("phase_remaining_seconds")
                    if (remaining is not None and int(remaining) <= 60) or (len(public_messages(state)) >= 18 and rng.random() < 0.12):
                        target = choose_target(state, rng)
                        if target:
                            submit_event(args, {"event_type": "vote", "target": target["name"]})
                            voted_this_phase = True
            elif phase == "night":
                if "mafia" in state.get("allowed_channels", []) and not mafia_note_done:
                    submit_event(args, {"event_type": "private_message", "channel": "mafia", "text": make_mafia_message(state, rng)})
                    mafia_note_done = True
                action = available_night_action(state)
                if action and not night_done:
                    target = choose_target(state, rng, include_self=(action == "protect"))
                    if target:
                        submit_event(args, {"event_type": "night_action", "action": action, "target": target["name"]})
                        night_done = True
        except Exception as exc:
            retry_notice(exc, 1)
        time.sleep(rng.uniform(args.min_delay, args.max_delay))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous seat client for the server-mediated Mafia game")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--session", required=True)
    parser.add_argument("--seat", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--state", action="store_true")
    parser.add_argument("--watch", action="store_true", help="Continuously print visible seat events as JSON lines")
    parser.add_argument("--auto", action="store_true", help="Autonomously keep playing through this seat's server projection")
    parser.add_argument("--poll-timeout", type=float, default=20.0)
    parser.add_argument("--min-delay", type=float, default=4.0)
    parser.add_argument("--max-delay", type=float, default=9.0)
    parser.add_argument("--say")
    parser.add_argument("--raw")
    parser.add_argument("--vote")
    parser.add_argument("--mafia")
    parser.add_argument("--night", nargs=2, metavar=("ACTION", "TARGET"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.state:
            print_json(seat_state(args))
            return 0
        if args.auto:
            run_auto(args)
            return 0
        if args.say:
            print_json(submit_event(args, {"event_type": "public_message", "text": args.say}))
            return 0
        if args.raw:
            print_json(submit_event(args, {"event_type": "raw_input", "text": args.raw}))
            return 0
        if args.vote:
            print_json(submit_event(args, {"event_type": "vote", "target": args.vote}))
            return 0
        if args.mafia:
            print_json(submit_event(args, {"event_type": "private_message", "channel": "mafia", "text": args.mafia}))
            return 0
        if args.night:
            action, target = args.night
            print_json(submit_event(args, {"event_type": "night_action", "action": action, "target": target}))
            return 0
        if args.watch:
            run_watch(args)
            return 0
        raise RuntimeError("select one seat action")
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"mafia_player_client: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
