# claude

Use an already-running Claude Code session as a subagent through a persistent
connection. Send instructions and receive its reports and questions independently.

[All skills](../../README.md#skills) · [한국어](claude.ko.md)

## Installation

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## Requirements and preparation

Supports same-user local Linux Claude Code sessions. Uses uv and Python 3.11 or
later. The compatibility baseline is Claude Code `2.1.299` and native peer
protocol `1`. Connecting and exchanging messages require no SDK; optional
history inspection uses `claude-agent-sdk==0.2.166` through the `history` extra.

Open Claude separately and keep the intended session running with a usable
inbox. For unattended delivery, choose `/config` →
`Messages from your other sessions` → `accept` in Claude. The skill discovers
that inbox and owns the connection; it does not start Claude or change its
settings. No open usable session means unavailable.

## Use

Ask naturally: “Use $claude to connect to the open session in this project and
ask it to review the parser.” The caller supplies instructions and interprets
results. The skill handles discovery, delivery, receiving, and shutdown.

Set `SKILL_DIR` to the installed skill's absolute directory and run from the
calling project's root:

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

Identify the session by name and working directory. Use its exact
`target.session_id` from an available row, then start a connection in a retained
host execution session with writable stdin:

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" connect \
  --session "$SESSION_ID" --run-dir "$CONNECTION_DIR"
```

The command stays in the foreground. Retain its execution session identifier,
wait for `connected`, and write JSONL controls to that same process:

```jsonl
{"type":"send","message":"Review the parser and report the problems you find."}
{"type":"send","message":"Also consider malformed input; leave the files unchanged."}
```

Follow-ups use the same connection. An optional `uuid` provides transmission
deduplication within the connection; repeating the same UUID and text returns
its saved outcome without resending. It does not pair a message with a response.

Read stdout JSONL events while doing other work. `message` events carry the
selected `session_id`, `connection_id`, `seq`, `source: "peer"`, `uuid`, and
`content`. Claude sends reports and questions through native `SendMessage` to
the sender's return address in the incoming message. Ordinary text left in
Claude's own conversation is not received by the connection. Content is
forwarded without reply tags, input/output matching, or task-completion judgment.
`sent`, `error`, and `closed` report transport and connection events.
`closed` ends normal message delivery; collect until the helper exits to receive
any final cleanup errors and its final exit code.

`delivery_status` events relay verified native transport notices such as held,
refused, or dropped messages. `orig_msg_id`, when present, refers to a
transmission, not a Claude reply. `delivered` means a held message was released
to Claude, not that it was read or its work completed. Not every accepted
message receives a notice; a successful `sent` or absent notice does not prove
admission. These notices do not cause automatic retries.
They arrive through the same return inbox as Claude's messages.

Keep host output waits under 60 seconds and resume collecting from the same
execution session. A poll timeout, Claude turn ending, `idle`, or `waiting`
does not end the connection. If a PTY is needed for writable retained stdin,
the helper disables echo and canonical input limits.

Paths in instructions refer to the target's machine and working directory.
Messages do not attach files or transfer the caller's conversation context.

## Optional history inspection

Inspect the selected open session's recent conversation separately when needed:

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

`--limit` is a positive integer and defaults to `10`. The command validates the
live target before and after reading. It returns one JSON object with
`type: "history"`, `session_id`, `cwd`, `limit`, `messages`, and `truncated`. Each
message has `type` (`user` or `assistant`), `uuid`, and `content`. It selects the
last requested number of nonempty visible text messages in chronological order,
preserving text and excluding thinking and tool blocks. `truncated` indicates
that the limit omitted earlier visible messages.

The command neither opens nor requires a persistent connection. Its output is
not mixed into connection events, and a failed inspection does not affect an
active connection. History is not polled or automatically inspected because
Claude is silent or a delivery notice is absent. A closed session cannot be
used as a fallback.

## Lifetime and records

Close the connection by sending:

```jsonl
{"type":"disconnect"}
```

Disconnect, stdin EOF, `SIGINT`/`SIGTERM`/`SIGHUP`, or loss/change of the exact
target end the helper and clean up its own return inbox. The helper does not
terminate Claude.
The helper binds the selected session ID, process, working directory, and
inbox. `/clear` or `/new` starts a new session and ends the old connection.
Stopping or restarting Claude also ends it, even if a new process resumes the
same session ID. Select a live target explicitly and start a new connection to
reconnect. The helper does not switch targets or continue reading a closed one.
The host's actual input channel must remain open while the connection is needed.

The first close reason is preserved. Exit code `0` means normal caller/owner
closure; `3` means target loss/change or an unsupported target/environment.
Helper execution, recording, or cleanup failure yields `1`, taking precedence
even after disconnect or target loss. Unexpected main-loop exceptions report
`internal_error`; errors are best effort if storage or output is unavailable.

Each connection has a new directory, defaulting to
`.codex-skills/claude/<unique-id>/`. It preserves `connection.json`,
`events.jsonl`, and `outbox.json` as local evidence. Existing run directories
cannot restart a connection or replay messages. Prior request directories are
left unchanged; the former `send`/`status`/`read`/`wait` API is removed.
Ignore `/.codex-skills/` in Git unless execution records should be versioned.

A successful socket write is not a native input acknowledgement. The helper
does not automatically retry uncertain writes, alter inbound controls, or
forcibly interrupt Claude's tools. Optional SDK use is limited to explicit
one-shot history inspection; no inference client is started. Claude's terminal
is not scraped.

See [SKILL.md](../../skills/claude/SKILL.md) for agent instructions and the
[inbox contract](../../skills/claude/references/inbox-contract.md) for framing,
event semantics, target identity, and compatibility details.
