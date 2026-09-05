# Turn Contract

Use when authoring a TurnBundle and its contract is not already in context. Load examples or UI-label details only for the relevant operation.

## CLI and Context

Use `uv run --no-project python "$SKILL_DIR/scripts/world_simulator.py" <command>`, with `SKILL_DIR` set to this skill's absolute directory. Commands accept `--root <storage-root>` and `--session <id>`; keep the same locator throughout a session.

- `next`: claim browser input and return `session`, `turn`, focus records, the complete active `world_index`, and `inspect_hint`.
- `inspect [query]`: retrieve GM-visible records and history without a result cap.
- `commit <bundle.json>`: validate and atomically persist the claimed turn.
- `status`: storage metadata and counts.

Studio/Begin receive the full active world in focus. Play receives focused records plus the full index; inspect other records when their truth affects the turn.

## Bundle Shape

Only the claimed `turn_id` and non-empty `response.markdown` are globally mandatory. Omit unchanged session fields and unused arrays:

```json
{
  "turn_id": 1,
  "response": {"markdown": "Visible response"},
  "upsert_entities": [],
  "upsert_relations": [],
  "retire_relations": [],
  "events": []
}
```

Replace the example ID with the claimed turn. Optional `session` patches session fields. For a complete record example, consult [turn-examples.md](turn-examples.md).

- `response.status`: localized `{label, value}` strings.
- `response.emphasis`: exact non-empty phrases from the visible prose. Keep prose free of inline emphasis markup; the browser also emphasizes quoted dialogue.
- `response.visuals`: objects with `asset_path` referencing an existing file under the session's `assets/`; localize alt text and captions.
- `events`: objects with `entity_ids`, canonical `public_summary`, `gm_summary`, and `data`.

## Create and Patch

Use stable lowercase IDs containing letters, digits, and hyphens.

New entities require `id`, `kind`, `name`, `aliases`, `public`, `gm`, `presentation`, `visibility`, and `active`. New relations require `id`, `source_id`, `predicate`, `target_id`, both fact objects, `presentation`, `visibility`, and `active`.

For an existing record, send its ID and changed fields only. Omission preserves the old value; arrays such as `aliases` replace the entire array.

`public`, `gm`, and `presentation` use JSON Merge Patch: objects merge recursively, scalars/arrays replace, and `null` removes a property. Session `narration` and `presentation` follow the same semantics.

Retire entities with `active: false`; retire relations that way or through `retire_relations`. Relation endpoints, event entity IDs, `player_id`, and `scene_id` must reference known entities after the bundle's updates.

## Language and Visibility

Canonical names, aliases, facts, predicates, event data, and narration profile are English. Preserve `turn.user_text` exactly. Visible prose, status, captions, and `presentation` use the user's language.

Presentation expresses canonical facts without inventing a second truth. Update canonical visible facts and their localized presentation together. Read [presentation-ui.md](presentation-ui.md) when creating or changing browser labels.

`visibility` is `public` or `gm`. Studio may show GM material for co-authoring; Play excludes GM-only records and facts. Existing sessions are preserved as stored, without automatic translation of legacy records.

## Commit Semantics

Commit is atomic. Recommitting the same normalized bundle is idempotent; different content for an already completed turn is rejected. Correct a failed bundle for the same claimed turn rather than claim another input.
