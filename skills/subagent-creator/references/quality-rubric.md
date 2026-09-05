# Definition Acceptance

Use this brief check before delivery. Configuration syntax belongs in [custom-agent-schema.md](custom-agent-schema.md); consult it only for optional or unfamiliar settings.

## Request Fidelity

- Every separately requested role or variant has a definition; no extra roles or unrelated runtime changes.
- Names, responsibilities, priorities, and boundaries match the user's brief instead of a generic worker template.
- Updates retain unrelated valid configuration and the requested role partition.

## Role Usefulness

The description lets a parent decide when to use the role. Instructions explain its work, ownership, evidence, output, and completion criteria without merely repeating the description.

Write-capable roles respect shared-workspace edits. Read-only roles prohibit mutation. Personal roles avoid unrequested environment-specific assumptions.

## Validation Evidence

Each candidate passes available validation, and warnings are reviewed. Report local-only checks honestly when native validation is unavailable.

Treat naming conventions and placeholder-like words as review signals, not automatic runtime failures: legitimate role prose may contain `TODO` or XML tags. Accept deliberate built-in overrides when authorized, without inventing a separate approval gate.

Deliver only when the requested definitions are present and valid under the checks performed; otherwise identify the missing responsibility or validation blocker.
