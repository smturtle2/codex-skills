---
name: world-simulator
description: Create and run persistent free-form world simulation sessions through a local Python GUI where all story input is submitted from the GUI, Codex acts as the world manager/GM, builds the world from a user concept, creates or helps create the player character, advances the story as serial novel-like prose from open-ended user actions without menu choices, and updates visible world state, hidden GM notes, foreshadowing, faction clocks, consequences, and turn logs every turn. Use when the user wants an interactive world simulator, narrative sandbox, RPG-like story manager, persistent fictional world, or Codex-managed worldbuilding session with local visualization and durable session files.
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
- The skill contract and reference procedures are the source of truth. The Python script is a deterministic bridge for input, rendering, persistence, and validation; it must stay aligned with the skill, not define world-manager behavior by itself.
- During skill development or live testing, every UI behavior change must update both the bundled script and the skill contract/reference files. Do not treat script-only fixes as complete.

## Commands

Create a new temporary session skeleton from the project root:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --init-session
```

Publish the Codex-authored initial GUI output:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --publish-output <payload.json>
```

Launch the GUI for that auto-created session:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --gui --session <auto-created-session-slug-or-path>
```

The `--session` value above is an internal handle read from the `--init-session` status output, not something to ask from the user. When that handle is a temporary `pending-world-*` session, the web GUI follows the active session after `--rename-session` instead of staying pinned to the old temporary path. The default GUI backend is the local browser HUD served by Python. Use `--backend qt` or `--backend tk` only as fallback. To resume a known existing final session, Codex may add `--session <existing-session-slug-or-path>`.

Wait indefinitely for the next GUI-submitted input:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --wait-for-input
```

Inspect session status:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --status
```

Publish a Codex-authored GUI output payload:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --publish-output <payload.json>
```

