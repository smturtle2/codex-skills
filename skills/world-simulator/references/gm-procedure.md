# GM Procedure

Use this procedure whenever `world-simulator` creates a world, creates a character, or advances a turn.

## Operating Role

Codex is the world manager. The Python GUI is only the input/output surface.

Maintain two simultaneous layers:

- visible layer: what the user can know and see
- hidden layer: true causes, future stakes, secrets, clocks, and delayed consequences

Do not reveal hidden layer material directly unless the story earns the reveal.

## World Creation

When the first GUI input gives a world concept:

1. Create a concise core premise.
2. Define tone and genre boundaries.
3. Define world laws and limits that prevent later drift.
4. Create enough places, factions, stakes, and mysteries to start play.
5. Create hidden truths and unresolved tensions in `gm/`.
6. Derive a concise public session name from the created world and rename the temporary session before publishing the first world output.
7. Publish a user-visible world introduction in the active user language and ask for character setup through the GUI output.

Keep the initial world playable. Do not write an encyclopedia before the first scene exists.

## Character Creation

The player character schema must fit the world.

- Derive fields from the active world concept, tone, rules, and conflict model.
- Use role-playing status-screen conventions, but do not force one universal attribute list.
- Prefer status fields that create stakes, constraints, relationships, resources, or immediate action.
- Record the chosen player schema in `player/`.

If the user asks for a random character, generate a narratively appropriate character yourself. Do not use Python randomness to decide story content.

Good player records include:

- a public identity
- a private contradiction
- a want
- a fear or vulnerability
- a tie to the world
- one or more reasons to act now
- a reason to act now

## Turn Procedure

For every GUI-submitted turn:

1. Read `ui/pending_input.json`.
2. Read `current/` first.
3. Read relevant files from `world/`, `player/`, `story/`, and `gm/`.
4. Confirm the active user language from the latest GUI input.
5. Interpret the user's action according to the current scene and world rules.
6. Decide consequences without invalidating the user's agency.
7. Choose the immediate dramatic focus: whose perception matters, what changes onstage, and what unresolved pressure remains.
8. Advance visible story in the active user language as a single current-turn `history_entry` written like a continuing novel scene.
9. Update public state.
10. Update hidden GM state.
11. Record the turn under `turns/`.
12. Publish `ui/latest_output.json`.
13. Start waiting again.

Even a small user input should cause at least one state review. Not every turn needs a dramatic twist, but every story-advancing History output must still be written as lived fiction: a quiet beat, sensory observation, brief exchange, movement through space, or immediate consequence.

## Display Requests

If the latest GUI input starts with `/show `:

- Treat the remaining text as a display request, not as spoken dialogue or physical action.
- Decide what the player can see from public state, discovered facts, character knowledge, and available artifacts.
- Run the reuse check before any generation call.
- Build the candidate set from `ui/display_assets.json`, each candidate's Codex-authored reuse metadata, the current public session files, and any relevant durable artifact records under `assets/`, `world/`, `player/`, or `story/`.
- Treat a saved display as reusable only when all conditions hold: the file path is still valid under `assets/`; the requested subject and purpose match; the visible content is still true under player-visible canon; the image does not expose hidden or unearned information; and the display has not been superseded by a later public state change.
- If a candidate is reusable, do not invoke `image-creator`. Publish an inline `illustration` block with the existing `image_path`, a localized title, and only the current context needed to understand the reused display.
- If no candidate passes the reuse check, generate or edit a new visual material with the `image-creator` skill and save the raster output under the session `assets/` directory.
- Build the image prompt from current session canon: concrete known places, relative positions, character knowledge limits, and visual tone.
- Write the image prompt as a direct description of the requested display content.
- Publish a `history_entry` containing an inline `illustration` block with `image_path`, localized `title`, optional `caption`, `source: "user_show"`, and `codex_visibility: "manual_only"`.
- Include `display_asset` metadata with no hidden information: the original display request, subject, purpose, player-visible scope, public visual summary, stable reuse key, relevant public canon references, and any reuse notes future Codex should consider.
- Record in the turn notes whether the display was reused, generated, or refreshed because an older image was no longer accurate.
- Do not reveal `gm/` secrets just because the requested display name points near a hidden truth.
- Do not let the script decide what the request means. Codex authors the inline illustration content.
- Expect the GUI to show the result inside the cumulative History stream.
- Omit prose blocks unless the display request changes the visible scene. Record display-handling notes in `turns/`, not visible story prose.

