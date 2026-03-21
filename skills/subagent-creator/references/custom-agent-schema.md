# Custom Agent Schema

Use this reference when you need exact field and placement rules for a Codex custom agent.

## File placement

- User-scoped agents live under `~/.codex/agents/`.
- Project-scoped agents live under `.codex/agents/`.
- One TOML file defines one custom agent.
- Matching the filename to the `name` field is the simplest convention.

## Built-in agents

Codex already ships with:

- `default`
- `worker`
- `explorer`

If a custom agent uses one of those names, the custom agent takes precedence. Avoid that unless the user explicitly wants an override.

## Required fields

Every standalone custom agent file must define:

```toml
name = "task-focused-agent"
description = """
Use `task-focused-agent` for <clear trigger>.
<Short statement of strengths and scope>.
Rules:
- <non-negotiable rule>
- <non-negotiable rule>
"""
developer_instructions = """
<Operational priorities>.
<Evidence, validation, or output expectations>.
<What the agent must avoid doing>.
"""
```

- `name`: the identifier Codex uses when spawning or referring to the agent.
- `description`: human-facing guidance about when to use the agent.
- `developer_instructions`: the core behavioral contract.

## Optional fields

These can be added when the brief clearly needs them:

- `nickname_candidates`
- `model`
- `model_reasoning_effort`
- `sandbox_mode`
- `mcp_servers`
- `skills.config`

When omitted, these settings inherit from the parent session.

## Inheritance and safety

- Subagents inherit the parent session's sandbox and approval behavior unless the custom agent overrides them.
- Prefer inheritance by default.
- Use `sandbox_mode = "read-only"` for pure research, review, or mapping roles.
- Use broader write access only when the role is explicitly meant to edit or generate artifacts.

## Naming guidance

- Prefer short, concrete names derived from the user's task language.
- Keep the role narrow. One agent should not mix exploration, review, implementation, and docs research unless the user explicitly wants a generalist.
- Do not default to stock names unless the brief clearly points there.
- Use a distinct name if a file already exists and the user did not ask to update it.

## Nickname guidance

- Use `nickname_candidates` only when repeated runs of the same agent would benefit from clearer display labels.
- Keep the list unique and non-empty.
- Restrict nicknames to ASCII letters, digits, spaces, hyphens, and underscores.

## What not to invent

Do not fabricate:

- MCP server URLs
- credentials
- filesystem paths outside the target agent file
- `skills.config` paths
- global `[agents]` settings in `.codex/config.toml`

Add those only when the user or the environment gives you concrete values.
