# Full Record Example

Consult this only when the compact turn contract is insufficient for creating records or localized presentation. Replace all example content with the active world's facts.

This example assumes `scene-glass-harbor` and `rain-census` already exist. It is not a standalone world initializer; every reference must resolve after the bundle's updates.

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
