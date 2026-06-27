# Free Chat Contract

The game must feel like an open Mafia table, not a turn prompt loop.

## Required Behavior

- Living players may submit public messages without being prompted.
- Subagents must not wait for main to say it is their turn.
- The seat client `--watch` is a persistent observation stream, not an action request.
- Speaking, staying silent, voting, lying, questioning, and changing suspicion are player choices.
- Main may resolve rules and phases but may not create player messages.
- Day and night are time-boxed free-chat windows. The timer constrains phase resolution, not individual speaking turns.

## Event Ordering

The server gives every accepted event a monotonic `event_number`.

This ordering exists for consistency and replay. It is not a turn system.

The clock, not event order, determines when main may close a discussion window and resolve votes or night actions.

## Free Text Parsing

Seat scripts and CLI clients may submit `raw_input` for compatibility.

The web user client must not use `raw_input`; it submits structured events from interactive controls.

Server parsing rules:

- `/vote TARGET` becomes `vote`.
- `/mafia TEXT` becomes mafia private `private_message`.
- `/night ACTION TARGET` becomes `night_action`.
- `/private TEXT` becomes a seat-private note/message.
- all other text becomes `public_message`.

Server validation remains authoritative after parsing.

## No Required Response Rule

Chat events do not require responses from every subagent. Main must not wait for all subagents before continuing normal observation.

Timeouts apply only to HTTP watch calls. A watch timeout means "no visible event yet"; it is not a player silence decision unless that subagent chooses to stay silent.
