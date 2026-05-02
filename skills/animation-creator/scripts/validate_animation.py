#!/usr/bin/env python3
"""Validate an animation sheet or frame directory and write JSON diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

from PIL import Image

from animation_common import (
    alpha_nonzero_count,
    chroma_adjacent_count,
    chroma_settings,
    edge_alpha_count,
    filter_states,
    load_json,
    locate_frame_files,
    manifest_for_run,
    manifest_settings,
    parse_hex_color,
    parse_size,
    resolve_path,
    write_json,
)


def load_frame_manifest_rows(root: Path) -> dict[str, dict[str, object]]:
    manifest_path = root / "frames-manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    rows = manifest.get("rows", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["state"]): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("state"), str)
    }


def validate_sheet(
    path: Path,
    settings: dict[str, object],
    *,
    min_used_pixels: int,
    near_opaque_threshold: float,
    allow_opaque: bool,
    chroma_key: tuple[int, int, int] | None,
    chroma_adjacent_threshold: float,
    chroma_adjacent_pixel_threshold: int,
    edge_margin: int,
    edge_pixel_threshold: int,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    cells: list[dict[str, object]] = []
    try:
        with Image.open(path) as opened:
            source_format = opened.format
            source_mode = opened.mode
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "file": str(path), "errors": [f"could not open image: {exc}"], "warnings": []}

    frame_w = int(settings["frame_width"])
    frame_h = int(settings["frame_height"])
    rows = max(int(state["row"]) for state in settings["states"]) + 1
    columns = max(int(state["frames"]) for state in settings["states"])
    expected_size = (columns * frame_w, rows * frame_h)
    if image.size != expected_size:
        errors.append(f"expected {expected_size[0]}x{expected_size[1]}, got {image.width}x{image.height}")
    if source_format not in {"PNG", "WEBP"}:
        errors.append(f"expected PNG or WebP, got {source_format}")
    if "A" not in source_mode and not allow_opaque:
        errors.append("image does not have an alpha channel")

    used_by_row = {int(state["row"]): (str(state["name"]), int(state["frames"])) for state in settings["states"]}
    for row in range(rows):
        state_name, used_count = used_by_row.get(row, (f"row-{row}", 0))
        for column in range(columns):
            cell = image.crop((column * frame_w, row * frame_h, (column + 1) * frame_w, (row + 1) * frame_h))
            nontransparent = alpha_nonzero_count(cell)
            edge_pixels = edge_alpha_count(cell, edge_margin)
            chroma_adjacent_pixels = chroma_adjacent_count(cell, chroma_key, chroma_adjacent_threshold)
            used = column < used_count
            cells.append(
                {
                    "state": state_name,
                    "row": row,
                    "column": column,
                    "used": used,
                    "nontransparent_pixels": nontransparent,
                    "edge_pixels": edge_pixels,
                    "chroma_adjacent_pixels": chroma_adjacent_pixels,
                }
            )
            if used and nontransparent < min_used_pixels:
                errors.append(f"{state_name} row {row} column {column} is empty or too sparse ({nontransparent} pixels)")
            if not used and nontransparent:
                errors.append(f"{state_name} row {row} unused column {column} is not transparent ({nontransparent} pixels)")
            if used and nontransparent > frame_w * frame_h * near_opaque_threshold:
                message = f"{state_name} row {row} column {column} is nearly opaque; background may not be transparent"
                if allow_opaque:
                    warnings.append(message)
                else:
                    errors.append(message)
            if used and edge_pixels > edge_pixel_threshold:
                warnings.append(f"{state_name} row {row} column {column} has {edge_pixels} non-transparent pixels near the cell edge")
            if used and chroma_adjacent_pixels > chroma_adjacent_pixel_threshold:
                errors.append(f"{state_name} row {row} column {column} has {chroma_adjacent_pixels} non-transparent pixels close to the chroma key")
    return {"ok": not errors, "file": str(path), "format": source_format, "mode": source_mode, "width": image.width, "height": image.height, "errors": errors, "warnings": warnings, "cells": cells}


def validate_frames(
    root: Path,
    settings: dict[str, object],
    min_used_pixels: int,
    *,
    chroma_key: tuple[int, int, int] | None,
    chroma_adjacent_threshold: float,
    chroma_adjacent_pixel_threshold: int,
    edge_margin: int,
    edge_pixel_threshold: int,
    require_components: bool,
    small_outlier_ratio: float,
    large_outlier_ratio: float,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    frames: list[dict[str, object]] = []
    expected_size = (int(settings["frame_width"]), int(settings["frame_height"]))
    manifest_rows = load_frame_manifest_rows(root)
    for state in settings["states"]:
        state_name = str(state["name"])
        manifest_row = manifest_rows.get(state_name, {})
        method = manifest_row.get("method")
        if require_components and method and method != "components":
            errors.append(f"{state_name} used extraction method {method}; regenerate the action or inspect slot slicing")
        elif method and method != "components":
            warnings.append(f"{state_name} used extraction method {method}; component extraction is preferred")
        files = locate_frame_files(root, str(state["name"]))
        if len(files) != int(state["frames"]):
            errors.append(f"{state['name']} needs exactly {state['frames']} frames, found {len(files)}")
        areas: list[int] = []
        for index, path in enumerate(files[: int(state["frames"])]):
            try:
                with Image.open(path) as opened:
                    mode = opened.mode
                    image = opened.convert("RGBA")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"could not open {path}: {exc}")
                continue
            nontransparent = alpha_nonzero_count(image)
            areas.append(nontransparent)
            edge_pixels = edge_alpha_count(image, edge_margin)
            chroma_adjacent_pixels = chroma_adjacent_count(image, chroma_key, chroma_adjacent_threshold)
            frames.append(
                {
                    "state": state["name"],
                    "index": index,
                    "file": str(path),
                    "width": image.width,
                    "height": image.height,
                    "mode": mode,
                    "nontransparent_pixels": nontransparent,
                    "edge_pixels": edge_pixels,
                    "chroma_adjacent_pixels": chroma_adjacent_pixels,
                }
            )
            if image.size != expected_size:
                errors.append(f"{path} expected {expected_size[0]}x{expected_size[1]}, got {image.width}x{image.height}")
            if nontransparent < min_used_pixels:
                errors.append(f"{path} is empty or too sparse ({nontransparent} pixels)")
            if "A" not in mode:
                warnings.append(f"{path} has no alpha channel")
            if edge_pixels > edge_pixel_threshold:
                warnings.append(f"{path} has {edge_pixels} non-transparent pixels near the cell edge")
            if chroma_adjacent_pixels > chroma_adjacent_pixel_threshold:
                errors.append(f"{path} has {chroma_adjacent_pixels} non-transparent pixels close to the chroma key")
        if areas:
            median_area = median(areas)
            for index, area in enumerate(areas[: int(state["frames"])]):
                if median_area > 0 and area < median_area * small_outlier_ratio:
                    warnings.append(f"{state_name} frame {index:03d} is much smaller than the state median ({area} vs {median_area:.0f})")
                if median_area > 0 and area > median_area * large_outlier_ratio:
                    warnings.append(f"{state_name} frame {index:03d} is much larger than the state median ({area} vs {median_area:.0f})")
    return {"ok": not errors, "frames_root": str(root), "errors": errors, "warnings": warnings, "frames": frames}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Validate one action/state from the run.")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--sheet")
    source.add_argument("--frames-root")
    parser.add_argument("--json-out")
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"))
    parser.add_argument("--min-used-pixels", type=int, default=50)
    parser.add_argument("--near-opaque-threshold", type=float, default=0.95)
    parser.add_argument("--edge-margin", type=int, default=2)
    parser.add_argument("--edge-pixel-threshold", type=int, default=24)
    parser.add_argument("--chroma-adjacent-threshold", type=float, default=190.0)
    parser.add_argument("--chroma-adjacent-pixel-threshold", type=int, default=800)
    parser.add_argument("--small-outlier-ratio", type=float, default=0.35)
    parser.add_argument("--large-outlier-ratio", type=float, default=2.75)
    parser.add_argument("--require-components", action="store_true", help="Fail actions that fell back to equal-slot extraction.")
    parser.add_argument("--allow-opaque", action="store_true")
    args = parser.parse_args()

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
    chroma = chroma_settings(manifest)
    chroma_key = parse_hex_color(chroma["hex"])
    if args.sheet:
        result = validate_sheet(
            resolve_path(args.sheet, run_dir),
            settings,
            min_used_pixels=args.min_used_pixels,
            near_opaque_threshold=args.near_opaque_threshold,
            allow_opaque=args.allow_opaque,
            chroma_key=chroma_key,
            chroma_adjacent_threshold=args.chroma_adjacent_threshold,
            chroma_adjacent_pixel_threshold=args.chroma_adjacent_pixel_threshold,
            edge_margin=args.edge_margin,
            edge_pixel_threshold=args.edge_pixel_threshold,
        )
    else:
        frames_root = args.frames_root or "frames"
        result = validate_frames(
            resolve_path(frames_root, run_dir),
            settings,
            args.min_used_pixels,
            chroma_key=chroma_key,
            chroma_adjacent_threshold=args.chroma_adjacent_threshold,
            chroma_adjacent_pixel_threshold=args.chroma_adjacent_pixel_threshold,
            edge_margin=args.edge_margin,
            edge_pixel_threshold=args.edge_pixel_threshold,
            require_components=args.require_components,
            small_outlier_ratio=args.small_outlier_ratio,
            large_outlier_ratio=args.large_outlier_ratio,
        )
    json_out = args.json_out or (f"final/{args.action_id}-validation.json" if args.action_id else "final/validation.json")
    if json_out:
        write_json(resolve_path(json_out, run_dir), result)
    print(json.dumps({key: value for key, value in result.items() if key not in {"cells", "frames"}}, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
