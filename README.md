# codex-skills

[한국어 README](README.ko.md)

Reusable Codex skills collected in one repository. Each skill lives in its own folder and includes a `SKILL.md` plus any bundled references, scripts, or assets it needs.

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory

## Install

Use the preinstalled `$skill-installer` system skill. Each skill entry below includes a copy-paste-ready one-line prompt.

After installing a skill, restart Codex to pick it up.

## Current Skills

### `image-creator`

- Folder: `skills/image-creator`
- Purpose: generate or edit raster images from the user's intended prompt without rewriting, translating, embellishing, or adding prompt scaffolding
- Default behavior: call the built-in `image_gen` tool directly, load any requested local input images first, then save the generated image to the requested path or project root
- Style: preserve the user's creative intent exactly while treating obvious save paths and file-loading details as execution instructions
- Boundary: intended for prompt-faithful image creation; skip when the user wants prompt engineering, UI blueprints, or code-native SVG/HTML/CSS artwork

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/image-creator
```

### `ui-blueprint`

- Folder: `skills/ui-blueprint`
- Purpose: require frontend UI work to start from a generated visual blueprint instead of a text-only design pass
- Default behavior: use `image-creator` to create a UI mockup, inspect the image, then implement against the extracted layout, hierarchy, color, typography, spacing, and state cues
- Style: keep the reasoning workflow pinned to `gpt-5.4` when model selection is available, while preserving the target repo's frontend stack and component conventions
- Boundary: intended for new UI, substantial redesigns, and visually led screens; skip for narrow bug fixes or small maintenance edits

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/ui-blueprint
```

### `subagent-creator`

- Folder: `skills/subagent-creator`
- Purpose: create or update one focused Codex custom subagent from a natural-language brief
- Default behavior: write a single custom-agent TOML, usually under `~/.codex/agents/`
- Style: derive the role from the brief, keep defaults conservative, and avoid inventing MCP URLs or extra config unless the task provides them
- Philosophy: keep the skill zero-shot by avoiding canned role examples and investing instead in rules, schema constraints, and validation

Install:

```text
Use $skill-installer to install https://github.com/smturtle2/codex-skills/tree/main/skills/subagent-creator
```

This skill is grounded in the official Codex subagent documentation:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

## Notes

- The repository is intentionally small and additive.
- Root docs describe the catalog.
- Skill-specific instructions live inside each skill folder instead of separate per-skill READMEs.
