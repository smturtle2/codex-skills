# Inbox contract

This reference describes the technical connection to an existing Claude Code
session. The caller determines the work, instructions, and meaning of the
returned response. No task types or task completion policy are added by the
runtime.

## Support and contract boundaries

The initial implementation supports local Linux sessions owned by the calling
operating-system user. Its compatibility baseline is Claude Code `2.1.299`,
native peer protocol `1`, and `claude-agent-sdk==0.2.166`. Other versions may
remain compatible, but an unsupported native layout is an explicit error, not a
reason to guess an address or start a replacement session. macOS, Windows named
pipes, remote machines, and cloud sessions are outside this implementation's
support.

The public interfaces used are:

- [`claude agents --json`](https://code.claude.com/docs/en/agent-view#list-sessions-as-json)
  for candidate discovery.
- The target's [inbox address and authentication](https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket).
- [`get_session_messages`](https://code.claude.com/docs/en/agent-sdk/python#get_session_messages)
  for reading the target's ordinary conversation messages.

Automatic native address lookup, registry layout, complete input frame, and raw
input record interpretation are version-specific compatibility details, not a
published stable API. Keep them together in `scripts/claude_native.py`.

## Exact target binding

Discovery starts with the public CLI list and verifies candidates against the
native local registry, process evidence, and Unix socket. A finished background
task can remain in the CLI list. Matching a label or directory alone therefore
does not establish an available target.

Each saved request binds:

```text
session ID
target working directory
PID, process start, native PID domain, and kernel boot ID
provided inbox address and socket identity
```

Before sending or reading history, revalidate this binding against the current
live session. Use the registry's provided endpoint, never an endpoint constructed
from the session's name. Socket and registry paths must belong to the same user
and have the expected native file types. Authentication material is read only
when needed and excluded from persisted requests and command output.

Socket identity includes the device and inode, so replacing a socket at the
same path changes the binding. Discovery connects without writing bytes to
check reachability and the listener's Linux `SO_PEERCRED` PID and user ID. The
actual sending connection checks that identity again before sending an
authentication token or message.

On the verified Linux version, the native PID domain contains `/etc/machine-id`
and the PID namespace. The adapter separately binds the kernel boot UUID so a
saved request cannot identify a process from a later boot as the original one.

The target's `/status` presents its inbox as `Peer address`; Claude's child
processes can receive `CLAUDE_CODE_MESSAGING_SOCKET` and
`CLAUDE_CODE_MESSAGING_TOKEN`. An inbox token is a technical session credential.
This skill does not use it to assert that it is the target's own child or to
bypass the target's inbound controls.

The adapter reads the target's scoped native peer-key record when present; it
does not substitute a caller's messaging environment token.

If the process exits, is replaced, changes session, or changes inbox, return
`session_unavailable`. Keep already observed evidence, but do not continue
against old history or select another session automatically. Listing sessions
does not create one. Importing the SDK for history does not start an SDK client.

## Wire delivery

The request is one UTF-8 JSON line terminated by `\n`:

```json
{
  "type": "user",
  "session_id": "<target-session-id>",
  "uuid": "<request-id>",
  "from": "Codex",
  "message": {
    "role": "user",
    "content": "<cross-session-message from-name=\"Codex\">\n<task text>\n</cross-session-message>"
  }
}
```

The caller's task text is preserved within the transport wrapper. An
`--expect-reply` request also carries a separate technical instruction to put the
answer in the session's normal assistant reply using this marker:

```xml
<codex-reply request-id="<request-id>">
The response text
</codex-reply>
```

There is no Codex peer inbox to reply to with Claude's `SendMessage`. The answer
must be in the target conversation so the SDK history reader can observe it.
The marker associates a response with a request; it is not a fixed result schema
and does not establish that the requested work succeeded.

An authenticated connection, where required, starts with:

```json
{"type":"auth","token":"<target-session-token>"}
```

Linux Unix sockets permit same-user connections without this line. The script
builds the complete request before connecting; it does not wait for model output
while keeping a partially written input connection open.

Save the target binding, task text, request UUID, and pre-send history boundary
before transmission. Persist the possible-write boundary before a user-frame write
can occur. An ordinary input frame has no ACK in the verified native protocol.
Socket success therefore records a transport fact, not receiver admission.

When a write may have occurred, errors or interrupted calls never cause automatic
replay. Repeating `send` with the same run directory checks the saved request and
observes it; it does not deliver it again. Incompatible request arguments do not
replace the saved request. To issue a new message, use a new run directory.

Transmission or observation errors for a valid loaded request include its
`run_dir`, `request_id`, and latest transport, input, and response states. Use that saved path to observe
the request even when the initial command did not succeed.

## Input and response observations

Claude persists incoming inbox user messages as `isMeta` native records. The
verified Python SDK [history implementation](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sessions.py)
filters these out. The native adapter reads only the relevant raw record needed
to observe the saved input UUID. Absence means unobserved, not proof that Claude
refused it.

The history adapter uses only:

```python
from claude_agent_sdk import get_session_messages

messages = get_session_messages(session_id, directory=target_cwd)
```

SDK message UUIDs and content fingerprints form the observation boundary.
Preserve newly observed messages and their revisions, and combine text blocks
belonging to the same native `message.id` before
matching the expected response. Thinking blocks and unrelated assistant messages
are not substitutes for matching assistant text. A shared Claude session may
handle several inputs in the same turn. A marker can identify the answer text;
it cannot make the session's turn boundaries exclusive to this request.

The current revision of every observed response group is considered when
matching. Two matching groups make the response `ambiguous`; editing a group
can remove its earlier match. Previously observed evidence remains saved when
the SDK's current conversation chain no longer contains it.

The command output keeps these evidence dimensions separate:

| Dimension | What it establishes |
| --- | --- |
| Session | Whether the exact bound process and inbox remain available |
| Transport | What the sender observed while writing; no native input ACK |
| Input | Whether the saved UUID appeared in the target's native input record |
| Response | Which normal assistant text matches the request, or why it remains unmatched or ambiguous |

If no marker was requested, newly observed assistant output is available without
being promoted to a corresponding answer. If an expected marker is absent,
incomplete, or has conflicting matches, report the observed output and match
state. Do not equate `idle`, a later timestamp, a final-looking answer, or a
successful socket write with a matching result.

If history compaction removes the saved observation boundary, report
`history_gap` and retain prior evidence. The polling timeout accepts 0–60 seconds;
an in-flight discovery or history read can finish after that deadline. Waiting
returns early for a matched reply, ambiguous matches, or a target
waiting for input. Without `--expect-reply`, newly observed readable output also
ends the wait. `timed_out: false` describes the wait, not task completion.
Timeout records the latest evidence; it neither cancels the Claude task nor
permits a resend. Closing the target ends observation with
`session_unavailable`.

Command output `responses` contains only text groups newly observed or revised
in that call. The saved request retains their accumulated revisions;
`matched_response` reflects the matching result across those observations.

## Inbound controls and troubleshooting

The user prepares the receiving session through `/config` → `Messages from your
other sessions` → `accept` when unattended delivery is desired. The skill does
not change settings. The receiver still applies its own tools and permissions.
`hold` and `refuse` can both leave a sender without an observed input; a live
inbox alone does not disclose the effective inbound setting.

Messages are plain text: file paths and `@` mentions do not attach resources.
Inbox delivery cannot interrupt a running tool or implement forced cancellation.
See [Claude's message delivery and inbound controls](https://code.claude.com/docs/en/cross-session-messaging)
for receiver behavior.

| Observation | Next technical action |
| --- | --- |
| No live candidate | Report unavailable; the user can open Claude separately |
| Incompatible native registry or peer protocol | Report compatibility failure; preserve the run |
| Possible write, input not observed | Recheck the same run; inspect receiver settings without resending |
| Input observed, response not matched | Read or wait on the same run; examine newly observed assistant text |
| History gap or ambiguous match | Report the gap or ambiguity with preserved evidence |
| Target no longer available | Stop observation; do not switch sessions or read archived history |

Run state stays under `.codex-skills/claude/<unique-id>/` unless an explicit
location was chosen. Keep unconfirmed evidence for recovery. Remove only
expendable intermediates after they are no longer needed; do not delete the
target's native history or unrelated workspace data.
