# claude

Exchange messages with an already-open local Claude Code session for delegated work, questions, and coordination. Inspect its history separately on demand.

[All skills](../../README.md#skills) · [한국어](claude.ko.md)

## Installation

```text
Use $skill-installer to install skills/claude from https://github.com/smturtle2/codex-skills.
```

## Requirements and preparation

Requires uv, Python 3.11 or later, and a local Linux Claude Code session running as the same operating-system user with a usable inbox. Open Claude separately and keep the intended session running. For unattended receipt, choose `/config` → `Messages from your other sessions` → `accept` in Claude.

The skill discovers the existing inbox and manages the connection. It does not launch Claude or change its settings. Without an open usable session, it is unavailable. See [native compatibility](../../skills/claude/references/inbox-contract.md#native-compatibility) for supported versions and protocol details. Only optional history inspection uses the SDK supplied by the `history` extra.

## Use

Ask naturally, identifying the intended session by its name and working directory when needed:

```text
Use $claude to ask the open session in this project to review this change.
Use $claude to ask that session which API rules it agreed on.
Use $claude to inspect the open session's last 10 conversation messages.
```

Delegating a review is one way to use Claude as a subagent. The same connection also supports questions and coordination. The caller chooses what to send and how to interpret and present received messages; the helper relays message content unchanged. Include relevant context and paths in messages: sending a message does not attach files or transfer the caller's conversation context. Paths refer to the target's machine and working directory.

### Many-to-many message exchange

On one connection, several instructions, questions, and reports can be exchanged independently, for example:

| Direction | Message |
| --- | --- |
| Codex → Claude | Review the parser for input-validation problems. Leave the files unchanged. |
| Codex → Claude | Include the legacy input format in the review. |
| Claude → Codex | I found that the current parser treats blank input as zero. |
| Claude → Codex | Is empty input allowed by the intended contract? |
| Codex → Claude | Empty input is invalid. The legacy path also changed in `src/legacy_parser.py`. |
| Claude → Codex | I have now inspected both entry points. |
| Claude → Codex | The legacy parser also drops the minus sign on negative values. |
| Codex → Claude | Also check how values above the supported numeric range are handled. |
| Claude → Codex | Both paths already reject values above the supported range. |
| Claude → Codex | The review found two problems: blank input becomes zero, and legacy negative values lose their sign. |

The caller can continue other work and send follow-ups on the same connection. Claude may send several findings, progress updates, or questions independently of those inputs.

## What is received

Claude sends messages through native `SendMessage` to the helper's return inbox. The connection receives those messages, rather than every ordinary answer in Claude's own conversation. It also reports transmission and connection events. Transmission status does not establish that Claude has completed the requested work, and uncertain transmissions are not retried automatically.

History inspection is a separate, read-only snapshot of recent user and assistant text. It is optional, does not require a persistent connection, and does not affect an active connection if it fails. Silence does not trigger automatic history inspection. See [history inspection](../../skills/claude/references/inbox-contract.md#history-inspection) for its command, limits, and output.

## Connection lifetime and records

Disconnecting ends the helper and removes its return inbox; Claude keeps running. Losing the owner's input channel, ending the selected session with `/clear` or `/new`, or stopping or restarting Claude also ends the connection. Reconnecting requires explicitly selecting a live target and starting a new connection. See [connection lifetime](../../skills/claude/references/inbox-contract.md#target-and-connection-lifetime).

Each connection keeps local records in a new directory under `.codex-skills/claude/<unique-id>/` by default, relative to the calling project's root. These records preserve messages and transmission outcomes for inspection; they do not restart connections or automatically replay messages. Ignore `/.codex-skills/` in Git unless those records should be versioned. See [records and recovery](../../skills/claude/references/inbox-contract.md#records-and-recovery).

[Read the agent instructions](../../skills/claude/SKILL.md) for the connection procedure and [controls and events](../../skills/claude/references/inbox-contract.md#controls-and-events) or [transmission and delivery](../../skills/claude/references/inbox-contract.md#transmission-and-delivery) for the detailed message contract.
