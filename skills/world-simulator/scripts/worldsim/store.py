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
    return connection


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
            "schema_version": "1",
            "session_id": session_path.name,
            "display_name": "Untitled World",
            "mode": "studio",
            "language": "ko",
            "player_id": "",
            "scene_id": "",
            "created_at": utc_now(),
        }
        connection.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", initial.items())
    return session_status(session_path)


def read_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM meta")}


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


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
    return {"session_id": session_path.name, "session_path": str(session_path.resolve()), "meta": meta, **counts}


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
    return {"turn_id": turn_id, "kind": resolved_kind, "user_text": cleaned, "status": "pending"}


def _row_entity(row: sqlite3.Row, include_gm: bool) -> dict[str, Any]:
    entity = {
        "id": row["id"],
        "kind": row["kind"],
        "name": row["name"],
        "aliases": json_load(row["aliases_json"], []),
        "public": json_load(row["public_json"], {}),
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
                "SELECT * FROM turns WHERE id > ? ORDER BY id ASC LIMIT ?", (after, safe_limit)
            ).fetchall()
            has_more = bool(rows) and connection.execute(
                "SELECT 1 FROM turns WHERE id > ? LIMIT 1", (rows[-1]["id"],)
            ).fetchone() is not None
        else:
            boundary = before if before is not None else 2**63 - 1
            rows = connection.execute(
                "SELECT * FROM turns WHERE id < ? ORDER BY id DESC LIMIT ?", (boundary, safe_limit)
            ).fetchall()
            rows = list(reversed(rows))
            has_more = bool(rows) and connection.execute(
                "SELECT 1 FROM turns WHERE id < ? LIMIT 1", (rows[0]["id"],)
            ).fetchone() is not None
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
    return {
        "session_id": session_path.name,
        "display_name": meta.get("display_name", "Untitled World"),
        "mode": meta.get("mode", "studio"),
        "language": meta.get("language", "ko"),
        "player_id": meta.get("player_id", ""),
        "scene_id": meta.get("scene_id", ""),
        "entities": [_row_entity(row, include_gm=studio) for row in entity_rows],
        "relations": [_row_relation(row, include_gm=studio) for row in relation_rows],
        "latest_response": json_load(latest["response_json"], None) if latest else None,
        "processing": outstanding["id"] if outstanding else None,
        "can_begin": studio and completed_studio > 0 and bool(entity_rows),
    }


