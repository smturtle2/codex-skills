#!/usr/bin/env python3
"""Record a generated base character or action grid into an animation run."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from animation_common import load_json, manifest_for_run, write_json


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


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

    output_raw = job.get("output_path")
    if not isinstance(output_raw, str):
        raise SystemExit(f"job {args.job_id} has no output_path")
    output = run_dir / output_raw
    if output.exists() and not args.force:
        raise SystemExit(f"{output} already exists; pass --force to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != output.resolve():
        shutil.copy2(source, output)

    if args.job_id == "base-character":
        canonical_raw = job.get("canonical_output_path", "references/canonical-base.png")
        if not isinstance(canonical_raw, str):
            raise SystemExit("base-character job has invalid canonical_output_path")
        canonical = run_dir / canonical_raw
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, canonical)
        manifest["canonical_base"] = rel(canonical, run_dir)
        for other_job in job_list(jobs_manifest):
            if other_job.get("kind") in {"action-grid", "action-strip"} and other_job.get("status") == "blocked":
                other_job["status"] = "ready"

    completed_at = datetime.now(timezone.utc).isoformat()
    job["status"] = "complete"
    job["source_path"] = str(source)
    job["recorded_output"] = rel(output, run_dir)
    job["source_sha256"] = file_sha256(source)
    job["output_sha256"] = file_sha256(output)
    job["completed_at"] = completed_at

    write_json(manifest_path, manifest)
    write_json(run_dir / "animation_request.json", manifest)
    write_json(jobs_path, jobs_manifest)
    print(str(output))


if __name__ == "__main__":
    main()
