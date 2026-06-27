#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import random
import secrets
import sys
import threading
import time
import urllib.parse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


DEFAULT_ROOT = pathlib.Path("mafia-runs")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790
DEFAULT_SESSION = "default"
DEFAULT_ROLES = ["mafia", "mafia", "detective", "doctor", "citizen", "citizen", "citizen", "citizen"]
DEFAULT_NICKNAMES = [
    "카페라떼",
    "밤하늘별빛",
    "청바지도둑",
    "모카번",
    "빵굽는곰",
    "달빛여우",
    "낙엽스프",
    "시나몬조아",
    "새벽탐정",
    "검은우산",
    "골목시계",
    "푸른성냥",
    "은빛라디오",
    "호두신문",
    "비밀편지",
    "노을가로등",
]
DEFAULT_PERSONAS = [
    {"label": "말 빠른 장난러", "voice": "툭툭 농담을 섞지만 의심은 바로 이름 찍어서 말한다.", "catchphrase": "잠깐, 이거 냄새 나는데?"},
    {"label": "눈치 빠른 리액션러", "voice": "상대 말에 바로 반응하고 어색한 침묵을 가볍게 찌른다.", "catchphrase": "오, 방금 좀 걸렸어요."},
    {"label": "느긋한 빈정러", "voice": "느긋하게 웃듯 말하지만 빠져나가는 말에는 살짝 빈정댄다.", "catchphrase": "흠, 너무 매끈한데요."},
    {"label": "급발진 추리러", "voice": "확신이 빠르고 말도 빠르다. 틀릴 수 있어도 일단 던진다.", "catchphrase": "저 지금 꽂혔어요."},
    {"label": "조용한 한마디러", "voice": "말수는 적지만 한 문장으로 분위기를 바꾼다.", "catchphrase": "저는 거기 봅니다."},
    {"label": "헛웃음 방어러", "voice": "몰리면 헛웃음으로 넘기지만 반격은 짧고 세게 한다.", "catchphrase": "아니 그건 좀 억지죠."},
    {"label": "메모하는 의심러", "voice": "방금 나온 말을 기억했다가 자연스럽게 다시 꺼낸다.", "catchphrase": "그 말은 저장해둘게요."},
    {"label": "밈 좋아하는 수다러", "voice": "가벼운 표현을 쓰되 판 읽기는 은근히 날카롭다.", "catchphrase": "이 흐름, 좀 수상한 맛."},
    {"label": "차분한 압박러", "voice": "목소리는 낮지만 질문은 피하기 어렵게 좁힌다.", "catchphrase": "그럼 하나만 답해줘요."},
    {"label": "감으로 찍는 촉러", "voice": "논리보다 분위기와 타이밍을 믿고 솔직하게 말한다.", "catchphrase": "촉이 자꾸 그쪽이에요."},
    {"label": "말꼬리 잡는 타입", "voice": "단어 하나를 집요하게 물고 늘어지지만 장황하지 않다.", "catchphrase": "그 표현 왜 썼어요?"},
    {"label": "친근한 중재러", "voice": "싸움은 말리되 애매한 사람은 웃으면서 불러낸다.", "catchphrase": "잠깐만, 정리하고 가요."},
    {"label": "대놓고 직진러", "voice": "돌려 말하지 않고 의심 대상을 바로 부른다.", "catchphrase": "저는 그냥 말할게요."},
    {"label": "느낌표 많은 몰입러", "voice": "반응이 크고 감정 표현이 많지만 메시지는 짧다.", "catchphrase": "아 이거 진짜 이상해요!"},
    {"label": "피곤한 현실러", "voice": "귀찮아하는 듯하지만 핵심 아닌 말은 바로 쳐낸다.", "catchphrase": "복잡하게 말고요."},
    {"label": "살짝 삐딱한 관찰러", "voice": "한 발 물러서서 보다가 흐름이 이상하면 바로 태클 건다.", "catchphrase": "그림이 좀 안 맞네요."},
    {"label": "수상하면 웃는 타입", "voice": "의심스러운 순간에 웃으며 분위기를 가볍게 흔든다.", "catchphrase": "왜 웃기지 이거."},
    {"label": "한 박자 늦은 추리러", "voice": "조금 늦게 따라오지만 놓친 포인트를 뜬금없이 잘 잡는다.", "catchphrase": "아, 이제 봤는데요."},
    {"label": "깔끔한 요약러", "voice": "길어진 대화를 짧게 묶고 빠진 사람을 지목한다.", "catchphrase": "정리하면 이거예요."},
    {"label": "의심 많은 친구", "voice": "친구처럼 말하지만 쉽게 믿지 않고 확인 질문을 던진다.", "catchphrase": "나만 찝찝해요?"},
    {"label": "장난 반 진심 반", "voice": "장난처럼 시작해서 마지막엔 진짜 의심을 남긴다.", "catchphrase": "농담 같죠? 아닌데요."},
    {"label": "담백한 팩트러", "voice": "꾸미지 않고 보이는 행동만 짧게 말한다.", "catchphrase": "보이는 건 이거예요."},
    {"label": "괜히 찔러보는 타입", "voice": "확정하지 않고 여러 사람을 가볍게 건드려 반응을 본다.", "catchphrase": "그냥 찔러보는 건데요."},
    {"label": "진지해지면 무서운 타입", "voice": "평소엔 가볍다가 의심이 생기면 말투가 단호해진다.", "catchphrase": "여기서부터 진지하게요."},
    {"label": "말 아끼는 방어러", "voice": "자기 방어는 짧게 하고 남의 과한 몰이를 더 의심한다.", "catchphrase": "그 몰이는 너무 빠른데요."},
    {"label": "흐름 보는 판독러", "voice": "개별 말보다 누가 흐름을 만들고 피하는지 본다.", "catchphrase": "흐름이 그쪽으로 가네요."},
    {"label": "살짝 허세 있는 추리러", "voice": "자신만만하게 말하지만 근거는 간단히만 붙인다.", "catchphrase": "제가 보기엔 답 나왔어요."},
    {"label": "눈치 없는 척하는 타입", "voice": "모르는 척 질문하면서 상대의 허술한 답을 끌어낸다.", "catchphrase": "어, 그럼 이건 뭐예요?"},
    {"label": "짧게 치고 빠지는 타입", "voice": "한 번 말하고 길게 싸우지 않는다. 대신 포인트가 선명하다.", "catchphrase": "제 말은 여기까지."},
    {"label": "분위기 깨는 솔직러", "voice": "좋게 포장하지 않고 어색한 부분을 바로 말한다.", "catchphrase": "솔직히 이상해요."},
    {"label": "천천히 조이는 타입", "voice": "부드럽게 시작해서 점점 질문을 좁힌다.", "catchphrase": "그럼 다음 질문이요."},
    {"label": "끝까지 의심 남기는 타입", "voice": "확정하지 않아도 마지막에 의심 씨앗을 남긴다.", "catchphrase": "일단 표시해둘게요."},
]
AI_MESSAGE_MAX_CHARS = 140
VALID_PHASES = {"setup", "day", "night", "game_over"}
REQUIRED_PLAYERS = 8
DEFAULT_DAY_SECONDS = 300
DEFAULT_NIGHT_SECONDS = 120
ROLE_ACTIONS = {
    "mafia": {"kill"},
    "detective": {"investigate"},
    "doctor": {"protect"},
    "citizen": set(),
}


class MafiaGameError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def default_phase_duration(phase: str) -> int | None:
    if phase == "day":
        return DEFAULT_DAY_SECONDS
    if phase == "night":
        return DEFAULT_NIGHT_SECONDS
    return None


def remaining_seconds(ends_at: str | None) -> int | None:
    if not ends_at:
        return None
    return max(0, int((parse_utc_timestamp(ends_at) - utc_now()).total_seconds()))


