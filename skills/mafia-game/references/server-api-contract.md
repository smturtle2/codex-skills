# Server API Contract

The bundled server uses local HTTP APIs. Clients should use the bundled scripts instead of hand-writing requests during normal play.

## Authentication

GM scripts and AI seat scripts use bearer tokens:

```text
Authorization: Bearer <token>
```

Token classes:

- `gm`: full GM projection and GM events.
- `user`: user player's projection and user player events.
- `seat`: one AI seat projection and that seat's player events.

The user web client must not require a token in the URL. `GET /play?session=<id>` sets an HttpOnly same-origin cookie for the user web session, and user web API calls may authenticate through that cookie.

## Session Creation

`POST /api/session`

Request fields:

- `session_id`: required string.
- `user_name`: optional string for setup metadata compatibility. It is not used as the in-game public name.
- `seed`: optional string or integer for deterministic role assignment in tests.

Response fields:

- `session_id`
- `gm_token`
- `user_token`
- `user_web_url`
- `seats`: array with `seat_id`, `name`, `kind`, and seat token only for AI seats.

Session creation assigns every seat a unique random public `name`. The name is the in-game nickname shown to all clients. Seat identity and authorization still use `seat_id` and tokens.

New sessions start in `setup`. The GM cannot move the game into `day`, `night`, or `game_over` until all eight seats have attended through their own web or seat projection.

Only the GM setup flow may expose seat tokens. Do not relay seat tokens in chat after subagents are spawned.

## Projections

`GET /api/gm/state?session=<id>`

Requires GM token. Returns full state and all canonical events.

`GET /api/user/state?session=<id>`

Requires a user bearer token or the user web session cookie. Returns only the user player's projection.

`GET /api/seat/state?session=<id>&seat=<seat-id>`

Requires that seat's token. Returns only that seat's projection.

Projection fields:

- `session_id`
- `phase`
- `day`
- `timing_mode`
- `phase_started_at`
- `phase_duration_seconds`
- `phase_ends_at`
- `phase_remaining_seconds`
- `attendance`: `attended`, `required`, and `ready`
- `seat_id`
- `seat_name`
- `role_view`
- `persona_view`
- `table`
- `allowed_channels`
- `allowed_actions`
- `events`
- `last_event_number`

No player projection may include `auth`, full role table, other-seat private events, GM-only events, or hidden resolution notes.

`persona_view` contains public roleplay style only: `label`, `voice`, `catchphrase`, `message_max_chars`, and `speech_rule`. It must not encode hidden role, alignment, token class, or subagent implementation details.

## Player Events

`POST /api/player/event?session=<id>`

Requires a user bearer token, user web session cookie, or seat token.

Allowed event types:

- `public_message`
- `private_message`
- `vote`
- `night_action`
- `raw_input`: compatibility path for scripts and CLI clients only.

The web user client must submit structured `public_message`, `private_message`, `vote`, and `night_action` events. It must not submit `raw_input`.

AI player text may be constrained by the server's `message_max_chars` policy so autonomous participants stay readable in the web UI.

Validation requirements:

- actor token must be valid
- actor must be alive for player events
- private channel membership must be valid
- vote target must be a living seat
- night action must match the actor's role

The server appends accepted events to the canonical ledger. It rejects invalid events without changing state.

## GM Events

`POST /api/gm/event?session=<id>`

Requires GM token.

Allowed event types:

- `phase_change`
- `public_announcement`
- `private_notice`
- `eliminate`
- `game_over`
- `gm_note`

GM events progress the game. Player events only express player behavior.

`phase_change` may include `duration_seconds`. If omitted, the server applies the default timed free-chat window for the target phase. A `setup` session rejects phase changes away from setup until `attendance.ready` is true.

## Watch

`GET /api/events/watch?session=<id>&after=<event-number>&scope=<gm|user|seat>&seat=<seat-id>&timeout=<seconds>`

The server long-polls until at least one visible event exists after `after`, or until timeout.

The endpoint returns:

- `events`: visible events after `after`
- `last_event_number`: latest visible event number in this projection

Seat clients should keep watching indefinitely. Watch is not a turn prompt.
