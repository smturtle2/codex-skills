from __future__ import annotations

import importlib.util
import errno
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "gomoku" / "scripts" / "gomoku_gui.py"
sys.path.insert(0, str(SCRIPT.parent))

spec = importlib.util.spec_from_file_location("gomoku_gui", SCRIPT)
gomoku_gui = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gomoku_gui)
import gomoku_session as session


def started_state(**kwargs):
    return gomoku_gui.start_game(gomoku_gui.new_state(**kwargs))


def script_env(state_path: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    env["GOMOKU_STATE_PATH"] = str(state_path)
    return env


class GomokuGuiTests(unittest.TestCase):
    def test_cli_workspaces_are_isolated_and_legacy_state_remains_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            legacy = project / "legacy/state.json"
            first = pathlib.Path(".codex-skills/gomoku/first")
            second = pathlib.Path(".codex-skills/gomoku/second")

            def invoke(*args, env=None):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), *args], cwd=project,
                    env=env or script_env(legacy), capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            started = invoke("--run-dir", str(first), "--start-game")
            self.assertTrue(started["setup_complete"])
            invoke("--run-dir", str(second))
            self.assertFalse(legacy.exists())  # Explicit CLI workspace takes precedence.
            self.assertTrue(invoke("--run-dir", str(first))["setup_complete"])
            self.assertFalse(invoke("--run-dir", str(second))["setup_complete"])
            invoke("--start-game")
            self.assertTrue(legacy.is_file())
            self.assertTrue(invoke()["setup_complete"])
            env = os.environ.copy()
            env.pop("GOMOKU_STATE_PATH", None)
            invoke(env=env)
            self.assertTrue((project / ".codex-skills/gomoku/default/state.json").is_file())
            self.assertFalse((project / ".codex-gomoku").exists())

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
                [sys.executable, str(SCRIPT), "--codex-move", "8", "9",
                 "--game-id", state["game_id"], "--revision", str(state["revision"])],
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

    def test_reset_close_and_resume_release_the_existing_waiter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "state.json"
            before = session.apply_move(started_state(human_player="white"), 8, 8, "black")
            session.save_state(path, before)

            def waiter():
                return subprocess.Popen([sys.executable, str(SCRIPT), "--wait-for-codex-turn",
                                         "--poll-interval", "0.01", "--timeout", "3"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        env=script_env(path))

            process = waiter()
            time.sleep(0.1)
            # A replacement imported from an old helper may restart its counter.
            replacement = started_state(human_player="white")
            session.save_state(path, replacement)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)["game_id"], replacement["game_id"])

            session.save_state(path, before)
            with session.gui_session(path):
                process = waiter()
                time.sleep(0.1)
                self.assertIsNone(process.poll())
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            closed = json.loads(stdout)
            self.assertEqual(closed["session_status"], "closed")
            self.assertEqual(closed["game_id"], before["game_id"])
            self.assertEqual(session.load_state(path)["board"], before["board"])
            with session.gui_session(path) as reopened:
                self.assertEqual(reopened["session_status"], "open")
                self.assertEqual(reopened["board"], before["board"])
                self.assertGreater(reopened["revision"], closed["revision"])

            # An abruptly terminated owner cannot run its normal close handler.
            session.save_state(path, started_state(human_player="white"))
            program = """import json, pathlib, sys, time
sys.path.insert(0, sys.argv[2])
from gomoku_session import gui_session
with gui_session(pathlib.Path(sys.argv[1])) as state:
    print(json.dumps({'game_id': state['game_id'], 'revision': state['revision']}), flush=True)
    time.sleep(30)
"""
            owner = subprocess.Popen([sys.executable, "-c", program, str(path), str(SCRIPT.parent)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                token = json.loads(owner.stdout.readline())
            finally:
                owner.kill()
                owner.communicate(timeout=5)
            with self.assertRaisesRegex(session.GomokuError, "stale position"):
                session.codex_move(path, 8, 8, token["game_id"], token["revision"])
            recovered = session.load_state(path)
            self.assertEqual(recovered["session_status"], "closed")
            self.assertTrue(all(cell == session.EMPTY for row in recovered["board"] for cell in row))
            view = subprocess.run([sys.executable, str(SCRIPT), "--threat-view"],
                                  env=script_env(path), capture_output=True, text=True, timeout=5)
            self.assertEqual(view.returncode, 0, view.stderr)
            self.assertEqual(json.loads(view.stdout)["session_status"], "closed")

    def test_selection_tokens_and_transactions_preserve_rejected_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "state.json"
            state = started_state(human_player="white", renju_rules=True)
            for row, col in ((8, 7), (8, 10), (8, 11), (6, 8), (7, 8), (9, 8)):
                state["board"][row - 1][col - 1] = session.BLACK
            session.save_state(path, state)
            original = path.read_bytes()
            with self.assertRaisesRegex(session.GomokuError, "double-four"):
                session.codex_move(path, 8, 8, *session.position_token(state))
            self.assertEqual(path.read_bytes(), original)
            reset = session.mutate_state(path, lambda current: session.start_game(session.reset_game(current)))
            original = path.read_bytes()
            with self.assertRaisesRegex(session.GomokuError, "stale position"):
                session.codex_move(path, 8, 8, *session.position_token(state))
            self.assertEqual(path.read_bytes(), original)
            self.assertNotEqual(reset["game_id"], state["game_id"])
            self.assertGreater(reset["revision"], state["revision"])

            command = [sys.executable, str(SCRIPT), "--codex-move", "8", "8",
                       "--game-id", reset["game_id"], "--revision", str(reset["revision"])]
            # Simultaneous adapters cannot both commit decisions from one view.
            processes = [subprocess.Popen(command, env=script_env(path), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True) for _ in range(2)]
            results = [(p.returncode, out, err) for p in processes for out, err in [p.communicate(timeout=5)]]
            self.assertEqual(sorted(code for code, _, _ in results), [0, 2])
            self.assertIn("stale position", next(err for code, _, err in results if code))
            self.assertEqual(len(session.load_state(path)["moves"]), 1)

    def test_legacy_state_migration_and_windows_byte_lock_protocol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "legacy.json"
            legacy = started_state()
            for key in ("game_id", "revision", "session_status"):
                legacy.pop(key)
            legacy.update(win_length=5, overline_wins=False)
            path.write_text(json.dumps(legacy), encoding="utf-8")
            loaded = session.load_state(path)
            self.assertEqual(loaded["board"], legacy["board"])
            self.assertEqual(session.position_token(session.load_state(path)), session.position_token(loaded))
            self.assertNotIn("win_length", loaded)

            calls = []
            failures = [True, False]
            def locking(fd, mode, length):
                calls.append((mode, length))
                if mode == 1 and failures.pop(0):
                    raise OSError(errno.EACCES, "locked")
            msvcrt = types.SimpleNamespace(locking=locking, LK_NBLCK=1, LK_UNLCK=2)
            with patch.dict(sys.modules, {"msvcrt": msvcrt}), patch.object(session.os, "name", "nt"), patch.object(session.time, "sleep"):
                with session.file_lock(path):
                    pass
            self.assertEqual(calls, [(1, 1), (1, 1), (2, 1)])
            def busy(*args):
                raise OSError(errno.EACCES, "locked")
            msvcrt.locking = busy
            with patch.dict(sys.modules, {"msvcrt": msvcrt}), patch.object(session.os, "name", "nt"):
                with self.assertRaises(session.LockBusy):
                    with session.file_lock(path, ".gui-lock", blocking=False):
                        self.fail("busy lock must not be acquired")


if __name__ == "__main__":
    unittest.main()
