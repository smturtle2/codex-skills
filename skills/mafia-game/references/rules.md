# Default Rules

The first version uses a fixed 8-player Mafia setup.

## Seats

Required seats:

- `seat-01`: user player
- `seat-02` through `seat-08`: AI subagent players

Each seat receives one unique random public nickname at session creation. Nicknames are stable for the session and must not encode role, token class, subagent implementation, or hidden game information.

## Roles

Role list:

- 2 mafia
- 1 detective
- 1 doctor
- 4 citizens

The server assigns roles at session creation. Only GM state contains the full role table.

Player role visibility:

- each player knows their own role
- mafia players know the other mafia seat
- citizens, detective, and doctor do not know other roles

## Channels

Allowed channels:

- `public`: living players and GM-visible public table
- `seat:<seat-id>`: one player and GM
- `mafia`: living mafia players and GM
- `gm`: GM-only events

## Player Events

Allowed player events:

- `public_message`
- `private_message`
- `vote`
- `night_action`

Role-specific night actions:

- mafia: `kill`
- detective: `investigate`
- doctor: `protect`
- citizen: none

## GM Resolution

The server validates permissions and records events. Main resolves outcomes as GM.

Default vote rule:

- use the latest valid vote from each living player
- eliminate the target with the highest vote count when main closes voting
- if tied, main may announce no elimination or apply a stated house rule before the vote

Default night rule:

- mafia kill chooses a target from accepted mafia `kill` actions
- doctor protect cancels one matching kill
- detective investigate result is sent as a private notice

## Win Conditions

Mafia wins when living mafia count is greater than or equal to living non-mafia count.

Town wins when no living mafia remain.
