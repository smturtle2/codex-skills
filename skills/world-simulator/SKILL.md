---
name: world-simulator
description: Create and run persistent free-form world simulation sessions through a local Python GUI where all story input is submitted from the GUI, Codex acts as the world manager/GM, builds the world from a user concept, creates or helps create the player character, advances the story from open-ended user actions without menu choices, and updates visible world state, hidden GM notes, foreshadowing, faction clocks, consequences, and turn logs every turn. Use when the user wants an interactive world simulator, narrative sandbox, RPG-like story manager, persistent fictional world, or Codex-managed worldbuilding session with local visualization and durable session files.
---

# World Simulator

Run a persistent free-form world simulation where Codex is the world manager and the bundled Python GUI is only the visual input/output bridge.

The GUI must stay minimal and world-agnostic. Codex defines each world's status content, hidden GM state, foreshadowing, factions, and consequences according to the user's concept.

## Core Contract

- All story input must come from the Python GUI. Do not ask the user to type in chat for world concepts, character setup, or in-world actions.
- Use chat only for operational status, errors, and session control.
- The Python script must not create story content, decide outcomes, define world rules, or generate random characters.
- Codex may expand the world, but must not overwrite established canon.
- Do not present story choices or action buttons. The user acts through free-form text.
- User-visible story, status, prompts, labels, and chat operations must follow the active user language. The active language is the latest GUI-submitted language unless the user explicitly requests another.
- Codex must define the visible GUI tone through `ui_theme`; the script must render that theme without making genre decisions.
- Persist state to files every turn. Do not rely on conversation memory as the source of truth.
- Keep `gm/` private to Codex. Never render hidden GM files directly in the GUI.
- During skill development or live testing, every UI behavior change must update both the bundled script and the skill contract/reference files. Do not treat script-only fixes as complete.

## Commands

Start or resume the GUI from the project root:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --gui --session <session-slug>
```

The default GUI backend is the local browser HUD served by Python. Use `--backend qt` or `--backend tk` only as fallback.

Wait indefinitely for the next GUI-submitted input:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --wait-for-input --session <session-slug>
```

Inspect session status:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --status --session <session-slug>
```

Publish a Codex-authored GUI output payload:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --publish-output <payload.json> --session <session-slug>
```

Use `--root <dir>` to store sessions somewhere other than `world-runs/`.

## Session Flow

1. Launch the GUI and tell the user the window is ready.
2. Run `--wait-for-input` and keep it blocking until the user submits from the GUI.
3. When the wait command returns JSON, read the session files before writing any story response.
4. If this is the first input, create the world from the user's concept.
5. Set the active user language from the latest GUI input and keep all user-visible output in that language.
6. If the phase is character creation, create or refine the player character from the user's GUI input. If the user asks for a random character, generate narrative randomness yourself; do not use code RNG for story content.
7. If the latest GUI input starts with `/show `, treat the remaining text as a display request and publish a `popup` object. Do not interpret it as a character action.
8. If the phase is play, advance the story from the user's open-ended action.
9. Update `current/`, `world/`, `player/`, `story/`, `gm/`, and `turns/` as needed.
10. Publish `ui/latest_output.json` through `--publish-output`.
11. Immediately start `--wait-for-input` again while the session is active.

Do not send a final response while an active session is waiting for the user unless the GUI is closed, the user stops the session, or you are only reporting an operational failure.

## Directory Model

The top-level session directories are stable; files inside them are flexible:

- `current/`: short current context Codex rereads first every turn.
- `world/`: world canon, tone, laws, places, factions, cultures, magic, technology, or equivalent setting material.
- `player/`: player character information appropriate to the world.
- `story/`: public story progress, known threads, discovered facts, and visible history.
- `gm/`: Codex-only secrets, foreshadowing, faction plans, hidden truths, and delayed consequences.
- `turns/`: append-only turn records, usually numbered as `0001/`, `0002/`, and so on.
- `ui/`: machine-readable GUI bridge files.
- `assets/`: optional maps, images, references, or generated materials.

Only `ui/` has a strict machine contract. Use flexible Markdown, YAML, JSON, or text files elsewhere, choosing names that make the world easy for Codex to inspect.

