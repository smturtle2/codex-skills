#!/usr/bin/env python3
"""Extract animation grid images into transparent frames at generated cell size."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

from animation_common import (
    DEFAULT_SAFE_MARGIN,
    chroma_settings,
    filter_states,
    load_json,
    manifest_for_run,
    manifest_settings,
    parse_hex_color,
    parse_size,
    perceptual_background_distance,
    remove_chroma_background,
    resolve_path,
    write_json,
)

GENERATED_CELL_BORDER_ERASE_PAD = 8
SAFE_LINE_SEARCH_PAD = 36
DETECTED_SAFE_BOX_INNER_PAD = 3


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
    cell_width = int(layout.get("cell_width", 0) or 0)
    cell_height = int(layout.get("cell_height", 0) or 0)
    safe_margin_x = layout.get("safe_margin_x")
    safe_margin_y = layout.get("safe_margin_y")
    if columns <= 0 or rows <= 0:
        raise SystemExit(f"invalid grid layout for {state['name']}")
    if columns * rows < frame_count:
        raise SystemExit(f"grid layout {columns}x{rows} cannot fit {frame_count} frames for {state['name']}")
    result = {"columns": columns, "rows": rows, "cell_width": cell_width, "cell_height": cell_height}
    if safe_margin_x is not None:
        result["safe_margin_x"] = int(safe_margin_x)
    if safe_margin_y is not None:
        result["safe_margin_y"] = int(safe_margin_y)
    return result


def slot_centers(sheet: Image.Image, layout: dict[str, int], frame_count: int) -> list[tuple[int, float, float]]:
    slot_width = sheet.width / layout["columns"]
    slot_height = sheet.height / layout["rows"]
    return [
        (index, (index % layout["columns"] + 0.5) * slot_width, (index // layout["columns"] + 0.5) * slot_height)
        for index in range(frame_count)
    ]


def component_span(component: dict[str, Any]) -> tuple[int, int]:
    bbox = component["bbox"]
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def is_grid_artifact_component(component: dict[str, Any], sheet: Image.Image, layout: dict[str, int]) -> bool:
    width, height = component_span(component)
    if width <= 0 or height <= 0:
        return True
    sheet_w, sheet_h = sheet.size
    slot_w = sheet_w / layout["columns"]
    slot_h = sheet_h / layout["rows"]
    bbox = component["bbox"]
    bbox_area = width * height
    fill_ratio = component["area"] / bbox_area if bbox_area else 1.0
    sparse_sheet_spanning = width > sheet_w * 0.90 and height > sheet_h * 0.90 and fill_ratio < 0.12
    spans_multiple_columns = width > slot_w * 1.35
    spans_multiple_rows = height > slot_h * 1.35
    very_wide = width > sheet_w * 0.80 and height < slot_h * 0.18
    very_tall = height > sheet_h * 0.80 and width < slot_w * 0.18
    covers_grid = width > sheet_w * 0.65 and height > sheet_h * 0.65
    thin_for_extent = min(width, height) / max(width, height) < 0.08
    sheet_artifact = (
        sparse_sheet_spanning
        or very_wide
        or very_tall
        or (covers_grid and thin_for_extent)
        or (spans_multiple_columns and spans_multiple_rows and thin_for_extent)
    )
    if sheet_artifact:
        return True

    safe_x = layout.get("safe_margin_x")
    safe_y = layout.get("safe_margin_y")
    if safe_x is None or safe_y is None:
        return False

    column = min(int(layout["columns"]) - 1, max(0, int(component["center_x"] // slot_w)))
    row = min(int(layout["rows"]) - 1, max(0, int(component["center_y"] // slot_h)))
    slot_left = round(column * sheet_w / int(layout["columns"]))
    slot_top = round(row * sheet_h / int(layout["rows"]))
    slot_right = round((column + 1) * sheet_w / int(layout["columns"]))
    slot_bottom = round((row + 1) * sheet_h / int(layout["rows"]))
    scale_x = slot_w / max(1, int(layout.get("cell_width") or round(slot_w)))
    scale_y = slot_h / max(1, int(layout.get("cell_height") or round(slot_h)))
    safe_left = slot_left + round(int(safe_x) * scale_x)
    safe_right = slot_right - round(int(safe_x) * scale_x)
    safe_top = slot_top + round(int(safe_y) * scale_y)
    safe_bottom = slot_bottom - round(int(safe_y) * scale_y)
    tolerance = max(3, round(min(slot_w, slot_h) / 512 * 8))
    thin_vertical = width <= max(4, round(slot_w * 0.03)) and height >= slot_h * 0.45
    thin_horizontal = height <= max(4, round(slot_h * 0.03)) and width >= slot_w * 0.45
    near_safe_vertical = abs(bbox[0] - safe_left) <= tolerance or abs(bbox[2] - safe_right) <= tolerance
    near_safe_horizontal = abs(bbox[1] - safe_top) <= tolerance or abs(bbox[3] - safe_bottom) <= tolerance
    return (thin_vertical and near_safe_vertical) or (thin_horizontal and near_safe_horizontal)


def character_components(components: list[dict[str, Any]], sheet: Image.Image, layout: dict[str, int]) -> list[dict[str, Any]]:
    return [
        component
        for component in components
        if not is_grid_artifact_component(component, sheet, layout)
    ]


def component_slot_index(component: dict[str, Any], centers: list[tuple[int, float, float]]) -> int:
    return min(
        centers,
        key=lambda center: (component["center_x"] - center[1]) ** 2 + (component["center_y"] - center[2]) ** 2,
    )[0]


def slot_boxes(sheet: Image.Image, layout: dict[str, int], frame_count: int) -> list[tuple[int, int, int, int]]:
    boxes = []
    for index in range(frame_count):
        column = index % layout["columns"]
        row = index // layout["columns"]
        left = round(column * sheet.width / layout["columns"])
        top = round(row * sheet.height / layout["rows"])
        right = round((column + 1) * sheet.width / layout["columns"])
        bottom = round((row + 1) * sheet.height / layout["rows"])
        boxes.append(
            (
                max(0, min(sheet.width, left)),
                max(0, min(sheet.height, top)),
                max(0, min(sheet.width, right)),
                max(0, min(sheet.height, bottom)),
            )
        )
    return boxes


def common_slot_size(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int]:
    return (
        max(right - left for left, _top, right, _bottom in boxes),
        max(bottom - top for _left, top, _right, bottom in boxes),
    )


def is_chroma_green_like(red: int, green: int, blue: int) -> bool:
    return green >= 170 and red <= 100 and blue <= 120 and green - red >= 70 and green - blue >= 70


def is_neutral_canvas_like(red: int, green: int, blue: int) -> bool:
    return min(red, green, blue) >= 232 and max(red, green, blue) - min(red, green, blue) <= 18


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(left[index] - right[index]) for index in range(3))


def rgb_saturation_value(red: int, green: int, blue: int) -> tuple[float, float]:
    high = max(red, green, blue) / 255.0
    low = min(red, green, blue) / 255.0
    saturation = 0.0 if high <= 0 else (high - low) / high
    return saturation, high


def mask_components(mask: bytes, width: int, height: int) -> list[dict[str, Any]]:
    visited = bytearray(width * height)
    components: list[dict[str, Any]] = []
    for start, value in enumerate(mask):
        if visited[start]:
            continue
        if value <= 0:
            visited[start] = 1
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
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                neighbor = ny * width + nx
                if visited[neighbor] or mask[neighbor] <= 0:
                    continue
                visited[neighbor] = 1
                stack.append(neighbor)
        components.append(
            {
                "area": len(pixels),
                "bbox": (min_x, min_y, max_x + 1, max_y + 1),
            }
        )
    return components


def detect_chroma_rect_in_slot(
    cell: Image.Image,
    fallback_key: tuple[int, int, int],
    *,
    expected_left: int,
    expected_top: int,
    expected_right: int,
    expected_bottom: int,
) -> tuple[int, int, int, int] | None:
    width, height = cell.size
    if width <= 0 or height <= 0:
        return None
    pixels = cell.load()
    raw = bytearray(width * height)
    generous_threshold = 96.0
    for yy in range(height):
        for xx in range(width):
            red, green, blue = pixels[xx, yy]
            saturation, value = rgb_saturation_value(red, green, blue)
            close_to_manifest = perceptual_background_distance((red, green, blue), fallback_key) < generous_threshold
            broad_chroma = saturation > 0.45 and value > 0.35
            if close_to_manifest or broad_chroma:
                raw[yy * width + xx] = 255

    radius = max(2, min(7, round(min(width, height) / 96)))
    mask_image = Image.frombytes("L", (width, height), bytes(raw))
    mask_image = mask_image.filter(ImageFilter.MaxFilter(radius * 2 + 1)).filter(ImageFilter.MinFilter(radius * 2 + 1))
    open_radius = max(1, min(5, round(radius * 0.6)))
    mask_image = mask_image.filter(ImageFilter.MinFilter(open_radius * 2 + 1)).filter(ImageFilter.MaxFilter(open_radius * 2 + 1))
    mask = mask_image.tobytes()

    expected_center_x = (expected_left + expected_right) / 2
    expected_center_y = (expected_top + expected_bottom) / 2
    expected_area = max(1, (expected_right - expected_left) * (expected_bottom - expected_top))
    min_area = max(64, round(expected_area * 0.18))
    best_box: tuple[int, int, int, int] | None = None
    best_score = float("-inf")
    for component in mask_components(mask, width, height):
        area = int(component["area"])
        if area < min_area:
            continue
        left, top, right, bottom = [int(value) for value in component["bbox"]]
        box_width = right - left
        box_height = bottom - top
        if box_width <= 0 or box_height <= 0:
            continue
        rect_area = box_width * box_height
        fill_ratio = area / rect_area
        if fill_ratio < 0.30:
            continue
        if box_width < width * 0.25 or box_height < height * 0.25:
            continue
        aspect = max(box_width / box_height, box_height / box_width)
        if aspect > 4.0:
            continue
        center_penalty = abs(((left + right) / 2) - expected_center_x) + abs(((top + bottom) / 2) - expected_center_y)
        score = area + rect_area * 0.3 + fill_ratio * 10000.0 - center_penalty * 20.0
        if score > best_score:
            best_score = score
            best_box = (left, top, right, bottom)
    return best_box


def guide_line_pixel_weight(red: int, green: int, blue: int, ignored_colors: tuple[tuple[int, int, int], ...]) -> int:
    pixel = (red, green, blue)
    if any(color_distance(pixel, ignored) <= 32 for ignored in ignored_colors):
        return 0
    if is_chroma_green_like(red, green, blue) or is_neutral_canvas_like(red, green, blue):
        return 0
    if min(red, green, blue) <= 96:
        return 1
    if max(red, green, blue) - min(red, green, blue) >= 32:
        return 1
    if 70 <= red <= 220 and 70 <= green <= 220 and 70 <= blue <= 220:
        return 1
    return 0


def quantized_color(red: int, green: int, blue: int) -> tuple[int, int, int]:
    return tuple(min(255, (value // 8) * 8 + 4) for value in (red, green, blue))


def dominant_inner_color(
    cell: Image.Image,
    *,
    expected_left: int,
    expected_top: int,
    expected_right: int,
    expected_bottom: int,
) -> tuple[int, int, int] | None:
    pixels = cell.load()
    width, height = cell.size
    inset_x = max(4, round((expected_right - expected_left) * 0.20))
    inset_y = max(4, round((expected_bottom - expected_top) * 0.20))
    sample_left = max(0, min(width, expected_left + inset_x))
    sample_right = max(0, min(width, expected_right - inset_x))
    sample_top = max(0, min(height, expected_top + inset_y))
    sample_bottom = max(0, min(height, expected_bottom - inset_y))
    if sample_right <= sample_left or sample_bottom <= sample_top:
        return None
    step = max(1, round(min(width, height) / 128))
    counts: Counter[tuple[int, int, int]] = Counter()
    for yy in range(sample_top, sample_bottom, step):
        for xx in range(sample_left, sample_right, step):
            counts[quantized_color(*pixels[xx, yy])] += 1
    return counts.most_common(1)[0][0] if counts else None


def safe_area_line_scores(
    cell: Image.Image,
    *,
    expected_left: int,
    expected_top: int,
    expected_right: int,
    expected_bottom: int,
) -> tuple[list[int], list[int]]:
    pixels = cell.load()
    width, height = cell.size
    row_scores = [0] * height
    column_scores = [0] * width
    scan_left = max(0, expected_left)
    scan_right = min(width, expected_right)
    scan_top = max(0, expected_top)
    scan_bottom = min(height, expected_bottom)
    dominant = dominant_inner_color(
        cell,
        expected_left=expected_left,
        expected_top=expected_top,
        expected_right=expected_right,
        expected_bottom=expected_bottom,
    )
    ignored_colors = (dominant,) if dominant else ()

    for yy in range(height):
        score = 0
        for xx in range(scan_left, scan_right):
            score += guide_line_pixel_weight(*pixels[xx, yy], ignored_colors)
        row_scores[yy] = score

    for xx in range(width):
        score = 0
        for yy in range(scan_top, scan_bottom):
            score += guide_line_pixel_weight(*pixels[xx, yy], ignored_colors)
        column_scores[xx] = score

    return row_scores, column_scores


def best_line_group(
    scores: list[int],
    *,
    expected: int,
    search_pad: int,
    minimum_score: int,
    min_index: int | None = None,
    max_index: int | None = None,
) -> tuple[int, int] | None:
    start = max(0, expected - search_pad, min_index if min_index is not None else 0)
    end = min(len(scores), expected + search_pad + 1, max_index if max_index is not None else len(scores))
    groups: list[tuple[int, int, int, int]] = []
    group_start: int | None = None
    group_score = 0
    group_peak = 0
    for index in range(start, end):
        if scores[index] >= minimum_score:
            if group_start is None:
                group_start = index
                group_score = 0
                group_peak = 0
            group_score += scores[index]
            group_peak = max(group_peak, scores[index])
        elif group_start is not None:
            groups.append((group_start, index, group_score, group_peak))
            group_start = None
    if group_start is not None:
        groups.append((group_start, end, group_score, group_peak))
    if not groups:
        return None
    best = max(groups, key=lambda item: (item[3], item[2], -abs(((item[0] + item[1]) / 2) - expected)))
    return best[0], best[1]


def first_index_at_least(scores: list[int], start: int, end: int, minimum_score: int) -> int | None:
    for index in range(max(0, start), min(len(scores), end)):
        if scores[index] >= minimum_score:
            return index
    return None


def last_index_at_least(scores: list[int], start: int, end: int, minimum_score: int) -> int | None:
    for index in range(min(len(scores), end) - 1, max(0, start) - 1, -1):
        if scores[index] >= minimum_score:
            return index
    return None


def detect_inner_fill_box(
    cell: Image.Image,
    *,
    expected_left: int,
    expected_top: int,
    expected_right: int,
    expected_bottom: int,
    search_pad: int,
    chroma_key: tuple[int, int, int],
    chroma_threshold: float,
) -> tuple[int, int, int, int] | None:
    pixels = cell.load()
    width, height = cell.size
    row_counts = [0] * height
    column_counts = [0] * width
    for yy in range(height):
        for xx in range(width):
            if color_distance(pixels[xx, yy], chroma_key) <= chroma_threshold:
                row_counts[yy] += 1
                column_counts[xx] += 1

    horizontal_span = max(1, expected_right - expected_left)
    vertical_span = max(1, expected_bottom - expected_top)
    horizontal_min = max(12, round(horizontal_span * 0.20))
    vertical_min = max(12, round(vertical_span * 0.20))
    inner_left = first_index_at_least(
        column_counts,
        expected_left - search_pad,
        expected_left + search_pad + 1,
        vertical_min,
    )
    inner_top = first_index_at_least(
        row_counts,
        expected_top - search_pad,
        expected_top + search_pad + 1,
        horizontal_min,
    )
    inner_right = last_index_at_least(
        column_counts,
        expected_right - search_pad,
        expected_right + search_pad + 1,
        vertical_min,
    )
    inner_bottom = last_index_at_least(
        row_counts,
        expected_bottom - search_pad,
        expected_bottom + search_pad + 1,
        horizontal_min,
    )
    if inner_left is None or inner_top is None or inner_right is None or inner_bottom is None:
        return None
    if inner_right <= inner_left or inner_bottom <= inner_top:
        return None
    return inner_left, inner_top, inner_right + 1, inner_bottom + 1


def detect_inner_safe_box(
    source: Image.Image,
    layout: dict[str, int],
    slot_box: tuple[int, int, int, int],
    chroma_key: tuple[int, int, int],
    chroma_threshold: float,
) -> tuple[tuple[int, int, int, int], str]:
    """Find the generated safe-area inner fill and return its box in sheet coordinates."""
    left, top, right, bottom = slot_box
    cell = source.crop(slot_box).convert("RGB")
    width, height = cell.size
    slot_w = source.width / int(layout["columns"])
    slot_h = source.height / int(layout["rows"])
    scale_x = slot_w / max(1, int(layout.get("cell_width") or round(slot_w)))
    scale_y = slot_h / max(1, int(layout.get("cell_height") or round(slot_h)))
    expected_left = round(int(layout.get("safe_margin_x", 0) or 0) * scale_x)
    expected_top = round(int(layout.get("safe_margin_y", 0) or 0) * scale_y)
    expected_right = width - expected_left
    expected_bottom = height - expected_top
    inner_pad = max(1, round(min(width, height) / 512 * DETECTED_SAFE_BOX_INNER_PAD))
    fallback = (
        left + expected_left + inner_pad,
        top + expected_top + inner_pad,
        left + expected_right - inner_pad,
        top + expected_bottom - inner_pad,
    )
    if expected_left <= 0 or expected_top <= 0:
        return fallback, "manifest"

    chroma_rect = detect_chroma_rect_in_slot(
        cell,
        chroma_key,
        expected_left=expected_left,
        expected_top=expected_top,
        expected_right=expected_right,
        expected_bottom=expected_bottom,
    )
    if chroma_rect is not None:
        inner_left = left + chroma_rect[0] + inner_pad
        inner_top = top + chroma_rect[1] + inner_pad
        inner_right = left + chroma_rect[2] - inner_pad
        inner_bottom = top + chroma_rect[3] - inner_pad
        if inner_right > inner_left and inner_bottom > inner_top:
            return (inner_left, inner_top, inner_right, inner_bottom), "detected-safe-area-inner-fill"

    search_pad = max(6, round(min(width, height) / 512 * SAFE_LINE_SEARCH_PAD))
    fill_box = detect_inner_fill_box(
        cell,
        expected_left=expected_left,
        expected_top=expected_top,
        expected_right=expected_right,
        expected_bottom=expected_bottom,
        search_pad=search_pad,
        chroma_key=chroma_key,
        chroma_threshold=chroma_threshold,
    )
    if fill_box is not None:
        inner_left = left + fill_box[0] + inner_pad
        inner_top = top + fill_box[1] + inner_pad
        inner_right = left + fill_box[2] - inner_pad
        inner_bottom = top + fill_box[3] - inner_pad
        if inner_right > inner_left and inner_bottom > inner_top:
            return (inner_left, inner_top, inner_right, inner_bottom), "detected-safe-area-inner-fill"

    row_scores, column_scores = safe_area_line_scores(
        cell,
        expected_left=expected_left,
        expected_top=expected_top,
        expected_right=expected_right,
        expected_bottom=expected_bottom,
    )

    horizontal_span = max(1, expected_right - expected_left)
    vertical_span = max(1, expected_bottom - expected_top)
    horizontal_min = max(20, round(horizontal_span * 0.45))
    vertical_min = max(20, round(vertical_span * 0.45))
    edge_clear_x = max(2, round(expected_left * 0.75))
    edge_clear_y = max(2, round(expected_top * 0.75))
    top_group = best_line_group(
        row_scores,
        expected=expected_top,
        search_pad=search_pad,
        minimum_score=horizontal_min,
        min_index=edge_clear_y,
    )
    bottom_group = best_line_group(
        row_scores,
        expected=expected_bottom - 1,
        search_pad=search_pad,
        minimum_score=horizontal_min,
        max_index=height - edge_clear_y,
    )
    left_group = best_line_group(
        column_scores,
        expected=expected_left,
        search_pad=search_pad,
        minimum_score=vertical_min,
        min_index=edge_clear_x,
    )
    right_group = best_line_group(
        column_scores,
        expected=expected_right - 1,
        search_pad=search_pad,
        minimum_score=vertical_min,
        max_index=width - edge_clear_x,
    )
    if not all((top_group, bottom_group, left_group, right_group)):
        return fallback, "manifest"

    inner_left = left + left_group[1] + inner_pad
    inner_top = top + top_group[1] + inner_pad
    inner_right = left + right_group[0] - inner_pad
    inner_bottom = top + bottom_group[0] - inner_pad
    if inner_right <= inner_left or inner_bottom <= inner_top:
        return fallback, "manifest"
    return (inner_left, inner_top, inner_right, inner_bottom), "detected-safe-area-line"


def detect_inner_safe_boxes(
    source: Image.Image,
    layout: dict[str, int],
    frame_count: int,
    chroma_key: tuple[int, int, int],
    chroma_threshold: float,
) -> dict[int, dict[str, object]]:
    return {
        index: {"box": list(box), "source": source_name}
        for index, slot_box in enumerate(slot_boxes(source, layout, frame_count))
        for box, source_name in [detect_inner_safe_box(source, layout, slot_box, chroma_key, chroma_threshold)]
    }


def remove_chroma_background_in_safe_boxes(
    image: Image.Image,
    safe_boxes: dict[int, dict[str, object]],
    chroma_key: tuple[int, int, int],
    chroma_threshold: float,
) -> Image.Image:
    rgba = image.convert("RGBA")
    for detected in safe_boxes.values():
        if not isinstance(detected, dict) or not isinstance(detected.get("box"), list) or len(detected["box"]) != 4:
            continue
        left, top, right, bottom = [int(value) for value in detected["box"]]
        left = max(0, min(rgba.width, left))
        top = max(0, min(rgba.height, top))
        right = max(left, min(rgba.width, right))
        bottom = max(top, min(rgba.height, bottom))
        if right <= left or bottom <= top:
            continue
        cleaned = remove_chroma_background(rgba.crop((left, top, right, bottom)), chroma_key, chroma_threshold)
        rgba.paste(cleaned, (left, top))
    return rgba


def erase_generated_cell_borders(sheet: Image.Image, layout: dict[str, int]) -> Image.Image:
    """Remove visible registration-guide lines before component extraction."""
    image = sheet.convert("RGBA")
    pixels = image.load()
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    slot_w = image.width / columns
    slot_h = image.height / rows
    border_pad = max(2, round(min(slot_w, slot_h) / 512 * GENERATED_CELL_BORDER_ERASE_PAD))

    def clear_column(x: int) -> None:
        left = max(0, x - border_pad)
        right = min(image.width, x + border_pad + 1)
        for yy in range(image.height):
            for xx in range(left, right):
                pixels[xx, yy] = (0, 0, 0, 0)

    def clear_row(y: int) -> None:
        top = max(0, y - border_pad)
        bottom = min(image.height, y + border_pad + 1)
        for yy in range(top, bottom):
            for xx in range(image.width):
                pixels[xx, yy] = (0, 0, 0, 0)

    for column in range(columns + 1):
        clear_column(round(column * image.width / columns))
    for row in range(rows + 1):
        clear_row(round(row * image.height / rows))

    return image


def erase_outside_safe_areas(
    image: Image.Image,
    layout: dict[str, int],
    safe_boxes: dict[int, dict[str, object]] | None = None,
) -> Image.Image:
    """Discard visible guide canvas outside each chroma-key inner safe area."""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    slot_w = rgba.width / columns
    slot_h = rgba.height / rows
    safe_x = layout.get("safe_margin_x")
    safe_y = layout.get("safe_margin_y")
    if safe_x is None or safe_y is None:
        return rgba
    scale_x = slot_w / max(1, int(layout.get("cell_width") or round(slot_w)))
    scale_y = slot_h / max(1, int(layout.get("cell_height") or round(slot_h)))
    safe_x_px = round(int(safe_x) * scale_x)
    safe_y_px = round(int(safe_y) * scale_y)
    for row in range(rows):
        top = round(row * rgba.height / rows)
        bottom = round((row + 1) * rgba.height / rows)
        for column in range(columns):
            index = row * columns + column
            left = round(column * rgba.width / columns)
            right = round((column + 1) * rgba.width / columns)
            detected = safe_boxes.get(index) if safe_boxes else None
            if isinstance(detected, dict) and isinstance(detected.get("box"), list) and len(detected["box"]) == 4:
                safe_left, safe_top, safe_right, safe_bottom = [int(value) for value in detected["box"]]
            else:
                safe_left = left + safe_x_px
                safe_top = top + safe_y_px
                safe_right = right - safe_x_px
                safe_bottom = bottom - safe_y_px
            for yy in range(top, bottom):
                for xx in range(left, right):
                    if not (safe_left <= xx < safe_right and safe_top <= yy < safe_bottom):
                        pixels[xx, yy] = (0, 0, 0, 0)
    return rgba


def is_guide_canvas_background(red: int, green: int, blue: int) -> bool:
    return min(red, green, blue) >= 232 and max(red, green, blue) - min(red, green, blue) <= 32


def erase_connected_guide_canvas_background(image: Image.Image, *, large_component_min_area: int | None = None) -> Image.Image:
    """Remove light neutral guide-canvas remnants that are connected to transparent background."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited = bytearray(width * height)
    for start in range(width * height):
        if visited[start]:
            continue
        x = start % width
        y = start // width
        red, green, blue, alpha = pixels[x, y]
        if alpha <= 16 or not is_guide_canvas_background(red, green, blue):
            visited[start] = 1
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        touches_transparent = False
        while stack:
            current = stack.pop()
            component.append(current)
            cx = current % width
            cy = current // width
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    touches_transparent = True
                    continue
                nred, ngreen, nblue, nalpha = pixels[nx, ny]
                if nalpha <= 16:
                    touches_transparent = True
                    continue
                if is_guide_canvas_background(nred, ngreen, nblue):
                    neighbor = ny * width + nx
                    if visited[neighbor]:
                        continue
                    visited[neighbor] = 1
                    stack.append(neighbor)
        is_large_background = large_component_min_area is not None and len(component) >= large_component_min_area
        if touches_transparent or is_large_background:
            for pixel_index in component:
                px = pixel_index % width
                py = pixel_index // width
                pixels[px, py] = (0, 0, 0, 0)
    return rgba


