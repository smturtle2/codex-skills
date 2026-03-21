# Brief Patterns

Use this reference when a user gives a short task brief and you need to turn it into one narrow custom agent zero-shot.

## Default decision rule

- Create one agent, not a bundle.
- Choose the single role that best matches the dominant job in the brief.
- Prefer conservative optional fields.
- Default output path is `~/.codex/agents/<agent-name>.toml`.

## Common patterns

### Codebase exploration

Use a mapper or explorer-style role when the brief is about tracing code paths, locating ownership, or gathering evidence.

- Good names: `code-mapper`, `pr-explorer`, `ownership-mapper`
- Usual posture: read-only if you pin a sandbox at all
- Instruction style: trace execution paths, cite files and symbols, avoid proposing fixes unless asked

### Review and risk finding

Use a reviewer-style role when the brief is about correctness, regressions, security, or test gaps.

- Good names: `reviewer`, `security-reviewer`, `test-reviewer`
- Usual posture: read-only
- Instruction style: lead with findings, prioritize real bugs and missing coverage, avoid style-only comments

### Documentation research

Use a docs researcher when the brief is about verifying APIs or framework behavior.

- Good names: `docs-researcher`, `api-verifier`
- Usual posture: read-only
- Instruction style: use primary docs, return concise references, do not edit code
- Add `mcp_servers` only when a concrete server is already available

### Focused implementation

Use a fixer or implementer when the brief is about making a bounded code change.

- Good names: `ui-fixer`, `bug-fixer`, `migration-fixer`
- Usual posture: inherit parent settings unless a stricter sandbox is clearly better
- Instruction style: own one fix, keep changes minimal, validate only changed behavior, avoid unrelated edits

### Reproduction and debugging

Use a debugger when the brief is about reproducing a UI or integration issue and gathering evidence.

- Good names: `browser-debugger`, `integration-debugger`
- Usual posture: inherit unless the tool surface requires something concrete
- Instruction style: reproduce first, capture exact behavior, separate evidence gathering from implementation

## Optional field heuristics

### Model and reasoning

- Omit both fields by default and inherit from the parent session.
- Reach for `gpt-5.4` when the child agent needs deeper multi-step reasoning.
- Reach for `gpt-5.4-mini` when the role is read-heavy, exploratory, or optimized for fast parallel scans.
- Pin higher reasoning effort only for roles that need careful tracing, review, or risk analysis.

### Sandbox and integrations

- Omit `sandbox_mode` unless the role clearly needs an explicit read-only or write posture.
- Add `nickname_candidates` only when repeated spawns would benefit from readable labels.
- Add `mcp_servers` or `skills.config` only when the environment already gives you concrete names, URLs, or paths.

## Instruction writing heuristics

- Start with the agent's primary job.
- State what to prioritize.
- State what evidence or output to return.
- State one or two key boundaries such as "do not edit code" or "keep unrelated files untouched."
- For write-capable agents, tell the child that it is not alone in the codebase and it must avoid reverting unrelated edits.

## Zero-shot fallback

If the brief is underspecified but still workable:

- infer one dominant role
- omit optional fields
- write the smallest correct TOML
- report the chosen path and role briefly

Ask one clarification only when the agent would otherwise require a concrete missing value, such as a specific MCP server URL or an explicit write surface that materially changes safety.
