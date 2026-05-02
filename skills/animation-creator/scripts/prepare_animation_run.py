#!/usr/bin/env python3
"""Create a manifest-driven animation run folder and layout guides."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from animation_common import (
    DEFAULT_SAFE_MARGIN,
    chroma_settings,
    draw_dashed_line,
    load_json,
    manifest_settings,
    parse_size,
    recommended_grid,
    slugify,
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


def base_prompt(
    *,
    character_name: str,
    character_prompt: str,
    chroma: dict[str, object],
) -> str:
    chroma_hex = str(chroma["hex"])
    return f"""Create one clean full-body reference image for an animation character named {character_name}.

Character: {character_prompt or "an original character suitable for animation"}.

Output a single centered full-body character pose on a perfectly flat chroma-key background using {chroma_hex}. The character must be fully visible, readable, and suitable for generating animation frames. Do not include scenery, text, labels, borders, ground planes, floors, cast shadows, contact shadows, oval floor shadows, landing marks, glows, detached effects, or extra props not requested. Do not use {chroma_hex} or colors close to it in the character, outfit, props, highlights, shadows, or effects."""


def action_prompt(
    *,
    action_id: str,
    action: str,
    character_name: str,
    frames: int,
    frame_size: tuple[int, int],
    layout: dict[str, object],
    chroma: dict[str, object],
) -> str:
    chroma_hex = str(chroma["hex"])
    columns = int(layout["columns"])
    rows = int(layout["rows"])
    cell_width = int(layout["cell_width"])
    cell_height = int(layout["cell_height"])
    return f"""Create one animation frame grid for {character_name} performing `{action_id}`.

Use the attached canonical base image as the character identity source. Use the attached layout guide only for frame count, slot spacing, centering, and safe padding. Do not copy guide lines, boxes, labels, colors, or the guide background into the output.

Identity lock:
- Do not redesign the character.
- Preserve the same head shape, face, proportions, silhouette, markings, palette, outfit, materials, and props from the canonical base.
- Change only pose, expression, and action timing needed for this action: {action}.

Output exactly {frames} separate full-body animation frames as a {columns}x{rows} animation frame grid. Read and fill frames left-to-right across each row, then top-to-bottom. Each working grid cell is {cell_width}x{cell_height}; each final extracted frame will be normalized to {frame_size[0]}x{frame_size[1]}.

