from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.request


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "mafia-game" / "scripts" / "mafia_server.py"

spec = importlib.util.spec_from_file_location("mafia_server", SCRIPT)
mafia_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mafia_server)


def make_store(tmpdir: str):
    return mafia_server.MafiaGameStore(pathlib.Path(tmpdir))


def create_session(store):
    return store.create_session("game", user_name="User", seed="fixed")


def seat_with_role(store, role: str, kind: str | None = "ai") -> dict:
    state = store.load_state("game")
    for seat in state["seats"]:
        if seat["role"] == role and (kind is None or seat["kind"] == kind):
            return seat
    raise AssertionError(f"no AI seat with role {role}")


def token_for(bootstrap: dict, seat_id: str) -> str:
    if seat_id == "seat-01":
        return bootstrap["user_token"]
    for seat in bootstrap["seats"]:
        if seat["seat_id"] == seat_id:
            return seat["token"]
    raise AssertionError(f"no token for {seat_id}")


def attend_all(store, bootstrap: dict) -> None:
    for seat in bootstrap["seats"]:
        store.player_projection("game", token_for(bootstrap, seat["seat_id"]), seat["seat_id"])


def start_day(store, bootstrap: dict) -> None:
    attend_all(store, bootstrap)
    store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "phase_change", "phase": "day"})


