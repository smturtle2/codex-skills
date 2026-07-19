# Quality Rubric

Use this reference to judge whether every requested custom subagent definition is focused, faithful to the brief, and honestly validated.

## Request Fidelity

- Treat the user's brief as the source of truth.
- Produce the number of definitions the user requested; do not impose a fixed cardinality.
- Preserve the requested role partition, including explicitly requested variants of the same responsibility. Do not merge separate definitions or invent extra ones by splitting a coherent request.
- Preserve the user's domain language, boundaries, priorities, and output requirements.
- Avoid replacing a novel responsibility with a canned explorer, reviewer, fixer, or researcher template.

## Role Quality

For each definition, confirm that a parent can tell:

1. when to use the role
2. what the role is optimized to do
3. what the role must not do
4. what evidence, validation, and output it returns

Use `description` for selection guidance and `developer_instructions` for execution behavior. Do not repeat the same shallow sentence in both.

For write-capable roles, assign ownership, acknowledge other contributors, and forbid reverting unrelated edits. For read-only roles, explicitly forbid workspace and external-system mutation.

## Configuration Quality

- Include all required metadata and keep it non-empty.
- Omit optional configuration by default.
- Add an optional key only when justified and verified against current Codex syntax.
- Treat sandbox and approval values as defaults that may be superseded by live parent permissions.
- Keep personal definitions reusable unless the user explicitly supplies role-specific environment assumptions.
- Never invent models, MCP endpoints, credentials, paths, approval settings, or skill selectors.

## Runtime Validity Versus Authoring Preference

- Runtime validity requires parseable TOML, required metadata, supported config shapes, and valid nickname data.
- ASCII lowercase hyphenated names and matching filenames are authoring preferences, not Codex validity requirements.
- Built-in names are valid overrides but require deliberate intent.
- Literal strings such as `TODO` or XML tags may be legitimate role content; treat placeholder-like text as a review warning rather than an automatic schema failure.

## Update Quality

- Read every existing target first.
- Change only what the new brief requires.
- Preserve unrelated supported configuration and explicit choices.
- Never delete an unfamiliar key merely to satisfy a frozen local allowlist.
- Report changed boundaries, preserved configuration, and any current-Codex validation blocker.

## Validation Quality

- Validate every generated or updated definition independently.
- Treat local parse and schema errors as blockers.
- Use native Codex checking when available for the full configuration layer.
- Distinguish full native validation from local-only validation in the response.
- Do not claim success when Codex would ignore the role as malformed.

## Final Gate

Accept the result only when:

- every explicitly requested role has a corresponding definition
- no unrequested roles or runtime configuration were added
- each role boundary is focused and operational
- optional configuration is minimal and justified
- updates preserve unrelated valid state
- every file passes available validation, with unresolved warnings disclosed
