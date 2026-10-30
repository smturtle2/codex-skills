#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read subtitle evidence and publish the agent's edited SRT or WebVTT cues."""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import tempfile


class SubtitleError(ValueError):
    pass


TIMESTAMPS = {
    "srt": r"\d+:[0-5]\d:[0-5]\d[,.]\d{3}",
    "vtt": r"(?:\d{2,}:)?[0-5]\d:[0-5]\d\.\d{3}",
}


def timestamp_ms(value: str) -> int:
    fields = value.replace(",", ".").split(":")
    seconds, milliseconds = fields[-1].split(".")
    hours = int(fields[0]) if len(fields) == 3 else 0
    return ((hours * 60 + int(fields[-2])) * 60 + int(seconds)) * 1000 + int(milliseconds)


def timestamp_text(value: int, format_: str) -> str:
    seconds, milliseconds = divmod(value, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    separator = "," if format_ == "srt" else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def subtitle_format(path: Path) -> str:
    format_ = path.suffix.lower().removeprefix(".")
    if format_ not in TIMESTAMPS:
        raise SubtitleError("Use an .srt or .vtt subtitle file")
    return format_


def parse_payload(text: str, format_: str, *, allow_empty: bool = False) -> tuple[list[dict], list[str]]:
    text = text.removeprefix("\ufeff")
    if "\x00" in text:
        raise SubtitleError("Subtitle contains NUL characters; check its encoding")
    blocks = [block for block in re.split(r"\n(?:[ \t]*\n)+", text.strip("\n")) if block.strip()]
    metadata = []
    if format_ == "vtt":
        if not blocks or not re.fullmatch(r"WEBVTT(?:[ \t][^\n]*)?", blocks[0].split("\n")[0]):
            raise SubtitleError("WebVTT must start with a WEBVTT header and a blank line before cues")
        header = blocks.pop(0)
        if "-->" in header:
            raise SubtitleError("WebVTT header must be separated from cues by a blank line")
        metadata.append(header)
    stamp = TIMESTAMPS[format_]
    timing = re.compile(rf"(?P<start>{stamp})[ \t]+-->[ \t]+(?P<end>{stamp})(?:[ \t]+(?P<settings>[^\n]*))?")
    cues = []
    for number, block in enumerate(blocks, 1):
        lines = block.split("\n")
        first = lines[0]
        comment = first == "NOTE" or first.startswith(("NOTE ", "NOTE\t"))
        declaration = first in {"STYLE", "REGION"} and (len(lines) < 2 or timing.fullmatch(lines[1]) is None)
        if format_ == "vtt" and (comment or declaration):
            metadata.append(block)
            continue
        match = timing.fullmatch(first)
        identifier = None
        payload = lines[1:]
        if match is None and len(lines) > 1 and "-->" not in first:
            match = timing.fullmatch(lines[1])
            identifier = first
            payload = lines[2:]
        if match is None:
            raise SubtitleError(f"Invalid timing in subtitle block {number}: {first!r}")
        if any(timing.fullmatch(line) for line in payload):
            raise SubtitleError(f"Another timing line occurs inside block {number}; check cue separators")
        cue = {"id": f"s{len(cues) + 1}", "start_ms": timestamp_ms(match["start"]),
               "end_ms": timestamp_ms(match["end"]), "text": "\n".join(payload)}
        if identifier is not None:
            cue["identifier"] = identifier
        if match["settings"]:
            cue["settings"] = match["settings"]
        cues.append(cue)
    if not cues and not allow_empty:
        raise SubtitleError("No subtitle cues found")
    return cues, metadata


def parse_subtitles(path: Path, encoding: str = "utf-8-sig", *, allow_empty: bool = False) -> dict:
    format_ = subtitle_format(path)
    cues, metadata = parse_payload(path.read_text(encoding=encoding), format_, allow_empty=allow_empty)
    return {"version": 1, "source": {"path": str(path.resolve()), "format": format_, "encoding": encoding},
            "cues": cues, "metadata": metadata}


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise SubtitleError(f"Expected a JSON object in {path}")
    return value


def write_atomic(path: Path, text: str, *, overwrite: bool = False) -> None:
    """Publish a finished sibling file, with exclusive creation unless replacement is requested."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if overwrite:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise SubtitleError(f"Destination exists: {path}; choose another path or authorize --overwrite") from exc
    finally:
        temporary.unlink(missing_ok=True)


def source_warnings(source: dict) -> list[str]:
    warnings = []
    last_start = -1
    for cue in source["cues"]:
        if cue["end_ms"] <= cue["start_ms"]:
            warnings.append(f"Source {cue['id']} has a non-positive duration")
        if not cue["text"].strip():
            warnings.append(f"Source {cue['id']} has empty text")
        if cue["start_ms"] < last_start:
            warnings.append(f"Source {cue['id']} starts before the preceding source cue")
        last_start = cue["start_ms"]
    if any("X-TIMESTAMP-MAP" in block for block in source.get("metadata", [])):
        warnings.append("Source contains WebVTT timestamp mapping; establish its relation to the media clock")
    return warnings


def inspect(input_: Path, workdir: Path | None, encoding: str) -> dict:
    source = parse_subtitles(input_, encoding)
    if workdir is None:
        return {**source, "warnings": source_warnings(source)}
    if workdir.exists() and (not workdir.is_dir() or any(workdir.iterdir())):
        raise SubtitleError("workdir is not empty; resume its source.json and work.json in place")
    workdir.mkdir(parents=True, exist_ok=True)
    work = {"version": 1, "target_language": "", "groups": [], "omitted": [], "pending": [], "notes": []}
    for filename, data in (("source.json", source), ("work.json", work)):
        write_atomic(workdir / filename, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return {"source_path": str((workdir / "source.json").resolve()),
            "work_path": str((workdir / "work.json").resolve()), "cue_count": len(source["cues"]),
            "last_source_end_ms": max(cue["end_ms"] for cue in source["cues"]),
            "warnings": source_warnings(source)}


def integer(value) -> bool:
    return type(value) is int


def load_source(workdir: Path) -> dict:
    source = read_json(workdir / "source.json")
    info = source.get("source")
    cues = source.get("cues")
    if type(source.get("version")) is not int or source["version"] != 1 or not isinstance(info, dict):
        raise SubtitleError("Invalid source.json version or source metadata")
    if not isinstance(info.get("path"), str) or not Path(info["path"]).is_absolute() or info.get("format") not in TIMESTAMPS:
        raise SubtitleError("Invalid source.json source path or format")
    if not isinstance(cues, list) or not cues:
        raise SubtitleError("source.json must contain source cues")
    seen = set()
    for cue in cues:
        if not isinstance(cue, dict) or not isinstance(cue.get("id"), str) or not cue["id"] or cue["id"] in seen:
            raise SubtitleError("source.json has missing or duplicate cue IDs")
        if not all(integer(cue.get(key)) and cue[key] >= 0 for key in ("start_ms", "end_ms")) or not isinstance(cue.get("text"), str):
            raise SubtitleError(f"Invalid source cue: {cue['id']}")
        seen.add(cue["id"])
    return source


def check_work(source: dict, work: dict, media_duration: int | None = None) -> tuple[dict, list[dict]]:
    errors, warnings, blockers = [], [], []
    source_ids = {cue["id"] for cue in source["cues"]}
    assigned = {}
    output = []

    def records(key: str) -> list:
        value = work.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")
            return []
        return value

    def references(record: dict, label: str, *, assign: bool) -> list[str]:
        refs = record.get("source_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{label}.source_ids must be a nonempty list")
            return []
        local = set()
        for ref in refs:
            if not isinstance(ref, str) or ref not in source_ids:
                errors.append(f"{label} refers to unknown source ID {ref!r}")
                continue
            if ref in local:
                errors.append(f"{label} repeats source ID {ref}")
            local.add(ref)
            if assign:
                if ref in assigned:
                    errors.append(f"{ref} is assigned in both {assigned[ref]} and {label}")
                else:
                    assigned[ref] = label
        return list(local)

    if type(work.get("version")) is not int or work["version"] != 1:
        errors.append("work.json version must be 1")
    language = work.get("target_language")
    if not isinstance(language, str):
        errors.append("target_language must be a string")
    elif not language.strip():
        blockers.append("Set target_language")
    for index, group in enumerate(records("groups"), 1):
        label = f"groups[{index}]"
        if not isinstance(group, dict):
            errors.append(f"{label} must be an object")
            continue
        references(group, label, assign=True)
        cues = group.get("cues")
        if not isinstance(cues, list) or not cues:
            errors.append(f"{label}.cues must be a nonempty list; record removed sources in omitted")
            continue
        for cue_index, cue in enumerate(cues, 1):
            location = f"{label}.cues[{cue_index}]"
            if not isinstance(cue, dict):
                errors.append(f"{location} must be an object")
                continue
            start, end, text = cue.get("start_ms"), cue.get("end_ms"), cue.get("text")
            if not integer(start) or not integer(end) or start < 0 or end <= start:
                errors.append(f"{location} requires integer times with 0 <= start_ms < end_ms")
                continue
            if not isinstance(text, str) or not text.strip() or "\r" in text or "\x00" in text or any(not line.strip() for line in text.split("\n")):
                errors.append(f"{location}.text must contain nonempty lines separated by LF")
                continue
            if media_duration is not None and end > media_duration:
                errors.append(f"{location} ends beyond the supplied media duration")
            output.append({"start_ms": start, "end_ms": end, "text": text})
    omitted = records("omitted")
    for index, record in enumerate(omitted, 1):
        label = f"omitted[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        references(record, label, assign=True)
        if not isinstance(record.get("reason"), str) or not record["reason"].strip():
            errors.append(f"{label}.reason must explain the omission")
    pending = records("pending")
    for index, record in enumerate(pending, 1):
        label = f"pending[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        references(record, label, assign=False)
        if not isinstance(record.get("reason"), str) or not record["reason"].strip():
            errors.append(f"{label}.reason must explain what remains unresolved")
        if "start_ms" in record or "end_ms" in record:
            start, end = record.get("start_ms"), record.get("end_ms")
            if not integer(start) or not integer(end) or start < 0 or end <= start:
                errors.append(f"{label} requires integer times with 0 <= start_ms < end_ms")
    if any(not isinstance(note, str) or not note.strip() for note in records("notes")):
        errors.append("notes must contain nonempty strings")
    unprocessed = [cue["id"] for cue in source["cues"] if cue["id"] not in assigned]
    if unprocessed:
        blockers.append(f"{len(unprocessed)} source cues remain unprocessed")
    if pending:
        blockers.append(f"{len(pending)} pending items remain")
    cue_metrics, overlaps = [], []
    active_end, active_index, last_start = -1, 0, -1
    for index, cue in enumerate(output, 1):
        start, end, text = cue["start_ms"], cue["end_ms"], cue["text"]
        if start < last_start:
            errors.append(f"Output cue {index} starts before the preceding output cue; arrange groups and cues in display order")
        if start < active_end:
            overlaps.append({"earlier_cue": active_index, "cue": index, "overlap_ms": min(end, active_end) - start})
        if end > active_end:
            active_end, active_index = end, index
        last_start = start
        characters = len(text.replace("\n", ""))
        cue_metrics.append({"cue": index, "duration_ms": end - start, "characters": characters,
                            "line_lengths": [len(line) for line in text.split("\n")],
                            "characters_per_second": round(characters * 1000 / (end - start), 2)})
    if overlaps:
        warnings.append(f"{len(overlaps)} output cues overlap an earlier cue; review the intended dialogue timing")
    complete = not blockers and not errors
    report = {"valid": not errors, "complete": complete, "export_ready": not errors and complete,
              "errors": errors, "blockers": blockers, "warnings": warnings, "unprocessed_ids": unprocessed,
              "metrics": {"source_cues": len(source["cues"]), "assigned_source_cues": len(assigned),
                          "output_cues": len(output), "omission_records": len(omitted), "pending_items": len(pending),
                          "overlaps": overlaps, "cues": cue_metrics}}
    return report, output


def render_subtitles(cues: list[dict], format_: str) -> str:
    blocks = ["WEBVTT"] if format_ == "vtt" else []
    for index, cue in enumerate(cues, 1):
        timing = f"{timestamp_text(cue['start_ms'], format_)} --> {timestamp_text(cue['end_ms'], format_)}"
        blocks.append((f"{index}\n" if format_ == "srt" else "") + timing + "\n" + escape(cue["text"], quote=False))
    return "\n\n".join(blocks) + ("\n\n" if blocks else "")


def payload_matches(actual: list[dict], cues: list[dict]) -> bool:
    actual = [{key: cue[key] for key in ("start_ms", "end_ms", "text")} for cue in actual]
    expected = [{**cue, "text": escape(cue["text"], quote=False)} for cue in cues]
    return actual == expected


def inspect_publication(output: Path, cues: list[dict], report: dict) -> None:
    published = parse_subtitles(output, allow_empty=True)
    matches = payload_matches(published["cues"], cues)
    report["publication_matches"] = matches
    report["output_path"] = str(output.resolve())
    if not matches:
        report["errors"].append("Published cue text or times differ from current work.json")
        report["valid"] = report["export_ready"] = False


def export(workdir: Path, output: Path, source: dict, cues: list[dict], report: dict, overwrite: bool) -> dict:
    if not report["export_ready"]:
        return report
    protected = [Path(source["source"]["path"]), workdir / "source.json", workdir / "work.json"]
    for path in protected:
        if output.resolve() == path.resolve() or (output.exists() and path.exists() and output.samefile(path)):
            raise SubtitleError(f"Output must be distinct from source and working data: {path}")
    format_ = subtitle_format(output)
    rendered = render_subtitles(cues, format_)
    parsed, _ = parse_payload(rendered, format_, allow_empty=True)
    if not payload_matches(parsed, cues):
        raise SubtitleError("Serialized cue text or times differ from work.json; output was not changed")
    write_atomic(output, rendered, overwrite=overwrite)
    inspect_publication(output, cues, report)
    return {**report, "saved_path": str(output.resolve()), "format": format_}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="Read SRT/WebVTT; optionally prepare a new empty workspace")
    inspect_parser.add_argument("--input", type=Path, required=True)
    inspect_parser.add_argument("--encoding", default="utf-8-sig")
    inspect_parser.add_argument("--workdir", type=Path)
    for name in ("check", "export"):
        command = commands.add_parser(name, help="Check current work and optional published output" if name == "check" else "Publish complete work as SRT/WebVTT")
        command.add_argument("--workdir", type=Path, required=True)
        command.add_argument("--output", type=Path, required=name == "export")
        command.add_argument("--media-duration-ms", type=int)
        if name == "export":
            command.add_argument("--overwrite", action="store_true", help="Replace an explicitly authorized output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect(args.input.expanduser(), args.workdir.expanduser() if args.workdir else None, args.encoding)
        else:
            if args.media_duration_ms is not None and args.media_duration_ms < 0:
                raise SubtitleError("--media-duration-ms must be nonnegative")
            workdir = args.workdir.expanduser().resolve()
            source = load_source(workdir)
            report, cues = check_work(source, read_json(workdir / "work.json"), args.media_duration_ms)
            if args.command == "export":
                result = export(workdir, args.output.expanduser(), source, cues, report, args.overwrite)
            else:
                if args.output is not None:
                    inspect_publication(args.output.expanduser(), cues, report)
                result = report
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("export_ready", True) else 1
    except (ValueError, OSError, UnicodeError, LookupError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
