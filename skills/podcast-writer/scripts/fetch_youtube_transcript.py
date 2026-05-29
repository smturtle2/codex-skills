#!/usr/bin/env python3
# /// script
# dependencies = ["youtube-transcript-api>=1.0.0"]
# ///
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float | None = None
    duration: float | None = None


def extract_video_id(value: str) -> str:
    candidate = value.strip()
    if VIDEO_ID_RE.fullmatch(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    is_youtube_host = (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtube-nocookie.com"
        or host.endswith(".youtube-nocookie.com")
    )

    query_id = parse_qs(parsed.query).get("v", [""])[0]
    if is_youtube_host and VIDEO_ID_RE.fullmatch(query_id):
        return query_id

    if (host == "youtu.be" or host.endswith(".youtu.be")) and path_parts and VIDEO_ID_RE.fullmatch(path_parts[0]):
        return path_parts[0]

    if is_youtube_host:
        for marker in ("shorts", "embed", "live"):
            if marker in path_parts:
                index = path_parts.index(marker)
                if index + 1 < len(path_parts) and VIDEO_ID_RE.fullmatch(path_parts[index + 1]):
                    return path_parts[index + 1]

    raise ValueError(f"Could not extract an 11-character YouTube video id from: {value}")


def clean_segment_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def segment_from_raw(segment: Any) -> TranscriptSegment:
    if isinstance(segment, dict):
        text = str(segment.get("text", ""))
        start = segment.get("start")
        duration = segment.get("duration")
    else:
        text = str(getattr(segment, "text", ""))
        start = getattr(segment, "start", None)
        duration = getattr(segment, "duration", None)

    return TranscriptSegment(
        text=clean_segment_text(text),
        start=float(start) if start is not None else None,
        duration=float(duration) if duration is not None else None,
    )


def normalize_segments(raw_segments: Iterable[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    previous = ""
    for raw in raw_segments:
        segment = segment_from_raw(raw)
        if not segment.text or segment.text == previous:
            continue
        segments.append(segment)
        previous = segment.text
    return segments


def transcript_to_text(segments: Iterable[TranscriptSegment]) -> str:
    return "\n".join(segment.text for segment in segments if segment.text).strip()


def require_usable_segments(segments: list[TranscriptSegment], video_id: str) -> list[TranscriptSegment]:
    if not segments:
        raise TranscriptError(f"Transcript for video id {video_id} contained no text segments.")
    return segments


def fetch_transcript(video_id: str, languages: list[str]) -> list[TranscriptSegment]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
    except ImportError as exc:
        raise TranscriptError(
            "youtube-transcript-api is required. Run with `uv run` or install youtube-transcript-api."
        ) from exc

    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=languages)
        else:
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except (NoTranscriptFound, TranscriptsDisabled) as exc:
        raise TranscriptError(f"No usable transcript found for video id {video_id}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - library/network errors vary.
        raise TranscriptError(f"Failed to fetch transcript for video id {video_id}: {exc}") from exc

    if hasattr(fetched, "to_raw_data"):
        fetched = fetched.to_raw_data()
    return require_usable_segments(normalize_segments(fetched), video_id)


def parse_languages(value: str) -> list[str]:
    languages = [part.strip() for part in value.split(",") if part.strip()]
    if not languages:
        raise argparse.ArgumentTypeError("at least one language code is required")
    return languages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and normalize a YouTube transcript.")
    parser.add_argument("source", help="YouTube URL or 11-character video id")
    parser.add_argument(
        "--languages",
        type=parse_languages,
        default=["ko", "en"],
        help="Comma-separated transcript language preference order. Default: ko,en",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output normalized transcript as plain text or JSON. Default: text",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        video_id = extract_video_id(args.source)
        segments = fetch_transcript(video_id, args.languages)
    except (ValueError, TranscriptError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = {
            "video_id": video_id,
            "languages": args.languages,
            "text": transcript_to_text(segments),
            "segments": [segment.__dict__ for segment in segments],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(transcript_to_text(segments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
