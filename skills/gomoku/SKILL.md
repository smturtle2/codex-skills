---
name: gomoku
description: Play 오목/Gomoku against the user on a local GUI board, with Codex choosing moves and maintaining the live game session. Use for playing or resuming a game, not building a game engine.
---

# Gomoku

Codex chooses moves; the Python/Pygame helper displays the board and validates legality. During play, do not write or run an AI search/scoring engine or read the backing storage. Use the helper's Codex view.

Set `SKILL_DIR` to this skill's absolute directory and run from the session project. The script declares its pygame dependency for uv.

## Start and Play

Launch the GUI:

```bash
uv run --script "$SKILL_DIR/scripts/gomoku_gui.py" --gui
```

New games open on settings. Let the user choose them and click Start Game; use `--start-game` only when the user explicitly requests starting with the current settings. Settings changes alone do not start play.

Repeat the turn loop:

1. Wait for the game to start and Codex's turn:

   ```bash
   uv run --script "$SKILL_DIR/scripts/gomoku_gui.py" --wait-for-codex-turn
   ```

2. Read the returned status and `ascii_board`. If the game ended, report the winner or draw.
3. Before choosing a move, read [references/tactics.md](references/tactics.md) if not already in context, then inspect tactical facts:

   ```bash
   uv run --script "$SKILL_DIR/scripts/gomoku_gui.py" --threat-view
   ```

4. Choose a legal move from the visible board and those facts, then apply it:

   ```bash
   uv run --script "$SKILL_DIR/scripts/gomoku_gui.py" --codex-move <row> <col>
   ```

5. Immediately start the next wait.

Coordinates are always 1-based `row col`. In `ascii_board`, `B/W` are stones, `b/w` mark the last move, and `.` is empty.

## Maintain the Session

Keep the waiter attached during the user's turn, including after GUI launch and each Codex move. Retain and poll a yielded session handle instead of launching duplicate waiters or asking the user to announce a move.

Use commentary for operational updates and chosen moves. Do not send a final response while the game is active; finish after game end, GUI closure, or explicit user stop. Address intervening control messages and resume the existing wait when play continues.

If a move is rejected, refresh the Codex view and select a legal move from the current state. Do not bypass validation. If the GUI or helper cannot run, report its error rather than claim the board is ready.

## Other Operations

No action flag prints the current Codex view; `--codex-view` is its alias. Use `--reset` only for a requested reset. New-game options are `--size N` (default 15), `--human black|white` (default black), and `--renju`.

Report whose turn it is, the chosen move when applied, and the final game result. Keep implementation details out of routine play unless needed to explain a problem.