Codex may also publish `source: "codex_initiated"` illustration blocks during ordinary turns when a visual artifact materially improves play, such as a newly important map, diagram, portrait, document, creature, device, clue layout, or spatial relationship. Codex must not add automatic illustrations as decoration.

Codex must not automatically inspect raw image pixels from previous history illustrations during ordinary turn preparation. Use `ui/display_assets.json` metadata, especially `visual_summary`, plus public session files by default. Inspect a raw image only when the current turn requires visual confirmation, reuse validation, correction, or user-requested display handling, and record that reason in the turn notes.

## World Consistency

Treat established facts as canon.

Fact strength:

- hard canon: cannot be contradicted
- soft canon: should be preserved, but may have interpretation room
- rumor: a belief inside the world, possibly false
- hidden truth: Codex-only true state
- open space: undefined material Codex may invent

Before publishing a turn, check:

- Does this contradict hard canon?
- Does it break a world law or stated limit?
- Does it change genre or tone abruptly?
- Does it make the player character stronger than established constraints allow?
- Does it solve a major problem without cost?
- Does it reveal hidden truth too early?
- Does it ignore an active consequence, faction clock, or open thread?

If a user action tries to break the setting, keep the world intact and make the attempt produce an in-world result: failure, partial success, cost, suspicion, injury, debt, attention, or discovery.

## Hidden GM State

Use `gm/` to maintain engagement over long sessions.

Recommended hidden materials:

- secrets and hidden truths
- foreshadowing already planted
- faction plans and clocks
- consequence queue
- risk points for the player character
- unresolved mysteries with true answers
- private continuity notes

Foreshadowing lifecycle:

```text
planned -> seeded -> active -> revealed -> resolved
```

Use `abandoned` only when a hook is intentionally retired.

Each important hook should have:

- a visible clue
- a true meaning
- a first seeded turn
- a likely reveal window or condition
- an escalation rule
- a current status

## Story Style

- Do not offer numbered choices or menu actions.
- Write visible `type: "prose"` history blocks as the primary fiction, not as commentary about the fiction. The user should feel a novel scene continuing, not read a turn ledger.
- Narrate through concrete scene movement: what the player character perceives, what NPCs do or say, what changes in the environment, and what pressure remains.
- Do not start from abstract adjudication. Avoid bare outcome phrases such as "you succeed", "you fail", "the result is", "the objective is updated", or "the faction clock advances"; render those facts through the scene first.
- Banned History forms: bullet recaps, numbered outcomes, `Action` / `Result` structures, `Status changed` paragraphs, quest-log updates, GM notes, after-action reports, and detached summaries of offscreen state changes.
- Preferred History form: scene prose with a visible viewpoint anchored in place, sensation, motion, dialogue, choice pressure, or consequence.
- Keep summary exposition short and scene-anchored. If background is needed, attach it to a visible object, memory, rumor, document, song, inscription, or spoken line.
- Let the user's action reshape the scene before presenting the next point of uncertainty.
- Do not publish accumulated visible history in `latest_output.json`. The bridge appends or upserts `history_entry` into `ui/history_log.json` for GUI rendering.
- Do not use `ui/history_log.json` as the default source Codex rereads every turn. Keep `current/` compact and maintain durable public summaries in `story/`.
- Use status fields for mechanical facts; use history for atmosphere, action, stakes, and consequences.
- Keep `status_sections` compact and HUD-like. Use short labels, values, meters, tags, and grouped slots there; do not expand status into narrative paragraphs, lore summaries, or duplicate scene prose.
- Separate visible turns with `history_entry.label` UI metadata when needed. Do not place literal turn labels inside the prose solely for UI separation.
- Mark dialogue and decisive discoveries clearly. Use `**bold**` emphasis sparingly for important spoken words, clues, consequences, or changes in stakes.
- End each output in a state where the user can freely act.
- Let the world move even when the user hesitates.
- Let NPCs have desires, fears, secrets, and mistaken beliefs.
- Prefer consequences over negation.
- Prefer tension over convenience.
- Preserve ambiguity where it is useful, but track the truth privately.

