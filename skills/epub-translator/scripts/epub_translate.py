#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=12.0.0"]
# ///
"""EPUB translation CLI; language choices and translations belong to the agent."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from epub_common import EpubTranslatorError, FLOW_SCHEMA_VERSION, TEXT_SCHEMA_VERSION, package_data, read_json, safe_extract, utc_now, write_json
from epub_package import build, prepare_inputs, validate
from epub_resources import export_resources, inspect_epub, record_image
from reading_flow import DEFAULT_MAX_CHARS, DEFAULT_SOFT_MIN, build_flow, read_flow, record_legacy_recovery, source_fingerprint, write_chunks
from translation_state import TranslationState


def ingest(epub: Path, workdir: Path, max_chars: int, soft_min: int) -> dict:
    if not epub.is_file():
        raise EpubTranslatorError(f"EPUB not found: {epub}")
    if workdir.exists() and any(workdir.iterdir()):
        raise EpubTranslatorError("workdir is not empty; use status/recover to resume it or choose a new run directory")
    workdir.mkdir(parents=True, exist_ok=True)
    unpacked = workdir / "unpacked"
    unpacked.mkdir()
    safe_extract(epub, unpacked)
    rootfile, _, items, spine_hrefs = package_data(unpacked)
    flow = build_flow(unpacked, rootfile, spine_hrefs, items)
    write_json(workdir / "flow/book.flow.json", flow)
    chunks = write_chunks(flow, workdir / "chunks", max_chars, soft_min)
    _, images = export_resources(unpacked, rootfile, items, workdir)
    inspected = inspect_epub(epub)
    write_json(workdir / "edition.json", {"schema_version": 2, "target_language": None, "language_tag": None,
                                         "page_progression_direction": "ltr", "text_direction": "ltr"})
    (workdir / "translations").mkdir()
    write_json(workdir / "manifest.json", {"generated_at": utc_now(), "epub": str(epub.resolve()), "rootfile": rootfile,
              "flow_schema_version": FLOW_SCHEMA_VERSION, "text_schema_version": TEXT_SCHEMA_VERSION, "spine_hrefs": spine_hrefs,
              "block_count": len(flow["blocks"]), "slot_count": chunks["total_items"], "chunk_count": len(chunks["chunks"]),
              **chunks, "image_job_count": len(images["jobs"]), "unsupported_image_count": len(images["unsupported"]),
              "unsupported_inline_media_count": flow["stats"]["unsupported_inline_media"], "flow_stats": flow["stats"], "inspect": inspected})
    manifest = read_json(workdir / "manifest.json")
    manifest["source_fingerprint"] = source_fingerprint(unpacked, rootfile, items)
    write_json(workdir / "manifest.json", manifest)
    (workdir / "translation-notes.md").write_text("# Translation notes\n\n## Rolling summary\n\n## Glossary (source → target)\n\n## Style\n", encoding="utf-8")
    return {"ok": True, "manifest": str(workdir / "manifest.json"), "flow": str(workdir / "flow/book.flow.json"),
            "chunks": str(workdir / "chunks"), "edition": str(workdir / "edition.json")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epub_translate.py")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Summarize a source EPUB")
    inspect.add_argument("--epub", required=True)
    inspect.add_argument("--json", action="store_true")
    extract = commands.add_parser("ingest", help="Create a new ordered translation run; never replace an existing run")
    extract.add_argument("--epub", required=True)
    extract.add_argument("--workdir", required=True)
    extract.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    extract.add_argument("--soft-min", type=int, default=DEFAULT_SOFT_MIN)
    for name, help_text in (("status", "Validated progress and contiguous seam"), ("recover", "Explicitly add omitted legacy source items without replacing completed rows")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--workdir", required=True)
    image = commands.add_parser("record-image", help="Resolve one image job with its actual replacement format")
    image.add_argument("--workdir", required=True)
    image.add_argument("--image-id", required=True)
    mode = image.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replacement")
    mode.add_argument("--skip-no-text", action="store_true")
    for name in ("build", "validate"):
        command = commands.add_parser(name, help="Publish only a complete, independently verified EPUB" if name == "build" else "Verify current state and final package bytes")
        command.add_argument("--workdir", required=True)
        command.add_argument("--output", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_epub(Path(args.epub))
            if not args.json:
                print(f"title: {result['title']}\nlanguage: {result['language']}\ncounts: {result['counts']}")
                return 0
        elif args.command == "ingest":
            result = ingest(Path(args.epub), Path(args.workdir), args.max_chars, args.soft_min)
        elif args.command == "status":
            workdir = Path(args.workdir)
            flow = read_flow(workdir)
            state = TranslationState(workdir, flow)
            result = state.progress()
            try:
                prepare_inputs(workdir, flow, state)
                result.update(build_ready=True, build_blockers=[])
            except EpubTranslatorError as exc:
                result.update(build_ready=False, build_blockers=[str(exc)])
        elif args.command == "recover":
            workdir = Path(args.workdir)
            flow = read_flow(workdir)
            if not flow.get("legacy"):
                raise EpubTranslatorError("recover is for flow schema v2 runs; new runs already retain complete mixed content")
            result = {"ok": True, "added_chunks": record_legacy_recovery(workdir, flow), "preserved_existing_rows": True}
        elif args.command == "record-image":
            result = {"ok": True, "job": record_image(Path(args.workdir), args.image_id, Path(args.replacement) if args.replacement else None, args.skip_no_text)}
        elif args.command == "build":
            result = build(Path(args.workdir), Path(args.output))
        else:
            result = validate(Path(args.workdir), Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except (EpubTranslatorError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