class MafiaGameServerTests(unittest.TestCase):
    def test_create_session_has_fixed_8_player_role_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            state = store.load_state("game")

            self.assertEqual(len(state["seats"]), 8)
            self.assertEqual(state["seats"][0]["kind"], "user")
            self.assertEqual([seat["kind"] for seat in state["seats"][1:]], ["ai"] * 7)
            self.assertEqual(sorted(seat["role"] for seat in state["seats"]), sorted(mafia_server.DEFAULT_ROLES))
            self.assertTrue(bootstrap["gm_token"])
            self.assertTrue(bootstrap["user_token"])
            self.assertEqual(len([seat for seat in bootstrap["seats"] if seat.get("token")]), 7)
            self.assertEqual(state["phase"], "setup")
            self.assertEqual(state["timing_mode"], "timed_free_chat")
            self.assertIsNone(state["phase_duration_seconds"])
            self.assertTrue(state["phase_started_at"])
            self.assertIsNone(state["phase_ends_at"])
            self.assertEqual(state["required_attendance_count"], 8)
            self.assertFalse(any(seat["attended"] for seat in state["seats"]))
            self.assertGreaterEqual(len(mafia_server.DEFAULT_PERSONAS), 24)
            personas = [seat["persona"]["label"] for seat in state["seats"]]
            self.assertEqual(len(set(personas)), 8)

    def test_create_session_assigns_unique_public_nicknames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            state = store.load_state("game")
            user_projection = store.player_projection("game", bootstrap["user_token"], "seat-01")

            state_names = [seat["name"] for seat in state["seats"]]
            bootstrap_names = [seat["name"] for seat in bootstrap["seats"]]
            projection_names = [seat["name"] for seat in user_projection["table"]]
            projection_personas = [seat["persona_label"] for seat in user_projection["table"]]

            self.assertEqual(len(state_names), 8)
            self.assertEqual(len({name.lower() for name in state_names}), 8)
            self.assertTrue(all(name.strip() for name in state_names))
            self.assertEqual(bootstrap_names, state_names)
            self.assertEqual(projection_names, state_names)
            self.assertEqual(len({persona.lower() for persona in projection_personas}), 8)
            self.assertEqual(user_projection["attendance"]["attended"], 1)
            self.assertTrue(user_projection["table"][0]["attended"])

    def test_game_start_requires_all_players_to_attend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)

            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "phase_change", "phase": "day"})

            attend_all(store, bootstrap)
            accepted = store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "phase_change", "phase": "day"})
            state = store.load_state("game")

            self.assertTrue(accepted["accepted"])
            self.assertEqual(state["phase"], "day")
            self.assertEqual(state["phase_duration_seconds"], mafia_server.DEFAULT_DAY_SECONDS)
            self.assertEqual(store.attendance_summary(state), {"attended": 8, "required": 8, "ready": True})

    def test_seeded_session_keeps_role_and_nickname_assignment_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
            left = make_store(left_dir)
            right = make_store(right_dir)
            create_session(left)
            create_session(right)
            left_state = left.load_state("game")
            right_state = right.load_state("game")

            self.assertEqual([seat["role"] for seat in left_state["seats"]], [seat["role"] for seat in right_state["seats"]])
            self.assertEqual([seat["name"] for seat in left_state["seats"]], [seat["name"] for seat in right_state["seats"]])
            self.assertEqual([seat["persona"] for seat in left_state["seats"]], [seat["persona"] for seat in right_state["seats"]])

    def test_player_projection_hides_auth_and_other_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            user_projection = store.player_projection("game", bootstrap["user_token"], "seat-01")
            gm_projection = store.gm_projection("game", bootstrap["gm_token"])
            ai_seat = next(seat for seat in bootstrap["seats"] if seat["kind"] == "ai")

            self.assertNotIn("auth", user_projection)
            self.assertIn("auth", gm_projection["state"])
            self.assertIn("own_role", user_projection["role_view"])
            self.assertIn("persona_view", user_projection)
            self.assertEqual(user_projection["persona_view"]["message_max_chars"], mafia_server.AI_MESSAGE_MAX_CHARS)
            self.assertTrue(all("role" not in seat for seat in user_projection["table"]))
            self.assertNotIn("state", user_projection)
            self.assertNotIn("gm_token", str(user_projection))
            self.assertNotIn("user_token", str(user_projection))
            self.assertNotIn("seat_tokens", str(user_projection))
            with self.assertRaises(mafia_server.MafiaGameError):
                store.player_projection("game", token_for(bootstrap, ai_seat["seat_id"]), "seat-01")
            with self.assertRaises(mafia_server.MafiaGameError):
                store.gm_projection("game", bootstrap["user_token"])
            with self.assertRaises(mafia_server.MafiaGameError):
                store.watch("game", token_for(bootstrap, ai_seat["seat_id"]), "seat", after=0, timeout_seconds=0, seat_id="seat-01")
            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", bootstrap["gm_token"], {"event_type": "public_message", "text": "no"})

    def test_mafia_private_message_only_reaches_mafia_and_gm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            state = store.load_state("game")
            mafia_seats = [seat for seat in state["seats"] if seat["role"] == "mafia"]
            citizen = seat_with_role(store, "citizen")
            mafia_token = token_for(bootstrap, mafia_seats[0]["seat_id"])
            citizen_token = token_for(bootstrap, citizen["seat_id"])

            store.submit_player_event("game", mafia_token, {"event_type": "private_message", "channel": "mafia", "text": "meet at night"})

            teammate_projection = store.player_projection("game", token_for(bootstrap, mafia_seats[1]["seat_id"]), mafia_seats[1]["seat_id"])
            citizen_projection = store.player_projection("game", citizen_token, citizen["seat_id"])
            gm_projection = store.gm_projection("game", bootstrap["gm_token"])

            self.assertTrue(any(event["visibility"] == "mafia_private" for event in teammate_projection["events"]))
            self.assertFalse(any(event["visibility"] == "mafia_private" for event in citizen_projection["events"]))
            self.assertTrue(any(event["visibility"] == "mafia_private" for event in gm_projection["events"]))
            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", citizen_token, {"event_type": "private_message", "channel": "mafia", "text": "let me in"})

    def test_raw_input_and_role_limited_night_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            state = store.load_state("game")
            night_actor = next(seat for seat in state["seats"] if seat["kind"] == "ai" and mafia_server.ROLE_ACTIONS[seat["role"]])
            night_action = sorted(mafia_server.ROLE_ACTIONS[night_actor["role"]])[0]
            citizen = seat_with_role(store, "citizen")
            start_day(store, bootstrap)

            vote = store.submit_player_event("game", bootstrap["user_token"], {"event_type": "raw_input", "text": "/vote seat-02"})
            self.assertEqual(vote["event"]["event_type"], "vote")
            self.assertEqual(vote["event"]["visibility"], "public")

            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", token_for(bootstrap, citizen["seat_id"]), {"event_type": "night_action", "action": "investigate", "target": "seat-01"})

            night_event = store.submit_player_event(
                "game",
                token_for(bootstrap, night_actor["seat_id"]),
                {"event_type": "night_action", "action": night_action, "target": "seat-01"},
            )
            self.assertEqual(night_event["event"]["visibility"], "seat_private")
            user_projection = store.player_projection("game", bootstrap["user_token"], "seat-01")
            self.assertFalse(any(event["event_id"] == night_event["event"]["event_id"] for event in user_projection["events"]))

    def test_structured_public_message_with_command_like_text_is_not_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)

            accepted = store.submit_player_event("game", bootstrap["user_token"], {"event_type": "public_message", "text": "/vote seat-02"})

            self.assertEqual(accepted["event"]["event_type"], "public_message")
            self.assertEqual(accepted["event"]["payload"]["text"], "/vote seat-02")

    def test_ai_messages_are_constrained_to_short_rp_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            ai_seat = next(seat for seat in bootstrap["seats"] if seat["kind"] == "ai")
            long_text = "가" * (mafia_server.AI_MESSAGE_MAX_CHARS + 50)

            accepted = store.submit_player_event("game", token_for(bootstrap, ai_seat["seat_id"]), {"event_type": "public_message", "text": long_text})
            user_accepted = store.submit_player_event("game", bootstrap["user_token"], {"event_type": "public_message", "text": long_text})

            self.assertLessEqual(len(accepted["event"]["payload"]["text"]), mafia_server.AI_MESSAGE_MAX_CHARS)
            self.assertTrue(accepted["event"]["payload"]["text"].endswith("..."))
            self.assertEqual(user_accepted["event"]["payload"]["text"], long_text)

    def test_manipulated_structured_events_are_rejected_server_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            citizen = seat_with_role(store, "citizen")
            citizen_token = token_for(bootstrap, citizen["seat_id"])

            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", citizen_token, {"event_type": "private_message", "channel": "mafia", "text": "let me in"})
            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", citizen_token, {"event_type": "night_action", "action": "investigate", "target": "seat-01"})

            store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "eliminate", "target": citizen["seat_id"]})
            with self.assertRaises(mafia_server.MafiaGameError):
                store.submit_player_event("game", citizen_token, {"event_type": "public_message", "text": "after death"})

    def test_gm_progression_changes_server_state_but_not_player_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)
            attend_all(store, bootstrap)

            store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "phase_change", "phase": "night", "duration_seconds": 45})
            store.submit_gm_event("game", bootstrap["gm_token"], {"event_type": "eliminate", "target": "seat-02"})
            user_projection = store.player_projection("game", bootstrap["user_token"], "seat-01")

            self.assertEqual(user_projection["phase"], "night")
            self.assertEqual(user_projection["timing_mode"], "timed_free_chat")
            self.assertEqual(user_projection["phase_duration_seconds"], 45)
            self.assertLessEqual(user_projection["phase_remaining_seconds"], 45)
            self.assertGreaterEqual(user_projection["phase_remaining_seconds"], 0)
            self.assertFalse(next(seat for seat in user_projection["table"] if seat["seat_id"] == "seat-02")["alive"])
            self.assertNotIn("auth", user_projection)
            self.assertNotIn("/api/gm", mafia_server.WEB_HTML)

    def test_http_user_web_url_uses_cookie_not_query_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            server = mafia_server.MafiaHTTPServer(("127.0.0.1", 0), store, "game")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                request = urllib.request.Request(
                    f"{base}/api/session",
                    data=json.dumps({"session_id": "game", "seed": "fixed"}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request) as response:
                    created = json.loads(response.read().decode("utf-8"))
                self.assertEqual(created["user_web_url"], f"{base}/play?session=game")
                self.assertNotIn("token=", created["user_web_url"])

                with urllib.request.urlopen(created["user_web_url"]) as response:
                    cookie = response.headers["Set-Cookie"]
                self.assertIn("mafia_user_game=", cookie)
                self.assertIn("HttpOnly", cookie)

                request = urllib.request.Request(f"{base}/api/user/state?session=game", headers={"Cookie": cookie})
                with urllib.request.urlopen(request) as response:
                    projection = json.loads(response.read().decode("utf-8"))
                self.assertEqual(projection["seat_id"], "seat-01")
                self.assertNotIn("auth", projection)

                with urllib.request.urlopen(f"{base}/") as response:
                    self.assertEqual(response.geturl(), f"{base}/play?session=game")
                    self.assertIn("mafia_user_game=", response.headers["Set-Cookie"])
            finally:
                server.shutdown()
                server.server_close()

    def test_web_client_is_user_player_surface_not_admin_console(self) -> None:
        html = mafia_server.WEB_HTML

        self.assertIn("투표 확정", html)
        self.assertIn("마피아 채팅", html)
        self.assertIn("비공개 메모", html)
        self.assertIn("시간제 자유토론", html)
        self.assertIn("플레이어", html)
        self.assertIn("/api/user/state", html)
        self.assertIn("/api/player/event", html)
        self.assertIn('credentials: "same-origin"', html)
        self.assertIn("height: 100dvh", html)
        self.assertIn("overflow: hidden", html)
        self.assertIn("phase_ends_at", html)
        self.assertIn("player_attended", html)
        self.assertIn("feed.scrollTop = feed.scrollHeight", html)
        self.assertIn('event_type: "public_message"', html)
        self.assertIn('event_type: "private_message"', html)
        self.assertIn('event_type: "vote"', html)
        self.assertIn('event_type: "night_action"', html)
        self.assertIn("ko:", html)
        self.assertIn("메시지를 입력하세요", html)
        self.assertNotIn("/vote", html)
        self.assertNotIn("/mafia", html)
        self.assertNotIn("/night", html)
        self.assertNotIn("/private", html)
        self.assertNotIn("raw_input", html)
        self.assertNotIn("commandForChannel", html)
        self.assertNotIn('data-template="/', html)
        self.assertNotIn("/api/gm", html)
        self.assertNotIn("GM token", html)
        self.assertNotIn("세션 또는 토큰이 없습니다.", html)

    def test_watch_returns_visible_events_without_turn_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = make_store(tmpdir)
            bootstrap = create_session(store)

            first = store.watch("game", bootstrap["user_token"], "user", after=0, timeout_seconds=0)
            self.assertTrue(first["events"])
            last = first["last_event_number"]
            second = store.watch("game", bootstrap["user_token"], "user", after=last, timeout_seconds=0)
            self.assertEqual(second["events"], [])


if __name__ == "__main__":
    unittest.main()
