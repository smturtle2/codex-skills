# codex-skills

[한국어 README](README.ko.md)

Reusable Codex skills collected in one repository. Each skill lives in its own folder and includes a `SKILL.md` plus any bundled references, scripts, or assets it needs.

## Repository Layout

- `skills/`: skill folders ready to copy into a Codex skills directory

## Install

Install one skill by copying it into your Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/subagent-creator "${CODEX_HOME:-$HOME/.codex}/skills/"
```

If you want the repo checkout to stay as the source of truth while you update it, create a symlink instead:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$(pwd)/skills/subagent-creator" "${CODEX_HOME:-$HOME/.codex}/skills/subagent-creator"
```

After that, Codex can discover the skill as `$subagent-creator`.

## Current Skills

### `subagent-creator`

- Folder: `skills/subagent-creator`
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
