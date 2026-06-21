# Runtime Contract

This reference defines the durable session and GUI bridge contract for `world-simulator`.

## Session Root

Default root:

```text
world-runs/
```

Default temporary session path:

```text
world-runs/pending-world-YYYYMMDD-HHMMSS[-NN]/
```

Final named session path after world creation:

```text
world-runs/<world-derived-session-slug>/
```

The CLI generates a temporary `pending-world-*` slug when `--session` is omitted for `--gui` or `--init-session`. Codex must not ask the user to choose a session name. After the first GUI-submitted world concept is processed, Codex chooses a concise public name from the created world and runs `--rename-session` to move the session to its final name. `--session` is reserved for resuming or recovering an existing session by known slug or explicit path.

The root may contain `.active_session.json`. This marker is maintained by the script and lets bridge commands operate on the current session when `--session` is omitted.

Required top-level directories:

```text
current/
world/
player/
story/
gm/
turns/
ui/
assets/
```

The directory names are stable. File names and internal schemas outside `ui/` are flexible. Codex should choose whatever files make the current world easiest to inspect and maintain.

## Directory Roles

- `current/`: short, rereadable session context. Keep it compact enough to read before every turn.
- `world/`: canon and setting material. Include world laws, tone, limits, factions, places, cultures, and other setting-specific documents as needed.
- `player/`: player character data. Use role-playing status concepts suited to the world; do not force one universal attribute list.
- `story/`: public narrative record. Keep visible progress, known facts, public threads, and discoveries here.
- `gm/`: Codex-only state. Store secrets, hidden truths, foreshadowing plans, faction clocks, delayed consequences, and private continuity notes here.
- `turns/`: append-only turn ledger. Each processed input should create or update a numbered turn directory.
- `ui/`: machine-readable bridge files used by the Python GUI and Codex.
- `assets/`: optional supporting files, maps, images, reference art, or generated visual material.

## UI Bridge Files

`ui/pending_input.json` is written by the GUI when the user submits input.

Required fields:

- `session_id`: string.
- `turn_id`: integer, monotonically increasing.
- `phase`: string.
- `text`: string.
- `created_at`: UTC timestamp string.

`ui/input_ack.json` is written by `--wait-for-input` when Codex receives a pending input.

Required fields:

- `session_id`: string.
- `turn_id`: integer matching the acknowledged input.
- `status`: string.
- `acknowledged_at`: UTC timestamp string.

`ui/latest_output.json` is written by Codex through `--publish-output`.

Required fields:

- `phase`: string.
- `turn_id`: integer matching the processed input.
- `language`: string identifying the active user-facing language.
- `status_sections`: array.
- `input_enabled`: boolean.
- `status_message`: string.
- `ui_theme`: object.

Optional fields:

- `history_entry`: object containing the newly visible ordered history blocks for this output. Required for story-advancing outputs, `/show` display requests, and Codex-initiated illustrations.
- `popup`: object reserved for non-story utility overlays. `/show` display requests must not use `popup`.

`history_entry` object contract:

- `blocks`: required ordered array of user-visible history blocks for this output only.
- `turn_id`: optional integer. Defaults to `latest_output.turn_id`.
- `id`: optional string. Defaults to `turn:<turn_id>`. Reusing an `id` replaces the existing cumulative history item instead of appending.
- `label`: optional short scene or beat label rendered as UI chrome.
- `phase`: optional string. Defaults to `latest_output.phase`.
- `created_at`: optional UTC timestamp string.

`history_entry.blocks` item contract:

- `type`: required string. Allowed values: `prose`, `illustration`.

`type: "prose"` block contract:

- `markdown`: required user-visible serial prose string. It must read like a novelistic scene passage or scene transition, not a log entry, recap, game ledger, outcome list, GM explanation, or status summary.
- The prose may include dialogue and sparse emphasis, but must not contain headings such as `Action`, `Result`, `Status`, `Quest`, `Turn`, or equivalent ledger labels unless they are diegetic text inside the world.

`type: "illustration"` block contract:

- `image_path`: required local file path under the session `assets/` directory.
- `asset_id`: optional stable public asset id. Defaults to `display_asset.reuse_key`, `id`, or `image_path`.
- `title`: optional localized title rendered above or below the image.
- `caption`: optional localized caption.
- `alt`: optional localized image alt text.
- `source`: optional string. Use `user_show` for `/show` requests and `codex_initiated` for Codex-authored interstitial illustrations.
- `codex_visibility`: required string. Must be `manual_only`. The bridge may default a missing value to `manual_only`; other values are invalid.
- `display_asset`: optional Codex-authored metadata object for future reuse checks. Use it when `image_path` is present.

