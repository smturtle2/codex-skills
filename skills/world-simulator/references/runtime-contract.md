# Runtime Contract

This reference defines the durable session and GUI bridge contract for `world-simulator`.

## Session Root

Default root:

```text
world-runs/
```

Default session path:

```text
world-runs/<session-slug>/
```

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
- `history_markdown`: user-visible markdown string.
- `status_sections`: array.
- `input_enabled`: boolean.
- `status_message`: string.
- `ui_theme`: object.

Optional fields:

- `popup`: object describing an in-browser HUD popup display authored by Codex.

`status_sections` item contract:

- `title`: required string.
- `body`: optional string or string array.
- `kind`: optional string used for visual grouping. Use `player` for an existing player character. Use `setup` before the character exists. Other useful values include `world`, `clock`, `threat`, `resource`, `relationship`, `objective`, `scene`, `inventory`, or another concise world-appropriate kind.
- `icon`: optional string chosen by Codex for the active world.
- `subtitle`: optional string. For `kind: player`, use this for role, archetype, class, calling, or social identity.
- `summary`: optional string. For `kind: player`, use this for the current status line.
- `vitals`: optional array of label/value/tone objects. For `kind: player`, use this for the most important current condition, player-bound variable, carried resource, or objective.
- `stats`: optional array of label/value/tone objects. For `kind: player`, use this for world-specific abilities, attributes, ratings, or affinities.
- `groups`: optional array of titled item groups. For `kind: player`, use this for concept-specific skills, equipment, status conditions, objectives, relationships, or powers.
- `fields`: optional array of label/value objects.
- `tags`: optional array of short state strings.
- `meters`: optional array of bounded numeric progress objects.

`popup` object contract:

- `id`: required string. Change it whenever a new popup should open.
- `title`: required string.
- `markdown`: optional user-visible markdown string.
- `kind`: optional visual grouping string. The GUI may expose it as a CSS class but must not infer world meaning from it.
- `image_path`: optional local file path under the session `assets/` directory. For `/show` visual materials, this should normally be a raster image produced through the `image-creator` skill.
- `caption`: optional string shown with the popup content.

At least one of `markdown`, `image_path`, or `caption` must be present. All user-visible popup text must use the active `language`.

The web GUI renders `popup` inside the current browser page as a modal HUD panel.

Generated `image_path` assets are the visual content shown inside that panel.

The GUI renders each section without interpreting genre-specific fields.

`kind: player` is a role-playing player status HUD, not a plain info card. Its structure should remain recognizable across worlds while its labels and values change by world. Use `title`, `subtitle`, `summary`, `meters`, `stats`, `groups`, `fields`, and `tags` to represent the player character. Do not require a universal stat list.

Player/world separation contract:

- `kind: player` describes the player character only: identity, role, condition, abilities, resources, equipment, relationships, current objectives, and player-affecting statuses.
- Do not put global world symptoms, faction clocks, scene danger, or setting exposition inside `kind: player` unless they are explicitly attached to the player character.
- Before character creation is complete, use `kind: setup` for missing character fields and `kind: world` or `kind: scene` for world information.
- World or scene meters may exist, but they must live in non-player sections and be titled as concrete in-world facts.

RPG grammar contract:

- The GUI may present profile, resource bars, attribute tiles, grouped slots, tags, and conditions.
- Codex must choose the actual labels from the current world concept.
- Do not always include every container. Publish only the containers that make sense for the current world and current scene.
- Do not publish universal video-game labels (`HP`, `MP`, `STR`, `class`, `level`) unless the active world actually uses those concepts.

Do not publish generic GM tension labels as visible section titles. Represent the concrete in-world thing causing tension: a curse spreading, oxygen running out, a faction becoming suspicious, a debt coming due, a door seal failing, or a relationship fraying.

Language contract:

- Codex sets `language` from the latest GUI-submitted user language unless the user explicitly requests another.
- `history_markdown`, `status_sections`, `status_message`, and all `ui_theme` text fields must use `language`.
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

## CLI Contract

Launch or resume a GUI:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --gui --session <session-slug>
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
python3 skills/world-simulator/scripts/world_simulator_gui.py --init-session --session <session-slug>
```

Print session status:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --status --session <session-slug>
```

Wait indefinitely for a GUI input that does not yet have matching output:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --wait-for-input --session <session-slug>
```

Publish output:

```bash
python3 skills/world-simulator/scripts/world_simulator_gui.py --publish-output <payload.json> --session <session-slug>
```

All commands accept:

```bash
--root <session-root>
```

The default root is `world-runs/`.

## Atomicity and Recovery

- JSON bridge files must be written through a temporary file followed by rename.
- `--wait-for-input` must not time out.
- A pending input remains processable until `latest_output.json.turn_id` is greater than or equal to `pending_input.json.turn_id`.
- `input_ack.json` indicates that Codex has seen an input; it does not make the input unprocessable.
- On restart, run `--status`, read the session files, then continue from the latest pending input or latest output.
- The GUI may preserve draft text in `gui_state.json`, but draft text is not a story turn until submitted.
- During processing, the GUI preserves submitted input text. It clears that text only after a matching or newer output is available and input is enabled again.

## Output Rules

`history_markdown` must contain user-visible narrative prose. It should read like an unfolding scene, not a system log, status recap, schema dump, or GM note.

`history_markdown` may include concise scene headings, dialogue, selective `**bold**` emphasis, and short paragraph breaks. It must not include numbered action menus, hidden GM truth, file-management commentary, operational status, or literal turn labels used only for UI separation.

Optional `history_turns` contract:

- `history_turns`: array of visible turn objects.
- `history_turns[].turn_id`: required integer.
- `history_turns[].label`: optional short UI label.
- `history_turns[].markdown`: required user-visible narrative prose.

When `history_turns` is present, the GUI renders turn separation as UI chrome. The `markdown` field remains pure prose.

Do not show literal turn counters such as `Turn 3` or `턴 3` in the main HUD. `turn_id` is for file synchronization, not player-facing flavor.

`status_sections` must be compact, playable, and player-centered. Each update should make the user's current situation easier to read: player identity, role, world-specific abilities, resources, equipment, conditions, constraints, concrete active stakes, and unresolved objectives must be represented when relevant to the world.

Order `status_sections` by play use: player RPG status HUD first, concrete active stakes second when they matter now, current scene third, inventory/supporting details after that. Keep entries short and HUD-like.

`input_enabled` should normally be `true` after Codex publishes an output. Set it to `false` only for terminal states, unrecoverable errors, or explicit pause states.

Never copy `gm/` file contents directly into `latest_output.json`.
