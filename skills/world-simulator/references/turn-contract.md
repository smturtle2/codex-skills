# Turn Contract

The CLI is the boundary between Codex authorship and deterministic storage.

## Commands and Context

```bash
python scripts/world_simulator.py start [--root <dir>] [--session <id>] [--port 8765]
python scripts/world_simulator.py next [--root <dir>] [--session <id>] [--poll 0.5]
python scripts/world_simulator.py commit [--root <dir>] [--session <id>] <bundle.json>
python scripts/world_simulator.py status [--root <dir>] [--session <id>]
python scripts/world_simulator.py inspect [--root <dir>] [--session <id>] [query]
```

`next` claims one `studio`, `begin`, or `play` turn and returns:

- `session`: canonical session data, including narration and localized presentation;
- `turn`: the exact claimed input;
- `focus.entities` and `focus.relations`: full records for the player, current scene, explicitly named entities, and their direct relations;
- `world_index`: a compact, complete index of every active entity and relation;
- `inspect_hint`: when to retrieve more detail.

Studio and Begin receive the full active world in `focus`. Play receives the focused records plus the full index. The runtime does not select story records by kind, schedule, recent-turn window, or narrative condition.

`inspect` searches the full ledger—entities, relations, events, and exact turns—without hiding records behind a result cap. Its output is GM-visible and may contain secrets.

## Language Boundary

Canonical internal world data is English. This includes session `display_name` and `narration`, entity `name`, `aliases`, `public`, and `gm`, relation predicates and facts, and event summaries and data. Use stable Latin/English forms for canonical names and aliases.

Preserve `turn.user_text` exactly as submitted. Write `response.markdown`, `scene_label`, `status`, visual alt text and captions, and all `presentation` values in the user's language and script.

`presentation` is non-authoritative. It expresses the matching canonical fact without adding a second version of world truth. Whenever a canonical visible fact changes, update its localized presentation in the same bundle.

## TurnBundle

Commit one JSON object for the claimed `turn.id`:

```json
{
  "turn_id": 1,
  "response": {
    "markdown": "비가 지도 위의 잉크를 거꾸로 끌어올린다. 항구가 미라의 빚을 알아본 것이다.",
    "emphasis": ["항구가 미라의 빚을 알아본 것이다."],
    "scene_label": "유리항 · 썰물",
    "status": [
      {"label": "위치", "value": "유리항"},
      {"label": "상황", "value": "항구가 미라를 알아봄"}
    ],
    "visuals": []
  },
  "session": {
    "display_name": "The Cartographers of Rain",
    "language": "ko",
    "mode": "studio",
    "player_id": "player",
    "scene_id": "scene-glass-harbor",
    "narration": {
      "role": "A close dramatic storyteller who makes the world's responses tangible.",
      "focalization": "Limited to what Mira can perceive, with no unrevealed GM knowledge.",
      "voice": "Lucid, rain-dark, observant, and unsentimental.",
      "delivery": "Lead with consequences, keep action spatially clear, and let dialogue carry character friction."
    },
    "presentation": {
      "display_name": "비의 지도 제작자들",
      "narration": {
        "role": {"label": "서술자의 역할", "value": "세계의 반응을 손에 잡히게 전하는 근접한 극적 서술자"},
        "focalization": {"label": "시점", "value": "미라가 감지할 수 있는 범위에 한정"},
        "voice": {"label": "목소리", "value": "명료하고 비에 젖은 듯하며 관찰력이 있고 감상적이지 않음"},
        "delivery": {"label": "전달 방식", "value": "결과를 먼저 보여주고 행동의 공간 관계를 명확히 함"}
      },
      "ui": {
        "rail_title": "모험 기록",
        "character_tab": "인물",
        "world_tab": "세계",
        "send": "전송",
        "begin_button": "모험 시작",
        "begin_input": "모험을 시작한다."
      }
    }
  },
  "upsert_entities": [
    {
      "id": "player",
      "kind": "player",
      "name": "Mira",
      "aliases": [],
      "public": {"calling": "Forbidden cartographer"},
      "gm": {"unrevealed_debt": "She owes the harbor itself."},
      "presentation": {
        "name": "미라",
        "aliases": [],
        "kind_label": "플레이어",
        "public": {
          "calling": {"label": "역할", "value": "금지된 지도 제작자"}
        },
        "gm": {
          "unrevealed_debt": {"label": "숨겨진 빚", "value": "항구 자체에 빚을 지고 있음"}
        }
      },
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
      "gm": {"reason": "A stolen map"},
      "presentation": {
        "predicate_label": "추적당함",
        "public": {},
        "gm": {"reason": {"label": "이유", "value": "훔친 지도"}}
      },
      "visibility": "gm",
      "active": true
    }
  ],
  "retire_relations": [],
  "events": [
    {
      "entity_ids": ["player", "scene-glass-harbor"],
      "public_summary": "Mira entered Glass Harbor, which visibly recognized her.",
      "gm_summary": "The harbor recognized its debtor.",
      "data": {"tide": "low"}
    }
  ]
}
```

