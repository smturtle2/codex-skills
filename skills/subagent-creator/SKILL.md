---
name: subagent-creator
description: Create or update one high-quality Codex custom subagent directly from a raw task brief. Use when Codex needs to write or revise a `~/.codex/agents/*.toml` or `.codex/agents/*.toml` file, especially when the role should be synthesized zero-shot from the user's task instead of chosen from canned templates.
---

# Subagent Creator

Create or update one high-quality Codex custom agent directly from the user's brief.

Read [references/custom-agent-schema.md](references/custom-agent-schema.md) for the file schema and inheritance rules. Read [references/quality-rubric.md](references/quality-rubric.md) for the quality bar the finished agent definition should meet. When the environment allows it, run `scripts/validate_agent_toml.py` on the finished TOML before returning a preview or writing the file.

## Happy Path

User request:

```text
Use $subagent-creator to create a read-only dependency audit agent.
```

Skill behavior:

1. Distill the brief into one focused role contract.
2. Choose a user-scoped path such as `~/.codex/agents/dependency-audit.toml` unless the user asks for project scope.
3. Write exactly one TOML file with `name`, `description`, and `developer_instructions`.
4. Validate the TOML when possible, then report the path, scope, and role boundary.

## Operating Stance

- Treat the user's brief as source material, not as a category label.
- Default to a global user-scoped agent under `~/.codex/agents/`.
- Preserve zero-shot synthesis. Use decision rules and schema constraints instead of canned role examples.
- Generate exactly one agent file unless the user explicitly asks for multiple agents.

## Core Rule

- Derive the agent contract from the actual job, boundaries, collaboration mode, and output expectations in the brief.
- Do not snap to a canned roster of explorer, reviewer, fixer, or researcher roles unless the brief itself clearly asks for one.
- Preserve the user's domain language when it carries important meaning.

## Request Modes

- `create`: make a new agent file from the brief.
- `update`: read the existing agent file first, then change only what the new brief requires.
- `preview`: return the intended path and TOML without writing.
- If the user asks to update an agent that you cannot uniquely identify, spend the one clarification on locating the target instead of guessing.

## Workflow

1. Determine whether the request is `create`, `update`, or `preview`.
2. Distill the brief into a role contract.
3. Choose the output scope and path.
4. Derive a concrete agent name and collision strategy.
5. Decide which optional fields are justified.
6. Draft or update the TOML.
7. Run the self-check and validator.
8. Save the file or return a preview, then report the scope, path, and role boundary.

## Role Contract

Before you write, answer these questions from the brief itself:

- When should this agent be used?
- What is it optimized to do better than the parent agent?
- What must it avoid doing?
- If it can edit, what does it own and what must it not touch?
- What should it return, prioritize, or validate?
- Which responsibilities are essential, secondary, or droppable?

## Scope And Path

- Default to user scope: `~/.codex/agents/<agent-name>.toml`.
- Use project scope: `.codex/agents/<agent-name>.toml` only when the user explicitly asks for a project-scoped agent.
- The global-first default is intentional. Prefer reusable personal agents over project-local ones unless the user explicitly wants project scoping.
- When you use the global default, keep the instructions reusable. Do not hardcode repo-specific paths, branch names, local conventions, or environment assumptions unless the user explicitly asks for them.
- Create the target directory if it does not exist.
- Match the filename to the `name` field when practical.

## Naming And Collisions

- Derive the name from the user's actual task nouns and verbs instead of reaching for stock names first.
- Prefer short lowercase names.
- Normalize newly generated names to ASCII lowercase with digits and hyphens. Preserve an existing explicit name on update unless the user asked to rename it.
- Built-in names `default`, `worker`, and `explorer` are reserved unless the user explicitly asks to override one of them.
- If the intended target already exists and the user did not ask for an update, do not overwrite blindly. Inspect the collision and use a deterministic nearby name such as `-2`, then `-3`, and so on.

## Multi-Role Briefs

- Make the role narrow and opinionated.
- If one primary role needs bounded secondary responsibilities to be usable, keep those secondary responsibilities.
- If the brief truly spans multiple independent roles, compress it to the primary role and explicitly say what was left out in the response or preview.
- Never silently drop validation, review, ownership, or safety constraints.

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
- For write-capable roles, assign ownership, say the agent is not alone in the workspace, and forbid reverting unrelated edits.
- For read-only roles, explicitly say not to edit workspace artifacts unless the user asks.

## Configuration Rules

- Always write `name`, `description`, and `developer_instructions`.
- Optional fields are allowed only when the brief or environment clearly justifies them and you know the exact TOML shape to write.
- If the exact shape of an optional field is uncertain, omit it instead of inventing syntax.
- By default, let `model`, `model_reasoning_effort`, `mcp_servers`, and `skills.config` inherit from the parent session.
- For pure research, review, or mapping roles, prefer explicitly setting `sandbox_mode = "read-only"` when the environment supports it.
- For write-capable roles, widen sandbox access only when the role clearly needs it.
- Add `nickname_candidates` only when the user is likely to run many copies of the same agent and wants clearer UI labels.
- Do not create or modify `.codex/config.toml` unless the user explicitly asks for global agent settings too.
- Do not invent MCP URLs, credentials, approval keys, filesystem paths, or skill paths.

## Clarifications And Conservative Defaults

- Ask at most one clarification when a missing detail would make the result unsafe, invalid, or too generic.
- Otherwise proceed with these defaults.
- Use user scope under `~/.codex/agents/`.
- Generate one focused agent file.
- Inherit optional fields unless there is a concrete reason to pin one.
- Omit `nickname_candidates` unless repeated runs are part of the brief.
- Omit `mcp_servers` and `skills.config` unless the brief or environment provides concrete values.
- Keep global agents reusable instead of embedding repo-specific assumptions.

## Update Rules

- Read the existing file before editing it.
- Preserve unrelated fields and explicit user choices.
- Change only what the new brief requires.
- Keep the existing name and path unless the user asked to rename or move the agent.
- If the brief changes the role boundary, make that change explicit in the response.

## Self-Check

Before previewing or writing:

- Confirm that you are producing exactly one TOML file and one intended path.
- Confirm that `name`, `description`, and `developer_instructions` are present and non-empty.
- Remove placeholder text such as `<...>` or `TODO`.
- Reject unknown top-level keys and invented approval settings.
- Check whether the filename and `name` still align.
- Omit optional fields whose exact values are not known.
- Recheck that the sandbox choice matches the role.
- Recheck that a global agent does not overfit to one repository unless the user asked for that.
- Validate that the TOML parses cleanly. Run `scripts/validate_agent_toml.py` when possible.

## Response

- If you wrote the file, report the output path, whether it is user-scoped or project-scoped, and a one-line summary of the agent's job.
- If you updated an existing file, summarize what changed and what was preserved.
- If the user asked for a preview, return the TOML and intended path without writing.
- If you dropped responsibilities to keep the role focused, say which ones were left out.
- Do not spawn the new agent unless the user explicitly asks.
- For write-capable roles, mention the ownership boundary or the files the new agent should leave untouched.
