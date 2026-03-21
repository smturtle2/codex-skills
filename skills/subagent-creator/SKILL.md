---
name: subagent-creator
description: Create focused Codex custom subagents from a natural-language task brief. Use when Codex needs to design, write, or update a `~/.codex/agents/*.toml` or `.codex/agents/*.toml` file for a new subagent, especially zero-shot from a short description of the job, boundaries, tools, or sandbox posture.
---

# Subagent Creator

Create one focused Codex custom agent from the user's brief.

Read [references/custom-agent-schema.md](references/custom-agent-schema.md) for the file schema and inheritance rules. Read [references/brief-patterns.md](references/brief-patterns.md) when you need help mapping a vague request to one narrow agent.

## Workflow

1. Identify the single primary job in the brief.
2. Choose the output scope and path.
3. Derive a narrow agent identity and boundary.
4. Write the minimum TOML needed for that role.
5. Save the file or return a preview if the user asked for one.

## Output Scope

- Default to user scope: `~/.codex/agents/<agent-name>.toml`.
- Use project scope: `.codex/agents/<agent-name>.toml` only when the user explicitly asks for a project-scoped agent.
- Create the target directory if it does not exist.
- Generate exactly one agent file unless the user explicitly asks for multiple agents.

## Agent Design Rules

- Make the role narrow and opinionated. Prefer one job such as `reviewer`, `code-mapper`, `docs-researcher`, or `ui-fixer`.
- Do not use built-in names `default`, `worker`, or `explorer`.
- Match the filename to the `name` field when practical.
- Prefer lowercase hyphen-case for new agent names unless the user asks to match an existing convention.
- If the brief spans multiple roles, compress it to the most important single role and leave the rest out.
- If a file with the intended name already exists and the user did not ask to update it, create a distinct nearby name instead of overwriting blindly.

## Configuration Rules

- Always write `name`, `description`, and `developer_instructions`.
- Omit optional fields unless the brief or environment clearly justifies them.
- By default, let `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, and `skills.config` inherit from the parent session.
- Pin `sandbox_mode` only when the role clearly needs a stricter or broader surface.
- Add `nickname_candidates` only when the user is likely to run many copies of the same agent and wants clearer UI labels.
- Do not create or modify `.codex/config.toml` unless the user explicitly asks for global agent settings too.

## Zero-Shot Defaults

- Ask at most one clarification only when a concrete missing value blocks correctness or safety.
- Otherwise proceed with conservative defaults.
- Do not invent MCP URLs, credentials, filesystem paths, or skill paths.
- Do not add optional integrations just because they would be nice to have.
- Keep `developer_instructions` imperative, specific, and bounded by what the role should not do.

## Minimal Template

```toml
name = "docs-researcher"
description = "Documentation specialist that verifies APIs and framework behavior."
developer_instructions = """
Use primary documentation sources to confirm APIs, options, and version-specific behavior.
Return concise answers with exact references when available.
Do not make code changes.
"""
```

## Response

- If you wrote the file, report the output path and a one-line summary of the agent's job.
- If the user asked for a preview, return the TOML and intended path without writing.
- Do not spawn the new agent unless the user explicitly asks.
- For write-capable roles, mention the ownership boundary or the files the new agent should leave untouched.
