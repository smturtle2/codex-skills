#!/usr/bin/env python3
# /// script
# dependencies = ["pygame>=2.6"]
# ///
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from copy import deepcopy
from typing import Any

EMPTY = 0
BLACK = 1
WHITE = 2

PLAYER_TO_VALUE = {"black": BLACK, "white": WHITE}
NEXT_PLAYER = {"black": "white", "white": "black"}
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
MIN_BOARD_SIZE = 5
MAX_BOARD_SIZE = 25
MIN_WINDOW_WIDTH = 560
MIN_WINDOW_HEIGHT = 620
DEFAULT_STATE_PATH = pathlib.Path(".codex-gomoku/state.json")


class GomokuError(ValueError):
    pass


def new_state(
    size: int = 15,
    human_player: str = "black",
    renju_rules: bool = False,
) -> dict[str, Any]:
    if size < MIN_BOARD_SIZE:
        raise GomokuError("board size must be at least 5")
    if human_player not in PLAYER_TO_VALUE:
        raise GomokuError("human player must be black or white")
    codex_player = NEXT_PLAYER[human_player]
    return {
        "version": 1,
        "size": size,
        "renju_rules": renju_rules,
        "human_player": human_player,
        "codex_player": codex_player,
        "board": [[EMPTY for _ in range(size)] for _ in range(size)],
        "next_player": "black",
        "setup_complete": False,
        "game_event_id": 0,
        "moves": [],
        "last_move": None,
        "winner": None,
        "winning_line": [],
        "draw": False,
    }


