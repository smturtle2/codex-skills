---
name: mafia-game
description: Run an 8-player server-mediated Mafia game where the user plays through a web client, the main Codex agent creates and progresses the game as GM through scripts, and seven persistent autonomous subagents play through seat scripts. Use when the user wants a Mafia/Werewolf-style social deduction game with free chat, hidden roles, autonomous AI players, server-owned access control, and no direct main-to-subagent prompting after player creation.
---

# Mafia Game

Run a free-chat Mafia game through a local server. The server is the only communication bus, access boundary, event ledger, and projection source.

The main agent is the GM actor, not a player and not a narrator for subagents. After subagents are created, main, subagents, and the user communicate only with the server.

## Core Contract

- The user plays only through the web client.
- The user web URL must not require or expose a query-string token. The server may use an HttpOnly same-origin cookie for the user web session.
- Main and subagents use bundled scripts only.
- Main creates the session, starts or resumes the server, creates seven subagent player sessions with `model="gpt-5.5"` and `reasoning_effort="medium"`, and progresses the game through GM server APIs.
- Main must not tell subagents when to act, what happened, what to say, or how to vote.
- Subagents are persistent autonomous players. They watch their own seat projection and decide whether to speak, stay silent, vote, send private messages, or submit night actions.
- The server owns persistence, event routing, access control, projections, and the canonical event ledger.
- The web client reflects allowed user state from the server. Main does not update or render the web view.
- Scripts must not decide social strategy, author player speech, infer hidden motives, or resolve social outcomes.
- No actor may read files or API views outside its role: GM token for GM state, user token for user state, seat token for that seat only.

## Commands

Start the local server:

```bash
python3 skills/mafia-game/scripts/mafia_server.py --serve --session <session-slug>
```

Create a game session through the GM client:

```bash
python3 skills/mafia-game/scripts/mafia_gm_client.py --server http://127.0.0.1:8790 --session <session-slug> --create-session
```

Open the returned web URL for the user. The URL includes only the session id; do not ask the user to copy or paste a token.

Run each subagent as a persistent autonomous seat client:

```bash
python3 skills/mafia-game/scripts/mafia_player_client.py --server http://127.0.0.1:8790 --session <session-slug> --seat seat-02 --token <seat-token> --auto
```

Watch the game as GM:

```bash
python3 skills/mafia-game/scripts/mafia_gm_client.py --server http://127.0.0.1:8790 --session <session-slug> --token <gm-token> --watch
```

## Game Flow

1. Start or resume the server.
2. Create a session with the GM client if one does not exist.
3. Read the created seat tokens from the GM client output.
4. Spawn seven subagents, one per AI seat. Required spawn parameters are `model="gpt-5.5"` and `reasoning_effort="medium"`. Give each subagent only: server URL, session id, seat id, and its own seat token.
5. Tell the user the web URL is ready.
6. Wait until all eight seats have attended through their own user/seat projection.
7. Start day 1 only after the server reports full attendance.
8. Keep the GM watch active while the game is running.
9. Progress the game only through GM client commands or GM-authorized API events.
10. Let subagents keep playing through `--auto`. Do not send direct gameplay messages to them.
11. When the game ends, stop the GM watch and close subagents.

Do not send a final response while an active game is still running unless the user stops the game, the server exits, or an unrecoverable operational failure occurs.

## Free Chat Contract

Free chat is always available through the server while the actor is alive and has channel access.

- Public messages may be submitted by the user or any living subagent.
- Mafia private messages may be submitted only by living mafia seats.
- Vote and night-action submissions are events, not commands from main.
- Day and night are timed free-chat windows. Event numbers preserve ordering but never define turns.
- New sessions begin in `setup`; the game cannot progress into day or night until all eight participants have connected.
- Server validation checks identity, liveness, channel membership, role permissions, and target validity.
- Main resolves game consequences through GM events after observing server state.

Subagents are not turn responders. They do not wait for a "your turn" prompt. They watch their own seat stream and decide independently when to act.

## Server-Mediated Architecture

All communication must pass through the server:

```text
browser user client  <->  mafia server
main GM script       <->  mafia server
subagent seat script <->  mafia server
```

Forbidden paths:

```text
main agent -> subagent gameplay instruction
subagent -> main direct gameplay message
subagent -> subagent direct gameplay message
web client -> GM-only state
seat client -> other seat private state
script -> social strategy decision
```

Read [references/architecture-contract.md](references/architecture-contract.md) before starting or modifying a session. Read [references/server-api-contract.md](references/server-api-contract.md) before patching scripts. Read [references/gm-procedure.md](references/gm-procedure.md) before running a live game. Read [references/subagent-seat-contract.md](references/subagent-seat-contract.md) before spawning subagents. Read [references/free-chat-contract.md](references/free-chat-contract.md) when changing chat/watch behavior. Read [references/rules.md](references/rules.md) when changing role or resolution behavior.

## Runtime Files

Default root:

```text
mafia-runs/
```

Default session path:

```text
mafia-runs/<session-slug>/
```

The server writes:

- `state.json`: authoritative game state, roles, tokens, phase, seats, and counters.
- `events/canonical.jsonl`: append-only canonical event ledger.

Actors must not read these files directly during normal play. Use the server APIs through the bundled scripts.

## Response Rules

When starting or continuing a game, report only operational facts:

- server command or URL
- user web URL
- which subagent seats were created
- GM watch command in use
- game over result when the server state reaches a terminal phase

Do not reveal hidden roles, GM-only events, seat tokens, or private channel content in chat.
