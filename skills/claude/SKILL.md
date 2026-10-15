---
name: claude
description: Use an already-running local Claude Code session as a subagent through a persistent connection that sends instructions and relays its messages. Requires a live session; does not launch Claude.
---

# Claude

Connect to an open Claude Code session and exchange messages while it works.
This skill owns discovery, the connection, delivery, receiving, and shutdown.
The caller supplies the work and instructions and interprets Claude's output.

Supports same-user local Linux sessions. Set `SKILL_DIR` to this skill's absolute
directory and run from the calling project's root. Claude must already have a
usable inbox. The user prepares its inbound settings; the skill does not change
them. No live target means `session_unavailable`: do not launch, resume, fork,
or substitute an archived conversation.

## Find and connect

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

Identify the target by name and working directory, then use the exact
`target.session_id` from an available row. Discovery verifies the process and
inbox; a CLI listing alone can include a finished session.

Start the following command in a **retained host execution session with writable
stdin**. Keep that execution session's identifier to send controls and collect
output from the same process.

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" connect \
  --session "$SESSION_ID" --run-dir "$CONNECTION_DIR"
```

Wait for `connected` before sending work. `connect` stays in the foreground;
it is not a one-shot shell command. If the host requires a PTY to retain stdin,
use one; the helper disables terminal echo and canonical input limits. A pipe
that closes after supplying one command also closes the connection.

Use `.codex-skills/claude/<unique-id>/` for each connection unless the user gives
another location; omitting `--run-dir` creates a unique default path. Existing
run directories cannot start a new connection. In Git projects, ignore
`/.codex-skills/` unless execution records should be versioned.

## Send and receive independently

Write one UTF-8 JSON object followed by a newline to the retained process's
stdin. Supply the caller's message unchanged:

```jsonl
{"type":"send","message":"Review the parser and report the problems you find."}
{"type":"send","message":"Focus on malformed input; leave the files unchanged."}
```

A follow-up uses the same connection. An optional `uuid` identifies a
transmission for deduplication within this connection; repeating the same UUID
and text never resends it. It does not pair an input with Claude's output.

Read asynchronous JSONL events from stdout while continuing other work. Keep
host output waits under 60 seconds, then resume collecting from the same
execution session. Poll timeouts and Claude's `idle` or `waiting` state leave
the connection open.

Claude sends reports and questions through native `SendMessage` to the sender's
return address, supplied in the incoming message. `message` events relay those
messages with `seq`, `connection_id`, `session_id`, `source: "peer"`, `uuid`, and
`content`. Ordinary text in Claude's own conversation is not received by the
connection. Connecting, sending, and receiving require no SDK or history reads.
Forward the content as received. There may be multiple outputs for one
instruction or one output after several instructions. Do not require a reply
tag, match outputs to inputs, or treat an event as proof of task completion.

`sent` reports a socket-write outcome; transmission failures use `error` with
the same UUID and transport state. `delivery_status` relays verified native
transport notices such as held, refused, or dropped messages. Its `orig_msg_id`,
when present, identifies a transmission, not a Claude reply. A `delivered` notice
means a held message was released to Claude, not that work finished. A successful
write or absent notice does not prove admission. Do not automatically replay an
uncertain transmission. Other `error` events report connection or command
failures. `closed` ends the connection and normal message delivery. Keep
collecting until the helper exits: final cleanup errors can follow `closed`,
and the process exit code reports the final outcome.

Paths in messages refer to the target's machine and working directory. Inbox
messages do not attach files or transfer the caller's conversation context.

## Inspect history only when needed

History inspection is a separate, optional one-shot command:

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

It requires a live selected target and the optional SDK dependency. It returns
the latest visible user/assistant text messages as standalone JSON, with a
default limit of 10. It does not feed connection events or affect an active
connection. Do not invoke it automatically because Claude is silent or a
delivery notice is absent. See the
[inbox contract](references/inbox-contract.md#optional-history-inspection) for
the output and filtering rules.

## Close the connection

When the connection is no longer needed, send:

```jsonl
{"type":"disconnect"}
```

Explicit disconnect, stdin EOF, `SIGINT`/`SIGTERM`/`SIGHUP`, or loss/change of the
exact bound Claude session end the helper and clean up its own inbox. The helper
binds both the chosen session ID and its process. `/clear` or `/new` starts a new
session and closes the old connection; stopping or restarting the process also
ends it, even if the new process resumes the same session ID. Reconnect only by
explicitly selecting an open target and starting a new connection. The helper
does not terminate Claude. Do not replace a lost target with a same-named session.
Keep the host's actual control channel open for as long as the connection is needed;
a chat turn ending is not a reliable process-lifetime signal.

Exit codes are `0` for normal caller/owner closure, `3` for target loss/change or
unsupported targets/environments, and `1` for helper execution, recording, or
cleanup failure. A local failure takes precedence even after a disconnect or
target loss; the first close reason is preserved. Error reporting is best effort
if storage or output is unavailable.

The run directory preserves `connection.json`, `events.jsonl`, and `outbox.json`
as connection evidence. A stopped helper does not replay them or read a closed
Claude session. Prior request directories remain untouched; the old
`send`/`status`/`read`/`wait` command API is no longer used.

Read [the inbox contract](references/inbox-contract.md) for event semantics,
native framing, compatibility, and lifecycle details.