Rename the temporary session after the first world concept is processed:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --rename-session <world-derived-session-name>
```

Use `--root <dir>` to store sessions somewhere other than `world-runs/`.

Do not ask the user to choose a session name. When `--session` is omitted, `--gui` and `--init-session` create a new temporary `pending-world-*` session and record it as the active session. Bridge commands without `--session` use that active session. After the first GUI world concept gives the world enough identity, Codex must choose a concise public world-derived session name and run `--rename-session` before publishing the first world output. Use `--session <existing-session-slug-or-path>` only when Codex is explicitly resuming or recovering a known existing session.

The script must not publish a built-in starting prompt, default story text, default status content, or language-specific template. For a cold start, Codex must author the initial GUI output from scratch in the current user language and publish it with `--publish-output` before the GUI is shown to the user or before waiting for user input. That initial payload defines `language`, `history_entry`, `status_sections`, `ui_theme`, `status_message`, and `input_enabled`.

## Session Flow

1. Create a temporary session skeleton with `--init-session`; read the returned `session_path` or `session_id`.
2. Publish a Codex-authored initial GUI output from scratch in the current user language. Do not use a reusable text template for this.
3. Launch the GUI for that auto-created session and tell the user the window is ready.
4. Run `--wait-for-input` and keep it blocking until the user submits from the GUI.
5. When the wait command returns JSON, read the session files before writing any story response.
6. If this is the first input, create the world from the user's concept, derive a concise public session name from that world, and rename the temporary session before publishing the world output.
7. Set the active user language from the latest GUI input and keep all user-visible output in that language.
8. If the phase is character creation, create or refine the player character from the user's GUI input. If the user asks for a random character, generate narrative randomness yourself; do not use code RNG for story content.
9. If the latest GUI input starts with `/show `, treat the remaining text as a display request and publish an inline `illustration` block in `history_entry.blocks`. Do not interpret it as a character action.
10. If the phase is play, advance the story from the user's open-ended action.
11. Update `current/`, `world/`, `player/`, `story/`, `gm/`, and `turns/` as needed.
12. Publish `ui/latest_output.json` through `--publish-output`.
13. Immediately start `--wait-for-input` again while the session is active.

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

- `History` shows the visible story as serial prose plus inline illustrations when a display is requested or Codex judges one is useful. It must read like a continuing novel scene, not a system log, bullet recap, status dump, outcome report, or GM note.
- `Status` shows compact world-specific playable state written by Codex.
- `Input` is a multiline free-form text box with a submit command.
- A compact `?` help control must be available near the input controls. It explains command mechanics such as `/show` and exposes saved display images without adding story choices.
- After submission, the GUI must visibly show that Codex is processing.
- Submitted text must remain visible while Codex is processing and clear only when the next input is available.
- Do not hardcode RPG stats or genre-specific fields in the GUI.
- Do not add story action buttons.
- Display requests use the exact text command prefix `/show `. The GUI submits the command like any other input; Codex handles the meaning and the GUI renders the resulting inline history illustration.
- Render the interface as a lightweight world HUD, not a generic form. The HUD identity must come from `ui_theme`, not from hardcoded genre decoration.
- Do not use lined-paper, notebook, parchment, or ruled backgrounds unless explicitly requested.
- Keep the layout stable while letting `ui_theme` control color, labels, icons, processing copy, and tone.
- Do not show literal turn counters such as `Turn 3` or `턴 3` in the main HUD. Keep `turn_id` for files and synchronization; use scene labels or visual grouping for user-facing separation.
- When the user asks for a light theme without further palette details, prefer clean white, blue, cyan, and slate tones. Do not interpret light theme as beige, cream, parchment, or warm paper unless the user or world concept calls for it.
- Match `ui_theme` to the active world concept every time Codex publishes output.

The status panel should read like a role-playing game player status screen by default, but every stat, resource, skill, condition, and objective label must be derived from the active world concept. Codex controls the content; the GUI only provides the status-screen grammar.

Status sections must be decision-useful and player-centered. The first completed-player section with `kind: "player"` must read as the player's RPG character status screen reskinned through the active world concept. It is not a generic summary card. It should expose the player character's current identity, role, condition, usable capabilities, constraints, player-attached immediate risks, resources carried by or bound to the player, and unresolved objectives selected from the current world state. Avoid pure lore summaries in the status panel.

The player status HUD must not carry global world symptoms, faction clocks, scene danger, or setting exposition as if they were player resources. Put those in separate `world`, `threat`, `clock`, or `scene` sections. If a player character does not exist yet, publish a `setup` section for character creation instead of a fake `player` HUD with world meters.

Status ordering contract:

- Put player character state first as the main RPG status HUD: name, role/archetype, current condition, player-bound variables, capabilities, weaknesses, objectives, and resources attached to the character.
- For the first `kind: "player"` section, generate a world-specific character sheet. Use `title` for the character name, callsign, or current identity; `subtitle` for the world's equivalent of class, role, rank, origin, faction, or archetype; `summary` for one current-status line; `meters` for character-bound resources or burdens; `vitals` for the most important current condition slots; `stats` for world-specific abilities or attributes; `groups` for skills, equipment, powers, conditions, objectives, relationships, permissions, or other character-sheet categories; `fields` only for short secondary slots; and `tags` for short flags.
- The `kind: "player"` section must feel like opening the character sheet for this specific world. Rename every resource, attribute, skill, item, condition, and objective into the world's own vocabulary.
- After player state, show only concrete in-world stakes that currently affect play. Name them by what they are in the fiction, not by generic GM terms.
- Use meters only when they track a named world condition, resource, objective, relationship, or clock. The section title and fields must make clear why the meter matters.
- Put scene facts and inventory after player state and any concrete active stake.
- Keep status values short enough to scan during play.
- Never force one universal schema (`HP`, `MP`, `STR`, `class`, `level`) unless the active world actually uses those concepts. Use the RPG status-screen grammar, but choose only the resources, attributes, skills, equipment, conditions, and objectives that fit the current world.

History prose contract:

- Write in the active user language.
- Treat `type: "prose"` as the main story text. It must read like a novel continuing from the previous visible scene.
- Advance the story through scene action, sensory detail, character perception, dialogue, implication, and consequence. Do not merely announce the result of the user's input.
- Keep the player character's viewpoint or immediate dramatic focus clear unless the current world intentionally uses another narrative viewpoint.
- Show consequences in the fiction before summarizing them. If a door opens, an NPC reacts, a wound worsens, a clue appears, or a clock advances, render what the character notices first.
- Use exposition only when it is anchored to the current scene: an object, spoken line, memory, inscription, rumor, or visible change.
- "Newly visible content" means the next readable passage of the serial scene, not a synopsis of what changed.
- Publish only the newly visible content for the current turn in `history_entry.blocks`. Do not resend the full accumulated history in `latest_output.json`.
- `history_entry.blocks` is an ordered array. Use `type: "prose"` for narrative prose and `type: "illustration"` for inline maps, diagrams, portraits, records, sheets, or other visual displays.
- The Python bridge appends or upserts `history_entry` into `ui/history_log.json`; the GUI renders that cumulative log.
- Treat `ui/history_log.json` as display history, not as the context Codex must reread every turn. Maintain compact playable context in `current/` and durable story summaries in `story/`.
- Treat illustration images as user-visible history assets, not automatic Codex context. Codex must not inspect raw image pixels on later turns unless the current turn explicitly requires visual confirmation, reuse validation, correction, or user-requested display handling.
- Separate visible turns through structured history entry metadata, not literal turn labels inside prose.
- Use dialogue lines and selective `**bold**` emphasis to make speech, stakes, discoveries, and important sensory details easy to scan.
- Do not overuse emphasis. Bold only what changes the user's reading of the scene or immediate decision.
- Do not use bold as a ledger marker, heading, outcome label, stat change, or status callout inside prose. Bold may emphasize words already embedded in a natural sentence or dialogue line.
- Do not put hidden GM truth, file-management commentary, schema labels, operational status, status recaps, or raw mechanics in `history_entry.blocks`.
- Do not write ledger prose such as "You succeed", "The result is", "Status updated", "Current objective", or "Available actions" unless those words are part of in-world speech, signage, documents, or interface fiction.
- Do not use menu choices or numbered actions.
- End in a live situation where the user can freely act.
- Keep mechanical facts in `status_sections`; keep story experience and inline illustrations in `history_entry.blocks`.
- `status_sections` is the compact HUD for scan-ready state: condition, resources, objectives, risks, inventory, clocks, and scene facts. Do not restate the HUD as prose in History unless the information is being experienced by a character in the scene.
- Use `history_entry.label` only for short scene or beat labels. Prose blocks must not say `Turn N` or `턴 N` unless a character literally says it.
- For `/show` display requests, publish a `history_entry` with an inline `illustration` block. Omit prose blocks unless the display request itself changes the visible scene. Store display handling notes in turn files, not visible story prose.

## UI Theme Contract

Every `latest_output.json` payload must include `language` and `ui_theme`.

`language` is the active user-facing language for the published output. User-visible `history_entry.blocks` text, `history_entry.label`, `status_sections`, `status_message`, and all `ui_theme` text fields must use that language.

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
- `open_image_label`
- `download_image_label`

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

## Inline Illustration Contract

When the user submits `/show MESSAGE`, Codex must:

- Read the current session state before deciding what to show.
- Treat `MESSAGE` as a request for a visible artifact, reference, diagram, sheet, map, note, record, or other world-appropriate display.
- Before generating a new image, Codex must run a display-reuse check: read `ui/display_assets.json`, compare saved displays against the request and current player-visible canon, and reuse a saved `image_path` when it still satisfies the request.
- The Python script only records and renders reusable assets. It must not be treated as the reuse policy, semantic matcher, or source of story truth.
- For visual display requests, use the `image-creator` skill to generate or edit a raster image and save it under the session `assets/` directory before publishing the history entry.
- The image prompt must describe the requested display content directly: subject, visible structure, labels, known locations, relative positions, player knowledge, visual tone, and established setting limits.
- The generated image is shown inline in `History`, not in a `/show` popup.
- Publish the requested display as a `history_entry.blocks[]` item with `type: "illustration"`, `image_path`, localized `title`, optional `caption`, `source: "user_show"`, `codex_visibility: "manual_only"`, and `display_asset` metadata for future Codex reuse checks.
- When reusing a saved display, publish a new inline illustration block with the existing `image_path`, localized title, and current context instead of invoking image generation.
- Every inline illustration `image_path` under `assets/` is a reusable candidate. Codex-authored `display_asset` metadata should describe the request, subject, purpose, visible canon scope, visual summary, and reuse key without hidden information. The script records that metadata in `ui/display_assets.json`. The default web GUI help panel must let the user reopen or download saved display images; fallback backends must at least list reusable image paths.
- Keep hidden GM-only truth out of the illustration and its metadata unless the player has earned that information.
- Keep the current story state stable unless the display request itself reasonably changes what the character does in-world.
- Persist any durable generated artifact under `assets/`, `world/`, `player/`, or `story/` as appropriate.

Codex may also add `source: "codex_initiated"` illustration blocks without a `/show` request when a visual artifact materially improves play: a newly important map, diagram, portrait, document, creature, device, clue layout, or spatial relationship that is likely to be reused.

Codex must write enough public `display_asset.visual_summary` metadata to reason about the asset later without looking at the raw image. On later turns, Codex may inspect the raw image only when the current turn requires visual confirmation, reuse validation, correction, or user-requested display handling.

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