Only `turn_id` and non-empty `response.markdown` are globally mandatory. Omitted top-level arrays and patch objects are empty. Include only changed session fields.

`response.status` is an array of localized `{label, value}` strings. The browser displays every supplied item.

Write `response.markdown` as clean visible prose without inline emphasis markup. Put exact localized words, phrases, or decisive sentences that need emphasis in `response.emphasis`. Select them by meaning: emphasize what defines the Studio concept or changes how the player understands and acts in a scene. Do not use a fixed quota or decorate ordinary supporting prose. The browser also emphasizes complete spoken lines enclosed by `“…”`, `"..."`, `「…」`, or `『…』`. Legacy Markdown emphasis remains readable but must not be authored in new bundles.

## Create and Patch Semantics

IDs use lowercase letters, digits, and hyphens and remain stable.

A new entity must include `id`, `kind`, `name`, `aliases`, `public`, `gm`, `presentation`, `visibility`, and `active`. A new relation must include its corresponding complete set: `id`, endpoints, `predicate`, both fact objects, `presentation`, `visibility`, and `active`.

To update an existing entity or relation, send its `id` plus only the fields that changed. Omitted top-level fields remain unchanged. `aliases` and other arrays replace the old array.

`public`, `gm`, and `presentation` use JSON Merge Patch semantics:

- an omitted property remains unchanged;
- an object recursively merges;
- a scalar or array replaces the old value;
- `null` removes that property.

For example, this preserves every unmentioned player field, changes one fact and its localization, and removes a stale secret:

```json
{
  "id": "player",
  "public": {"calling": "Harbor-recognized cartographer"},
  "gm": {"unrevealed_debt": null},
  "presentation": {
    "public": {
      "calling": {"label": "역할", "value": "항구가 알아본 지도 제작자"}
    },
    "gm": {"unrevealed_debt": null}
  }
}
```

Session `narration` and `presentation` use the same merge semantics. Set `active: false` to retire an entity. Use `retire_relations` or patch `active: false` to retire a relation. Relation endpoints must exist after entity updates in the same bundle.

`visibility` is `public` or `gm`. During Play, the browser receives localized presentation for public records and no GM-only truth. Existing sessions are preserved as stored; the runtime does not translate legacy data automatically.

Visual paths must name existing files under the session's `assets/` directory. `player_id` and `scene_id` must reference known entities. A successful commit is atomic. Recommitting the same normalized bundle is idempotent; different content for a completed turn is rejected.

## Presentation UI Keys

Set session `presentation.ui` during Studio in the user's language. The browser recognizes these keys and keeps existing values when a later bundle omits them:

`app_name`, `rail_title`, `close_rail`, `character_tab`, `world_tab`, `older_turns`, `empty_title`, `empty_body`, `input_label`, `keyboard_hint`, `begin_button`, `untitled_world`, `studio_scene`, `play_scene`, `boolean_true`, `boolean_false`, `status_label`, `character_empty`, `character_detail_empty`, `location_label`, `character_section`, `character_facts_empty`, `inventory_section`, `location_section`, `gm_note`, `relations_section`, `scene_section`, `world_empty`, `concept_mark`, `visual_alt`, `processing_turn`, `turn_error`, `studio_input_title`, `play_input_title`, `studio_input_context`, `current_scene`, `studio_placeholder`, `play_placeholder`, `waiting`, `send`, `begin_input`, `load_error_title`, and `load_error_body`.
