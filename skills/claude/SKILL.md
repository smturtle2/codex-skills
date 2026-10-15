---
name: claude
description: Exchange messages with an already-running local Claude Code session and inspect its history on demand. Use for delegated work, questions, and coordination.
---

# Claude

Exchange messages with an open Claude Code session. The helper manages discovery, the connection, delivery, receiving, and cleanup, and relays message content unchanged. The caller decides what to send and how to interpret and present received messages.

Supports same-user local Linux sessions. Claude must already be running with a usable inbox; the user prepares its inbound settings. No live target means `session_unavailable`: do not launch, resume, fork, or substitute an archived conversation. See [native compatibility](references/inbox-contract.md#native-compatibility) for supported versions and inbox requirements.

Set `SKILL_DIR` to this skill's absolute directory and run from the calling project's root. The helper creates a new `.codex-skills/claude/<unique-id>/` for each connection. Use `--run-dir <new-directory>` for another location; an existing directory cannot be restarted. In Git projects, ensure `/.codex-skills/` is ignored unless the records should be versioned.

## Find and connect

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" sessions
```

Identify the target by name and working directory, then use the exact `target.session_id` from an available row. Discovery verifies the process and inbox; a CLI listing alone can include a finished session.

Run `connect` in a **retained host execution session with writable stdin**:

```sh
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/claude.py" connect \
  --session "$SESSION_ID"
```

Keep that execution session's identifier for both controls and output collection. `connect` stays in the foreground. Use a PTY if the host requires one to retain stdin. Keep its input channel open while the connection is needed, and wait for `connected` before sending messages.

## Send and receive

Write one UTF-8 JSON object followed by a newline to the retained process's stdin. Supply the caller's message unchanged:

```jsonl
{"type":"send","message":"Review the parser and report the problems you find."}
{"type":"send","message":"Focus on malformed input; leave the files unchanged."}
```

Send follow-ups through the same connection. Collect asynchronous JSONL output in bounded waits from that same execution session while continuing other work.

Claude uses native `SendMessage` to the sender's return address supplied in the incoming message. The helper emits that content as `message` events. Ordinary text in Claude's own conversation is not received. Send and receive independently on the same connection. Either side may send multiple messages without waiting for a reply; messages do not need to correspond one-to-one.

`sent` reports socket-write state; `delivery_status` relays native delivery notices. Neither establishes task completion. Do not automatically replay an uncertain transmission. Read [controls and events](references/inbox-contract.md#controls-and-events) for event fields and [transmission and delivery](references/inbox-contract.md#transmission-and-delivery) for UUID deduplication and delivery notices.

Paths in messages refer to the target's machine and working directory. Messages do not attach files or transfer the caller's conversation context.

## Disconnect

When the connection is no longer needed, send:

```jsonl
{"type":"disconnect"}
```

Disconnect, owner-channel closure, or loss/change of the exact bound target ends the helper and removes its inbox. `/clear` and `/new` start a new session; restarting Claude also ends the old connection, even if it resumes the same session ID. Select an open target explicitly to reconnect. The helper does not terminate Claude or switch to another session automatically.

Claude's `idle` or `waiting` state, an output-wait timeout, and a caller's chat turn ending do not by themselves close it. `closed` ends normal message delivery; collect output until the helper process exits because cleanup errors can follow. See [connection lifetime](references/inbox-contract.md#target-and-connection-lifetime) for exit codes and [records and recovery](references/inbox-contract.md#records-and-recovery) for retained evidence or output not collected from stdout.

## Optional history inspection

Inspect conversation context explicitly when useful:

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

This one-shot command requires a live selected target and the optional SDK. It returns the latest visible user/assistant text messages as standalone JSON, defaulting to 10. It does not require or affect an active connection. Connecting, sending, and receiving require no SDK or history reads. Do not invoke history automatically because Claude is silent or a delivery notice is absent. See [history inspection](references/inbox-contract.md#history-inspection) for its output and filtering rules.
