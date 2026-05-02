#!/usr/bin/env python3
"""Finalize an animation-creator run after visual generation jobs are complete."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command))
    return subprocess.run(command, check=check, text=True)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def manifest_path(raw: object, *, run_dir: Path, field: str, job_id: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise SystemExit(f"job {job_id} has no {field}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    return path.resolve()


def action_job_ids(manifest: dict[str, object], action_id: str | None) -> list[str]:
    animation = manifest.get("animation")
    if not isinstance(animation, dict):
        raise SystemExit("animation_manifest.json is missing animation settings")
    states = animation.get("states")
    if not isinstance(states, list) or not states:
        raise SystemExit("animation_manifest.json is missing animation states")
    names = [str(state.get("name")) for state in states if isinstance(state, dict) and state.get("name")]
    if action_id:
        if action_id not in names:
            raise SystemExit(f"unknown action/state id: {action_id}")
        return [action_id]
    return names


def validate_completed_jobs(run_dir: Path, job_ids: set[str]) -> None:
    jobs_manifest = load_json(run_dir / "animation-jobs.json")
    jobs = jobs_manifest.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("animation-jobs.json is missing a jobs list")
    jobs_by_id = {str(job.get("id")): job for job in jobs if isinstance(job, dict)}
    missing = sorted(job_ids - set(jobs_by_id))
    if missing:
        raise SystemExit("animation jobs are missing: " + ", ".join(missing))
    incomplete = [
        job_id
        for job_id in sorted(job_ids)
        if jobs_by_id[job_id].get("status", "pending") != "complete"
    ]
    if incomplete:
        raise SystemExit("animation jobs are not complete: " + ", ".join(incomplete))
    for job_id in sorted(job_ids):
        job = jobs_by_id[job_id]
        source = manifest_path(job.get("source_path"), run_dir=run_dir, field="source_path", job_id=job_id)
        output = manifest_path(job.get("output_path"), run_dir=run_dir, field="output_path", job_id=job_id)
        if not source.is_file():
            raise SystemExit(f"job {job_id} source image is missing: {source}")
        if not output.is_file():
            raise SystemExit(f"job {job_id} recorded output is missing: {output}")


def validation_failures(review: dict[str, object]) -> list[str]:
    errors = review.get("errors")
    if isinstance(errors, list) and errors:
        return [str(error) for error in errors]
    return ["validation did not pass"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--action-id", help="Finalize one action/state. Defaults to every action in the run.")
    parser.add_argument("--skip-preview", action="store_true")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest_path = run_dir / "animation_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"animation manifest not found: {manifest_path}")
    manifest = load_json(manifest_path)
    job_ids = set(action_job_ids(manifest, args.action_id))
    validate_completed_jobs(run_dir, job_ids)

    final_dir = run_dir / "final"
    qa_dir = run_dir / "qa"
    final_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    action_args = ["--action-id", args.action_id] if args.action_id else []

    run(
        [
            sys.executable,
            str(scripts_dir / "extract_frames.py"),
            "--run-dir",
            str(run_dir),
            *action_args,
            "--method",
            "auto",
        ]
    )

    review_path = qa_dir / (f"{args.action_id}-review.json" if args.action_id else "review.json")
    validate_command = [
        sys.executable,
        str(scripts_dir / "validate_animation.py"),
        "--run-dir",
        str(run_dir),
        *action_args,
        "--json-out",
        str(review_path),
    ]
    run(validate_command, check=False)
    review = load_json(review_path)
    if not review.get("ok"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "review": str(review_path),
                    "repair_hint": "Regenerate the failed action grid with $image-creator, record it, then finalize again.",
                    "failures": validation_failures(review),
                },
                indent=2,
            )
        )
        raise SystemExit(1)

    composed_path = final_dir / (f"{args.action_id}-frames.webp" if args.action_id else "animation-frames.webp")
    run(
        [
            sys.executable,
            str(scripts_dir / "compose_animation.py"),
            "--run-dir",
            str(run_dir),
            *action_args,
            "--output",
            str(composed_path),
        ]
    )

    validation_path = final_dir / (f"{args.action_id}-validation.json" if args.action_id else "validation.json")
    run(
        [
            sys.executable,
            str(scripts_dir / "validate_animation.py"),
            "--run-dir",
            str(run_dir),
            *action_args,
            "--sheet",
            str(composed_path),
            "--json-out",
            str(validation_path),
        ]
    )

    contact_sheet_path = qa_dir / (f"{args.action_id}-contact-sheet.png" if args.action_id else "contact-sheet.png")
    run(
        [
            sys.executable,
            str(scripts_dir / "make_contact_sheet.py"),
            "--run-dir",
            str(run_dir),
            *action_args,
            "--sheet",
            str(composed_path),
            "--output",
            str(contact_sheet_path),
        ]
    )

    final_animations = [str(final_dir / f"{job_id}.webp") for job_id in sorted(job_ids)]
    preview_dir = qa_dir / "previews"
    if not args.skip_preview:
        run(
            [
                sys.executable,
                str(scripts_dir / "render_preview.py"),
                "--run-dir",
                str(run_dir),
                *action_args,
                "--formats",
                "webp",
                "--write-final",
            ]
        )

    summary = {
        "ok": True,
        "run_dir": str(run_dir),
        "actions": sorted(job_ids),
        "composed_sheet": str(composed_path),
        "review": str(review_path),
        "validation": str(validation_path),
        "contact_sheet": str(contact_sheet_path),
        "preview_dir": None if args.skip_preview else str(preview_dir),
        "final_animations": [] if args.skip_preview else final_animations,
        "visual_review_required": True,
        "visual_review_status": "pending",
    }
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    action_outputs = outputs.get("actions")
    if not isinstance(action_outputs, dict):
        action_outputs = {}
    for job_id in sorted(job_ids):
        action_outputs[job_id] = {
            "frames_dir": f"frames/{job_id}",
            "composed_sheet": f"final/{job_id}-frames.webp",
            "review": f"qa/{job_id}-review.json",
            "validation": f"final/{job_id}-validation.json",
            "contact_sheet": f"qa/{job_id}-contact-sheet.png",
            "preview": None if args.skip_preview else f"qa/previews/{job_id}.webp",
            "final_animation": None if args.skip_preview else f"final/{job_id}.webp",
        }
    outputs["actions"] = action_outputs
    if not args.action_id:
        outputs["aggregate"] = {
            "composed_sheet": rel(composed_path, run_dir),
            "validation": rel(validation_path, run_dir),
            "contact_sheet": rel(contact_sheet_path, run_dir),
        }
    manifest["outputs"] = outputs
    write_json(manifest_path, manifest)

    summary_path = qa_dir / "run-summary.json"
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
