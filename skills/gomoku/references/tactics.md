# Move Selection

Use during Codex move selection; retain these rules in context rather than rereading every turn.

## Tactical Facts

`--threat-view` supplements the ordinary board view. It is a factual checklist, not move ordering or a recommendation engine:

- `tactical_facts.black` and `tactical_facts.white` describe visible board patterns.
- `completion_points` gives 1-based completing moves; forbidden black completions include `forbidden` and `reason`.
- `lines` includes `open_four`, `half_open_four`, `closed_four`, `broken_four`, `open_three`, and `existing_five`.
- Ordering is deterministic, not strategic. The view intentionally excludes scores, recommended moves, search depth, raw matrices, legal-move catalogs, and move history.

## Choose a Move

1. Take a legal immediate win if available.
2. Check every opponent completion point and block immediate wins, accounting for Renju-forbidden black moves.
3. Inspect open/broken/half-open fours, open threes, compound threats, and repeated line patterns before pursuing an attack.
4. Prefer forcing moves after covering opponent threats; reject moves leaving a greater threat unanswered.

Judge fours by open ends as well as length: open fours are urgent, half-open fours depend on context, and closed fours have low value.

Consider the last move, all active threat lines, and central connection points. When stones form distant repeated, ladder, regularly spaced, or grid-like patterns, scan the whole board's rows, columns, and diagonals for gaps and connecting moves; do not dismiss them as isolated edge stones.

The helper establishes legality and wins, not strategy. Codex remains responsible for its choice.

## Rule Modes

Simple Gomoku: black moves first; five or more connected stones wins, with no forbidden moves.

Renju: black must make exactly five; overlines, double-threes, and double-fours are forbidden for black. White wins with five or more. Follow the helper's current legality results.
