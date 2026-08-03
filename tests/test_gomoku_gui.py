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
        self.assertTrue(all(cell == gomoku_gui.EMPTY for row in state["board"] for cell in row))

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
        state = gomoku_gui.apply_move(started_state(), 8, 8, "black")

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 8, "white")

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
            state["board"][7][col - 1] = gomoku_gui.BLACK

        with self.assertRaises(gomoku_gui.GomokuError):
            gomoku_gui.apply_move(state, 8, 6, "black")

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

    def test_cli_codex_move_updates_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = started_state()
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
            self.assertIn("ascii_board", payload)
            self.assertNotIn("board", payload)
            self.assertEqual(payload["next_player"], "black")
            saved = gomoku_gui.load_state(state_path)
            self.assertEqual(saved["board"][7][8], gomoku_gui.WHITE)
            self.assertEqual(saved["last_move"], {"row": 8, "col": 9, "player": "white"})

    def test_wait_returns_after_start_game_event_when_codex_is_black(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = pathlib.Path(tmpdir) / "state.json"
            state = gomoku_gui.new_state(human_player="white")
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
            gomoku_gui.save_state(state_path, gomoku_gui.start_game(gomoku_gui.load_state(state_path)))
            stdout, stderr = process.communicate(timeout=3)

            self.assertEqual(process.returncode, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["codex_player"], "black")
            self.assertEqual(payload["next_player"], "black")
            self.assertIn("ascii_board", payload)
            self.assertNotIn("board", payload)


if __name__ == "__main__":
    unittest.main()