The Codex-authored payload must not include the full accumulated history. The Python bridge records `history_entry` into `ui/history_log.json`.

`status_sections` item contract:

- `title`: required string.
- `body`: optional string or string array.
- `kind`: optional string used for visual grouping. Use `player` for an existing player character. Use `setup` before the character exists. Other useful values include `world`, `clock`, `threat`, `resource`, `relationship`, `objective`, `scene`, `inventory`, or another concise world-appropriate kind.
- `icon`: optional string chosen by Codex for the active world.
- `subtitle`: optional string. For `kind: "player"`, use this for role, archetype, class, calling, or social identity.
- `summary`: optional string. For `kind: "player"`, use this for the current status line.
- `vitals`: optional array of label/value/tone objects. For `kind: "player"`, use this for the most important current condition, player-bound variable, carried resource, or objective.
- `stats`: optional array of label/value/tone objects. For `kind: "player"`, use this for world-specific abilities, attributes, ratings, or affinities.
- `groups`: optional array of titled item groups. For `kind: "player"`, use this for concept-specific skills, equipment, status conditions, objectives, relationships, or powers.
- `fields`: optional array of label/value objects.
- `tags`: optional array of short state strings.
- `meters`: optional array of bounded numeric progress objects.

Status sections are compact HUD data, not prose scenes or lore summaries. Keep `body`, `summary`, `fields`, `groups`, and labels short enough to scan during play. Long explanation belongs in session files or, if experienced in-fiction, in `history_entry.blocks`.

`popup` object contract:

- `id`: required string. Change it whenever a new popup should open.
- `title`: required string.
- `markdown`: optional user-visible markdown string.
- `kind`: optional visual grouping string. The GUI may expose it as a CSS class but must not infer world meaning from it.
- `image_path`: optional local file path under the session `assets/` directory for utility overlays.
- `caption`: optional string shown with the popup content.
- `display_asset`: optional Codex-authored metadata object for future reuse checks. Use it when `image_path` is present.

At least one of `markdown`, `image_path`, or `caption` must be present. All user-visible popup text must use the active `language`.

The web GUI renders `popup` inside the current browser page as a modal HUD panel. Do not use this object for `/show`; `/show` uses inline history illustration blocks.

Generated `image_path` assets are the visual content shown inside that panel.

`display_asset` object fields:

- `request`: optional original `/show` request text without the command prefix.
- `subject`: optional concise subject of the displayed image.
- `purpose`: optional display type or use, such as map, sheet, record, diagram, portrait, or reference.
- `visible_scope`: optional short description of the player-visible facts represented by the image.
- `visual_summary`: optional public text summary of what the image visibly contains, written so Codex can reason about the asset later without inspecting raw image pixels.
- `reuse_key`: optional stable human-readable key Codex can use when comparing later display requests.
- `canon_refs`: optional array of public file names, turn ids, scene labels, or other public references used to make the image.
- `reuse_tags`: optional array of short public tags useful for future matching.
- `reuse_notes`: optional public note for future Codex reuse decisions.

`display_asset` must not contain hidden GM-only truth. The script may copy these fields into `ui/display_assets.json`, but it must not decide whether they semantically satisfy a later request.

The GUI renders each section without interpreting genre-specific fields.

`kind: "player"` is the player's RPG character status screen for the active world, not a plain info card or setting summary. It must feel like opening this world's character sheet. Its visual grammar should remain recognizable across worlds while every label and value is reskinned through the current world concept. Do not require a universal stat list.

`kind: "player"` field contract:

- `title`: the player character's name, callsign, public identity, disguise, or current identity.
- `subtitle`: the world's equivalent of class, role, rank, origin, faction, calling, social identity, or archetype.
- `summary`: one compact line describing current condition, leverage, vulnerability, or immediate constraint.
- `meters`: bounded player-bound resources, burdens, drives, wounds, stress, power reserves, access, reputation, corruption, or other character-attached tracks.
- `vitals`: the most important current condition slots that should be visible before detailed stats.
- `stats`: world-specific abilities, attributes, ratings, affinities, proficiencies, permissions, or competencies.
- `groups`: titled character-sheet categories such as skills, equipment, powers, spells, augmentations, conditions, objectives, relationships, debts, cover identities, or permissions.
- `fields`: short secondary slots only. Do not use `fields` as a dumping ground for lore.
- `tags`: short state flags that help scan the character sheet.

