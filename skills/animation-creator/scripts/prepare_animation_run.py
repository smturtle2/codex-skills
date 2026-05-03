#!/usr/bin/env python3
"""Create a manifest-driven animation run folder and layout guides."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from animation_common import (
    BASE_REFERENCE_BACKGROUND,
    DEFAULT_SAFE_MARGIN_X,
    DEFAULT_SAFE_MARGIN_Y,
    DEFAULT_WORKING_CELL_SIZE,
    MAX_RECOMMENDED_GRID_FRAMES,
    choose_chroma_key_for_image,
    chroma_settings,
    draw_dashed_line,
    load_json,
    manifest_settings,
    parse_size,
    recommended_grid,
    slugify,
    validate_image_2_size,
    write_json,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def resolve_project_path(raw: str, project_root: Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_png_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        opened.convert("RGBA").save(target, format="PNG")


def base_prompt(
    *,
    character_name: str,
    character_prompt: str,
    frame_size: tuple[int, int],
    safe_margin: tuple[int, int],
) -> str:
    safe_width = max(1, frame_size[0] - safe_margin[0] * 2)
    safe_height = max(1, frame_size[1] - safe_margin[1] * 2)
    return f"""Create one clean full-body canonical reference image for an animation character named {character_name}.

Character: {character_prompt or "an original character suitable for animation"}.

Use this prompt as an authoritative animation-production spec. The result will become the single identity reference for every generated animation frame.

Design contract:
- Make one compact, readable whole-body character with a clear silhouette, stable proportions, simple face, limited palette, and details that remain legible when reused across animation cells.
- Design the character to fit comfortably inside a {frame_size[0]}x{frame_size[1]} animation layout cell with {safe_margin[0]}px horizontal and {safe_margin[1]}px vertical safe margins, leaving an effective safe area of {safe_width}x{safe_height}.
- Keep the full body scaled for that safe area: no oversized head, antenna, hands, feet, hair, clothing, or props should require touching the future animation cell edge.
- Prefer clean shape design, flat or lightly cel-shaded forms, and consistent outline/edge treatment over complex rendering.
- Do not expand the request into polished illustration, painterly character art, anime key art, 3D render, vector mascot, glossy app icon, realistic portrait, marketing artwork, or a scene.
- Do not add new props, accessories, symbols, logos, text, or environment details unless explicitly requested in the character description.
- Keep the pose neutral and animation-ready: centered, balanced, full body visible, arms and legs readable, no cropped parts, no extreme perspective, and no motion effects.

Output a single centered full-body character pose on a perfectly flat white background using {BASE_REFERENCE_BACKGROUND}. The character must be fully visible, readable, and suitable as the canonical identity source for generating consistent animation frames in the described layout cell. Do not include scenery, text, labels, borders, ground planes, floors, cast shadows, contact shadows, oval floor shadows, landing marks, glows, detached effects, or extra props not requested."""


def action_prompt(
    *,
    action_id: str,
    action: str,
    character_name: str,
    frames: int,
    frame_size: tuple[int, int],
    layout: dict[str, object],
    frame_actions: list[str],
    chroma: dict[str, object],
    chroma_ready: bool = True,
    registration_guide_ready: bool = False,
) -> str:
    chroma_hex = str(chroma["hex"])
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    cell_width = int(layout["cell_width"])
    cell_height = int(layout["cell_height"])
    guide_width = columns * cell_width
    guide_height = rows * cell_height
    aspect = guide_width / guide_height
    chroma_background_requirement = (
        f"- Fill only the inside of each blue safe-area rectangle with chroma key {chroma_hex}, then draw the character pose on that chroma background."
        if chroma_ready
        else "- This is a pre-base planning prompt. Do not use it for final action generation until the canonical base is recorded and this prompt is regenerated with the selected chroma-key background."
    )
    registration_guide_instruction = (
        "\n".join(
            [
                "- Edit the attached registration guide into the animation action sheet.",
                "- Keep unchanged: canvas size, grid layout, black cell borders, blue safe-area rectangles, and neutral background outside the blue rectangles.",
                "- Remove from the generated result: gray dashed centerlines and faint guide characters.",
                "- Use the attached canonical base only for character identity.",
            ]
        )
        if registration_guide_ready
        else "- After the canonical base is recorded, a registration guide may be attached to show the base character's consistent slot placement."
    )
    return f"""Create one animation frame grid for {character_name} performing `{action_id}`.

