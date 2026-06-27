# Web Client Contract

The web client is only the user player's client.

## Required User Surface

The web client must show:

- current phase and day
- timed free-chat countdown
- public event log
- player table with public seat state
- user's own role view
- user's private visible events
- public chat input
- interactive channel tabs for public, mafia, and private notes when allowed
- interactive target selection for votes and role actions
- role action controls derived from the user's `allowed_actions`
- public random nicknames for all seats
- public persona labels for all seats

The web client must not show:

- GM token
- user token in the URL
- seat tokens
- full role table
- canonical event ledger beyond user-visible events
- subagent runtime status
- server filesystem paths
- hidden night actions from other seats
- slash-command controls or templates

The user entry URL must be `GET /play?session=<id>` without a token query parameter. The server may authenticate the browser with an HttpOnly same-origin cookie.

## Layout

The web client must not require page-level scrolling during normal play. The viewport owns the whole app, and only dense content panes such as player list, chat, and case log may scroll internally.

## Input

The web client must submit structured player events directly:

- public chat: `{"event_type":"public_message","text":"..."}`
- mafia chat: `{"event_type":"private_message","channel":"mafia","text":"..."}`
- private note: `{"event_type":"private_message","channel":"seat:<own-seat-id>","text":"..."}`
- vote: `{"event_type":"vote","target":"seat-05"}`
- role action: `{"event_type":"night_action","action":"investigate","target":"seat-05"}`

The web client must use canonical `seat_id` values for targets. It may display nicknames, but nicknames are not the UI action identifier.

Persona labels are presentation metadata only. The web client must not imply they reveal hidden role or team information.

The web client must not package user input as `raw_input`.

Server validation remains authoritative for channel access, role actions, liveness, and targets.

## State Reflection

The web client polls or watches the user projection and renders it. Main does not push UI updates, format the UI state, or manually refresh the web view.
