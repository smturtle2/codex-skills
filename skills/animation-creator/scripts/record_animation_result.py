#!/usr/bin/env python3
"""Record a generated base character or action grid into an animation run."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from animation_common import load_json, manifest_for_run, write_json
from build_generation_prompt import build_prompt
from prepare_animation_run import refresh_after_canonical_base
from rembg_runtime import DEFAULT_MODEL as REMBG_MODEL
from rembg_runtime import background_removal_defaults
from rembg_runtime import remove_background


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def resolve_run_path(run_dir: Path, raw: object, *, field: str, job_id: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise SystemExit(f"job {job_id} has no {field}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    return path.resolve()


def job_list(jobs_manifest: dict[str, object]) -> list[dict[str, object]]:
    jobs = jobs_manifest.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("animation-jobs.json is missing a jobs list")
    return [job for job in jobs if isinstance(job, dict)]


def find_job(jobs_manifest: dict[str, object], job_id: str) -> dict[str, object]:
    for job in job_list(jobs_manifest):
        if job.get("id") == job_id:
            return job
    raise SystemExit(f"unknown job id: {job_id}")


def raw_output_path(run_dir: Path, job_id: str) -> Path:
    return run_dir / "generated" / "raw" / f"{job_id}.png"


def state_for_job(manifest: dict[str, object], job_id: str) -> dict[str, object]:
    animation = manifest.get("animation")
    states = animation.get("states") if isinstance(animation, dict) else None
    if not isinstance(states, list):
        raise SystemExit("animation manifest is missing states")
    for state in states:
        if isinstance(state, dict) and state.get("name") == job_id:
            return state
    raise SystemExit(f"animation manifest has no state for action job: {job_id}")


def slot_boxes(width: int, height: int, columns: int, rows: int, frames: int) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(frames):
        column = index % columns
        row = index // columns
        left = round(column * width / columns)
        right = round((column + 1) * width / columns)
        top = round(row * height / rows)
        bottom = round((row + 1) * height / rows)
        boxes.append((left, top, right, bottom))
    return boxes


def border_strip_inset(width: int, height: int) -> int:
    return max(4, round(min(width, height) * 0.015))


def inset_box(box: tuple[int, int, int, int], inset: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    if right - left <= inset * 2 or bottom - top <= inset * 2:
        return box
    return (left + inset, top + inset, right - inset, bottom - inset)


def parse_hex_rgb(raw: object) -> tuple[int, int, int]:
    if not isinstance(raw, str):
        raise SystemExit("animation manifest removal_background.hex must be a string")
    value = raw.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) != 6:
        raise SystemExit(f"invalid removal matte hex: {raw}")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise SystemExit(f"invalid removal matte hex: {raw}") from exc


def removal_matte_rgb(manifest: dict[str, object]) -> tuple[int, int, int]:
    removal = manifest.get("removal_background")
    if not isinstance(removal, dict):
        raise SystemExit("animation manifest is missing removal_background")
    return parse_hex_rgb(removal.get("hex"))


def clean_matte_residue(
    path: Path,
    matte_rgb: tuple[int, int, int],
    *,
    hard_tolerance: int = 24,
    soft_tolerance: int = 72,
) -> dict[str, object]:
    if hard_tolerance < 0 or soft_tolerance <= hard_tolerance:
        raise SystemExit("invalid matte residue cleanup tolerances")
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    pixels = image.load()
    changed = 0
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            distance = max(abs(r - matte_rgb[0]), abs(g - matte_rgb[1]), abs(b - matte_rgb[2]))
            if distance <= hard_tolerance:
                pixels[x, y] = (0, 0, 0, 0)
                changed += 1
            elif distance <= soft_tolerance:
                fade = (distance - hard_tolerance) / (soft_tolerance - hard_tolerance)
                next_alpha = min(a, round(a * fade))
                if next_alpha < a:
                    pixels[x, y] = (r, g, b, next_alpha)
                    changed += 1
    if changed:
        image.save(path, format="PNG")
    return {
        "matte_hex": f"#{matte_rgb[0]:02X}{matte_rgb[1]:02X}{matte_rgb[2]:02X}",
        "hard_tolerance": hard_tolerance,
        "soft_tolerance": soft_tolerance,
        "pixels_changed": changed,
    }


def remove_action_sheet_background(run_dir: Path, job_id: str, source: Path, output: Path, manifest: dict[str, object]) -> dict[str, object]:
    state = state_for_job(manifest, job_id)
    layout = state.get("layout")
    if not isinstance(layout, dict):
        raise SystemExit(f"state {job_id} has no layout")
    columns = int(layout.get("columns", 0))
    rows = int(layout.get("rows", 0))
    frames = int(state.get("frames", 0))
    if columns <= 0 or rows <= 0 or frames <= 0 or columns * rows < frames:
        raise SystemExit(f"state {job_id} has invalid layout")

    with Image.open(source) as opened:
        sheet = opened.convert("RGBA")
    normalized = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
    work_dir = run_dir / "generated" / "rembg-work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    matte_rgb = removal_matte_rgb(manifest)
    first_removal: dict[str, object] | None = None
    cleanup_pixels_changed = 0
    cleanup_metadata: dict[str, object] | None = None
    boxes = slot_boxes(sheet.width, sheet.height, columns, rows, frames)
    border_insets: list[int] = []
    rembg_boxes: list[tuple[int, int, int, int]] = []
    for index, box in enumerate(boxes):
        inset = border_strip_inset(box[2] - box[0], box[3] - box[1])
        rembg_box = inset_box(box, inset)
        border_insets.append(inset)
        rembg_boxes.append(rembg_box)
        slot_raw = work_dir / f"{index:03d}-raw.png"
        slot_trimmed = work_dir / f"{index:03d}-border-stripped.png"
        slot_alpha = work_dir / f"{index:03d}.png"
        sheet.crop(box).save(slot_raw, format="PNG")
        sheet.crop(rembg_box).save(slot_trimmed, format="PNG")
        removal = remove_background(slot_trimmed, slot_alpha)
        cleanup = clean_matte_residue(slot_alpha, matte_rgb)
        cleanup_pixels_changed += int(cleanup["pixels_changed"])
        cleanup_metadata = cleanup
        if first_removal is None or ("gpu_fallback" in removal and "gpu_fallback" not in first_removal):
            first_removal = removal
        with Image.open(slot_alpha) as opened:
            normalized.alpha_composite(opened.convert("RGBA"), (rembg_box[0], rembg_box[1]))
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(output, format="PNG")
    metadata = dict(first_removal or {"engine": "rembg", "required": True})
    metadata.update(
        {
            "scope": "action-sheet-slots",
            "slot_count": frames,
            "columns": columns,
            "rows": rows,
            "source_sheet_size": [sheet.width, sheet.height],
            "slot_boxes": [list(box) for box in boxes],
            "rembg_boxes": [list(box) for box in rembg_boxes],
            "border_strip": {
                "policy": "strip-outer-black-cell-borders-before-rembg",
                "insets": border_insets,
            },
            "matte_residue_cleanup": {
                **(cleanup_metadata or {"matte_hex": f"#{matte_rgb[0]:02X}{matte_rgb[1]:02X}{matte_rgb[2]:02X}"}),
                "pixels_changed": cleanup_pixels_changed,
            },
        }
    )
    return metadata


def manifest_background_removal(metadata: dict[str, object]) -> dict[str, object]:
    keys = (
        "required",
        "engine",
        "backend",
        "device",
        "available_providers",
        "selected_providers",
        "model",
        "alpha_matting",
        "model_cache",
        "gpu_fallback",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--job-id", required=True, help="Use base-character or an action id.")
    parser.add_argument("--source", required=True, help="Generated image saved by $image-creator.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"source image not found: {source}")

    manifest_path = manifest_for_run(run_dir)
    if manifest_path is None or not manifest_path.is_file():
        raise SystemExit(f"animation manifest not found for run: {run_dir}")
    manifest = load_json(manifest_path)
    manifest["background_removal"] = background_removal_defaults(model=REMBG_MODEL, alpha_matting=True)
    jobs_path = run_dir / "animation-jobs.json"
    jobs_manifest = load_json(jobs_path)
    job = find_job(jobs_manifest, args.job_id)
    prompt_file = resolve_run_path(run_dir, job.get("prompt_file"), field="prompt_file", job_id=args.job_id)
    if not prompt_file.is_file():
        raise SystemExit(f"job {args.job_id} prompt is missing: {prompt_file}")
    job["prompt_sha256"] = file_sha256(prompt_file)
    job["image_creator_prompt_sha256"] = text_sha256(build_prompt(run_dir, job))

    output_raw = job.get("output_path")
    if not isinstance(output_raw, str):
        raise SystemExit(f"job {args.job_id} has no output_path")
    output = run_dir / output_raw
    raw_output = raw_output_path(run_dir, args.job_id)
    if output.exists() and not args.force:
        raise SystemExit(f"{output} already exists; pass --force to replace it")
    if raw_output.exists() and source.resolve() != raw_output.resolve() and not args.force:
        raise SystemExit(f"{raw_output} already exists; pass --force to replace it")
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != raw_output.resolve():
        shutil.copy2(source, raw_output)

    if args.job_id == "base-character":
        shutil.copy2(raw_output, output)
        canonical_raw = job.get("canonical_output_path", "references/canonical-base.png")
        if not isinstance(canonical_raw, str):
            raise SystemExit("base-character job has invalid canonical_output_path")
        canonical = run_dir / canonical_raw
        canonical.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != canonical.resolve():
            shutil.copy2(output, canonical)
        regenerated_prompts = refresh_after_canonical_base(
            run_dir=run_dir,
            manifest=manifest,
            jobs_manifest=jobs_manifest,
            canonical=canonical,
        )
        job["regenerated_action_prompts"] = regenerated_prompts
    else:
        removal = remove_action_sheet_background(run_dir, args.job_id, raw_output, output, manifest)
        job["background_removal"] = removal
        manifest["background_removal"] = manifest_background_removal(removal)

    completed_at = datetime.now(timezone.utc).isoformat()
    job["status"] = "complete"
    job["original_source_path"] = str(source)
    job["source_path"] = rel(raw_output, run_dir)
    job["recorded_output"] = rel(output, run_dir)
    job["raw_source_sha256"] = file_sha256(raw_output)
    job["output_sha256"] = file_sha256(output)
    job["completed_at"] = completed_at

    write_json(manifest_path, manifest)
    write_json(jobs_path, jobs_manifest)
    print(str(output))


if __name__ == "__main__":
    main()