def clear_unused_slots(image: Image.Image, layout: dict[str, int], frame_count: int) -> Image.Image:
    """Make generated content in unused grid slots invisible to extraction."""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    capacity = int(layout["columns"]) * int(layout["rows"])
    if frame_count >= capacity:
        return rgba
    for left, top, right, bottom in slot_boxes(rgba, layout, capacity)[frame_count:]:
        for yy in range(top, bottom):
            for xx in range(left, right):
                pixels[xx, yy] = (0, 0, 0, 0)
    return rgba


def unused_slot_diagnostics(sheet: Image.Image, layout: dict[str, int], frame_count: int) -> list[dict[str, object]]:
    capacity = int(layout["columns"]) * int(layout["rows"])
    if frame_count >= capacity:
        return []
    diagnostics = []
    for index, crop_box in enumerate(slot_boxes(sheet, layout, capacity)[frame_count:], start=frame_count):
        frame = sheet.crop(crop_box).convert("RGBA")
        alpha = frame.getchannel("A")
        nontransparent = sum(alpha.histogram()[1:])
        bbox = frame.getbbox()
        diagnostics.append(
            {
                "slot": index + 1,
                "index": index,
                "crop_box": list(crop_box),
                "nontransparent_pixels": nontransparent,
                "bbox": list(bbox) if bbox else None,
            }
        )
    return diagnostics


