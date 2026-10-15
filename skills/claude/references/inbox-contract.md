# Inbox contract

This runtime connects to an existing Claude Code session. It transports the
caller's instructions and relays Claude's messages; the caller owns task
assignment and interpretation. Inputs and outputs are independent streams.

## Support and interfaces

Supports local Linux sessions owned by the calling operating-system user. The
compatibility baseline is Claude Code `2.1.299`, native peer protocol `1`, and
`claude-agent-sdk==0.2.166`. Unsupported native layouts are explicit errors.
macOS, Windows named pipes, remote machines, and cloud sessions are outside this
implementation's support.

The public interfaces used are:

- [`claude agents --json`](https://code.claude.com/docs/en/agent-view#list-sessions-as-json)
  for candidate discovery.
- The target's [inbox address and authentication](https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket).
- [`get_session_messages`](https://code.claude.com/docs/en/agent-sdk/python#get_session_messages)
  for ordinary conversation history.

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
- One receive cursor for ordinary assistant output.
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
| `message` | Native peer content or new/revised ordinary assistant text |
| `sent` | Transmission UUID and observed transport outcome |
| `delivery_status` | Verified native peer transport notice, separate from assistant output |
| `error` | Command or connection failure; inspect the error and later stream events |
| `history_gap` | The saved history boundary disappeared from the current SDK chain |
| `closed` | The helper has ended the connection |

`closed` ends normal message delivery. Final output or reader cleanup errors
can follow it. Retain the host execution session and collect until the helper
exits; its exit code reports the final outcome.

Invalid controls or rejected peer frames report errors without closing an
otherwise usable connection. Target, return-listener, and record failures close
the helper. A history gap is reported once when the cursor first detects it and
remains recorded; it does not close the connection.

Events carry `seq`, `connection_id`, and the selected `session_id`. Each
`message` also carries `source` (`peer` or `assistant`), `uuid`, and `content`.
Assistant messages additionally carry `message_id` and `revision`. A revised
assistant event updates the same output group; an empty
revision clears its previously observed text. Preserve message content and
revisions when presenting or consuming output.

The event journal spools output while the host pauses collection. A full stdout
pipe does not block stdin controls or connection shutdown. Unread output stays
in `events.jsonl`; shutdown makes only a bounded attempt to flush stdout.
The last stdout line can therefore be incomplete at shutdown. Ignore that
partial line and use the journal for output not collected from stdout.

The stream does not label answers as matched, unmatched, ambiguous, or complete.
Progress, questions, intermediate results, and final reports can all arrive.
Additional instructions can be sent while Claude works. One instruction need
not produce one output, and the helper does not impose a response format.

The native peer and assistant-history sources remain distinguishable. Content
that appears in both sources is not collapsed by textual similarity: repetition
alone does not establish that two messages are the same event.

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

The return address is the helper's actual `uds:` inbox address. Claude can use
its native `SendMessage` reply path to reach that inbox. Ordinary assistant
text is also received through the SDK history reader; the helper does not ask
Claude to choose a prescribed reply channel or wrap its reply in a marker.
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

## Assistant history stream

History reading uses only:

```python
from claude_agent_sdk import get_session_messages

messages = get_session_messages(session_id, directory=target_cwd)
```

Capture the initial history boundary once when connecting. Assistant output
returned by that initial read is the baseline. Track SDK UUIDs,
content fingerprints, and native `message.id` groups to emit new or revised
assistant text. Thinking and tool blocks are not assistant text. Sending a
follow-up neither resets the cursor nor consumes received output.
Each observation validates the bound target, reads SDK history, and validates
the target again before enqueuing the result or advancing the worker cursor.
Only observations passing that post-read check are published. Already accepted
queued output can drain during closure; if the session switches or the process
ends during a read, that last observation may be lost. The SDK returns
session-level history and does not identify the writer PID of every record.
Journal an entire accepted observation batch before committing its new receive
cursor.
An SDK empty result is an empty observation, including when its history file
has not appeared yet. Records first exposed later are newly observed; the API
cannot establish from an empty result whether they predated the connection.

If compaction removes the observation boundary, preserve previously observed
events and report a history gap. A gap does not authorize rereading all old
output as new. The helper does not infer which instructions any assistant text
answers or infer task completion from session status.

## Evidence and inbound controls

Each connection gets a new run directory, defaulting to
`.codex-skills/claude/<unique-id>/`:

| File | Responsibility |
| --- | --- |
| `connection.json` | Exact target, helper metadata, receive cursor, sequence, connection state and close reason |
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
