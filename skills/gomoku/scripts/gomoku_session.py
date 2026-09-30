"""Game transitions and locked, atomic session storage shared by GUI and CLI."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable
import uuid

from gomoku_rules import BLACK, EMPTY, WHITE, RuleEvaluator, freeze

PLAYER_TO_VALUE = {"black": BLACK, "white": WHITE}
NEXT_PLAYER = {"black": "white", "white": "black"}
MIN_BOARD_SIZE, MAX_BOARD_SIZE = 5, 25
State = dict[str, Any]


class GomokuError(ValueError):
    pass


class LockBusy(GomokuError):
    pass


def new_state(size: int = 15, human_player: str = "black", renju_rules: bool = False) -> State:
    if type(size) is not int or size < MIN_BOARD_SIZE:
        raise GomokuError("board size must be an integer of at least 5")
    if human_player not in PLAYER_TO_VALUE:
        raise GomokuError("human player must be black or white")
    return {
        "version": 1, "size": size, "renju_rules": renju_rules,
        "human_player": human_player, "codex_player": NEXT_PLAYER[human_player],
        "board": [[EMPTY] * size for _ in range(size)], "next_player": "black",
        "setup_complete": False, "game_event_id": 0, "moves": [], "last_move": None,
        "winner": None, "winning_line": [], "draw": False,
        "game_id": str(uuid.uuid4()), "revision": 0, "session_status": "headless",
    }


def normalized_state(state: State) -> State:
    """Copy and normalize version-one legacy files without mutating callers."""
    if not isinstance(state, dict) or state.get("version", 1) != 1:
        raise GomokuError("invalid state: unsupported version")
    result = deepcopy(state)
    size, board = result.get("size"), result.get("board")
    if type(size) is not int or size < MIN_BOARD_SIZE or not isinstance(board, list):
        raise GomokuError("invalid state: missing size or board")
    if len(board) != size or any(not isinstance(row, list) or len(row) != size for row in board):
        raise GomokuError("invalid state: board must be a square matrix matching size")
    if any(type(cell) is not int or cell not in {EMPTY, BLACK, WHITE} for row in board for cell in row):
        raise GomokuError("invalid state: board cells must be 0, 1, or 2")
    if result.get("next_player") not in PLAYER_TO_VALUE:
        raise GomokuError("invalid state: next_player must be black or white")
    human = result.setdefault("human_player", "black")
    if human not in PLAYER_TO_VALUE or result.setdefault("codex_player", NEXT_PLAYER[human]) != NEXT_PLAYER[human]:
        raise GomokuError("invalid state: players must be black and white opposites")
    result.setdefault("version", 1)
    result.setdefault("moves", [])
    result.setdefault("last_move", None)
    result.setdefault("winner", None)
    result.setdefault("draw", False)
    result.setdefault("winning_line", [])
    if not isinstance(result["moves"], list) or result["winner"] not in {None, "black", "white"}:
        raise GomokuError("invalid state: invalid moves or winner")
    result.setdefault("renju_rules", False)
    result.setdefault("setup_complete", bool(result["moves"] or result["winner"] or result["draw"]))
    result.setdefault("game_event_id", len(result["moves"]))
    result.setdefault("revision", result["game_event_id"])
    for key in ("game_event_id", "revision"):
        if type(result[key]) is not int or result[key] < 0:
            raise GomokuError(f"invalid state: {key} must be a nonnegative integer")
    if "game_id" not in result:
        result["game_id"] = str(uuid.uuid4())
    try:
        uuid.UUID(result["game_id"])
    except (ValueError, TypeError, AttributeError) as error:
        raise GomokuError("invalid state: game_id must be a UUID") from error
    result.setdefault("session_status", "headless")
    if result["session_status"] not in {"headless", "open", "closed"}:
        raise GomokuError("invalid state: unsupported session status")
    result.pop("win_length", None)
    result.pop("overline_wins", None)
    return result


def validate_state_shape(state: State) -> None:
    normalized_state(state)


def position_token(state: State) -> tuple[str, int]:
    return state["game_id"], state["revision"]


def require_position(state: State, game_id: str, revision: int) -> None:
    if position_token(state) != (game_id, revision):
        raise GomokuError("stale position: refresh the Codex view before selecting another move")


def advance(state: State, *, game_event: bool = True) -> State:
    state["revision"] += 1
    if game_event:
        state["game_event_id"] += 1
    return state


def start_game(state: State) -> State:
    result = normalized_state(state)
    if not result["setup_complete"]:
        result["setup_complete"] = True
        advance(result)
    return result


def reset_game(state: State, size: int | None = None, human_player: str | None = None,
               renju_rules: bool | None = None) -> State:
    previous = normalized_state(state)
    result = new_state(size if size is not None else previous["size"],
                       human_player if human_player is not None else previous["human_player"],
                       renju_rules if renju_rules is not None else previous["renju_rules"])
    result.update(revision=previous["revision"] + 1, game_event_id=previous["game_event_id"] + 1,
                  session_status=previous["session_status"])
    if "gui_id" in previous:
        result["gui_id"] = previous["gui_id"]
    return result


def apply_move(state: State, row: int, col: int, player: str | None = None) -> State:
    result = normalized_state(state)
    player = player or result["next_player"]
    if player not in PLAYER_TO_VALUE:
        raise GomokuError("player must be black or white")
    if result["winner"] or result["draw"]:
        raise GomokuError("game is already finished")
    if result["session_status"] == "closed":
        raise GomokuError("GUI is closed; reopen the game to continue")
    if not result["setup_complete"]:
        raise GomokuError("game has not started")
    if player != result["next_player"]:
        raise GomokuError(f"it is {result['next_player']}'s turn")
    if type(row) is not int or type(col) is not int or not 1 <= row <= result["size"] or not 1 <= col <= result["size"]:
        raise GomokuError(f"move must be between 1 and {result['size']}")
    assessment = RuleEvaluator(result["renju_rules"]).assess(freeze(result["board"]), (row - 1, col - 1), PLAYER_TO_VALUE[player])
    if not assessment.legal:
        if assessment.violation == "occupied":
            raise GomokuError(f"cell {row},{col} is already occupied")
        reason = {"black_overline": "black overline", "black_double_four": "black double-four",
                  "black_double_three": "black double-three"}.get(assessment.violation, assessment.violation)
        raise GomokuError(f"renju forbidden move: {reason}")
    result["board"] = [list(cells) for cells in assessment.board]
    move = {"row": row, "col": col, "player": player}
    result["moves"].append(move)
    result["last_move"] = move
    advance(result)
    if assessment.winner:
        result["winner"] = assessment.winner
        result["winning_line"] = [{"row": r + 1, "col": c + 1} for r, c in assessment.winning_line]
    elif all(cell != EMPTY for cells in result["board"] for cell in cells):
        result["draw"] = True
    else:
        result["next_player"] = NEXT_PLAYER[player]
    return result


def settings_editable(state: State) -> bool:
    return not state.get("setup_complete", False) and not state.get("moves")


def adjust_settings(state: State, action: str) -> State:
    if action == "start-game":
        return start_game(state)
    if not settings_editable(state):
        return deepcopy(state)
    size, human, renju = state["size"], state["human_player"], state.get("renju_rules", False)
    if action == "toggle-human":
        human = NEXT_PLAYER[human]
    elif action == "size-up":
        size = min(MAX_BOARD_SIZE, size + 1)
    elif action == "size-down":
        size = max(MIN_BOARD_SIZE, size - 1)
    elif action == "toggle-renju":
        renju = not renju
        size = 15 if renju else size
    else:
        return deepcopy(state)
    return reset_game(state, size, human, renju)


@contextmanager
def file_lock(path: Path, suffix: str = ".lock", *, blocking: bool = True):
    """OS-released locks; every production read/modify/write is one transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + suffix).open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, os.SEEK_END)
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in {11, 13, 36}:
                        raise
                    if not blocking:
                        raise LockBusy("a GUI is already open for this game") from error
                    time.sleep(0.025)
            def unlock():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError as error:
                raise LockBusy("a GUI is already open for this game") from error
            def unlock():
                fcntl.flock(stream, fcntl.LOCK_UN)
        try:
            yield
        finally:
            unlock()


