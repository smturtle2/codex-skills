# codex-skills

[![Skills](https://img.shields.io/badge/skills-9-2563eb)](#skills) [![Codex](https://img.shields.io/badge/Codex-compatible-111827)](#quick-install) [![Assets](https://img.shields.io/badge/assets-16-16a34a)](docs/assets) [![Language](https://img.shields.io/badge/README-%ED%95%9C%EA%B5%AD%EC%96%B4-7c3aed)](README.ko.md)

A small, installable catalog of Codex skills for silent idea capture, image generation, EPUB translation, animation assets, UI blueprints, subagent creation, podcast scripts, world simulation, and Gomoku.

Each skill is self-contained with a `SKILL.md` trigger contract plus any local scripts, references, assets, and agent metadata it needs.

Languages: English | [한국어](README.ko.md)

![Codex skills catalog](docs/assets/codex-skills-hero.png)

## Why Use This

- Self-contained skills that can be copied into a Codex skills directory.
- Copy-paste install prompts for each skill.
- Practical workflows, not demos.
- Small enough to audit before installing.

## Skills

| Skill | Best for | Output | Install |
| --- | --- | --- | --- |
| [`idea-scribe`](#idea-scribe) | Silently capturing a stream of ideas while maintaining the current organized view | Append-only `raw.txt` and rewritten `organized.html` | [Prompt](#idea-scribe) |
| [`image-creator`](#image-creator) | Generating, editing, or removing backgrounds from project-local raster images | Saved raster file or true-alpha PNG plus the exact final prompt | [Prompt](#image-creator) |
| [`epub-translator`](#epub-translator) | Translating EPUB books into natural new target-language editions | New translated `.epub`, flow-IR run folder, slim chunk translations, edition policy, image job ledger, and validation summary | [Prompt](#epub-translator) |
| [`animation-creator`](#animation-creator) | Creating project-local character animation assets | Run folder with prompts, layout guides, frames, validation, contact sheets, and previews | [Prompt](#animation-creator) |
| [`ui-blueprint`](#ui-blueprint) | Building or substantially redesigning frontend UI | Generated UI mockup, visual notes, and implemented UI | [Prompt](#ui-blueprint) |
| [`subagent-creator`](#subagent-creator) | Creating or updating custom Codex subagents | One or more TOML agent definitions with the achieved validation level reported | [Prompt](#subagent-creator) |
| [`podcast-writer`](#podcast-writer) | Turning sources into one-person podcast scripts | Plain `.txt` script plus strict content-quality evaluation | [Prompt](#podcast-writer) |
| [`world-simulator`](#world-simulator) | Building and playing a persistent Codex-native world RPG | Browser Studio and Chronicle backed by an atomic SQLite world ledger | [Prompt](#world-simulator) |
| [`gomoku`](#gomoku) | Playing Gomoku against Codex in a local GUI | Python board plus JSON state bridge for Codex moves | [Prompt](#gomoku) |

## Quick Install

Use the preinstalled `$skill-installer` system skill, then restart Codex so the installed skill is picked up.

```text
Use $skill-installer to install skills/<skill-name> from https://github.com/smturtle2/codex-skills.
```

## Catalog

### `idea-scribe`

Record the user's ongoing idea stream verbatim while maintaining a readable brief of only the ideas that remain active.

| Field | Details |
| --- | --- |
| Folder | `skills/idea-scribe` |
| Use when | The user wants to think aloud without conversational interruption while Codex records and organizes the material. |
| Produces | Exactly two files: append-only `raw.txt` and a self-contained, single-column `organized.html` current-state brief. |
| Avoids | Clarifying dialogue, invented conclusions, change history in the organized view, spatial graphs, and additional user-facing artifacts. |

Install:

```text
Use $skill-installer to install skills/idea-scribe from https://github.com/smturtle2/codex-skills.
```

### `image-creator`

Generate or edit raster images, optionally produce a true-alpha transparent PNG, and save the result into the current project.

![Image Creator workflow](docs/assets/image-creator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/image-creator` |
| Use when | You need a generated or edited raster image, a local image reference, or explicit transparent-background output saved into the current project. |
| Produces | An unchanged copy of the generated raster file or a natively generated transparent PNG with verified transparency, the exact final prompt, bound local input paths, and actual dimensions/format metadata. |
| Avoids | Unbound image inputs, rollout or state-database payload lookup, silent opaque transparency fallbacks, and code-native SVG/HTML/CSS artwork. |

Install:

```text
Use $skill-installer to install skills/image-creator from https://github.com/smturtle2/codex-skills.
```

### `epub-translator`

Translate EPUB books into natural new target-language editions. The helper extracts a normalized reading-flow IR, packs slim chunks, and deterministically builds a new EPUB — source wrappers and fixed offsets are flattened; only reading/anchor/link/image invariants are preserved.

![EPUB Translator workflow](docs/assets/epub-translator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/epub-translator` |
| Use when | You need to translate an EPUB into a natural new target-language EPUB, handle large books with chunk continuity, and process text inside embedded raster images. |
| Produces | A new translated `.epub`, flow IR plus run folder, slim chunk JSON with a seam tail, edition policy, image job ledger, and build/validation summary. |
| Avoids | Patching source XHTML, layout wrappers that create overflow, per-filename layout exceptions, and using image generation for images with no text to translate. |

Install `$image-creator` as well when image text translation is needed:

```text
Use $skill-installer to install skills/image-creator and skills/epub-translator from https://github.com/smturtle2/codex-skills.
```

### `animation-creator`

Create character animation assets from a source character image or a generated base character.

![Animation Creator workflow](docs/assets/animation-creator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/animation-creator` |
| Use when | You need project-local sprite strips, frame sequences, GIF/WebP/MP4 previews, or additional actions that preserve one character identity. |
| Produces | A run folder with canonical base references, action prompts, layout guides, extracted frames, contact sheets, validation JSON, and previews. |
| Avoids | Global packaging, local code-generated character art, and accepting clipped or slot-crossing animation frames. |

Install:

```text
Use $skill-installer to install skills/animation-creator from https://github.com/smturtle2/codex-skills.
```

### `ui-blueprint`

Create a generated UI mockup first, then implement frontend work against that visual blueprint.

![UI Blueprint workflow](docs/assets/ui-blueprint-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/ui-blueprint` |
| Use when | You are building new UI, doing a substantial redesign, or working on a visually led screen. |
| Produces | A generated mockup, extracted layout and visual decisions, and implementation guidance for the existing frontend stack. |
| Avoids | Skipping the blueprint for visually important UI work, and applying the workflow to narrow bug fixes or small maintenance edits. |

Install:

```text
Use $skill-installer to install skills/ui-blueprint from https://github.com/smturtle2/codex-skills.
```

### `subagent-creator`

Create or update one or more Codex custom subagents from natural-language role briefs, matching the number the user explicitly requests.

![Subagent Creator workflow](docs/assets/subagent-creator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/subagent-creator` |
| Use when | You need to create or update one or more Codex custom subagents from natural-language briefs. |
| Produces | The explicitly requested number of TOML agent definitions, each with a clear role, tool policy, constraints, and the achieved validation level reported. |
| Default location | `$CODEX_HOME/agents`; falls back to `~/.codex/agents` when `CODEX_HOME` is unset. |
| Outside scope | `[agents]` runtime settings and spawning or executing subagents. |
| Avoids | Inventing MCP URLs or credentials and snapping to canned role examples unless required. |

Install:

```text
Use $skill-installer to install skills/subagent-creator from https://github.com/smturtle2/codex-skills.
```

Docs:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

### `podcast-writer`

Turn PDFs, text files, websites, and YouTube transcripts into a one-person podcast script saved as plain text.

![Podcast Writer workflow](docs/assets/podcast-writer-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/podcast-writer` |
| Use when | You need Codex to collect source material, use YouTube captions or GPU-only Whisper transcription when needed, write a one-person podcast monologue, and keep revising until strict content-quality evaluation passes. |
| Produces | A saved `.txt` script, source handling notes, and a strict subagent evaluation with all rubric items passing. |
| Avoids | Speaker labels, interview/dialogue format, source-free claims, final-script metadata, and using the evaluator for TTS or formatting checks. |

Install:

```text
Use $skill-installer to install skills/podcast-writer from https://github.com/smturtle2/codex-skills.
```

### `world-simulator`

Build an original world in a browser Studio, then inhabit it as a persistent solo RPG. Codex authors the setting and directs each scene; the bundled runtime keeps the interface, history, and world state durable without deciding the fiction itself.

- **Studio:** Turns a rough concept into public lore, hidden pressures, characters, factions, places, relations, a player, and an opening situation without forcing a setup wizard.
- **Play:** Accepts unrestricted natural-language actions. Every player input and resulting scene remains in one chronological reading flow, with dialogue and decisive details emphasized for scanning.
- **Living world:** Creates people, places, cultures, institutions, objects, and history as they are encountered, connects them to established causes, and persists them instead of pausing for lore dumps.
- **RPG interface:** Keeps player identity and current state in the left desktop rail, places character and world reference in the same rail, and preserves disclosure state while the chronicle updates.
- **World ledger:** Commits each response, entity, relation, event, consequence, and private GM update atomically to `world.sqlite3`; Play exposes only player-visible truth and can resume the same session later.

| Field | Details |
| --- | --- |
| Folder | `skills/world-simulator` |
| Use when | You want to co-author an original setting and then play a persistent solo RPG through unrestricted natural-language actions. |
| Produces | A light browser Studio/Play UI, complete input-and-response chronicle, persistent player sheet, public worldbook, private GM state, entity graph, causal event history, and resumable `world.sqlite3`. |
| Avoids | Chat-side story input, lorebook keyword injection, fixed RPG stat schemas, forced choice menus, and Python-generated narrative decisions. |

Install:

```text
Use $skill-installer to install skills/world-simulator from https://github.com/smturtle2/codex-skills.
```

### `gomoku`

Play Gomoku with a local Python GUI while Codex waits, reads Codex view JSON, and applies its own moves.

![Gomoku workflow](docs/assets/gomoku-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/gomoku` |
| Use when | You want to play Gomoku with a local Python GUI while Codex chooses and applies its own moves. |
| Produces | A Pygame board, internally managed state, move validation, win detection, optional Renju restrictions, and Codex wait/apply commands. |
| Avoids | A fixed AI engine and OpenAI API calls from the GUI. |

Install:

```text
Use $skill-installer to install skills/gomoku from https://github.com/smturtle2/codex-skills.
```

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory.
- `skills/*/SKILL.md`: the instruction body Codex reads when a skill is triggered.
- `skills/*/scripts/`: helper scripts bundled with a skill.
- `skills/*/references/`: optional supporting references used by a skill.
- `skills/*/assets/`: skill icon assets and reusable bundled files.
- `skills/*/agents/`: optional agent/provider metadata for a skill.
- `docs/assets/`: README images and repository-level documentation assets.

## Contributing

New skills should include a `SKILL.md`, a clear trigger description, and any required scripts or references inside the skill folder.

Quality bar:

- Clear trigger rules.
- Minimal bundled context.
- No hidden credentials.
- Local, auditable scripts.
- Skill icon assets and agent metadata references when a skill is listed in the catalog.
- README entry and install prompt.

## Notes

- Root docs describe the catalog.
- Skill behavior lives in each skill's `SKILL.md`.
- Restart Codex after installing or updating a skill.
