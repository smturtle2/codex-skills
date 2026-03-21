# codex-skills

[한국어 README](README.ko.md)

Reusable Codex skills collected in one repository. Each skill lives in its own folder and includes a `SKILL.md` plus any bundled references, scripts, or assets it needs.

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory

## Install

Use the preinstalled `$skill-installer` system skill. Each skill entry below includes a copy-paste-ready one-line prompt.

After installing a skill, restart Codex to pick it up.

## Current Skills

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
