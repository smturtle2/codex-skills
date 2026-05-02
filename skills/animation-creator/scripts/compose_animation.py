#!/usr/bin/env python3
"""Compose normalized frames into a transparent animation sheet."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from animation_common import (
    filter_states,
    fit_to_frame,
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
    frame_size = parse_size(args.frame_size, (512, 512)) if args.frame_size else None
    settings = filter_states(
        manifest_settings(manifest, frame_size=frame_size, frame_count=args.frame_count, fps=args.fps, output_format=args.format),
        args.action_id,
    )
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    frames_root = resolve_path(args.frames_root or paths.get("frames_dir", "frames"), run_dir)
    default_output = f"final/{args.action_id}-frames.png" if args.action_id else paths.get("composed", "final/animation.png")
    output = resolve_path(args.output or default_output, run_dir)

    rows = max(state["row"] for state in settings["states"]) + 1
    columns = max(state["frames"] for state in settings["states"])
    frame_size_tuple = (settings["frame_width"], settings["frame_height"])
    sheet = Image.new("RGBA", (columns * frame_size_tuple[0], rows * frame_size_tuple[1]), (0, 0, 0, 0))

    for state in settings["states"]:
        files = locate_frame_files(frames_root, state["name"])
        if len(files) < state["frames"]:
            raise SystemExit(f"{state['name']} needs {state['frames']} frames, found {len(files)} under {frames_root}")
        for column, frame_path in enumerate(files[: state["frames"]]):
            with Image.open(frame_path) as opened:
                frame = fit_to_frame(opened, frame_size_tuple, padding=args.padding)
            sheet.alpha_composite(frame, (column * frame_size_tuple[0], state["row"] * frame_size_tuple[1]))

    save_image(sheet, output)
    print(f"wrote {output}")
    if args.webp_output:
        webp_output = resolve_path(args.webp_output, run_dir)
        save_image(sheet, webp_output)
        print(f"wrote {webp_output}")


if __name__ == "__main__":
    main()
