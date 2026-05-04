#!/usr/bin/env python3
"""Shared helpers for deterministic animation-creator scripts."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
DEFAULT_FORMAT = "webp"
DEFAULT_CHROMA_KEY = "#00FF00"
BASE_REFERENCE_BACKGROUND = "#FFFFFF"
DEFAULT_WORKING_CELL_SIZE = (512, 512)
DEFAULT_SAFE_MARGIN_X = 30
DEFAULT_SAFE_MARGIN_Y = 24
DEFAULT_SAFE_MARGIN = DEFAULT_SAFE_MARGIN_X
MAX_RECOMMENDED_GRID_FRAMES = 16
MIN_FRAME_INSET = 5
CHROMA_ARTIFACT_THRESHOLD = 190.0
INTERNAL_CHROMA_HOLE_MAX_PIXELS = 128
CODEX_IMAGEGEN_MAX_ASPECT_RATIO = 3.0
CONNECTED_CHROMA_MIN_COMPONENT_AREA_RATIO = 0.05
CONNECTED_CHROMA_MIN_RECT_FILL = 0.35
CONNECTED_CHROMA_EDGE_BAND_RADIUS = 4
CONNECTED_CHROMA_SPILL_BAND_RADIUS = 2
BACKGROUND_EDGE_SAMPLE_BAND_RATIO = 0.08
BACKGROUND_COLOR_BUCKET_SIZE = 24
BACKGROUND_TIGHT_MARGIN = 4.0
BACKGROUND_LOOSE_MARGIN = 18.0
KEY_STRENGTH_MARGIN = 6.0


def load_json(path: Path) -> dict[str, Any]:
    with path.expanduser().resolve().open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"manifest must be a JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_size(raw: str | None, default: tuple[int, int]) -> tuple[int, int]:
    if not raw:
        return default
    match = re.fullmatch(r"\s*(\d+)x(\d+)\s*", raw.lower())
    if not match:
        raise SystemExit(f"invalid size '{raw}', expected WIDTHxHEIGHT")
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise SystemExit("width and height must be positive")
    return width, height


def parse_hex_color(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise SystemExit(f"invalid color '{value}', expected #RRGGBB")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def choose_chroma_key_for_image(path: Path, threshold: float = 96.0) -> dict[str, Any]:
    candidates = [
        (0, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
        (255, 255, 0),
        (255, 0, 0),
        (0, 0, 255),
    ]
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    sample: list[tuple[int, int, int]] = []
    step = max(1, min(image.size) // 96)
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            red, green, blue, alpha = image.getpixel((x, y))
            if alpha <= 16:
                continue
            if red > 245 and green > 245 and blue > 245:
                continue
            sample.append((red, green, blue))
    if not sample:
        sample = [(0, 0, 0)]
    best = max(candidates, key=lambda candidate: min(color_distance(r, g, b, candidate) for r, g, b in sample))
    return {"hex": rgb_to_hex(best), "rgb": list(best), "threshold": threshold}


def color_distance(
    red: int,
    green: int,
    blue: int,
    key: tuple[int, int, int],
) -> float:
    return math.sqrt((red - key[0]) ** 2 + (green - key[1]) ** 2 + (blue - key[2]) ** 2)


def is_chroma_artifact_color(
    red: int,
    green: int,
    blue: int,
    key: tuple[int, int, int],
    threshold: float,
) -> bool:
    if color_distance(red, green, blue, key) <= threshold:
        return True
    channels = (red, green, blue)
    key_max = max(key)
    if key_max <= 0:
        return False
    key_channels = [index for index, value in enumerate(key) if value >= key_max * 0.75]
    if not key_channels:
        return False
    artifact_values = [channels[index] for index in key_channels]
    if min(artifact_values) < 60 or max(artifact_values) - min(artifact_values) > 100:
        return False
    low_limit = min(artifact_values) * 0.60
    return all(channels[index] <= low_limit for index in range(3) if index not in key_channels)


def suppress_chroma_spill_pixel(
    red: int,
    green: int,
    blue: int,
    alpha: int,
    key: tuple[int, int, int],
    allowance: int = 0,
) -> tuple[int, int, int, int]:
    channels = [red, green, blue]
    key_max = max(key)
    if key_max <= 0:
        return red, green, blue, alpha
    key_channels = [index for index, value in enumerate(key) if value >= key_max * 0.75]
    non_key_channels = [index for index in range(3) if index not in key_channels]
    if not key_channels or not non_key_channels:
        return red, green, blue, alpha
    ceiling = max(channels[index] for index in non_key_channels) + allowance
    for index in key_channels:
        channels[index] = min(channels[index], ceiling)
    return channels[0], channels[1], channels[2], alpha


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "animation"


def resolve_path(path: str | Path, base: Path | None = None) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute() or base is None:
        return candidate.resolve()
    return (base / candidate).resolve()


def image_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


DEFAULT_PREVIEW_FRAME_DURATION_MS = 125


def default_states(frame_count: int, fps: float | None = None) -> list[dict[str, Any]]:
    state: dict[str, Any] = {"name": "animation", "row": 0, "frames": frame_count}
    if fps is not None:
        state["fps"] = fps
    return [state]


def round_up_to_multiple(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def validate_image_2_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise SystemExit("image size must be positive")
    aspect = max(width, height) / min(width, height)
    if aspect > CODEX_IMAGEGEN_MAX_ASPECT_RATIO:
        raise SystemExit(f"layout guide maximum aspect ratio is 3:1; got {width}x{height}")


def image_2_cell_size(columns: int, rows: int, nominal: tuple[int, int] = DEFAULT_WORKING_CELL_SIZE) -> tuple[int, int]:
    width = columns * nominal[0]
    height = rows * nominal[1]
    aspect = max(width, height) / min(width, height)
    if aspect > CODEX_IMAGEGEN_MAX_ASPECT_RATIO:
        raise SystemExit(f"layout aspect ratio must be at most 3:1 for Codex image generation; got {columns}x{rows}")
    validate_image_2_size(width, height)
    return nominal


def recommended_grid(frame_count: int) -> dict[str, Any]:
    if frame_count <= 0:
        raise SystemExit("frame count must be positive")
    if frame_count > MAX_RECOMMENDED_GRID_FRAMES:
        raise SystemExit(f"frame count must be {MAX_RECOMMENDED_GRID_FRAMES} or fewer")
    if frame_count <= 2:
        columns = frame_count
        rows = 1
    elif frame_count <= 4:
        columns = 2
        rows = 2
    elif frame_count <= 6:
        columns = 3
        rows = 2
    elif frame_count <= 8:
        columns = 4
        rows = 2
    elif frame_count == 9:
        columns = 3
        rows = 3
    elif frame_count <= 12:
        columns = 4
        rows = 3
    else:
        columns = 4
        rows = 4
    cell_width, cell_height = image_2_cell_size(columns, rows)
    cell_count = columns * rows
    return {
        "type": "grid",
        "order": "left-to-right-top-to-bottom",
        "columns": columns,
        "rows": rows,
        "frame_count": frame_count,
        "cell_count": cell_count,
        "used_slots": frame_count,
        "unused_slots": list(range(frame_count + 1, cell_count + 1)),
        "cell_width": cell_width,
        "cell_height": cell_height,
        "nominal_cell_width": DEFAULT_WORKING_CELL_SIZE[0],
        "nominal_cell_height": DEFAULT_WORKING_CELL_SIZE[1],
        "working_cell_size": [cell_width, cell_height],
        "recommended_max_frames": MAX_RECOMMENDED_GRID_FRAMES,
    }


def normalize_grid_layout(raw: Any, frame_count: int) -> dict[str, Any]:
    layout = recommended_grid(frame_count)
    if isinstance(raw, dict):
        columns = int(raw.get("columns", layout["columns"]))
        rows = int(raw.get("rows", layout["rows"]))
        cell_width = int(raw.get("cell_width", raw.get("frame_width", layout["cell_width"])))
        cell_height = int(raw.get("cell_height", raw.get("frame_height", layout["cell_height"])))
        if columns <= 0 or rows <= 0 or cell_width <= 0 or cell_height <= 0:
            raise SystemExit("grid layout columns, rows, and cell size must be positive")
        if columns * rows < frame_count:
            raise SystemExit(f"grid layout {columns}x{rows} cannot fit {frame_count} frames")
        layout.update(
            {
                "columns": columns,
                "rows": rows,
                "cell_width": cell_width,
                "cell_height": cell_height,
                "cell_count": columns * rows,
                "working_cell_size": [cell_width, cell_height],
            }
        )
    layout["frame_count"] = frame_count
    layout["used_slots"] = frame_count
    layout["unused_slots"] = list(range(frame_count + 1, int(layout["columns"]) * int(layout["rows"]) + 1))
    return layout


def manifest_settings(
    manifest: dict[str, Any] | None,
    *,
    frame_size: tuple[int, int] | None = None,
    frame_count: int | None = None,
    fps: float | None = None,
    output_format: str | None = None,
    require_states: bool = True,
) -> dict[str, Any]:
    manifest = manifest or {}
    animation = manifest.get("animation", {})
    if not isinstance(animation, dict):
        raise SystemExit("manifest.animation must be an object")

    raw_layout = animation.get("layout", manifest.get("layout"))
    raw_size = animation.get("frame_size", manifest.get("frame_size"))
    if isinstance(raw_size, list) and len(raw_size) == 2:
        size = (int(raw_size[0]), int(raw_size[1]))
    elif isinstance(raw_size, dict):
        size = (int(raw_size.get("width", 0)), int(raw_size.get("height", 0)))
    elif isinstance(raw_size, str):
        size = parse_size(raw_size, DEFAULT_WORKING_CELL_SIZE)
    else:
        size = DEFAULT_WORKING_CELL_SIZE
    if frame_size is not None:
        size = frame_size
    if size[0] <= 0 or size[1] <= 0:
        raise SystemExit("frame size must be positive")

    raw_count = animation.get("frame_count", manifest.get("frame_count"))
    if frame_count is not None:
        raw_count = frame_count
    count = int(raw_count) if raw_count is not None else None
    if count is not None and count <= 0:
        raise SystemExit("frame count must be positive")

    raw_fps = fps
    if raw_fps is None:
        raw_fps = animation.get("fps", manifest.get("fps"))
    resolved_fps = float(raw_fps) if raw_fps is not None else None
    if resolved_fps is not None and resolved_fps <= 0:
        raise SystemExit("fps must be positive")

    fmt = str(animation.get("format", manifest.get("format", output_format or DEFAULT_FORMAT)))
    if output_format is not None:
        fmt = output_format
    fmt = fmt.lower().lstrip(".")
    if fmt not in {"png", "webp"}:
        raise SystemExit("frame format must be png or webp")

    states = animation.get("states", manifest.get("states"))
    if states is None:
        if count is None:
            if not require_states:
                states = []
            else:
                raise SystemExit("frame count is required when no planned animation states are present")
        else:
            states = default_states(count, resolved_fps)
    if isinstance(states, dict):
        states = [{"name": name, **spec} for name, spec in states.items()]
    if not isinstance(states, list) or (require_states and not states):
        raise SystemExit("states must be a non-empty list or object")

    normalized_states: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        if isinstance(state, str):
            item = {"name": state}
        elif isinstance(state, dict):
            item = dict(state)
        else:
            raise SystemExit("each state must be a string or object")
        name = slugify(str(item.get("name", item.get("id", f"state-{index}"))))
        frame_actions = item.get("frame_actions")
        if not isinstance(frame_actions, list):
            frame_actions = item.get("beats")
        if not isinstance(frame_actions, list):
            frame_actions = []
        frame_actions = [str(beat) for beat in frame_actions]
        motion_beats = item.get("motion_beats")
        if not isinstance(motion_beats, list):
            motion_beats = [
                {"frame": beat_index + 1, "beat": beat}
                for beat_index, beat in enumerate(frame_actions)
            ]
        raw_frames = item.get("frames", item.get("frame_count", len(frame_actions) or count))
        if raw_frames is None:
            raise SystemExit(f"state {name} must define frames or frame actions")
        frames = int(raw_frames)
        if frames <= 0:
            raise SystemExit(f"state {name} frame count must be positive")
        layout = normalize_grid_layout(item.get("layout", raw_layout), frames)
        normalized_states.append(
            {
                "name": name,
                "row": int(item.get("row", index)),
                "frames": frames,
                "frame_count": frames,
                "frame_actions": frame_actions,
                "motion_beats": motion_beats,
                "action": item.get("action"),
                **({"fps": float(item["fps"])} if item.get("fps") is not None else ({"fps": resolved_fps} if resolved_fps is not None else {})),
                "source": item.get("source"),
                "layout": layout,
            }
        )
    resolved_count = count
    if resolved_count is None and normalized_states:
        resolved_count = max(int(state["frames"]) for state in normalized_states)
    resolved_layout = normalize_grid_layout(raw_layout, resolved_count) if resolved_count else None
    return {
        "frame_width": size[0],
        "frame_height": size[1],
        "frame_count": resolved_count or 0,
        "fps": resolved_fps,
        "format": fmt,
        "layout": resolved_layout,
        "states": normalized_states,
    }


def filter_states(settings: dict[str, Any], action_id: str | None) -> dict[str, Any]:
    if not action_id:
        return settings
    wanted = slugify(action_id)
    states = [state for state in settings["states"] if state["name"] == wanted]
    if not states:
        raise SystemExit(f"unknown action/state id: {action_id}")
    filtered = dict(settings)
    filtered["states"] = [{**states[0], "row": 0}]
    return filtered


def manifest_for_run(run_dir: str | Path | None, manifest: str | Path | None = None) -> Path | None:
    if manifest:
        return Path(manifest).expanduser().resolve()
    if run_dir:
        return Path(run_dir).expanduser().resolve() / "animation_manifest.json"
    return None


def chroma_settings(manifest: dict[str, Any] | None, override: str | None = None) -> dict[str, Any]:
    manifest = manifest or {}
    raw = override or manifest.get("chroma_key", DEFAULT_CHROMA_KEY)
    if isinstance(raw, dict):
        hex_value = str(raw.get("hex", DEFAULT_CHROMA_KEY))
        threshold = float(raw.get("threshold", 96.0))
    else:
        hex_value = str(raw)
        threshold = float(manifest.get("chroma_threshold", 96.0))
    rgb = parse_hex_color(hex_value)
    return {"hex": rgb_to_hex(rgb), "rgb": list(rgb), "threshold": threshold}


def remove_chroma_background(
    image: Image.Image,
    chroma_key: tuple[int, int, int],
    threshold: float,
) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    fallback_background = estimate_edge_background_color(rgba, chroma_key)
    background_thresholds = estimate_background_thresholds(rgba, fallback_background, threshold)
    strong_mask = bytearray(width * height)
    exact_mask = bytearray(width * height)
    distances = [0.0] * (width * height)
    key_strengths = [0.0] * (width * height)
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            dist = perceptual_background_distance((red, green, blue), fallback_background)
            strength = key_chroma_strength((red, green, blue), fallback_background)
            index = y * width + x
            distances[index] = dist
            key_strengths[index] = strength
            if dist <= background_thresholds["possible"]:
                strong_mask[index] = 1
            if dist <= background_thresholds["sure"]:
                exact_mask[index] = 1

    sure_background = connected_chroma_background_mask(
        strong_mask,
        exact_mask,
        width,
        height,
        distances=distances,
        key_strengths=key_strengths,
        background_thresholds=background_thresholds,
    )
    key_strength_thresholds = estimate_key_strength_thresholds(rgba, fallback_background, sure_background)
    background_labels, background_colors = label_background_components(rgba, sure_background)
    fallback_background_color = median_mask_color(rgba, sure_background) or fallback_background
    alpha_values = build_connected_chroma_alpha(
        rgba,
        sure_background,
        background_labels,
        background_colors,
        fallback_background_color,
        background_thresholds,
        key_strength_thresholds,
        strong_mask,
    )
    for y in range(height):
        for x in range(width):
            index = y * width + x
            red, green, blue, alpha = pixels[x, y]
            new_alpha = alpha_values[index]
            if new_alpha <= 0:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            pixels[x, y] = (red, green, blue, new_alpha)
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if 10 < alpha < 250:
                background_color = nearest_background_color(
                    background_labels,
                    background_colors,
                    width,
                    height,
                    x,
                    y,
                    fallback_background_color,
                )
                new_red, new_green, new_blue = restore_foreground_color((red, green, blue), background_color, alpha)
                new_red, new_green, new_blue = despill_background_edge((new_red, new_green, new_blue), background_color, strength=1.08)
                pixels[x, y] = (new_red, new_green, new_blue, alpha)
    despill_visible_background_direction(rgba, fallback_background_color)
    return rgba


def estimate_edge_background_color(image: Image.Image, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    width, height = image.size
    pixels = image.load()
    band = max(2, round(min(width, height) * BACKGROUND_EDGE_SAMPLE_BAND_RATIO))
    fallback_strength = key_chroma_strength(fallback, fallback)
    candidates: list[tuple[int, int, int]] = []
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for y in range(height):
        for x in range(width):
            if x >= band and y >= band and x < width - band and y < height - band:
                continue
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            color = (red, green, blue)
            saturation, value = rgb_saturation_value(color)
            dist_to_fallback = perceptual_background_distance(color, fallback)
            strength = key_chroma_strength(color, fallback)
            if saturation > 0.35 and value > 0.20 and (
                dist_to_fallback < 96.0 or (fallback_strength > 1.0 and strength > fallback_strength * 0.35)
            ):
                candidates.append(color)
            bucket = (
                red // BACKGROUND_COLOR_BUCKET_SIZE,
                green // BACKGROUND_COLOR_BUCKET_SIZE,
                blue // BACKGROUND_COLOR_BUCKET_SIZE,
            )
            buckets.setdefault(bucket, []).append((red, green, blue))
    if len(candidates) >= max(12, round((width + height) * 0.06)):
        clustered: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
        for red, green, blue in candidates:
            bucket = (
                red // BACKGROUND_COLOR_BUCKET_SIZE,
                green // BACKGROUND_COLOR_BUCKET_SIZE,
                blue // BACKGROUND_COLOR_BUCKET_SIZE,
            )
            clustered.setdefault(bucket, []).append((red, green, blue))
        return median_rgb(max(clustered.values(), key=len))
    if not buckets:
        return fallback
    estimated = median_rgb(max(buckets.values(), key=len))
    if perceptual_background_distance(estimated, fallback) < 144.0:
        return estimated
    saturation, value = rgb_saturation_value(estimated)
    if saturation > 0.35 and value > 0.20:
        return estimated
    return fallback


def estimate_background_thresholds(
    image: Image.Image,
    background_color: tuple[int, int, int],
    threshold: float,
) -> dict[str, float]:
    distances: list[float] = []
    for red, green, blue in sample_border_rgb(image):
        distance = perceptual_background_distance((red, green, blue), background_color)
        strength = key_chroma_strength((red, green, blue), background_color)
        background_strength = key_chroma_strength(background_color, background_color)
        if distance < 48.0 or (background_strength > 1.0 and strength > background_strength * 0.70):
            distances.append(distance)
    if not distances:
        possible = min(max(threshold, 56.0), 96.0)
        return {"sure": 18.0, "possible": possible}
    distances.sort()
    sure = max(10.0, min(42.0, percentile_value(distances, 0.99) + BACKGROUND_TIGHT_MARGIN))
    dynamic_loose = max(sure + 12.0, percentile_value(distances, 0.995) + 24.0, sure + BACKGROUND_LOOSE_MARGIN)
    if threshold > 0:
        possible = max(dynamic_loose, threshold * 0.65)
        possible = min(possible, threshold)
    else:
        possible = dynamic_loose
    possible = max(sure + 8.0, min(96.0, possible))
    return {"sure": sure, "possible": possible}


def rgb_saturation_value(color: tuple[int, int, int]) -> tuple[float, float]:
    high = max(color) / 255.0
    low = min(color) / 255.0
    saturation = 0.0 if high <= 0 else (high - low) / high
    return saturation, high


def sample_border_rgb(image: Image.Image) -> list[tuple[int, int, int]]:
    width, height = image.size
    pixels = image.load()
    band = max(2, round(min(width, height) * BACKGROUND_EDGE_SAMPLE_BAND_RATIO))
    samples: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if x >= band and y >= band and x < width - band and y < height - band:
                continue
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            samples.append((red, green, blue))
    return samples


def percentile_value(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return values[index]


def estimate_key_strength_thresholds(
    image: Image.Image,
    background_color: tuple[int, int, int],
    sure_background: bytearray | None = None,
) -> dict[str, float]:
    if sure_background is None:
        strengths = [key_chroma_strength(color, background_color) for color in sample_border_rgb(image)]
    else:
        width, height = image.size
        pixels = image.load()
        strengths = []
        step = max(1, round(math.sqrt(max(1, sum(sure_background))) / 128))
        for y in range(0, height, step):
            for x in range(0, width, step):
                if not sure_background[y * width + x]:
                    continue
                red, green, blue, alpha = pixels[x, y]
                if alpha > 16:
                    strengths.append(key_chroma_strength((red, green, blue), background_color))
    if not strengths:
        high = max(KEY_STRENGTH_MARGIN * 2.0, key_chroma_strength(background_color, background_color) * 0.50)
        return {"low": max(4.0, high * 0.20), "high": high}
    strengths.sort()
    high = max(KEY_STRENGTH_MARGIN * 2.0, percentile_value(strengths, 0.50) - 4.0)
    low = max(4.0, high * 0.20)
    return {"low": low, "high": high}


def median_rgb(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not colors:
        return DEFAULT_CHROMA_RGB
    mid = len(colors) // 2
    return (
        sorted(color[0] for color in colors)[mid],
        sorted(color[1] for color in colors)[mid],
        sorted(color[2] for color in colors)[mid],
    )


def perceptual_background_distance(
    color: tuple[int, int, int],
    background_color: tuple[int, int, int],
) -> float:
    lab_a = rgb_to_lab(color)
    lab_b = rgb_to_lab(background_color)
    return math.sqrt(sum((lab_a[index] - lab_b[index]) ** 2 for index in range(3)))


def rgb_to_lab(color: tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = [srgb_to_linear(channel / 255.0) for channel in color]
    x = red * 0.4124564 + green * 0.3575761 + blue * 0.1804375
    y = red * 0.2126729 + green * 0.7151522 + blue * 0.0721750
    z = red * 0.0193339 + green * 0.1191920 + blue * 0.9503041
    x /= 0.95047
    z /= 1.08883
    fx = lab_pivot(x)
    fy = lab_pivot(y)
    fz = lab_pivot(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def srgb_to_linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def lab_pivot(value: float) -> float:
    if value > 0.008856:
        return value ** (1.0 / 3.0)
    return 7.787 * value + 16.0 / 116.0


def chroma_channel_groups(chroma_key: tuple[int, int, int]) -> tuple[list[int], list[int]]:
    key_max = max(chroma_key)
    if key_max <= 0:
        return [1], [0, 2]
    key_channels = [index for index, value in enumerate(chroma_key) if value >= key_max * 0.75]
    if not key_channels:
        key_channels = [max(range(3), key=lambda index: chroma_key[index])]
    non_key_channels = [index for index in range(3) if index not in key_channels]
    return key_channels, non_key_channels


def chroma_excess(
    red: int,
    green: int,
    blue: int,
    key_channels: list[int],
    non_key_channels: list[int],
) -> int:
    channels = (red, green, blue)
    key_value = min(channels[index] for index in key_channels)
    non_key_value = max([channels[index] for index in non_key_channels] or [0])
    return key_value - non_key_value


def connected_chroma_background_mask(
    strong_mask: bytearray,
    exact_mask: bytearray,
    width: int,
    height: int,
    *,
    distances: list[float] | None = None,
    key_strengths: list[float] | None = None,
    background_thresholds: dict[str, float] | None = None,
) -> bytearray:
    visited = bytearray(width * height)
    sure = bytearray(width * height)
    frame_area = max(1, width * height)
    possible_threshold = float((background_thresholds or {}).get("possible", 56.0))
    sure_threshold = float((background_thresholds or {}).get("sure", 18.0))
    strength_high = 0.0
    if key_strengths:
        background_strengths = [key_strengths[index] for index, value in enumerate(exact_mask) if value]
        if background_strengths:
            background_strengths.sort()
            strength_high = percentile_value(background_strengths, 0.50) * 0.65
    for start, value in enumerate(strong_mask):
        if visited[start]:
            continue
        if not value:
            visited[start] = 1
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        touches_edge = False
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        exact_count = 0
        distance_sum = 0.0
        high_strength_count = 0
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            y = current // width
            touches_edge = touches_edge or x == 0 or y == 0 or x == width - 1 or y == height - 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            exact_count += 1 if exact_mask[current] else 0
            if distances is not None:
                distance_sum += distances[current]
            if key_strengths is not None and strength_high > 0.0 and key_strengths[current] >= strength_high:
                high_strength_count += 1
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                neighbor = ny * width + nx
                if visited[neighbor] or not strong_mask[neighbor]:
                    continue
                visited[neighbor] = 1
                stack.append(neighbor)
        area_ratio = len(component) / frame_area
        mean_distance = distance_sum / max(1, len(component)) if distances is not None else 0.0
        tight_ratio = exact_count / max(1, len(component))
        key_ratio = high_strength_count / max(1, len(component)) if strength_high > 0.0 else 0.0
        is_internal_hole = (
            not touches_edge
            and area_ratio < 0.05
            and mean_distance < possible_threshold * 0.75
            and tight_ratio > 0.65
        )
        if key_strengths is not None and key_ratio > 0.80 and tight_ratio > 0.50 and mean_distance < max(possible_threshold, sure_threshold + 8.0):
            is_internal_hole = is_internal_hole or (not touches_edge and area_ratio < 0.03)
        if touches_edge or is_internal_hole:
            for index in component:
                sure[index] = 1
    mark_small_exact_chroma_holes(exact_mask, sure, width, height)
    return sure


def mark_small_exact_chroma_holes(exact_mask: bytearray, sure: bytearray, width: int, height: int) -> None:
    visited = bytearray(width * height)
    max_hole_area = max(1, min(INTERNAL_CHROMA_HOLE_MAX_PIXELS, round(width * height * 0.02)))
    for start, value in enumerate(exact_mask):
        if visited[start]:
            continue
        if not value or sure[start]:
            visited[start] = 1
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        touches_edge = False
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            y = current // width
            touches_edge = touches_edge or x == 0 or y == 0 or x == width - 1 or y == height - 1
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                neighbor = ny * width + nx
                if visited[neighbor] or not exact_mask[neighbor] or sure[neighbor]:
                    continue
                visited[neighbor] = 1
                stack.append(neighbor)
        if not touches_edge and len(component) <= max_hole_area:
            for index in component:
                sure[index] = 1


def median_mask_color(image: Image.Image, mask: bytearray) -> tuple[int, int, int] | None:
    pixels = image.load()
    reds: list[int] = []
    greens: list[int] = []
    blues: list[int] = []
    width, height = image.size
    step = max(1, round(math.sqrt(max(1, sum(mask))) / 96))
    for y in range(0, height, step):
        for x in range(0, width, step):
            if not mask[y * width + x]:
                continue
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            reds.append(red)
            greens.append(green)
            blues.append(blue)
    if not reds:
        return None
    mid = len(reds) // 2
    return sorted(reds)[mid], sorted(greens)[mid], sorted(blues)[mid]


def label_background_components(
    image: Image.Image,
    mask: bytearray,
) -> tuple[list[int], list[tuple[int, int, int]]]:
    width, height = image.size
    pixels = image.load()
    labels = [-1] * (width * height)
    colors: list[tuple[int, int, int]] = []
    for start, value in enumerate(mask):
        if not value or labels[start] != -1:
            continue
        label = len(colors)
        stack = [start]
        labels[start] = label
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            y = current // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                neighbor = ny * width + nx
                if not mask[neighbor] or labels[neighbor] != -1:
                    continue
                labels[neighbor] = label
                stack.append(neighbor)
        reds: list[int] = []
        greens: list[int] = []
        blues: list[int] = []
        step = max(1, round(math.sqrt(len(component)) / 96))
        for pixel_index in component[::step]:
            x = pixel_index % width
            y = pixel_index // width
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            reds.append(red)
            greens.append(green)
            blues.append(blue)
        if reds:
            mid = len(reds) // 2
            colors.append((sorted(reds)[mid], sorted(greens)[mid], sorted(blues)[mid]))
        else:
            colors.append(DEFAULT_CHROMA_RGB)
    return labels, colors


def build_connected_chroma_alpha(
    image: Image.Image,
    sure_background: bytearray,
    background_labels: list[int],
    background_colors: list[tuple[int, int, int]],
    fallback_background_color: tuple[int, int, int],
    background_thresholds: dict[str, float],
    key_strength_thresholds: dict[str, float],
    possible_background: bytearray | None = None,
) -> bytearray:
    width, height = image.size
    alpha = bytearray([255]) * (width * height)
    for index, value in enumerate(sure_background):
        if value:
            alpha[index] = 0
    sure_image = Image.frombytes("L", (width, height), bytes(255 if value else 0 for value in sure_background))
    min_dim = min(width, height)
    edge_radius = max(CONNECTED_CHROMA_EDGE_BAND_RADIUS, round(min_dim / 70))
    spill_radius = max(3, round(min_dim / 100))
    alpha_band = sure_image.filter(ImageFilter.MaxFilter(edge_radius * 2 + 1)).tobytes()
    spill_band = sure_image.filter(ImageFilter.MaxFilter(spill_radius * 2 + 1)).tobytes()
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if sure_background[index] or not alpha_band[index]:
                continue
            if possible_background is not None and possible_background[index]:
                continue
            red, green, blue, source_alpha = pixels[x, y]
            if source_alpha <= 16:
                alpha[index] = 0
                continue
            background_color = nearest_background_color(
                background_labels,
                background_colors,
                width,
                height,
                x,
                y,
                fallback_background_color,
            )
            dist = perceptual_background_distance((red, green, blue), background_color)
            strength = key_chroma_strength((red, green, blue), background_color)
            high_strength_gate = max(key_strength_thresholds["high"] * 0.45, key_strength_thresholds["low"] + 1.0)
            if dist <= background_thresholds["sure"]:
                distance_remove_t = 1.0
            elif strength >= high_strength_gate:
                distance_remove_t = 1.0 - smoothstep(
                    background_thresholds["sure"],
                    max(background_thresholds["possible"] + 28.0, background_thresholds["sure"] + 1.0),
                    dist,
                )
            else:
                distance_remove_t = 0.0
            remove_t = distance_remove_t
            if spill_band[index]:
                excess_remove_t = (
                    key_strength_remove_factor((red, green, blue), background_color, key_strength_thresholds)
                    if strength >= high_strength_gate
                    else 0.0
                )
                remove_t = max(remove_t, excess_remove_t)
            remove_t = max(0.0, min(1.0, remove_t))
            alpha[index] = min(255, max(0, round(255 * (1.0 - remove_t))))
    alpha_image = Image.frombytes("L", (width, height), bytes(alpha))
    alpha_image = alpha_image.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.35))
    alpha = bytearray(alpha_image.tobytes())
    for index, value in enumerate(sure_background):
        if value:
            alpha[index] = 0
    return alpha


DEFAULT_CHROMA_RGB = parse_hex_color(DEFAULT_CHROMA_KEY)


def nearest_background_color(
    background_labels: list[int],
    background_colors: list[tuple[int, int, int]],
    width: int,
    height: int,
    x: int,
    y: int,
    fallback: tuple[int, int, int],
) -> tuple[int, int, int]:
    for radius in (1, 2, 4):
        left = max(0, x - radius)
        right = min(width, x + radius + 1)
        top = max(0, y - radius)
        bottom = min(height, y + radius + 1)
        for yy in range(top, bottom):
            for xx in range(left, right):
                label = background_labels[yy * width + xx]
                if 0 <= label < len(background_colors):
                    return background_colors[label]
    return fallback


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def restore_foreground_color(
    color: tuple[int, int, int],
    background_color: tuple[int, int, int],
    alpha: int,
) -> tuple[int, int, int]:
    alpha_f = max(0.04, min(0.98, alpha / 255.0))
    return tuple(
        max(0, min(255, round((color[index] - (1.0 - alpha_f) * background_color[index]) / alpha_f)))
        for index in range(3)
    )


def despill_chroma_edge(
    red: int,
    green: int,
    blue: int,
    key_channels: list[int],
    non_key_channels: list[int],
    allowance: int,
) -> tuple[int, int, int]:
    channels = [red, green, blue]
    non_key_value = max([channels[index] for index in non_key_channels] or [0])
    limit = min(255, non_key_value + allowance)
    for index in key_channels:
        channels[index] = min(channels[index], limit)
    return tuple(channels)


def key_strength_remove_factor(
    color: tuple[int, int, int],
    background_color: tuple[int, int, int],
    thresholds: dict[str, float],
) -> float:
    strength = key_chroma_strength(color, background_color)
    low = thresholds["low"]
    high = max(low + 1.0, thresholds["high"])
    return smoothstep(low, high, strength)


def key_chroma_strength(
    color: tuple[int, int, int],
    background_color: tuple[int, int, int],
) -> float:
    key_vector = chroma_vector(background_color)
    key_length = math.sqrt(sum(value * value for value in key_vector))
    if key_length < 1.0:
        return 0.0
    pixel_vector = chroma_vector(color)
    return sum(pixel_vector[index] * key_vector[index] for index in range(3)) / key_length


def chroma_vector(color: tuple[int, int, int]) -> tuple[float, float, float]:
    mean = sum(color) / 3.0
    return color[0] - mean, color[1] - mean, color[2] - mean


def despill_background_edge(
    color: tuple[int, int, int],
    background_color: tuple[int, int, int],
    strength: float = 0.72,
) -> tuple[int, int, int]:
    color_gray = sum(color) / 3.0
    background_vector = chroma_vector(background_color)
    background_length = math.sqrt(sum(value * value for value in background_vector))
    if background_length < 1.0:
        return color
    color_vector = chroma_vector(color)
    unit = tuple(value / background_length for value in background_vector)
    spill = sum(color_vector[index] * unit[index] for index in range(3))
    if spill <= 0:
        return color
    spill_scale = max(0.0, min(1.25, strength))
    cleaned = [
        color_gray + color_vector[index] - spill_scale * spill * unit[index]
        for index in range(3)
    ]
    return tuple(max(0, min(255, round(value))) for value in cleaned)


def despill_visible_background_direction(image: Image.Image, background_color: tuple[int, int, int]) -> None:
    width, height = image.size
    pixels = image.load()
    threshold = max(24.0, key_chroma_strength(background_color, background_color) * 0.16)
    exterior = exterior_transparent_mask(image)
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha <= 16:
                continue
            if alpha >= 250 and not touches_exterior_transparency(exterior, width, height, x, y):
                continue
            color = (red, green, blue)
            if key_chroma_strength(color, background_color) < threshold:
                continue
            new_red, new_green, new_blue = despill_background_edge(color, background_color, strength=1.08)
            pixels[x, y] = (new_red, new_green, new_blue, alpha)


def touches_exterior_transparency(exterior: bytearray, width: int, height: int, x: int, y: int) -> bool:
    radius = max(2, round(min(width, height) * 0.018))
    for yy in range(max(0, y - radius), min(height, y + radius + 1)):
        for xx in range(max(0, x - radius), min(width, x + radius + 1)):
            if exterior[yy * width + xx]:
                return True
    return False


def exterior_transparent_mask(image: Image.Image) -> bytearray:
    width, height = image.size
    pixels = image.load()
    exterior = bytearray(width * height)
    stack: list[int] = []
    for x in range(width):
        for y in (0, height - 1):
            red, green, blue, alpha = pixels[x, y]
            index = y * width + x
            if alpha <= 16 and not exterior[index]:
                exterior[index] = 1
                stack.append(index)
    for y in range(height):
        for x in (0, width - 1):
            red, green, blue, alpha = pixels[x, y]
            index = y * width + x
            if alpha <= 16 and not exterior[index]:
                exterior[index] = 1
                stack.append(index)
    while stack:
        current = stack.pop()
        x = current % width
        y = current // width
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            neighbor = ny * width + nx
            if exterior[neighbor]:
                continue
            red, green, blue, alpha = pixels[nx, ny]
            if alpha > 16:
                continue
            exterior[neighbor] = 1
            stack.append(neighbor)
    return exterior


def suppress_chroma_spill_components(
    image: Image.Image,
    chroma_key: tuple[int, int, int],
    threshold: float,
    *,
    remove_internal_holes: bool = True,
) -> None:
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    for start in range(width * height):
        if visited[start]:
            continue
        x = start % width
        y = start // width
        red, green, blue, alpha = pixels[x, y]
        if alpha <= 16 or not is_chroma_artifact_color(red, green, blue, chroma_key, threshold):
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
                if is_chroma_artifact_color(nred, ngreen, nblue, chroma_key, threshold):
                    neighbor = ny * width + nx
                    if visited[neighbor]:
                        continue
                    visited[neighbor] = 1
                    stack.append(neighbor)
        if touches_transparent:
            for pixel_index in component:
                px = pixel_index % width
                py = pixel_index // width
                pixels[px, py] = suppress_chroma_spill_pixel(*pixels[px, py], chroma_key)
        elif remove_internal_holes and len(component) <= INTERNAL_CHROMA_HOLE_MAX_PIXELS:
            for pixel_index in component:
                px = pixel_index % width
                py = pixel_index // width
                pixels[px, py] = (0, 0, 0, 0)


def alpha_nonzero_count(image: Image.Image) -> int:
    if image.mode in {"1", "L", "I", "I;16", "F"}:
        channel = image.convert("L")
    elif "A" in image.getbands():
        channel = image.getchannel("A")
    else:
        return image.width * image.height
    return sum(channel.histogram()[1:])


def edge_alpha_count(image: Image.Image, margin: int) -> int:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    width, height = alpha.size
    clamped = max(0, min(margin, width, height))
    if clamped == 0:
        return 0
    total = 0
    for box in (
        (0, 0, width, clamped),
        (0, height - clamped, width, height),
        (0, 0, clamped, height),
        (width - clamped, 0, width, height),
    ):
        total += alpha_nonzero_count(alpha.crop(box))
    return total


def chroma_adjacent_count(
    image: Image.Image,
    chroma_key: tuple[int, int, int] | None,
    threshold: float,
) -> int:
    if chroma_key is None:
        return 0
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited = bytearray(width * height)
    exterior_transparent = exterior_transparent_mask(rgba)
    count = 0
    for start in range(width * height):
        if visited[start]:
            continue
        x = start % width
        y = start // width
        red, green, blue, alpha = pixels[x, y]
        if alpha <= 16 or not is_chroma_artifact_color(red, green, blue, chroma_key, threshold):
            visited[start] = 1
            continue
        stack = [start]
        visited[start] = 1
        component_size = 0
        touches_transparent = False
        while stack:
            current = stack.pop()
            component_size += 1
            cx = current % width
            cy = current // width
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    touches_transparent = True
                    continue
                nred, ngreen, nblue, nalpha = pixels[nx, ny]
                if nalpha <= 16 and exterior_transparent[ny * width + nx]:
                    touches_transparent = True
                    continue
                if is_chroma_artifact_color(nred, ngreen, nblue, chroma_key, threshold):
                    neighbor = ny * width + nx
                    if not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)
        if touches_transparent:
            count += component_size
    return count


def fit_to_frame(image: Image.Image, size: tuple[int, int], padding: int = DEFAULT_SAFE_MARGIN) -> Image.Image:
    rgba = image.convert("RGBA")
    target = Image.new("RGBA", size, (0, 0, 0, 0))
    bbox = rgba.getbbox()
    if bbox is None:
        return target
    sprite = rgba.crop(bbox)
    inset = max(MIN_FRAME_INSET, padding)
    max_width = max(1, size[0] - inset * 2)
    max_height = max(1, size[1] - inset * 2)
    scale = min(max_width / sprite.width, max_height / sprite.height, 1.0)
    if scale != 1.0:
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
            Image.Resampling.LANCZOS,
        )
    left = (size[0] - sprite.width) // 2
    top = (size[1] - sprite.height) // 2
    target.alpha_composite(sprite, (left, top))
    return target


def checker(size: tuple[int, int], square: int = 16) -> Image.Image:
    image = Image.new("RGB", size, "#ffffff")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], square):
        for x in range(0, size[0], square):
            if (x // square + y // square) % 2:
                draw.rectangle((x, y, x + square - 1, y + square - 1), fill="#e8e8e8")
    return image


def draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: str,
    dash: int = 8,
    gap: int = 6,
) -> None:
    x1, y1 = start
    x2, y2 = end
    if x1 == x2:
        for y in range(min(y1, y2), max(y1, y2), dash + gap):
            draw.line((x1, y, x2, min(y + dash, max(y1, y2))), fill=fill)
    elif y1 == y2:
        for x in range(min(x1, x2), max(x1, x2), dash + gap):
            draw.line((x, y1, min(x + dash, max(x1, x2)), y2), fill=fill)
    else:
        raise ValueError("only horizontal or vertical dashed lines are supported")


def locate_frame_files(root: Path, state: str) -> list[Path]:
    candidates = [root / state, root / "frames" / state]
    for candidate in candidates:
        files = image_files(candidate)
        if files:
            return files
    patterns = [f"{state}_*", f"{state}-*", "frame_*", "frame-*"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p for p in root.glob(pattern) if p.suffix.lower() in IMAGE_SUFFIXES)
    return sorted(set(files))


def load_frames_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "frames-manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def frame_manifest_rows(root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_frames_manifest(root)
    rows = manifest.get("rows", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["state"]): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("state"), str)
    }


def frame_size_from_manifest(row: dict[str, Any]) -> tuple[int, int] | None:
    raw = row.get("extracted_frame_size") or row.get("frame_size")
    if isinstance(raw, list) and len(raw) == 2:
        width, height = int(raw[0]), int(raw[1])
        if width > 0 and height > 0:
            return (width, height)
    if isinstance(raw, dict):
        width, height = int(raw.get("width", 0)), int(raw.get("height", 0))
        if width > 0 and height > 0:
            return (width, height)
    return None


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as opened:
        return (opened.width, opened.height)
