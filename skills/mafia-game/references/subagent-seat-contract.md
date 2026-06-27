# Subagent Seat Contract

Each subagent is an autonomous player. It is not a one-shot responder.

Each subagent receives an in-game persona from its server projection. This persona is public roleplay style only. It must not be treated as hidden alignment or role information.

## Spawn Contract

Main must create every AI seat subagent with:

- `model`: `gpt-5.5`
- `reasoning_effort`: `medium`

Main may provide only:

- server URL
- session id
- seat id
- seat token
- instruction to use `$mafia-game` and run the seat client

Main must not provide:

- GM state
- role list
- other seat tokens
- private channel content not visible to the seat
- tactical instructions
- "your turn" prompts
- summaries of recent events outside the server projection

## Operating Loop

Each subagent should:

1. Run the seat client `--auto`.
2. Read only events printed by the seat client or the seat projection from `--state`.
3. Follow its own `persona_view` voice when speaking.
4. Keep public and private messages short: one or two sentences, normally under 140 Korean characters.
5. Decide independently whether to speak, stay silent, vote, or act.
6. Submit events through the seat client.
7. Keep the autonomous loop running and retry server failures.

The subagent may maintain its own reasoning in its own conversation context. It must not inspect server files directly.

## Allowed Script Actions

Common commands:

```bash
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --state
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --watch
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --auto
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --say "message"
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --vote seat-05
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --mafia "message"
python3 skills/mafia-game/scripts/mafia_player_client.py --server <url> --session <id> --seat <seat> --token <token> --night kill seat-06
```

## Privacy Rules

The subagent must treat missing information as unknown. It may lie in character, but it must not claim hidden facts obtained outside its own projection.

If a command is rejected, the subagent should continue watching and adjust its play from visible server state.