def _write(path: Path, state: State) -> None:
    payload = json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".gomoku-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path: Path, size: int, human_player: str, renju_rules: bool) -> State:
    if not path.exists():
        result = new_state(size, human_player, renju_rules)
        _write(path, result)
        return result
    try:
        original = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise GomokuError(f"cannot read game state: {error}") from error
    result = normalized_state(original)
    if result != original:
        _write(path, result)
    return result


def load_state(path: Path, size: int = 15, human_player: str = "black", renju_rules: bool = False) -> State:
    with file_lock(path):
        state = _read(path, size, human_player, renju_rules)
    # Probe the GUI after releasing the state lock. A successful probe holds
    # GUI -> state locks while closing an abandoned session, never the reverse.
    return check_gui_liveness(path, state)


def save_state(path: Path, state: State) -> None:
    """Explicit snapshot replacement, principally for imports and test fixtures."""
    with file_lock(path):
        _write(path, normalized_state(state))


def mutate_state(path: Path, transition: Callable[[State], State], size: int = 15,
                 human_player: str = "black", renju_rules: bool = False) -> State:
    with file_lock(path):
        current = _read(path, size, human_player, renju_rules)
        result = normalized_state(transition(current))
        if result != current:
            _write(path, result)
        return result


def codex_move(path: Path, row: int, col: int, game_id: str, revision: int) -> State:
    def move(state):
        require_position(state, game_id, revision)
        return apply_move(state, row, col, state["codex_player"])
    with file_lock(path):
        if not path.is_file():
            raise GomokuError("stale position: game no longer exists; refresh the Codex view")
        snapshot = _read(path, 15, "black", False)
    check_gui_liveness(path, snapshot)
    with file_lock(path):
        if not path.is_file():
            raise GomokuError("stale position: game no longer exists; refresh the Codex view")
        current = _read(path, 15, "black", False)
        result = move(current)
        _write(path, result)
        return result