def load_state(
    path: pathlib.Path,
    size: int = 15,
    human_player: str = "black",
    renju_rules: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        state = new_state(size=size, human_player=human_player, renju_rules=renju_rules)
        save_state(path, state)
        return state
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    validate_state_shape(state)
    return state


def save_state(path: pathlib.Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)


def validate_state_shape(state: dict[str, Any]) -> None:
    size = state.get("size")
    board = state.get("board")
    if not isinstance(size, int) or not isinstance(board, list):
        raise GomokuError("invalid state: missing size or board")
    if len(board) != size or any(not isinstance(row, list) or len(row) != size for row in board):
        raise GomokuError("invalid state: board must be a square matrix matching size")
    if any(cell not in {EMPTY, BLACK, WHITE} for row in board for cell in row):
        raise GomokuError("invalid state: board cells must be 0, 1, or 2")
    if state.get("next_player") not in PLAYER_TO_VALUE:
        raise GomokuError("invalid state: next_player must be black or white")
    human_player = state.get("human_player", "black")
    codex_player = state.get("codex_player", NEXT_PLAYER.get(human_player))
    if human_player not in PLAYER_TO_VALUE:
        raise GomokuError("invalid state: human_player must be black or white")
    if codex_player != NEXT_PLAYER[human_player]:
        raise GomokuError("invalid state: codex_player must be the opposite of human_player")
    state.setdefault("renju_rules", False)
    state.setdefault("setup_complete", bool(state.get("moves") or state.get("winner") or state.get("draw")))
    state.setdefault("game_event_id", len(state.get("moves", [])))
    state.pop("win_length", None)
    state.pop("overline_wins", None)


def next_game_event_id(state: dict[str, Any]) -> int:
    return int(state.get("game_event_id", 0)) + 1


def start_game(state: dict[str, Any]) -> dict[str, Any]:
    validate_state_shape(state)
    next_state = deepcopy(state)
    if next_state.get("setup_complete", False):
        return next_state
    next_state["setup_complete"] = True
    next_state["game_event_id"] = next_game_event_id(state)
    return next_state


def apply_move(state: dict[str, Any], row: int, col: int, player: str | None = None) -> dict[str, Any]:
    validate_state_shape(state)
    next_state = deepcopy(state)
    size = next_state["size"]
    player = player or next_state["next_player"]
    if player not in PLAYER_TO_VALUE:
        raise GomokuError("player must be black or white")
    if next_state.get("winner"):
        raise GomokuError("game is already finished")
    if next_state.get("draw"):
        raise GomokuError("game is already a draw")
    if not next_state.get("setup_complete", False):
        raise GomokuError("game has not started")
    if player != next_state["next_player"]:
        raise GomokuError(f"it is {next_state['next_player']}'s turn")
    if row < 1 or row > size or col < 1 or col > size:
        raise GomokuError(f"move must be between 1 and {size}")

    row_index = row - 1
    col_index = col - 1
    if next_state["board"][row_index][col_index] != EMPTY:
        raise GomokuError(f"cell {row},{col} is already occupied")

    value = PLAYER_TO_VALUE[player]
    next_state["board"][row_index][col_index] = value
    if player == "black" and next_state.get("renju_rules", False):
        validate_renju_black_move(next_state["board"], row_index, col_index)
    move = {"row": row, "col": col, "player": player}
    next_state["moves"].append(move)
    next_state["last_move"] = move
    next_state["game_event_id"] = next_game_event_id(state)

    winning_line = find_winning_line(
        next_state["board"],
        row_index,
        col_index,
        value,
        5,
        player == "white" or not next_state.get("renju_rules", False),
    )
    if winning_line:
        next_state["winner"] = player
        next_state["winning_line"] = [{"row": r + 1, "col": c + 1} for r, c in winning_line]
    elif all(cell != EMPTY for board_row in next_state["board"] for cell in board_row):
        next_state["draw"] = True
    else:
        next_state["next_player"] = NEXT_PLAYER[player]

    return next_state


def validate_renju_black_move(board: list[list[int]], row: int, col: int) -> None:
    if has_overline(board, row, col, BLACK):
        raise GomokuError("renju forbidden move: black overline")
    if find_winning_line(board, row, col, BLACK, 5, False):
        return
    if count_open_threes(board, row, col, BLACK) >= 2:
        raise GomokuError("renju forbidden move: black double-three")
    if count_fours(board, row, col, BLACK) >= 2:
        raise GomokuError("renju forbidden move: black double-four")


def has_overline(board: list[list[int]], row: int, col: int, value: int) -> bool:
    return any(len(collect_line(board, row, col, value, dr, dc, len(board))) > 5 for dr, dc in DIRECTIONS)


def count_fours(board: list[list[int]], row: int, col: int, value: int) -> int:
    count = 0
    for row_delta, col_delta in DIRECTIONS:
        cells = directional_window(board, row, col, row_delta, col_delta)
        if line_has_exact_pattern(cells, [value, value, value, value, EMPTY]) or line_has_exact_pattern(
            cells, [EMPTY, value, value, value, value]
        ):
            count += 1
        elif line_has_exact_pattern(cells, [value, value, value, EMPTY, value]) or line_has_exact_pattern(
            cells, [value, EMPTY, value, value, value]
        ):
            count += 1
    return count


def count_open_threes(board: list[list[int]], row: int, col: int, value: int) -> int:
    count = 0
    for row_delta, col_delta in DIRECTIONS:
        cells = directional_window(board, row, col, row_delta, col_delta)
        if any(
            line_has_exact_pattern(cells, pattern)
            for pattern in (
                [EMPTY, value, value, value, EMPTY],
                [EMPTY, value, value, EMPTY, value, EMPTY],
                [EMPTY, value, EMPTY, value, value, EMPTY],
            )
        ):
            count += 1
    return count


def directional_window(
    board: list[list[int]],
    row: int,
    col: int,
    row_delta: int,
    col_delta: int,
    radius: int = 5,
) -> list[int | None]:
    size = len(board)
    cells: list[int | None] = []
    for offset in range(-radius, radius + 1):
        r = row + offset * row_delta
        c = col + offset * col_delta
        cells.append(board[r][c] if 0 <= r < size and 0 <= c < size else None)
    return cells


def line_has_exact_pattern(cells: list[int | None], pattern: list[int]) -> bool:
    width = len(pattern)
    for start in range(0, len(cells) - width + 1):
        if cells[start : start + width] == pattern:
            return True
    return False


def find_winning_line(
    board: list[list[int]],
    row: int,
    col: int,
    value: int,
    win_length: int,
    overline_wins: bool,
) -> list[tuple[int, int]]:
    size = len(board)
    for row_delta, col_delta in DIRECTIONS:
        line = collect_line(board, row, col, value, row_delta, col_delta, size)
        if len(line) >= win_length and overline_wins:
            return line
        if len(line) == win_length:
            return line
    return []


def collect_line(
    board: list[list[int]],
    row: int,
    col: int,
    value: int,
    row_delta: int,
    col_delta: int,
    size: int,
) -> list[tuple[int, int]]:
    before: list[tuple[int, int]] = []
    r, c = row - row_delta, col - col_delta
    while 0 <= r < size and 0 <= c < size and board[r][c] == value:
        before.append((r, c))
        r -= row_delta
        c -= col_delta

    after: list[tuple[int, int]] = []
    r, c = row + row_delta, col + col_delta
    while 0 <= r < size and 0 <= c < size and board[r][c] == value:
        after.append((r, c))
        r += row_delta
        c += col_delta

    return list(reversed(before)) + [(row, col)] + after


def forbidden_move_list(state: dict[str, Any]) -> list[list[int]]:
    validate_state_shape(state)
    forbidden_moves = []
    if not state.get("setup_complete", False) or state.get("winner") or state.get("draw"):
        return forbidden_moves

    player = state["next_player"]
    for row_index, board_row in enumerate(state["board"]):
        for col_index, cell in enumerate(board_row):
            if cell != EMPTY:
                continue
            row = row_index + 1
            col = col_index + 1
            if not is_legal_move(state, row, col, player):
                forbidden_moves.append([row, col])
    return forbidden_moves


def status_payload(state: dict[str, Any]) -> dict[str, Any]:
    validate_state_shape(state)
    payload = deepcopy(state)
    payload["forbidden_moves"] = forbidden_move_list(state)
    return payload


def coordinate_list(state: dict[str, Any], value: int) -> list[list[int]]:
    return [
        [row_index + 1, col_index + 1]
        for row_index, row in enumerate(state["board"])
        for col_index, cell in enumerate(row)
        if cell == value
    ]


def recent_moves(state: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    moves = state.get("moves", [])
    if not isinstance(moves, list):
        return []
    return [
        {"row": move["row"], "col": move["col"], "player": move["player"]}
        for move in moves[-limit:]
        if isinstance(move, dict) and {"row", "col", "player"} <= move.keys()
    ]


def ascii_board(state: dict[str, Any]) -> str:
    size = state["size"]
    last_move = state.get("last_move") or {}
    last_cell = None
    if isinstance(last_move, dict):
        last_cell = (last_move.get("row"), last_move.get("col"), last_move.get("player"))

    lines = ["     " + " ".join(f"{col:02d}" for col in range(1, size + 1))]
    for row_index, board_row in enumerate(state["board"]):
        row = row_index + 1
        cells = []
        for col_index, value in enumerate(board_row):
            col = col_index + 1
            if last_cell == (row, col, "black"):
                marker = "b"
            elif last_cell == (row, col, "white"):
                marker = "w"
            elif value == BLACK:
                marker = "B"
            elif value == WHITE:
                marker = "W"
            else:
                marker = "."
            cells.append(marker)
        lines.append(f"{row:02d}   " + "  ".join(cells))
    return "\n".join(lines)


def codex_view_payload(state: dict[str, Any]) -> dict[str, Any]:
    status = status_payload(state)
    return {
        "size": status["size"],
        "next_player": status["next_player"],
        "codex_player": status["codex_player"],
        "human_player": status["human_player"],
        "renju_rules": status.get("renju_rules", False),
        "setup_complete": status.get("setup_complete", False),
        "game_event_id": status.get("game_event_id", 0),
        "last_move": status.get("last_move"),
        "recent_moves": recent_moves(status),
        "ascii_board": ascii_board(status),
        "black": coordinate_list(status, BLACK),
        "white": coordinate_list(status, WHITE),
        "forbidden_moves": status["forbidden_moves"],
        "winner": status.get("winner"),
        "winning_line": [[item["row"], item["col"]] for item in status.get("winning_line", [])],
        "draw": status.get("draw", False),
    }


def is_legal_move(state: dict[str, Any], row: int, col: int, player: str) -> bool:
    try:
        apply_move(state, row, col, player)
    except GomokuError:
        return False
    return True


def is_codex_wait_ready(state: dict[str, Any]) -> bool:
    return bool(
        state.get("winner")
        or state.get("draw")
        or (state.get("setup_complete", False) and state["next_player"] == state["codex_player"])
    )


def wait_for_codex_turn(
    state_path: pathlib.Path,
    size: int,
    human_player: str,
    renju_rules: bool,
    poll_interval: float,
    timeout: float | None,
) -> dict[str, Any]:
    start = time_monotonic()
    initial_state = load_state(
        state_path,
        size=size,
        human_player=human_player,
        renju_rules=renju_rules,
    )
    baseline_event_id = int(initial_state.get("game_event_id", 0))
    if is_codex_wait_ready(initial_state):
        return status_payload(initial_state)
    while True:
        state = load_state(
            state_path,
            size=size,
            human_player=human_player,
            renju_rules=renju_rules,
        )
        event_advanced = int(state.get("game_event_id", 0)) > baseline_event_id
        if event_advanced and is_codex_wait_ready(state):
            return status_payload(state)
        if timeout is not None and time_monotonic() - start >= timeout:
            raise GomokuError("timed out waiting for Codex turn")
        sleep(poll_interval)


def time_monotonic() -> float:
    import time

    return time.monotonic()


def sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def run_gui(state_path: pathlib.Path, size: int, human_player: str, renju_rules: bool) -> None:
    try:
        import pygame
    except ImportError as exc:
        raise SystemExit("pygame is required for the GUI. Install pygame in the active Python environment.") from exc

    pygame.init()
    state = load_state(
        state_path,
        size=size,
        human_player=human_player,
        renju_rules=renju_rules,
    )
    board_size = state["size"]
    cell = 38
    margin = 48
    status_height = 78
    width, height = window_size(board_size, cell, margin, status_height)
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Gomoku")
    font = pygame.font.SysFont("arial", 18)
    small_font = pygame.font.SysFont("arial", 14)
    title_font = pygame.font.SysFont("arial", 28)
    clock = pygame.time.Clock()
    last_mtime = state_path.stat().st_mtime if state_path.exists() else 0.0
    screen_mode = "game" if state.get("setup_complete", False) else "settings"

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                state = new_state(
                    size=board_size,
                    human_player=state["human_player"],
                    renju_rules=state["renju_rules"],
                )
                screen_mode = "settings"
                save_state(state_path, state)
                last_mtime = state_path.stat().st_mtime
            elif event.type == pygame.KEYDOWN and settings_editable(state):
                state = handle_settings_key(event.key, state)
                board_size = state["size"]
                save_state(state_path, state)
                width, height = window_size(board_size, cell, margin, status_height)
                screen = pygame.display.set_mode((width, height))
                last_mtime = state_path.stat().st_mtime
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                width, height = screen.get_size()
                if screen_mode == "settings":
                    action = settings_screen_action_at(event.pos, width, height)
                    if action and settings_editable(state):
                        state = adjust_settings(state, action)
                        if action == "start-game":
                            screen_mode = "game"
                        board_size = state["size"]
                        save_state(state_path, state)
                        width, height = window_size(board_size, cell, margin, status_height)
                        screen = pygame.display.set_mode((width, height))
                        last_mtime = state_path.stat().st_mtime
                    continue
                move = pixel_to_move(event.pos, board_size, cell, margin)
                if (
                    move
                    and state.get("setup_complete", False)
                    and state["next_player"] == state["human_player"]
                    and not state.get("winner")
                    and not state.get("draw")
                ):
                    try:
                        state = apply_move(state, move[0], move[1], state["human_player"])
                        save_state(state_path, state)
                        last_mtime = state_path.stat().st_mtime
                    except GomokuError:
                        pass

        if state_path.exists():
            mtime = state_path.stat().st_mtime
            if mtime > last_mtime:
                state = load_state(
                    state_path,
                    size=size,
                    human_player=human_player,
                    renju_rules=renju_rules,
                )
                board_size = state["size"]
                if not state.get("setup_complete", False):
                    screen_mode = "settings"
                last_mtime = mtime

        if screen_mode == "settings":
            draw_settings_screen(screen, state, title_font, font, small_font)
        else:
            draw(screen, state, cell, margin, status_height, font, small_font)
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


def window_size(board_size: int, cell: int, margin: int, status_height: int) -> tuple[int, int]:
    board_extent = margin * 2 + cell * (board_size - 1)
    return max(MIN_WINDOW_WIDTH, board_extent), max(MIN_WINDOW_HEIGHT, board_extent + status_height)


def handle_settings_key(key: int, state: dict[str, Any]) -> dict[str, Any]:
    import pygame

    if key == pygame.K_h:
        return adjust_settings(state, "toggle-human")
    elif key in {pygame.K_EQUALS, pygame.K_PLUS}:
        return adjust_settings(state, "size-up")
    elif key in {pygame.K_MINUS, pygame.K_UNDERSCORE}:
        return adjust_settings(state, "size-down")
    elif key == pygame.K_l:
        return adjust_settings(state, "toggle-renju")
    elif key == pygame.K_s:
        return adjust_settings(state, "start-game")
    return state


def settings_editable(state: dict[str, Any]) -> bool:
    return not state.get("setup_complete", False) and not state.get("moves")


def adjust_settings(state: dict[str, Any], action: str) -> dict[str, Any]:
    if action == "start-game":
        return start_game(state)
    if not settings_editable(state):
        return state

    size = state["size"]
    human_player = state["human_player"]
    renju_rules = state.get("renju_rules", False)

    if action == "toggle-human":
        human_player = NEXT_PLAYER[human_player]
    elif action == "size-up":
        size = min(MAX_BOARD_SIZE, size + 1)
    elif action == "size-down":
        size = max(MIN_BOARD_SIZE, size - 1)
    elif action == "toggle-renju":
        renju_rules = not renju_rules
        if renju_rules:
            size = 15
    else:
        return state

    return new_state(size=size, human_player=human_player, renju_rules=renju_rules)


def settings_screen_action_at(pos: tuple[int, int], width: int, height: int) -> str | None:
    x, y = pos
    for action, rect, _label in settings_screen_buttons(width, height):
        rx, ry, rw, rh = rect
        if rx <= x <= rx + rw and ry <= y <= ry + rh:
            return action
    return None


def settings_screen_buttons(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int], str]]:
    panel_width, panel_height, left, top = settings_panel_rect(width, height)
    button_height = 38
    control_left = left + panel_width - 196
    narrow_width = 82
    return [
        ("toggle-human", (control_left, top + 112, 168, button_height), "Play as other"),
        ("size-down", (control_left, top + 174, narrow_width, button_height), "-"),
        ("size-up", (control_left + 90, top + 174, narrow_width, button_height), "+"),
        ("toggle-renju", (control_left, top + 236, 168, button_height), "Enable/disable Renju"),
        ("start-game", (left + 28, top + panel_height - 62, 132, button_height), "Start Game"),
    ]


