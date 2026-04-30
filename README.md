# codex-skills

[한국어 README](README.ko.md)

Reusable Codex skills collected in one repository. Each skill lives in its own folder and includes a `SKILL.md` plus any bundled references, scripts, or assets it needs.

![Codex skills overview](docs/assets/codex-skills-hero.png)

Use this repository as a small installable catalog: copy a skill into your Codex skills directory with `$skill-installer`, restart Codex, then invoke the skill by name when its trigger matches your work.

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory
- `skills/*/SKILL.md`: the instruction body Codex reads when a skill is triggered
- `skills/*/scripts/`: helper scripts bundled with a skill
- `skills/*/references/`: optional supporting references used by a skill
- `skills/*/agents/`: optional agent/provider metadata for a skill
- `docs/assets/`: README images and other repository-level documentation assets

## Install

Use the preinstalled `$skill-installer` system skill. Each skill entry below includes a copy-paste-ready one-line prompt.

After installing a skill, restart Codex to pick it up.

## Choose A Skill

| Need | Use | Output |
| --- | --- | --- |
| Generate or edit a project-local raster image | `image-creator` | Saved image file plus the exact rewritten prompt |
| Build or substantially redesign frontend UI | `ui-blueprint` | Generated UI mockup, extracted visual notes, implemented UI |
| Create or update one custom Codex subagent | `subagent-creator` | One focused TOML agent definition with validation |
| Play Gomoku against Codex | `gomoku-codex` | Python GUI board plus JSON state bridge for Codex moves |

## Current Skills

### `image-creator`

![Image Creator workflow](docs/assets/image-creator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/image-creator` |
| Use when | You need a generated or edited raster image saved into the current project. |
| Does | Rewrites the user's request into a concise image prompt, preserves exact rendered text and explicit constraints, calls the selected generation path, then saves the output. |
| Does not | Use `view_image` outside the immediate bridge step for local input images, invent extra creative constraints, or handle code-native SVG/HTML/CSS artwork. |

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/image-creator
```

### `ui-blueprint`

| Field | Details |
| --- | --- |
| Folder | `skills/ui-blueprint` |
| Use when | You are building new UI, doing a substantial redesign, or working on a visually led screen. |
| Does | Uses `image-creator` to create a mockup first, extracts layout and visual decisions, then implements against the existing frontend stack. |
| Does not | Skip the generated blueprint for visually important UI work, or use this workflow for narrow bug fixes and small maintenance edits. |

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/ui-blueprint
```

### `subagent-creator`

![Subagent Creator workflow](docs/assets/subagent-creator-workflow.png)

| Field | Details |
| --- | --- |
| Folder | `skills/subagent-creator` |
| Use when | You need one focused Codex custom subagent derived from a natural-language brief. |
| Does | Distills the role contract, writes a TOML agent definition, keeps defaults conservative, and validates the result when possible. |
| Does not | Create multiple agents by default, invent MCP URLs or credentials, or snap to canned role examples unless the brief requires them. |

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/subagent-creator
```

This skill is grounded in the official Codex subagent documentation:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

### `gomoku-codex`

| Field | Details |
| --- | --- |
| Folder | `skills/gomoku-codex` |
| Use when | You want to play Gomoku with a local Python GUI while Codex chooses and applies its own moves. |
| Does | Runs a Pygame board, persists a JSON game state, validates moves, wins, and optional Renju restrictions, and lets Codex wait on the state file before applying its configured color. |
| Does not | Implement a fixed AI engine or call the OpenAI API from the GUI. |

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/gomoku-codex
```

## Notes

- The repository is intentionally small and additive.
- Root docs describe the catalog.
- Skill-specific instructions live inside each skill folder instead of separate per-skill READMEs.