Read [references/runtime-contract.md](references/runtime-contract.md) for the GUI and file bridge contract. Read [references/gm-procedure.md](references/gm-procedure.md) before creating a world, character, or turn update.

## GUI Requirements

Use the bundled GUI as a quiet writing console:

```text
history | status
input
```

- `History` shows the visible story as narrative prose. It must read like an unfolding scene, not a system log, bullet recap, status dump, or GM note.
- `Status` shows compact world-specific playable state written by Codex.
- `Input` is a multiline free-form text box with a submit command.
- After submission, the GUI must visibly show that Codex is processing.
- Submitted text must remain visible while Codex is processing and clear only when the next input is available.
- Do not hardcode RPG stats or genre-specific fields in the GUI.
- Do not add story action buttons.
- Display requests use the exact text command prefix `/show `. The GUI submits the command like any other input; Codex handles the meaning and the GUI only renders the resulting `popup` payload.
- Render the interface as a lightweight world HUD, not a generic form. The HUD identity must come from `ui_theme`, not from hardcoded genre decoration.
- Do not use lined-paper, notebook, parchment, or ruled backgrounds unless explicitly requested.
- Keep the layout stable while letting `ui_theme` control color, labels, icons, processing copy, and tone.
- Do not show literal turn counters such as `Turn 3` or `턴 3` in the main HUD. Keep `turn_id` for files and synchronization; use scene labels or visual grouping for user-facing separation.
- When the user asks for a light theme without further palette details, prefer clean white, blue, cyan, and slate tones. Do not interpret light theme as beige, cream, parchment, or warm paper unless the user or world concept calls for it.
- Match `ui_theme` to the active world concept every time Codex publishes output.

The status panel should read like a role-playing game player status screen by default, but every stat, resource, skill, condition, and objective label must be derived from the active world concept. Codex controls the content; the GUI only provides the status-screen grammar.

Status sections must be decision-useful and player-centered. They should expose the player character's current identity, role, condition, usable capabilities, constraints, player-attached immediate risks, resources carried by or bound to the player, and unresolved objectives selected from the current world state. Avoid pure lore summaries in the status panel.

The player status HUD must not carry global world symptoms, faction clocks, scene danger, or setting exposition as if they were player resources. Put those in separate `world`, `threat`, `clock`, or `scene` sections. If a player character does not exist yet, publish a `setup` section for character creation instead of a fake `player` HUD with world meters.

Status ordering contract:

- Put player character state first as the main RPG status HUD: name, role/archetype, current condition, player-bound variables, capabilities, weaknesses, objectives, and resources attached to the character.
- For the first `player` section, use `subtitle` for role/archetype, `summary` for the current status line, `meters` for world-specific resources, `stats` for world-specific abilities/attributes, `groups` for concept-specific skills/equipment/conditions/objectives, and `tags` for short flags.
- After player state, show only concrete in-world stakes that currently affect play. Name them by what they are in the fiction, not by generic GM terms.
- Use meters only when they track a named world condition, resource, objective, relationship, or clock. The section title and fields must make clear why the meter matters.
- Put scene facts and inventory after player state and any concrete active stake.
- Keep status values short enough to scan during play.
- Use RPG status-screen structure generally, but never force one universal schema (`HP`, `MP`, `STR`). Choose only the resources, attributes, skills, equipment, conditions, and objectives that fit the current world, and rename them in the world's own vocabulary.

History prose contract:

- Write in the active user language.
- Prefer immersive scene narration, sensory detail, character stakes, consequences, and dialogue when appropriate.
- Separate visible turns through structured UI turn metadata, not literal turn labels inside prose.
- Use dialogue lines and selective `**bold**` emphasis to make speech, stakes, discoveries, and important sensory details easy to scan.
- Do not overuse emphasis. Bold only what changes the user's reading of the scene or immediate decision.
- Do not put hidden GM truth, file-management commentary, schema labels, or operational status in `history_markdown`.
- Do not use menu choices or numbered actions.
- End in a live situation where the user can freely act.
- Keep mechanical facts in `status_sections`; keep story experience in `history_markdown`.
- If the UI needs turn separation, publish `history_turns` with `turn_id`, optional `label`, and `markdown`. The prose inside each turn must not say `턴 N` unless a character literally says it.
- For `/show` display requests, keep `history_markdown` on the current scene. Store display handling notes in turn files, not in visible story prose.

