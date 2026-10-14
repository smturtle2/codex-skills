# claude

Send work to an already-running Claude Code session through its inbox and read that session's replies to use Claude as a Codex subagent.

[All skills](../../README.md#skills) · [한국어](claude.ko.md)

## Installation

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## Requirements and preparation

The skill supports local Linux Claude Code sessions owned by the same user. It
uses uv and Python 3.11 or later; its locked history-reading dependency is
`claude-agent-sdk==0.2.166`. Claude Code `2.1.299` and native peer protocol `1`
are the initial compatibility baseline.

Open Claude Code separately and leave the intended session running. For
unattended delivery, choose `/config` → `Messages from your other sessions` →
`accept` in Claude. The skill discovers the session's existing inbox and does
not start Claude, change its settings, or recreate a closed session. An open
session without a usable inbox is unavailable.

## Use

Ask naturally: “Use $claude to ask the open session in this project to examine
the parser and read its response.” The calling Codex determines the task and
instructions and assesses the result. The skill handles the connection,
delivery, and observations.

Set `SKILL_DIR` to the installed skill's absolute path and run from the calling
project's root:

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

Identify the session by name and working directory, then use its exact
`target.session_id` from an available row. Write the task to a UTF-8 file and
choose a unique run directory:

```sh
SESSION_ID="<listed session ID>"
RUN_DIR=".codex-skills/claude/<unique-id>"

uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" send \
  --session "$SESSION_ID" --message-file request.txt \
  --expect-reply --run-dir "$RUN_DIR"

uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" wait \
  "$RUN_DIR" --timeout 30
```

`--expect-reply` adds a technical response marker while preserving the task text.
Claude is asked to write its answer normally in that session, wrapped in
`<codex-reply request-id="UUID">...</codex-reply>`. This lets the reader distinguish
the answer from other input and output in the shared conversation. It does not
impose a task format or decide whether the work succeeded.

| Command | Purpose |
| --- | --- |
| `sessions` | List live candidates and connection availability |
| `send --session ID --message-file PATH` | Save and send one message; optional `--expect-reply` and `--run-dir` |
| `status RUN_DIR` | Refresh target availability and saved observations |
| `read RUN_DIR` | Read newly observed replies without waiting |
| `wait RUN_DIR --timeout N` | Poll for changes until an N-second deadline; N is 0–60 |

Waiting returns early for a matching reply, ambiguous matches, or a session
waiting for input. Without `--expect-reply`, newly observed readable output also
ends the wait. An early return does not decide whether the work is complete.
An in-flight discovery or history read can finish after the polling deadline.

A follow-up uses the same live session ID with a new message and run directory.
Observation commands reuse the original run directory. Paths mentioned in the
task refer to the target's machine and working directory; messages do not attach
files or transfer Codex's conversation context.

## Results and recovery

The runtime separately reports session availability, transport observations,
input UUID observation, and response matching. Socket writing has no native
message ACK. A write is not proof of arrival, and a matching reply is not a
judgment that the task is complete. Replies are read through the SDK's history
API, without SDK inference or terminal scraping.

Every target access revalidates the exact session, process start, and inbox,
including the socket identity and actual listener PID and user ID. A
closed or changed target returns `session_unavailable`; the reader does not use
archived history or switch to a same-named session. Missing or ambiguous reply
markers and `history_gap` remain explicit observations. A timeout ends only the
wait, not Claude's ongoing work.

New or revised assistant text appears in `responses`; the saved request retains
the accumulated evidence. `matched_response` is reevaluated across current
response revisions, so conflicting replies or edits can invalidate an earlier
match.

After a write may have started, the same saved request is never automatically
resent. Repeating `send` with that run directory only observes the existing
request. Use `status`, `read`, or `wait` for recovery. Inbound `hold` or `refuse`
may prevent an input from appearing, and the skill does not change those
settings. The inbox cannot forcibly interrupt Claude's running tools.

Transmission or observation errors for a valid loaded request include `run_dir`,
`request_id`, and the latest evidence states. Keep that path and use it for recovery, including when the
initial `send` failed.

## Working files

Use the project-root-relative `.codex-skills/claude/<unique-id>/` unless the user
chooses another location. Omitting `--run-dir` creates a unique default directory.
Keep an existing request at its saved path for observation and recovery. Retain
unconfirmed runs and remove only expendable intermediates from your own work.
In Git projects, ignore `/.codex-skills/` unless execution records are intended
to be versioned.

For the skill instructions, see [SKILL.md](../../skills/claude/SKILL.md). For the
native framing, public/private contract boundaries, and troubleshooting, see
the [inbox contract](../../skills/claude/references/inbox-contract.md).
