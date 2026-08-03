# Turn Contract

The CLI is the boundary between Codex authorship and deterministic storage.

## Commands

All commands use the active marker under `world-runs/` unless `--root` or `--session` is supplied.

```bash
python scripts/world_simulator.py start [--root <dir>] [--session <id>] [--port 8765]
python scripts/world_simulator.py next [--root <dir>] [--session <id>] [--poll 0.5]
python scripts/world_simulator.py commit [--root <dir>] [--session <id>] <bundle.json>
python scripts/world_simulator.py status [--root <dir>] [--session <id>]
python scripts/world_simulator.py inspect [--root <dir>] [--session <id>] [query]
```

With no `--session`, `start` creates a new Studio session; the other commands use the active marker. Stop the server with an interrupt when the user is finished.

`next` waits until the browser submits an input, marks it `processing`, and prints one object with `session`, `turn`, `entities`, `relations`, `recent_turns`, `recent_events`, `available_entity_count`, and `inspect_hint`. `turn.kind` is `studio`, `begin`, or `play`. Use `inspect` for missing GM-visible facts.

## TurnBundle

Commit exactly one JSON object for the claimed `turn.id`:

```json
{
  "turn_id": 1,
  "response": {
    "markdown": "The visible Studio summary or scene response.",
    "scene_label": "Optional scene label",
    "status": [{"location": "Glass Harbor"}],
    "visuals": [
      {
        "asset_path": "assets/harbor.webp",
        "alt": "A rain-dark harbor beneath glass towers",
        "caption": "Glass Harbor at low tide"
      }
    ]
  },
  "session": {
    "display_name": "The Cartographers of Rain",
    "language": "ko",
    "mode": "studio",
    "player_id": "player",
    "scene_id": "scene-glass-harbor"
  },
  "upsert_entities": [
    {
      "id": "player",
      "kind": "player",
      "name": "Mira",
      "aliases": [],
      "public": {"calling": "forbidden cartographer"},
      "gm": {"unrevealed_debt": "owes the harbor itself"},
      "visibility": "public",
      "active": true
    }
  ],
  "upsert_relations": [
    {
      "id": "mira-hunted-by-census",
      "source_id": "player",
      "predicate": "hunted-by",
      "target_id": "rain-census",
      "public": {},
      "gm": {"reason": "stolen map"},
      "visibility": "gm",
      "active": true
    }
  ],
  "retire_relations": [],
  "events": [
    {
      "entity_ids": ["player"],
      "public_summary": "Mira entered Glass Harbor.",
      "gm_summary": "The harbor recognized its debtor.",
      "data": {"time": "low tide"}
    }
  ]
}
```

Only `turn_id` and non-empty `response.markdown` are mandatory. Omitted arrays and objects become empty. Include only session fields that change.

## State Semantics

- IDs use lowercase letters, digits, and hyphens and remain stable for the session.
- Entity upserts replace `kind`, `name`, `aliases`, `public`, `gm`, `visibility`, and `active` as complete values.
- Retire an entity by upserting its full record with `active: false`.
- Relation upserts likewise replace their stored values. Both endpoints must exist after the entity upserts in the same bundle.
- `visibility` is `public` or `gm`. During Play, GM fields and GM-only entities and relations never appear in the browser API.
- `gm.next_due` may hold a turn number; due entities are automatically added to later `next` context.
- Visual paths must name an existing file below that session's `assets/` directory.
- Session `player_id` and `scene_id` must reference known entities.
- A successful commit is atomic. Recommitting the same normalized bundle content is idempotent; different content for an already complete turn is rejected.

The `response` is the only player-facing narration. Its `markdown` field supports `**bold**` emphasis; use it for important words, decisive sentences, and complete spoken lines. Events are compact causal memory; entities are current truth; relations are durable graph edges; GM fields are private direction.
