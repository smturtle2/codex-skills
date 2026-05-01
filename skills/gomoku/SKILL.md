---
name: gomoku
description: Play Gomoku with a human user through a Python/Pygame board while Codex chooses its own moves from the script's Codex view output. Use when the user wants to play 오목/Gomoku/Five-in-a-row against Codex, launch a local Python GUI game board, inspect the board position, apply Codex moves, reset the game, or maintain a Codex-vs-user Gomoku session without building a fixed AI engine.
---

# Gomoku

Run a local Python/Pygame Gomoku board for the user while Codex waits through the bundled script, reads the script's 1-based Codex view, and applies its next move through the bundled script.

Do not read, choose, or mention the backing storage during normal play. Use the default Codex view JSON or `--wait-for-codex-turn` output.

## Dependency Handling

The GUI script depends on `pygame>=2.6`. If launching the GUI fails because `pygame` is missing, install `pygame` into the active Python environment and retry the same command. Do not ask the user to install dependencies unless the automated install fails or the environment blocks package installation.

## Quick Start

Start the GUI from the project root:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --gui
```

Use this command when Codex needs the current position for move selection:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py
```

Wait until the board reaches Codex's turn:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --wait-for-codex-turn
```

Start a configured game from the command line when needed:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --start-game
```

Apply Codex's move after choosing a coordinate:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --codex-move 8 8
```

Coordinates are 1-based as `row col`, matching the labels shown in the GUI.

## Waiting Rules

Waiting behavior is the most important part of this skill.

- Start or restart `--wait-for-codex-turn` immediately after the GUI opens, after `Start Game`, and after every Codex move.
- Keep the wait command running while it is the user's turn. Do not ask the user to say they moved.
- Do not send a final response while a game is active and Codex is supposed to be waiting.
- Only stop waiting when the wait command returns, the game ends, the GUI is closed, or the user explicitly stops the session.
- Settings changes are not game events. The wait command should only wake for actual game events: game start, user move, Codex turn, win, or draw.
- After applying a Codex move, immediately start the next wait command before giving any closing-style response.

## Game Flow

1. Launch the GUI and tell the user the board is ready.
2. New games open on the settings screen. Let the user choose settings there; the game does not start from setting changes alone.
3. Wait for the user to click `Start Game`, or run `--start-game` only when the user explicitly wants to begin with the current settings.
4. Run `--wait-for-codex-turn` and leave it blocking while the user plays on the GUI. Waiting only wakes after the game has started.
5. When the wait command returns JSON, choose Codex's move from that 1-based Codex view. Do not open or parse the backing JSON.
6. Run `--codex-move <row> <col>` with the chosen 1-based coordinate.
7. Run `--wait-for-codex-turn` again and repeat until `winner` or `draw` is set in the state.

If the GUI is already running, it refreshes after Codex applies a move.

## Move Selection Guidance

During an active game, do not write or run custom Gomoku AI, search, or scoring code to choose a move. Read the Codex view JSON and choose the move directly from these priorities.

Before considering Codex's attack, scan the human threats:

1. Win immediately if Codex has a legal completing move.
2. Find every legal human move that would make five next turn, then block one of those squares unless Renju makes it unplayable for the human.
3. Scan human open fours, half-open fours, open threes, compound threats, and repeated line patterns before considering Codex's own extensions.
4. Prefer Codex moves that force a response only after the human threats are covered.
5. Reject any move that leaves a larger human threat unanswered.

Evaluate fours by both length and open ends. An open four is urgent, a half-open four is situational, and a four with both ends blocked is low value even though four stones are connected.

Scan globally when the human spreads out. If human stones repeat on a row, column, or diagonal with regular spacing, ladder/step geometry, or a wide grid-like pattern, prioritize the middle gaps, connection points, and extension points that would complete that pattern. Do not treat these as ordinary isolated edge moves.

Limit candidates to moves near the last move, all active threat lines, and central connection points. If the human is playing distant repeated patterns or multiple separated lines, make a full row/column/diagonal scan before choosing.

The script validates only board legality and win conditions. Codex is responsible for strategic choice.

## Commands

- no action flag: print the current Codex view JSON.
- `--gui`: launch the Pygame board.
- `--codex-view`: backward-compatible alias for the default Codex view output.
- `--start-game`: mark setup complete so moves and Codex waiting can begin.
- `--codex-move ROW COL`: place Codex's configured stone color, save state, and exit.
- `--wait-for-codex-turn`: block until setup is complete and it is Codex's turn, or until the game ends, then print Codex view JSON and exit.
- `--reset`: reset the game and exit.
- `--size N`: board size for new games. Default is `15`.
- `--human black|white`: human player color for new games. Default is `black`.
- `--renju`: enable Renju restrictions for black.

## Codex View Contract

Use the default command, `--codex-view`, or `--wait-for-codex-turn` output for move selection. The Codex-facing board view is `ascii_board`.

- `ascii_board`: a 1-based coordinate board for visual reading. `B` is black, `W` is white, `b` is the last black move, `w` is the last white move, and `.` is empty.
- All displayed coordinates are 1-based and match the GUI and `--codex-move`.
- The JSON output also includes game status metadata such as size, players, turn, winner, draw, and winning line when available.
- The raw `board` matrix, full legal move list, full move history, threat summaries, line analysis, scores, and move recommendations are intentionally omitted.

## Rules

Default rules are simple Gomoku: black moves first after setup, no forbidden-move restrictions, and five or more connected stones wins. When Renju is enabled, black must make exactly five to win and black overline, double-three, and double-four moves are forbidden; white still wins with five or more.

## Response

When starting or continuing a game, report:

- the GUI command in use
- whether it is the user's turn or Codex's turn
- Codex's chosen move when applying one
- the winner or draw status when the game ends

Use commentary updates while the game is active. Use a final response only after the game is over, the GUI is closed, or the user asks to stop testing.