def settings_panel_rect(width: int, height: int) -> tuple[int, int, int, int]:
    panel_width = min(500, width - 48)
    panel_height = min(440, height - 48)
    left = (width - panel_width) // 2
    top = (height - panel_height) // 2
    return panel_width, panel_height, left, top


def settings_summary(state: dict[str, Any]) -> str:
    phase = "started" if state.get("setup_complete", False) else "setup"
    return (
        f"Human {state['human_player']} | Codex {state['codex_player']} | "
        f"{state['size']}x{state['size']} | renju {'on' if state.get('renju_rules', False) else 'off'} | {phase}"
    )


def pixel_to_move(pos: tuple[int, int], size: int, cell: int, margin: int) -> tuple[int, int] | None:
    x, y = pos
    col = round((x - margin) / cell)
    row = round((y - margin) / cell)
    if row < 0 or row >= size or col < 0 or col >= size:
        return None
    snap_x = margin + col * cell
    snap_y = margin + row * cell
    if abs(x - snap_x) > cell * 0.42 or abs(y - snap_y) > cell * 0.42:
        return None
    return row + 1, col + 1


def draw(screen: Any, state: dict[str, Any], cell: int, margin: int, status_height: int, font: Any, small_font: Any) -> None:
    import pygame

    board_size = state["size"]
    width, height = screen.get_size()
    board_bottom = height - status_height
    screen.fill((236, 188, 112))
    pygame.draw.rect(screen, (42, 34, 26), (0, board_bottom, width, status_height))

    for index in range(board_size):
        start = margin
        end = margin + cell * (board_size - 1)
        coord = margin + index * cell
        pygame.draw.line(screen, (48, 37, 27), (start, coord), (end, coord), 2)
        pygame.draw.line(screen, (48, 37, 27), (coord, start), (coord, end), 2)
        row_label = small_font.render(str(index + 1), True, (42, 34, 26))
        col_label = small_font.render(str(index + 1), True, (42, 34, 26))
        screen.blit(row_label, (16, coord - 8))
        screen.blit(col_label, (coord - 6, 18))

    star_points = star_point_indexes(board_size)
    for row in star_points:
        for col in star_points:
            pygame.draw.circle(screen, (48, 37, 27), (margin + col * cell, margin + row * cell), 4)

    winning_cells = {(item["row"], item["col"]) for item in state.get("winning_line", [])}
    for row_index, board_row in enumerate(state["board"]):
        for col_index, value in enumerate(board_row):
            if value == EMPTY:
                continue
            center = (margin + col_index * cell, margin + row_index * cell)
            color = (20, 20, 20) if value == BLACK else (244, 244, 244)
            outline = (10, 10, 10)
            pygame.draw.circle(screen, outline, center, 15)
            pygame.draw.circle(screen, color, center, 13)
            if (row_index + 1, col_index + 1) in winning_cells:
                pygame.draw.circle(screen, (220, 40, 40), center, 18, 3)

    last_move = state.get("last_move")
    if last_move:
        center = (margin + (last_move["col"] - 1) * cell, margin + (last_move["row"] - 1) * cell)
        pygame.draw.circle(screen, (219, 52, 52), center, 5)

    status = status_text(state)
    draw_text_clipped(screen, status, font, (250, 250, 250), (20, board_bottom + 12), width - 40)
    draw_text_clipped(screen, hint_text(state), small_font, (210, 210, 210), (20, board_bottom + 40), width - 40)


