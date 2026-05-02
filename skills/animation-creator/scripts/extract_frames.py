#!/usr/bin/env python3
"""Extract animation grid images into normalized transparent frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from animation_common import (
    DEFAULT_SAFE_MARGIN,
    chroma_settings,
    filter_states,
    fit_to_frame,
    load_json,
    manifest_for_run,
    manifest_settings,
    parse_hex_color,
    parse_size,
    remove_chroma_background,
    resolve_path,
    write_json,
)


def connected_components(image: Image.Image) -> list[dict[str, Any]]:
    alpha = image.getchannel("A")
    width, height = image.size
    data = alpha.tobytes()
    visited = bytearray(width * height)
    components: list[dict[str, Any]] = []
    for start, value in enumerate(data):
        if value <= 16 or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        pixels: list[int] = []
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        while stack:
            current = stack.pop()
            pixels.append(current)
            x = current % width
            y = current // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            for neighbor in (current - 1, current + 1, current - width, current + width):
                if neighbor < 0 or neighbor >= len(data) or visited[neighbor]:
                    continue
                nx = neighbor % width
                if abs(nx - x) > 1:
                    continue
                if data[neighbor] > 16:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append(
            {
                "pixels": pixels,
                "area": len(pixels),
                "bbox": (min_x, min_y, max_x + 1, max_y + 1),
                "center_x": (min_x + max_x + 1) / 2,
                "center_y": (min_y + max_y + 1) / 2,
            }
        )
    return components


def state_layout(state: dict[str, Any], frame_count: int) -> dict[str, int]:
    layout = state.get("layout") if isinstance(state.get("layout"), dict) else {}
    columns = int(layout.get("columns", frame_count))
    rows = int(layout.get("rows", 1))
    if columns <= 0 or rows <= 0:
        raise SystemExit(f"invalid grid layout for {state['name']}")
    if columns * rows < frame_count:
        raise SystemExit(f"grid layout {columns}x{rows} cannot fit {frame_count} frames for {state['name']}")
    return {"columns": columns, "rows": rows}


def slot_centers(sheet: Image.Image, layout: dict[str, int], frame_count: int) -> list[tuple[int, float, float]]:
    slot_width = sheet.width / layout["columns"]
    slot_height = sheet.height / layout["rows"]
    return [
        (index, (index % layout["columns"] + 0.5) * slot_width, (index // layout["columns"] + 0.5) * slot_height)
        for index in range(frame_count)
    ]


def component_group_image(source: Image.Image, components: list[dict[str, Any]], padding: int) -> Image.Image:
    width, height = source.size
    min_x = max(0, min(component["bbox"][0] for component in components) - padding)
    min_y = max(0, min(component["bbox"][1] for component in components) - padding)
    max_x = min(width, max(component["bbox"][2] for component in components) + padding)
    max_y = min(height, max(component["bbox"][3] for component in components) + padding)
    output = Image.new("RGBA", (max_x - min_x, max_y - min_y), (0, 0, 0, 0))
    source_pixels = source.load()
    output_pixels = output.load()
    for component in components:
        for pixel_index in component["pixels"]:
            x = pixel_index % width
            y = pixel_index // width
            output_pixels[x - min_x, y - min_y] = source_pixels[x, y]
    return output


def extract_component_frames(
    sheet: Image.Image,
    frame_count: int,
    frame_size: tuple[int, int],
    layout: dict[str, int],
    padding: int,
) -> list[Image.Image] | None:
    components = connected_components(sheet)
    if not components:
        return None
    largest = max(component["area"] for component in components)
    seeds = [component for component in components if component["area"] >= max(120, largest * 0.20)]
    if len(seeds) < frame_count:
        seeds = sorted(components, key=lambda component: component["area"], reverse=True)[:frame_count]
    if len(seeds) < frame_count:
        return None
    centers = slot_centers(sheet, layout, frame_count)
    seeds = sorted(
        seeds[:frame_count],
        key=lambda component: min(
            centers,
            key=lambda center: (component["center_x"] - center[1]) ** 2 + (component["center_y"] - center[2]) ** 2,
        )[0],
    )
    seed_ids = {id(seed) for seed in seeds}
    groups: list[list[dict[str, Any]]] = [[seed] for seed in seeds]
    noise_threshold = max(12, largest * 0.002)
    for component in components:
        if id(component) in seed_ids or component["area"] < noise_threshold:
            continue
        nearest = min(
            range(len(seeds)),
            key=lambda index: (seeds[index]["center_x"] - component["center_x"]) ** 2 + (seeds[index]["center_y"] - component["center_y"]) ** 2,
        )
        groups[nearest].append(component)
    return [fit_to_frame(component_group_image(sheet, group, padding), frame_size, padding=padding) for group in groups]


def extract_slot_frames(sheet: Image.Image, frame_count: int, frame_size: tuple[int, int], layout: dict[str, int], padding: int) -> list[Image.Image]:
    slot_width = sheet.width / layout["columns"]
    slot_height = sheet.height / layout["rows"]
    frames = []
    for index in range(frame_count):
        column = index % layout["columns"]
        row = index // layout["columns"]
        crop = sheet.crop(
            (
                round(column * slot_width),
                round(row * slot_height),
                round((column + 1) * slot_width),
                round((row + 1) * slot_height),
            )
        )
        frames.append(fit_to_frame(crop, frame_size, padding=padding))
    return frames


def state_source(run_dir: Path | None, decoded_dir: Path, state: dict[str, Any]) -> Path:
    if state.get("source"):
        return resolve_path(str(state["source"]), run_dir)
    decoded = decoded_dir / f"{state['name']}.png"
    if decoded.is_file() or run_dir is None:
        return decoded
    return run_dir / "generated" / f"{state['name']}.png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Extract one action/state from the run.")
    parser.add_argument("--decoded-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"))
    parser.add_argument("--states", help="Comma-separated subset of state names.")
    parser.add_argument("--chroma-key")
    parser.add_argument("--key-threshold", type=float)
    parser.add_argument("--method", choices=("auto", "components", "slots"), default="auto")
    parser.add_argument("--padding", type=int, default=DEFAULT_SAFE_MARGIN)
    args = parser.parse_args()

    manifest_path = manifest_for_run(args.run_dir, args.manifest)
    manifest = load_json(manifest_path) if manifest_path else {}
    run_dir = Path(manifest["run_dir"]).expanduser().resolve() if manifest.get("run_dir") else None
    frame_size = parse_size(args.frame_size, (192, 192)) if args.frame_size else None
    settings = filter_states(
        manifest_settings(manifest, frame_size=frame_size, frame_count=args.frame_count, fps=args.fps, output_format=args.format),
        args.action_id,
    )
    chroma = chroma_settings(manifest, args.chroma_key)
    if args.key_threshold is not None:
        chroma["threshold"] = args.key_threshold
    key_rgb = parse_hex_color(chroma["hex"])
    base = run_dir or Path.cwd()
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    decoded_dir = resolve_path(args.decoded_dir or paths.get("decoded_dir", "decoded"), base)
    output_dir = resolve_path(args.output_dir or paths.get("frames_dir", "frames"), base)
    requested_states = {item.strip() for item in args.states.split(",")} if args.states else None

    rows = []
    for state in settings["states"]:
        if requested_states and state["name"] not in requested_states:
            continue
        source = state_source(run_dir, decoded_dir, state)
        if not source.is_file():
            raise SystemExit(f"missing grid sheet for {state['name']}: {source}")
        with Image.open(source) as opened:
            sheet = remove_chroma_background(opened, key_rgb, float(chroma["threshold"]))
        frames = None
        used_method = args.method
        layout = state_layout(state, int(state["frames"]))
        if args.method in {"auto", "components"}:
            frames = extract_component_frames(sheet, state["frames"], (settings["frame_width"], settings["frame_height"]), layout, args.padding)
            if frames is None and args.method == "components":
                raise SystemExit(f"could not extract {state['frames']} components from {source}")
            if frames is not None:
                used_method = "components"
        if frames is None:
            frames = extract_slot_frames(sheet, state["frames"], (settings["frame_width"], settings["frame_height"]), layout, args.padding)
            used_method = "slots"

        state_dir = output_dir / state["name"]
        state_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for index, frame in enumerate(frames):
            target = state_dir / f"{index:03d}.{settings['format']}"
            save_kwargs = {"format": settings["format"].upper()}
            if settings["format"] == "webp":
                save_kwargs.update({"lossless": True, "quality": 100, "method": 6})
            frame.save(target, **save_kwargs)
            outputs.append(str(target))
        rows.append({"state": state["name"], "source": str(source), "frames": outputs, "method": used_method, "layout": state["layout"]})

    result = {"ok": True, "frame_size": [settings["frame_width"], settings["frame_height"]], "format": settings["format"], "chroma_key": chroma, "split_order": "left-to-right-top-to-bottom", "rows": rows}
    write_json(output_dir / "frames-manifest.json", result)
    print(json.dumps({"ok": True, "frames_root": str(output_dir), "states": [row["state"] for row in rows]}, indent=2))


if __name__ == "__main__":
    main()