## UI Theme Contract

Every `latest_output.json` payload must include `language` and `ui_theme`.

`language` is the active user-facing language for the published output. `history_markdown`, `status_sections`, `status_message`, and all `ui_theme` text fields must use that language.

Required `ui_theme` fields:

- `title`: top bar title.
- `history_title`: left panel label.
- `status_title`: right panel label.
- `input_title`: input panel label.
- `input_placeholder`: input box placeholder.
- `send_label`: submit button label.
- `processing_message`: short processing badge text.
- `processing_detail`: one-line processing explanation.
- `palette`: color object for the active world tone.

Optional `ui_theme` fields:

- `header_icon`
- `history_icon`
- `status_icon`
- `input_icon`
- `input_hint`
- `popup_close_label`

`palette` keys:

- `app_background`
- `panel_background`
- `status_background`
- `input_background`
- `text`
- `muted_text`
- `accent`
- `accent_2`
- `border`
- `selection`
- `button_text`
- `disabled_background`
- `disabled_text`

Use emojis only when they match the world concept and improve scanning. Do not use them as decoration.

## Processing UI Contract

The GUI processing state is mandatory.

- When the user submits input, keep the submitted text visible in the input box.
- While `pending_input.turn_id` is greater than `latest_output.turn_id`, make the input read-only, disable the submit command, and show a clear processing badge or banner.
- When Codex publishes a matching or newer `latest_output.turn_id` with `input_enabled: true`, clear the submitted input, restore focus, and return to the normal send label.
- The processing text must follow the active user language and current world tone through `ui_theme`.

## Popup Contract

When the user submits `/show MESSAGE`, Codex must:

- Read the current session state before deciding what to show.
- Treat `MESSAGE` as a request for a visible artifact, reference, diagram, sheet, map, note, record, or other world-appropriate display.
- For visual display requests, use the `image-creator` skill to generate or edit a raster image and save it under the session `assets/` directory before publishing the popup.
- The image prompt must describe the requested display content directly: subject, visible structure, labels, known locations, relative positions, player knowledge, visual tone, and established setting limits.
- The generated image is the content shown inside the GUI popup.
- Publish the requested display in `latest_output.json.popup`, usually with `image_path` pointing at the generated asset and `markdown` or `caption` giving only necessary context.
- Keep hidden GM-only truth out of the popup unless the player has earned that information.
- Keep the current story state stable unless the display request itself reasonably changes what the character does in-world.
- Persist any durable generated artifact under `assets/`, `world/`, `player/`, or `story/` as appropriate.

The web GUI renders `popup` as a clean in-HUD popup panel over the current browser page. Codex authors the meaning of `MESSAGE`; the Python script renders the authored payload.

## Waiting Rules

Waiting behavior is mandatory.

- Start `--wait-for-input` after launching the GUI and after every Codex output.
- Keep the wait command running while it is the user's turn.
- Never impose a time limit on user input.
- Do not ask the user to confirm in chat that they submitted input.
- The wait command should only wake for GUI-submitted input that has not yet received a corresponding Codex output.
- If Codex or the terminal restarts, inspect `--status` and resume from the session files instead of starting over.

## World Consistency

Before every turn, read the current session state. Treat established facts as canon.

- Hard canon and world laws must not be contradicted.
- Undefined areas may be expanded when the new details fit the concept, tone, and established limits.
- User input that violates the setting should be resolved through existing rules, costs, failure, partial success, misunderstanding, or consequences.
- Every new fact introduced during play must be written back to the appropriate session directory.
- Hidden truths may stay hidden, but they must remain consistent with public facts.

## Response

When operating a session, report only concise operational updates in chat:

- the GUI command in use
- the active session path or slug
- whether Codex is waiting, processing, or publishing output
- any recovery action if the session state is inconsistent

Keep story prose in the GUI output and session files, not in the chat response.
