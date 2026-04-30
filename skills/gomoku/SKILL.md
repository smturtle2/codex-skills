---
name: gomoku
description: Play Gomoku with a human user through a Python/Pygame board while Codex chooses its own moves from the script's Codex view output. Use when the user wants to play 오목/Gomoku/Five-in-a-row against Codex, launch a local Python GUI game board, inspect the board position, apply Codex moves, reset the game, or maintain a Codex-vs-user Gomoku session without building a fixed AI engine.
---

# Gomoku

Run a local Python/Pygame Gomoku board for the user while Codex waits through the bundled script, reasons from the script's 1-based Codex view, and applies its next move through the bundled script.

Do not read the raw state file for move selection. Use `--codex-view` or `--wait-for-codex-turn` output.

## Dependency Handling

The GUI script depends on `pygame>=2.6`. If launching the GUI fails because `pygame` is missing, install `pygame` into the active Python environment and retry the same command. Do not ask the user to install dependencies unless the automated install fails or the environment blocks package installation.

## Quick Start

Start the GUI from the project root:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --state .codex-gomoku/state.json
```

Use this command when Codex needs the current position for move selection:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --state .codex-gomoku/state.json --codex-view
```

Wait until the board reaches Codex's turn:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --state .codex-gomoku/state.json --wait-for-codex-turn
```

Start a configured game from the command line when needed:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --state .codex-gomoku/state.json --start-game
```

Apply Codex's move after choosing a coordinate:

```bash
python3 skills/gomoku/scripts/gomoku_gui.py --state .codex-gomoku/state.json --codex-move 8 8
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
5. When the wait command returns JSON, choose Codex's move from that 1-based Codex view. Do not open or parse the raw state file.
6. Run `--codex-move <row> <col>` with the chosen 1-based coordinate.
7. Run `--wait-for-codex-turn` again and repeat until `winner` or `draw` is set in the state.

If the GUI is already running, it watches the state file and refreshes after Codex applies a move.

## Move Selection Guidance

When selecting Codex's move, use normal Gomoku tactical priorities:

- Win immediately if Codex has a completing move.
- Block an immediate human win.
- Create or extend open fours, then block human open fours.
- Create or block strong open threes.
- Prefer central, connected moves when no forcing move exists.
- Avoid isolated edge moves unless they address a concrete threat.

The script validates only board legality and win conditions. Codex is responsible for strategic choice.

## Commands

- `--codex-view`: print Codex's preferred 1-based coordinate summary without the raw board matrix.
- `--start-game`: mark setup complete so moves and Codex waiting can begin.
- `--codex-move ROW COL`: place Codex's configured stone color, save state, and exit.
- `--wait-for-codex-turn`: block until setup is complete and it is Codex's turn, or until the game ends, then print Codex view JSON and exit.
- `--reset`: overwrite the state file with a new game and exit.
- `--state PATH`: choose the state JSON path. Default is `.codex-gomoku/state.json`.
- `--size N`: board size for new games. Default is `15`.
- `--human black|white`: human player color for new games. Default is `black`.
- `--renju`: enable Renju restrictions for black.

## Codex View Contract

Use `--codex-view` and `--wait-for-codex-turn` output for move selection. This is the required board-reading interface for Codex during normal play. Both use 1-based coordinates matching the GUI and `--codex-move`.

- `black`: black stones as `[[row, col], ...]`.
- `white`: white stones as `[[row, col], ...]`.
- `legal_moves`: legal moves as `[[row, col], ...]`, with Renju forbidden moves excluded.
- `moves`: move history as `[[player, row, col], ...]`.
- `last_move`: last move object with 1-based `row`, `col`, and `player`.
- The raw `board` matrix is intentionally omitted to avoid zero-based indexing mistakes.

## Rules

Default rules are simple Gomoku: black moves first after setup, no forbidden-move restrictions, and five or more connected stones wins. When Renju is enabled, black must make exactly five to win and black overline, double-three, and double-four moves are forbidden; white still wins with five or more.

## Response

When starting or continuing a game, report:

- the GUI command or state path in use
- whether it is the user's turn or Codex's turn
- Codex's chosen move when applying one
- the winner or draw status when the game ends

Use commentary updates while the game is active. Use a final response only after the game is over, the GUI is closed, or the user asks to stop testing.