def draw_text_clipped(
    screen: Any,
    text: str,
    font: Any,
    color: tuple[int, int, int],
    pos: tuple[int, int],
    max_width: int,
) -> None:
    if font.size(text)[0] <= max_width:
        screen.blit(font.render(text, True, color), pos)
        return
    ellipsis = "..."
    clipped = text
    while clipped and font.size(clipped + ellipsis)[0] > max_width:
        clipped = clipped[:-1]
    screen.blit(font.render(clipped + ellipsis, True, color), pos)


def draw_settings_screen(screen: Any, state: dict[str, Any], title_font: Any, font: Any, small_font: Any) -> None:
    import pygame

    width, height = screen.get_size()
    screen.fill((31, 34, 38))
    panel_width, panel_height, left, top = settings_panel_rect(width, height)
    panel = (left, top, panel_width, panel_height)
    pygame.draw.rect(screen, (242, 242, 238), panel, border_radius=8)
    pygame.draw.rect(screen, (78, 78, 72), panel, width=2, border_radius=8)

    title = title_font.render("Game Settings", True, (28, 28, 26))
    screen.blit(title, (left + 24, top + 22))

    editable = settings_editable(state)
    subtitle_text = "Choose settings, then start the game." if editable else "Game already started. Settings are read-only."
    subtitle = small_font.render(subtitle_text, True, (86, 86, 78))
    screen.blit(subtitle, (left + 24, top + 58))

    values = [
        ("Players", f"Human {state['human_player']} / Codex {state['codex_player']}"),
        ("Board size", f"{state['size']} x {state['size']}"),
        ("Renju rules", "On" if state.get("renju_rules", False) else "Off"),
    ]
    for index, (label, value) in enumerate(values):
        y = top + 112 + index * 62
        label_text = small_font.render(label.upper(), True, (102, 102, 94))
        value_text = font.render(value, True, (38, 38, 34))
        screen.blit(label_text, (left + 28, y - 4))
        screen.blit(value_text, (left + 28, y + 18))

    for action, rect, label in settings_screen_buttons(width, height):
        if not editable:
            continue
        if action == "toggle-human":
            label = f"Play as {NEXT_PLAYER[state['human_player']].title()}"
        elif action == "toggle-renju":
            label = "Disable Renju" if state.get("renju_rules", False) else "Enable Renju"
        draw_button(screen, rect, label, small_font, primary=(action == "start-game"))


