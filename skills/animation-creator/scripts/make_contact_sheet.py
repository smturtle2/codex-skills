#!/usr/bin/env python3
"""Create a labeled contact sheet for an animation sheet or frame directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from animation_common import (
    checker,
    filter_states,
    load_json,
    locate_frame_files,
    manifest_for_run,
    manifest_settings,
    parse_size,
    resolve_path,
)

LABEL_HEIGHT = 24


def load_cells_from_sheet(sheet_path: Path, settings: dict[str, object]) -> dict[str, list[Image.Image]]:
    with Image.open(sheet_path) as opened:
        sheet = opened.convert("RGBA")
    frame_w = int(settings["frame_width"])
    frame_h = int(settings["frame_height"])
    cells: dict[str, list[Image.Image]] = {}
    for state in settings["states"]:
        row = int(state["row"])
        cells[str(state["name"])] = [
            sheet.crop((column * frame_w, row * frame_h, (column + 1) * frame_w, (row + 1) * frame_h))
            for column in range(int(state["frames"]))
        ]
    return cells


def load_cells_from_frames(root: Path, settings: dict[str, object]) -> dict[str, list[Image.Image]]:
    cells: dict[str, list[Image.Image]] = {}
    for state in settings["states"]:
        frames = []
        for path in locate_frame_files(root, str(state["name"]))[: int(state["frames"])]:
            with Image.open(path) as opened:
                frames.append(opened.convert("RGBA"))
        cells[str(state["name"])] = frames
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Create a contact sheet for one action/state.")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--sheet")
    source.add_argument("--frames-root")
    parser.add_argument("--output")
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"))
    args = parser.parse_args()

    if args.scale <= 0:
        raise SystemExit("scale must be positive")
    manifest_path = manifest_for_run(args.run_dir, args.manifest)
    manifest = load_json(manifest_path) if manifest_path else {}
    run_dir = Path(manifest["run_dir"]).expanduser().resolve() if manifest.get("run_dir") else Path.cwd()
    settings = filter_states(
        manifest_settings(
            manifest,
            frame_size=parse_size(args.frame_size, (512, 512)) if args.frame_size else None,
            frame_count=args.frame_count,
            fps=args.fps,
            output_format=args.format,
        ),
        args.action_id,
    )
    frames_root = args.frames_root or "frames"
    cells = load_cells_from_sheet(resolve_path(args.sheet, run_dir), settings) if args.sheet else load_cells_from_frames(resolve_path(frames_root, run_dir), settings)

    frame_w = max(1, round(int(settings["frame_width"]) * args.scale))
    frame_h = max(1, round(int(settings["frame_height"]) * args.scale))
    columns = max(int(state["frames"]) for state in settings["states"])
    rows = len(settings["states"])
    width = columns * frame_w
    height = rows * (frame_h + LABEL_HEIGHT)
    sheet = Image.new("RGB", (width, height), "#f7f7f7")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for visual_row, state in enumerate(settings["states"]):
        state_name = str(state["name"])
        y = visual_row * (frame_h + LABEL_HEIGHT)
        draw.rectangle((0, y, width, y + LABEL_HEIGHT - 1), fill="#111111")
        draw.text((6, y + 6), f"{state_name} ({state['frames']} frames @ {state['fps']:g} fps)", fill="#ffffff", font=font)
        for column in range(columns):
            x = column * frame_w
            bg = checker((frame_w, frame_h), square=max(4, round(16 * args.scale)))
            if column < len(cells.get(state_name, [])):
                frame = cells[state_name][column].resize((frame_w, frame_h), Image.Resampling.LANCZOS)
                bg.paste(frame, (0, 0), frame)
                outline = "#18a058"
            else:
                outline = "#cc3344" if column < int(state["frames"]) else "#777777"
            sheet.paste(bg, (x, y + LABEL_HEIGHT))
            draw.rectangle((x, y + LABEL_HEIGHT, x + frame_w - 1, y + LABEL_HEIGHT + frame_h - 1), outline=outline)
            draw.text((x + 4, y + LABEL_HEIGHT + 4), str(column), fill="#111111", font=font)

    output_path = args.output or (f"qa/{args.action_id}-contact-sheet.png" if args.action_id else "qa/contact-sheet.png")
    target = resolve_path(output_path, run_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
