---
name: world-simulator
description: Build and play a persistent single-player world RPG in a browser, with free-form actions, evolving characters, and durable world history. Use for interactive worldbuilding and continuing narrative play.
---

# World Simulator

Codex authors the world, narration, characters, and consequences. Python only stores, retrieves, validates, commits, and displays them; do not turn it into a story engine.

Set `SKILL_DIR` to this skill's absolute directory. Run from the session project; storage defaults to `world-runs/`. For an existing world, keep its original storage root and pass `--root <root>` consistently if the working directory differs.

## Start or Resume

```bash
uv run --no-project python "$SKILL_DIR/scripts/world_simulator.py" start
```

Add `--session <stable-id>` to resume rather than create another world. Keep the server process alive and give the printed local URL if the browser does not open. Once open, world revisions and play input belong in the browser so the chronicle remains complete.

## Process Turns

1. Wait for and claim browser input:

   ```bash
   uv run --no-project python "$SKILL_DIR/scripts/world_simulator.py" next
   ```

2. Load [references/turn-contract.md](references/turn-contract.md) when its data contract is absent from context. Use [references/world-compiler.md](references/world-compiler.md) for `studio`/`begin` or [references/scene-director.md](references/scene-director.md) for `play`; reread on mode changes or context loss, not mechanically every turn.
3. Use focus records and the complete index. Retrieve missing facts that affect the turn with `inspect "<id, name, or text>"` through the same CLI.
4. Author one TurnBundle containing the visible response and all resulting state changes.
5. Commit it atomically:

   ```bash
   uv run --no-project python "$SKILL_DIR/scripts/world_simulator.py" commit <turn-bundle.json>
   ```

6. Remove the temporary bundle after success and return immediately to `next`. On commit failure, correct the bundle and retry the same claimed turn.

## Stay Attached

Keep exactly one `next` waiter. Retain and poll yielded process/session handles; a background process alone cannot wake Codex to author the next turn.

Use commentary for operational updates while the session is active, without a final “waiting” handoff. Address chat messages as control/development input, then resume the same waiter unless the user ends the session.

After interruption, resume the known handle; if unusable, stop only the identified stale waiter and replace it while preserving the server. On explicit session end, stop the waiter and server before the final handoff. If the server fails, report the failure and retained session location instead of claiming continued play.

## World Invariants

- Keep canonical data in English and raw user input unchanged. Write visible responses and `presentation` in the user's language.
- Patch stable IDs instead of cloning records. Use relations for durable connections and events for causally useful history.
- Keep secrets in `gm` or GM-only records. `inspect` may expose secrets and is not player-facing output.
- Preserve player agency: never invent unsubmitted choices, dialogue, beliefs, or emotions.
- Do not add command vocabularies, choice menus, hidden dice, timers, or deterministic narrative rules.
- Store optional visuals under the session's `assets/` with localized captions and alt text.

Use `status` for storage metadata. Story responses belong in the browser; the final session handoff should identify the retained world and any unresolved operational issue.