def atomic_write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def append_jsonl(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def safe_session_id(session_id: str) -> str:
    value = session_id.strip()
    if not value:
        raise MafiaGameError("session_id is required")
    if any(part in {"", ".", ".."} for part in pathlib.PurePosixPath(value).parts):
        raise MafiaGameError("session_id must not contain path traversal")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(char not in allowed for char in value):
        raise MafiaGameError("session_id may contain only letters, digits, hyphens, and underscores")
    return value


def token() -> str:
    return secrets.token_urlsafe(24)


def random_nicknames(rng: random.Random, nickname_pool: list[str] | None = None) -> list[str]:
    nicknames = [name.strip() for name in (nickname_pool or DEFAULT_NICKNAMES) if name.strip()]
    if len({name.lower() for name in nicknames}) < 8:
        raise MafiaGameError("at least eight unique nicknames are required")
    rng.shuffle(nicknames)
    selected: list[str] = []
    seen: set[str] = set()
    for nickname in nicknames:
        key = nickname.lower()
        if key in seen:
            continue
        selected.append(nickname)
        seen.add(key)
        if len(selected) == 8:
            return selected
    raise MafiaGameError("at least eight unique nicknames are required")


def random_personas(rng: random.Random) -> list[dict[str, Any]]:
    personas = [deepcopy(persona) for persona in DEFAULT_PERSONAS]
    if len({persona["label"].lower() for persona in personas}) < 8:
        raise MafiaGameError("at least eight unique personas are required")
    rng.shuffle(personas)
    return personas[:8]


def persona_for_index(index: int) -> dict[str, Any]:
    return deepcopy(DEFAULT_PERSONAS[index % len(DEFAULT_PERSONAS)])


def constrain_ai_text(seat: dict[str, Any], text: str) -> str:
    if seat.get("kind") != "ai" or len(text) <= AI_MESSAGE_MAX_CHARS:
        return text
    return text[: AI_MESSAGE_MAX_CHARS - 3].rstrip() + "..."


def public_seat(seat: dict[str, Any]) -> dict[str, Any]:
    return {
        "seat_id": seat["seat_id"],
        "name": seat["name"],
        "persona_label": seat.get("persona", {}).get("label"),
        "kind": seat["kind"],
        "alive": bool(seat.get("alive", True)),
        "attended": bool(seat.get("attended", False)),
        "revealed_role": seat.get("revealed_role"),
    }


class MafiaGameStore:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def session_path(self, session_id: str) -> pathlib.Path:
        return self.root / safe_session_id(session_id)

    def state_path(self, session_id: str) -> pathlib.Path:
        return self.session_path(session_id) / "state.json"

    def events_path(self, session_id: str) -> pathlib.Path:
        return self.session_path(session_id) / "events" / "canonical.jsonl"

    def create_session(
        self,
        session_id: str,
        user_name: str = "You",
        seed: str | int | None = None,
        nickname_pool: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session_id = safe_session_id(session_id)
            path = self.session_path(session_id)
            if self.state_path(session_id).exists():
                raise MafiaGameError("session already exists", 409)

            role_order = list(DEFAULT_ROLES)
            if seed is not None:
                role_rng: random.Random = random.Random(f"{seed}:roles")
                nickname_rng: random.Random = random.Random(f"{seed}:nicknames")
                persona_rng: random.Random = random.Random(f"{seed}:personas")
            else:
                role_rng = random.SystemRandom()
                nickname_rng = random.SystemRandom()
                persona_rng = random.SystemRandom()
            role_rng.shuffle(role_order)
            names = random_nicknames(nickname_rng, nickname_pool)
            personas = random_personas(persona_rng)

            seats: list[dict[str, Any]] = []
            for index in range(8):
                seat_id = f"seat-{index + 1:02d}"
                seats.append(
                    {
                        "seat_id": seat_id,
                        "name": names[index],
                        "kind": "user" if index == 0 else "ai",
                        "role": role_order[index],
                        "persona": personas[index],
                        "alive": True,
                        "attended": False,
                        "last_seen_at": None,
                        "revealed_role": None,
                    }
                )

            auth = {
                "gm_token": token(),
                "user_token": token(),
                "seat_tokens": {seat["seat_id"]: token() for seat in seats if seat["kind"] == "ai"},
            }
            now = utc_now()
            state = {
                "version": 1,
                "session_id": session_id,
                "created_at": utc_timestamp(now),
                "phase": "setup",
                "day": 1,
                "timing_mode": "timed_free_chat",
                "phase_started_at": utc_timestamp(now),
                "phase_duration_seconds": None,
                "phase_ends_at": None,
                "required_attendance_count": REQUIRED_PLAYERS,
                "winner": None,
                "next_event_number": 1,
                "seats": seats,
                "auth": auth,
            }
            path.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.state_path(session_id), state)
            self.events_path(session_id).parent.mkdir(parents=True, exist_ok=True)
            self.events_path(session_id).write_text("", encoding="utf-8")
            self.append_event(
                session_id,
                actor={"kind": "server"},
                event_type="session_created",
                visibility="public",
                channel="public",
                payload={
                    "message": "A new Mafia lobby is waiting for all participants.",
                    "seats": [public_seat(seat) for seat in seats],
                },
            )
            return self.bootstrap_payload(session_id)

    def bootstrap_payload(self, session_id: str) -> dict[str, Any]:
        state = self.load_state(session_id)
        return {
            "session_id": state["session_id"],
            "gm_token": state["auth"]["gm_token"],
            "user_token": state["auth"]["user_token"],
            "seats": [
                {
                    "seat_id": seat["seat_id"],
                    "name": seat["name"],
                    "kind": seat["kind"],
                    "token": state["auth"]["seat_tokens"].get(seat["seat_id"]),
                }
                for seat in state["seats"]
            ],
        }

    def user_token(self, session_id: str) -> str:
        return str(self.load_state(session_id)["auth"]["user_token"])

    def load_state(self, session_id: str) -> dict[str, Any]:
        path = self.state_path(session_id)
        if not path.exists():
            raise MafiaGameError("session not found", 404)
        state = read_json(path)
        migrated = False
        if self.ensure_timing_fields(state):
            migrated = True
        if self.ensure_persona_fields(state):
            migrated = True
        if self.ensure_attendance_fields(state):
            migrated = True
        if migrated:
            self.save_state(session_id, state)
        return state

    def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        atomic_write_json(self.state_path(session_id), state)

    def start_phase_timer(self, state: dict[str, Any], duration_seconds: int | None = None) -> None:
        phase = str(state.get("phase") or "")
        duration = duration_seconds if duration_seconds is not None else default_phase_duration(phase)
        now = utc_now()
        state["timing_mode"] = "timed_free_chat"
        state["phase_started_at"] = utc_timestamp(now)
        state["phase_duration_seconds"] = duration
        state["phase_ends_at"] = utc_timestamp(now + timedelta(seconds=duration)) if duration else None

    def ensure_timing_fields(self, state: dict[str, Any]) -> bool:
        if state.get("timing_mode") == "timed_free_chat" and "phase_started_at" in state and "phase_duration_seconds" in state and "phase_ends_at" in state:
            return False
        self.start_phase_timer(state)
        return True

    def ensure_persona_fields(self, state: dict[str, Any]) -> bool:
        changed = False
        valid_labels = {persona["label"] for persona in DEFAULT_PERSONAS}
        for index, seat in enumerate(state.get("seats", [])):
            persona = seat.get("persona")
            if not isinstance(persona, dict) or persona.get("label") not in valid_labels or not persona.get("voice"):
                seat["persona"] = persona_for_index(index)
                changed = True
        return changed

    def ensure_attendance_fields(self, state: dict[str, Any]) -> bool:
        changed = False
        if "required_attendance_count" not in state:
            state["required_attendance_count"] = REQUIRED_PLAYERS
            changed = True
        for seat in state.get("seats", []):
            if "attended" not in seat:
                seat["attended"] = False
                changed = True
            if "last_seen_at" not in seat:
                seat["last_seen_at"] = None
                changed = True
        return changed

    def attendance_summary(self, state: dict[str, Any]) -> dict[str, Any]:
        seats = state.get("seats", [])
        required = int(state.get("required_attendance_count") or REQUIRED_PLAYERS)
        attended = sum(1 for seat in seats if seat.get("attended"))
        return {
            "attended": attended,
            "required": required,
            "ready": attended >= required,
        }

    def all_attended(self, state: dict[str, Any]) -> bool:
        return bool(self.attendance_summary(state)["ready"])

    def record_attendance(self, session_id: str, seat_id: str) -> None:
        with self._lock:
            state = self.load_state(session_id)
            seat = self.seat(state, seat_id)
            first_seen = not seat.get("attended")
            if not first_seen:
                return
            seat["attended"] = True
            seat["last_seen_at"] = utc_timestamp()
            self.save_state(session_id, state)
            summary = self.attendance_summary(state)
            actor_kind = "user" if seat.get("kind") == "user" else "seat"
            self.append_event(
                session_id,
                actor={"kind": actor_kind, "seat_id": seat["seat_id"], "name": seat["name"]},
                event_type="player_attended",
                visibility="public",
                channel="public",
                payload={
                    "name": seat["name"],
                    "attended_count": summary["attended"],
                    "required_count": summary["required"],
                },
            )

    def events(self, session_id: str) -> list[dict[str, Any]]:
        self.load_state(session_id)
        return read_jsonl(self.events_path(session_id))

    def append_event(
        self,
        session_id: str,
        actor: dict[str, Any],
        event_type: str,
        visibility: str,
        channel: str,
        payload: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self.load_state(session_id)
            event_number = int(state.get("next_event_number", 1))
            event = {
                "event_id": f"evt_{event_number:06d}",
                "event_number": event_number,
                "created_at": utc_timestamp(),
                "actor": actor,
                "event_type": event_type,
                "visibility": visibility,
                "channel": channel,
                "recipients": recipients or [],
                "payload": payload or {},
            }
            state["next_event_number"] = event_number + 1
            self.save_state(session_id, state)
            append_jsonl(self.events_path(session_id), event)
            return event

    def authenticate(self, session_id: str, bearer: str | None) -> dict[str, Any]:
        if not bearer:
            raise MafiaGameError("missing bearer token", 401)
        state = self.load_state(session_id)
        auth = state["auth"]
        if bearer == auth["gm_token"]:
            return {"kind": "gm", "seat_id": None}
        if bearer == auth["user_token"]:
            return {"kind": "user", "seat_id": "seat-01"}
        for seat_id, seat_token in auth["seat_tokens"].items():
            if bearer == seat_token:
                return {"kind": "seat", "seat_id": seat_id}
        raise MafiaGameError("invalid bearer token", 403)

    def seat(self, state: dict[str, Any], seat_id: str) -> dict[str, Any]:
        for seat in state["seats"]:
            if seat["seat_id"] == seat_id:
                return seat
        raise MafiaGameError("seat not found", 404)

    def resolve_target(self, state: dict[str, Any], raw_target: str) -> dict[str, Any]:
        target = raw_target.strip()
        if not target:
            raise MafiaGameError("target is required")
        for seat in state["seats"]:
            if seat["seat_id"] == target or seat["name"].lower() == target.lower():
                return seat
        raise MafiaGameError("target seat not found")

    def known_teammates(self, state: dict[str, Any], seat: dict[str, Any]) -> list[dict[str, Any]]:
        if seat["role"] != "mafia":
            return []
        return [
            {"seat_id": other["seat_id"], "name": other["name"], "alive": bool(other.get("alive", True))}
            for other in state["seats"]
            if other["role"] == "mafia" and other["seat_id"] != seat["seat_id"]
        ]

    def allowed_channels(self, seat: dict[str, Any]) -> list[str]:
        if not seat.get("alive", True):
            return []
        channels = ["public", f"seat:{seat['seat_id']}"]
        if seat["role"] == "mafia":
            channels.append("mafia")
        return channels

    def allowed_actions(self, seat: dict[str, Any]) -> list[str]:
        if not seat.get("alive", True):
            return []
        actions = ["public_message", "private_message", "vote"]
        for role_action in sorted(ROLE_ACTIONS.get(seat["role"], set())):
            actions.append(f"night_action:{role_action}")
        return actions

    def event_visible_to(self, state: dict[str, Any], event: dict[str, Any], identity: dict[str, Any]) -> bool:
        if identity["kind"] == "gm":
            return True
        seat_id = identity["seat_id"]
        if event["visibility"] == "public":
            return True
        if event["visibility"] == "seat_private":
            return seat_id in event.get("recipients", [])
        if event["visibility"] == "mafia_private":
            seat = self.seat(state, seat_id)
            return seat["role"] == "mafia" and seat_id in event.get("recipients", [])
        return False

    def player_projection(self, session_id: str, bearer: str, seat_id: str | None = None) -> dict[str, Any]:
        identity = self.authenticate(session_id, bearer)
        if identity["kind"] == "gm":
            raise MafiaGameError("GM token cannot read player projection", 403)
        if seat_id and seat_id != identity["seat_id"]:
            raise MafiaGameError("token cannot read another seat projection", 403)
        self.record_attendance(session_id, identity["seat_id"])
        state = self.load_state(session_id)
        seat = self.seat(state, identity["seat_id"])
        visible_events = [event for event in self.events(session_id) if self.event_visible_to(state, event, identity)]
        return {
            "session_id": state["session_id"],
            "phase": state["phase"],
            "day": state["day"],
            "timing_mode": state.get("timing_mode", "timed_free_chat"),
            "phase_started_at": state.get("phase_started_at"),
            "phase_duration_seconds": state.get("phase_duration_seconds"),
            "phase_ends_at": state.get("phase_ends_at"),
            "phase_remaining_seconds": remaining_seconds(state.get("phase_ends_at")),
            "attendance": self.attendance_summary(state),
            "seat_id": seat["seat_id"],
            "seat_name": seat["name"],
            "role_view": {
                "own_role": seat["role"],
                "known_teammates": self.known_teammates(state, seat),
            },
            "persona_view": {
                "label": seat["persona"]["label"],
                "voice": seat["persona"]["voice"],
                "catchphrase": seat["persona"].get("catchphrase"),
                "message_max_chars": AI_MESSAGE_MAX_CHARS,
                "speech_rule": "AI players should speak in one or two short sentences and keep each message under the character limit.",
            },
            "table": [public_seat(other) for other in state["seats"]],
            "allowed_channels": self.allowed_channels(seat),
            "allowed_actions": self.allowed_actions(seat),
            "events": visible_events,
            "private_events": [event for event in visible_events if event["visibility"] != "public"],
            "last_event_number": max([event["event_number"] for event in visible_events], default=0),
            "server_time": utc_timestamp(),
        }

    def gm_projection(self, session_id: str, bearer: str) -> dict[str, Any]:
        identity = self.authenticate(session_id, bearer)
        if identity["kind"] != "gm":
            raise MafiaGameError("GM token required", 403)
        state = self.load_state(session_id)
        events = self.events(session_id)
        return {
            "session_id": state["session_id"],
            "state": deepcopy(state),
            "events": events,
            "last_event_number": max([event["event_number"] for event in events], default=0),
            "server_time": utc_timestamp(),
        }

    def parse_raw_input(self, state: dict[str, Any], seat: dict[str, Any], text: str) -> dict[str, Any]:
        value = text.strip()
        if not value:
            raise MafiaGameError("text is required")
        lower = value.lower()
        if lower.startswith("/vote "):
            return {"event_type": "vote", "target": value.split(None, 1)[1].strip()}
        if lower.startswith("/mafia "):
            return {"event_type": "private_message", "channel": "mafia", "text": value.split(None, 1)[1].strip()}
        if lower.startswith("/night "):
            parts = value.split()
            if len(parts) < 3:
                raise MafiaGameError("/night requires action and target")
            return {"event_type": "night_action", "action": parts[1], "target": parts[2]}
        if lower.startswith("/private "):
            return {"event_type": "private_message", "channel": f"seat:{seat['seat_id']}", "text": value.split(None, 1)[1].strip()}
        return {"event_type": "public_message", "text": value}

    def submit_player_event(self, session_id: str, bearer: str, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            identity = self.authenticate(session_id, bearer)
            if identity["kind"] == "gm":
                raise MafiaGameError("GM token cannot submit player events", 403)
            state = self.load_state(session_id)
            seat = self.seat(state, identity["seat_id"])
            if not seat.get("alive", True):
                raise MafiaGameError("dead players cannot submit player events", 403)

            event_body = body
            if body.get("event_type") == "raw_input":
                event_body = self.parse_raw_input(state, seat, str(body.get("text") or ""))
            event_type = str(event_body.get("event_type") or "")
            actor = {"kind": identity["kind"], "seat_id": seat["seat_id"], "name": seat["name"]}
            if state.get("phase") == "setup" and event_type in {"vote", "night_action"}:
                raise MafiaGameError("game has not started", 403)

            if event_type == "public_message":
                text = constrain_ai_text(seat, str(event_body.get("text") or "").strip())
                if not text:
                    raise MafiaGameError("text is required")
                event = self.append_event(session_id, actor, "public_message", "public", "public", {"text": text})
            elif event_type == "private_message":
                text = constrain_ai_text(seat, str(event_body.get("text") or "").strip())
                channel = str(event_body.get("channel") or "").strip()
                if not text:
                    raise MafiaGameError("text is required")
                if channel == "mafia":
                    if seat["role"] != "mafia":
                        raise MafiaGameError("mafia channel requires mafia role", 403)
                    recipients = [other["seat_id"] for other in state["seats"] if other["role"] == "mafia" and other.get("alive", True)]
                    event = self.append_event(session_id, actor, "private_message", "mafia_private", "mafia", {"text": text}, recipients)
                elif channel in {f"seat:{seat['seat_id']}", "self"}:
                    event = self.append_event(
                        session_id,
                        actor,
                        "private_message",
                        "seat_private",
                        f"seat:{seat['seat_id']}",
                        {"text": text},
                        [seat["seat_id"]],
                    )
                else:
                    raise MafiaGameError("private channel is not available to this seat", 403)
            elif event_type == "vote":
                target = self.resolve_target(state, str(event_body.get("target") or ""))
                if not target.get("alive", True):
                    raise MafiaGameError("vote target must be alive")
                event = self.append_event(
                    session_id,
                    actor,
                    "vote",
                    "public",
                    "public",
                    {"target": target["seat_id"], "target_name": target["name"]},
                )
            elif event_type == "night_action":
                action = str(event_body.get("action") or "").strip()
                target = self.resolve_target(state, str(event_body.get("target") or ""))
                if action not in ROLE_ACTIONS.get(seat["role"], set()):
                    raise MafiaGameError("night action is not available to this role", 403)
                event = self.append_event(
                    session_id,
                    actor,
                    "night_action",
                    "seat_private",
                    "night",
                    {"action": action, "target": target["seat_id"], "target_name": target["name"]},
                    [seat["seat_id"]],
                )
            else:
                raise MafiaGameError("unsupported player event_type")
            return {"accepted": True, "event": event}

    def submit_gm_event(self, session_id: str, bearer: str, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            identity = self.authenticate(session_id, bearer)
            if identity["kind"] != "gm":
                raise MafiaGameError("GM token required", 403)
            state = self.load_state(session_id)
            event_type = str(body.get("event_type") or "")
            actor = {"kind": "gm"}

            if event_type == "phase_change":
                phase = str(body.get("phase") or body.get("payload", {}).get("phase") or "")
                if phase not in VALID_PHASES:
                    raise MafiaGameError("invalid phase")
                if state.get("phase") == "setup" and phase != "setup" and not self.all_attended(state):
                    raise MafiaGameError("all players must attend before the game starts", 409)
                state["phase"] = phase
                if "day" in body:
                    state["day"] = int(body["day"])
                duration_seconds = body.get("duration_seconds")
                self.start_phase_timer(state, int(duration_seconds) if duration_seconds is not None else None)
                self.save_state(session_id, state)
                event = self.append_event(
                    session_id,
                    actor,
                    "phase_change",
                    "public",
                    "public",
                    {
                        "phase": state["phase"],
                        "day": state["day"],
                        "phase_ends_at": state.get("phase_ends_at"),
                        "duration_seconds": state.get("phase_duration_seconds"),
                    },
                )
            elif event_type == "public_announcement":
                text = str(body.get("text") or "").strip()
                if not text:
                    raise MafiaGameError("text is required")
                event = self.append_event(session_id, actor, "public_announcement", "public", "public", {"text": text})
            elif event_type == "private_notice":
                target = self.resolve_target(state, str(body.get("target") or ""))
                text = str(body.get("text") or "").strip()
                if not text:
                    raise MafiaGameError("text is required")
                event = self.append_event(session_id, actor, "private_notice", "seat_private", f"seat:{target['seat_id']}", {"text": text}, [target["seat_id"]])
            elif event_type == "eliminate":
                target = self.resolve_target(state, str(body.get("target") or ""))
                reveal = bool(body.get("reveal_role", True))
                target["alive"] = False
                if reveal:
                    target["revealed_role"] = target["role"]
                self.save_state(session_id, state)
                event = self.append_event(
                    session_id,
                    actor,
                    "eliminate",
                    "public",
                    "public",
                    {"target": target["seat_id"], "target_name": target["name"], "revealed_role": target.get("revealed_role")},
                )
            elif event_type == "game_over":
                winner = str(body.get("winner") or "").strip()
                if not winner:
                    raise MafiaGameError("winner is required")
                state["phase"] = "game_over"
                state["winner"] = winner
                self.save_state(session_id, state)
                event = self.append_event(session_id, actor, "game_over", "public", "public", {"winner": winner})
            elif event_type == "gm_note":
                text = str(body.get("text") or "").strip()
                if not text:
                    raise MafiaGameError("text is required")
                event = self.append_event(session_id, actor, "gm_note", "gm_only", "gm", {"text": text})
            else:
                raise MafiaGameError("unsupported GM event_type")
            return {"accepted": True, "event": event}

    def watch(
        self,
        session_id: str,
        bearer: str,
        scope: str,
        after: int,
        timeout_seconds: float,
        seat_id: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if scope == "gm":
                projection = self.gm_projection(session_id, bearer)
            elif scope == "user":
                projection = self.player_projection(session_id, bearer, "seat-01")
            elif scope == "seat":
                projection = self.player_projection(session_id, bearer, seat_id)
            else:
                raise MafiaGameError("invalid watch scope")
            events = [event for event in projection["events"] if int(event["event_number"]) > after]
            if events or time.monotonic() >= deadline:
                return {
                    "events": events,
                    "last_event_number": projection["last_event_number"],
                    "server_time": utc_timestamp(),
                }
            time.sleep(0.25)


WEB_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>마피아</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050607;
      --surface: rgba(10, 13, 14, 0.92);
      --surface-2: rgba(16, 20, 22, 0.95);
      --surface-3: #151b1d;
      --ink: #f4efe4;
      --muted: #9f988d;
      --dim: #69635b;
      --line: rgba(196, 169, 113, 0.24);
      --line-cool: rgba(86, 213, 230, 0.34);
      --cyan: #65dff0;
      --cyan-soft: rgba(101, 223, 240, 0.12);
      --red: #ef5d55;
      --red-soft: rgba(239, 93, 85, 0.13);
      --gold: #d6a743;
      --gold-soft: rgba(214, 167, 67, 0.15);
      --green: #81d86b;
      --shadow: 0 22px 60px rgba(0, 0, 0, 0.52);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 50% 38%, rgba(130, 91, 39, 0.25), transparent 34%),
        radial-gradient(circle at 75% 8%, rgba(78, 206, 226, 0.11), transparent 26%),
        linear-gradient(140deg, #040506 0%, #090a0a 42%, #050606 100%);
      color: var(--ink);
      overflow-x: hidden;
    }
    button, input, textarea, select { font: inherit; }
    button { color: inherit; }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 10px;
      padding: 10px;
    }
    .topbar {
      display: grid;
      grid-template-columns: minmax(200px, 0.85fr) repeat(3, minmax(140px, 0.6fr)) minmax(220px, 0.75fr);
      gap: 10px;
      align-items: stretch;
    }
    .brand, .status-card, .role-summary, .lang-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: rgba(6, 8, 9, 0.84);
      box-shadow: var(--shadow);
    }
    .brand {
      display: grid;
      align-content: center;
      gap: 2px;
      min-height: 96px;
      padding: 18px 22px;
    }
    h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(40px, 4.4vw, 66px);
      line-height: 0.9;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    .brand-sub { color: var(--muted); font-size: 15px; font-weight: 760; }
    .status-card, .role-summary, .lang-card {
      display: grid;
      align-content: center;
      gap: 8px;
      padding: 14px 18px;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 850;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .status-value {
      min-width: 0;
      color: var(--ink);
      font-size: 28px;
      font-weight: 850;
      line-height: 1.05;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .status-value.cyan { color: var(--cyan); }
    .status-value.gold { color: var(--gold); }
    .role-summary { border-color: rgba(101, 223, 240, 0.38); }
    .role-line {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }
    .role-name {
      color: var(--cyan);
      font-family: Georgia, "Times New Roman", serif;
      font-size: 34px;
      line-height: 1;
      overflow-wrap: anywhere;
    }
    .role-help { color: var(--muted); font-size: 13px; line-height: 1.35; }
    .lang-card { grid-template-columns: 1fr 1fr; gap: 8px; }
    .lang-button {
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #0d1112;
      color: var(--muted);
      cursor: pointer;
      font-weight: 800;
    }
    .lang-button.active { border-color: var(--cyan); color: var(--cyan); background: var(--cyan-soft); }
    .game-shell {
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(250px, 310px) minmax(520px, 1fr) minmax(340px, 420px);
      gap: 10px;
    }
    .panel {
      min-width: 0;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel-title {
      min-height: 48px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 16px;
      border-bottom: 1px solid rgba(196, 169, 113, 0.18);
      color: var(--ink);
      font-size: 15px;
      font-weight: 850;
    }
    .panel-title .count { color: var(--muted); font-size: 13px; }
    .players-panel { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; }
    #players { min-height: 0; padding: 10px; overflow: auto; }
    .seat-row {
      width: 100%;
      min-height: 68px;
      display: grid;
      grid-template-columns: 38px 48px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 7px;
      padding: 8px;
      border: 1px solid rgba(101, 223, 240, 0.16);
      border-radius: var(--radius);
      background: rgba(9, 13, 14, 0.82);
      text-align: left;
      cursor: pointer;
    }
    .seat-row:hover, .seat-row.selected { border-color: var(--cyan); background: var(--cyan-soft); }
    .seat-row.me { box-shadow: inset 0 0 0 1px rgba(101, 223, 240, 0.2); }
    .seat-row.dead { opacity: 0.58; }
    .seat-index {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--cyan);
      font-weight: 900;
    }
    .portrait {
      width: 46px;
      height: 46px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(214, 167, 67, 0.35);
      border-radius: 50%;
      background: radial-gradient(circle at 50% 32%, #30302b, #070808 68%);
      color: var(--gold);
      font-weight: 900;
    }
    .seat-row.selected .portrait { border-color: var(--cyan); color: var(--cyan); }
    .seat-main { min-width: 0; display: grid; gap: 3px; }
    .seat-name { overflow: hidden; color: var(--ink); font-size: 15px; font-weight: 820; text-overflow: ellipsis; white-space: nowrap; }
    .seat-state { color: var(--green); font-size: 12px; font-weight: 760; }
    .dead .seat-state { color: var(--red); }
    .seat-meta { color: var(--gold); font-size: 12px; white-space: nowrap; }
    .legend { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px 14px; border-top: 1px solid rgba(196, 169, 113, 0.18); color: var(--muted); font-size: 12px; }
    .board-panel { display: grid; grid-template-rows: minmax(380px, 1fr) auto; background: rgba(5, 6, 6, 0.76); }
    .table-stage {
      position: relative;
      min-height: 0;
      overflow: hidden;
      background:
        radial-gradient(circle at 50% 48%, rgba(214, 167, 67, 0.14), transparent 28%),
        radial-gradient(ellipse at center, rgba(20, 15, 10, 0.72), rgba(5, 6, 6, 0.94) 69%);
    }
    .table-stage::before {
      content: "";
      position: absolute;
      inset: 9% 10%;
      border: 1px solid rgba(214, 167, 67, 0.34);
      border-radius: 50%;
      background:
        radial-gradient(circle at 50% 50%, rgba(214, 167, 67, 0.10), transparent 42%),
        repeating-radial-gradient(circle at 50% 50%, rgba(255,255,255,0.035), rgba(255,255,255,0.035) 1px, transparent 2px, transparent 18px);
      box-shadow: inset 0 0 70px rgba(0,0,0,0.8), 0 28px 70px rgba(0,0,0,0.45);
    }
    .table-token {
      position: absolute;
      left: var(--x);
      top: var(--y);
      transform: translate(-50%, -50%);
      width: 86px;
      min-height: 108px;
      display: grid;
      justify-items: center;
      gap: 6px;
      border: 0;
      background: transparent;
      cursor: pointer;
    }
    .token-face {
      width: 68px;
      height: 68px;
      display: grid;
      place-items: center;
      border: 2px solid var(--cyan);
      border-radius: 50%;
      background: radial-gradient(circle at 50% 32%, #2f342e, #080909 70%);
      color: var(--ink);
      font-size: 22px;
      font-weight: 900;
      box-shadow: 0 0 18px rgba(101, 223, 240, 0.22);
    }
    .table-token.selected .token-face { border-color: var(--gold); box-shadow: 0 0 28px rgba(214, 167, 67, 0.46); }
    .table-token.dead .token-face { border-color: var(--red); color: var(--red); filter: grayscale(0.8); }
    .token-number {
      position: absolute;
      left: 0;
      top: 6px;
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border: 1px solid var(--cyan);
      border-radius: 50%;
      background: #081011;
      color: var(--cyan);
      font-size: 13px;
      font-weight: 900;
    }
    .token-name { max-width: 100%; color: var(--ink); font-size: 12px; font-weight: 840; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .table-token.dead .token-name { color: var(--red); }
    .table-center {
      position: absolute;
      left: 50%;
      top: 49%;
      transform: translate(-50%, -50%);
      width: min(380px, 54%);
      display: grid;
      gap: 10px;
      justify-items: center;
      padding: 22px;
      border: 1px solid rgba(214, 167, 67, 0.5);
      border-radius: var(--radius);
      background: rgba(8, 10, 10, 0.88);
      text-align: center;
    }
    .center-title { font-size: 21px; font-weight: 860; }
    .center-sub { color: var(--gold); font-size: 14px; font-weight: 760; }
    .target-name { color: var(--cyan); font-size: 22px; font-weight: 900; overflow-wrap: anywhere; }
    .board-actions {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 10px;
      padding: 12px;
      border-top: 1px solid rgba(196, 169, 113, 0.18);
      background: rgba(9, 11, 12, 0.96);
    }
    .action-card {
      display: grid;
      gap: 10px;
      padding: 14px;
      border: 1px solid rgba(101, 223, 240, 0.24);
      border-radius: var(--radius);
      background: var(--surface-2);
    }
    .action-head { display: flex; justify-content: space-between; gap: 10px; color: var(--ink); font-weight: 860; }
    .action-desc { min-height: 36px; color: var(--muted); font-size: 13px; line-height: 1.35; }
    .action-button {
      min-height: 48px;
      border: 1px solid var(--cyan);
      border-radius: 7px;
      background: var(--cyan-soft);
      color: var(--cyan);
      cursor: pointer;
      font-weight: 900;
    }
    .action-button.vote { border-color: var(--gold); background: var(--gold-soft); color: var(--gold); }
    .action-button.danger { border-color: var(--red); background: var(--red-soft); color: var(--red); }
    .action-button:disabled { border-color: rgba(255,255,255,0.12); background: rgba(255,255,255,0.04); color: var(--dim); cursor: not-allowed; }
    .right-stack { min-height: 0; display: grid; grid-template-rows: minmax(330px, 1fr) minmax(230px, 0.75fr); gap: 10px; }
    .comms { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; }
    .mode-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 10px; border-bottom: 1px solid rgba(196, 169, 113, 0.15); }
    .mode-tab {
      min-height: 38px;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 7px;
      background: #0a0d0e;
      color: var(--muted);
      cursor: pointer;
      font-size: 13px;
      font-weight: 840;
    }
    .mode-tab.active { border-color: var(--cyan); color: var(--cyan); background: var(--cyan-soft); }
    .mode-tab.mafia.active { border-color: var(--red); color: var(--red); background: var(--red-soft); }
    .mode-tab:disabled { opacity: 0.42; cursor: not-allowed; }
    .chat-feed, .case-feed { min-height: 0; padding: 10px; overflow: auto; }
    .message, .case-row, .notice-row {
      display: grid;
      grid-template-columns: 38px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      margin-bottom: 8px;
      padding: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: var(--radius);
      background: rgba(13, 17, 18, 0.86);
    }
    .message.mafia { border-color: rgba(239, 93, 85, 0.34); background: rgba(30, 8, 8, 0.42); }
    .message.system, .case-row.system { border-color: rgba(214, 167, 67, 0.24); }
    .message-icon, .case-icon {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(101, 223, 240, 0.28);
      border-radius: 50%;
      color: var(--cyan);
      font-weight: 900;
    }
    .message.mafia .message-icon { border-color: rgba(239, 93, 85, 0.5); color: var(--red); }
    .message-head { display: flex; gap: 8px; align-items: baseline; margin-bottom: 3px; min-width: 0; }
    .actor { color: var(--cyan); font-size: 14px; font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .message.mafia .actor { color: var(--red); }
    .kind, .time { color: var(--muted); font-size: 12px; white-space: nowrap; }
    .message-text, .case-text { color: var(--ink); font-size: 14px; line-height: 1.42; overflow-wrap: anywhere; }
    .chat-form { display: grid; grid-template-columns: minmax(0, 1fr) 52px; gap: 8px; padding: 10px; border-top: 1px solid rgba(196, 169, 113, 0.16); }
    .chat-input {
      width: 100%;
      min-height: 48px;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 7px;
      background: #090b0c;
      color: var(--ink);
      padding: 0 14px;
    }
    .chat-input::placeholder { color: #6f6960; }
    .chat-send {
      min-height: 48px;
      border: 1px solid var(--cyan);
      border-radius: 7px;
      background: var(--cyan-soft);
      color: var(--cyan);
      cursor: pointer;
      font-size: 22px;
      font-weight: 900;
    }
    .chat-send.mafia { border-color: var(--red); background: var(--red-soft); color: var(--red); }
    .log-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); }
    .empty {
      min-height: 120px;
      display: grid;
      place-items: center;
      border: 1px dashed rgba(255,255,255,0.14);
      border-radius: var(--radius);
      color: var(--muted);
      text-align: center;
      padding: 16px;
    }
    .error { min-height: 20px; padding: 0 12px 10px; color: var(--red); font-size: 13px; font-weight: 780; }
    @media (max-width: 1240px) {
      .topbar { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .brand { grid-column: 1 / -1; }
      .lang-card { grid-column: span 3; }
      .game-shell { grid-template-columns: minmax(250px, 320px) minmax(0, 1fr); }
      .right-stack { grid-column: 1 / -1; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-rows: minmax(360px, 1fr); }
    }
    @media (max-width: 820px) {
      .app { display: block; padding: 8px; }
      .topbar, .game-shell, .right-stack, .board-actions { display: grid; grid-template-columns: 1fr; }
      .topbar, .game-shell, .right-stack { margin-bottom: 10px; }
      .brand, .status-card, .role-summary, .lang-card, .panel { margin-bottom: 10px; }
      .lang-card { grid-column: auto; }
      .panel, .players-panel, .right-stack, .comms, .log-panel { min-height: auto; }
      #players, .chat-feed, .case-feed { max-height: none; overflow: visible; }
      .table-stage { min-height: 540px; }
      .table-center { width: min(330px, 72%); padding: 16px; }
      .table-token { width: 74px; }
      .token-face { width: 56px; height: 56px; }
      .message, .case-row, .notice-row { grid-template-columns: 34px minmax(0, 1fr); }
      .time { grid-column: 2; }
    }
    html, body {
      width: 100%;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }
    body {
      height: 100dvh;
      min-height: 0;
      overflow: hidden;
    }
    .app {
      height: 100dvh;
      min-height: 0;
      grid-template-rows: 72px minmax(0, 1fr);
      gap: 8px;
      padding: 8px;
      overflow: hidden;
    }
    .topbar {
      min-height: 0;
      grid-template-columns: minmax(150px, 0.85fr) minmax(160px, 0.9fr) minmax(126px, 0.55fr) minmax(150px, 0.65fr) minmax(150px, 0.65fr);
      gap: 8px;
      overflow: hidden;
    }
    .brand, .status-card, .role-summary, .lang-card {
      min-height: 0;
      padding: 8px 12px;
      box-shadow: 0 12px 34px rgba(0, 0, 0, 0.38);
    }
    h1 { font-size: clamp(28px, 3vw, 42px); }
    .brand-sub, .role-help { font-size: 12px; line-height: 1.22; }
    .label { font-size: 11px; }
    .status-value { font-size: 20px; }
    .role-name { font-size: 24px; }
    .lang-button { min-height: 0; }
    .game-shell {
      height: 100%;
      min-height: 0;
      grid-template-columns: minmax(210px, 250px) minmax(430px, 1fr) minmax(320px, 380px);
      gap: 8px;
      overflow: hidden;
    }
    .panel-title { min-height: 38px; padding: 0 12px; }
    #players, .chat-feed, .case-feed {
      min-height: 0;
      overflow: auto;
      scrollbar-width: thin;
    }
    .seat-row {
      min-height: 52px;
      grid-template-columns: 28px 36px minmax(0, 1fr) auto;
      gap: 8px;
      margin-bottom: 6px;
      padding: 6px;
    }
    .seat-index { width: 28px; height: 28px; font-size: 12px; }
    .portrait { width: 36px; height: 36px; }
    .seat-name { font-size: 13px; }
    .seat-state, .seat-meta { font-size: 11px; }
    .legend { padding: 8px 10px; gap: 8px; }
    .board-panel { grid-template-rows: minmax(0, 1fr) 128px; }
    .table-center { width: min(310px, 50%); gap: 6px; padding: 14px; }
    .center-title { font-size: 17px; }
    .center-sub, .action-desc { font-size: 12px; line-height: 1.25; }
    .target-name { font-size: 18px; }
    .table-token { width: 72px; min-height: 88px; gap: 4px; }
    .token-face { width: 52px; height: 52px; font-size: 18px; }
    .token-number { width: 23px; height: 23px; font-size: 11px; }
    .token-name { font-size: 11px; }
    .board-actions { gap: 8px; padding: 8px; }
    .action-card { gap: 6px; padding: 9px; }
    .action-desc { min-height: 30px; }
    .action-button { min-height: 36px; }
    .right-stack {
      min-height: 0;
      grid-template-rows: minmax(0, 1fr) minmax(146px, 0.42fr);
      gap: 8px;
      overflow: hidden;
    }
    .mode-tabs { gap: 6px; padding: 8px; }
    .mode-tab { min-height: 32px; font-size: 12px; }
    .chat-feed, .case-feed { padding: 8px; }
    .message, .case-row, .notice-row {
      grid-template-columns: 30px minmax(0, 1fr) auto;
      gap: 8px;
      margin-bottom: 6px;
      padding: 8px;
    }
    .message-icon, .case-icon { width: 30px; height: 30px; }
    .message-text, .case-text { font-size: 13px; line-height: 1.34; }
    .chat-form {
      grid-template-columns: minmax(0, 1fr) 44px;
      gap: 6px;
      padding: 8px;
    }
    .chat-input, .chat-send { min-height: 38px; }
    .error { min-height: 16px; padding: 0 10px 8px; }
    .empty { min-height: 80px; }
    @media (max-width: 1240px) {
      .app { display: grid; grid-template-rows: 68px minmax(0, 1fr); }
      .topbar {
        grid-template-columns: minmax(130px, 0.8fr) minmax(150px, 0.9fr) minmax(112px, 0.55fr) minmax(130px, 0.62fr) minmax(128px, 0.58fr);
      }
      .brand, .lang-card { grid-column: auto; }
      .game-shell { grid-template-columns: minmax(190px, 230px) minmax(0, 1fr) minmax(300px, 340px); }
      .right-stack { grid-column: auto; grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) minmax(130px, 0.38fr); }
    }
    @media (max-width: 820px) {
      .app {
        display: grid;
        grid-template-rows: 62px minmax(0, 1fr);
        padding: 6px;
        gap: 6px;
      }
      .topbar {
        grid-template-columns: repeat(5, minmax(124px, 1fr));
        gap: 6px;
        overflow-x: auto;
        overflow-y: hidden;
      }
      .brand, .status-card, .role-summary, .lang-card, .panel {
        margin-bottom: 0;
        padding: 6px 8px;
      }
      h1 { font-size: 24px; }
      .brand-sub, .role-help { display: none; }
      .status-value { font-size: 17px; }
      .role-name { font-size: 20px; }
      .lang-card { grid-column: auto; grid-template-columns: 1fr 1fr; }
      .game-shell {
        grid-template-columns: 1fr;
        grid-template-rows: 116px minmax(0, 1fr) 210px;
        gap: 6px;
      }
      .players-panel, .right-stack, .comms, .log-panel { min-height: 0; }
      .players-panel { grid-template-rows: 34px minmax(0, 1fr); }
      .legend { display: none; }
      #players {
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: minmax(140px, 1fr);
        gap: 6px;
        padding: 6px;
        overflow-x: auto;
        overflow-y: hidden;
      }
      .seat-row {
        min-height: 64px;
        margin-bottom: 0;
        grid-template-columns: 26px minmax(0, 1fr);
      }
      .portrait, .seat-meta { display: none; }
      .board-panel { grid-template-rows: minmax(0, 1fr) 100px; }
      .table-stage { min-height: 0; }
      .table-center { width: min(250px, 58%); padding: 10px; }
      .table-token { width: 56px; min-height: 68px; }
      .token-face { width: 40px; height: 40px; }
      .token-name { max-width: 54px; }
      .board-actions { grid-template-columns: 1fr 1fr; padding: 6px; }
      .action-card { padding: 7px; }
      .action-desc { display: none; }
      .action-button { min-height: 34px; }
      .right-stack {
        grid-template-columns: 1fr 0.75fr;
        grid-template-rows: minmax(0, 1fr);
        gap: 6px;
        margin-bottom: 0;
      }
      #players, .chat-feed, .case-feed {
        max-height: none;
        overflow: auto;
      }
      .message, .case-row, .notice-row { grid-template-columns: 28px minmax(0, 1fr); }
      .time { display: none; }
      .case-feed { padding: 6px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <section class="brand">
        <h1 data-i18n="app_title">MAFIA</h1>
        <div class="brand-sub" data-i18n="subtitle">8인 게임</div>
      </section>
      <section class="role-summary">
        <div class="role-line">
          <div class="label" data-i18n="my_role">내 역할</div>
          <div class="label" id="seatName">—</div>
        </div>
        <div class="role-name" id="role">—</div>
        <div class="role-help" id="roleHelp" data-i18n="waiting_projection">서버 상태를 기다리는 중입니다.</div>
      </section>
      <section class="status-card">
        <div class="label" data-i18n="current_phase">현재 상황</div>
        <div class="status-value gold" id="phase">—</div>
      </section>
      <section class="status-card">
        <div class="label" data-i18n="survivors">생존자</div>
        <div class="status-value cyan" id="alive">—</div>
      </section>
      <section class="lang-card" aria-label="Language">
        <button class="lang-button" type="button" data-lang="ko">한국어</button>
        <button class="lang-button" type="button" data-lang="en">English</button>
      </section>
    </header>

    <main class="game-shell">
      <aside class="panel players-panel">
        <div class="panel-title"><span data-i18n="players">플레이어</span><span class="count" id="tableCount">—</span></div>
        <div id="players"></div>
        <div class="legend">
          <span data-i18n="legend_me">나</span>
          <span data-i18n="legend_selected">선택됨</span>
          <span data-i18n="legend_dead">사망</span>
        </div>
      </aside>

      <section class="panel board-panel">
        <div class="table-stage" id="tableStage">
          <div id="boardSeats"></div>
          <div class="table-center">
            <div class="label" data-i18n="vote_target">투표 대상</div>
            <div class="target-name" id="selectedTarget">—</div>
            <div class="center-title" data-i18n="select_target">대상을 선택하세요</div>
            <div class="center-sub" id="voteHint" data-i18n="latest_vote_counts">가장 최근 투표가 집계됩니다.</div>
          </div>
        </div>
        <div class="board-actions">
          <section class="action-card">
            <div class="action-head"><span data-i18n="vote_action">투표</span><span id="voteSummary">—</span></div>
            <div class="action-desc" id="voteDesc" data-i18n="vote_desc">명단이나 테이블에서 생존자를 선택한 뒤 투표를 확정하세요.</div>
            <button class="action-button vote" id="voteButton" type="button" data-i18n="confirm_vote">투표 확정</button>
          </section>
          <section class="action-card">
            <div class="action-head"><span data-i18n="role_action">역할 행동</span><span id="nightActionLabel">—</span></div>
            <div class="action-desc" id="nightDesc" data-i18n="role_action_desc">역할에 따라 가능한 행동만 서버가 허용합니다.</div>
            <button class="action-button danger" id="nightActionButton" type="button" data-i18n="submit_role_action">역할 행동 실행</button>
          </section>
        </div>
      </section>

      <aside class="right-stack">
        <section class="panel comms">
          <div class="panel-title"><span data-i18n="conversation">대화</span><span class="count" id="channelStatus">—</span></div>
          <div class="mode-tabs">
            <button class="mode-tab active" type="button" data-channel="public" data-i18n="public_chat">공개 채팅</button>
            <button class="mode-tab mafia" type="button" data-channel="mafia" data-i18n="mafia_chat">마피아 채팅</button>
            <button class="mode-tab" type="button" data-channel="self" data-i18n="private_note">비공개 메모</button>
          </div>
          <div class="error" id="error"></div>
          <div class="chat-feed" id="chatFeed"></div>
          <form class="chat-form" id="chatForm">
            <input class="chat-input" id="chatInput" autocomplete="off" data-i18n-placeholder="message_placeholder" placeholder="메시지를 입력하세요...">
            <button class="chat-send" id="chatSend" type="submit" aria-label="Send">➤</button>
          </form>
        </section>

        <section class="panel log-panel">
          <div class="panel-title"><span data-i18n="case_log">사건 로그</span><span class="count" id="connection">—</span></div>
          <div class="case-feed" id="caseFeed"></div>
        </section>
      </aside>
    </main>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const session = params.get("session") || "";
    const token = params.get("token") || "";
    const headers = () => token ? { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
    const seatCoords = [[50, 10], [72, 18], [88, 40], [80, 68], [58, 82], [36, 80], [16, 60], [22, 28]];
    let locale = resolveLocale();
    let lastState = null;
    let selectedTarget = null;
    let chatChannel = "public";

    const I18N = {
      en: {
        app_title: "MAFIA",
        subtitle: "8-player game",
        my_role: "My Role",
        waiting_projection: "Waiting for the server projection.",
        current_phase: "Current Phase",
        survivors: "Timed Free Chat",
        players: "Players",
        legend_me: "You",
        legend_selected: "Selected",
        legend_dead: "Dead",
        vote_target: "Vote Target",
        select_target: "Select a target",
        latest_vote_counts: "The latest vote from each player is counted.",
        vote_action: "Vote",
        vote_desc: "Select a living player from the table, then confirm your vote.",
        confirm_vote: "Confirm Vote",
        role_action: "Role Action",
        role_action_desc: "The server only accepts actions available to your role.",
        submit_role_action: "Submit Role Action",
        conversation: "Conversation",
        public_chat: "Public Chat",
        mafia_chat: "Mafia Chat",
        private_note: "Private Note",
        case_log: "Case Log",
        message_placeholder: "Type your message...",
        no_public_messages: "No public messages yet.",
        no_mafia_messages: "No mafia messages visible.",
        no_private_messages: "No private notes yet.",
        no_case_log: "No visible events yet.",
        missing_session: "Missing session.",
        request_failed: "request failed",
        send_failed: "send failed",
        select_living_target: "Select a living player first.",
        channel_unavailable: "This channel is not available to your role.",
        vote_sent: "Vote submitted.",
        action_sent: "Role action submitted.",
        connected: "Connected",
        disconnected: "Disconnected",
        alive_state: "Alive",
        eliminated_state: "Eliminated",
        you: "You",
        vote_count: "Votes {counts}",
        no_vote_count: "No votes",
        attendance_count: "{attended}/{required} joined",
        action_none: "None",
        action_kill: "Kill",
        action_investigate: "Investigate",
        action_protect: "Protect",
        role_mafia: "Mafia",
        role_detective: "Detective",
        role_doctor: "Doctor",
        role_citizen: "Citizen",
        phase_setup: "Setup",
        phase_day: "Day {day}",
        phase_night: "Night {day}",
        phase_game_over: "Game Over",
        ability_mafia: "Coordinate privately and choose one target at night.",
        ability_detective: "Investigate one player at night. Results arrive privately.",
        ability_doctor: "Protect one player at night.",
        ability_citizen: "No night action. Read, argue, and vote.",
        event_session_created: "Session Created",
        event_public_message: "Public Message",
        event_player_attended: "Joined",
        event_private_message: "Private Message",
        event_vote: "Vote",
        event_phase_change: "Phase Change",
        event_public_announcement: "Announcement",
        event_eliminate: "Elimination",
        event_game_over: "Game Over",
        event_night_action: "Night Action",
        actor_server: "Server",
        actor_gm: "GM",
        vote_text: "{actor} voted for {target}.",
        eliminate_text: "{target} was eliminated{role}.",
        eliminate_role: " as {role}",
        phase_text: "Phase changed to {phase}.",
        game_over_text: "Game over: {winner}",
        session_created_text: "Lobby open. The game starts after everyone joins.",
        player_attended_text: "{actor} joined. ({attended}/{required})"
      },
      ko: {
        app_title: "MAFIA",
        subtitle: "8인 게임",
        my_role: "내 역할",
        waiting_projection: "서버 상태를 기다리는 중입니다.",
        current_phase: "현재 상황",
        survivors: "시간제 자유토론",
        players: "플레이어",
        legend_me: "나",
        legend_selected: "선택됨",
        legend_dead: "사망",
        vote_target: "투표 대상",
        select_target: "대상을 선택하세요",
        latest_vote_counts: "각 플레이어의 가장 최근 투표가 집계됩니다.",
        vote_action: "투표",
        vote_desc: "명단이나 테이블에서 생존자를 선택한 뒤 투표를 확정하세요.",
        confirm_vote: "투표 확정",
        role_action: "역할 행동",
        role_action_desc: "역할에 따라 가능한 행동만 서버가 허용합니다.",
        submit_role_action: "역할 행동 실행",
        conversation: "대화",
        public_chat: "공개 채팅",
        mafia_chat: "마피아 채팅",
        private_note: "비공개 메모",
        case_log: "사건 로그",
        message_placeholder: "메시지를 입력하세요...",
        no_public_messages: "아직 공개 메시지가 없습니다.",
        no_mafia_messages: "표시할 마피아 메시지가 없습니다.",
        no_private_messages: "아직 비공개 메모가 없습니다.",
        no_case_log: "아직 표시할 사건이 없습니다.",
        missing_session: "세션이 없습니다.",
        request_failed: "요청 실패",
        send_failed: "전송 실패",
        select_living_target: "먼저 생존 플레이어를 선택하세요.",
        channel_unavailable: "이 채널은 현재 역할에서 사용할 수 없습니다.",
        vote_sent: "투표를 제출했습니다.",
        action_sent: "역할 행동을 제출했습니다.",
        connected: "연결됨",
        disconnected: "끊김",
        alive_state: "생존",
        eliminated_state: "탈락",
        you: "나",
        vote_count: "투표 {counts}",
        no_vote_count: "투표 없음",
        attendance_count: "{attended}/{required} 입장",
        action_none: "없음",
        action_kill: "제거",
        action_investigate: "조사",
        action_protect: "보호",
        role_mafia: "마피아",
        role_detective: "탐정",
        role_doctor: "의사",
        role_citizen: "시민",
        phase_setup: "준비",
        phase_day: "낮 {day}",
        phase_night: "밤 {day}",
        phase_game_over: "게임 종료",
        ability_mafia: "마피아 전용 채팅으로 협의하고 밤에 제거 대상을 선택합니다.",
        ability_detective: "밤에 플레이어 한 명을 조사합니다. 결과는 비공개로 도착합니다.",
        ability_doctor: "밤에 플레이어 한 명을 보호합니다.",
        ability_citizen: "밤 행동은 없습니다. 읽고, 압박하고, 투표하세요.",
        event_session_created: "세션 생성",
        event_public_message: "공개 발언",
        event_player_attended: "입장",
        event_private_message: "비공개 메시지",
        event_vote: "투표",
        event_phase_change: "단계 변경",
        event_public_announcement: "공지",
        event_eliminate: "탈락",
        event_game_over: "게임 종료",
        event_night_action: "밤 행동",
        actor_server: "서버",
        actor_gm: "GM",
        vote_text: "{actor} 님이 {target}에게 투표했습니다.",
        eliminate_text: "{target} 님이 탈락했습니다{role}.",
        eliminate_role: " ({role})",
        phase_text: "단계가 {phase}(으)로 변경되었습니다.",
        game_over_text: "게임 종료: {winner}",
        session_created_text: "대기실이 열렸습니다. 모두 입장하면 게임이 시작됩니다.",
        player_attended_text: "{actor} 입장. ({attended}/{required})"
      }
    };

    function resolveLocale() {
      const requested = (params.get("lang") || "").toLowerCase();
      if (requested === "ko" || requested === "en") return requested;
      return (navigator.language || "").toLowerCase().startsWith("ko") ? "ko" : "en";
    }
    function t(key) { return (I18N[locale] && I18N[locale][key]) || I18N.en[key] || key; }
    function template(key, values) { return t(key).replace(/\{(\w+)\}/g, (_, name) => values[name] ?? ""); }
    function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
    function title(value) { return String(value || "").replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase()); }
    function seatNumber(seatId) { const match = String(seatId || "").match(/(\d+)$/); return match ? String(Number(match[1])) : "-"; }
    function displayNameForSeat(seatId) { return ((lastState && lastState.table) || []).find(seat => seat.seat_id === seatId)?.name || seatId || "-"; }
    function initial(value) { return String(value || "?").trim().slice(0, 1) || "?"; }
    function roleLabel(role) { return t(`role_${role}`) || title(role); }
    function actionLabel(action) { return t(`action_${action}`) || title(action); }
    function eventKindLabel(eventType) { return t(`event_${eventType}`) || title(eventType); }
    function phaseLabel(state) {
      if (!state) return "-";
      if (state.phase === "day") return template("phase_day", { day: state.day });
      if (state.phase === "night") return template("phase_night", { day: state.day });
      return t(`phase_${state.phase}`) || title(state.phase);
    }
    function timerLabel(state) {
      if (!state || !state.phase_ends_at) return "--:--";
      const remaining = Math.max(0, Math.floor((Date.parse(state.phase_ends_at) - Date.now()) / 1000));
      const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
      const seconds = String(remaining % 60).padStart(2, "0");
      return `${minutes}:${seconds}`;
    }
    function actorName(event) { return (event.actor || {}).name || t(`actor_${(event.actor || {}).kind}`) || title((event.actor || {}).kind) || t("actor_server"); }
    function eventText(event) {
      const p = event.payload || {};
      if (event.event_type === "session_created") return t("session_created_text");
      if (event.event_type === "player_attended") return template("player_attended_text", { actor: actorName(event), attended: p.attended_count || "?", required: p.required_count || "?" });
      if (p.text) return p.text;
      if (p.message) return p.message;
      if (event.event_type === "vote") return template("vote_text", { actor: actorName(event), target: p.target_name || displayNameForSeat(p.target) });
      if (event.event_type === "eliminate") {
        const role = p.revealed_role ? template("eliminate_role", { role: roleLabel(p.revealed_role) }) : "";
        return template("eliminate_text", { target: p.target_name || displayNameForSeat(p.target), role });
      }
      if (event.event_type === "phase_change") return template("phase_text", { phase: phaseLabel({ phase: p.phase, day: p.day || "" }) });
      if (event.event_type === "game_over") return template("game_over_text", { winner: p.winner });
      if (event.event_type === "night_action") return `${actionLabel(p.action)}: ${p.target_name || displayNameForSeat(p.target)}`;
      return JSON.stringify(p);
    }
    function eventIcon(event) {
      if (event.event_type === "vote") return "!";
      if (event.event_type === "eliminate") return "x";
      if (event.event_type === "phase_change") return "*";
      if (event.event_type === "game_over") return "!";
      if (event.event_type === "player_attended") return "+";
      if ((event.actor || {}).kind === "gm") return "GM";
      if ((event.actor || {}).kind === "server") return "S";
      return initial(actorName(event));
    }
    function applyTranslations() {
      document.documentElement.lang = locale;
      document.title = locale === "ko" ? "마피아" : "Mafia";
      document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.getAttribute("data-i18n")); });
      document.querySelectorAll("[data-i18n-placeholder]").forEach(node => { node.setAttribute("placeholder", t(node.getAttribute("data-i18n-placeholder"))); });
      document.querySelectorAll(".lang-button").forEach(button => button.classList.toggle("active", button.dataset.lang === locale));
    }
    function latestVotes(events) {
      const votes = {};
      for (const event of events || []) {
        if (event.event_type === "vote" && event.actor && event.actor.seat_id) votes[event.actor.seat_id] = event.payload.target;
      }
      return votes;
    }
    function selectedSeat(state) { return (state.table || []).find(seat => seat.seat_id === selectedTarget) || null; }
    function availableNightAction(state) {
      const action = (state.allowed_actions || []).find(value => value.startsWith("night_action:"));
      return action ? action.split(":", 2)[1] : "";
    }
    function chatChannelLabel(channel) {
      if (channel === "mafia") return t("mafia_chat");
      if (channel === "self") return t("private_note");
      return t("public_chat");
    }
    function setError(message) { document.getElementById("error").textContent = message || ""; }
    function selectTarget(seatId) {
      if (!lastState) return;
      const seat = lastState.table.find(item => item.seat_id === seatId);
      if (!seat || !seat.alive) return;
      selectedTarget = seatId;
      render(lastState);
    }
    function renderPlayers(state) {
      const votes = latestVotes(state.events);
      const voteCounts = {};
      Object.values(votes).forEach(target => { voteCounts[target] = (voteCounts[target] || 0) + 1; });
      document.getElementById("players").innerHTML = state.table.map(seat => {
        const mine = seat.seat_id === state.seat_id;
        const selected = seat.seat_id === selectedTarget;
        const votesAgainst = voteCounts[seat.seat_id] || 0;
        const revealed = seat.revealed_role ? ` / ${roleLabel(seat.revealed_role)}` : "";
        const persona = seat.persona_label ? ` · ${seat.persona_label}` : "";
        return `<button class="seat-row ${mine ? "me" : ""} ${selected ? "selected" : ""} ${seat.alive ? "" : "dead"}" type="button" data-seat="${esc(seat.seat_id)}" ${seat.alive ? "" : "disabled"}>
          <span class="seat-index">${esc(seatNumber(seat.seat_id))}</span>
          <span class="portrait">${esc(String(seat.name || "?").slice(0, 1))}</span>
          <span class="seat-main"><span class="seat-name">${esc(seat.name)} ${mine ? `<span class="seat-meta">${esc(t("you"))}</span>` : ""}</span><span class="seat-state">${seat.alive ? t("alive_state") : t("eliminated_state")}${esc(revealed)}${esc(persona)}</span></span>
          <span class="seat-meta">${votesAgainst ? `+${votesAgainst}` : ""}</span>
        </button>`;
      }).join("");
      document.querySelectorAll(".seat-row").forEach(row => row.addEventListener("click", () => selectTarget(row.dataset.seat)));
      document.getElementById("tableCount").textContent = `${state.table.length}`;
      const counts = Object.entries(voteCounts).map(([seat, count]) => `${displayNameForSeat(seat)} ${count}`).join(" · ");
      document.getElementById("voteSummary").textContent = counts ? template("vote_count", { counts }) : t("no_vote_count");
    }
    function renderBoard(state) {
      document.getElementById("boardSeats").innerHTML = state.table.map((seat, index) => {
        const [x, y] = seatCoords[index] || [50, 50];
        return `<button class="table-token ${seat.seat_id === selectedTarget ? "selected" : ""} ${seat.alive ? "" : "dead"}" type="button" data-seat="${esc(seat.seat_id)}" style="--x:${x}%;--y:${y}%;" ${seat.alive ? "" : "disabled"}>
          <span class="token-number">${esc(seatNumber(seat.seat_id))}</span>
          <span class="token-face">${esc(String(seat.name || "?").slice(0, 1))}</span>
          <span class="token-name">${esc(seat.name)}</span>
        </button>`;
      }).join("");
      document.querySelectorAll(".table-token").forEach(tokenButton => tokenButton.addEventListener("click", () => selectTarget(tokenButton.dataset.seat)));
      const target = selectedSeat(state);
      document.getElementById("selectedTarget").textContent = target ? target.name : "-";
      document.getElementById("voteHint").textContent = target && target.persona_label ? target.persona_label : t("latest_vote_counts");
      document.getElementById("voteButton").disabled = !target;
    }
    function renderMessages(state) {
      const events = state.events || [];
      const visible = chatChannel === "public"
        ? events.filter(event => event.visibility === "public" && ["public_message", "public_announcement", "session_created"].includes(event.event_type))
        : chatChannel === "mafia"
          ? events.filter(event => event.visibility === "mafia_private")
          : (state.private_events || []).filter(event => event.visibility === "seat_private");
      const emptyKey = chatChannel === "public" ? "no_public_messages" : chatChannel === "mafia" ? "no_mafia_messages" : "no_private_messages";
      const feed = document.getElementById("chatFeed");
      feed.innerHTML = visible.map(event => `<article class="message ${event.visibility === "mafia_private" ? "mafia" : ""} ${(event.actor || {}).kind === "gm" || (event.actor || {}).kind === "server" ? "system" : ""}">
        <div class="message-icon">${esc(eventIcon(event))}</div>
        <div><div class="message-head"><span class="actor">${esc(actorName(event))}</span><span class="kind">${esc(eventKindLabel(event.event_type))}</span></div><div class="message-text">${esc(eventText(event))}</div></div>
        <time class="time">${esc(String(event.created_at || "").slice(11, 16))}</time>
      </article>`).join("") || `<div class="empty">${esc(t(emptyKey))}</div>`;
      requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
    }
    function renderCaseLog(state) {
      const events = (state.events || []).slice(-12).reverse();
      document.getElementById("caseFeed").innerHTML = events.map(event => `<article class="case-row ${(event.actor || {}).kind === "gm" || (event.actor || {}).kind === "server" ? "system" : ""}">
        <div class="case-icon">${esc(eventIcon(event))}</div>
        <div><div class="message-head"><span class="actor">${esc(eventKindLabel(event.event_type))}</span></div><div class="case-text">${esc(eventText(event))}</div></div>
        <time class="time">${esc(String(event.created_at || "").slice(11, 16))}</time>
      </article>`).join("") || `<div class="empty">${esc(t("no_case_log"))}</div>`;
    }
    function renderChatModes(state) {
      const channels = state.allowed_channels || [];
      const selfChannel = `seat:${state.seat_id}`;
      const allowed = {
        public: channels.includes("public"),
        mafia: channels.includes("mafia"),
        self: channels.includes(selfChannel),
      };
      if (!allowed[chatChannel]) chatChannel = allowed.public ? "public" : allowed.self ? "self" : "public";
      document.querySelectorAll(".mode-tab").forEach(button => {
        const mode = button.dataset.channel;
        button.disabled = !allowed[mode];
        button.classList.toggle("active", mode === chatChannel);
      });
      document.getElementById("channelStatus").textContent = chatChannelLabel(chatChannel);
      document.getElementById("chatSend").classList.toggle("mafia", chatChannel === "mafia");
    }
    function renderActions(state) {
      const target = selectedSeat(state);
      const action = availableNightAction(state);
      document.getElementById("nightActionLabel").textContent = action ? actionLabel(action) : t("action_none");
      document.getElementById("nightActionButton").disabled = !target || !action;
      document.getElementById("nightDesc").textContent = action && target ? `${actionLabel(action)}: ${target.name}` : t("role_action_desc");
    }
    function render(state) {
      lastState = state;
      applyTranslations();
      const alive = state.table.filter(seat => seat.alive).length;
      const currentTarget = selectedSeat(state);
      if (selectedTarget && (!currentTarget || !currentTarget.alive)) selectedTarget = null;
      const role = state.role_view.own_role;
      document.getElementById("seatName").textContent = state.seat_name || state.seat_id;
      document.getElementById("role").textContent = roleLabel(role);
      document.getElementById("roleHelp").textContent = t(`ability_${role}`) || t("waiting_projection");
      document.getElementById("phase").textContent = phaseLabel(state);
      const attendance = state.attendance || {};
      document.getElementById("alive").textContent = state.phase === "setup"
        ? template("attendance_count", { attended: attendance.attended ?? 0, required: attendance.required ?? state.table.length })
        : `${timerLabel(state)} · ${alive} / ${state.table.length}`;
      document.getElementById("connection").textContent = t("connected");
      renderPlayers(state);
      renderBoard(state);
      renderChatModes(state);
      renderMessages(state);
      renderCaseLog(state);
      renderActions(state);
    }
    async function postPlayerEvent(payload, successMessage) {
      const controls = document.querySelectorAll("button, input");
      controls.forEach(control => control.disabled = true);
      try {
        const res = await fetch(`/api/player/event?session=${encodeURIComponent(session)}`, { method: "POST", headers: headers(), credentials: "same-origin", body: JSON.stringify(payload) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || t("send_failed"));
        setError(successMessage || "");
        await poll();
      } catch (err) {
        setError(err.message);
      } finally {
        controls.forEach(control => control.disabled = false);
        if (lastState) render(lastState);
      }
    }
    async function poll() {
      if (!session) {
        setError(t("missing_session"));
        document.getElementById("connection").textContent = t("disconnected");
        return;
      }
      try {
        const res = await fetch(`/api/user/state?session=${encodeURIComponent(session)}`, { headers: headers(), credentials: "same-origin" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || t("request_failed"));
        render(data);
      } catch (err) {
        setError(err.message);
        document.getElementById("connection").textContent = t("disconnected");
      }
    }
    document.querySelectorAll(".lang-button").forEach(button => button.addEventListener("click", () => { locale = button.dataset.lang; applyTranslations(); if (lastState) render(lastState); }));
    document.querySelectorAll(".mode-tab").forEach(button => button.addEventListener("click", () => { if (button.disabled) return; chatChannel = button.dataset.channel; if (lastState) render(lastState); }));
    document.getElementById("chatForm").addEventListener("submit", async event => {
      event.preventDefault();
      if (!lastState) return;
      const input = document.getElementById("chatInput");
      const text = input.value.trim();
      if (!text) return;
      const channels = lastState.allowed_channels || [];
      let payload;
      if (chatChannel === "public") {
        if (!channels.includes("public")) return setError(t("channel_unavailable"));
        payload = { event_type: "public_message", text };
      } else if (chatChannel === "mafia") {
        if (!channels.includes("mafia")) return setError(t("channel_unavailable"));
        payload = { event_type: "private_message", channel: "mafia", text };
      } else {
        const channel = `seat:${lastState.seat_id}`;
        if (!channels.includes(channel)) return setError(t("channel_unavailable"));
        payload = { event_type: "private_message", channel, text };
      }
      input.value = "";
      await postPlayerEvent(payload, "");
      input.focus();
    });
    document.getElementById("voteButton").addEventListener("click", async () => {
      if (!selectedTarget) return setError(t("select_living_target"));
      await postPlayerEvent({ event_type: "vote", target: selectedTarget }, t("vote_sent"));
    });
    document.getElementById("nightActionButton").addEventListener("click", async () => {
      if (!lastState || !selectedTarget) return setError(t("select_living_target"));
      const action = availableNightAction(lastState);
      if (!action) return setError(t("channel_unavailable"));
      await postPlayerEvent({ event_type: "night_action", action, target: selectedTarget }, t("action_sent"));
    });
    applyTranslations();
    poll();
    setInterval(poll, 1200);
  </script>
</body>
</html>
"""


class MafiaHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], store: MafiaGameStore, default_session: str = DEFAULT_SESSION) -> None:
        super().__init__(server_address, MafiaRequestHandler)
        self.store = store
        self.default_session = safe_session_id(default_session)


class MafiaRequestHandler(BaseHTTPRequestHandler):
    server: MafiaHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}", file=sys.stderr)

    def user_cookie_name(self, session_id: str) -> str:
        return f"mafia_user_{safe_session_id(session_id)}"

    def cookie_value(self, name: str) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        for chunk in raw_cookie.split(";"):
            if not chunk.strip() or "=" not in chunk:
                continue
            key, value = chunk.strip().split("=", 1)
            if key == name:
                return urllib.parse.unquote(value)
        return None

    def bearer_token(self, query: dict[str, list[str]], session_id: str | None = None) -> str | None:
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header.split(None, 1)[1]
        query_token = first(query, "token")
        if query_token:
            return query_token
        if session_id:
            return self.cookie_value(self.user_cookie_name(session_id))
        return None

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MafiaGameError("request body must be JSON") from exc
        if not isinstance(payload, dict):
            raise MafiaGameError("request body must be a JSON object")
        return payload

    def send_payload(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html: str, session_id: str | None = None) -> None:
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if session_id:
            self.server.store.record_attendance(session_id, "seat-01")
            cookie = urllib.parse.quote(self.server.store.user_token(session_id), safe="")
            self.send_header("Set-Cookie", f"{self.user_cookie_name(session_id)}={cookie}; Path=/; SameSite=Lax; HttpOnly")
        self.end_headers()
        self.wfile.write(data)

    def redirect_to_play(self, session_id: str, query: dict[str, list[str]]) -> None:
        lang = first(query, "lang")
        params = {"session": session_id}
        if lang:
            params["lang"] = lang
        location = f"/play?{urllib.parse.urlencode(params)}"
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_error(self, exc: Exception) -> None:
        if isinstance(exc, MafiaGameError):
            self.send_payload(exc.status, {"error": str(exc)})
        else:
            self.send_payload(500, {"error": str(exc)})

    def do_OPTIONS(self) -> None:
        self.send_payload(200, {"ok": True})

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"
            if path in {"/", "/play"}:
                session_id = first(query, "session")
                if not session_id:
                    self.redirect_to_play(self.server.default_session, query)
                    return
                self.send_html(WEB_HTML, session_id)
                return
            if path == "/api/health":
                self.send_payload(200, {"ok": True})
                return
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            session_id = required(query, "session")
            bearer = self.bearer_token(query, session_id)
            if path == "/api/gm/state":
                self.send_payload(200, self.server.store.gm_projection(session_id, bearer or ""))
            elif path == "/api/user/state":
                self.send_payload(200, self.server.store.player_projection(session_id, bearer or "", "seat-01"))
            elif path == "/api/seat/state":
                self.send_payload(200, self.server.store.player_projection(session_id, bearer or "", required(query, "seat")))
            elif path == "/api/events/watch":
                timeout_seconds = float(first(query, "timeout") or "20")
                payload = self.server.store.watch(
                    session_id,
                    bearer or "",
                    first(query, "scope") or "user",
                    int(first(query, "after") or "0"),
                    min(timeout_seconds, 60.0),
                    first(query, "seat"),
                )
                self.send_payload(200, payload)
            else:
                raise MafiaGameError("not found", 404)
        except Exception as exc:
            self.handle_error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"
            body = self.read_body()
            if path == "/api/session":
                result = self.server.store.create_session(
                    str(body.get("session_id") or first(query, "session") or DEFAULT_SESSION),
                    str(body.get("user_name") or "You"),
                    body.get("seed"),
                )
                base_url = f"http://{self.headers.get('Host', f'{DEFAULT_HOST}:{DEFAULT_PORT}')}"
                result["user_web_url"] = f"{base_url}/play?session={urllib.parse.quote(result['session_id'])}"
                self.send_payload(201, result)
                return
            session_id = required(query, "session")
            bearer = self.bearer_token(query, session_id)
            if path == "/api/player/event":
                self.send_payload(200, self.server.store.submit_player_event(session_id, bearer or "", body))
            elif path == "/api/gm/event":
                self.send_payload(200, self.server.store.submit_gm_event(session_id, bearer or "", body))
            else:
                raise MafiaGameError("not found", 404)
        except Exception as exc:
            self.handle_error(exc)


def first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def required(query: dict[str, list[str]], key: str) -> str:
    value = first(query, key)
    if not value:
        raise MafiaGameError(f"missing query parameter: {key}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Server-mediated Mafia game runtime")
    parser.add_argument("--serve", action="store_true", help="Run the local Mafia server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Session storage root")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="Default session slug for operator convenience")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.serve:
        raise SystemExit("mafia_server.py requires --serve")
    store = MafiaGameStore(pathlib.Path(args.root))
    httpd = MafiaHTTPServer((args.host, args.port), store, args.session)
    print(f"mafia server: http://{args.host}:{args.port}/play?session={urllib.parse.quote(args.session)}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