def pad_to_size(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    rgba = image.convert("RGBA")
    if rgba.size == size:
        return rgba
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    output.alpha_composite(rgba, (0, 0))
    return output


def component_group_slot_image(
    source: Image.Image,
    components: list[dict[str, Any]],
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
) -> Image.Image:
    left, top, right, bottom = crop_box
    output = Image.new("RGBA", output_size, (0, 0, 0, 0))
    width, _height = source.size
    source_pixels = source.load()
    output_pixels = output.load()
    for component in components:
        for pixel_index in component["pixels"]:
            x = pixel_index % width
            y = pixel_index // width
            if left <= x < right and top <= y < bottom:
                output_pixels[x - left, y - top] = source_pixels[x, y]
    return output


def extract_component_frames(
    sheet: Image.Image,
    frame_count: int,
    layout: dict[str, int],
    crop_boxes: list[tuple[int, int, int, int]],
    output_size: tuple[int, int],
) -> list[Image.Image] | None:
    components = character_components(connected_components(sheet), sheet, layout)
    if not components:
        return None
    largest = max(component["area"] for component in components)
    centers = slot_centers(sheet, layout, frame_count)
    by_slot: list[list[dict[str, Any]]] = [[] for _ in range(frame_count)]
    for component in components:
        index = component_slot_index(component, centers)
        if index < frame_count:
            by_slot[index].append(component)

    seed_threshold = max(120, largest * 0.02)
    selected: list[dict[str, Any]] = []
    for slot_components in by_slot:
        if not slot_components:
            return None
        seed = max(slot_components, key=lambda component: component["area"])
        if seed["area"] < seed_threshold:
            return None
        selected.append(seed)

    groups: list[list[dict[str, Any]]] = [[] for _ in range(frame_count)]
    for seed in selected:
        index = component_slot_index(seed, centers)
        if index < frame_count:
            groups[index].append(seed)

    if any(not group for group in groups):
        return None

    seed_ids = {id(seed) for seed in selected}
    noise_threshold = max(12, largest * 0.002)
    for component in components:
        if id(component) in seed_ids:
            continue
        index = component_slot_index(component, centers)
        if index < frame_count:
            if component["area"] < noise_threshold and not component_near_seed(component, selected[index]):
                continue
            groups[index].append(component)

    return [
        component_group_slot_image(sheet, group, crop_boxes[index], output_size)
        for index, group in enumerate(groups)
    ]


def component_near_seed(component: dict[str, Any], seed: dict[str, Any], max_gap: int = 10) -> bool:
    left, top, right, bottom = component["bbox"]
    seed_left, seed_top, seed_right, seed_bottom = seed["bbox"]
    horizontal_gap = max(seed_left - right, left - seed_right, 0)
    vertical_gap = max(seed_top - bottom, top - seed_bottom, 0)
    return max(horizontal_gap, vertical_gap) <= max_gap


def guide_scale(sheet: Image.Image, layout: dict[str, int]) -> tuple[float, float]:
    cell_width = int(layout.get("cell_width") or 0)
    cell_height = int(layout.get("cell_height") or 0)
    if cell_width <= 0 or cell_height <= 0:
        return (sheet.width / layout["columns"], sheet.height / layout["rows"])
    return (
        (sheet.width // layout["columns"]) / cell_width,
        (sheet.height // layout["rows"]) / cell_height,
    )


def scaled_cell_box(index: int, layout: dict[str, int], scale: tuple[float, float], sheet: Image.Image) -> tuple[int, int, int, int]:
    return slot_boxes(sheet, layout, index + 1)[index]


def scaled_safe_box(crop_box: tuple[int, int, int, int], layout: dict[str, int], scale: tuple[float, float], state: dict[str, Any]) -> tuple[int, int, int, int] | None:
    safe_x = state.get("safe_margin_x")
    safe_y = state.get("safe_margin_y")
    if safe_x is None or safe_y is None:
        safe_x = layout.get("safe_margin_x")
        safe_y = layout.get("safe_margin_y")
    if safe_x is None or safe_y is None:
        return None
    left, top, right, bottom = crop_box
    return (
        left + round(int(safe_x) * scale[0]),
        top + round(int(safe_y) * scale[1]),
        right - round(int(safe_x) * scale[0]),
        bottom - round(int(safe_y) * scale[1]),
    )


def extract_slot_frames(
    sheet: Image.Image,
    frame_count: int,
    layout: dict[str, int],
    state: dict[str, Any],
    crop_boxes: list[tuple[int, int, int, int]],
    output_size: tuple[int, int],
) -> tuple[list[Image.Image], list[dict[str, object]]]:
    frames = []
    boxes = []
    scale = guide_scale(sheet, layout)
    for index in range(frame_count):
        crop_box = crop_boxes[index]
        safe = scaled_safe_box(crop_box, layout, scale, state)
        frames.append(pad_to_size(sheet.crop(crop_box), output_size))
        rel_safe = []
        if safe is not None:
            rel_safe = [safe[0] - crop_box[0], safe[1] - crop_box[1], safe[2] - crop_box[0], safe[3] - crop_box[1]]
        boxes.append(
            {
                "index": index,
                "crop_box": list(crop_box),
                "safe_box": list(safe or []),
                "safe_box_in_frame": rel_safe,
            }
        )
    return frames, boxes


def state_source(run_dir: Path | None, state: dict[str, Any]) -> Path:
    if state.get("source"):
        return resolve_path(str(state["source"]), run_dir)
    if run_dir is None:
        return Path("generated") / f"{state['name']}.png"
    return run_dir / "generated" / f"{state['name']}.png"


def guide_by_state(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    guides = manifest.get("registration_guides")
    if not isinstance(guides, list) or not guides:
        guides = manifest.get("layout_guides")
    if not isinstance(guides, list):
        return {}
    return {
        str(guide["state"]): guide
        for guide in guides
        if isinstance(guide, dict) and isinstance(guide.get("state"), str)
    }


def add_guide_safe_margins(layout: dict[str, int], guide: dict[str, Any] | None) -> dict[str, int]:
    if not guide:
        return layout
    updated = dict(layout)
    for source_key, target_key in (("width", "guide_width"), ("height", "guide_height")):
        if target_key not in updated and guide.get(source_key) is not None:
            updated[target_key] = int(guide[source_key])
    if "safe_margin_x" not in updated and guide.get("safe_margin_x") is not None:
        updated["safe_margin_x"] = int(guide["safe_margin_x"])
    if "safe_margin_y" not in updated and guide.get("safe_margin_y") is not None:
        updated["safe_margin_y"] = int(guide["safe_margin_y"])
    return updated


def validate_sheet_aspect(sheet: Image.Image, layout: dict[str, int], state_name: str, tolerance: float = 0.02) -> None:
    guide_width = int(layout.get("guide_width") or layout["columns"] * int(layout.get("cell_width") or 0))
    guide_height = int(layout.get("guide_height") or layout["rows"] * int(layout.get("cell_height") or 0))
    if guide_width <= 0 or guide_height <= 0:
        return
    guide_aspect = guide_width / guide_height
    sheet_aspect = sheet.width / sheet.height
    relative_delta = abs(sheet_aspect - guide_aspect) / guide_aspect
    if relative_delta > tolerance:
        raise SystemExit(
            f"{state_name} generated sheet aspect ratio {sheet.width}x{sheet.height} "
            f"({sheet_aspect:.4g}:1) does not match layout guide {guide_width}x{guide_height} "
            f"({guide_aspect:.4g}:1); regenerate the action sheet with the guide aspect preserved"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--run-dir")
    parser.add_argument("--action-id", help="Extract one action/state from the run.")
    parser.add_argument("--output-dir")
    parser.add_argument("--frame-size")
    parser.add_argument("--frame-count", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--format", choices=("png", "webp"), help="Accepted for compatibility; extracted frame files are always PNG.")
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
    output_dir = resolve_path(args.output_dir or paths.get("frames_dir", "frames"), base)
    requested_states = {item.strip() for item in args.states.split(",")} if args.states else None
    guides_by_state = guide_by_state(manifest)

    rows = []
    for state in settings["states"]:
        if requested_states and state["name"] not in requested_states:
            continue
        source = state_source(run_dir, state)
        if not source.is_file():
            raise SystemExit(f"missing grid sheet for {state['name']}: {source}")
        with Image.open(source) as opened:
            source_rgb = opened.convert("RGB")
            sheet = opened.convert("RGBA")
        frames: list[Image.Image] | None = None
        crop_boxes: list[dict[str, object]] = []
        used_method = args.method
        layout = add_guide_safe_margins(state_layout(state, int(state["frames"])), guides_by_state.get(str(state["name"])))
        validate_sheet_aspect(sheet, layout, str(state["name"]))
        safe_boxes = detect_inner_safe_boxes(source_rgb, layout, int(state["frames"]), key_rgb, float(chroma["threshold"]))
        sheet = remove_chroma_background_in_safe_boxes(sheet, safe_boxes, key_rgb, float(chroma["threshold"]))
        sheet = erase_generated_cell_borders(sheet, layout)
        sheet = erase_outside_safe_areas(sheet, layout, safe_boxes)
        slot_area = max(1, round((sheet.width / int(layout["columns"])) * (sheet.height / int(layout["rows"]))))
        sheet = erase_connected_guide_canvas_background(sheet, large_component_min_area=max(256, round(slot_area * 0.08)))
        unused_slots = unused_slot_diagnostics(sheet, layout, int(state["frames"]))
        sheet = clear_unused_slots(sheet, layout, int(state["frames"]))
        crop_box_values = slot_boxes(sheet, layout, int(state["frames"]))
        generated_frame_size = common_slot_size(crop_box_values)
        if args.method in {"auto", "components"}:
            frames = extract_component_frames(sheet, state["frames"], layout, crop_box_values, generated_frame_size)
            if frames is None and args.method == "components":
                raise SystemExit(f"could not extract {state['frames']} components from {source}")
            if frames is not None:
                used_method = "components"
        if frames is None:
            frames, crop_boxes = extract_slot_frames(sheet, state["frames"], layout, state, crop_box_values, generated_frame_size)
            used_method = "slots"

        state_dir = output_dir / state["name"]
        state_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for index, frame in enumerate(frames):
            target = state_dir / f"{index:03d}.png"
            frame.save(target, format="PNG")
            outputs.append(str(target))
        extracted_size = list(frames[0].size) if frames else []
        safe_box_sources = {
            str(box.get("source"))
            for box in safe_boxes.values()
            if isinstance(box, dict) and box.get("source") is not None
        }
        detected_sources = {"detected-safe-area-line", "detected-safe-area-inner-fill"}
        guide_erase_policy = (
            "detected-safe-area-inner-box"
            if safe_box_sources and safe_box_sources <= detected_sources
            else "manifest-safe-area-fallback"
            if safe_box_sources == {"manifest"}
            else "detected-safe-area-inner-box-with-manifest-fallback"
        )
        rows.append(
            {
                "state": state["name"],
                "source": str(source),
                "source_size": [sheet.width, sheet.height],
                "frames": outputs,
                "method": used_method,
                "layout": state["layout"],
                "extracted_frame_size": extracted_size,
                "extraction_size_policy": "preserve-generated-cell-size",
                "generated_cell_border_removed": True,
                "guide_erase_policy": guide_erase_policy,
                "detected_safe_boxes": safe_boxes,
                "unused_slots": unused_slots,
                "crop_boxes": crop_boxes,
            }
        )

    result = {
        "ok": True,
        "nominal_frame_size": [settings["frame_width"], settings["frame_height"]],
        "format": "png",
        "final_format": settings["format"],
        "chroma_key": chroma,
        "split_order": "left-to-right-top-to-bottom",
        "rows": rows,
    }
    write_json(output_dir / "frames-manifest.json", result)
    print(json.dumps({"ok": True, "frames_root": str(output_dir), "states": [row["state"] for row in rows]}, indent=2))


if __name__ == "__main__":
    main()
