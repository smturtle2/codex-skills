# Architecture Contract

This skill runs Mafia as a server-mediated system. The server, not the main agent, is the trust boundary.

## Actors

Required actors:

- `server`: authoritative event store, access controller, projection source, and web host.
- `main`: GM actor using GM scripts and GM token.
- `user`: one player using only the web client.
- `subagent`: seven autonomous AI players using seat scripts and seat tokens.

## Non-Negotiable Invariants

1. After subagent creation, main and subagents never communicate directly about gameplay.
2. Every gameplay observation and action travels through the server.
3. The user web client is not a GM console.
4. Main may progress the game but may not author player decisions.
5. Subagents may act only from their own seat projection, role view, memory, and visible event stream.
6. The server owns canonical persistence and projection. Clients are replaceable.
7. Access control is enforced before projection and before event append.
8. Hidden information is never sent to a token that cannot know it.

## Communication Topology

Allowed:

```text
web browser <-> server user API
GM script   <-> server GM API
seat script <-> server seat API
```

Forbidden:

```text
main -> subagent gameplay prompt
subagent -> main gameplay report
subagent -> subagent direct chat
web -> GM-only endpoint
seat -> another seat endpoint
```

## Server Responsibilities

The server must:

- create and persist sessions
- assign roles
- issue actor tokens
- maintain an append-only canonical event ledger
- expose GM, user, and seat projections
- route public and private channel events
- validate actor identity, liveness, channel membership, role permissions, and targets
- provide a web client for the user
- provide long-poll or stream-style watch endpoints for scripts

The server must not:

- decide social strategy
- author player speech
- choose votes or night targets
- resolve ambiguous social reasoning without a GM event

## Main Responsibilities

Main must:

- start or resume the server
- create the session if needed
- spawn seven subagents with only their seat credentials
- watch GM state through the GM script
- resolve votes, night actions, eliminations, and win checks through GM events
- stop or close subagents when the game ends

Main must not:

- tell a subagent that it is their turn
- summarize the game directly to a subagent
- instruct a subagent what to say
- edit a subagent outbox
- update the web UI

## Subagent Responsibilities

Each subagent must:

- run a persistent seat client
- observe only its own seat projection
- maintain its own reasoning and memory inside its own session context
- submit player events through the seat client
- keep watching after speaking or acting

Subagents must not read `state.json`, `events/canonical.jsonl`, GM projections, or another seat projection.

## User Web Responsibilities

The web client must:

- show the user's allowed projection
- submit public and private chat text as structured player events
- submit vote and role-action selections as structured player events
- poll or watch for state changes
- render public log, player list with random nicknames, own role, own private events, and allowed channels/actions

The web client must not:

- show GM controls
- show subagent implementation details
- infer hidden roles
- decide outcomes
- expose slash-command controls
