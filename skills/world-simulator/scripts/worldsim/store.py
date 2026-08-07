from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sqlite3
import time
import uuid
from typing import Any

DEFAULT_ROOT = pathlib.Path("world-runs")
ACTIVE_FILE = ".world-simulator-active.json"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
VALID_MODES = {"studio", "play"}
VALID_TURN_KINDS = {"studio", "begin", "play"}


class WorldSimError(ValueError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def atomic_write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def new_session_id(root: pathlib.Path) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    while True:
        candidate = f"world-{stamp}-{uuid.uuid4().hex[:6]}"
        if not (root / candidate).exists():
            return candidate


def write_active_session(root: pathlib.Path, session_id: str) -> None:
    atomic_write_json(root / ACTIVE_FILE, {"session_id": session_id, "updated_at": utc_now()})


def read_active_session(root: pathlib.Path) -> str:
    marker = root / ACTIVE_FILE
    if not marker.exists():
        raise WorldSimError("No active world session. Run the start command first.")
    data = json.loads(marker.read_text(encoding="utf-8"))
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not ID_PATTERN.fullmatch(session_id):
        raise WorldSimError("The active world session marker is invalid.")
    return session_id


def resolve_session(root: pathlib.Path, session_id: str | None) -> pathlib.Path:
    resolved_id = session_id or read_active_session(root)
    if not ID_PATTERN.fullmatch(resolved_id):
        raise WorldSimError("Session IDs must use lowercase letters, digits, and hyphens.")
    session_path = root / resolved_id
    if not (session_path / "world.sqlite3").exists():
        raise WorldSimError(f"World session does not exist: {resolved_id}")
    return session_path


def connect(session_path: pathlib.Path) -> sqlite3.Connection:
    connection = sqlite3.connect(session_path / "world.sqlite3", timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    _migrate_schema(connection)
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
    )


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _migrate_schema(connection: sqlite3.Connection) -> None:
    changed = False
    if _table_exists(connection, "entities") and "presentation_json" not in _column_names(connection, "entities"):
        connection.execute("ALTER TABLE entities ADD COLUMN presentation_json TEXT NOT NULL DEFAULT '{}'")
        changed = True
    if _table_exists(connection, "relations") and "presentation_json" not in _column_names(connection, "relations"):
        connection.execute("ALTER TABLE relations ADD COLUMN presentation_json TEXT NOT NULL DEFAULT '{}'")
        changed = True
    if _table_exists(connection, "meta"):
        meta = read_meta(connection)
        defaults = {
            "schema_version": "2",
            "narration": "{}",
            "presentation": "{}",
        }
        for key, value in defaults.items():
            if meta.get(key) != value and (key == "schema_version" or key not in meta):
                set_meta(connection, key, value)
                changed = True
    if changed:
        connection.commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    user_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    response_markdown TEXT,
    response_json TEXT,
    bundle_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    public_json TEXT NOT NULL DEFAULT '{}',
    gm_json TEXT NOT NULL DEFAULT '{}',
    presentation_json TEXT NOT NULL DEFAULT '{}',
    visibility TEXT NOT NULL DEFAULT 'public',
    active INTEGER NOT NULL DEFAULT 1,
    created_turn INTEGER,
    updated_turn INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    target_id TEXT NOT NULL,
    public_json TEXT NOT NULL DEFAULT '{}',
    gm_json TEXT NOT NULL DEFAULT '{}',
    presentation_json TEXT NOT NULL DEFAULT '{}',
    visibility TEXT NOT NULL DEFAULT 'public',
    active INTEGER NOT NULL DEFAULT 1,
    created_turn INTEGER,
    updated_turn INTEGER NOT NULL,
    FOREIGN KEY(source_id) REFERENCES entities(id),
    FOREIGN KEY(target_id) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    public_summary TEXT NOT NULL DEFAULT '',
    gm_summary TEXT NOT NULL DEFAULT '',
    data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(turn_id) REFERENCES turns(id)
);

