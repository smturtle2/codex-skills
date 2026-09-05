# Optional Agent Configuration

Read when a definition needs optional configuration, a built-in override, or an unfamiliar existing key. Basic fields and placement are in the skill entrypoint.

## Inheritance and Scope

A standalone role file is a Codex configuration layer, not a closed list of role-only fields. Omit optional settings unless supplied by the user, already present, or necessary for an explicit requirement with verified syntax.

Common optional keys include `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, `skills.config`, and `nickname_candidates`. This list is not an allowlist.

- Omitted model and reasoning settings inherit the live parent configuration unless selected at spawn time. Pinned role values take precedence over ordinary spawn-time choices.
- The parent turn's live permission choices are reapplied at spawn time. An agent-file sandbox value is a default, not an absolute boundary.
- Express read/write ownership in `developer_instructions` even when a sandbox field is present.
- Do not edit global `[agents]` runtime settings to register standalone definitions.

## Supported Shapes

Verify unfamiliar keys against the installed Codex or current official configuration schema.

- `sandbox_mode`: `read-only`, `workspace-write`, or `danger-full-access`.
- `skills.config`: array of tables (`[[skills.config]]`), with boolean `enabled` and a supported skill selector.
- `mcp_servers.<name>`: table with a valid transport, such as a non-empty stdio `command` or HTTP `url`.
- `model_reasoning_effort`: supported values depend on the selected model; do not enforce a frozen global enum.
- `nickname_candidates`: non-empty list of case-sensitive unique names after trimming, using ASCII letters, digits, spaces, hyphens, or underscores.

Do not invent MCP endpoints, credentials, paths, model identifiers, or permission settings.

## Names and Overrides

Codex identifies roles by their non-empty `name`; matching filenames and lowercase hyphenated spelling are authoring preferences, not runtime validity requirements. Preserve valid existing names.

Names `default`, `worker`, and `explorer` can override built-in roles. Use them only when the request expresses that intent; no repeated confirmation is needed once intent is clear.

## Compatibility Failures

Preserve unrelated supported fields during updates. A key missing from the local reference is not evidence it is invalid.

Use native Codex checking when available. If it rejects an existing key, report the incompatible field and required correction rather than deleting unrelated configuration. Distinguish native validation from local parse/schema checks.
