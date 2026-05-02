#!/usr/bin/env python3
"""Print the exact $image-creator prompt for one animation generation job."""

from __future__ import annotations

import argparse
from pathlib import Path

from animation_common import load_json


def job_by_id(run_dir: Path, job_id: str) -> dict[str, object]:
    jobs_manifest = load_json(run_dir / "animation-jobs.json")
    jobs = jobs_manifest.get("jobs")
    if not isinstance(jobs, list):
        raise SystemExit("animation-jobs.json is missing a jobs list")
    for job in jobs:
        if isinstance(job, dict) and job.get("id") == job_id:
            return job
    raise SystemExit(f"unknown generation job: {job_id}")


def resolve_run_path(run_dir: Path, value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"job is missing {field}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    return path.resolve()


def run_relative(path: Path, run_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def build_prompt(run_dir: Path, job: dict[str, object]) -> str:
    prompt_path = resolve_run_path(run_dir, job.get("prompt_file"), field="prompt_file")
    if not prompt_path.is_file():
        raise SystemExit(f"prompt file not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    input_images = job.get("input_images")
    if not isinstance(input_images, list) or not input_images:
        return prompt + "\n"

    lines = [prompt, "", "Input images:"]
    for item in input_images:
        if not isinstance(item, dict):
            continue
        path_value = item.get("path")
        role = str(item.get("role") or "input image")
        image_path = resolve_run_path(run_dir, path_value, field="input_images.path")
        if not image_path.is_file():
            raise SystemExit(f"input image not found: {image_path}")
        lines.append(f"- {run_relative(image_path, run_dir)}: {role}.")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    job = job_by_id(run_dir, args.job_id)
    prompt = build_prompt(run_dir, job)
    print(prompt, end="")


if __name__ == "__main__":
    main()
