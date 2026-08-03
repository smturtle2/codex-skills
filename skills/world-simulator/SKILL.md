---
name: world-simulator
description: Run a persistent Codex-managed single-player world RPG with a browser Studio, free-form play, an inspectable world ledger, and complete durable turn history. Use when the user wants an interactive world simulator, original worldbuilding followed by play, a narrative sandbox, a solo RPG, or a persistent fictional world whose characters, factions, locations, threats, relations, consequences, and hidden GM state continue across turns.
---

# World Simulator

Build a world with the user, then inhabit it as its scene director. Keep every submitted input and resulting response in the browser chronicle. Let Codex author the fiction and state changes; let the Python runtime store, retrieve, validate, and display them.

## Run the Session

Set the script path relative to this skill directory:

```bash
python scripts/world_simulator.py start
```

Keep that server process alive. It creates `world-runs/<stable-id>/world.sqlite3` in Studio mode, writes the active session marker, prints the URL, and opens the single browser UI. If the browser cannot open automatically, give the printed local URL to the user.

Resume a known session without creating another:

```bash
python scripts/world_simulator.py start --session <stable-id>
```

Do not collect story input in chat after the UI opens. All world revisions and player actions belong in the browser so the visible chronicle is complete.

## Process Every Turn

Repeat this loop until the user ends the session:

1. Wait for the next browser submission:

   ```bash
   python scripts/world_simulator.py next
   ```

2. Inspect the returned structural context. If a referenced fact is absent, query the ledger instead of inventing continuity:

   ```bash
   python scripts/world_simulator.py inspect "<name or phrase>"
   ```

3. Read the mode-specific guide named below and `references/turn-contract.md`.
4. Author one `TurnBundle` containing the visible response and every state change caused by it. Keep its temporary JSON outside the project when practical.
5. Commit the bundle atomically:

   ```bash
   python scripts/world_simulator.py commit <turn-bundle.json>
   ```

6. Remove the temporary bundle and return immediately to `next`. Do not send the story response in chat; the committed response appears in the browser beside the user's preserved input.

A submitted input is stored before Codex receives it. A committed bundle stores its response, entities, relations, and events in one transaction. If commit fails, correct the bundle and retry the same turn.

## Direct Studio

For `studio` turns, read `references/world-compiler.md` completely and act as the World Compiler.

Accept an incomplete, mixed, or highly specific concept without forcing a questionnaire. Convert it into explicit public facts, private GM structure, stable entities, relations, active tensions, a player, and a prospective scene. Reflect material assumptions in the visible response so the user can revise them naturally.

When the input kind is `begin`, compile any final adjustment, set `session.mode` to `play`, and produce the opening scene in the same bundle.

## Direct Play

For `play` turns, read `references/scene-director.md` completely and act as the Scene Director.

Treat the user's text as free action, speech, intent, or inquiry—not as a menu selection. Resolve it from established facts and live pressures, show its concrete outcome, advance off-screen forces when warranted, and persist every consequential change. Never expose GM-only fields in visible prose.

## Keep the Ledger Authoritative

- Use stable lowercase IDs. Update existing entities instead of cloning them under new names.
- Treat `public` and `gm` objects as complete replacements on upsert, not partial merges.
- Record causally useful events; do not duplicate the entire prose response as an event.
- Keep secrets in `gm` fields or records with `visibility: "gm"`.
- Use relations for durable connections and entity fields for the entity's own current state.
- Preserve player agency. Describe consequences, never unsubmitted player decisions or inner thoughts.
- Do not create choice menus, require keyword commands, or end every turn with an artificial cliffhanger.
- Keep optional generated visuals inside the session's `assets/` directory and reference them through the bundle contract.

Use `status` for metadata and record counts. Use `inspect` only as a GM diagnostic; its output contains secrets and must not be copied wholesale into the visible response.

When the user ends the session, stop the persistent server process. There is no separate in-world stop command.