def _entity_search_text(entity: dict[str, Any]) -> str:
    return " ".join(
        [
            entity["name"],
            *entity.get("aliases", []),
            json.dumps(entity.get("public", {}), ensure_ascii=False),
            json.dumps(entity.get("gm", {}), ensure_ascii=False),
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
    all_rows = connection.execute("SELECT * FROM entities WHERE active=1 ORDER BY updated_turn DESC, id").fetchall()
    all_entities = [_row_entity(row, include_gm=True) for row in all_rows]
    by_id = {entity["id"]: entity for entity in all_entities}
    selected_ids: set[str] = set()
    for key in ("player_id", "scene_id"):
        if meta.get(key) in by_id:
            selected_ids.add(meta[key])
    lowered_input = turn["user_text"].lower()
    for entity in all_entities:
        names = [entity["name"], *entity.get("aliases", [])]
        if any(name and name.lower() in lowered_input for name in names):
            selected_ids.add(entity["id"])
        gm = entity.get("gm", {})
        if isinstance(gm, dict) and isinstance(gm.get("next_due"), int) and gm["next_due"] <= turn_id:
            selected_ids.add(entity["id"])
        if entity["kind"] in {"rule", "thread", "quest", "threat"}:
            selected_ids.add(entity["id"])
    relation_rows = connection.execute("SELECT * FROM relations WHERE active=1 ORDER BY updated_turn DESC").fetchall()
    relations = [_row_relation(row, include_gm=True) for row in relation_rows]
    relevant_relations: list[dict[str, Any]] = []
    for relation in relations:
        if relation["source_id"] in selected_ids or relation["target_id"] in selected_ids:
            relevant_relations.append(relation)
            selected_ids.add(relation["source_id"])
            selected_ids.add(relation["target_id"])
    recent_turn_rows = connection.execute(
        "SELECT * FROM turns WHERE status='complete' AND id < ? ORDER BY id DESC LIMIT 8", (turn_id,)
    ).fetchall()
    recent_events = connection.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT 16"
    ).fetchall()
    return {
        "session": {
            "session_id": meta.get("session_id", ""),
            "display_name": meta.get("display_name", "Untitled World"),
            "mode": meta.get("mode", "studio"),
            "language": meta.get("language", "ko"),
            "player_id": meta.get("player_id", ""),
            "scene_id": meta.get("scene_id", ""),
        },
        "turn": _turn_payload(turn),
        "entities": [by_id[entity_id] for entity_id in sorted(selected_ids) if entity_id in by_id],
        "relations": relevant_relations,
        "recent_turns": [_turn_payload(row) for row in reversed(recent_turn_rows)],
        "recent_events": [
            {
                "id": row["id"],
                "turn_id": row["turn_id"],
                "entity_ids": json_load(row["entity_ids_json"], []),
                "public_summary": row["public_summary"],
                "gm_summary": row["gm_summary"],
                "data": json_load(row["data_json"], {}),
            }
            for row in reversed(recent_events)
        ],
        "available_entity_count": len(all_entities),
        "inspect_hint": "Use the inspect command when the turn depends on an entity not included here.",
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
    visuals = response.get("visuals", [])
    if not isinstance(visuals, list) or any(not isinstance(item, dict) for item in visuals):
        raise WorldSimError("response.visuals must be an array of objects.")
    normalized_visuals = []
    for index, visual in enumerate(visuals):
        asset_path = visual.get("asset_path")
        if not isinstance(asset_path, str):
            raise WorldSimError(f"response.visuals[{index}].asset_path is required.")
        normalized_visuals.append({**visual, "asset_path": _safe_asset_reference(session_path, asset_path)})
    normalized_response = {
        "markdown": markdown.strip(),
        "scene_label": str(response.get("scene_label", "")).strip(),
        "status": status,
        "visuals": normalized_visuals,
    }
    session_patch = _require_object(payload.get("session"), "session")
    normalized_session: dict[str, str] = {}
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
    entities = payload.get("upsert_entities", [])
    if not isinstance(entities, list):
        raise WorldSimError("upsert_entities must be an array.")
    normalized_entities = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise WorldSimError(f"upsert_entities[{index}] must be an object.")
        entity_id = _require_id(entity.get("id"), f"upsert_entities[{index}].id")
        kind = entity.get("kind")
        name = entity.get("name")
        if not isinstance(kind, str) or not kind.strip() or not isinstance(name, str) or not name.strip():
            raise WorldSimError(f"upsert_entities[{index}] requires kind and name.")
        normalized_entities.append(
            {
                "id": entity_id,
                "kind": kind.strip(),
                "name": name.strip(),
                "aliases": _require_string_list(entity.get("aliases"), f"upsert_entities[{index}].aliases"),
                "public": _require_object(entity.get("public"), f"upsert_entities[{index}].public"),
                "gm": _require_object(entity.get("gm"), f"upsert_entities[{index}].gm"),
                "visibility": entity.get("visibility", "public"),
                "active": bool(entity.get("active", True)),
            }
        )
        if normalized_entities[-1]["visibility"] not in {"public", "gm"}:
            raise WorldSimError("Entity visibility must be public or gm.")
    relations = payload.get("upsert_relations", [])
    if not isinstance(relations, list):
        raise WorldSimError("upsert_relations must be an array.")
    normalized_relations = []
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise WorldSimError(f"upsert_relations[{index}] must be an object.")
        predicate = relation.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            raise WorldSimError(f"upsert_relations[{index}].predicate is required.")
        visibility = relation.get("visibility", "public")
        if visibility not in {"public", "gm"}:
            raise WorldSimError("Relation visibility must be public or gm.")
        normalized_relations.append(
            {
                "id": _require_id(relation.get("id"), f"upsert_relations[{index}].id"),
                "source_id": _require_id(relation.get("source_id"), f"upsert_relations[{index}].source_id"),
                "predicate": predicate.strip(),
                "target_id": _require_id(relation.get("target_id"), f"upsert_relations[{index}].target_id"),
                "public": _require_object(relation.get("public"), f"upsert_relations[{index}].public"),
                "gm": _require_object(relation.get("gm"), f"upsert_relations[{index}].gm"),
                "visibility": visibility,
                "active": bool(relation.get("active", True)),
            }
        )
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
                "entity_ids": [_require_id(item, f"events[{index}].entity_ids item") for item in _require_string_list(event.get("entity_ids"), f"events[{index}].entity_ids")],
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
        existing_ids = {row[0] for row in connection.execute("SELECT id FROM entities")}
        incoming_ids = {entity["id"] for entity in bundle["upsert_entities"]}
        known_ids = existing_ids | incoming_ids
        for relation in bundle["upsert_relations"]:
            if relation["source_id"] not in known_ids or relation["target_id"] not in known_ids:
                raise WorldSimError(f"Relation {relation['id']} references an unknown entity.")
        for event in bundle["events"]:
            if any(entity_id not in known_ids for entity_id in event["entity_ids"]):
                raise WorldSimError("An event references an unknown entity.")
        for entity in bundle["upsert_entities"]:
            connection.execute(
                """
                INSERT INTO entities(id, kind, name, aliases_json, public_json, gm_json, visibility, active, created_turn, updated_turn)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    name=excluded.name,
                    aliases_json=excluded.aliases_json,
                    public_json=excluded.public_json,
                    gm_json=excluded.gm_json,
                    visibility=excluded.visibility,
                    active=excluded.active,
                    updated_turn=excluded.updated_turn
                """,
                (
                    entity["id"], entity["kind"], entity["name"], json_dump(entity["aliases"]),
                    json_dump(entity["public"]), json_dump(entity["gm"]), entity["visibility"],
                    int(entity["active"]), turn_id, turn_id,
                ),
            )
        for relation in bundle["upsert_relations"]:
            connection.execute(
                """
                INSERT INTO relations(id, source_id, predicate, target_id, public_json, gm_json, visibility, active, created_turn, updated_turn)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_id=excluded.source_id,
                    predicate=excluded.predicate,
                    target_id=excluded.target_id,
                    public_json=excluded.public_json,
                    gm_json=excluded.gm_json,
                    visibility=excluded.visibility,
                    active=excluded.active,
                    updated_turn=excluded.updated_turn
                """,
                (
                    relation["id"], relation["source_id"], relation["predicate"], relation["target_id"],
                    json_dump(relation["public"]), json_dump(relation["gm"]), relation["visibility"],
                    int(relation["active"]), turn_id, turn_id,
                ),
            )
        for relation_id in bundle["retire_relations"]:
            connection.execute("UPDATE relations SET active=0, updated_turn=? WHERE id=?", (turn_id, relation_id))
        for event in bundle["events"]:
            connection.execute(
                "INSERT INTO events(turn_id, entity_ids_json, public_summary, gm_summary, data_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    turn_id, json_dump(event["entity_ids"]), event["public_summary"], event["gm_summary"],
                    json_dump(event["data"]), utc_now(),
                ),
            )
        for key, value in bundle["session"].items():
            if key in {"player_id", "scene_id"} and value not in known_ids:
                raise WorldSimError(f"session.{key} references an unknown entity.")
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
    return {"turn_id": turn_id, "status": "complete", "idempotent": False, "session": session_status(session_path)}


def inspect_world(session_path: pathlib.Path, query: str = "") -> dict[str, Any]:
    lowered = query.strip().lower()
    with connect(session_path) as connection:
        meta = read_meta(connection)
        entity_rows = connection.execute("SELECT * FROM entities WHERE active=1 ORDER BY kind, name").fetchall()
        entities = [_row_entity(row, include_gm=True) for row in entity_rows]
        if lowered:
            entities = [entity for entity in entities if lowered in _entity_search_text(entity)]
        selected = {entity["id"] for entity in entities}
        relation_rows = connection.execute("SELECT * FROM relations WHERE active=1 ORDER BY predicate, id").fetchall()
        relations = [
            _row_relation(row, include_gm=True)
            for row in relation_rows
            if not lowered
            or row["source_id"] in selected
            or row["target_id"] in selected
            or lowered
            in f"{row['id']} {row['predicate']} {row['public_json']} {row['gm_json']}".lower()
        ]
        events = []
        if lowered:
            event_rows = connection.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50").fetchall()
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
                if lowered in f"{row['public_summary']} {row['gm_summary']} {row['data_json']}".lower()
            ]
    return {"session": meta, "query": query, "entities": entities, "relations": relations, "events": events}
