---
name: world-simulator
description: Run a persistent Codex-managed single-player world RPG with a browser Studio, free-form play, an inspectable world ledger, and complete durable turn history. Use when the user wants an interactive world simulator, original worldbuilding followed by play, a narrative sandbox, a solo RPG, or a persistent fictional world whose characters, factions, locations, tensions, relations, consequences, and hidden GM state continue across turns.
---

# World Simulator

Build a substantial world with the user, then perform it as a continuing narrative RPG. Codex owns interpretation, invention, staging, narration, characters, and state changes. Python only stores, retrieves, validates, commits, and displays records; never turn it into a story engine.

## Run the Session

From this skill directory, start a new Studio session:

```bash
python scripts/world_simulator.py start
```

Keep the server alive. It creates `world-runs/<stable-id>/world.sqlite3`, writes the active-session marker, and opens the browser UI. Give the printed local URL to the user if the browser does not open.

Resume a known session without creating another:

```bash
python scripts/world_simulator.py start --session <stable-id>
```

After the UI opens, world revisions and play input belong in the browser so the chronicle remains complete.

## Keep the Controller Attached

Treat an active world session as ongoing work, not as a background service that is complete once the server and an input waiter exist. A waiting process cannot wake Codex or author the next turn by itself.

- Do not send a final response while the session is active. Use commentary for brief operational updates and remain in the tool loop.
- Keep exactly one `next` waiter for the active session. When execution yields a continuation or session handle instead of turn JSON, retain that handle and poll it until input arrives. Do not launch another waiter merely because a poll returned no output.
- When browser input arrives, process and commit it, remove the temporary bundle, and immediately return to `next` without yielding the conversation back as complete.
- Treat chat messages received during the run as control or development messages. Address them, then resume the same waiter unless the user explicitly ends the world session.
- After an interruption, resume the known waiter handle when possible. If it cannot be resumed, inspect the exact world-simulator processes, stop only the stale `next` waiter, and create one replacement. Keep the Studio server alive.
- Never report “waiting” in a final response. Only an explicit request to end the session authorizes stopping the waiter and server and then sending the final handoff.

## Process Every Turn

Repeat until the user ends the session:

1. Wait for and claim the next browser input while remaining attached to the command:

   ```bash
   python scripts/world_simulator.py next
   ```

2. Read `references/turn-contract.md` and the guide for the current turn:
   - `references/world-compiler.md` for `studio` and `begin`
   - `references/scene-director.md` for `play`
3. Use the focus records and complete world index to interpret the turn. Inspect any record whose full truth matters:

   ```bash
   python scripts/world_simulator.py inspect "<id, name, or text>"
   ```

4. Author one `TurnBundle`: the visible response plus every resulting change.
5. Commit it atomically:

   ```bash
   python scripts/world_simulator.py commit <turn-bundle.json>
   ```

6. Remove the temporary bundle and immediately return to the single `next` waiter. The story response belongs in the browser, not chat.

If commit fails, correct the same bundle and retry the same turn.

## Direct Studio

Turn incomplete or highly specific ideas into a broad setting that can sustain play. Use the World Compiler's creative selection pass before authoring canon; a coherent first idea is not automatically the most compelling direction. Establish enough of the chosen world up front for later developments to have causes and alternatives.

The world remains editable. Revise established records and add newly encountered detail as play changes or expands the setting.

For `begin`, apply any final adjustment, switch the session to Play, and perform the opening situation in the same bundle.

## Direct Play

Treat input as free action, speech, intent, or inquiry. Do not generate the next passage by merely continuing the last passage. Understand the attempt, consult the world, compare plausible developments, choose and stage one that is both earned by the situation and worth playing, let narrator and characters perform it, then persist the consequences.

Keep the hidden director's judgment, the narrator's prose persona, and each character's roleplay distinct. Never expose GM-only truth.

## Keep the Ledger Authoritative

- Store canonical world data in English. Preserve raw user input and write visible responses and `presentation` data in the user's language and script.
- Use stable lowercase IDs. Patch existing records instead of cloning them under new names.
- Keep secrets in `gm` or `visibility: "gm"`; keep player-visible truth in `public`.
- Use relations for durable connections and entity fields for an entity's own current state.
- Record only events that will remain causally useful.
- Preserve player agency. Show consequences without inventing unsubmitted player choices, dialogue, beliefs, or emotions.
- Do not create command vocabularies, choice menus, hidden dice, timers, or deterministic narrative rules.
- Keep optional visuals inside the session `assets/` directory and localize their alt text and captions.

`status` reports storage metadata. `inspect` is a GM diagnostic and may contain secrets.

When the user ends the session, stop the persistent server. There is no in-world stop command.
