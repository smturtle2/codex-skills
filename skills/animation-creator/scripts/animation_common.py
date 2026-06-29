#!/usr/bin/env python3
"""Shared helpers for deterministic animation-creator scripts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
DEFAULT_FORMAT = "webp"
DEFAULT_WORKING_CELL_SIZE = (362, 362)
DEFAULT_SAFE_MARGIN_X = 30
DEFAULT_SAFE_MARGIN_Y = 24
DEFAULT_SAFE_MARGIN = DEFAULT_SAFE_MARGIN_X
MIN_FRAME_INSET = 5
CODEX_IMAGEGEN_MAX_ASPECT_RATIO = 3.0
CODEX_IMAGEGEN_GUIDE_MAX_EDGE = 1448
FIXED_GUIDE_COLUMNS = 4
FIXED_GUIDE_ROWS = 3
MAX_RECOMMENDED_GRID_FRAMES = FIXED_GUIDE_COLUMNS * FIXED_GUIDE_ROWS


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


def round_up_to_multiple(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def validate_image_2_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise SystemExit("image size must be positive")
    aspect = max(width, height) / min(width, height)
    if aspect > CODEX_IMAGEGEN_MAX_ASPECT_RATIO:
        raise SystemExit(f"layout guide maximum aspect ratio is 3:1; got {width}x{height}")


def image_2_cell_size(columns: int, rows: int, nominal: tuple[int, int] = DEFAULT_WORKING_CELL_SIZE) -> tuple[int, int]:
    cell_size = min(nominal[0], nominal[1], CODEX_IMAGEGEN_GUIDE_MAX_EDGE // max(columns, rows))
    width = columns * cell_size
    height = rows * cell_size
    aspect = max(width, height) / min(width, height)
    if aspect > CODEX_IMAGEGEN_MAX_ASPECT_RATIO:
        raise SystemExit(f"layout aspect ratio must be at most 3:1 for Codex image generation; got {columns}x{rows}")
    validate_image_2_size(width, height)
    return (cell_size, cell_size)


def recommended_grid(frame_count: int) -> dict[str, Any]:
    if frame_count <= 0:
        raise SystemExit("frame count must be positive")
    if frame_count > MAX_RECOMMENDED_GRID_FRAMES:
        raise SystemExit(f"frame count must be {MAX_RECOMMENDED_GRID_FRAMES} or fewer")
    columns = FIXED_GUIDE_COLUMNS
    rows = FIXED_GUIDE_ROWS
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
        raw_cell_width = int(raw.get("cell_width", raw.get("frame_width", layout["cell_width"])))
        raw_cell_height = int(raw.get("cell_height", raw.get("frame_height", layout["cell_height"])))
        if raw_cell_width <= 0 or raw_cell_height <= 0:
            raise SystemExit("grid layout cell size must be positive")
        cell_width, cell_height = image_2_cell_size(
            int(layout["columns"]),
            int(layout["rows"]),
            (raw_cell_width, raw_cell_height),
        )
        layout.update(
            {
                "cell_width": cell_width,
                "cell_height": cell_height,
                "cell_count": int(layout["columns"]) * int(layout["rows"]),
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
        if not require_states:
            states = []
        else:
            raise SystemExit("planned animation states are required")
    if not isinstance(states, list) or (require_states and not states):
        raise SystemExit("states must be a non-empty list")

    normalized_states: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        if isinstance(state, dict):
            item = dict(state)
        else:
            raise SystemExit("each state must be an object")
        name = slugify(str(item.get("name", item.get("id", f"state-{index}"))))
        frame_actions = item.get("frame_actions")
        if not isinstance(frame_actions, list) or not frame_actions:
            raise SystemExit(f"state {name} must define non-empty frame_actions")
        frame_actions = [str(beat) for beat in frame_actions]
        motion_beats = item.get("motion_beats")
        if not isinstance(motion_beats, list):
            motion_beats = [
                {"frame": beat_index + 1, "beat": beat}
                for beat_index, beat in enumerate(frame_actions)
            ]
        frames = len(frame_actions)
        raw_frames = item.get("frames", item.get("frame_count"))
        if raw_frames is not None and int(raw_frames) != frames:
            raise SystemExit(f"state {name} frames must match frame_actions length")
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
    elif resolved_count is not None and normalized_states:
        actual_count = max(int(state["frames"]) for state in normalized_states)
        if resolved_count != actual_count:
            raise SystemExit("animation.frame_count must match the longest state frame_actions length")
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
