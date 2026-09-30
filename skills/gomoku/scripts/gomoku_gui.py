#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pygame>=2.6"]
# ///
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

from gomoku_rules import BLACK, EMPTY, WHITE, RuleEvaluator, existing_lines, freeze
from gomoku_session import (
    GomokuError, MAX_BOARD_SIZE, MIN_BOARD_SIZE, NEXT_PLAYER, PLAYER_TO_VALUE,
    adjust_settings, apply_move, codex_move, gui_session, is_codex_wait_ready,
    load_state, mutate_state, new_state, normalized_state, position_token,
    require_position, reset_game, save_state, settings_editable, start_game,
    validate_state_shape, wait_for_codex_turn,
)

MIN_WINDOW_WIDTH = 560
MIN_WINDOW_HEIGHT = 620
DEFAULT_STATE_PATH = pathlib.Path(".codex-skills/gomoku/default/state.json")


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
    state = normalized_state(state)
    return {
        "game_id": state["game_id"],
        "revision": state["revision"],
        "session_status": state["session_status"],
        "size": state["size"],
        "next_player": state["next_player"],
        "codex_player": state["codex_player"],
        "human_player": state["human_player"],
        "renju_rules": state.get("renju_rules", False),
        "setup_complete": state.get("setup_complete", False),
        "game_event_id": state.get("game_event_id", 0),
        "ascii_board": ascii_board(state),
        "winner": state.get("winner"),
        "winning_line": [[item["row"], item["col"]] for item in state.get("winning_line", [])],
        "draw": state.get("draw", False),
    }


def coords_payload(coords):
    return [[row + 1, col + 1] for row, col in coords]


def threat_view_payload(state: dict[str, Any]) -> dict[str, Any]:
    state = normalized_state(state)
    payload = codex_view_payload(state)
    evaluator = RuleEvaluator(state["renju_rules"])
    payload["tactical_facts"] = {
        player: tactical_facts_for_player(state, player, evaluator)
        for player in ("black", "white")
    }
    return payload


def tactical_facts_for_player(state, player, evaluator=None):
    evaluator = evaluator or RuleEvaluator(state["renju_rules"])
    board, value = freeze(state["board"]), PLAYER_TO_VALUE[player]
    completions = []
    for (row, col), assessment in evaluator.completions(board, value):
        fact = {"row": row + 1, "col": col + 1, "kind": "five_completion"}
        if not assessment.legal:
            fact.update(forbidden=True, reason=assessment.violation)
        if assessment.winning_line:
            fact["line"] = coords_payload(assessment.winning_line)
        completions.append(fact)
    fours, threes = evaluator.threats(board, value)
    lines = []
    for four in fours:
        contiguous = all((b[0] - a[0], b[1] - a[1]) == four.direction
                         for a, b in zip(four.stones, four.stones[1:]))
        kind = ("open_four" if four.straight else "half_open_four") if contiguous else "broken_four"
        fact = {"kind": kind, "stones": coords_payload(four.stones),
                "direction": list(four.direction), "completion_points": coords_payload(four.completions)}
        if contiguous:
            fact["open_ends"] = coords_payload(four.completions)
        lines.append(fact)
    for three in threes:
        lines.append({"kind": "open_three", "stones": coords_payload(three.stones),
                      "direction": list(three.direction), "extension_points": coords_payload(three.extensions)})
    for direction, stones in existing_lines(board, value, state["renju_rules"]):
        lines.append({"kind": "existing_five", "stones": coords_payload(stones), "direction": list(direction)})
    ordering = {"existing_five": 0, "open_four": 1, "broken_four": 2, "half_open_four": 3, "open_three": 4}
    lines.sort(key=lambda fact: (ordering[fact["kind"]], fact["stones"], fact["direction"]))
    return {"completion_points": completions, "lines": lines}


def run_gui(state_path: pathlib.Path, size: int, human_player: str, renju_rules: bool) -> None:
    try:
        import pygame
    except ImportError as exc:
        raise SystemExit("pygame is required for the GUI. Install pygame in the active Python environment.") from exc

    pygame.init()
    try:
        with gui_session(state_path, size, human_player, renju_rules) as state:
            run_window(pygame, state_path, state)
    finally:
        pygame.quit()