{registration_guide_instruction}
Use the attached canonical base image as the character identity source. Follow the grid specification below for frame count, slot order, centering, and safe padding.

Identity lock:
- Do not redesign the character.
- Preserve the same head shape, face, proportions, silhouette, markings, palette, outfit, materials, and props from the canonical base.
- Change pose, expression, and action timing for this action: {action}.

Motion sequence instructions:
Frame labels below are text-only ordering instructions for the generator. They are the final audited result of a sequential one-beat-at-a-time planning pass: missing transition beats were added, redundant duplicate beats were removed, and the remaining beats are intended to play as one continuous motion. Use them to map each pose to the correct slot, but never draw frame numbers or frame labels in the image.
{format_frame_actions(frame_actions)}

Animation continuity contract:
- Treat these as consecutive animation frames, not separate pose studies or unrelated character variations.
- Each frame must visibly continue from the immediately previous frame and lead into the immediately next frame. Do not skip the physical transition implied by adjacent frame notes.
- Keep the same camera distance, character scale, line weight, rendering detail, and facing direction across all frames.
- Keep the character's full-body height, head size, torso size, and limb thickness visually identical in every slot; do not shrink or enlarge any frame to fit the pose.
- Preserve a smooth visual motion path from frame to frame; the character must not teleport, suddenly grow, shrink, flip direction, or jump to a new camera framing.
- Anchor the character to the same registration point in every slot: keep the midpoint between the feet at the same x/y position, and keep the pelvis and torso center aligned to the same vertical centerline unless the listed motion explicitly requires body travel.
- Make every frame a natural in-between or key pose between the previous and next listed frame actions, with consistent limb arcs, balance, weight shift, and follow-through.
- Space the poses so playback feels smooth when played in sequence: avoid abrupt pose gaps, strobing changes, frozen duplicate frames, or uneven timing unless the action explicitly requires a sharp accent.
- Avoid redundant pose copies: adjacent frames should not be visually identical unless the listed motion beat explicitly calls for a hold.
- Use subtle easing through anticipation, acceleration, deceleration, overshoot, and settle so the motion reads as animated rather than as unrelated snapshots.
- For any action with body travel or vertical motion, follow one invisible motion arc inside the slots. Show the motion only through pose and body position; do not draw floor cues.
- Keep the final frame close enough to the first frame for a clean loop when this action loops, with consistent scale, facing, and slot placement.

Output exactly {frames} separate full-body animation frames as a {columns}x{rows} animation frame grid. Read and fill frames left-to-right across each row, then top-to-bottom. Preserve a {aspect:.4g}:1 overall grid aspect ratio with equal-size {columns}x{rows} slot proportions.