Player/world separation contract:

- `kind: "player"` describes the player character only: identity, role, condition, abilities, resources, equipment, relationships, current objectives, and player-affecting statuses.
- Do not put global world symptoms, faction clocks, scene danger, or setting exposition inside `kind: "player"` unless they are explicitly attached to the player character.
- Before character creation is complete, use `kind: setup` for missing character fields and `kind: world` or `kind: scene` for world information.
- World or scene meters may exist, but they must live in non-player sections and be titled as concrete in-world facts.

RPG grammar contract:

- The GUI may present profile, resource bars, attribute tiles, grouped slots, tags, and conditions.
- Codex must choose the actual labels from the current world concept.
- Do not always include every container. Publish only the containers that make sense for the current world and current scene.
- Do not publish universal video-game labels (`HP`, `MP`, `STR`, `class`, `level`) unless the active world actually uses those concepts.
- A valid `kind: "player"` section should be recognizable as a character status sheet even when the world is not fantasy, combat, or game-themed.

Do not publish generic GM tension labels as visible section titles. Represent the concrete in-world thing causing tension: a curse spreading, oxygen running out, a faction becoming suspicious, a debt coming due, a door seal failing, or a relationship fraying.

Language contract:

- Codex sets `language` from the latest GUI-submitted user language unless the user explicitly requests another.
- User-visible `history_entry.blocks` text, `history_entry.label`, `status_sections`, `status_message`, and all `ui_theme` text fields must use `language`.
- The GUI does not translate story or status content. Codex is responsible for publishing already-localized text.
- Internal bridge field names remain in English for machine stability.

`fields` item contract:

- `label`: required string.
- `value`: required string.
- `tone`: optional string. Allowed values: `neutral`, `good`, `warning`, `danger`.

`vitals` item contract:

- `label`: required string.
- `value`: required string.
- `tone`: optional string. Allowed values: `neutral`, `good`, `warning`, `danger`.

`stats` item contract:

- `label`: required string.
- `value`: required string or number.
- `tone`: optional string. Allowed values: `neutral`, `good`, `warning`, `danger`.

`groups` item contract:

- `title`: required string.
- `icon`: optional string.
- `items`: required array of label/value/tone objects.

`meters` item contract:

- `label`: required string.
- `value`: required number.
- `max`: required positive number.
- `tone`: optional string. Allowed values: `neutral`, `good`, `warning`, `danger`.

`ui_theme` contract:

- `title`: top bar title.
- `history_title`: left panel label.
- `status_title`: right panel label.
- `input_title`: input panel label.
- `input_placeholder`: input box placeholder.
- `send_label`: submit button label.
- `processing_message`: short processing badge text.
- `processing_detail`: one-line processing explanation.
- `input_hint`: optional short input instruction.
- `header_icon`: optional semantic icon.
- `history_icon`: optional semantic icon.
- `status_icon`: optional semantic icon.
- `input_icon`: optional semantic icon.
- `popup_close_label`: optional close-button label.
- `open_image_label`: optional popup action label for opening a popup image asset.
- `download_image_label`: optional popup action label for downloading a popup image asset.
- `palette`: required color object.

Required `palette` keys:

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

`ui/gui_state.json` is maintained by the GUI for draft text, next turn id, and display state. Codex should not treat it as world canon.

`ui/heartbeat.json` is maintained by the GUI while it is open.

`ui/history_log.json` is maintained by the script when Codex publishes `history_entry`.

Required fields:

- `session_id`: string.
- `version`: integer.
- `last_seq`: integer identifying the latest cumulative display sequence.
- `items`: array of cumulative visible history records.
- `updated_at`: UTC timestamp string.

`items` record fields:

- `seq`: integer display sequence assigned by the bridge.
- `id`: string. Usually `turn:<turn_id>`.
- `turn_id`: integer.
- `phase`: string.
- `label`: optional short UI label.
- `blocks`: ordered array of normalized `prose` and `illustration` blocks for that one output.
- `created_at`: UTC timestamp string for the first registry entry.
- `updated_at`: UTC timestamp string for the latest replacement.

