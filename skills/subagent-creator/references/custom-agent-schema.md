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

## Required top-level fields

Every standalone custom agent file must define these top-level keys:

| Field | Type | Rules |
| --- | --- | --- |
| `name` | string | Agent identifier used when spawning or referring to the agent. Prefer a short concrete name. |
| `description` | string | Human-facing trigger and boundary. Use multiline text when one sentence would flatten the role too much. |
| `developer_instructions` | string | Operational contract. State priorities, evidence, and what not to do. |

## Optional top-level fields

Add optional fields only when the brief or environment clearly needs them and you know the exact TOML shape.

| Field | Type or shape | Use when | Notes |
| --- | --- | --- | --- |
| `nickname_candidates` | array of strings | Many runs of the same agent need clearer UI labels | Keep values unique and non-empty. |
| `model` | string | The user or environment requires a pinned model | Otherwise inherit from the parent session. |
| `model_reasoning_effort` | string | The model choice needs a pinned reasoning level | Use only values supported by the current Codex release. |
| `sandbox_mode` | string | The role needs a stricter or broader sandbox than the parent session | Prefer `read-only` for pure research, review, or mapping roles. |
| `mcp_servers` | TOML table keyed by server name | The role requires concrete MCP access | Do not invent URLs, names, or credentials. |
| `skills.config` | nested skills config matching current Codex config syntax | The environment already provides exact skills configuration to inherit or pin | If the shape is uncertain, omit it. |

When omitted, these settings inherit from the parent session.

## Inheritance and safety

- Subagents inherit the parent session's sandbox and approval behavior unless the custom agent overrides them.
- Prefer inheritance by default.
- Use `sandbox_mode = "read-only"` for pure research, review, or mapping roles.
- Use broader write access only when the role is explicitly meant to edit or generate artifacts.
- Codex reapplies the parent turn's live runtime overrides when it spawns a child. Do not invent custom approval fields to fight that behavior.

## Naming guidance

- Prefer short, concrete names derived from the user's task language.
- Keep the role narrow. One agent should not mix exploration, review, implementation, and docs research unless the user explicitly wants a generalist.
- For newly generated names, prefer ASCII lowercase with digits and hyphens.
- Preserve an existing explicit name on update unless the user asks to rename it.
- Do not default to stock names unless the brief clearly points there.
- Use a distinct name if a file already exists and the user did not ask to update it.

## Nickname guidance

- Use `nickname_candidates` only when repeated runs of the same agent would benefit from clearer display labels.
- Keep the list unique and non-empty.
- Restrict nicknames to ASCII letters, digits, spaces, hyphens, and underscores.

## Formatting guidance

- One TOML file defines one custom agent.
- Matching the filename to the `name` field is the simplest convention, but `name` is the source of truth.
- Use multiline strings for `description` and `developer_instructions` when the role has real boundaries or detailed instructions.
- Rewrite or escape text that would break TOML string parsing.
- The final file must parse cleanly as TOML.

## Unknown or forbidden material

Do not fabricate:

- undocumented top-level keys
- approval-specific keys that are not confirmed by the current Codex docs
- MCP server URLs
- credentials
- filesystem paths outside the target agent file
- `skills.config` paths or shapes that were not provided
- global `[agents]` settings in `.codex/config.toml`

Add optional material only when the user or the environment gives you concrete values.
