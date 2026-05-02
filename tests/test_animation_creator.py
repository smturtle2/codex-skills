from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "skills" / "animation-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
DEFAULT_TEST_CHROMA = "#00FF00"
WAVE_BEATS = [
    "start in a relaxed friendly pose",
    "raise the right hand to shoulder height",
    "lift the right hand beside the head",
    "tilt the raised hand outward",
    "tilt the raised hand inward",
    "return to the relaxed friendly pose",
]

from animation_common import chroma_adjacent_count, fit_to_frame, recommended_grid, remove_chroma_background  # noqa: E402
from extract_frames import extract_component_frames, extract_slot_frames  # noqa: E402


class AnimationCreatorTests(unittest.TestCase):
    def run_script(self, script: str, *args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def make_grid(
        self,
        path: pathlib.Path,
        *,
        frames: int = len(WAVE_BEATS),
        size: int = 312,
        columns: int = 3,
        rows: int = 2,
        chroma: str | tuple[int, int, int] = DEFAULT_TEST_CHROMA,
        artifacts: bool = False,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (columns * size, rows * size), chroma)
        draw = ImageDraw.Draw(image)
        for index in range(frames):
            left = (index % columns) * size
            top = (index // columns) * size
            cx = left + size // 2
            cy = top + size // 2
            radius = 80 + index * 3
            if artifacts:
                draw.ellipse(
                    (cx - radius - 16, cy - radius - 10, cx + radius + 16, cy + radius + 18),
                    fill=(0, 180, 0),
                )
                for offset in range(24):
                    image.putpixel((left + 24 + offset, top + 30), (0, 190, 0))
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=(40, 120 + index * 10, 220),
                outline=(10, 20, 30),
                width=8,
            )
        image.save(path)

    def hex_to_rgb(self, value: str) -> tuple[int, int, int]:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))

    def test_project_local_prepare_and_end_to_end_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir) / "project"
            project.mkdir()
            codex_prepared_frame_actions = WAVE_BEATS

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--character-prompt",
                "a compact blue robot",
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(codex_prepared_frame_actions),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            self.assertTrue(run_dir.is_relative_to(project))
            self.assertEqual(run_dir.parent, project / "animation-runs")

            manifest_path = run_dir / "animation_manifest.json"
            jobs_path = run_dir / "animation-jobs.json"
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(jobs_path.is_file())
            self.assertTrue((run_dir / "prompts" / "base-character.md").is_file())
            self.assertTrue((run_dir / "prompts" / "actions" / "wave.md").is_file())
            self.assertFalse((run_dir / "references" / "layout-guides" / "wave.png").exists())
            expected_grid = recommended_grid(len(codex_prepared_frame_actions))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["animation"]["layout"]["columns"], expected_grid["columns"])
            self.assertEqual(manifest["animation"]["layout"]["rows"], expected_grid["rows"])
            self.assertEqual(manifest["animation"]["layout"]["working_cell_size"], expected_grid["working_cell_size"])
            self.assertEqual(manifest["animation"]["states"][0]["layout"]["order"], "left-to-right-top-to-bottom")
            self.assertEqual(manifest["animation"]["states"][0]["frames"], len(WAVE_BEATS))
            self.assertEqual(manifest["animation"]["states"][0]["frame_count"], len(WAVE_BEATS))
            self.assertEqual(manifest["animation"]["states"][0]["frame_actions"], WAVE_BEATS)
            self.assertEqual(manifest["animation"]["states"][0]["motion_beats"][0], {"frame": 1, "beat": WAVE_BEATS[0]})
            self.assertEqual(manifest["action_plans"]["wave"]["frame_actions"], WAVE_BEATS)
            self.assertEqual(manifest["frame_width"], 512)
            self.assertEqual(manifest["frame_height"], 512)
            self.assertEqual(manifest["background_mode"], "chroma-key")
            self.assertEqual(manifest["chroma_key_status"], "pending-canonical-base")
            self.assertNotIn("fps", manifest)
            self.assertNotIn("fps", manifest["animation"])
            self.assertTrue(manifest["loop"])
            self.assertEqual(manifest["actions"], ["wave"])
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            initial_jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            initial_wave_job = next(job for job in initial_jobs["jobs"] if job["id"] == "wave")
            self.assertEqual(initial_wave_job["status"], "blocked")
            self.assertEqual(initial_wave_job["prompt_status"], "pending-canonical-base")

            base_source = pathlib.Path(tmpdir) / "base-generated.png"
            base_image = Image.new("RGB", (312, 312), "#FFFFFF")
            ImageDraw.Draw(base_image).ellipse((180, 96, 332, 448), fill=(40, 120, 220), outline=(10, 20, 30), width=8)
            base_image.save(base_source)
            recorded_base = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "base-character",
                "--source",
                str(base_source),
                cwd=project,
            )
            self.assertEqual(recorded_base.returncode, 0, recorded_base.stderr)
            manifest_after_base = json.loads(manifest_path.read_text(encoding="utf-8"))
            selected_chroma = manifest_after_base["chroma_key"]
            selected_chroma_rgb = tuple(selected_chroma["rgb"])
            self.assertRegex(selected_chroma["hex"], r"^#[0-9A-F]{6}$")
            self.assertNotEqual(selected_chroma["hex"], "#FFFFFF")
            self.assertEqual(manifest_after_base["chroma_key_status"], "ready")
            registration_guide_path = run_dir / "references" / "registration-guides" / "wave.png"
            self.assertTrue(registration_guide_path.is_file())
            with Image.open(registration_guide_path) as guide:
                self.assertEqual(
                    guide.size,
                    (
                        expected_grid["columns"] * expected_grid["cell_width"],
                        expected_grid["rows"] * expected_grid["cell_height"],
                    ),
                )
            jobs_after_base = json.loads(jobs_path.read_text(encoding="utf-8"))
            base_job_after = next(job for job in jobs_after_base["jobs"] if job["id"] == "base-character")
            wave_job_after = next(job for job in jobs_after_base["jobs"] if job["id"] == "wave")
            self.assertEqual(wave_job_after["prompt_status"], "ready-after-canonical-base")
            self.assertTrue(wave_job_after["prompt_regenerated_after_base"])
            self.assertEqual(wave_job_after["chroma_key_hex"], selected_chroma["hex"])
            self.assertEqual(base_job_after["regenerated_action_prompts"], ["prompts/actions/wave.md"])

            prompt_result = self.run_script(
                "build_generation_prompt.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                cwd=project,
            )
            self.assertEqual(prompt_result.returncode, 0, prompt_result.stderr)
            self.assertIn("Input images:", prompt_result.stdout)
            self.assertIn("Reproduce those outer cell and inner safe-area border guidelines", prompt_result.stdout)
            self.assertIn("Reproduce the registration guide's visible outer cell borders and inner safe-area borders", prompt_result.stdout)
            self.assertIn("references/registration-guides/wave.png", prompt_result.stdout)
            self.assertNotIn("references/layout-guides/wave.png", prompt_result.stdout)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())

            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            self.make_grid(generated_source, chroma=selected_chroma_rgb, artifacts=True)
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(generated_source),
                cwd=project,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertTrue((run_dir / "generated" / "wave.png").is_file())

            result = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                cwd=project,
            )
            self.assertEqual(result.returncode, 0, f"finalize_animation_run.py\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

            frames = sorted((run_dir / "frames" / "wave").glob("*.png"))
            self.assertEqual(len(frames), len(codex_prepared_frame_actions))
            observed_sizes = []
            for frame_path in frames:
                with Image.open(frame_path) as frame:
                    self.assertEqual(frame.format, "PNG")
                    rgba = frame.convert("RGBA")
                    bbox = rgba.getbbox()
                    self.assertIsNotNone(bbox)
                    observed_sizes.append(bbox[2] - bbox[0])
                    self.assertEqual(chroma_adjacent_count(rgba, selected_chroma_rgb, 190), 0)
            self.assertEqual(observed_sizes, sorted(observed_sizes))
            self.assertTrue((run_dir / "final" / "wave-frames.webp").is_file())
            self.assertTrue((run_dir / "final" / "wave.webp").is_file())
            with Image.open(run_dir / "final" / "wave.webp") as animated:
                self.assertTrue(getattr(animated, "is_animated", False))
                self.assertEqual(getattr(animated, "n_frames", 1), len(codex_prepared_frame_actions))
            with Image.open(run_dir / "final" / "wave-frames.webp") as sheet:
                self.assertEqual(sheet.size, (312 * len(codex_prepared_frame_actions), 312))
            self.assertTrue((run_dir / "final" / "wave-validation.json").is_file())
            self.assertTrue((run_dir / "qa" / "wave-contact-sheet.png").is_file())
            self.assertTrue((run_dir / "qa" / "wave-review.json").is_file())
            self.assertTrue((run_dir / "qa" / "previews" / "wave.webp").is_file())
            self.assertTrue((run_dir / "qa" / "run-summary.json").is_file())
            validation = json.loads((run_dir / "final" / "wave-validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["ok"], validation)
            finalized_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                finalized_manifest["outputs"]["actions"]["wave"],
                {
                    "frames_dir": "frames/wave",
                    "composed_sheet": "final/wave-frames.webp",
                    "review": "qa/wave-review.json",
                    "validation": "final/wave-validation.json",
                    "contact_sheet": "qa/wave-contact-sheet.png",
                    "preview": "qa/previews/wave.webp",
                    "final_animation": "final/wave.webp",
                },
            )
            summary = json.loads((run_dir / "qa" / "run-summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["visual_review_required"])
            self.assertEqual(summary["visual_review_status"], "pending")

    def test_prepare_requires_frame_actions_for_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                cwd=project,
            )

            self.assertNotEqual(prepared.returncode, 0)
            self.assertIn("frame actions must be planned", prepared.stderr)

    def test_codex_prepared_frame_actions_finalize_frame_count_before_layout(self) -> None:
        codex_prepared_frame_actions = [
            "ready stance",
            "lean into the motion",
            "hit the main pose",
            "recover from the motion",
            "settle into the ending pose",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--action-id",
                "gesture",
                "--action",
                "short gesture",
                "--frame-count",
                "9",
                "--frame-actions",
                "; ".join(codex_prepared_frame_actions),
                cwd=project,
            )

            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            manifest = json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))
            state = manifest["animation"]["states"][0]
            self.assertEqual(state["frames"], 5)
            self.assertEqual(state["frame_count"], 5)
            self.assertEqual(state["frame_actions"], codex_prepared_frame_actions)
            self.assertEqual(state["layout"]["columns"], 3)
            self.assertEqual(state["layout"]["rows"], 2)
            self.assertFalse((run_dir / "references" / "layout-guides" / "gesture.png").exists())
            prompt = (run_dir / "prompts" / "actions" / "gesture.md").read_text(encoding="utf-8")
            self.assertIn("Output exactly 5", prompt)
            self.assertIn("Frame 5 ordering note: settle into the ending pose", prompt)

    def test_recommended_grid_sizes_fit_codex_imagegen_cell_budget(self) -> None:
        for frame_count in range(1, 17):
            grid = recommended_grid(frame_count)
            width = grid["columns"] * grid["cell_width"]
            height = grid["rows"] * grid["cell_height"]
            with self.subTest(frame_count=frame_count):
                self.assertEqual(grid["working_cell_size"], [512, 512])
                self.assertLessEqual(max(width, height) / min(width, height), 3)

    def test_motion_plan_length_overrides_deprecated_frame_count_hint(self) -> None:
        codex_prepared_frame_actions = [
            "idle ready stance",
            "shift weight backward in anticipation",
            "dip into a stronger crouch",
            "push off into the motion",
            "reach the first airborne key pose",
            "extend into the main action pose",
            "begin follow-through with hair and jacket trailing",
            "descend into recovery",
            "land with knees absorbing weight",
            "settle back toward the loop-ready stance",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.png"
            Image.new("RGB", (64, 64), "red").save(source_character)

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source_character),
                "--action-id",
                "leap",
                "--action",
                "full-body leap loop",
                "--frame-count",
                "2",
                "--frame-actions",
                "; ".join(codex_prepared_frame_actions),
                cwd=project,
            )

            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            manifest = json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))
            state = manifest["animation"]["states"][0]
            self.assertEqual(state["frames"], 10)
            self.assertEqual(state["frame_count"], 10)
            self.assertEqual(state["layout"]["columns"], 4)
            self.assertEqual(state["layout"]["rows"], 3)
            self.assertEqual(manifest["animation"]["layout"]["columns"], 4)
            self.assertEqual(manifest["animation"]["layout"]["rows"], 3)
            self.assertFalse((run_dir / "references" / "layout-guides" / "leap.png").exists())
            with Image.open(run_dir / "references" / "registration-guides" / "leap.png") as guide:
                self.assertEqual(guide.size, (2048, 1536))
            built_prompt = self.run_script(
                "build_generation_prompt.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "leap",
                cwd=project,
            )
            self.assertEqual(built_prompt.returncode, 0, built_prompt.stderr)
            self.assertIn("Input images:", built_prompt.stdout)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            generated_source = pathlib.Path(tmpdir) / "leap-generated.png"
            chroma = tuple(manifest["chroma_key"]["rgb"])
            self.make_grid(generated_source, frames=10, columns=4, rows=3, chroma=chroma)
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "leap",
                "--source",
                str(generated_source),
                cwd=project,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            finalized = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "leap",
                cwd=project,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            frames = sorted((run_dir / "frames" / "leap").glob("*.png"))
            self.assertEqual(len(frames), len(codex_prepared_frame_actions))
            with Image.open(frames[0]) as frame:
                self.assertEqual(frame.format, "PNG")
                self.assertEqual(frame.size, (312, 312))
            with Image.open(run_dir / "final" / "leap.webp") as animated:
                self.assertEqual(getattr(animated, "n_frames", 1), len(codex_prepared_frame_actions))

    def test_finalize_rejects_generated_sheet_with_wrong_guide_aspect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.png"
            Image.new("RGB", (64, 64), "red").save(source_character)
            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source_character),
                "--chroma-key",
                DEFAULT_TEST_CHROMA,
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "one; two; three; four; five; six; seven; eight",
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            self.assertFalse((run_dir / "references" / "layout-guides" / "wave.png").exists())
            with Image.open(run_dir / "references" / "registration-guides" / "wave.png") as guide:
                self.assertEqual(guide.size, (2048, 1024))

            generated_source = pathlib.Path(tmpdir) / "wrong-aspect.png"
            Image.new("RGB", (1672, 941), DEFAULT_TEST_CHROMA).save(generated_source)
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(generated_source),
                cwd=project,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)

            finalized = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                cwd=project,
            )

            self.assertNotEqual(finalized.returncode, 0)
            self.assertIn("does not match layout guide", finalized.stderr)

    def test_add_action_preserves_existing_completed_job_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.jpg"
            Image.new("RGB", (16, 16), "red").save(source_character, format="JPEG")

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source_character),
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            base_job = next(
                job
                for job in json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))["jobs"]
                if job["id"] == "base-character"
            )
            self.assertEqual(base_job["status"], "complete")
            self.assertTrue((run_dir / "references" / "canonical-base.png").is_file())
            self.assertFalse((run_dir / "generated" / "base-character.png").exists())
            with Image.open(run_dir / "references" / "canonical-base.png") as base_image:
                self.assertEqual(base_image.format, "PNG")
            self.assertEqual(base_job["recorded_output"], "references/canonical-base.png")
            self.assertIn("source_sha256", base_job)
            self.assertIn("output_sha256", base_job)
            self.assertNotIn("image_creator_prompt_file", base_job)

            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            chroma = tuple(json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))["chroma_key"]["rgb"])
            self.make_grid(generated_source, chroma=chroma)
            built_prompt = self.run_script(
                "build_generation_prompt.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                cwd=project,
            )
            self.assertEqual(built_prompt.returncode, 0, built_prompt.stderr)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(generated_source),
                cwd=project,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            before_jobs = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            before_wave = next(job for job in before_jobs["jobs"] if job["id"] == "wave")
            self.assertEqual(before_wave["status"], "complete")
            self.assertIn("source_sha256", before_wave)

            added = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--run-dir",
                str(run_dir),
                "--add-action",
                "--action-id",
                "jump",
                "--action",
                "jumping motion",
                "--frame-actions",
                "crouch; airborne; land",
                cwd=project,
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            after_jobs = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            after_wave = next(job for job in after_jobs["jobs"] if job["id"] == "wave")
            jump = next(job for job in after_jobs["jobs"] if job["id"] == "jump")
            self.assertEqual(after_wave["status"], "complete")
            self.assertEqual(after_wave["source_sha256"], before_wave["source_sha256"])
            self.assertEqual(after_wave["output_sha256"], before_wave["output_sha256"])
            self.assertEqual(jump["status"], "ready")

    def test_record_copies_generated_action_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.png"
            Image.new("RGB", (64, 64), "red").save(source_character)
            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source_character),
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            chroma = tuple(json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))["chroma_key"]["rgb"])
            self.make_grid(generated_source, chroma=chroma)
            built_prompt = self.run_script(
                "build_generation_prompt.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                cwd=project,
            )
            self.assertEqual(built_prompt.returncode, 0, built_prompt.stderr)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(generated_source),
                cwd=project,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            jobs = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            wave = next(job for job in jobs["jobs"] if job["id"] == "wave")
            self.assertEqual(wave["status"], "complete")
            self.assertEqual(wave["recorded_output"], "generated/wave.png")
            self.assertNotIn("decoded_path", wave)
            self.assertIn("source_sha256", wave)
            self.assertIn("output_sha256", wave)
            self.assertIn("image_creator_prompt_sha256", wave)

    def test_record_hashes_source_and_built_prompts_without_prompt_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.png"
            Image.new("RGB", (64, 64), "red").save(source_character)
            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source_character),
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            chroma = tuple(json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))["chroma_key"]["rgb"])
            self.make_grid(generated_source, chroma=chroma)

            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(generated_source),
                cwd=project,
            )

            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            jobs = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            wave = next(job for job in jobs["jobs"] if job["id"] == "wave")
            self.assertIn("prompt_sha256", wave)
            self.assertIn("image_creator_prompt_sha256", wave)
            self.assertNotIn("image_creator_prompt_file", wave)

    def test_fit_to_frame_keeps_safe_inset(self) -> None:
        source = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        ImageDraw.Draw(source).rectangle((0, 0, 79, 79), fill=(20, 100, 220, 255))

        fitted = fit_to_frame(source, (64, 64), padding=0)
        bbox = fitted.getbbox()

        self.assertEqual(bbox, (5, 5, 59, 59))

    def test_chroma_cleanup_keeps_embedded_character_color(self) -> None:
        source = Image.new("RGB", (96, 96), DEFAULT_TEST_CHROMA)
        draw = ImageDraw.Draw(source)
        draw.rectangle((28, 24, 68, 68), fill=(40, 120, 220))
        draw.rectangle((34, 56, 62, 64), fill=(0, 180, 0))
        draw.rectangle((42, 58, 54, 62), fill=DEFAULT_TEST_CHROMA)
        draw.rectangle((42, 44, 54, 50), fill=(180, 0, 90))
        draw.rectangle((18, 78, 78, 82), fill=(0, 180, 0))
        draw.rectangle((18, 84, 78, 86), fill=(14, 102, 14))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 47)), (180, 0, 90, 255))
        self.assertEqual(cleaned.getpixel((48, 60))[3], 0)
        self.assertEqual(cleaned.getpixel((36, 60))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 80))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 85))[3], 0)

    def test_validate_flags_chroma_adjacent_and_edge_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            frame_dir = project / "frames" / "animation"
            frame_dir.mkdir(parents=True)
            (project / "frames" / "frames-manifest.json").write_text(
                json.dumps({"rows": [{"state": "animation", "method": "slots"}]}),
                encoding="utf-8",
            )
            frame = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((8, 8, 20, 20), fill=(40, 120, 220, 255))
            draw.rectangle((0, 0, 3, 3), fill=(40, 120, 220, 255))
            draw.rectangle((22, 8, 24, 10), fill=(0, 180, 0, 255))
            frame.save(frame_dir / "000.png")

            result = self.run_script(
                "validate_animation.py",
                "--frames-root",
                str(project / "frames"),
                "--frame-size",
                "32x32",
                "--frame-count",
                "1",
                "--min-used-pixels",
                "1",
                "--edge-pixel-threshold",
                "1",
                "--chroma-adjacent-pixel-threshold",
                "1",
                "--require-components",
                "--json-out",
                str(project / "validation.json"),
                cwd=project,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout)
            validation = json.loads((project / "validation.json").read_text(encoding="utf-8"))
            self.assertFalse(validation["ok"])
            self.assertTrue(any("used extraction method slots" in error for error in validation["errors"]))
            self.assertTrue(any("close to the chroma key" in error for error in validation["errors"]))
            self.assertTrue(any("near the cell edge" in warning for warning in validation["warnings"]))
            self.assertGreater(validation["frames"][0]["chroma_adjacent_pixels"], 1)
            self.assertGreater(validation["frames"][0]["edge_pixels"], 1)

if __name__ == "__main__":
    unittest.main()
