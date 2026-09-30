# Move Selection

Use during Codex move selection; retain these rules in context rather than rereading every turn.

## Tactical Facts

`--threat-view` supplements the ordinary board view. It is a factual checklist, not move ordering or a recommendation engine:

- `tactical_facts.black` and `tactical_facts.white` describe visible board patterns.
- `completion_points` gives 1-based completing moves; forbidden black completions include `forbidden` and `reason`.
- `lines` includes `open_four`, `half_open_four`, `broken_four`, `open_three`, and `existing_five`. Four facts carry their actual `completion_points`; threes carry legal `extension_points` to a straight four. Runs with no winning completion are omitted.
- A four is identified by its four stones, so its two completing ends count as one four. Separate fours can share a direction. Renju threes are included only when an extension is legal, including recursively checking forbidden double-threes; an apparent three blocked by an overline or another forbidden extension is omitted.
- Ordering is deterministic, not strategic. The view intentionally excludes scores, recommended moves, search depth, raw matrices, legal-move catalogs, and move history.

## Choose a Move

1. Take a legal immediate win if available.
2. Check every opponent completion point and block immediate wins, accounting for Renju-forbidden black moves.
3. Inspect open/broken/half-open fours, open threes, compound threats, and repeated line patterns before pursuing an attack.
4. Prefer forcing moves after covering opponent threats; reject moves leaving a greater threat unanswered.

Judge fours by their completing ends as well as length: open fours are urgent, and half-open fours depend on context.

Consider the last move, all active threat lines, and central connection points. When stones form distant repeated, ladder, regularly spaced, or grid-like patterns, scan the whole board's rows, columns, and diagonals for gaps and connecting moves; do not dismiss them as isolated edge stones.

The helper establishes legality and wins, not strategy. Codex remains responsible for its choice.

## Rule Modes

Simple Gomoku: black moves first; five or more connected stones wins, with no forbidden moves.

Renju restrictions: black wins by exactly five; an attained five takes precedence over a simultaneous overline or other forbidden pattern. Without that five, overlines, true double-threes, and double-fours are forbidden for black. Only threats meeting at the played intersection count toward a double threat. White wins with five or more. The helper uses the [RIF definitions and rules 9.1–9.3](https://www.renju.net/rifrules/) for these restrictions; board settings and opening play remain freely configurable. Follow the helper's current legality results.

Choose from one returned view and retain its `game_id` and `revision` for `--codex-move`. A stale selection is rejected; refresh the view before choosing again. A `closed` session status ends the wait without discarding resumable state.