Publishing a `history_entry` appends a new item unless an existing item has the same `id` or `turn_id`; in that case, the bridge replaces that item in place and preserves its `seq`. This makes retry and recovery idempotent.

`ui/history_log.json` is the GUI display source, not Codex's per-turn prompt source. Codex should read compact files in `current/`, plus relevant `world/`, `player/`, `story/`, and `gm/` files. It should not reread the full cumulative history every turn.

`ui/display_assets.json` is maintained by the script when Codex publishes an inline history illustration, or a non-story utility popup, with an `image_path` under the session `assets/` directory.

Required fields:

- `session_id`: string.
- `items`: array of reusable display image records.
- `updated_at`: UTC timestamp string.

`items` record fields:

- `id`: string. Usually the illustration `asset_id` or stable reuse key that first exposed or last refreshed the asset.
- `title`: string.
- `image_path`: string path under the session `assets/` directory, normalized relative to the session root.
- `caption`: optional string.
- `request`: optional original `/show` request text without the command prefix.
- `subject`: optional concise subject of the displayed image.
- `purpose`: optional display type or use.
- `visible_scope`: optional short description of the player-visible facts represented by the image.
- `visual_summary`: optional public text summary of the image content for later Codex reasoning without automatic raw image inspection.
- `reuse_key`: optional stable human-readable key for Codex's future comparison.
- `canon_refs`: optional array of public references used to make the image.
- `reuse_tags`: optional array of short public tags useful for future matching.
- `reuse_notes`: optional public note for future Codex reuse decisions.
- `turn_id`: integer identifying the latest output turn that exposed the asset.
- `created_at`: UTC timestamp string for the first registry entry.
- `last_seen_at`: UTC timestamp string for the latest publication that referenced the asset.

The registry is a reuse index, not world canon. It exists so Codex can find previously shown display images; it is not a semantic matcher, policy engine, or source of story truth.

During `/show` handling, Codex must read the registry before generating a new image and decide whether to reuse a saved `image_path` by comparing the request against current player-visible canon. Reuse is allowed only when the saved display still matches what the player can know and see. If the registry is empty, broken, stale, or semantically insufficient, Codex should generate or refresh the display instead.

The registry is the default Codex-readable representation of prior illustrations. Codex must not automatically inspect raw image pixels from `assets/` while preparing ordinary turns. Codex may inspect an illustration image only when the current turn requires visual confirmation, reuse validation, correction, or user-requested display handling; record that inspection reason in the turn notes.

The default web GUI may show registry items in command help and reopen or download their files. Fallback GUI backends must at least expose reusable image paths in help. No GUI backend may infer story meaning from registry fields or decide that a saved image satisfies a new `/show` request.

Missing, malformed, or invalid registry entries must not block the GUI. The script may ignore unusable records, including broken JSON, missing files, or paths outside `assets/`.

## CLI Contract

Launch a new GUI session:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --gui
```

The script creates only the session skeleton and GUI bridge files. It must not create a built-in language-specific starting prompt, story template, status template, or `ui/latest_output.json` content. Codex must infer the current user language from the conversation, author the initial GUI output from scratch, and publish it with `--publish-output` before waiting for the user's first GUI input. After the first GUI input, Codex sets `latest_output.json.language` from the latest GUI-submitted language unless the user explicitly requests another.

Resume a known existing GUI session:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --gui --session <existing-session-slug-or-path>
```

Default backend:

- `auto`: Python-served local browser HUD.

Fallback backends:

- `web`: explicitly use the local browser HUD.
- `qt`: PyQt6 desktop fallback.
- `tk`: Tk desktop fallback.

Web GUI options:

```bash
--host <host>
--port <port>
--no-open-browser
```

Create a session skeleton without opening a GUI:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --init-session
```

Print session status:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --status
```

Wait indefinitely for a GUI input that does not yet have matching output:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --wait-for-input
```

Publish output:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --publish-output <payload.json>
```

