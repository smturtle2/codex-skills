#!/usr/bin/env python3
# /// script
# dependencies = [
#   "faster-whisper>=1.1.0",
#   "nvidia-cublas-cu12>=12.0",
#   "nvidia-cudnn-cu12>=9.0",
#   "yt-dlp>=2025.1.15",
# ]
# ///
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
DEFAULT_MODEL = "turbo"
DEFAULT_COMPUTE_TYPE = "float16"


class GpuTranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscribedSegment:
    text: str
    start: float
    end: float


def source_to_download_url(source: str) -> str:
    value = source.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return f"https://www.youtube.com/watch?v={value}"
    if not value:
        raise ValueError("YouTube URL or video id is required")
    return value


def require_cuda_gpu(cuda_count: Callable[[], int] | None = None) -> int:
    if cuda_count is None:
        try:
            import ctranslate2
        except ImportError as exc:
            raise GpuTranscriptionError(
                "ctranslate2 is required to verify CUDA. Run this helper with `uv run`."
            ) from exc
        cuda_count = ctranslate2.get_cuda_device_count

    try:
        count = int(cuda_count())
    except Exception as exc:
        raise GpuTranscriptionError(f"Could not verify CUDA GPU availability: {exc}") from exc

    if count < 1:
        raise GpuTranscriptionError("CUDA GPU is required. CPU fallback is forbidden for this skill.")
    return count


def nvidia_library_dirs() -> list[Path]:
    dirs: list[Path] = []
    for module_name in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.submodule_search_locations is None:
            continue
        for location in spec.submodule_search_locations:
            path = Path(location)
            if path.is_dir():
                dirs.append(path)
    return dirs


def preload_nvidia_libraries() -> None:
    lib_dirs = nvidia_library_dirs()
    if not lib_dirs:
        return

    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    extra_ld_path = ":".join(str(path) for path in lib_dirs)
    os.environ["LD_LIBRARY_PATH"] = f"{extra_ld_path}:{current_ld_path}" if current_ld_path else extra_ld_path

    for lib_dir in lib_dirs:
        for lib_path in sorted(lib_dir.glob("*.so*")):
            try:
                ctypes.CDLL(str(lib_path), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                continue


def download_audio(source: str, output_dir: Path) -> Path:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise GpuTranscriptionError("yt-dlp is required. Run this helper with `uv run`.") from exc

    output_template = str(output_dir / "%(id)s.%(ext)s")
    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    url = source_to_download_url(source)
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as exc:
        raise GpuTranscriptionError(f"Failed to download YouTube audio: {exc}") from exc

    if path.exists():
        return path

    matches = sorted(output_dir.glob(f"{info.get('id', '*')}.*"))
    if matches:
        return matches[0]
    raise GpuTranscriptionError("yt-dlp reported success but no audio file was found.")


def normalize_segment_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    compute_type: str,
    language: str | None,
    beam_size: int,
) -> tuple[list[TranscribedSegment], dict[str, Any]]:
    require_cuda_gpu()
    preload_nvidia_libraries()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise GpuTranscriptionError("faster-whisper is required. Run this helper with `uv run`.") from exc

    try:
        model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
        raw_segments, info = model.transcribe(str(audio_path), language=language, beam_size=beam_size)
        segments = [
            TranscribedSegment(
                text=normalize_segment_text(segment.text),
                start=float(segment.start),
                end=float(segment.end),
            )
            for segment in raw_segments
            if normalize_segment_text(segment.text)
        ]
    except Exception as exc:
        message = str(exc)
        if "libcublas" in message or "libcudnn" in message:
            raise GpuTranscriptionError(
                f"GPU transcription failed because CUDA runtime libraries could not be loaded: {message}"
            ) from exc
        raise GpuTranscriptionError(f"GPU transcription failed: {exc}") from exc

    if not segments:
        raise GpuTranscriptionError("GPU transcription produced no text segments.")

    metadata = {
        "model": model_name,
        "device": "cuda",
        "compute_type": compute_type,
        "language": getattr(info, "language", language),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
    }
    return segments, metadata


def segments_to_text(segments: Iterable[TranscribedSegment]) -> str:
    return "\n".join(segment.text for segment in segments if segment.text).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download YouTube audio and transcribe it with CUDA-only faster-whisper.")
    parser.add_argument("source", help="YouTube URL or 11-character video id")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"faster-whisper model name. Default: {DEFAULT_MODEL}")
    parser.add_argument(
        "--compute-type",
        default=DEFAULT_COMPUTE_TYPE,
        choices=("float16", "int8_float16", "int8"),
        help=f"CUDA compute type. Default: {DEFAULT_COMPUTE_TYPE}",
    )
    parser.add_argument("--language", default=None, help="Optional language code such as ko or en")
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for transcription. Default: 5")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output transcript as text or JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        require_cuda_gpu()
        with tempfile.TemporaryDirectory(prefix="podcast-writer-audio-") as tmpdir:
            audio_path = download_audio(args.source, Path(tmpdir))
            segments, metadata = transcribe_audio(
                audio_path,
                model_name=args.model,
                compute_type=args.compute_type,
                language=args.language,
                beam_size=args.beam_size,
            )
    except (ValueError, GpuTranscriptionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = {
            **metadata,
            "text": segments_to_text(segments),
            "segments": [segment.__dict__ for segment in segments],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(segments_to_text(segments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