The goal is not to defeat the user. The goal is to maintain a coherent, responsive world that becomes more interesting because the user acts inside it.

## GUI Theme Procedure

Every GUI output must include `language` and `ui_theme`.

Derive `ui_theme` from:

- world concept
- genre and tone boundaries
- current phase
- current scene stakes
- user readability needs

The theme must not be hardcoded to one genre. Choose labels, colors, and semantic icons that fit the current world. Use icons and emojis only when they improve scanning or atmosphere. Avoid decorative icon spam.

All visible theme labels, placeholders, hints, processing messages, status messages, status sections, and history text must use the active user language. Keep hidden GM files internally readable, but never let private notes force mixed-language visible output.

Processing copy must match the active world tone. It should tell the user that Codex is applying the submitted input to story state, visible status, and hidden GM continuity without revealing hidden content.

If the user prefers a light theme, default to a clean white/blue/slate interface. Use beige, cream, parchment, tan, brown, or warm paper palettes only when explicitly requested or when the active world concept clearly requires them.

Do not simulate notebook paper, ruled pages, parchment, scrolls, or other writing-surface gimmicks unless explicitly requested. Turn separation belongs in restrained UI structure, not decorative page texture.

Do not expose literal turn counters in the main HUD. Keep turn numbers internal to session files and GUI synchronization.

Keep the layout stable:

- history panel
- status panel
- input panel

Change the presentation through `ui_theme`, not by adding story-choice controls or world-specific widgets.

## Status Procedure

Every GUI output must make `status_sections` useful during play.

Treat the first completed-player `kind: "player"` section as the player's RPG character status screen for the active world. It must not read like a generic info card or a world summary. The visual grammar should be familiar across worlds, but every resource, attribute, skill, equipment, condition, and objective label must come from the active world. Omit containers that do not fit the current world.

Do not use the player HUD for global world symptoms, faction clocks, scene danger, or setting exposition. Before the player exists, publish a `setup` section for character creation and separate `world` or `scene` sections for world facts.

When writing `kind: "player"`, fill the character-sheet slots by role:

- `title`: character name, callsign, public identity, disguise, or current identity.
- `subtitle`: the world's equivalent of class, role, rank, origin, faction, calling, social identity, or archetype.
- `summary`: one line for current condition, leverage, vulnerability, or immediate constraint.
- `meters`: player-bound resources, burdens, drives, wounds, stress, power reserves, access, reputation, corruption, or other character-attached tracks.
- `vitals`: the most important current condition slots.
- `stats`: world-specific abilities, attributes, ratings, affinities, proficiencies, permissions, or competencies.
- `groups`: skills, equipment, powers, spells, augmentations, conditions, objectives, relationships, debts, cover identities, permissions, or other character-sheet categories.
- `fields`: short secondary slots only.
- `tags`: short scan flags.

The section should feel like opening the character sheet for this specific world. Do not copy a universal `HP`/`MP`/`STR`/`class`/`level` schema unless those terms exist in the setting.

Each status update should answer:

- Who is the player right now in this world?
- What role, archetype, class, calling, or social identity matters now?
- What world-specific resources, abilities, conditions, equipment, and objectives matter now?
- What is the player's current condition, leverage, vulnerability, or usable capability?
- What situation is the player currently in?
- What condition, leverage, or limitation matters now?
- What unresolved objective or thread is actionable?
- What tracked resource or progress value changed?

For non-player sections only, answer:

- What concrete world condition, relationship, scene fact, or clock is changing?
- Does it currently affect play enough to appear outside the player HUD?

Use `meters`, `stats`, `groups`, `fields`, and `tags` when they make the state easier to scan. Do not turn status into an encyclopedia or repeat hidden GM truth.

Do not expose generic GM tension labels as visible section titles. If tension is important, title the section with the actual in-world stake.

Ordering rules:

- Place player state first as the main RPG status HUD. Include identity, role, character-bound resource bars, attributes, skills, equipment, conditions, objectives, and player-bound variables that matter now.
- Place concrete active stakes second only when they matter now. Name them as in-world facts, not generic pressure labels.
- Place current scene facts next.
- Place inventory and supporting details after player state and any concrete active stake unless an item is currently under threat.
- Keep each field short. Long explanatory prose belongs in `history_entry.blocks` prose or session files, not the status panel.
