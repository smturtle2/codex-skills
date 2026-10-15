# Inbox contract

## Controls and events

`connect --session ID [--run-dir PATH]` keeps one foreground helper open. The host retains its writable stdin and reads its stdout using the same execution session. If a PTY is needed to retain input, the helper disables echo and canonical input limits; it does not read Claude's terminal.

Stdin accepts UTF-8 JSONL, one control object followed by `\n`:

```jsonl
{"type":"send","message":"Inspect the implementation and report what you find."}
{"type":"send","uuid":"53fb2a6e-2ae2-4568-80d5-8d519a15642a","message":"Also consider concurrent edits."}
{"type":"disconnect"}
```

`send` accepts only `type`, `message`, and optional `uuid`. The message must be a string containing non-whitespace text. `disconnect` accepts only `type` and stops the connection, including queued messages not yet transmitted. Every control must fit within the 1,000,000-byte input limit.

Stdout contains asynchronous JSONL events. Normal events carry `type`, `seq`, `connection_id`, and the selected `session_id`, plus the fields below:

| Event | Additional fields and meaning |
| --- | --- |
| `connected` | `run_dir`, `target`, `reply_address`: the selected target and return inbox are ready |
| `message` | `source: "peer"`, `uuid`, `content`: Claude's native peer message, with its body unchanged |
| `sent` | `uuid`, `transport`: the observed transmission state; a repeated UUID also has `replayed: false` |
| `delivery_status` | `source: "peer"`, receipt `uuid`, `status`, and optional native fields described below |
| `error` | `error: {code, message}`; transmission failures also carry `uuid` and `transport` |
| `closed` | `reason`: normal message delivery has ended |

Claude sends content through native `SendMessage` to the helper's return address supplied in each incoming message. Ordinary text in Claude's own conversation does not reach this stream. The helper imposes no response format. The caller decides how to interpret and present received content.

Instructions and received messages are independent streams. Questions, updates, and results may arrive at any time while additional instructions are sent. Native message UUIDs deduplicate received events; repeated text alone does not make two messages the same event.