Layout requirements:
- Treat the image as {columns} columns by {rows} rows of equal-size invisible frame slots.
- Fill each of the first {frames} slots with exactly one complete centered pose.
- Leave any unused trailing grid slots empty with only the flat chroma-key background.
- Keep every body part inside the slot's safe area.
- No pose may cross into a neighboring slot.
- Spread poses evenly across the whole grid in left-to-right, top-to-bottom frame order.
- Use a perfectly flat chroma-key background using {chroma_hex}.
- Do not include any ground plane, floor line, cast shadow, contact shadow, oval floor shadow, landing mark, dust, glow, speed line, motion trail, smear, detached symbol, loose effect, visible grid, box, frame number, text, watermark, or scenery.
- Show weight, jumping, or landing only through the character pose. Do not draw floor cues.
- Keep the first and last frames compatible for a clean loop when possible."""


def create_layout_guide(
    path: Path,
    *,
    state: str,
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
        "frames": frames,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Optional seed manifest JSON.")
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
    parser.add_argument("--frame-count", type=int, help="Default frame count.")
    parser.add_argument("--fps", type=float, help="Default animation FPS.")
    parser.add_argument("--format", default=None, choices=("png", "webp"), help="Frame output format.")
    parser.add_argument("--states", help="Comma-separated state names for a simple manifest.")
    parser.add_argument("--chroma-key", help="Chroma key color as #RRGGBB.")
    parser.add_argument(
        "--safe-margin",
        default=f"{DEFAULT_SAFE_MARGIN}x{DEFAULT_SAFE_MARGIN}",
        help="Safe margin as XxY pixels.",
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

    frame_size = parse_size(args.frame_size, (512, 512)) if args.frame_size else None
    settings = manifest_settings(
        seed,
        frame_size=frame_size,
        frame_count=args.frame_count,
        fps=args.fps,
        output_format=args.format,
    )
    action_id = slugify(args.action_id)
    if args.states:
        names = [slugify(item) for item in args.states.split(",") if item.strip()]
        settings["states"] = [
            {"name": name, "row": index, "frames": settings["frame_count"], "fps": settings["fps"], "layout": recommended_grid(settings["frame_count"])}
            for index, name in enumerate(names)
        ]
    elif args.add_action:
        existing_states = list(settings["states"])
        existing_names = {state["name"] for state in existing_states}
        if action_id not in existing_names:
            existing_states.append(
                {
                    "name": action_id,
                    "row": max((int(state["row"]) for state in existing_states), default=-1) + 1,
                    "frames": settings["frame_count"],
                    "fps": settings["fps"],
                    "layout": recommended_grid(settings["frame_count"]),
                }
            )
        settings["states"] = existing_states
    else:
        settings["states"] = [{"name": action_id, "row": 0, "frames": settings["frame_count"], "fps": settings["fps"], "layout": recommended_grid(settings["frame_count"])}]

    safe_margin = parse_size(args.safe_margin, (DEFAULT_SAFE_MARGIN, DEFAULT_SAFE_MARGIN))
    character_name = args.character_name or str(seed.get("character_name") or seed.get("name") or args.name or action_id)
    character_id = slugify(character_name)
    run_name = slugify(args.name or str(seed.get("name", "")) or character_name)
    if raw_run_dir:
        run_dir = resolve_project_path(raw_run_dir, project_root)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = (project_root / "animation-runs" / f"{run_name}-{timestamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    chroma = chroma_settings(seed, args.chroma_key)
    prompts_dir = run_dir / "prompts"
    action_prompt_dir = prompts_dir / "actions"
    references_dir = run_dir / "references"
    generated_dir = run_dir / "generated"
    decoded_dir = run_dir / "decoded"
    for directory in [prompts_dir, action_prompt_dir, references_dir, generated_dir, decoded_dir, run_dir / "frames", run_dir / "final", run_dir / "qa"]:
        directory.mkdir(parents=True, exist_ok=True)

    canonical_base = references_dir / "canonical-base.png"
    source_character_path = None
    if args.source_character:
        source = resolve_project_path(args.source_character, project_root)
        if not source.is_file():
            raise SystemExit(f"source character not found: {source}")
        copied = references_dir / f"source-character{source.suffix.lower() or '.png'}"
        shutil.copy2(source, copied)
        source_character_path = copied
        if not canonical_base.exists():
            shutil.copy2(copied, canonical_base)

    guides = []
    frame_size_tuple = (settings["frame_width"], settings["frame_height"])
    for state in settings["states"]:
        guides.append(
            create_layout_guide(
                references_dir / "layout-guides" / f"{state['name']}.png",
                state=state["name"],
                frames=state["frames"],
                frame_size=frame_size_tuple,
                safe_margin=safe_margin,
                layout=state["layout"],
            )
        )

    write_text(
        prompts_dir / "base-character.md",
        base_prompt(
            character_name=character_name,
            character_prompt=args.character_prompt or str(seed.get("character_prompt", "")),
            chroma=chroma,
        ),
    )
    for state in settings["states"]:
        write_text(
            action_prompt_dir / f"{state['name']}.md",
            action_prompt(
                action_id=state["name"],
                action=args.action if state["name"] == action_id else str(state.get("action", state["name"])),
                character_name=character_name,
                frames=int(state["frames"]),
                frame_size=frame_size_tuple,
                layout=state["layout"],
                chroma=chroma,
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
        "animation": {
            "frame_size": [settings["frame_width"], settings["frame_height"]],
            "frame_count": settings["frame_count"],
            "fps": settings["fps"],
            "format": settings["format"],
            "layout": settings["layout"],
            "states": settings["states"],
        },
        "chroma_key": chroma,
        "paths": {
            "canonical_base": "references/canonical-base.png",
            "generated_dir": "generated",
            "decoded_dir": "decoded",
            "frames_dir": "frames",
            "composed": f"final/{run_name}.png",
            "contact_sheet": f"qa/{run_name}-contact-sheet.png",
            "preview_dir": "qa/previews",
        },
        "layout_guides": guides,
    }
    if source_character_path is not None:
        manifest["source_character"] = rel(source_character_path, run_dir)
    if canonical_base.exists():
        manifest["canonical_base"] = rel(canonical_base, run_dir)

    write_json(run_dir / "animation_manifest.json", manifest)
    write_json(run_dir / "animation_request.json", manifest)
    jobs = {
        "schema_version": 1,
        "project_root": str(project_root),
        "run_dir": str(run_dir),
        "generation_skill": "$image-creator",
        "jobs": [
            {
                "id": "base-character",
                "kind": "base-character",
                "status": "ready" if not canonical_base.exists() else "complete",
                "prompt_file": "prompts/base-character.md",
                "output_path": "generated/base-character.png",
                "canonical_output_path": "references/canonical-base.png",
                "input_images": [] if source_character_path is None else [{"path": rel(source_character_path, run_dir), "role": "source character reference"}],
            },
            *[
                {
                    "id": state["name"],
                    "kind": "action-grid",
                    "status": "ready" if canonical_base.exists() else "blocked",
                    "prompt_file": f"prompts/actions/{state['name']}.md",
                    "output_path": f"generated/{state['name']}.png",
                    "decoded_path": f"decoded/{state['name']}.png",
                    "input_images": [
                        {"path": "references/canonical-base.png", "role": "canonical base character"},
                        {"path": f"references/layout-guides/{state['name']}.png", "role": "layout guide for animation frame grid slots"},
                    ],
                }
                for state in settings["states"]
            ],
        ],
    }
    write_json(run_dir / "animation-jobs.json", jobs)
    print(str(run_dir))


if __name__ == "__main__":
    main()
