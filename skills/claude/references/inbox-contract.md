# Inbox contract

This runtime connects to an existing Claude Code session. It transports the
caller's instructions and relays Claude's messages; the caller owns task
assignment and interpretation. Inputs and outputs are independent streams.

## Support and interfaces

Supports local Linux sessions owned by the calling operating-system user. The
compatibility baseline is Claude Code `2.1.299` and native peer protocol `1`.
Optional history inspection uses `claude-agent-sdk==0.2.166`, installed through
the `history` extra. `sessions` and `connect` require no SDK. Unsupported native
layouts are explicit errors.
macOS, Windows named pipes, remote machines, and cloud sessions are outside this
implementation's support.

The public interfaces used are:

- [`claude agents --json`](https://code.claude.com/docs/en/agent-view#list-sessions-as-json)
  for candidate discovery.
- The target's [inbox address and authentication](https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket).
- [`get_session_messages`](https://code.claude.com/docs/en/agent-sdk/python#get_session_messages)
  only for explicitly requested, one-shot history inspection.

Registry layout, native frame fields, and direct peer reply addresses are
version-specific compatibility details owned by `scripts/claude_native.py`.
The helper uses its own Unix inbox as a reply address. It does not register a
fake Claude session, install an MCP server, or start an SDK inference client.

## Connection ownership and lifetime

`sessions` lists verified candidates. `connect --session ID [--run-dir PATH]`
starts one foreground helper bound to one exact live target. The host retains
that process with writable stdin and reads its stdout. When a host requires a
PTY for retained input, the helper disables echo and canonical input limits.
This is process control, not reading Claude's terminal.

The helper owns:

- The exact target binding and its availability checks.
- A local return inbox for native peer messages.
- Per-transmission UUID bookkeeping, independent of received messages.
- Event output, local evidence, and cleanup.

The target binding includes:

```text
session ID, working directory, and native registry start time
PID, process start, native PID domain, and kernel boot ID
provided inbox address, socket device, and socket inode
```

Discovery verifies the public CLI candidate against the native registry,
process, and Unix inbox. Registry/socket ownership and permissions must be
valid. A nonwriting probe checks reachability and Linux `SO_PEERCRED`; the
sending connection checks the listener's PID and user ID again before sending
credentials or message bytes. The native PID domain contains machine ID and PID
namespace; kernel boot ID is bound separately.

After discovery, validation checks the bound registry, process and inbox
directly without repeatedly starting the CLI. It also rejects another live
local process sharing the same session ID. Brief partial registry writes are
retried with a bounded delay; changed identity or unsafe ownership is rejected.
Revalidation continues throughout the connection and before target access. If
the session, process, or inbox disappears or changes, emit the failure and close
the helper. `/clear` and `/new` start a new session: the old connection ends even
if its process and inbox remain. Process shutdown or restart also ends the old
connection, even when a new process resumes the same session ID. Reconnecting
requires explicitly selecting a live target and starting a new connection.
Do not select another target or continue reading archived history.

Explicit `disconnect`, stdin EOF, `SIGINT`/`SIGTERM`/`SIGHUP`, and exact target
loss/change close the connection and remove the helper's own socket.
An unusable stdout channel also ends the helper. Claude is not terminated.
Signals are owned from startup through final cleanup; handlers only request
shutdown, and ordinary execution checkpoints perform it. An unexpected worker
failure closes the helper rather than leaving an incomplete connection open.
Claude's turn ending, `idle`, `waiting`, and host output-poll timeouts do not
close the connection. The lifetime signal from the caller is its actual process
control channel; do not infer it from a chat turn or UI window.

The first close reason is preserved independently of the final exit code:

| Exit code | Meaning |
| --- | --- |
| `0` | Normal explicit disconnect or owner-channel closure |
| `3` | Selected target lost/changed, or unsupported target/environment |
| `1` | Helper execution, recording, or cleanup failure; takes precedence over `3` |

Unexpected main-loop exceptions report `internal_error`. A genuine local
failure during cleanup produces exit `1` even after normal disconnect or target
loss. A late target-unavailable result after intentional disconnect does not
turn that normal closure into failure. Errors are reported best effort when
storage or output is no longer usable.

## Control and event streams

Stdin accepts UTF-8 JSONL. A control is one JSON object plus `\n`:

```jsonl
{"type":"send","message":"Inspect the implementation and report what you find."}
{"type":"send","uuid":"53fb2a6e-2ae2-4568-80d5-8d519a15642a","message":"Also consider concurrent edits."}
```

`send.message` is the caller's text. `uuid` is optional; omission generates a
fresh UUID. Within the connection, repeating an existing UUID with the same
text returns its saved transmission outcome without sending again. Reusing it
with different text is an error. There is no implicit retry or replay, including
for an uncertain write. These UUIDs do not associate outputs with inputs.
`send` controls must contain nonempty message text. Every control must fit within
the 1 MB input limit. Close the connection separately when it is no longer needed:

```jsonl
{"type":"disconnect"}
```

Disconnect stops the connection, including queued messages not yet transmitted.

Stdout contains asynchronous JSONL events:

| Event | Meaning |
| --- | --- |
| `connected` | Exact target binding and the helper's return inbox are ready |
| `message` | Claude's native peer content |
| `sent` | Transmission UUID and observed transport outcome |
| `delivery_status` | Verified native transport notice from the same return inbox |
| `error` | Command or connection failure; inspect the error and later stream events |
| `closed` | The helper has ended the connection |

`closed` ends normal message delivery. Final output or reader cleanup errors
can follow it. Retain the host execution session and collect until the helper
exits; its exit code reports the final outcome.

Invalid controls or rejected peer frames report errors without closing an
otherwise usable connection. Target, return-listener, and record failures close
the helper.

Events carry `seq`, `connection_id`, and the selected `session_id`. Each
`message` also carries `source: "peer"`, `uuid`, and `content`. Preserve the
received content when presenting or consuming output. The connection does not
read conversation history or emit ordinary assistant output, revisions, or
history-gap events.

The event journal spools output while the host pauses collection. A full stdout
pipe does not block stdin controls or connection shutdown. Unread output stays
in `events.jsonl`; shutdown makes only a bounded attempt to flush stdout.
The last stdout line can therefore be incomplete at shutdown. Ignore that
partial line and use the journal for output not collected from stdout.

The stream does not label answers as matched, unmatched, ambiguous, or complete.
Progress, questions, intermediate results, and final reports can all arrive.
Additional instructions can be sent while Claude works. One instruction need
not produce one output, and the helper does not impose a response format.

Native message UUIDs provide event deduplication. Repeated text alone does not
establish that two messages are the same event.

## Native delivery and return inbox

The sender builds one complete UTF-8 JSON line before transmission:

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

The return address is the helper's actual `uds:` inbox address. Claude uses
native `SendMessage` to that address for reports and questions. Ordinary text
left in Claude's own conversation does not reach the helper. No reply marker or
input/output matching is required.
The adapter creates a unique `codex-<id>.sock` in the target's validated inbox
directory with mode `0600`. It removes that socket at shutdown only while its
identity still belongs to this helper; the run directory holds records only.

If required, authentication precedes the user frame:

```json
{"type":"auth","token":"<target-session-token>"}
```

Same-user Linux Unix socket connections can omit that line. Authentication
material is read from the selected target's scoped native peer-key record when
present and is excluded from persisted state and output. A caller's messaging
environment token is not substituted.

Claude's `/status` exposes its inbox as `Peer address`; child processes may
receive `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN`. These
are session credentials, not a reason to bypass the target's inbound controls.
The helper's return inbox checks its incoming native peer against the bound
Claude process before accepting message bytes.

Persist each outbound message and the `not_sent` state before transmission.
Persist `write_started` before the user frame can be written. The resulting
transport state is `written` or, when bytes may have been sent without a known
outcome, `delivery_unknown`. A `sent` event carries `uuid` and `transport`.
`written` means socket-write success, not admission by Claude. The helper does
not read raw transcripts to certify input receipt.
At shutdown, an unfinished `write_started` transmission is frozen as
`delivery_unknown`. Workers cannot update transmission records after closure.

The same return inbox carries Claude's messages and native delivery notices;
these are different frame types, not separate receive channels.
The return inbox accepts the bound Claude process only and retains its
post-read binding check. It recognizes native `control` frames with
`action: "peer_message_status"` and relays allowlisted, type-checked fields as
`delivery_status` events. Authentication and unrelated control traffic are not
exposed. A public notice has the common event fields plus:

```json
{
  "type": "delivery_status",
  "source": "peer",
  "uuid": "<native-receipt-msg_id>",
  "status": "expired",
  "status_detail": "refused",
  "orig_msg_id": "<transmission-uuid>",
  "reason": "<native reason>"
}
```

Known `status` values are `held`, `denied`, `expired`, `delivered`, `refused`,
and `dropped`. Optional native fields are `status_detail`, `reason`,
`orig_msg_id`, `drop_reason`, and `dropped_msg_ids`; the helper preserves allowed
values without synthesizing a receipt. Claude Code `2.1.299` reports refusal as
`status: "expired"` with `status_detail: "refused"`. `delivered` means a held
message was released to the receiving Claude, not that it was read or its work
completed. There is no positive receipt for every initially accepted message.
Missing notices prove nothing about admission.

`orig_msg_id` and dropped-message IDs identify the transmissions described by
native notices. They do not pair Claude's output with an input, establish task
completion, trigger automatic retries, or change the saved socket-write state.

## Optional history inspection

History is an independent inspection command, not part of task messaging:

```sh
uv run --project "$SKILL_DIR" --extra history \
  "$SKILL_DIR/scripts/claude.py" history --session "$SESSION_ID" --limit 10
```

`--limit` must be a positive integer and defaults to `10`. The command selects
one exact live target and validates it before and after reading. It does not
open or require a persistent connection. An unavailable or changed target is an
error; an archived conversation cannot substitute for it.

The optional `history` extra supplies the pinned SDK. Its only SDK operation is
read-only history retrieval:

```python
from claude_agent_sdk import get_session_messages

messages = get_session_messages(session_id, directory=target_cwd)
```

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

Select the last `limit` nonempty visible user/assistant text messages and retain
their chronological order. Text is preserved verbatim; thinking, tool calls,
and tool results are excluded. `truncated: true` means earlier visible messages
were omitted by the limit. An empty visible history returns `messages: []` and
`truncated: false`. This is the SDK's session-level view; it does not identify
the writer PID of each record.

Inspection does not create or update a connection cursor, emit `message`
events, or change connection records. It does not associate inputs with
responses or establish task completion. Its failure does not affect an active
connection. Do not invoke it automatically on silence, a host output timeout,
or a missing delivery notice. The caller chooses it only when inspecting the
conversation is useful. No SDK inference client or fallback session is started.

## Evidence and inbound controls

Each connection gets a new run directory, defaulting to
`.codex-skills/claude/<unique-id>/`:

| File | Responsibility |
| --- | --- |
| `connection.json` | Exact target, helper metadata, sequence, connection state and close reason |
| `events.jsonl` | Persisted stream events, including the closing event |
| `outbox.json` | Outbound text and transport state keyed by transmission UUID |

Any existing directory, including an empty one, cannot start a connection. The
records remain evidence after shutdown; they are not a queue to resume or replay.
After an uncatchable process termination such as `SIGKILL`, cleanup cannot run:
`connected` may remain on disk and `write_started` must be treated as an unknown
transmission. Check the saved server PID before interpreting connection state;
never restart that directory or replay its outbox. A leftover helper socket can
be removed only after confirming its owning process is gone and its identity.
Old request directories are untouched, and old request-based commands and reply
contracts are removed. Keep records needed by the caller, and remove only
expendable files belonging to this work. Do not alter Claude's native history.

For unattended receipt, the user prepares Claude through `/config` →
`Messages from your other sessions` → `accept`. The skill does not change this
setting. `hold` or `refuse` can prevent admission despite a successful write.
Claude still applies its own tools and permissions. Paths and `@` mentions in a
message do not attach resources, and inbox delivery cannot forcibly interrupt
a running tool. See [Claude's messaging controls](https://code.claude.com/docs/en/cross-session-messaging).
