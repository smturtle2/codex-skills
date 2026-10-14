---
name: claude
description: Use an already-running local Claude Code session as a subagent through its inbox and read its replies. Requires a live session; does not launch Claude.
---

# Claude

Use an open Claude Code session to perform work supplied by the calling agent.
This skill owns session discovery, inbox delivery, and reply observation; the
caller supplies the work and instructions and interprets the result.

Supports same-user local Linux sessions. Set `SKILL_DIR` to this skill's absolute
directory and run from the calling project's root. Claude Code must already be
running with a usable inbox. The user prepares its inbound settings; the skill
does not change them. No live target means `session_unavailable`: do not launch,
resume, fork, or substitute an archived conversation.

## Find the target

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

Identify the target by its displayed name and working directory, then use its
exact `target.session_id` from an available row. Discovery verifies the actual
process and inbox; a row in `claude agents --json` alone can refer to a finished
session. Once a request is
saved, it stays bound to that session, process start, working directory, and
inbox. Never replace it with a same-named session.

## Send and read

Write the caller's task to a UTF-8 file. Paths in the task refer to the target
session's machine and working directory; inbox messages do not attach files or
transfer the calling conversation's context.

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" send \
  --session "$SESSION_ID" --message-file request.txt \
  --expect-reply --run-dir "$RUN_DIR"

uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" wait \
  "$RUN_DIR" --timeout 30
```

Use `--expect-reply` when the caller needs a corresponding answer. It preserves
the task text and adds a technical instruction to wrap the normal assistant
reply in `<codex-reply request-id="UUID">...</codex-reply>`. Omit it for a
message whose reply will be read without request matching. A follow-up is a new
message to the same live session with a new run directory, not a resend of the
previous request.

`wait --timeout` accepts 0–60 seconds as a polling deadline; an in-flight
discovery or history read can finish after that deadline. Continue other work
between waits, or use `read "$RUN_DIR"` for an immediate observation. `status "$RUN_DIR"`
refreshes the target and saved evidence. These commands do not send messages or
start Claude. Every observation revalidates the live target; if it closes,
observation stops with `session_unavailable`.

Waiting returns when a reply matches, matches are ambiguous, or Claude is
waiting for input. Without `--expect-reply`, new readable output also ends the
wait. Inspect the evidence; an early return does not establish task completion.

Use `.codex-skills/claude/<unique-id>/` for each new message unless the user gives
another location; omitting `--run-dir` creates a unique default path. Use the
same saved path for observation and recovery. In a Git project, ensure
`/.codex-skills/` is ignored unless the user intends to version execution data.

## Interpret the evidence

Transport, input, and response observations are separate. Socket writing has no
ordinary message acknowledgement; a write does not prove delivery. Input is
observed by its UUID in Claude's native record. Replies are read through the
Agent SDK's history API, without starting inference. Shared sessions can contain
interleaved user input and multiple tasks: a recent assistant message or an idle
session does not identify this request's answer or prove task completion.

After a write may have begun, repeating `send` with its saved run directory only
observes the existing request. Never replay an uncertain send. Keep unconfirmed
runs and use `status`, `read`, or `wait` to recover observations. Report a missing
reply, ambiguous match, or history gap as such instead of inferring an answer.

Transmission or observation errors for a valid loaded request include its
`run_dir`, `request_id`, and latest evidence states for recovery. `responses` contains new or revised text
from that observation; `matched_response` is evaluated against the accumulated
evidence. Revisions can invalidate a previously matched reply.

For wire framing, version compatibility, inbound controls, evidence states, and
failure recovery, read [the inbox contract](references/inbox-contract.md).
