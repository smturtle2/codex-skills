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
DEFAULT_WORKING_CELL_SIZE = (512, 512)
DEFAULT_SAFE_MARGIN = 28
MAX_RECOMMENDED_GRID_FRAMES = 16
MIN_FRAME_INSET = 5
CHROMA_ARTIFACT_THRESHOLD = 190.0


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
    low_limit = min(artifact_values) * 0.75
    return all(channels[index] <= low_limit for index in range(3) if index not in key_channels)


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


def default_states(frame_count: int, fps: float = 8) -> list[dict[str, Any]]:
    return [{"name": "animation", "row": 0, "frames": frame_count, "fps": fps}]


def recommended_grid(frame_count: int) -> dict[str, Any]:
    if frame_count <= 0:
        raise SystemExit("frame count must be positive")
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
    elif frame_count <= 16:
        columns = 4
        rows = 4
    else:
        columns = 4
        rows = math.ceil(frame_count / columns)
    return {
        "type": "grid",
        "order": "left-to-right-top-to-bottom",
        "columns": columns,
        "rows": rows,
        "frame_count": frame_count,
        "cell_width": DEFAULT_WORKING_CELL_SIZE[0],
        "cell_height": DEFAULT_WORKING_CELL_SIZE[1],
        "working_cell_size": list(DEFAULT_WORKING_CELL_SIZE),
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
                "working_cell_size": [cell_width, cell_height],
            }
        )
    layout["frame_count"] = frame_count
    return layout


def manifest_settings(
    manifest: dict[str, Any] | None,
    *,
    frame_size: tuple[int, int] | None = None,
    frame_count: int | None = None,
    fps: float | None = None,
    output_format: str | None = None,
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
        size = parse_size(raw_size, (512, 512))
    else:
        size = DEFAULT_WORKING_CELL_SIZE
    if frame_size is not None:
        size = frame_size
    if size[0] <= 0 or size[1] <= 0:
        raise SystemExit("frame size must be positive")

    count = int(animation.get("frame_count", manifest.get("frame_count", frame_count or 6)))
    if frame_count is not None:
        count = frame_count
    if count <= 0:
        raise SystemExit("frame count must be positive")

    resolved_fps = float(animation.get("fps", manifest.get("fps", fps or 8)))
    if fps is not None:
        resolved_fps = fps
    if resolved_fps <= 0:
        raise SystemExit("fps must be positive")

    fmt = str(animation.get("format", manifest.get("format", output_format or DEFAULT_FORMAT)))
    if output_format is not None:
        fmt = output_format
    fmt = fmt.lower().lstrip(".")
    if fmt not in {"png", "webp"}:
        raise SystemExit("frame format must be png or webp")

    states = animation.get("states", manifest.get("states"))
    if states is None:
        states = default_states(count, resolved_fps)
    if isinstance(states, dict):
        states = [{"name": name, **spec} for name, spec in states.items()]
    if not isinstance(states, list) or not states:
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
        frames = int(item.get("frames", item.get("frame_count", count)))
        layout = normalize_grid_layout(item.get("layout", raw_layout), frames)
        normalized_states.append(
            {
                "name": name,
                "row": int(item.get("row", index)),
                "frames": frames,
                "fps": float(item.get("fps", resolved_fps)),
                "source": item.get("source"),
                "layout": layout,
            }
        )
    return {
        "frame_width": size[0],
        "frame_height": size[1],
        "frame_count": count,
        "fps": resolved_fps,
        "format": fmt,
        "layout": normalize_grid_layout(raw_layout, count),
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
    remove_chroma_artifact_components(rgba, chroma_key, CHROMA_ARTIFACT_THRESHOLD)
    return rgba


def remove_chroma_artifact_components(
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
    data = rgba.tobytes()
    count = 0
    for index in range(0, len(data), 4):
        red, green, blue, alpha = data[index : index + 4]
        if alpha > 16 and color_distance(red, green, blue, chroma_key) <= threshold:
            count += 1
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