Edit instructions:
- Keep the output as a {columns}x{rows} registration-guide sheet, read left-to-right then top-to-bottom.
- Keep black cell borders and blue safe-area rectangles visible.
- Remove gray dashed centerlines and faint guide characters from the generated result.
- Fill each requested slot with exactly one full-body pose matching the corresponding numbered motion instruction above.
- Keep each pose fully inside its blue safe-area rectangle.
{chroma_background_requirement}
- The output must contain only the edited registration guide layout, chroma-key safe-area backgrounds, and character artwork. The words "Frame 1", "Frame 2", and other frame labels are prompt instructions only and must not appear visually. Do not draw sequence numbers, circles, labels, captions, markers, UI badges, text, extra guide marks, center dashed lines, center marks, ghost characters, or watermarks in any slot.
- Do not include any ground plane, floor line, cast shadow, contact shadow, oval floor shadow, landing mark, dust, glow, speed line, motion trail, motion mark, wave arc, sound-wave curve, action line, smear, detached symbol, loose effect, or scenery.
- Show contact, weight, or travel only through the character pose. Do not draw floor cues.
- Keep the first and last frames compatible for a clean loop when possible."""


def split_frame_actions(raw: str | None) -> list[str]:
    if not raw:
        return []
    actions: list[str] = []
    for chunk in raw.replace("\n", ";").split(";"):
        item = chunk.strip()
        if item:
            actions.append(item)
    return actions


def format_frame_actions(frame_actions: list[str]) -> str:
    return "\n".join(f"Frame {index} consecutive motion beat: {beat}" for index, beat in enumerate(frame_actions, start=1))


def normalize_frame_actions(action_id: str, action: str, explicit: list[str] | None = None) -> list[str]:
    frame_actions = [item.strip() for item in explicit or [] if item.strip()]
    if not frame_actions:
        raise SystemExit(
            f"frame actions must be planned before layout generation for {action_id}; "
            "pass --frame-action repeatedly, --frame-actions, or provide action_plans in the manifest"
        )
    if len(frame_actions) > MAX_RECOMMENDED_GRID_FRAMES:
        raise SystemExit(
            f"frame actions for {action_id} contain {len(frame_actions)} beats; "
            f"review the sequential plan and delete or merge excessive duplicate beats before layout generation "
            f"({MAX_RECOMMENDED_GRID_FRAMES} frames maximum)"
        )
    return frame_actions


def motion_beats(frame_actions: list[str]) -> list[dict[str, object]]:
    return [{"frame": index + 1, "beat": beat} for index, beat in enumerate(frame_actions)]


def with_fps(value: float | None) -> dict[str, float]:
    return {"fps": value} if value is not None else {}


def normalize_layout_for_beats(raw: object, frame_count: int) -> dict[str, object]:
    layout = recommended_grid(frame_count)
    if isinstance(raw, dict):
        cell_width = int(raw.get("cell_width", raw.get("frame_width", layout["cell_width"])))
        cell_height = int(raw.get("cell_height", raw.get("frame_height", layout["cell_height"])))
        layout["cell_width"] = cell_width
        layout["cell_height"] = cell_height
        layout["working_cell_size"] = [cell_width, cell_height]
    return layout


def seed_frame_actions(seed: dict[str, object], state_name: str) -> list[str]:
    action_plans = seed.get("action_plans")
    if isinstance(action_plans, dict):
        raw = action_plans.get(state_name)
        if isinstance(raw, list):
            return [str(item) for item in raw]
        if isinstance(raw, dict):
            beats = raw.get("frame_actions") or raw.get("beats")
            if isinstance(beats, list):
                return [str(item) for item in beats]
    animation = seed.get("animation")
    if isinstance(animation, dict):
        states = animation.get("states")
        if isinstance(states, list):
            for state in states:
                if isinstance(state, dict) and state.get("name") == state_name:
                    beats = state.get("frame_actions") or state.get("beats")
                    if isinstance(beats, list):
                        return [str(item) for item in beats]
    return []


def existing_jobs_by_id(run_dir: Path) -> dict[str, dict[str, object]]:
    jobs_path = run_dir / "animation-jobs.json"
    if not jobs_path.is_file():
        return {}
    jobs_manifest = load_json(jobs_path)
    jobs = jobs_manifest.get("jobs")
    if not isinstance(jobs, list):
        return {}
    return {
        str(job["id"]): dict(job)
        for job in jobs
        if isinstance(job, dict) and isinstance(job.get("id"), str)
    }


def action_job_for_state(
    state: dict[str, object],
    *,
    canonical_base_exists: bool,
    existing_jobs: dict[str, dict[str, object]],
) -> dict[str, object]:
    state_name = str(state["name"])
    base_job = {
        "id": state_name,
        "kind": "action-grid",
        "status": "ready" if canonical_base_exists else "blocked",
        "prompt_file": f"prompts/actions/{state_name}.md",
        "output_path": f"generated/{state_name}.png",
        "input_images": [],
    }
    registration_path = f"references/registration-guides/{state_name}.png"
    if canonical_base_exists:
        base_job["input_images"].append(
            {
                "path": registration_path,
                "role": "registration guide edit template; keep black cell borders, blue safe-area rectangles, and neutral outside background, remove gray dashed centerlines and faint guide characters, and fill only safe-area interiors with chroma-key",
            }
        )
    base_job["input_images"].append({"path": "references/canonical-base.png", "role": "canonical base character"})
    existing = existing_jobs.get(state_name)
    if not existing:
        return base_job
    merged = {**base_job, **existing}
    merged["prompt_file"] = base_job["prompt_file"]
    merged["input_images"] = base_job["input_images"]
    merged.pop("image_creator_prompt_file", None)
    merged.pop("image_creator_prompt_sha256", None)
    merged["output_path"] = base_job["output_path"]
    merged["input_images"] = base_job["input_images"]
    return merged


def create_layout_guide(
    path: Path,
    *,
    state: str,
    frames: int,
    frame_size: tuple[int, int],
    safe_margin: tuple[int, int],
    layout: dict[str, object],
    frame_actions: list[str],
) -> dict[str, object]:
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    cell_width = int(layout["cell_width"])
    cell_height = int(layout["cell_height"])
    width = columns * cell_width
    height = rows * cell_height
    validate_image_2_size(width, height)
    image = Image.new("RGB", (width, height), "#f7f7f7")
    draw = ImageDraw.Draw(image)

    for index in range(frames):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * cell_height
        right = left + cell_width - 1
        bottom = top + cell_height - 1
        draw.rectangle((left, top, right, bottom), outline="#111111", width=2)
        safe_left = left + safe_margin[0]
        safe_top = top + safe_margin[1]
        safe_right = right - safe_margin[0]
        safe_bottom = bottom - safe_margin[1]
        draw.rectangle((safe_left, safe_top, safe_right, safe_bottom), outline="#2f80ed", width=2)
        center_x = left + cell_width // 2
        center_y = top + cell_height // 2
        draw_dashed_line(draw, (center_x, safe_top), (center_x, safe_bottom), fill="#b8b8b8")
        draw_dashed_line(draw, (safe_left, center_y), (safe_right, center_y), fill="#b8b8b8")

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {
        "state": state,
        "path": str(path),
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 6),
        "image_model": "codex-built-in-image-gen",
        "image_model_size_constraints": {
            "max_aspect_ratio": "3:1",
            "cell_size": "512x512",
            "max_16_frame_canvas": "2048x2048",
        },
        "frames": frames,
        "frame_actions": frame_actions,
        "frame_width": frame_size[0],
        "frame_height": frame_size[1],
        "layout": layout,
        "columns": columns,
        "rows": rows,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "safe_margin_x": safe_margin[0],
        "safe_margin_y": safe_margin[1],
        "usage": "layout guide only; do not copy guide lines into generated art",
    }


def base_sprite_for_registration(source: Path, target_size: tuple[int, int], safe_margin: tuple[int, int]) -> Image.Image:
    with Image.open(source) as opened:
        rgba = opened.convert("RGBA")
    bbox = rgba.getbbox()
    target = Image.new("RGBA", target_size, (0, 0, 0, 0))
    if bbox is None:
        return target
    sprite = rgba.crop(bbox)
    max_width = max(1, target_size[0] - safe_margin[0] * 2)
    max_height = max(1, target_size[1] - safe_margin[1] * 2)
    scale = min(max_width / sprite.width, max_height / sprite.height, 1.0)
    if scale != 1.0:
        sprite = sprite.resize(
            (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
            Image.Resampling.LANCZOS,
        )
    left = (target_size[0] - sprite.width) // 2
    top = (target_size[1] - sprite.height) // 2
    target.alpha_composite(sprite, (left, top))
    return target


def create_registration_guide(
    path: Path,
    *,
    canonical_base: Path,
    frames: int,
    frame_size: tuple[int, int],
    safe_margin: tuple[int, int],
    layout: dict[str, object],
) -> dict[str, object]:
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    cell_width = int(layout["cell_width"])
    cell_height = int(layout["cell_height"])
    width = columns * cell_width
    height = rows * cell_height
    image = Image.new("RGBA", (width, height), (247, 247, 247, 255))
    draw = ImageDraw.Draw(image)
    sprite = base_sprite_for_registration(canonical_base, frame_size, safe_margin)
    ghost = sprite.copy()
    alpha = ghost.getchannel("A").point(lambda value: round(value * 0.32))
    ghost.putalpha(alpha)

    for index in range(frames):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * cell_height
        right = left + cell_width - 1
        bottom = top + cell_height - 1
        draw.rectangle((left, top, right, bottom), outline="#111111", width=2)
        safe_left = left + safe_margin[0]
        safe_top = top + safe_margin[1]
        safe_right = right - safe_margin[0]
        safe_bottom = bottom - safe_margin[1]
        draw.rectangle((safe_left, safe_top, safe_right, safe_bottom), outline="#2f80ed", width=2)
        center_x = left + cell_width // 2
        center_y = top + cell_height // 2
        draw_dashed_line(draw, (center_x, safe_top), (center_x, safe_bottom), fill="#b8b8b8")
        draw_dashed_line(draw, (safe_left, center_y), (safe_right, center_y), fill="#b8b8b8")
        image.alpha_composite(ghost, (left, top))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path)
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "frames": frames,
        "columns": columns,
        "rows": rows,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "safe_margin_x": safe_margin[0],
        "safe_margin_y": safe_margin[1],
        "usage": "registration guide edit template; generated action sheet keeps black cell borders and blue safe-area rectangles, removes gray dashed centerlines and faint guide characters, and replaces only safe-area interiors with chroma-key",
    }


def job_rows(jobs_manifest: dict[str, object]) -> list[dict[str, object]]:
    jobs = jobs_manifest.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("animation-jobs.json is missing a jobs list")
    return [job for job in jobs if isinstance(job, dict)]


def refresh_after_canonical_base(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    jobs_manifest: dict[str, object],
    canonical: Path,
    chroma: dict[str, object],
) -> list[str]:
    manifest["canonical_base"] = rel(canonical, run_dir)
    manifest["chroma_key"] = chroma
    manifest["chroma_key_status"] = "ready"
    if isinstance(manifest.get("animation"), dict):
        manifest["animation"]["background_mode"] = manifest.get("background_mode", "chroma-key")
    regenerated_prompts = []
    registration_guides = []
    animation = manifest.get("animation", {})
    states = animation.get("states", []) if isinstance(animation, dict) else []
    for state in states:
        if not isinstance(state, dict):
            continue
        layout = dict(state["layout"])
        frame_size = (int(manifest["frame_width"]), int(manifest["frame_height"]))
        safe_margin = (
            int(layout.get("safe_margin_x", 0) or 0),
            int(layout.get("safe_margin_y", 0) or 0),
        )
        registration_guide = create_registration_guide(
            run_dir / "references" / "registration-guides" / f"{state['name']}.png",
            canonical_base=canonical,
            frames=int(state["frames"]),
            frame_size=frame_size,
            safe_margin=safe_margin,
            layout=layout,
        )
        registration_guide["state"] = str(state["name"])
        registration_guides.append(registration_guide)
        prompt_path = run_dir / "prompts" / "actions" / f"{state['name']}.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            action_prompt(
                action_id=str(state["name"]),
                action=str(state.get("action", state["name"])),
                character_name=str(manifest.get("character_name", manifest.get("name", "character"))),
                frames=int(state["frames"]),
                frame_size=frame_size,
                layout=layout,
                frame_actions=[str(item) for item in state.get("frame_actions", [])],
                chroma=chroma,
                chroma_ready=True,
                registration_guide_ready=True,
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        regenerated_prompts.append(rel(prompt_path, run_dir))
    manifest["registration_guides"] = registration_guides
    for other_job in job_rows(jobs_manifest):
        if other_job.get("kind") in {"action-grid", "action-strip"} and other_job.get("status") == "blocked":
            other_job["status"] = "ready"
        if other_job.get("kind") in {"action-grid", "action-strip"}:
            other_job["prompt_status"] = "ready-after-canonical-base"
            other_job["prompt_regenerated_after_base"] = True
            other_job["chroma_key_hex"] = chroma["hex"]
            inputs = other_job.get("input_images")
            if isinstance(inputs, list):
                state_name = str(other_job.get("id"))
                inputs[:] = [
                    item
                    for item in inputs
                    if not (
                        isinstance(item, dict)
                        and str(item.get("path", "")).startswith("references/layout-guides/")
                    )
                ]
                registration_path = f"references/registration-guides/{state_name}.png"
                registration_item = next(
                    (
                        item
                        for item in inputs
                        if isinstance(item, dict) and item.get("path") == registration_path
                    ),
                    None,
                )
                if registration_item is None:
                    registration_item = {
                        "path": registration_path,
                        "role": "registration guide edit template; keep black cell borders, blue safe-area rectangles, and neutral outside background, remove gray dashed centerlines and faint guide characters, and fill only safe-area interiors with chroma-key",
                    }
                else:
                    registration_item["role"] = "registration guide edit template; keep black cell borders, blue safe-area rectangles, and neutral outside background, remove gray dashed centerlines and faint guide characters, and fill only safe-area interiors with chroma-key"
                inputs[:] = [
                    item
                    for item in inputs
                    if not (isinstance(item, dict) and item.get("path") == registration_path)
                ]
                inputs.insert(0, registration_item)
    return regenerated_prompts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Optional input manifest JSON.")
    parser.add_argument("--project-root", default=".", help="Session project root. Defaults to the current directory.")
    parser.add_argument("--run-dir", help="Existing or new run directory. Relative paths resolve from --project-root.")
    parser.add_argument("--output-dir", help="Alias for --run-dir.")
    parser.add_argument("--name", default="")
    parser.add_argument("--character-name", default="")
    parser.add_argument("--character-prompt", default="")
    parser.add_argument("--source-character", help="Optional source character image.")
    parser.add_argument("--action-id", default="animation")
    parser.add_argument("--action", default="")
    parser.add_argument("--add-action", action="store_true", help="Add one action to an existing run.")
    parser.add_argument("--frame-size", help="Override frame size as WIDTHxHEIGHT.")
    parser.add_argument("--frame-count", type=int, help="Deprecated compatibility hint; frame count is derived from frame actions.")
    parser.add_argument(
        "--frame-action",
        action="append",
        default=[],
        help="One frame action beat. Repeat to define the full action before layout is created.",
    )
    parser.add_argument(
        "--frame-actions",
        help="Semicolon-separated frame action beats. The number of beats becomes the frame count.",
    )
    parser.add_argument("--fps", type=float, help="Playback FPS to record when explicitly requested.")
    parser.add_argument("--format", default=None, choices=("webp",), help="Final animation output format. Intermediate extracted frames are PNG.")
    parser.add_argument("--states", help="Comma-separated state names for a simple manifest.")
    parser.add_argument("--chroma-key", help="Chroma key color as #RRGGBB.")
    parser.add_argument("--background-mode", choices=("chroma-key",), help="Background mode recorded in the run manifest.")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=None, help="Whether final animations should loop.")
    parser.add_argument(
        "--safe-margin",
        default=f"{DEFAULT_SAFE_MARGIN_X}x{DEFAULT_SAFE_MARGIN_Y}",
        help="Layout guide safe margin as XxY pixels.",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    raw_run_dir = args.run_dir or args.output_dir

    seed: dict[str, object] = load_json(Path(args.manifest)) if args.manifest else {}
    if raw_run_dir:
        candidate_run_dir = resolve_project_path(raw_run_dir, project_root)
        existing_manifest = candidate_run_dir / "animation_manifest.json"
        if existing_manifest.is_file() and not args.manifest:
            seed = load_json(existing_manifest)

    frame_size = parse_size(args.frame_size, DEFAULT_WORKING_CELL_SIZE) if args.frame_size else None
    settings = manifest_settings(
        seed,
        frame_size=frame_size,
        frame_count=None,
        fps=args.fps,
        output_format=args.format,
        require_states=False,
    )
    action_id = slugify(args.action_id)
    explicit_frame_actions = [*args.frame_action, *split_frame_actions(args.frame_actions)]
    action_text = args.action or action_id
    loop = bool(seed.get("loop", True)) if args.loop is None else bool(args.loop)
    background_mode = str(args.background_mode or seed.get("background_mode") or "chroma-key")

    if args.states:
        names = [slugify(item) for item in args.states.split(",") if item.strip()]
        planned_states = []
        for index, name in enumerate(names):
            beats = normalize_frame_actions(
                name,
                action_text if name == action_id else name,
                explicit_frame_actions if name == action_id else seed_frame_actions(seed, name),
            )
            planned_states.append(
                {
                    "name": name,
                    "row": index,
                    "frames": len(beats),
                    "frame_count": len(beats),
                    "frame_actions": beats,
                    "motion_beats": motion_beats(beats),
                    **with_fps(settings["fps"]),
                    "action": action_text if name == action_id else name,
                    "layout": recommended_grid(len(beats)),
                }
            )
        settings["states"] = planned_states
    elif args.add_action:
        existing_states = list(settings["states"])
        existing_names = {state["name"] for state in existing_states}
        normalized_existing = []
        for state in existing_states:
            state_action = str(state.get("action") or state["name"])
            beats = normalize_frame_actions(
                str(state["name"]),
                state_action,
                list(state.get("frame_actions") or seed_frame_actions(seed, str(state["name"]))),
            )
            normalized_existing.append(
                {
                    **state,
                    "frames": len(beats),
                    "frame_count": len(beats),
                    "frame_actions": beats,
                    "motion_beats": motion_beats(beats),
                    "action": state_action,
                    "layout": normalize_layout_for_beats(state.get("layout"), len(beats)),
                }
            )
        if action_id not in existing_names:
            beats = normalize_frame_actions(action_id, action_text, explicit_frame_actions)
            normalized_existing.append(
                {
                    "name": action_id,
                    "row": max((int(state["row"]) for state in normalized_existing), default=-1) + 1,
                    "frames": len(beats),
                    "frame_count": len(beats),
                    "frame_actions": beats,
                    "motion_beats": motion_beats(beats),
                    **with_fps(settings["fps"]),
                    "action": action_text,
                    "layout": recommended_grid(len(beats)),
                }
            )
        settings["states"] = normalized_existing
    else:
        beats = normalize_frame_actions(action_id, action_text, explicit_frame_actions or seed_frame_actions(seed, action_id))
        settings["states"] = [
            {
                "name": action_id,
                "row": 0,
                "frames": len(beats),
                "frame_count": len(beats),
                "frame_actions": beats,
                "motion_beats": motion_beats(beats),
                **with_fps(settings["fps"]),
                "action": action_text,
                "layout": recommended_grid(len(beats)),
            }
        ]
    settings["frame_count"] = max(int(state["frames"]) for state in settings["states"])
    settings["layout"] = recommended_grid(settings["frame_count"])

    safe_margin = parse_size(args.safe_margin, (DEFAULT_SAFE_MARGIN_X, DEFAULT_SAFE_MARGIN_Y))
    character_name = args.character_name or str(seed.get("character_name") or seed.get("name") or args.name or action_id)
    character_id = slugify(character_name)
    run_name = slugify(args.name or str(seed.get("name", "")) or character_name)
    if raw_run_dir:
        run_dir = resolve_project_path(raw_run_dir, project_root)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = (project_root / "animation-runs" / f"{run_name}-{timestamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    existing_jobs = existing_jobs_by_id(run_dir)

    chroma = chroma_settings(seed, args.chroma_key)
    prompts_dir = run_dir / "prompts"
    action_prompt_dir = prompts_dir / "actions"
    references_dir = run_dir / "references"
    generated_dir = run_dir / "generated"
    for directory in [prompts_dir, action_prompt_dir, references_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    canonical_base = references_dir / "canonical-base.png"
    source_character_path = None
    if args.source_character:
        source = resolve_project_path(args.source_character, project_root)
        if not source.is_file():
            raise SystemExit(f"source character not found: {source}")
        source_character_path = source
        if not canonical_base.exists():
            save_png_copy(source, canonical_base)
        if not args.chroma_key:
            chroma = choose_chroma_key_for_image(canonical_base)
    chroma_ready = bool(canonical_base.exists() or args.chroma_key)

    frame_size_tuple = (settings["frame_width"], settings["frame_height"])
    for state in settings["states"]:
        state["layout"]["safe_margin_x"] = safe_margin[0]
        state["layout"]["safe_margin_y"] = safe_margin[1]

    write_text(
        prompts_dir / "base-character.md",
        base_prompt(
            character_name=character_name,
            character_prompt=args.character_prompt or str(seed.get("character_prompt", "")),
            frame_size=frame_size_tuple,
            safe_margin=safe_margin,
        ),
    )
    for state in settings["states"]:
        write_text(
            action_prompt_dir / f"{state['name']}.md",
            action_prompt(
                action_id=state["name"],
                action=str(state.get("action", state["name"])),
                character_name=character_name,
                frames=int(state["frames"]),
                frame_size=frame_size_tuple,
                layout=state["layout"],
                frame_actions=list(state["frame_actions"]),
                chroma=chroma,
                chroma_ready=chroma_ready,
                registration_guide_ready=False,
            ),
        )

    manifest = {
        **seed,
        "name": run_name,
        "character_id": character_id,
        "character_name": character_name,
        "character_prompt": args.character_prompt or seed.get("character_prompt", ""),
        "project_root": str(project_root),
        "run_dir": str(run_dir),
        "description": args.character_prompt or seed.get("description") or seed.get("character_prompt", ""),
        "canonical_base": "references/canonical-base.png",
        "frame_width": settings["frame_width"],
        "frame_height": settings["frame_height"],
        "loop": loop,
        "background_mode": background_mode,
        "actions": [state["name"] for state in settings["states"]],
        "animation": {
            "frame_size": [settings["frame_width"], settings["frame_height"]],
            "frame_count": settings["frame_count"],
            "format": settings["format"],
            "loop": loop,
            "background_mode": background_mode,
            "layout": settings["layout"],
            "states": settings["states"],
        },
        "action_plans": {
            state["name"]: {
                "action": state.get("action", state["name"]),
                "frame_count": state["frames"],
                "frame_actions": state["frame_actions"],
                "motion_beats": state["motion_beats"],
            }
            for state in settings["states"]
        },
        "chroma_key": chroma,
        "chroma_key_status": "ready" if chroma_ready else "pending-canonical-base",
        "paths": {
            "canonical_base": "references/canonical-base.png",
            "generated_dir": "generated",
            "frames_dir": "frames",
            "preview_dir": "qa/previews",
        },
        "outputs": seed.get("outputs", {"actions": {}}),
        "registration_guides": [],
    }
    if settings["fps"] is not None:
        manifest["fps"] = settings["fps"]
        manifest["animation"]["fps"] = settings["fps"]
    if source_character_path is not None:
        manifest["source_character"] = str(source_character_path)
    if canonical_base.exists():
        manifest["canonical_base"] = rel(canonical_base, run_dir)

    base_job = {
        "id": "base-character",
        "kind": "base-character",
        "status": "ready" if not canonical_base.exists() else "complete",
        "prompt_file": "prompts/base-character.md",
        "output_path": "generated/base-character.png" if source_character_path is None else "references/canonical-base.png",
        "canonical_output_path": "references/canonical-base.png",
        "input_images": [],
    }
    action_prompt_status = "ready-after-canonical-base" if canonical_base.exists() else "pending-canonical-base"
    if source_character_path is not None and canonical_base.exists():
        base_job.update(
            {
                "source_path": str(source_character_path),
                "recorded_output": rel(canonical_base, run_dir),
                "source_sha256": file_sha256(source_character_path),
                "output_sha256": file_sha256(canonical_base),
                "canonical_sha256": file_sha256(canonical_base),
            }
        )
    if "base-character" in existing_jobs:
        base_job = {**base_job, **existing_jobs["base-character"]}
        base_job["prompt_file"] = "prompts/base-character.md"
        base_job["output_path"] = "generated/base-character.png" if source_character_path is None else "references/canonical-base.png"
        base_job["canonical_output_path"] = "references/canonical-base.png"
        base_job["input_images"] = []
        base_job.pop("image_creator_prompt_file", None)
        base_job.pop("image_creator_prompt_sha256", None)
        if source_character_path is not None and canonical_base.exists():
            base_job.update(
                {
                    "source_path": str(source_character_path),
                    "recorded_output": rel(canonical_base, run_dir),
                    "source_sha256": file_sha256(source_character_path),
                    "output_sha256": file_sha256(canonical_base),
                    "canonical_sha256": file_sha256(canonical_base),
                    "status": "complete",
                }
            )

    jobs = {
        "schema_version": 1,
        "project_root": str(project_root),
        "run_dir": str(run_dir),
        "generation_skill": "$image-creator",
        "jobs": [
            base_job,
            *[
                action_job_for_state(
                    state,
                    canonical_base_exists=canonical_base.exists(),
                    existing_jobs=existing_jobs,
                )
                | {"prompt_status": action_prompt_status, "chroma_key_hex": chroma["hex"]}
                for state in settings["states"]
            ],
        ],
    }
    if canonical_base.exists():
        regenerated_prompts = refresh_after_canonical_base(
            run_dir=run_dir,
            manifest=manifest,
            jobs_manifest=jobs,
            canonical=canonical_base,
            chroma=chroma,
        )
        base_job["regenerated_action_prompts"] = regenerated_prompts
    write_json(run_dir / "animation-jobs.json", jobs)
    write_json(run_dir / "animation_manifest.json", manifest)
    print(str(run_dir))


if __name__ == "__main__":
    main()