Rename the active temporary session after world creation:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --rename-session <world-derived-session-name>
```

For `--status`, `--wait-for-input`, and `--publish-output`, omitting `--session` uses `.active_session.json`. Codex may pass `--session <existing-session-slug-or-path>` for explicit recovery, parallel development sessions, or inspection of a non-active session, but this value is an operational handle and must not be requested from the user during normal play.

All commands accept:

```bash
--root <session-root>
```

The default root is `world-runs/`.

## Atomicity and Recovery

- JSON bridge files must be written through a temporary file followed by rename.
- `--gui` and `--init-session` without `--session` must create a fresh temporary `pending-world-*` session and update `.active_session.json`.
- `--gui` and `--init-session` must not write `ui/latest_output.json` automatically. Only `--publish-output` writes Codex-authored user-facing output.
- `--rename-session` must move the session directory, refresh bridge file `session_id` fields, and update `.active_session.json` to the final path.
- The web GUI must resolve the active session through `.active_session.json` on each request when launched without `--session` or when launched against a temporary `pending-world-*` session, so an already-open browser keeps working after rename.
- A `--gui --session pending-world-*` launch is an internal temporary handle, not a fixed resume target. After `--rename-session`, the web GUI must follow the renamed active session instead of recreating the old temporary directory.
- If `.active_session.json` already points to an existing final session, launching `--gui --session pending-world-*` must not overwrite that marker.
- Bridge commands without `--session` must use `.active_session.json`; if it is missing, they must fail with an operational error instead of asking the user for a session name.
- `--wait-for-input` must not time out.
- A pending input remains processable until `latest_output.json.turn_id` is greater than or equal to `pending_input.json.turn_id`.
- `input_ack.json` indicates that Codex has seen an input; it does not make the input unprocessable.
- `history_entry` publication updates `ui/history_log.json` through append-or-upsert semantics.
- On restart, run `--status`, read the session files, then continue from the latest pending input or latest output.
- The GUI may preserve draft text in `gui_state.json`, but draft text is not a story turn until submitted.
- During processing, the GUI preserves submitted input text. It clears that text only after a matching or newer output is available and input is enabled again.

## Output Rules

`history_entry.blocks` must contain newly visible content for the current output only. Prose blocks are the main fiction surface and must read like a continuing novel scene, not a system log, status recap, schema dump, outcome ledger, or GM note.

`type: "prose"` blocks may include concise scene headings, dialogue, selective `**bold**` emphasis, and short paragraph breaks. They must advance play through character perception, scene action, dialogue, sensory detail, and consequences visible in the fiction. They must not include numbered action menus, hidden GM truth, file-management commentary, operational status, raw mechanics, status recaps, or literal turn labels used only for UI separation.

Consequences must be rendered before they are abstracted. Do not publish prose that merely says an action succeeded, failed, updated an objective, changed a meter, advanced a clock, or unlocked an option. Show what the character sees, hears, feels, realizes, loses, gains, or is forced to face; put compact mechanical facts in `status_sections`.

`type: "illustration"` blocks are inline history displays. `/show` requests must publish illustration blocks, not popup payloads. Codex may also publish `source: "codex_initiated"` illustration blocks when a visual artifact materially improves play and is likely to be useful later.

Illustration blocks and their `display_asset` metadata must contain only player-visible information. Set or accept only `codex_visibility: "manual_only"`; raw image pixels are not automatic Codex context.

The GUI renders cumulative history from `ui/history_log.json`. The web GUI reads history through `GET /api/history?after_seq=N`, which returns records with `seq > N` plus `last_seq`; fallback GUI backends may render the full local history log.

Do not show literal turn counters such as `Turn 3` or `턴 3` in the main HUD. `turn_id` is for file synchronization, not player-facing flavor.

`status_sections` must be compact, playable, and player-centered. They support the prose; they must not replace it with a recap. The first completed-player `kind: "player"` section must be authored as a world-specific RPG character sheet. Each update should make the user's current situation easier to read: player identity, role, world-specific abilities, resources, equipment, conditions, constraints, concrete active stakes, and unresolved objectives must be represented when relevant to the world.

Order `status_sections` by play use: player RPG status HUD first, concrete active stakes second when they matter now, current scene third, inventory/supporting details after that. Keep entries short and HUD-like.

`input_enabled` should normally be `true` after Codex publishes an output. Set it to `false` only for terminal states, unrecoverable errors, or explicit pause states.

Never copy `gm/` file contents directly into `latest_output.json`.

The GUI must include a compact help control near the input controls. Help content is limited to command mechanics, including `/show MESSAGE`, and may list reusable display images from `ui/display_assets.json`. The default web GUI should provide open and download controls for saved display images; fallback backends may expose the same assets as text paths.
