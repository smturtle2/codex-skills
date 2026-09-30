"""One validated translation/edition state shared by status, build, and validate."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from epub_common import EpubTranslatorError, normalize_spaces, read_json
from reading_flow import legacy_recovery_chunks, marker_parts, ordered_nodes

SEAM_TAIL_CHARS = 240
EDITION_KEYS = {"schema_version", "target_language", "language_tag", "page_progression_direction", "text_direction"}
LANG_RE = re.compile(r"^[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*$")


def read_edition(workdir: Path) -> dict:
    edition = read_json(workdir / "edition.json")
    errors = []
    if type(edition.get("schema_version")) is not int or edition.get("schema_version") not in (1, 2):
        errors.append("schema_version must be 1 or 2")
    if set(edition) - EDITION_KEYS:
        errors.append(f"unknown keys: {sorted(set(edition) - EDITION_KEYS)}")
    for key in ("target_language", "language_tag"):
        value = edition.get(key)
        if not isinstance(value, str) or not LANG_RE.fullmatch(value):
            errors.append(f"{key} must be an explicit nonempty language tag")
    direction = edition.get("page_progression_direction")
    if direction not in ("ltr", "rtl"):
        errors.append("page_progression_direction must be ltr or rtl")
    # Version 1 had no text-direction field. Read it without modifying the file;
    # its explicit page direction is the only persisted direction evidence.
    text_direction = edition.get("text_direction", direction if edition.get("schema_version") == 1 else None)
    if text_direction not in ("ltr", "rtl"):
        errors.append("text_direction must be ltr or rtl")
    if errors:
        raise EpubTranslatorError("edition.json: " + "; ".join(errors))
    return {**edition, "text_direction": text_direction}


def expected_items(flow: dict) -> dict[str, dict]:
    if flow.get("legacy"):
        return {atom["id"]: {"id": atom["id"], "source": atom["source"]} for atom in flow["atoms"]}
    expected = {atom["id"]: {"id": atom["id"], "source": atom["source"]} for atom in flow["atoms"] if atom["kind"] != "text"}
    for node in ordered_nodes(flow):
        unit = node.get("unit")
        if unit and unit.get("id"):
            expected[unit["id"]] = {"id": unit["id"], "source": unit["source"], "markers": unit["markers"]}
    return expected


class TranslationState:
    def __init__(self, workdir: Path, flow: dict) -> None:
        self.errors: list[str] = []
        self.sources: dict[str, dict] = {}
        self.translations: dict[str, str] = {}
        self.chunks: list[dict] = []
        expected = expected_items(flow)
        paths = sorted((workdir / "chunks").glob("chunk-*.json"))
        seen_indices = set()
        for path in paths:
            try:
                chunk = read_json(path)
                index = chunk.get("chunk_index")
                if type(chunk.get("schema_version")) is not int or chunk.get("schema_version") not in (3, 4) or type(index) is not int or index < 0:
                    raise EpubTranslatorError("unsupported chunk schema or index")
                if path.name != f"chunk-{index:04d}.json" or index in seen_indices:
                    raise EpubTranslatorError("chunk filename/index mismatch or duplicate index")
                if chunk.get("kind") not in ("prose", "peripheral") or not isinstance(chunk.get("items"), list):
                    raise EpubTranslatorError("invalid chunk kind/items")
                seen_indices.add(index)
                for item in chunk["items"]:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("source"), str):
                        raise EpubTranslatorError("invalid source item")
                    sid = item["id"]
                    if sid in self.sources:
                        raise EpubTranslatorError(f"duplicate source id {sid}")
                    if sid not in expected:
                        raise EpubTranslatorError(f"source id absent from flow: {sid}")
                    source_equal = normalize_spaces(item["source"]) == normalize_spaces(expected[sid]["source"]) if flow.get("legacy") else item["source"] == expected[sid]["source"]
                    if not source_equal or item.get("markers", {}) != expected[sid].get("markers", {}):
                        raise EpubTranslatorError(f"source/markers differ from flow: {sid}")
                    if item.get("markers"):
                        marker_parts(item["source"], item["markers"])
                    self.sources[sid] = item
                self.chunks.append({**chunk, "path": str(path)})
            except EpubTranslatorError as exc:
                self.errors.append(f"{path.name}: {exc}")
        for chunk in legacy_recovery_chunks(workdir, flow):
            self.chunks.append({**chunk, "virtual": True, "path": str(workdir / "chunks" / f"chunk-{chunk['chunk_index']:04d}.json")})
            for item in chunk["items"]:
                self.sources[item["id"]] = item
        if not paths:
            self.errors.append("source chunks missing")
        absent = set(expected) - set(self.sources)
        if absent:
            self.errors.append(f"flow source IDs missing from chunks: {sorted(absent)[:10]}")
        if not flow.get("legacy"):
            actual_order = [item["id"] for chunk in self.chunks if chunk["kind"] == "prose" for item in chunk["items"]]
            desired_order = [node["unit"]["id"] for node in ordered_nodes(flow) if node.get("unit", {}).get("id")]
            if actual_order != desired_order:
                self.errors.append("prose chunks do not follow reading-flow order")
        self.chunks.sort(key=lambda c: c["chunk_index"])
        chunks_by_name = {Path(chunk["path"]).name: chunk for chunk in self.chunks if not chunk.get("virtual")}
        seen_rows = set()
        for path in sorted((workdir / "translations").glob("*.json")):
            try:
                chunk = chunks_by_name.get(path.name)
                if chunk is None:
                    raise EpubTranslatorError("translation file has no corresponding source chunk")
                data = read_json(path)
                if set(data) - {"schema_version", "chunk_index", "translations"}:
                    raise EpubTranslatorError("unknown translation document fields")
                if type(data.get("schema_version")) is not int or type(data.get("chunk_index")) is not int or data.get("schema_version") != chunk["schema_version"] or data.get("chunk_index") != chunk["chunk_index"]:
                    raise EpubTranslatorError("translation schema/index differs from source chunk")
                if not isinstance(data.get("translations"), list):
                    raise EpubTranslatorError("translations must be a list")
                allowed = {item["id"] for item in chunk["items"]}
                for row in data["translations"]:
                    if not isinstance(row, dict) or set(row) != {"id", "translation"} or not isinstance(row.get("id"), str):
                        self.errors.append(f"{path.name}: malformed translation row")
                        continue
                    sid = row["id"]
                    if sid not in allowed or sid in seen_rows:
                        self.errors.append(f"{path.name}: unknown, misplaced, or duplicate translation id {sid}")
                        continue
                    seen_rows.add(sid)
                    translation = row["translation"]
                    if not isinstance(translation, str) or not translation.strip():
                        self.errors.append(f"{path.name}: empty or non-string translation for {sid}")
                        continue
                    try:
                        if chunk["schema_version"] == 4 and chunk["kind"] == "prose":
                            markers = self.sources[sid].get("markers", {})
                            parts = marker_parts(translation, markers)
                            source_parts = marker_parts(self.sources[sid]["source"], markers)
                            source_prose = "".join(value for kind, value in source_parts if kind == "text").strip()
                            if source_prose and not "".join(value for kind, value in parts if kind == "text").strip():
                                raise EpubTranslatorError("empty translated prose after removing protected markers")
                    except EpubTranslatorError as exc:
                        self.errors.append(f"{path.name}: {sid}: {exc}")
                        continue
                    self.translations[sid] = translation
            except EpubTranslatorError as exc:
                self.errors.append(f"{path.name}: {exc}")
        self.pending = [sid for sid in self.sources if sid not in self.translations]
        self.recovery_required = bool(flow.get("recovery_items") and not flow.get("recovery_recorded"))
        self.legacy = bool(flow.get("legacy"))

    def require_complete(self) -> None:
        if self.recovery_required:
            raise EpubTranslatorError("legacy source contains omitted text: run recover --workdir <run-dir>, then translate the added recovery chunks; existing rows are preserved")
        if self.errors or self.pending:
            details = self.errors[:8] + ([f"missing translations: {self.pending[:10]}"] if self.pending else [])
            raise EpubTranslatorError("invalid/incomplete translation state: " + "; ".join(details))

    def progress(self) -> dict:
        next_chunk = None
        last_finished = None
        seam = ""
        for chunk in self.chunks:
            items = chunk["items"]
            if any(item["id"] not in self.translations for item in items):
                next_chunk = chunk["chunk_index"]
                break
            last_finished = chunk["chunk_index"]
            if chunk["kind"] == "prose" and items:
                seam = " ".join(self.translations[item["id"]] for item in items)[-SEAM_TAIL_CHARS:]
        ready = not self.errors and not self.pending and not self.recovery_required
        return {"ok": not self.errors, "valid": not self.errors, "text_complete": ready, "total_items": len(self.sources), "translated_items": len(self.translations), "remaining": len(self.pending),
                "last_finished_chunk": last_finished, "next_chunk": next_chunk, "seam_tail": seam,
                "errors": self.errors, "legacy_recovery_required": self.recovery_required,
                "legacy_fragment_translations": self.legacy}

    def report(self) -> dict:
        untranslated = []
        by_source: dict[str, set[str]] = defaultdict(set)
        ids: dict[str, list[str]] = defaultdict(list)
        for sid, item in self.sources.items():
            source = item["source"].strip()
            translation = self.translations.get(sid, "").strip()
            if translation == source:
                untranslated.append(sid)
            if translation:
                by_source[source].add(translation)
                ids[source].append(sid)
        divergences = [{"source": source, "translations": sorted(values), "ids": ids[source], "occurrences": len(ids[source])}
                       for source, values in by_source.items() if len(values) > 1]
        return {"ok": not self.errors and not self.pending and not self.recovery_required, "total_items": len(self.sources),
                "missing_translations": self.pending[:200], "missing_count": len(self.pending), "state_errors": self.errors,
                "empty_translations": [sid for sid in self.pending if any(sid in error and "empty" in error for error in self.errors)],
                "untranslated_candidates": untranslated[:200], "untranslated_count": len(untranslated),
                "divergences": divergences[:50], "divergence_count": len(divergences),
                "legacy_fragment_translations": self.legacy, "legacy_recovery_required": self.recovery_required}
