# Quality Rubric

Use this reference to judge whether a generated subagent was actually synthesized from the user's brief instead of snapped to a canned template.

## Source of truth

- The user's brief is the source of truth.
- The generated role should reflect the user's actual nouns, verbs, boundaries, and priorities.
- Novel requests should stay novel. Do not rename them into a stock category unless the brief clearly asks for that category.
- The global-first default is also part of the contract. A generated agent should remain reusable unless the user explicitly asks for project scoping or repo-specific hardcoding.

## Quality bar

A good custom agent definition should feel as clear and opinionated as the built-in agents.

- A caller should know exactly when to use it.
- A caller should know what the agent is optimized for.
- A caller should know the rules the agent must follow.
- The wording should feel specific to the task, not copied from a generic role library.
- The file should be valid TOML with no invented configuration.

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
- For write-capable agents, assign ownership and say the agent is not alone in the workspace.
- For read-only agents, explicitly forbid code edits or other mutations.

## Configuration rubric

- Required fields are present and non-empty.
- Optional fields appear only when they are justified and correctly formed.
- Pure research, review, or mapping roles should not get broad sandbox access without a clear reason.
- A global user-scoped agent should not be packed with one repo's paths, branches, or team-specific conventions unless the user explicitly asked for that.

## Update rubric

- An update reads the current file before changing it.
- The result preserves unrelated user choices.
- The response says what changed instead of silently rewriting the whole contract.

## Validation rubric

- The file parses as TOML.
- The file does not include placeholder markers such as `<...>` or `TODO`.
- The file does not use undocumented top-level keys or invented approval settings.
- The filename and `name` should align unless there is a deliberate reason not to.

## Failure modes

The result is too generic if it:

- uses filler like "helps with tasks"
- could apply equally well to many unrelated briefs
- defaults to a stock role name even though the brief is more specific
- omits explicit boundaries or collaboration rules
- repeats the same shallow sentence in both `description` and `developer_instructions`
- silently drops a required responsibility to force the brief into one role
- rewrites an existing agent destructively during an update
- emits invalid TOML
- invents optional field syntax
- hardcodes repo-specific assumptions into a default global agent without being asked

## Final gate

Before accepting a generated agent, confirm all of the following:

- The role is clearly derived from the brief.
- The scope and path are intentional and stated.
- The boundary is explicit.
- The configuration is justified and valid.
- The file passes TOML validation.
