# Custom Agent Schema

Use this reference for Codex validity, placement, inheritance, and update rules. Keep authoring preferences distinct from runtime requirements.

## Placement

- Personal definitions live under `$CODEX_HOME/agents/`; `CODEX_HOME` defaults to `~/.codex`.
- Project definitions live under `.codex/agents/` and apply through trusted project configuration layers.
- One TOML file defines one custom subagent. A request for multiple subagents produces multiple independent files.
- Codex identifies a role by its `name`; matching the filename is a convention, not a validity requirement.

## Required Metadata

Every standalone custom-agent file requires these non-empty strings:

| Field | Contract |
| --- | --- |
| `name` | Identifier used when spawning or referring to the role. Codex trims it and requires it to be non-empty. |
| `description` | Human-facing guidance that lets a parent decide when to use the role. |
| `developer_instructions` | Operational instructions applied to the spawned agent. |

`nickname_candidates` is optional. When present, it must be a non-empty list of case-sensitive unique names after trimming leading and trailing whitespace. Each name may contain ASCII letters, digits, spaces, hyphens, and underscores.

## Configuration Layer

A custom-agent file is also a normal Codex configuration layer. In addition to agent metadata, it may contain any key supported by the current `config.toml` schema.

Common optional keys include:

| Key | Default behavior when omitted |
| --- | --- |
| `model` | Preserve the live parent model unless spawn-time selection chooses another one. |
| `model_reasoning_effort` | Preserve the live parent reasoning setting unless spawn-time selection chooses another one. |
| `sandbox_mode` | Inherit the parent session's effective permission configuration. |
| `mcp_servers` | Inherit configured MCP servers. |
| `skills.config` | Inherit configured skill availability. |
| `nickname_candidates` | Use the normal role name as the display identity. |

This table is deliberately non-exhaustive. Do not reject a key solely because it is absent from this list. Verify additional keys against the installed Codex or current official config schema.

## Defaults And Precedence

- Prefer omission and inheritance over pinning optional settings.
- Role configuration can override persisted configuration values, but the parent turn's live permission and approval choices are reapplied when a child is spawned.
- `sandbox_mode` in a role file is therefore a default, not an absolute enforcement boundary.
- Model or reasoning values pinned in a role file take precedence over ordinary spawn-time choices.
- Do not add optional configuration merely to make a role look complete.

## Built-in Roles And Naming

Codex includes `default`, `worker`, and `explorer`. A custom role with the same name intentionally overrides the built-in role.

- Treat built-in override confirmation as an authoring safety check, not a schema restriction.
- For new definitions, prefer short ASCII lowercase names containing digits and hyphens.
- Codex itself accepts other non-empty names. Preserve runtime-valid existing names during update.

## Supported Shapes

- `sandbox_mode` accepts `read-only`, `workspace-write`, or `danger-full-access`.
- `skills.config` is an array of tables written with `[[skills.config]]`; each entry requires a boolean `enabled` and may select a skill using the current supported selector fields.
- Each `mcp_servers.<name>` entry is a table with a valid transport, such as a non-empty string `command` for stdio or `url` for HTTP-based transport.
- `model_reasoning_effort` support depends on the selected model and current model catalog. Do not enforce a frozen global enum.

## Update And Collision Rules

- Read every target before editing it.
- Preserve unrelated supported fields and explicit user choices.
- Keep existing names and paths unless the request changes them.
- Inspect both filenames and role `name` values in the selected scope before creation.
- Do not overwrite a create collision; apply the same deterministic numeric suffix to both the new role `name` and filename until both are unused.
- Do not remove an existing unverified key to make a local allowlist pass. Verify it with current Codex, and report a blocker if Codex rejects it.

## Out Of Scope

The global `[agents]` section controls multi-agent runtime behavior such as concurrency, nesting depth, batch timeout, interruption messages, and optional role registration. Standalone files under the agents directory are discovered without requiring this skill to edit `[agents]`.

This skill does not own:

- global `[agents]` settings
- spawning, steering, or closing agent threads
- orchestration between roles
- unrelated Codex configuration
