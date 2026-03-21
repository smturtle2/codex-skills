---
name: subagent-creator
description: Create high-quality Codex custom subagents directly from a raw task brief. Use when Codex needs to design, write, or update a `~/.codex/agents/*.toml` or `.codex/agents/*.toml` file, especially when the role is novel and should be derived from the user's task instead of picked from canned templates.
---

# Subagent Creator

Create one high-quality Codex custom agent directly from the user's brief.

Read [references/custom-agent-schema.md](references/custom-agent-schema.md) for the file schema and inheritance rules. Read [references/quality-rubric.md](references/quality-rubric.md) for the quality bar the finished agent definition should meet.

## Core Rule

Treat the user's brief as source material, not as a category label.

- Derive the agent contract from the actual job, boundaries, collaboration mode, and output expectations in the brief.
- Do not snap to a canned roster of explorer, reviewer, fixer, or researcher roles unless the brief itself clearly asks for one.
- Preserve the user's domain language when it carries important meaning.

## Workflow

1. Distill the brief into a role contract.
2. Choose the output scope and path.
3. Derive a concrete agent name from the brief itself.
4. Write a strong multiline `description`.
5. Write `developer_instructions` that operationalize the role.
6. Add optional fields only when the brief or environment requires them.
7. Save the file or return a preview if the user asked for one.

## Role Contract

Before you write, answer these questions from the brief itself:

- When should this agent be used?
- What is it optimized to do better than the parent agent?
- What must it avoid doing?
- If it can edit, what does it own and what must it not touch?
- What should it return, prioritize, or validate?

## Output Scope

- Default to user scope: `~/.codex/agents/<agent-name>.toml`.
- Use project scope: `.codex/agents/<agent-name>.toml` only when the user explicitly asks for a project-scoped agent.
- Create the target directory if it does not exist.
- Generate exactly one agent file unless the user explicitly asks for multiple agents.

## Agent Design Rules

- Make the role narrow and opinionated.
- Derive the role from the user's actual task nouns and verbs instead of reaching for stock names first.
- Do not use built-in names `default`, `worker`, or `explorer`.
- Match the filename to the `name` field when practical.
- Prefer short lowercase names. Use hyphens only when they improve readability.
- If the brief spans multiple roles, compress it to the most important single role and leave the rest out.
- If a file with the intended name already exists and the user did not ask to update it, create a distinct nearby name instead of overwriting blindly.

## Description Quality Bar

- The `description` should be strong enough that a parent agent can decide when to use the subagent without reading anything else.
- Prefer multiline `description` strings when the role has real boundaries or usage rules.
- State when to use the agent, what it is optimized for, and the non-negotiable rules.
- Avoid weak filler such as "helps with tasks" or "assists with work."
- Aim for the clarity and authority of the built-in agents: clear trigger, clear strengths, clear rules.

## Developer Instructions Quality Bar

- Use `developer_instructions` to turn the role contract into operational behavior.
- Complement the `description`; do not just repeat it.
- State execution priorities, output expectations, and what evidence or validation matters.
- For write-capable roles, assign ownership, say the agent is not alone in the codebase, and forbid reverting unrelated edits.
- For read-only roles, explicitly say not to edit code or mutate artifacts unless the user asks.

## Configuration Rules

- Always write `name`, `description`, and `developer_instructions`.
- Omit optional fields unless the brief or environment clearly justifies them.
- By default, let `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, and `skills.config` inherit from the parent session.
- Pin `sandbox_mode` only when the role clearly needs a stricter or broader surface.
- Add `nickname_candidates` only when the user is likely to run many copies of the same agent and wants clearer UI labels.
- Do not create or modify `.codex/config.toml` unless the user explicitly asks for global agent settings too.

## Default Behavior

- Ask at most one clarification only when a concrete missing value blocks correctness or safety.
- Otherwise proceed with conservative defaults.
- Synthesize the contract directly from the brief. Do not force the request into prewritten examples or category tables.
- Do not invent MCP URLs, credentials, filesystem paths, or skill paths.
- Do not add optional integrations just because they would be nice to have.
- Keep both text fields specific, high-signal, and grounded in the user's own brief.

## Response

- If you wrote the file, report the output path and a one-line summary of the agent's job.
- If the user asked for a preview, return the TOML and intended path without writing.
- Do not spawn the new agent unless the user explicitly asks.
- For write-capable roles, mention the ownership boundary or the files the new agent should leave untouched.