def draw_button(screen: Any, rect: tuple[int, int, int, int], label: str, font: Any, primary: bool = False) -> None:
    import pygame

    fill = (45, 87, 160) if primary else (255, 255, 255)
    border = (45, 87, 160) if primary else (125, 125, 116)
    text_color = (255, 255, 255) if primary else (28, 28, 26)
    pygame.draw.rect(screen, fill, rect, border_radius=5)
    pygame.draw.rect(screen, border, rect, width=1, border_radius=5)
    text = font.render(label, True, text_color)
    screen.blit(text, (rect[0] + (rect[2] - text.get_width()) // 2, rect[1] + (rect[3] - text.get_height()) // 2))


def star_point_indexes(size: int) -> list[int]:
    if size < 9:
        return [size // 2]
    edge = 3 if size >= 13 else 2
    return [edge, size // 2, size - edge - 1]


def status_text(state: dict[str, Any]) -> str:
    if state.get("winner"):
        return f"{state['winner'].title()} wins"
    if state.get("draw"):
        return "Draw"
    if not state.get("setup_complete", False):
        return "Setup: choose settings, then Start Game"
    human_player = state.get("human_player", "black")
    codex_player = state.get("codex_player", NEXT_PLAYER[human_player])
    if state["next_player"] == human_player:
        return f"Your turn: {human_player}"
    return f"Codex turn: {codex_player}"


def hint_text(state: dict[str, Any]) -> str:
    role = f"You {state.get('human_player', 'black')} | Codex {state.get('codex_player', 'white')}"
    rules = f"{state['size']}x{state['size']} | renju {'on' if state.get('renju_rules', False) else 'off'}"
    if not state.get("setup_complete", False):
        return f"{role} | {rules} | S start | R reset"
    return f"{role} | {rules} | R reset"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Gomoku with Codex through a Pygame GUI and managed game state.")
    parser.add_argument("--size", type=int, default=15)
    parser.add_argument("--human", choices=("black", "white"), default="black", help="Human player color for new games.")
    parser.add_argument("--renju", action="store_true", help="Enable Renju restrictions for black.")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the Pygame board instead of printing Codex view JSON.",
    )
    parser.add_argument(
        "--codex-view",
        action="store_true",
        help=(
            "Print a compact 1-based coordinate summary for Codex move selection. "
            "This is the default when no action flag is provided."
        ),
    )
    parser.add_argument("--reset", action="store_true", help="Reset the game and exit.")
    parser.add_argument("--start-game", action="store_true", help="Mark setup complete and start the current game.")
    parser.add_argument("--codex-move", nargs=2, type=int, metavar=("ROW", "COL"), help="Apply Codex's configured move using 1-based coordinates.")
    parser.add_argument(
        "--wait-for-codex-turn",
        action="store_true",
        help="Block until setup is complete and the state reaches Codex's turn, then print Codex view JSON.",
    )
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    state_path = pathlib.Path(os.environ.get("GOMOKU_STATE_PATH", DEFAULT_STATE_PATH))
    try:
        if args.reset:
            save_state(state_path, new_state(args.size, args.human, args.renju))
            print("reset")
            return 0

        if args.wait_for_codex_turn:
            payload = wait_for_codex_turn(
                state_path,
                args.size,
                args.human,
                args.renju,
                args.poll_interval,
                args.timeout,
            )
            print(json.dumps(codex_view_payload(payload), indent=2, sort_keys=True))
            return 0

        state = load_state(state_path, args.size, args.human, args.renju)

        if args.start_game:
            state = start_game(state)
            save_state(state_path, state)
            print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
            return 0

        if args.codex_move:
            row, col = args.codex_move
            state = apply_move(state, row, col, state["codex_player"])
            save_state(state_path, state)
            print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
            return 0

        if args.gui:
            run_gui(state_path, args.size, args.human, args.renju)
            return 0

        print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
        return 0
    except GomokuError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
