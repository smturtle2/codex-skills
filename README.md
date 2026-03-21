# codex-skills

[한국어 README](README.ko.md)

Reusable Codex skills collected in one repository. Each skill lives in its own folder and includes a `SKILL.md` plus any bundled references, scripts, or assets it needs.

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory

## Install

Use the preinstalled `$skill-installer` system skill. Each skill entry below includes a one-line install command.

After installing a skill, restart Codex to pick it up.

## Current Skills

### `subagent-creator`

- Folder: `skills/subagent-creator`
- Install: `Use $skill-installer to install \`skills/subagent-creator\` from the GitHub repo \`smturtle2/codex-skills\`.`
- Purpose: create one focused Codex custom subagent from a natural-language brief
- Default behavior: write a single custom-agent TOML, usually under `~/.codex/agents/`
- Style: derive the role from the brief, keep defaults conservative, and avoid inventing MCP URLs or extra config unless the task provides them

This skill is grounded in the official Codex subagent documentation:

- https://developers.openai.com/codex/subagents
- https://developers.openai.com/codex/concepts/subagents

## Notes

- The repository is intentionally small and additive.
- Root docs describe the catalog.
- Skill-specific instructions live inside each skill folder instead of separate per-skill READMEs.
