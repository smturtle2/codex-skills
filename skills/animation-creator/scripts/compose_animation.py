#!/usr/bin/env python3
"""Compose extracted frames into a transparent animation sheet."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from animation_common import (
    DEFAULT_WORKING_CELL_SIZE,
    frame_size_from_manifest,
    filter_states,
    load_json,
    locate_frame_files,
    manifest_for_run,
    manifest_settings,
    parse_size,
    resolve_path,
)


def save_image(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    if suffix == ".webp":
        image.save(output, format="WEBP", lossless=True, quality=100, method=6)
    else:
        image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Compose one action/state from the run.")
    parser.add_argument("--frames-root")
    parser.add_argument("--output")
    parser.add_argument("--webp-output")
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"))
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args()

    manifest_path = manifest_for_run(args.run_dir, args.manifest)
    manifest = load_json(manifest_path) if manifest_path else {}
    run_dir = Path(manifest["run_dir"]).expanduser().resolve() if manifest.get("run_dir") else Path.cwd()
    frame_size = parse_size(args.frame_size, DEFAULT_WORKING_CELL_SIZE) if args.frame_size else None
    settings = filter_states(
        manifest_settings(manifest, frame_size=frame_size, frame_count=args.frame_count, fps=args.fps, output_format=args.format),
        args.action_id,
    )
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    frames_root = resolve_path(args.frames_root or paths.get("frames_dir", "frames"), run_dir)
    default_output = f"final/{args.action_id}-frames.webp" if args.action_id else paths.get("aggregate_sheet", "final/animation-frames.webp")
    output = resolve_path(args.output or default_output, run_dir)

    frames_manifest_path = frames_root / "frames-manifest.json"
    frame_manifest_rows = {}
    if frames_manifest_path.is_file():
        frames_manifest = load_json(frames_manifest_path)
        rows_data = frames_manifest.get("rows")
        if isinstance(rows_data, list):
            frame_manifest_rows = {
                str(row["state"]): row
                for row in rows_data
                if isinstance(row, dict) and isinstance(row.get("state"), str)
            }

    rows = max(state["row"] for state in settings["states"]) + 1
    columns = max(state["frames"] for state in settings["states"])
    frame_size_tuple = None
    for state in settings["states"]:
        frame_size_tuple = frame_size_from_manifest(frame_manifest_rows.get(state["name"], {}))
        if frame_size_tuple:
            break
    if frame_size_tuple is None:
        frame_size_tuple = (settings["frame_width"], settings["frame_height"])
    sheet = Image.new("RGBA", (columns * frame_size_tuple[0], rows * frame_size_tuple[1]), (0, 0, 0, 0))

    for state in settings["states"]:
        files = locate_frame_files(frames_root, state["name"])
        if len(files) < state["frames"]:
            raise SystemExit(f"{state['name']} needs {state['frames']} frames, found {len(files)} under {frames_root}")
        for column, frame_path in enumerate(files[: state["frames"]]):
            with Image.open(frame_path) as opened:
                frame = opened.convert("RGBA")
                if frame.size != frame_size_tuple:
                    raise SystemExit(
                        f"{frame_path} must be {frame_size_tuple[0]}x{frame_size_tuple[1]}; "
                        f"got {frame.width}x{frame.height}"
                    )
            sheet.alpha_composite(frame, (column * frame_size_tuple[0], state["row"] * frame_size_tuple[1]))

    save_image(sheet, output)
    print(f"wrote {output}")
    if args.webp_output:
        webp_output = resolve_path(args.webp_output, run_dir)
        save_image(sheet, webp_output)
        print(f"wrote {webp_output}")


if __name__ == "__main__":
    main()
