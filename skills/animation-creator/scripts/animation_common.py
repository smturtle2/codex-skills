#!/usr/bin/env python3
"""Shared helpers for deterministic animation-creator scripts."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

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
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha and color_distance(red, green, blue, chroma_key) <= threshold:
                pixels[x, y] = (0, 0, 0, 0)
    suppress_chroma_spill_components(rgba, chroma_key, CHROMA_ARTIFACT_THRESHOLD)
    return rgba


def suppress_chroma_spill_components(
    image: Image.Image,
    chroma_key: tuple[int, int, int],
    threshold: float,
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
        elif len(component) <= INTERNAL_CHROMA_HOLE_MAX_PIXELS:
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
                if nalpha <= 16:
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
