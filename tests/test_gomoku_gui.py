from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "gomoku" / "scripts" / "gomoku_gui.py"

spec = importlib.util.spec_from_file_location("gomoku_gui", SCRIPT)
gomoku_gui = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gomoku_gui)


def started_state(**kwargs):
    return gomoku_gui.start_game(gomoku_gui.new_state(**kwargs))


def script_env(state_path: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    env["GOMOKU_STATE_PATH"] = str(state_path)
    return env


class GomokuGuiTests(unittest.TestCase):
    def test_new_state_defaults_to_empty_black_turn(self) -> None:
        state = gomoku_gui.new_state()

        self.assertEqual(state["size"], 15)
        self.assertEqual(state["next_player"], "black")
        self.assertEqual(state["human_player"], "black")
        self.assertEqual(state["codex_player"], "white")
        self.assertFalse(state["renju_rules"])
        self.assertFalse(state["setup_complete"])
        self.assertEqual(state["game_event_id"], 0)
        self.assertNotIn("win_length", state)
        self.assertNotIn("overline_wins", state)
        self.assertEqual(len(state["board"]), 15)
        self.assertTrue(all(cell == gomoku_gui.EMPTY for row in state["board"] for cell in row))

    def test_new_state_can_make_human_white_and_codex_black(self) -> None:
        state = gomoku_gui.new_state(human_player="white")

        self.assertEqual(state["human_player"], "white")
        self.assertEqual(state["codex_player"], "black")
        self.assertEqual(state["next_player"], "black")
        self.assertFalse(state["setup_complete"])

    def test_adjust_settings_changes_visible_game_options(self) -> None:
        state = gomoku_gui.new_state()

        state = gomoku_gui.adjust_settings(state, "toggle-human")
        self.assertEqual(state["human_player"], "white")
        self.assertEqual(state["codex_player"], "black")
        self.assertFalse(state["setup_complete"])

        state = gomoku_gui.adjust_settings(state, "size-up")
        self.assertEqual(state["size"], 16)

        state = gomoku_gui.adjust_settings(state, "toggle-renju")
        self.assertTrue(state["renju_rules"])
        self.assertEqual(state["size"], 15)
        self.assertFalse(state["setup_complete"])

    def test_start_game_marks_setup_complete(self) -> None:
        state = gomoku_gui.new_state(human_player="white")

        state = gomoku_gui.start_game(state)

        self.assertTrue(state["setup_complete"])
        self.assertEqual(state["game_event_id"], 1)
        self.assertEqual(state["next_player"], "black")
        self.assertEqual(state["codex_player"], "black")

    def test_settings_do_not_emit_game_events(self) -> None:
        state = gomoku_gui.new_state()

        state = gomoku_gui.adjust_settings(state, "toggle-human")
        state = gomoku_gui.adjust_settings(state, "toggle-renju")

        self.assertFalse(state["setup_complete"])
        self.assertEqual(state["game_event_id"], 0)

    def test_moves_emit_game_events(self) -> None:
        state = started_state()

        state = gomoku_gui.apply_move(state, 8, 8, "black")

        self.assertEqual(state["game_event_id"], 2)

    def test_adjust_settings_clamps_bounds(self) -> None:
        state = gomoku_gui.new_state(size=gomoku_gui.MAX_BOARD_SIZE)
        self.assertEqual(gomoku_gui.adjust_settings(state, "size-up")["size"], gomoku_gui.MAX_BOARD_SIZE)

        state = gomoku_gui.new_state(size=gomoku_gui.MIN_BOARD_SIZE)
        self.assertEqual(gomoku_gui.adjust_settings(state, "size-down")["size"], gomoku_gui.MIN_BOARD_SIZE)

    def test_unknown_settings_action_is_noop(self) -> None:
        state = gomoku_gui.new_state()

        self.assertIs(gomoku_gui.adjust_settings(state, "unknown"), state)

    def test_settings_screen_hit_testing(self) -> None:
        width = 666
        height = 732
        actions = {action: rect for action, rect, _label in gomoku_gui.settings_screen_buttons(width, height)}
        toggle = actions["toggle-human"]

        self.assertNotIn("win-up", actions)
        self.assertNotIn("win-down", actions)
        self.assertNotIn("toggle-overline", actions)
        self.assertNotIn("back", actions)
        self.assertIn("toggle-renju", actions)
        self.assertEqual(
            gomoku_gui.settings_screen_action_at((toggle[0] + toggle[2] // 2, toggle[1] + toggle[3] // 2), width, height),
            "toggle-human",
        )
        self.assertIsNone(gomoku_gui.settings_screen_action_at((1, 1), width, height))

    def test_settings_screen_buttons_do_not_overlap(self) -> None:
        buttons = [rect for _action, rect, _label in gomoku_gui.settings_screen_buttons(666, 732)]
        for index, rect in enumerate(buttons):
            for other in buttons[index + 1 :]:
                self.assertFalse(rectangles_overlap(rect, other), f"{rect} overlaps {other}")

    def test_settings_screen_button_labels_are_action_oriented(self) -> None:
        labels = {action: label for action, _rect, label in gomoku_gui.settings_screen_buttons(666, 732)}

        self.assertEqual(labels["toggle-human"], "Play as other")
        self.assertEqual(labels["toggle-renju"], "Enable/disable Renju")
        self.assertEqual(labels["start-game"], "Start Game")
        self.assertNotIn("Toggle", labels["toggle-human"])
        self.assertNotIn("Toggle", labels["toggle-renju"])

    def test_window_size_has_minimum_for_settings_screen(self) -> None:
        width, height = gomoku_gui.window_size(5, 38, 48, 152)

        self.assertGreaterEqual(width, gomoku_gui.MIN_WINDOW_WIDTH)
        self.assertGreaterEqual(height, gomoku_gui.MIN_WINDOW_HEIGHT)

    def test_hint_text_is_compact(self) -> None:
        state = gomoku_gui.new_state()

        self.assertIn("R reset", gomoku_gui.hint_text(state))
        self.assertNotIn("SET", gomoku_gui.hint_text(state))
        self.assertNotIn("below", gomoku_gui.hint_text(state).lower())

    def test_detects_horizontal_vertical_and_diagonal_wins(self) -> None:
        scenarios = (
            [(8, 1), (8, 2), (8, 3), (8, 4), (8, 5)],
            [(1, 8), (2, 8), (3, 8), (4, 8), (5, 8)],
            [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)],
            [(5, 1), (4, 2), (3, 3), (2, 4), (1, 5)],
        )
        for moves in scenarios:
            with self.subTest(moves=moves):
                state = started_state()
                for row, col in moves[:-1]:
                    state["board"][row - 1][col - 1] = gomoku_gui.WHITE
                state["next_player"] = "white"

                state = gomoku_gui.apply_move(state, *moves[-1], "white")

                self.assertEqual(state["winner"], "white")
                self.assertEqual(len(state["winning_line"]), 5)

    def test_rejects_occupied_cell(self) -> None:
        state = started_state()
        state = gomoku_gui.apply_move(state, 8, 8, "black")

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 8, "white")

    def test_rejects_out_of_range_move(self) -> None:
        state = started_state()

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 0, 8, "black")

    def test_rejects_move_before_start(self) -> None:
        state = gomoku_gui.new_state()

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 8, "black")

    def test_rejects_invalid_board_cell_values(self) -> None:
        state = gomoku_gui.new_state()
        state["board"][0][0] = 9

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.validate_state_shape(state)

    def test_validate_state_shape_migrates_removed_rule_fields(self) -> None:
        state = gomoku_gui.new_state()
        state["win_length"] = 4
        state["overline_wins"] = False
        del state["setup_complete"]
        state.pop("game_event_id")

        gomoku_gui.validate_state_shape(state)

        self.assertNotIn("win_length", state)
        self.assertNotIn("overline_wins", state)
        self.assertFalse(state["setup_complete"])
        self.assertEqual(state["game_event_id"], 0)

    def test_full_board_without_winner_is_draw(self) -> None:
        state = started_state(size=5)
        state["board"] = [
            [1, 2, 1, 2, 1],
            [2, 1, 2, 1, 2],
            [1, 2, 2, 2, 1],
            [2, 1, 2, 1, 2],
            [1, 2, 1, 2, 0],
        ]
        state["next_player"] = "white"

        state = gomoku_gui.apply_move(state, 5, 5, "white")

        self.assertTrue(state["draw"])
        self.assertIsNone(state["winner"])

    def test_renju_black_overline_is_forbidden(self) -> None:
        state = started_state(renju_rules=True)
        for col in range(1, 6):
            state["board"][7][col - 1] = gomoku_gui.WHITE
        state["next_player"] = "white"

        state = gomoku_gui.apply_move(state, 8, 6, "white")

        self.assertEqual(state["winner"], "white")

        black_state = started_state(renju_rules=True)
        for col in range(1, 6):
            black_state["board"][7][col - 1] = gomoku_gui.BLACK

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(black_state, 8, 6, "black")

    def test_renju_black_exact_five_wins(self) -> None:
        state = started_state(renju_rules=True)
        for col in range(1, 5):
            state["board"][7][col - 1] = gomoku_gui.BLACK

        state = gomoku_gui.apply_move(state, 8, 5, "black")

        self.assertEqual(state["winner"], "black")

    def test_renju_black_double_four_is_forbidden(self) -> None:
        state = started_state(renju_rules=True)
        for row, col in ((8, 5), (8, 6), (8, 7), (5, 8), (6, 8), (7, 8)):
            state["board"][row - 1][col - 1] = gomoku_gui.BLACK

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 8, "black")

    def test_renju_black_double_three_is_forbidden(self) -> None:
        state = started_state(renju_rules=True)
        for row, col in ((8, 6), (8, 7), (6, 8), (7, 8)):
            state["board"][row - 1][col - 1] = gomoku_gui.BLACK

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 8, "black")

    def test_status_payload_includes_only_empty_forbidden_moves(self) -> None:
        state = started_state(renju_rules=True)
        for row, col in ((8, 6), (8, 7), (6, 8), (7, 8)):
            state["board"][row - 1][col - 1] = gomoku_gui.BLACK

        payload = gomoku_gui.status_payload(state)

        self.assertIn([8, 8], payload["forbidden_moves"])
        self.assertNotIn([8, 6], payload["forbidden_moves"])

    def test_status_payload_has_no_forbidden_moves_in_standard_rules(self) -> None:
        state = started_state()
        state = gomoku_gui.apply_move(state, 8, 8, "black")

        payload = gomoku_gui.status_payload(state)

        self.assertEqual(payload["forbidden_moves"], [])

    def test_codex_view_payload_uses_one_based_coordinate_summary(self) -> None:
        state = started_state(human_player="white", renju_rules=True)
        state = gomoku_gui.apply_move(state, 8, 8, "black")
        state = gomoku_gui.apply_move(state, 7, 8, "white")
        state = gomoku_gui.apply_move(state, 9, 8, "black")

        payload = gomoku_gui.codex_view_payload(state)

        self.assertNotIn("board", payload)
        self.assertEqual(payload["size"], 15)
        self.assertEqual(payload["codex_player"], "black")
        self.assertEqual(payload["human_player"], "white")
        self.assertTrue(payload["renju_rules"])
        self.assertEqual(payload["last_move"], {"row": 9, "col": 8, "player": "black"})
        self.assertEqual(payload["black"], [[8, 8], [9, 8]])
        self.assertEqual(payload["white"], [[7, 8]])
        self.assertNotIn("moves", payload)
        self.assertNotIn("legal_moves", payload)
        self.assertEqual(payload["forbidden_moves"], [])

    def test_codex_view_forbidden_moves_include_renju_forbidden_empty_move(self) -> None:
        state = started_state(renju_rules=True)
        for row, col in ((8, 6), (8, 7), (6, 8), (7, 8)):
            state["board"][row - 1][col - 1] = gomoku_gui.BLACK

        payload = gomoku_gui.codex_view_payload(state)

        self.assertIn([8, 8], payload["forbidden_moves"])
        self.assertNotIn([8, 6], payload["forbidden_moves"])

    def test_cli_help_hides_storage_and_raw_status_options(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--state", result.stdout)
        self.assertNotIn("--status", result.stdout)
        self.assertNotIn("state file", result.stdout)

    def test_cli_codex_view_outputs_summary_without_raw_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = started_state(human_player="white")
            state = gomoku_gui.apply_move(state, 8, 8, "black")
            gomoku_gui.save_state(state_path, state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--codex-view"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)
            self.assertEqual(payload["black"], [[8, 8]])
            self.assertEqual(payload["white"], [])
            self.assertEqual(payload["forbidden_moves"], [])

    def test_cli_codex_move_updates_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            reset = subprocess.run(
                [sys.executable, str(SCRIPT), "--reset"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            self.assertEqual(reset.returncode, 0, reset.stderr)

            state = gomoku_gui.load_state(state_path)
            state = gomoku_gui.start_game(state)
            state = gomoku_gui.apply_move(state, 8, 8, "black")
            gomoku_gui.save_state(state_path, state)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--codex-move", "8", "9"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)
            self.assertIn([8, 9], payload["white"])
            self.assertEqual(payload["next_player"], "black")

    def test_cli_codex_move_uses_configured_codex_color(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            reset = subprocess.run(
                [sys.executable, str(SCRIPT), "--human", "white", "--reset"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            self.assertEqual(reset.returncode, 0, reset.stderr)

            start = subprocess.run(
                [sys.executable, str(SCRIPT), "--start-game"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            self.assertEqual(start.returncode, 0, start.stderr)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--codex-move", "8", "8"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)
            self.assertIn([8, 8], payload["black"])
            self.assertEqual(payload["next_player"], "white")

    def test_wait_for_codex_turn_returns_after_human_move(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = started_state()
            state = gomoku_gui.apply_move(state, 8, 8, "black")
            state = gomoku_gui.apply_move(state, 8, 9, "white")
            gomoku_gui.save_state(state_path, state)

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "2",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            time.sleep(0.15)
            state = gomoku_gui.load_state(state_path)
            state = gomoku_gui.apply_move(state, 9, 9, "black")
            gomoku_gui.save_state(state_path, state)
            stdout, stderr = process.communicate(timeout=3)

            self.assertEqual(process.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["next_player"], payload["codex_player"])
            self.assertEqual(payload["last_move"], {"row": 9, "col": 9, "player": "black"})
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)

    def test_wait_does_not_return_during_setup_even_when_codex_is_black(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = gomoku_gui.adjust_settings(gomoku_gui.new_state(), "toggle-human")
            gomoku_gui.save_state(state_path, state)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "0.2",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("timed out waiting for Codex turn", result.stderr)

    def test_wait_ignores_settings_save_after_wait_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            gomoku_gui.save_state(state_path, gomoku_gui.new_state())

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "0.4",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            time.sleep(0.1)
            state = gomoku_gui.load_state(state_path)
            state = gomoku_gui.adjust_settings(state, "toggle-human")
            gomoku_gui.save_state(state_path, state)
            stdout, stderr = process.communicate(timeout=2)

            self.assertEqual(process.returncode, 2)
            self.assertEqual(stdout, "")
            self.assertIn("timed out waiting for Codex turn", stderr)

    def test_wait_returns_after_start_game_event_when_codex_is_black(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = gomoku_gui.adjust_settings(gomoku_gui.new_state(), "toggle-human")
            gomoku_gui.save_state(state_path, state)

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "2",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            time.sleep(0.1)
            state = gomoku_gui.start_game(gomoku_gui.load_state(state_path))
            gomoku_gui.save_state(state_path, state)
            stdout, stderr = process.communicate(timeout=3)

            self.assertEqual(process.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["codex_player"], "black")
            self.assertEqual(payload["next_player"], "black")
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)

    def test_human_white_wait_flow_resumes_after_white_move(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = gomoku_gui.start_game(gomoku_gui.new_state(human_player="white"))
            gomoku_gui.save_state(state_path, state)

            first_wait = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            self.assertEqual(first_wait.returncode, 0, first_wait.stderr)
            self.assertEqual(json.loads(first_wait.stdout)["codex_player"], "black")

            codex_move = subprocess.run(
                [sys.executable, str(SCRIPT), "--codex-move", "8", "8"],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            self.assertEqual(codex_move.returncode, 0, codex_move.stderr)

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--wait-for-codex-turn",
                    "--poll-interval",
                    "0.05",
                    "--timeout",
                    "2",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_ROOT,
                env=script_env(state_path),
            )
            time.sleep(0.15)
            state = gomoku_gui.load_state(state_path)
            state = gomoku_gui.apply_move(state, 8, 9, "white")
            gomoku_gui.save_state(state_path, state)
            stdout, stderr = process.communicate(timeout=3)

            self.assertEqual(process.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["next_player"], "black")
            self.assertEqual(payload["last_move"], {"row": 8, "col": 9, "player": "white"})
            self.assertNotIn("board", payload)
            self.assertNotIn("moves", payload)
            self.assertNotIn("legal_moves", payload)

def rectangles_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


if __name__ == "__main__":
    unittest.main()