Invalid controls or rejected peer frames report errors without closing an otherwise usable connection. Target, return-listener, and record failures close the helper. Final cleanup errors can follow `closed`; collect output until the process exits. If recording is unavailable, best-effort emergency `error` output may lack `seq`. See [records and recovery](#records-and-recovery) for output that was not collected from stdout.

## Transmission and delivery

Omitting `send.uuid` generates a fresh UUID. A supplied UUID is normalized to canonical UUID form. Within the connection, repeating that UUID with the same text returns its saved state without sending again; different text produces `message_conflict`. A transmission UUID does not pair an input with Claude's output. There is no automatic retry or replay.

The helper saves each outbound message before transmission:

| Transport state | Meaning |
| --- | --- |
| `not_sent` | The message is recorded but its user frame has not begun writing |
| `write_started` | The helper is about to write, so some bytes may have reached the target |
| `written` | The socket write completed successfully |
| `delivery_unknown` | Bytes may have been sent without a known outcome |

`sent` reports a transport state, not admission by Claude. A transmission error carries the same UUID and its saved state. On shutdown, unfinished `write_started` entries become `delivery_unknown` and transmission records are frozen. Do not automatically replay an uncertain transmission.

Claude's messages and native delivery notices arrive through the same return inbox. A notice has its own native receipt UUID:

```json
{
  "type": "delivery_status",
  "seq": 3,
  "connection_id": "<connection-id>",
  "session_id": "<selected-session-id>",
  "source": "peer",
  "uuid": "<native-receipt-msg_id>",
  "status": "expired",
  "status_detail": "refused",
  "orig_msg_id": "<transmission-uuid>",
  "reason": "<native reason>"
}
```

Known `status` values are `held`, `denied`, `expired`, `delivered`, `refused`, and `dropped`. Optional fields are allowlisted and type-checked:

| Field | Accepted value |
| --- | --- |
| `status_detail` | `"refused"` with `status: "expired"` |
| `reason` | UTF-8 string |
| `orig_msg_id` | Native message UUID |
| `drop_reason` | With `dropped`: `rate-limited`, `duplicate`, `hop-loop`, `hop-runaway`, or `queue-full` |
| `dropped_msg_ids` | With `dropped`: a list of at most 256 native message UUIDs |

Allowed native values are preserved; absent fields are not synthesized. `delivered` means a held message was released to the receiving Claude. It does not establish that it was read or that work finished. There is no positive receipt for every initially accepted message; missing notices prove nothing about admission.

Notice transmission IDs need not exist in the local outbox. They describe native delivery, do not associate Claude's output with an input, and do not update saved socket-write states or trigger retries. Transport events do not establish task completion.

For unattended receipt, the user prepares Claude through `/config` → `Messages from your other sessions` → `accept`. The helper does not change this setting. `hold` or `refuse` can prevent admission despite a successful write. Claude still applies its tools and permissions. Paths and `@` mentions in a message do not attach resources, and inbox delivery cannot forcibly interrupt a running tool. See [Claude's messaging controls](https://code.claude.com/docs/en/cross-session-messaging).

## Target and connection lifetime

`sessions` lists verified candidates. Select an available row by name and working directory, and pass its exact `target.session_id` to `connect`. The helper binds one live conversation and process; it never launches Claude or selects a replacement automatically.

The helper continues checking the bound target even when Claude sends no messages. A changed or missing session, process, or inbox ends the connection. `/clear` and `/new` start a new session and end the old connection even if its process and inbox remain. Process shutdown or restart also ends it, even if a new process resumes the same session ID. Reconnecting requires explicit live target selection and a new connection.

Explicit `disconnect`, stdin EOF, `SIGINT`/`SIGTERM`/`SIGHUP`, unusable stdout, or target loss/change end the helper and clean up its own inbox. An unexpected worker failure also closes it. Claude is not terminated. Claude's turn ending, `idle`, `waiting`, host output-wait timeouts, and the caller's chat turn ending do not by themselves close the helper; its owner is the actual host process control channel.

The first close reason is preserved independently of the final exit code:

| Exit code | Meaning |
| --- | --- |
| `0` | Normal explicit disconnect or owner-channel closure |
| `3` | Selected target lost/changed, or unsupported target/environment |
| `1` | Helper execution, recording, or cleanup failure; takes precedence over `0` and `3` |

Unexpected main-loop exceptions report `internal_error`. A local failure during cleanup still produces exit `1` after disconnect or target loss. A late target-unavailable result after intentional disconnect does not turn that normal closure into failure. Errors are reported best effort when storage or output is no longer usable.

## History inspection

Inspect conversation context with a separate one-shot command:

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

`--limit` must be a positive integer and defaults to `10`. The command selects one exact live target and validates it before and after reading. It does not open or require a persistent connection. An unavailable or changed target is an error; an archived conversation cannot substitute for it.

The command returns one standalone JSON object:

```json
{
  "type": "history",
  "session_id": "<selected-session-id>",
  "cwd": "<target-working-directory>",
  "limit": 10,
  "messages": [
    {"type": "user", "uuid": "<record-uuid>", "content": "<visible text>"},
    {"type": "assistant", "uuid": "<record-uuid>", "content": "<visible text>"}
  ],
  "truncated": false
}
```

The latest snapshot for each record UUID supplies its visible text and native ordering. The last `limit` nonempty visible user/assistant messages are returned in chronological order. Text is preserved verbatim; thinking, tool calls, and tool results are excluded. `truncated: true` means earlier visible messages were omitted by the limit. An empty visible history returns `messages: []` and `truncated: false`. This is the SDK's session-level view; it does not identify the writer PID of each record.

Inspection does not change an active connection, its events, or its records. Failure is confined to the inspection command. Choose it explicitly when conversation context is useful, never automatically on silence, an output-wait timeout, or a missing delivery notice. Connecting and exchanging messages require no SDK or history retrieval.

## Records and recovery

Run from the calling project's root. Each connection gets a new directory, defaulting to `.codex-skills/claude/<unique-id>/`:

| File | Responsibility |
| --- | --- |
| `connection.json` | Exact target, helper metadata, sequence, connection state, and close reason |
| `events.jsonl` | Persisted stream events, including the closing event |
| `outbox.json` | Outbound text and transport state keyed by transmission UUID |

Any existing directory, including an empty one, cannot start a connection. Records remain evidence after shutdown; they are not a queue to resume or replay. In Git projects, ignore `/.codex-skills/` unless the records should be versioned.

The journal spools output while the host pauses collection. A full stdout pipe does not block controls or shutdown. Shutdown makes a bounded attempt to flush stdout, so its last line can be incomplete. Ignore that partial line and use complete `events.jsonl` records for events not collected from stdout. Use `connection_id` and `seq` to avoid consuming the same persisted event twice.

An uncatchable termination such as `SIGKILL` prevents cleanup: `connected` may remain on disk and `write_started` must be treated as an unknown transmission. Check the saved `server_pid` before interpreting connection state; never restart that directory or replay its outbox. Remove a leftover helper socket only after confirming its owning process is gone and its identity matches the helper's socket. Retain records needed by the caller and remove only expendable files belonging to this work. Do not alter Claude's native history.

## Native compatibility

Supports local Linux sessions owned by the calling operating-system user. The compatibility baseline is Claude Code `2.1.299` and native peer protocol `1`. In this baseline, refusal notices use `status: "expired"` with `status_detail: "refused"`. Unsupported native layouts are explicit errors. macOS, Windows named pipes, remote machines, and cloud sessions are outside this implementation's support.

The adapter uses [`claude agents --json`](https://code.claude.com/docs/en/agent-view#list-sessions-as-json) for discovery and the target's [inbox address and authentication](https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket) for transport. Registry layout, native framing, and peer reply addresses are version-specific details owned by `scripts/claude_native.py`.

The exact binding includes:

```text
session ID, working directory, and native registry start time
PID, process start, native PID domain, and kernel boot ID
provided inbox address, socket device, and socket inode
```

Discovery verifies the CLI candidate against the native registry, process, and Unix inbox. Registry/socket ownership and permissions must be valid. A nonwriting probe checks reachability and Linux `SO_PEERCRED`; sending verifies the listener PID and user ID again before credentials or message bytes. The native PID domain includes machine ID and PID namespace; boot ID is bound separately. Subsequent validation reads the bound registry, process, and inbox directly without repeatedly starting the CLI. Another live local process sharing the same session ID is rejected. Brief partial registry writes receive bounded retries; changed identity or unsafe ownership is rejected.

The sender builds one complete UTF-8 JSON line:

```json
{
  "msgV": 1,
  "msg_id": "<transmission-uuid>",
  "type": "user",
  "session_id": "<target-session-id>",
  "uuid": "<transmission-uuid>",
  "priority": "next",
  "from": "<helper-return-inbox-address>",
  "message": {
    "role": "user",
    "content": "<cross-session-message from=\"<helper-return-inbox-address>\" from-name=\"Codex\">\n<unchanged caller message>\n</cross-session-message>"
  }
}
```

The return address is the helper's actual `uds:` address: a unique `codex-<id>.sock` beside the target's validated inbox, with mode `0600`. At shutdown it is removed only while its identity belongs to this helper. The helper does not register a fake Claude session or install an MCP server. Incoming connections are accepted only from the bound Claude PID and user; the target is validated before and after reading. Known native `control` frames with `action: "peer_message_status"` produce delivery notices. Authentication and unrelated controls are not exposed as public events.

When required, authentication precedes the user frame:

```json
{"type":"auth","token":"<target-session-token>"}
```

Same-user Linux Unix socket connections can omit this line. Authentication material comes from the selected target's scoped native peer-key record when present and is excluded from records and output. A caller's messaging token is not substituted. Claude's `/status` exposes `Peer address`; child processes may receive `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN`. These credentials do not bypass Claude's inbound controls.

The optional `history` extra pins `claude-agent-sdk==0.2.166`. Its only SDK operation is read-only [`get_session_messages`](https://code.claude.com/docs/en/agent-sdk/python#get_session_messages):

```python
from claude_agent_sdk import get_session_messages

messages = get_session_messages(session_id, directory=target_cwd)
```

No SDK inference client or fallback session is started.
