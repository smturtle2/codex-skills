# GM Procedure

Use this procedure when running a live Mafia session.

## Start

1. Start the server.
2. Create a session with the GM client.
3. Keep the GM token private.
4. Give the user only the returned web URL.
5. Spawn one subagent per AI seat. Give each subagent only:
   - server URL
   - session id
   - seat id
   - that seat's token
6. Instruct each subagent to run the seat client with `--auto`.
7. Wait for the server attendance summary to show all eight seats joined.
8. Start day 1 only after full attendance.

Do not include role assignments, hidden state, or summaries in subagent prompts.

## Running the Game

Main observes GM projection through the GM client and progresses the game through GM events.

Day and night are timed free-chat windows. Main should use the phase timer to decide when to close discussion or night action collection; main must not run a player-by-player turn loop.

Main may:

- start the game after all seats have attended
- announce phase changes
- resolve night actions
- resolve votes
- eliminate players
- publish public announcements
- send private notices
- declare game over

Main must not:

- decide what a player says
- choose a player vote or target
- tell a subagent when to respond
- expose hidden roles in chat
- update the web UI

## Free Chat Handling

Public chat remains open while players are alive. Main should let player conversation develop through server events.

Main may intervene only as GM:

- to resolve a rules event
- to move from day to night or night to day
- to reject or ignore illegal player events already rejected by the server
- to end the game

## Resolution Guidance

The server validates permissions, not strategy. Main resolves game consequences from accepted player events.

For votes:

- read accepted `vote` events in GM state
- choose the latest valid vote per living player unless a future rules document changes this
- eliminate the target with a strict plurality or majority according to the active rule
- publish the result as a GM event

For night:

- mafia `night_action` with `action: kill` supplies kill candidates
- detective `night_action` with `action: investigate` supplies investigation target
- doctor `night_action` with `action: protect` supplies protection target
- main resolves conflicts and publishes only player-visible consequences
- private results go through `private_notice`

## Shutdown

When the game reaches `game_over`, close all subagents and stop watches. Do not leave player clients running after the session is complete.