def run_window(pygame, state_path, state):
    """UI events express transitions against the latest locked state."""
    cell, margin, status_height = 38, 48, 78
    screen = pygame.display.set_mode(window_size(state["size"], cell, margin, status_height))
    pygame.display.set_caption("Gomoku")
    font = pygame.font.SysFont("arial", 18)
    small_font = pygame.font.SysFont("arial", 14)
    title_font = pygame.font.SysFont("arial", 28)
    clock = pygame.time.Clock()
    notice = None
    running = True
    while running:
        state = load_state(state_path)
        board_size = state["size"]
        desired = window_size(board_size, cell, margin, status_height)
        if desired != screen.get_size():
            screen = pygame.display.set_mode(desired)
        screen_mode = screen_mode_for_state(state)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                state = mutate_state(state_path, reset_game)
                notice = None
            elif event.type == pygame.KEYDOWN and settings_editable(state):
                state = mutate_state(state_path, lambda current: handle_settings_key(event.key, current))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if screen_mode == "settings":
                    action = settings_screen_action_at(event.pos, *screen.get_size())
                    if action:
                        state = mutate_state(state_path, lambda current: adjust_settings(current, action))
                    continue
                move = pixel_to_move(event.pos, board_size, cell, margin)
                if (move and state["setup_complete"] and state["next_player"] == state["human_player"]
                        and not state["winner"] and not state["draw"]):
                    expected = position_token(state)
                    def human_move(current):
                        require_position(current, *expected)
                        return apply_move(current, *move, current["human_player"])
                    try:
                        state = mutate_state(state_path, human_move)
                        notice = None
                    except GomokuError as error:
                        notice = str(error)
                        state = load_state(state_path)
        if not running:
            break
        desired = window_size(state["size"], cell, margin, status_height)
        if desired != screen.get_size():
            screen = pygame.display.set_mode(desired)
        if screen_mode_for_state(state) == "settings":
            draw_settings_screen(screen, state, title_font, font, small_font)
        else:
            draw(screen, state, cell, margin, status_height, font, small_font, notice)
        pygame.display.flip()
        clock.tick(30)


def screen_mode_for_state(state: dict[str, Any]) -> str:
    return "game" if state.get("setup_complete", False) else "settings"


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


def draw(screen: Any, state: dict[str, Any], cell: int, margin: int, status_height: int, font: Any, small_font: Any, notice: str | None = None) -> None:
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
    draw_text_clipped(screen, notice or hint_text(state), small_font, (210, 210, 210), (20, board_bottom + 40), width - 40)


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
    parser.add_argument("--run-dir", type=pathlib.Path, help="Game workspace; stores state.json here. Use a distinct folder per session. Overrides GOMOKU_STATE_PATH; without either, uses .codex-skills/gomoku/default.")
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
    parser.add_argument(
        "--threat-view",
        action="store_true",
        help="Print opt-in tactical facts without scores, recommendations, raw board, or move history.",
    )
    parser.add_argument("--reset", action="store_true", help="Reset the game and exit.")
    parser.add_argument("--start-game", action="store_true", help="Mark setup complete and start the current game.")
    parser.add_argument("--codex-move", nargs=2, type=int, metavar=("ROW", "COL"), help="Apply Codex's configured move using 1-based coordinates.")
    parser.add_argument("--game-id", help="For --codex-move, the game_id from the view used to select the move.")
    parser.add_argument("--revision", type=int, help="For --codex-move, the revision from that same view.")
    parser.add_argument(
        "--wait-for-codex-turn",
        action="store_true",
        help="Wait for Codex's turn, game end, or GUI closure, then print Codex view JSON.",
    )
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args(argv)
    if args.codex_move and (not args.game_id or args.revision is None):
        parser.error("--codex-move requires --game-id and --revision from its selection view")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    state_path = (
        args.run_dir / "state.json"
        if args.run_dir is not None
        else pathlib.Path(os.environ.get("GOMOKU_STATE_PATH", DEFAULT_STATE_PATH))
    ).expanduser()
    try:
        if args.reset:
            mutate_state(state_path, lambda state: reset_game(state, args.size, args.human, args.renju),
                         args.size, args.human, args.renju)
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

        if args.start_game:
            state = mutate_state(state_path, start_game, args.size, args.human, args.renju)
            print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
            return 0

        if args.codex_move:
            row, col = args.codex_move
            state = codex_move(state_path, row, col, args.game_id, args.revision)
            print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
            return 0

        if args.gui:
            run_gui(state_path, args.size, args.human, args.renju)
            return 0

        state = load_state(state_path, args.size, args.human, args.renju)
        if args.threat_view:
            print(json.dumps(threat_view_payload(state), indent=2, sort_keys=True))
            return 0

        print(json.dumps(codex_view_payload(state), indent=2, sort_keys=True))
        return 0
    except (GomokuError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
