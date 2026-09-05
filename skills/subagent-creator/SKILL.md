---
name: subagent-creator
description: Create, update, or preview Codex custom-agent TOML definitions from a role brief. Use for agent definitions, not spawning agents or changing global orchestration settings.
---

# Subagent Creator

Produce the requested number and partition of role definitions. Do not merge requested variants, invent extra roles, run the agents, or modify global `[agents]`, skills, plugins, or unrelated configuration.

## Choose the Target

- `create`: write new definitions without overwriting existing ones.
- `update`: read each target first and change only what the brief requires.
- `preview`: return intended paths and TOML without creating target files.

Use personal scope at `$CODEX_HOME/agents/`, or `~/.codex/agents/` when unset. Use project `.codex/agents/` only when explicitly requested. Ask only when an update target cannot be identified or role ambiguity would materially change the definitions.

Before creation, check both filenames and role names. On collision, suffix the new name and filename together with `-2`, `-3`, etc. Preserve existing names and paths during updates unless the request changes them.

## Write the Definitions

Every file needs non-empty string fields:

- `name`: a concise role identifier; prefer lowercase ASCII and hyphens for new names.
- `description`: when the parent should use this specialization and its key boundary.
- `developer_instructions`: operational priorities, scope, evidence, output, and validation requirements.

For write-capable roles, assign ownership, acknowledge other workspace contributors, and prohibit reverting unrelated edits. For read-only roles, prohibit workspace and external-system mutation. Keep secondary duties only when needed for the role's primary purpose.

Omit optional configuration by default so the live parent settings are inherited. Do not ask the user to choose optional values merely because the fields exist.

Read [references/custom-agent-schema.md](references/custom-agent-schema.md) when handling optional settings, built-in overrides, or unfamiliar existing configuration. Preserve supported unrelated keys; do not remove an unknown key just to satisfy a local validator or invent model IDs and settings.

## Validate and Deliver

Use [references/quality-rubric.md](references/quality-rubric.md) for a brief acceptance check. Set `SKILL_DIR` to this skill's absolute directory and validate each definition with Python 3.11+ through uv:

```bash
uv run --no-project --python '>=3.11' python "$SKILL_DIR/scripts/validate_agent_toml.py" <file.toml>
```

For preview, pipe candidate TOML to the validator without writing its intended target:

```bash
uv run --no-project --python '>=3.11' python "$SKILL_DIR/scripts/validate_agent_toml.py" - --expected-path <intended-path>
```

Validate once per candidate and rerun after fixes. Use `--allow-builtin-override` only for a deliberately requested override. Resolve errors and disclose warnings or unavailable native checking; local checks alone do not establish full runtime compatibility.

Report each path and scope, role responsibility, changed boundaries, validation level, and any unresolved requirement. Distinguish saved definitions from previews and from agents actually executed.
