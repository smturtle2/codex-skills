#!/usr/bin/env python3
"""Render GIF, WebP, and optionally MP4 previews from animation frames or a sheet."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from animation_common import (
    DEFAULT_WORKING_CELL_SIZE,
    DEFAULT_PREVIEW_FRAME_DURATION_MS,
    checker,
    filter_states,
    load_json,
    locate_frame_files,
    manifest_for_run,
    manifest_settings,
    parse_size,
    resolve_path,
)


def frames_from_sheet(sheet_path: Path, state: dict[str, object], settings: dict[str, object]) -> list[Image.Image]:
    with Image.open(sheet_path) as opened:
        sheet = opened.convert("RGBA")
    columns = max(int(item["frames"]) for item in settings["states"])
    rows = max(int(item["row"]) for item in settings["states"]) + 1
    frame_w = sheet.width // columns
    frame_h = sheet.height // rows
    row = int(state["row"])
    return [
        sheet.crop((column * frame_w, row * frame_h, (column + 1) * frame_w, (row + 1) * frame_h))
        for column in range(int(state["frames"]))
    ]


def frames_from_root(root: Path, state: dict[str, object]) -> list[Image.Image]:
    frames = []
    for path in locate_frame_files(root, str(state["name"]))[: int(state["frames"])]:
        with Image.open(path) as opened:
            frames.append(opened.convert("RGBA"))
    return frames


def composite_preview_frames(frames: list[Image.Image], scale: int, transparent: bool) -> list[Image.Image]:
    output = []
    for frame in frames:
        if scale != 1:
            frame = frame.resize((frame.width * scale, frame.height * scale), Image.Resampling.NEAREST)
        if transparent:
            output.append(frame)
        else:
            bg = checker(frame.size, square=max(4, 16 * scale))
            bg.paste(frame, (0, 0), frame)
            output.append(bg.convert("RGB"))
    return output


def save_gif(frames: list[Image.Image], output: Path, duration_ms: int, loop_count: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=duration_ms, loop=loop_count, disposal=2)


def save_webp(frames: list[Image.Image], output: Path, duration_ms: int, loop_count: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], duration=duration_ms, loop=loop_count, lossless=True, quality=100, method=6)


def shell_quote_for_concat(path: Path) -> str:
    return "'" + str(path).replace("'", "'\\''") + "'"


def save_mp4(frames: list[Image.Image], output: Path, duration_ms: int, ffmpeg: str) -> bool:
    if not shutil.which(ffmpeg) and not Path(ffmpeg).exists():
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="animation-preview-") as temp_raw:
        temp = Path(temp_raw)
        frame_paths = []
        for index, frame in enumerate(frames):
            rgb = frame.convert("RGB")
            path = temp / f"frame-{index:04d}.png"
            rgb.save(path)
            frame_paths.append(path)
        concat = temp / "input.ffconcat"
        lines = ["ffconcat version 1.0"]
        for frame_path in frame_paths:
            lines.append(f"file {shell_quote_for_concat(frame_path)}")
            lines.append(f"duration {duration_ms / 1000:.3f}")
        lines.append(f"file {shell_quote_for_concat(frame_paths[-1])}")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat),
                "-vf",
                "format=yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Render one action/state.")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--sheet")
    source.add_argument("--frames-root")
    parser.add_argument("--output-dir")
    parser.add_argument("--formats", default="webp", help="Comma-separated: gif,webp,mp4")
    parser.add_argument(
        "--write-final",
        action="store_true",
        help="Also write unscaled final GIF/WebP animation files under final/.",
    )
    parser.add_argument(
        "--final-only",
        action="store_true",
        help="When used with --write-final, skip QA preview files and write only final animation files.",
    )
    parser.add_argument("--state", help="Render one state only. Alias for --action-id.")
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--loops", type=int, default=1, help="Repeat frames inside each preview.")
    parser.add_argument("--loop-count", type=int, help="Animated image loop count. Defaults to manifest loop setting: 0 for loop, 1 for no loop.")
    parser.add_argument("--transparent", action="store_true", help="Keep transparency for GIF/WebP instead of checker background.")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"))
    args = parser.parse_args()

    if args.scale <= 0 or args.loops <= 0:
        raise SystemExit("scale and loops must be positive")
    if args.loop_count is not None and args.loop_count < 0:
        raise SystemExit("loop-count must be non-negative")
    manifest_path = manifest_for_run(args.run_dir, args.manifest)
    manifest = load_json(manifest_path) if manifest_path else {}
    run_dir = Path(manifest["run_dir"]).expanduser().resolve() if manifest.get("run_dir") else Path.cwd()
    action_id = args.action_id or args.state
    settings = filter_states(
        manifest_settings(
            manifest,
            frame_size=parse_size(args.frame_size, DEFAULT_WORKING_CELL_SIZE) if args.frame_size else None,
            frame_count=args.frame_count,
            fps=args.fps,
            output_format=args.format,
        ),
        action_id,
    )
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    output_dir = resolve_path(args.output_dir or paths.get("preview_dir", "previews"), run_dir)
    requested_formats = {item.strip().lower().lstrip(".") for item in args.formats.split(",") if item.strip()}
    unknown = requested_formats - {"gif", "webp", "mp4"}
    if unknown:
        raise SystemExit(f"unknown preview format(s): {', '.join(sorted(unknown))}")
    manifest_loop = bool(manifest.get("loop", manifest.get("animation", {}).get("loop", True) if isinstance(manifest.get("animation"), dict) else True))
    loop_count = args.loop_count if args.loop_count is not None else (0 if manifest_loop else 1)

    rendered = []
    for state in settings["states"]:
        raw_frames = frames_from_sheet(resolve_path(args.sheet, run_dir), state, settings) if args.sheet else frames_from_root(resolve_path(args.frames_root or "frames", run_dir), state)
        if len(raw_frames) < int(state["frames"]):
            raise SystemExit(f"{state['name']} needs {state['frames']} frames, found {len(raw_frames)}")
        raw_frames = raw_frames * args.loops
        duration_ms = (
            max(1, round(1000 / float(state["fps"])))
            if state.get("fps") is not None
            else DEFAULT_PREVIEW_FRAME_DURATION_MS
        )
        stem = output_dir / str(state["name"])
        if not args.final_only:
            preview_frames = composite_preview_frames(raw_frames, args.scale, args.transparent)
            if "gif" in requested_formats:
                save_gif(preview_frames, stem.with_suffix(".gif"), duration_ms, loop_count)
                rendered.append(str(stem.with_suffix(".gif")))
            if "webp" in requested_formats:
                save_webp(preview_frames, stem.with_suffix(".webp"), duration_ms, loop_count)
                rendered.append(str(stem.with_suffix(".webp")))
            if "mp4" in requested_formats:
                mp4_path = stem.with_suffix(".mp4")
                if save_mp4(preview_frames, mp4_path, duration_ms, args.ffmpeg):
                    rendered.append(str(mp4_path))
                else:
                    print(f"skipped MP4 for {state['name']}: ffmpeg not found")

        if args.write_final:
            final_stem = run_dir / "final" / str(state["name"])
            final_frames = composite_preview_frames(raw_frames, 1, transparent=True)
            if "gif" in requested_formats:
                save_gif(final_frames, final_stem.with_suffix(".gif"), duration_ms, loop_count)
                rendered.append(str(final_stem.with_suffix(".gif")))
            if "webp" in requested_formats:
                save_webp(final_frames, final_stem.with_suffix(".webp"), duration_ms, loop_count)
                rendered.append(str(final_stem.with_suffix(".webp")))
    print("\n".join(rendered))


if __name__ == "__main__":
    main()