CREATE INDEX IF NOT EXISTS turns_status_idx ON turns(status, id);
CREATE INDEX IF NOT EXISTS entities_kind_idx ON entities(kind, active);
CREATE INDEX IF NOT EXISTS relations_source_idx ON relations(source_id, active);
CREATE INDEX IF NOT EXISTS relations_target_idx ON relations(target_id, active);
CREATE INDEX IF NOT EXISTS events_turn_idx ON events(turn_id, id);
"""


def init_session(session_path: pathlib.Path) -> dict[str, Any]:
    session_path.mkdir(parents=True, exist_ok=False)
    (session_path / "assets").mkdir()
    with connect(session_path) as connection:
        connection.executescript(SCHEMA)
        initial = {
            "schema_version": "2",
            "session_id": session_path.name,
            "display_name": "Untitled World",
            "mode": "studio",
            "language": "ko",
            "player_id": "",
            "scene_id": "",
            "narration": "{}",
            "presentation": "{}",
            "created_at": utc_now(),
        }
        connection.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", initial.items())
        _migrate_schema(connection)
    return session_status(session_path)


def read_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM meta")}


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _session_payload(meta: dict[str, str]) -> dict[str, Any]:
    return {
        "session_id": meta.get("session_id", ""),
        "display_name": meta.get("display_name", "Untitled World"),
        "mode": meta.get("mode", "studio"),
        "language": meta.get("language", "ko"),
        "player_id": meta.get("player_id", ""),
        "scene_id": meta.get("scene_id", ""),
        "narration": json_load(meta.get("narration"), {}),
        "presentation": json_load(meta.get("presentation"), {}),
    }


def session_status(session_path: pathlib.Path) -> dict[str, Any]:
    with connect(session_path) as connection:
        meta = read_meta(connection)
        counts = {
            "turns": connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
            "pending": connection.execute(
                "SELECT COUNT(*) FROM turns WHERE status IN ('pending', 'processing')"
            ).fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities WHERE active=1").fetchone()[0],
            "relations": connection.execute("SELECT COUNT(*) FROM relations WHERE active=1").fetchone()[0],
            "events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        }
    return {
        "session_id": session_path.name,
        "session_path": str(session_path.resolve()),
        "meta": meta,
        **counts,
    }


def submit_input(session_path: pathlib.Path, text: str, kind: str | None = None) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        raise WorldSimError("Input cannot be empty.")
    with connect(session_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        outstanding = connection.execute(
            "SELECT id FROM turns WHERE status IN ('pending', 'processing') ORDER BY id LIMIT 1"
        ).fetchone()
        if outstanding:
            raise WorldSimError("The previous input is still being processed.")
        meta = read_meta(connection)
        resolved_kind = kind or ("studio" if meta.get("mode") == "studio" else "play")
        if resolved_kind not in VALID_TURN_KINDS:
            raise WorldSimError(f"Unsupported input kind: {resolved_kind}")
        if resolved_kind == "begin" and meta.get("mode") != "studio":
            raise WorldSimError("The adventure has already begun.")
        cursor = connection.execute(
            "INSERT INTO turns(kind, user_text, status, created_at) VALUES(?, ?, 'pending', ?)",
            (resolved_kind, cleaned, utc_now()),
        )
        turn_id = int(cursor.lastrowid)
        connection.commit()
    return {
        "turn_id": turn_id,
        "kind": resolved_kind,
        "user_text": cleaned,
        "status": "pending",
    }


def _row_entity(row: sqlite3.Row, include_gm: bool) -> dict[str, Any]:
    entity = {
        "id": row["id"],
        "kind": row["kind"],
        "name": row["name"],
        "aliases": json_load(row["aliases_json"], []),
        "public": json_load(row["public_json"], {}),
        "presentation": json_load(row["presentation_json"], {}),
        "visibility": row["visibility"],
        "active": bool(row["active"]),
        "updated_turn": row["updated_turn"],
    }
    if include_gm:
        entity["gm"] = json_load(row["gm_json"], {})
    return entity


def _row_relation(row: sqlite3.Row, include_gm: bool) -> dict[str, Any]:
    relation = {
        "id": row["id"],
        "source_id": row["source_id"],
        "predicate": row["predicate"],
        "target_id": row["target_id"],
        "public": json_load(row["public_json"], {}),
        "presentation": json_load(row["presentation_json"], {}),
        "visibility": row["visibility"],
        "active": bool(row["active"]),
        "updated_turn": row["updated_turn"],
    }
    if include_gm:
        relation["gm"] = json_load(row["gm_json"], {})
    return relation


def _turn_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "user_text": row["user_text"],
        "status": row["status"],
        "response": json_load(row["response_json"], None),
        "error": row["error"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }


def _localized_fact_map(presentation: dict[str, Any], key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    value = presentation.get(key)
    return value if isinstance(value, dict) else fallback


def _browser_entity(entity: dict[str, Any], include_gm: bool) -> dict[str, Any]:
    presentation = entity.get("presentation", {})
    localized = presentation if isinstance(presentation, dict) else {}
    payload = {
        "id": entity["id"],
        "kind": entity["kind"],
        "kind_label": localized.get("kind_label", entity["kind"]),
        "name": localized.get("name", entity["name"]),
        "aliases": localized.get("aliases", entity.get("aliases", [])),
        "public": _localized_fact_map(localized, "public", entity.get("public", {})),
        "visibility": entity["visibility"],
        "active": entity["active"],
        "updated_turn": entity["updated_turn"],
    }
    if include_gm:
        payload["gm"] = _localized_fact_map(localized, "gm", entity.get("gm", {}))
    return payload


def _browser_relation(relation: dict[str, Any], include_gm: bool) -> dict[str, Any]:
    presentation = relation.get("presentation", {})
    localized = presentation if isinstance(presentation, dict) else {}
    payload = {
        "id": relation["id"],
        "source_id": relation["source_id"],
        "predicate": relation["predicate"],
        "predicate_label": localized.get("predicate_label", relation["predicate"]),
        "target_id": relation["target_id"],
        "public": _localized_fact_map(localized, "public", relation.get("public", {})),
        "visibility": relation["visibility"],
        "active": relation["active"],
        "updated_turn": relation["updated_turn"],
    }
    if include_gm:
        payload["gm"] = _localized_fact_map(localized, "gm", relation.get("gm", {}))
    return payload


def list_turns(
    session_path: pathlib.Path,
    *,
    before: int | None = None,
    after: int | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 100))
    with connect(session_path) as connection:
        if after is not None:
            rows = connection.execute(
                "SELECT * FROM turns WHERE id > ? ORDER BY id ASC LIMIT ?",
                (after, safe_limit),
            ).fetchall()
            has_more = (
                bool(rows)
                and connection.execute("SELECT 1 FROM turns WHERE id > ? LIMIT 1", (rows[-1]["id"],)).fetchone()
                is not None
            )
        else:
            boundary = before if before is not None else 2**63 - 1
            rows = connection.execute(
                "SELECT * FROM turns WHERE id < ? ORDER BY id DESC LIMIT ?",
                (boundary, safe_limit),
            ).fetchall()
            rows = list(reversed(rows))
            has_more = (
                bool(rows)
                and connection.execute("SELECT 1 FROM turns WHERE id < ? LIMIT 1", (rows[0]["id"],)).fetchone()
                is not None
            )
    return {"items": [_turn_payload(row) for row in rows], "has_more": has_more}


def public_state(session_path: pathlib.Path) -> dict[str, Any]:
    with connect(session_path) as connection:
        meta = read_meta(connection)
        studio = meta.get("mode") == "studio"
        entity_rows = connection.execute(
            "SELECT * FROM entities WHERE active=1 AND (? OR visibility='public') ORDER BY kind, name COLLATE NOCASE",
            (studio,),
        ).fetchall()
        if studio:
            relation_rows = connection.execute(
                "SELECT * FROM relations WHERE active=1 ORDER BY predicate, id"
            ).fetchall()
        else:
            relation_rows = connection.execute(
                "SELECT * FROM relations WHERE active=1 AND visibility='public' ORDER BY predicate, id"
            ).fetchall()
        latest = connection.execute(
            "SELECT response_json FROM turns WHERE status='complete' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        outstanding = connection.execute(
            "SELECT id FROM turns WHERE status IN ('pending', 'processing') ORDER BY id LIMIT 1"
        ).fetchone()
        completed_studio = connection.execute(
            "SELECT COUNT(*) FROM turns WHERE status='complete' AND kind='studio'"
        ).fetchone()[0]
    session = _session_payload(meta)
    presentation = session["presentation"]
    return {
        "session_id": session_path.name,
        "display_name": presentation.get("display_name", session["display_name"]),
        "mode": session["mode"],
        "language": session["language"],
        "player_id": session["player_id"],
        "scene_id": session["scene_id"],
        "narration": presentation.get("narration", session["narration"]),
        "presentation": presentation,
        "entities": [_browser_entity(_row_entity(row, include_gm=studio), include_gm=studio) for row in entity_rows],
        "relations": [
            _browser_relation(_row_relation(row, include_gm=studio), include_gm=studio) for row in relation_rows
        ],
        "latest_response": json_load(latest["response_json"], None) if latest else None,
        "processing": outstanding["id"] if outstanding else None,
        "can_begin": studio and completed_studio > 0 and bool(entity_rows),
    }


def _entity_search_text(entity: dict[str, Any]) -> str:
    return " ".join(
        [
            entity["id"],
            entity["kind"],
            entity["name"],
            *entity.get("aliases", []),
            json.dumps(entity.get("public", {}), ensure_ascii=False),
            json.dumps(entity.get("gm", {}), ensure_ascii=False),
            json.dumps(entity.get("presentation", {}), ensure_ascii=False),
        ]
    ).lower()


def next_turn_context(session_path: pathlib.Path, poll_interval: float = 0.5) -> dict[str, Any]:
    while True:
        with connect(session_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            turn = connection.execute(
                "SELECT * FROM turns WHERE status IN ('processing', 'pending') ORDER BY id LIMIT 1"
            ).fetchone()
            if turn:
                if turn["status"] == "pending":
                    connection.execute("UPDATE turns SET status='processing' WHERE id=?", (turn["id"],))
                connection.commit()
                return build_turn_context(connection, turn["id"])
            connection.commit()
        time.sleep(poll_interval)


def build_turn_context(connection: sqlite3.Connection, turn_id: int) -> dict[str, Any]:
    turn = connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
    if turn is None:
        raise WorldSimError(f"Turn not found: {turn_id}")
    meta = read_meta(connection)
    all_rows = connection.execute(
        "SELECT * FROM entities WHERE active=1 ORDER BY kind, name COLLATE NOCASE, id"
    ).fetchall()
    all_entities = [_row_entity(row, include_gm=True) for row in all_rows]
    by_id = {entity["id"]: entity for entity in all_entities}
    relation_rows = connection.execute("SELECT * FROM relations WHERE active=1 ORDER BY predicate, id").fetchall()
    relations = [_row_relation(row, include_gm=True) for row in relation_rows]
    if turn["kind"] in {"studio", "begin"}:
        selected_ids = set(by_id)
        relevant_relations = relations
    else:
        selected_ids = {meta[key] for key in ("player_id", "scene_id") if meta.get(key) in by_id}
        lowered_input = turn["user_text"].lower()
        for entity in all_entities:
            names = [entity["name"], *entity.get("aliases", [])]
            presentation = entity.get("presentation", {})
            if isinstance(presentation, dict):
                localized_name = presentation.get("name")
                if isinstance(localized_name, str):
                    names.append(localized_name)
                localized_aliases = presentation.get("aliases", [])
                if isinstance(localized_aliases, list):
                    names.extend(alias for alias in localized_aliases if isinstance(alias, str))
            if any(name and name.lower() in lowered_input for name in names):
                selected_ids.add(entity["id"])
        focus_seeds = set(selected_ids)
        relevant_relations = [
            relation
            for relation in relations
            if relation["source_id"] in focus_seeds or relation["target_id"] in focus_seeds
        ]
        for relation in relevant_relations:
            selected_ids.add(relation["source_id"])
            selected_ids.add(relation["target_id"])
    return {
        "session": _session_payload(meta),
        "turn": _turn_payload(turn),
        "focus": {
            "entities": [by_id[entity_id] for entity_id in sorted(selected_ids) if entity_id in by_id],
            "relations": relevant_relations,
        },
        "world_index": {
            "entities": [
                {
                    "id": entity["id"],
                    "kind": entity["kind"],
                    "name": entity["name"],
                    "aliases": entity.get("aliases", []),
                    "visibility": entity["visibility"],
                }
                for entity in all_entities
            ],
            "relations": [
                {
                    "id": relation["id"],
                    "source_id": relation["source_id"],
                    "predicate": relation["predicate"],
                    "target_id": relation["target_id"],
                    "visibility": relation["visibility"],
                }
                for relation in relations
            ],
        },
        "inspect_hint": "Use inspect when a turn depends on records outside focus.",
    }


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise WorldSimError(f"{label} must use lowercase letters, digits, and hyphens.")
    return value


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorldSimError(f"{label} must be an object.")
    return value


def _require_string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise WorldSimError(f"{label} must be an array of strings.")
    return value


def _merge_patch(target: Any, patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = _merge_patch(result.get(key), value)
        else:
            result[key] = value
    return result


def _normalize_optional_object(source: dict[str, Any], key: str, label: str, target: dict[str, Any]) -> None:
    if key in source:
        if not isinstance(source[key], dict):
            raise WorldSimError(f"{label} must be an object.")
        target[key] = source[key]


def _normalize_optional_string_list(source: dict[str, Any], key: str, label: str, target: dict[str, Any]) -> None:
    if key in source:
        value = source[key]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise WorldSimError(f"{label} must be an array of strings.")
        target[key] = value


def _safe_asset_reference(session_path: pathlib.Path, value: str) -> str:
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "assets":
        raise WorldSimError("Visual asset paths must stay under the session assets directory.")
    target = session_path.joinpath(*path.parts)
    if not target.is_file():
        raise WorldSimError(f"Visual asset does not exist: {value}")
    return path.as_posix()


def normalize_bundle(session_path: pathlib.Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WorldSimError("TurnBundle must be a JSON object.")
    turn_id = payload.get("turn_id")
    if not isinstance(turn_id, int) or turn_id < 1:
        raise WorldSimError("TurnBundle.turn_id must be a positive integer.")
    response = _require_object(payload.get("response"), "response")
    markdown = response.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise WorldSimError("response.markdown must contain the visible turn response.")
    status = response.get("status", [])
    if not isinstance(status, list) or any(not isinstance(item, dict) for item in status):
        raise WorldSimError("response.status must be an array of objects.")
    normalized_status = []
    for index, item in enumerate(status):
        label = item.get("label")
        value = item.get("value")
        if not isinstance(label, str) or not label.strip():
            raise WorldSimError(f"response.status[{index}].label must be a non-empty string.")
        if not isinstance(value, str) or not value.strip():
            raise WorldSimError(f"response.status[{index}].value must be a non-empty string.")
        normalized_status.append({"label": label.strip(), "value": value.strip()})
    visuals = response.get("visuals", [])
    if not isinstance(visuals, list) or any(not isinstance(item, dict) for item in visuals):
        raise WorldSimError("response.visuals must be an array of objects.")
    normalized_visuals = []
    for index, visual in enumerate(visuals):
        asset_path = visual.get("asset_path")
        if not isinstance(asset_path, str):
            raise WorldSimError(f"response.visuals[{index}].asset_path is required.")
        normalized_visuals.append({**visual, "asset_path": _safe_asset_reference(session_path, asset_path)})
    emphasis = response.get("emphasis", [])
    if not isinstance(emphasis, list) or any(
        not isinstance(phrase, str) or not phrase.strip() for phrase in emphasis
    ):
        raise WorldSimError("response.emphasis must be an array of non-empty strings.")
    normalized_response = {
        "markdown": markdown.strip(),
        "emphasis": [phrase.strip() for phrase in emphasis],
        "scene_label": str(response.get("scene_label", "")).strip(),
        "status": normalized_status,
        "visuals": normalized_visuals,
    }
    session_patch = _require_object(payload.get("session"), "session")
    normalized_session: dict[str, Any] = {}
    for key in ("display_name", "language"):
        if key in session_patch:
            if not isinstance(session_patch[key], str) or not session_patch[key].strip():
                raise WorldSimError(f"session.{key} must be a non-empty string.")
            normalized_session[key] = session_patch[key].strip()
    if "mode" in session_patch:
        if session_patch["mode"] not in VALID_MODES:
            raise WorldSimError("session.mode must be studio or play.")
        normalized_session["mode"] = session_patch["mode"]
    for key in ("player_id", "scene_id"):
        if key in session_patch:
            normalized_session[key] = _require_id(session_patch[key], f"session.{key}")
    _normalize_optional_object(session_patch, "narration", "session.narration", normalized_session)
    _normalize_optional_object(session_patch, "presentation", "session.presentation", normalized_session)
    entities = payload.get("upsert_entities", [])
    if not isinstance(entities, list):
        raise WorldSimError("upsert_entities must be an array.")
    normalized_entities = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise WorldSimError(f"upsert_entities[{index}] must be an object.")
        entity_id = _require_id(entity.get("id"), f"upsert_entities[{index}].id")
        normalized_entity: dict[str, Any] = {"id": entity_id}
        for key in ("kind", "name"):
            if key in entity:
                value = entity[key]
                if not isinstance(value, str) or not value.strip():
                    raise WorldSimError(f"upsert_entities[{index}].{key} must be a non-empty string.")
                normalized_entity[key] = value.strip()
        _normalize_optional_string_list(entity, "aliases", f"upsert_entities[{index}].aliases", normalized_entity)
        for key in ("public", "gm", "presentation"):
            _normalize_optional_object(entity, key, f"upsert_entities[{index}].{key}", normalized_entity)
        if "visibility" in entity:
            if entity["visibility"] not in {"public", "gm"}:
                raise WorldSimError("Entity visibility must be public or gm.")
            normalized_entity["visibility"] = entity["visibility"]
        if "active" in entity:
            if not isinstance(entity["active"], bool):
                raise WorldSimError(f"upsert_entities[{index}].active must be a boolean.")
            normalized_entity["active"] = entity["active"]
        normalized_entities.append(normalized_entity)
    relations = payload.get("upsert_relations", [])
    if not isinstance(relations, list):
        raise WorldSimError("upsert_relations must be an array.")
    normalized_relations = []
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise WorldSimError(f"upsert_relations[{index}] must be an object.")
        normalized_relation: dict[str, Any] = {"id": _require_id(relation.get("id"), f"upsert_relations[{index}].id")}
        for key in ("source_id", "target_id"):
            if key in relation:
                normalized_relation[key] = _require_id(relation[key], f"upsert_relations[{index}].{key}")
        if "predicate" in relation:
            predicate = relation["predicate"]
            if not isinstance(predicate, str) or not predicate.strip():
                raise WorldSimError(f"upsert_relations[{index}].predicate must be a non-empty string.")
            normalized_relation["predicate"] = predicate.strip()
        for key in ("public", "gm", "presentation"):
            _normalize_optional_object(relation, key, f"upsert_relations[{index}].{key}", normalized_relation)
        if "visibility" in relation:
            if relation["visibility"] not in {"public", "gm"}:
                raise WorldSimError("Relation visibility must be public or gm.")
            normalized_relation["visibility"] = relation["visibility"]
        if "active" in relation:
            if not isinstance(relation["active"], bool):
                raise WorldSimError(f"upsert_relations[{index}].active must be a boolean.")
            normalized_relation["active"] = relation["active"]
        normalized_relations.append(normalized_relation)
    retire_relations = _require_string_list(payload.get("retire_relations"), "retire_relations")
    for relation_id in retire_relations:
        _require_id(relation_id, "retire_relations item")
    events = payload.get("events", [])
    if not isinstance(events, list):
        raise WorldSimError("events must be an array.")
    normalized_events = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise WorldSimError(f"events[{index}] must be an object.")
        normalized_events.append(
            {
                "entity_ids": [
                    _require_id(item, f"events[{index}].entity_ids item")
                    for item in _require_string_list(event.get("entity_ids"), f"events[{index}].entity_ids")
                ],
                "public_summary": str(event.get("public_summary", "")).strip(),
                "gm_summary": str(event.get("gm_summary", "")).strip(),
                "data": _require_object(event.get("data"), f"events[{index}].data"),
            }
        )
    return {
        "turn_id": turn_id,
        "response": normalized_response,
        "session": normalized_session,
        "upsert_entities": normalized_entities,
        "upsert_relations": normalized_relations,
        "retire_relations": retire_relations,
        "events": normalized_events,
    }


ENTITY_CREATE_FIELDS = {
    "kind",
    "name",
    "aliases",
    "public",
    "gm",
    "presentation",
    "visibility",
    "active",
}
RELATION_CREATE_FIELDS = {
    "source_id",
    "predicate",
    "target_id",
    "public",
    "gm",
    "presentation",
    "visibility",
    "active",
}


def _require_create_fields(patch: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - patch.keys())
    if missing:
        raise WorldSimError(f"New {label} requires: {', '.join(missing)}.")


def _apply_entity_patch(row: sqlite3.Row | None, patch: dict[str, Any]) -> dict[str, Any]:
    if row is None:
        _require_create_fields(patch, ENTITY_CREATE_FIELDS, f"entity {patch['id']}")
        entity: dict[str, Any] = {"id": patch["id"]}
    else:
        entity = _row_entity(row, include_gm=True)
    for key in ("kind", "name", "aliases", "visibility", "active"):
        if key in patch:
            entity[key] = patch[key]
    for key in ("public", "gm", "presentation"):
        if key in patch:
            entity[key] = _merge_patch(entity.get(key), patch[key])
    return entity


def _apply_relation_patch(row: sqlite3.Row | None, patch: dict[str, Any]) -> dict[str, Any]:
    if row is None:
        _require_create_fields(patch, RELATION_CREATE_FIELDS, f"relation {patch['id']}")
        relation: dict[str, Any] = {"id": patch["id"]}
    else:
        relation = _row_relation(row, include_gm=True)
    for key in ("source_id", "predicate", "target_id", "visibility", "active"):
        if key in patch:
            relation[key] = patch[key]
    for key in ("public", "gm", "presentation"):
        if key in patch:
            relation[key] = _merge_patch(relation.get(key), patch[key])
    return relation


def commit_bundle(session_path: pathlib.Path, payload: Any) -> dict[str, Any]:
    bundle = normalize_bundle(session_path, payload)
    canonical = json_dump(bundle)
    turn_id = bundle["turn_id"]
    connection = connect(session_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        turn = connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
        if turn is None:
            raise WorldSimError(f"Turn not found: {turn_id}")
        if turn["status"] == "complete":
            if turn["bundle_json"] == canonical:
                connection.rollback()
                return {"turn_id": turn_id, "status": "complete", "idempotent": True}
            raise WorldSimError(f"Turn {turn_id} is already complete with different content.")
        if turn["status"] not in {"pending", "processing"}:
            raise WorldSimError(f"Turn {turn_id} cannot be committed from status {turn['status']}.")
        entity_records = []
        for patch in bundle["upsert_entities"]:
            row = connection.execute("SELECT * FROM entities WHERE id=?", (patch["id"],)).fetchone()
            entity_records.append(_apply_entity_patch(row, patch))
        relation_records = []
        for patch in bundle["upsert_relations"]:
            row = connection.execute("SELECT * FROM relations WHERE id=?", (patch["id"],)).fetchone()
            relation_records.append(_apply_relation_patch(row, patch))
        existing_ids = {row[0] for row in connection.execute("SELECT id FROM entities")}
        incoming_ids = {entity["id"] for entity in entity_records}
        known_ids = existing_ids | incoming_ids
        for relation in relation_records:
            if relation["source_id"] not in known_ids or relation["target_id"] not in known_ids:
                raise WorldSimError(f"Relation {relation['id']} references an unknown entity.")
        for event in bundle["events"]:
            if any(entity_id not in known_ids for entity_id in event["entity_ids"]):
                raise WorldSimError("An event references an unknown entity.")
        for entity in entity_records:
            connection.execute(
                """
                INSERT INTO entities(
                    id, kind, name, aliases_json, public_json, gm_json,
                    presentation_json, visibility, active, created_turn, updated_turn
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    name=excluded.name,
                    aliases_json=excluded.aliases_json,
                    public_json=excluded.public_json,
                    gm_json=excluded.gm_json,
                    presentation_json=excluded.presentation_json,
                    visibility=excluded.visibility,
                    active=excluded.active,
                    updated_turn=excluded.updated_turn
                """,
                (
                    entity["id"],
                    entity["kind"],
                    entity["name"],
                    json_dump(entity["aliases"]),
                    json_dump(entity["public"]),
                    json_dump(entity["gm"]),
                    json_dump(entity["presentation"]),
                    entity["visibility"],
                    int(entity["active"]),
                    turn_id,
                    turn_id,
                ),
            )
        for relation in relation_records:
            connection.execute(
                """
                INSERT INTO relations(
                    id, source_id, predicate, target_id, public_json, gm_json,
                    presentation_json, visibility, active, created_turn, updated_turn
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_id=excluded.source_id,
                    predicate=excluded.predicate,
                    target_id=excluded.target_id,
                    public_json=excluded.public_json,
                    gm_json=excluded.gm_json,
                    presentation_json=excluded.presentation_json,
                    visibility=excluded.visibility,
                    active=excluded.active,
                    updated_turn=excluded.updated_turn
                """,
                (
                    relation["id"],
                    relation["source_id"],
                    relation["predicate"],
                    relation["target_id"],
                    json_dump(relation["public"]),
                    json_dump(relation["gm"]),
                    json_dump(relation["presentation"]),
                    relation["visibility"],
                    int(relation["active"]),
                    turn_id,
                    turn_id,
                ),
            )
        for relation_id in bundle["retire_relations"]:
            connection.execute(
                "UPDATE relations SET active=0, updated_turn=? WHERE id=?",
                (turn_id, relation_id),
            )
        for event in bundle["events"]:
            connection.execute(
                "INSERT INTO events(turn_id, entity_ids_json, public_summary, gm_summary, data_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    json_dump(event["entity_ids"]),
                    event["public_summary"],
                    event["gm_summary"],
                    json_dump(event["data"]),
                    utc_now(),
                ),
            )
        meta = read_meta(connection)
        for key, value in bundle["session"].items():
            if key in {"player_id", "scene_id"} and value not in known_ids:
                raise WorldSimError(f"session.{key} references an unknown entity.")
            if key in {"narration", "presentation"}:
                current = json_load(meta.get(key), {})
                set_meta(connection, key, json_dump(_merge_patch(current, value)))
            else:
                set_meta(connection, key, value)
        response = bundle["response"]
        connection.execute(
            """
            UPDATE turns
            SET status='complete', response_markdown=?, response_json=?, bundle_json=?, error=NULL, completed_at=?
            WHERE id=?
            """,
            (response["markdown"], json_dump(response), canonical, utc_now(), turn_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "turn_id": turn_id,
        "status": "complete",
        "idempotent": False,
        "session": session_status(session_path),
    }


def inspect_world(session_path: pathlib.Path, query: str = "") -> dict[str, Any]:
    lowered = query.strip().lower()
    with connect(session_path) as connection:
        meta = read_meta(connection)
        entity_rows = connection.execute("SELECT * FROM entities ORDER BY kind, name").fetchall()
        entities = [_row_entity(row, include_gm=True) for row in entity_rows]
        if lowered:
            entities = [entity for entity in entities if lowered in _entity_search_text(entity)]
        selected = {entity["id"] for entity in entities}
        relation_rows = connection.execute("SELECT * FROM relations ORDER BY predicate, id").fetchall()
        relations = [
            _row_relation(row, include_gm=True)
            for row in relation_rows
            if not lowered
            or row["source_id"] in selected
            or row["target_id"] in selected
            or lowered
            in (
                f"{row['id']} {row['source_id']} {row['predicate']} {row['target_id']} "
                f"{row['public_json']} {row['gm_json']} {row['presentation_json']}"
            ).lower()
        ]
        event_rows = connection.execute("SELECT * FROM events ORDER BY id").fetchall()
        events = [
            {
                "id": row["id"],
                "turn_id": row["turn_id"],
                "entity_ids": json_load(row["entity_ids_json"], []),
                "public_summary": row["public_summary"],
                "gm_summary": row["gm_summary"],
                "data": json_load(row["data_json"], {}),
            }
            for row in event_rows
            if not lowered
            or lowered
            in (
                f"{row['id']} {row['turn_id']} {row['entity_ids_json']} "
                f"{row['public_summary']} {row['gm_summary']} {row['data_json']}"
            ).lower()
        ]
        turn_rows = connection.execute("SELECT * FROM turns ORDER BY id").fetchall()
        turns = [
            _turn_payload(row)
            for row in turn_rows
            if not lowered
            or lowered
            in (
                f"{row['id']} {row['kind']} {row['user_text']} {row['response_markdown'] or ''} {row['error'] or ''}"
            ).lower()
        ]
    return {
        "session": _session_payload(meta),
        "query": query,
        "entities": entities,
        "relations": relations,
        "events": events,
        "turns": turns,
    }
