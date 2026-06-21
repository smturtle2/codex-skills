#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


IMAGE_GENERATION_EVENT_TYPES = {
    "image_generation_call",
    "image_generation_end",
}


class SaveGeneratedImageError(Exception):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save an image_gen payload to a requested destination.",
    )
    parser.add_argument(
        "--since",
        type=float,
        help="Only consider rollout image payloads at or after this epoch timestamp.",
    )
    parser.add_argument(
        "--destination",
        help="Target file or directory. Defaults to the project root.",
    )
    parser.add_argument(
        "--project-root",
        help="Project root used when --destination is omitted or relative.",
    )
    parser.add_argument(
        "--rollout-path",
        help="Current thread rollout JSONL path. Defaults to CODEX_THREAD_ID lookup.",
    )
    parser.add_argument(
        "--base64-stdin",
        action="store_true",
        help="Read an image base64 payload from stdin instead of the current rollout.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination file.",
    )
    parser.add_argument(
        "--relative-to",
        help="When used with --json, include a POSIX path for the saved image relative to this directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON object instead of only the saved path.",
    )
    args = parser.parse_args(argv)

    if not args.base64_stdin and args.since is None:
        parser.error("--since is required unless --base64-stdin is used")
    if args.base64_stdin and args.rollout_path:
        parser.error("--rollout-path cannot be used with --base64-stdin")

    return args


def project_root(explicit_root: str | None) -> pathlib.Path:
    if explicit_root:
        return pathlib.Path(explicit_root).expanduser().resolve()

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return pathlib.Path(result.stdout.strip()).resolve()
    return pathlib.Path.cwd().resolve()


def state_db_path() -> pathlib.Path:
    codex_home = os.environ.get("CODEX_HOME")
    home = (
        pathlib.Path(codex_home).expanduser()
        if codex_home
        else pathlib.Path.home() / ".codex"
    )
    return home / "state_5.sqlite"


def current_rollout_path() -> pathlib.Path:
    thread_id = os.environ.get("CODEX_THREAD_ID")
    if not thread_id:
        raise SaveGeneratedImageError(
            "CODEX_THREAD_ID is not set; pass --rollout-path or --base64-stdin.",
        )

    db_path = state_db_path()
    if not db_path.exists():
        raise SaveGeneratedImageError(f"Codex state database not found: {db_path}")

    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "select rollout_path from threads where id = ?",
                (thread_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise SaveGeneratedImageError(f"Could not read Codex state database: {exc}") from exc

    if not row or not row[0]:
        raise SaveGeneratedImageError(f"No rollout path found for CODEX_THREAD_ID={thread_id}")

    return pathlib.Path(row[0]).expanduser().resolve()


def timestamp_to_epoch(timestamp: str) -> float:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SaveGeneratedImageError(f"Invalid rollout timestamp: {timestamp}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def newest_rollout_payload(rollout_path: pathlib.Path, since: float) -> str:
    if not rollout_path.exists():
        raise SaveGeneratedImageError(f"Rollout JSONL not found: {rollout_path}")

    candidates: list[tuple[float, int, str]] = []
    try:
        with rollout_path.open(encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") not in IMAGE_GENERATION_EVENT_TYPES:
                    continue

                result = payload.get("result")
                if not isinstance(result, str) or not result.strip():
                    continue

                timestamp = record.get("timestamp")
                if not isinstance(timestamp, str):
                    continue
                epoch = timestamp_to_epoch(timestamp)
                if epoch >= since:
                    candidates.append((epoch, line_number, result))
    except OSError as exc:
        raise SaveGeneratedImageError(f"Could not read rollout JSONL: {exc}") from exc

    if not candidates:
        raise SaveGeneratedImageError(
            f"No image_gen payload found at or after {since} in current thread rollout: {rollout_path}",
        )

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2]


def normalize_base64(payload: str) -> str:
    payload = payload.strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    return "".join(payload.split())


def image_suffix(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    if image_bytes.startswith(b"BM"):
        return ".bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp":
        brand = image_bytes[8:12]
        if brand in {b"avif", b"avis"}:
            return ".avif"
        if brand in {b"heic", b"heix", b"hevc", b"hevx"}:
            return ".heic"
    raise SaveGeneratedImageError("Decoded payload is not a recognized image format.")


def decode_image_payload(payload: str) -> tuple[bytes, str]:
    try:
        image_bytes = base64.b64decode(normalize_base64(payload), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SaveGeneratedImageError(f"Invalid image base64 payload: {exc}") from exc

    if not image_bytes:
        raise SaveGeneratedImageError("Image base64 payload decoded to empty bytes.")

    return image_bytes, image_suffix(image_bytes)


def default_filename(suffix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"image-creator-{stamp}{suffix}"


def resolve_destination(
    destination: str | None,
    root: pathlib.Path,
    suffix: str,
) -> pathlib.Path:
    if not destination:
        return root / default_filename(suffix)

    raw_destination = destination
    path = pathlib.Path(destination).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    is_directory = (
        raw_destination.endswith((os.sep, "/"))
        or path.exists()
        and path.is_dir()
        or not path.suffix
    )
    if is_directory:
        return path / default_filename(suffix)
    return path


def unique_path(path: pathlib.Path) -> pathlib.Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def write_image(image_bytes: bytes, destination: pathlib.Path, overwrite: bool) -> pathlib.Path:
    final_path = destination if overwrite else unique_path(destination)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(image_bytes)
    return final_path


def relative_reference(path: pathlib.Path, root: str | None) -> str | None:
    if not root:
        return None
    root_path = pathlib.Path(root).expanduser().resolve()
    try:
        relative = path.resolve().relative_to(root_path)
    except ValueError as exc:
        raise SaveGeneratedImageError(f"Saved image is not under --relative-to root: {root_path}") from exc
    return pathlib.PurePosixPath(*relative.parts).as_posix()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.base64_stdin:
            payload = sys.stdin.read()
        else:
            rollout_path = (
                pathlib.Path(args.rollout_path).expanduser().resolve()
                if args.rollout_path
                else current_rollout_path()
            )
            payload = newest_rollout_payload(rollout_path, args.since)

        image_bytes, suffix = decode_image_payload(payload)
        destination = resolve_destination(
            args.destination,
            project_root(args.project_root),
            suffix,
        )
        saved = write_image(image_bytes, destination, args.overwrite)
        relative_path = relative_reference(saved, args.relative_to)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "saved_path": str(saved),
                    "relative_path": relative_path,
                    "suffix": suffix,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
