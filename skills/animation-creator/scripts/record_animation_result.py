#!/usr/bin/env python3
"""Record a generated base character or action grid into an animation run."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from animation_common import choose_chroma_key_for_image, load_json, manifest_for_run, write_json
from build_generation_prompt import build_prompt
from prepare_animation_run import action_prompt, create_registration_guide


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
    same_output_path = source.resolve() == output.resolve()
    if output.exists() and not same_output_path and not args.force:
        raise SystemExit(f"{output} already exists; pass --force to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not same_output_path:
        shutil.copy2(source, output)

    if args.job_id == "base-character":
        canonical_raw = job.get("canonical_output_path", "references/canonical-base.png")
        if not isinstance(canonical_raw, str):
            raise SystemExit("base-character job has invalid canonical_output_path")
        canonical = run_dir / canonical_raw
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, canonical)
        manifest["canonical_base"] = rel(canonical, run_dir)
        chroma = choose_chroma_key_for_image(canonical)
        manifest["chroma_key"] = chroma
        manifest["chroma_key_status"] = "ready"
        if isinstance(manifest.get("animation"), dict):
            manifest["animation"]["background_mode"] = manifest.get("background_mode", "chroma-key")
        regenerated_prompts = []
        registration_guides = []
        for state in manifest.get("animation", {}).get("states", []):
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
        for other_job in job_list(jobs_manifest):
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
                        registration_item = (
                            {
                                "path": registration_path,
                                "role": "registration guide edit template; keep black cell borders, blue safe-area rectangles, and neutral outside background, remove gray dashed centerlines and faint guide characters, and fill only safe-area interiors with chroma-key",
                            }
                        )
                    else:
                        registration_item["role"] = "registration guide edit template; keep black cell borders, blue safe-area rectangles, and neutral outside background, remove gray dashed centerlines and faint guide characters, and fill only safe-area interiors with chroma-key"
                    inputs[:] = [
                        item
                        for item in inputs
                        if not (isinstance(item, dict) and item.get("path") == registration_path)
                    ]
                    inputs.insert(0, registration_item)
        job["regenerated_action_prompts"] = regenerated_prompts

    completed_at = datetime.now(timezone.utc).isoformat()
    job["status"] = "complete"
    job["source_path"] = str(source)
    job["recorded_output"] = rel(output, run_dir)
    job["source_sha256"] = file_sha256(source)
    job["output_sha256"] = file_sha256(output)
    job["completed_at"] = completed_at

    write_json(manifest_path, manifest)
    write_json(jobs_path, jobs_manifest)
    print(str(output))


if __name__ == "__main__":
    main()
