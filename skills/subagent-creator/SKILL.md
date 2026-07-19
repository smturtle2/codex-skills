---
name: subagent-creator
description: Create, update, or preview one or more Codex custom subagent definitions from a task brief. Use when Codex needs to write or revise personal `$CODEX_HOME/agents/*.toml` files or explicitly requested project `.codex/agents/*.toml` files. This skill owns custom-agent TOML definitions only; it does not manage global `[agents]` runtime settings or spawn agents.
---

# Subagent Creator

Create or update the custom subagent definitions requested by the user.

Read [references/custom-agent-schema.md](references/custom-agent-schema.md) before drafting configuration. Read [references/quality-rubric.md](references/quality-rubric.md) before accepting the result. Validate every resulting TOML with `python3 scripts/validate_agent_toml.py` when the environment permits it.

## Responsibility

- Own custom subagent TOML definitions and nothing else.
- Match the user's explicit requested cardinality and role partition, including multiple requested variants of the same responsibility.
- Preserve separately requested definitions as separate files. Do not merge them to enforce a one-agent limit, and do not split one coherent request merely to invent a team.
- Do not create or modify global `[agents]` settings, `AGENTS.md`, skills, plugins, or unrelated Codex configuration.
- Do not spawn, run, steer, or evaluate the created subagents unless the user makes that a separate request outside this skill.

## Request Modes

- `create`: create the requested definitions without overwriting unrelated files.
- `update`: read every targeted definition first and change only what the new brief requires.
- `preview`: return the intended paths and TOML without creating the target files.
- Resolve the targets from the request and environment. Ask one focused clarification only when an update target cannot be identified safely or the requested roles are materially ambiguous.

## Workflow

1. Determine the mode and the roles explicitly requested.
2. Distill each requested role into its own role contract.
3. Select the scope and collision-safe path for every definition.
4. Draft required fields first and omit optional configuration by default.
5. Preserve supported unrelated keys during updates.
6. Validate every definition and address hard failures.
7. Write the files or return the preview, then report paths, role boundaries, and validation level.

## Role Contract

For each requested role, derive:

- when a parent should use it
- what it is optimized to do
- what it must not do
- what it owns when it can edit
- what evidence, validation, and output it must return

Keep bounded secondary responsibilities only when the primary role needs them to work. Preserve every separately requested role, and do not invent additional independent roles that the user did not request.

## Scope And Paths

- Default to personal scope under `$CODEX_HOME/agents/`.
- When `CODEX_HOME` is unset, use `~/.codex/agents/`.
- Use `.codex/agents/` only when the user explicitly requests project scope.
- Create the selected directory when writing and it does not exist.
- Match each filename to its `name` when practical.
- Before creating files, inspect the selected scope's existing TOML filenames and role `name` values.
- On create collisions, preserve the existing definition and suffix both the new role `name` and filename with `-2`, then `-3`, and so on until both are unused.

## Naming

- Derive names from the user's domain nouns and responsibilities.
- For new definitions, prefer short ASCII lowercase names with digits and hyphens.
- Preserve an existing name during update unless the user asks to rename it.
- Avoid overriding `default`, `worker`, or `explorer` unless the request makes that intent explicit.

## Configuration Defaults

- Always provide non-empty `name`, `description`, and `developer_instructions`.
- Treat the custom-agent file as a Codex configuration layer; supported `config.toml` keys may appear when justified.
- Omit `model`, `model_reasoning_effort`, `sandbox_mode`, MCP, skills, approval, and other optional settings by default so the spawned agent inherits the live parent configuration.
- Do not ask the user to choose optional settings merely because they exist.
- Add or change an optional key only when the user supplied it, the existing file already contains it, or the role cannot satisfy an explicit requirement without it and the exact current syntax is verified.
- Treat agent-file sandbox and approval values as defaults. The parent turn's live permission choices take precedence.
- Express read-only or write-ownership boundaries in `developer_instructions` even when no sandbox setting is pinned.
- Never invent model identifiers, reasoning values, MCP endpoints, credentials, approval settings, filesystem paths, or skill selectors.

## Description And Instructions

- Make `description` sufficient for a parent to decide when to use the role without opening the file.
- State the trigger, specialization, and non-negotiable boundary.
- Make `developer_instructions` operational rather than repetitive: priorities, evidence, output, validation, and prohibited actions.
- For write-capable roles, assign ownership, state that the agent is not alone in the workspace, and forbid reverting unrelated edits.
- For read-only roles, explicitly forbid workspace and external-system mutation.

## Updates

- Preserve unrelated fields, supported configuration, names, and paths.
- Do not delete an unfamiliar key merely because the local validator does not recognize it.
- Use current Codex validation when available. If Codex rejects an existing key, do not silently remove it; report the blocker before changing unrelated configuration.
- Make any changed role boundary explicit in the response.

## Validation

Validate a written file with:

```text
python3 scripts/validate_agent_toml.py PATH
```

Validate preview TOML through stdin without creating its intended target:

```text
python3 scripts/validate_agent_toml.py - --expected-path INTENDED_PATH
```

- Run the validator once per definition.
- Treat errors as blockers.
- Review warnings as authoring or compatibility signals; do not claim complete validation when native Codex checking was unavailable.
- For intentional built-in overrides, rerun with `--allow-builtin-override`.

## Response

- Report every output path and whether it is personal or project scoped.
- Summarize each subagent's responsibility in one line.
- For updates, state what changed and what unrelated configuration was preserved.
- State the validation level and unresolved warnings.
- Report any requested responsibility left out of a definition.
- Do not report that the subagents were executed when only their definitions were created.