@contextmanager
def gui_session(path: Path, size: int = 15, human_player: str = "black", renju_rules: bool = False):
    """One GUI per state file; normal closure and process death wake waiters."""
    with file_lock(path, ".gui-lock", blocking=False):
        gui_id = str(uuid.uuid4())
        def opened(state):
            result = deepcopy(state)
            result.update(session_status="open", gui_id=gui_id)
            return advance(result, game_event=False)
        state = mutate_state(path, opened, size, human_player, renju_rules)
        try:
            yield state
        finally:
            def closed(current):
                if current.get("gui_id") != gui_id:
                    return current
                result = deepcopy(current)
                result["session_status"] = "closed"
                return advance(result, game_event=False)
            mutate_state(path, closed)


def check_gui_liveness(path: Path, state: State) -> State:
    if state["session_status"] != "open":
        return state
    try:
        with file_lock(path, ".gui-lock", blocking=False):
            def closed(current):
                if current.get("gui_id") != state.get("gui_id") or current["session_status"] != "open":
                    return current
                result = deepcopy(current)
                result["session_status"] = "closed"
                return advance(result, game_event=False)
            return mutate_state(path, closed)
    except LockBusy:
        return state


def is_codex_wait_ready(state: State) -> bool:
    return bool(state["session_status"] == "closed" or state.get("winner") or state.get("draw")
                or (state.get("setup_complete", False) and state["next_player"] == state["codex_player"]))


def wait_for_codex_turn(path: Path, size: int, human_player: str, renju_rules: bool,
                        poll_interval: float, timeout: float | None) -> State:
    if (not math.isfinite(poll_interval) or poll_interval <= 0
            or timeout is not None and (not math.isfinite(timeout) or timeout < 0)):
        raise GomokuError("poll interval must be positive and timeout must be nonnegative")
    started = time.monotonic()
    while True:
        state = load_state(path, size, human_player, renju_rules)
        if is_codex_wait_ready(state):
            return state
        if timeout is not None and time.monotonic() - started >= timeout:
            raise GomokuError("timed out waiting for Codex turn")
        time.sleep(poll_interval)
