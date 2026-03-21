# Zero-Shot Rubric

Use this reference to judge whether a generated subagent was actually synthesized from the user's brief instead of snapped to a canned template.

## What zero-shot means here

- The user's brief is the source of truth.
- The generated role should reflect the user's actual nouns, verbs, boundaries, and priorities.
- Novel requests should stay novel. Do not rename them into a stock category unless the brief clearly asks for that category.

## Quality bar

A good custom agent definition should feel as clear and opinionated as the built-in agents.

- A caller should know exactly when to use it.
- A caller should know what the agent is optimized for.
- A caller should know the rules the agent must follow.
- The wording should feel specific to the task, not copied from a generic role library.

## Description rubric

The `description` should answer three things:

1. When to use the agent.
2. What it is good at.
3. What rules define its boundary.

Prefer multiline `description` values when a single sentence would flatten the role too much.

Good descriptions usually include:

- an explicit usage trigger such as "Use `<name>` for ..."
- a short capability statement
- a `Rules:` section with 2-6 non-negotiable bullets

## Developer instructions rubric

The `developer_instructions` should make the role executable.

- State what to prioritize.
- State what evidence, output, or validation matters.
- State what not to do.
- For write-capable agents, assign ownership and say the agent is not alone in the codebase.
- For read-only agents, explicitly forbid code edits or other mutations.

## Failure modes

The result is too generic if it:

- uses filler like "helps with tasks"
- could apply equally well to many unrelated briefs
- defaults to a stock role name even though the brief is more specific
- omits explicit boundaries or collaboration rules
- repeats the same shallow sentence in both `description` and `developer_instructions`

## Generic skeleton

Use this as a shape check, not as content to copy literally:

```toml
name = "derived-from-brief"
description = """
Use `derived-from-brief` for <clear trigger from the user's brief>.
<Specific statement of strengths and scope>.
Rules:
- <boundary or prioritization rule>
- <boundary or collaboration rule>
"""
developer_instructions = """
<Operational priorities>.
<Evidence, validation, or output expectations>.
<What the agent must not do>.
"""
```
