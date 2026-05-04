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

from animation_common import (  # noqa: E402
    chroma_adjacent_count,
    estimate_edge_background_color,
    estimate_background_thresholds,
    fit_to_frame,
    recommended_grid,
    remove_chroma_background,
)
from extract_frames import character_components, connected_components, detect_chroma_rect_in_slot  # noqa: E402

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
        guide_canvas: bool = False,
        guide_line_width: int = 2,
        guide_line_color: str = "#2f80ed",
        guide_safe_fill: str | tuple[int, int, int] | None = None,
        guide_inner_edge_fragments: bool = False,
        extra_slot_content_indexes: set[int] | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (columns * size, rows * size), "#f7f7f7" if guide_canvas else chroma)
        draw = ImageDraw.Draw(image)
        extra_slot_content_indexes = extra_slot_content_indexes or set()
        total_slots = columns * rows
        for index in range(total_slots if guide_canvas else frames):
            left = (index % columns) * size
            top = (index // columns) * size
            safe_x = round(30 * size / 512)
            safe_y = round(24 * size / 512)
            if guide_canvas:
                draw.rectangle((left, top, left + size - 1, top + size - 1), outline="#111111", width=guide_line_width)
                draw.rectangle(
                    (left + safe_x, top + safe_y, left + size - safe_x - 1, top + size - safe_y - 1),
                    fill=guide_safe_fill or chroma,
                    outline=guide_line_color,
                    width=guide_line_width,
                )
                cx_line = left + size // 2
                cy_line = top + size // 2
                for yy in range(top + safe_y, top + size - safe_y, 16):
                    draw.line((cx_line, yy, cx_line, min(yy + 7, top + size - safe_y)), fill="#b8b8b8", width=guide_line_width)
                for xx in range(left + safe_x, left + size - safe_x, 16):
                    draw.line((xx, cy_line, min(xx + 7, left + size - safe_x), cy_line), fill="#b8b8b8", width=guide_line_width)
                if guide_inner_edge_fragments:
                    edge_y = top + safe_y
                    fragment_start = left + safe_x + 4
                    fragment_end = left + size - safe_x - 4
                    for xx in range(fragment_start, fragment_end, 48):
                        draw.line((xx, edge_y, min(xx + 35, fragment_end), edge_y), fill="#111111", width=1)
            if index >= frames and index not in extra_slot_content_indexes:
                continue
            cx = left + size // 2
            cy = top + size // 2
            radius = 80 + index * 3
            if index in extra_slot_content_indexes:
                radius = 96
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
                guide_rgb = guide.convert("RGB")
                self.assertNotEqual(guide_rgb.getpixel((34, 28)), selected_chroma_rgb)
                self.assertNotEqual(guide_rgb.getpixel((4, 4)), selected_chroma_rgb)
                dashed_samples = [
                    guide_rgb.getpixel((256, y))
                    for y in range(24, 96)
                ]
                self.assertTrue(any(max(pixel) - min(pixel) <= 8 and 150 <= pixel[0] <= 210 for pixel in dashed_samples))
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
            self.assertIn("Edit the attached registration guide into the animation action sheet", prompt_result.stdout)
            self.assertIn("Keep unchanged: canvas size, grid layout, black cell borders, blue safe-area rectangles", prompt_result.stdout)
            self.assertIn("Remove from the generated result: gray dashed centerlines and faint guide characters", prompt_result.stdout)
            self.assertIn("This is a delta-based cumulative animation plan", prompt_result.stdout)
            self.assertIn("accumulated result of all previous frame changes", prompt_result.stdout)
            self.assertIn("Anchor the character to the same registration point in every slot", prompt_result.stdout)
            self.assertIn("Fill only the inside of each requested slot's blue safe-area rectangle", prompt_result.stdout)
            self.assertNotIn("placement reference only, not as the output canvas", prompt_result.stdout)
            self.assertNotIn("Preserve/recreate the registration guide's visible outer cell borders", prompt_result.stdout)
            self.assertIn("references/registration-guides/wave.png", prompt_result.stdout)
            self.assertNotIn("references/layout-guides/wave.png", prompt_result.stdout)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())

            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            self.make_grid(generated_source, chroma=selected_chroma_rgb, guide_canvas=True)
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
            self.assertTrue((run_dir / "final" / "wave-frames.png").is_file())
            self.assertFalse((run_dir / "final" / "wave-frames.webp").exists())
            self.assertTrue((run_dir / "final" / "wave.webp").is_file())
            with Image.open(run_dir / "final" / "wave.webp") as animated:
                self.assertTrue(getattr(animated, "is_animated", False))
                self.assertEqual(getattr(animated, "n_frames", 1), len(codex_prepared_frame_actions))
            with Image.open(run_dir / "final" / "wave-frames.png") as sheet:
                self.assertEqual(sheet.format, "PNG")
                self.assertEqual(sheet.size, (312 * len(codex_prepared_frame_actions), 312))
            self.assertTrue((run_dir / "final" / "wave-validation.json").is_file())
            self.assertTrue((run_dir / "qa" / "wave-contact-sheet.png").is_file())
            self.assertTrue((run_dir / "qa" / "wave-review.json").is_file())
            self.assertFalse((run_dir / "qa" / "previews" / "wave.webp").exists())
            self.assertTrue((run_dir / "qa" / "run-summary.json").is_file())
            validation = json.loads((run_dir / "final" / "wave-validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["ok"], validation)
            summary = json.loads((run_dir / "qa" / "run-summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["visual_review_required"])
            self.assertEqual(summary["visual_review_status"], "pending")
            self.assertEqual(summary["composed_sheet"], str(run_dir / "final" / "wave-frames.png"))
            self.assertIsNone(summary["preview_dir"])

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
            self.assertIn("Frame 1: ready stance", prompt)
            self.assertIn("Frame 5: settle into the ending pose", prompt)
            self.assertIn("final audited result of a sequential one-beat-at-a-time planning pass", prompt)
            self.assertIn("missing transition beats were added, redundant duplicate beats were removed", prompt)
            self.assertIn("accumulated result of all previous frame changes", prompt)
            self.assertIn("what visibly changed from the immediately previous slot", prompt)
            self.assertIn("Motion arcs, speed lines, motion trails, motion marks, wave arcs", prompt)
            self.assertIn("every effect pixel must be fully opaque", prompt)
            self.assertIn("Do not draw translucent or faded effects", prompt)
            self.assertNotIn("Slots F6 must contain no character", prompt)
            self.assertNotIn("Fill only slots F1-F5", prompt)
            self.assertNotIn("Do not include any ground plane, floor line, cast shadow, contact shadow, oval floor shadow, landing mark, dust, glow, speed line", prompt)
            self.assertNotIn("for example", prompt.lower())
            self.assertNotIn("few-shot", prompt.lower())

    def test_prepare_records_unused_grid_slots_without_prompting_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            frame_actions = [
                "ready stance",
                "lower the body",
                "move through the middle of the action",
                "recover toward balance",
                "settle into the ending pose",
            ]

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
                "--frame-actions",
                "; ".join(frame_actions),
                cwd=project,
            )

            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            manifest = json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))
            layout = manifest["animation"]["states"][0]["layout"]
            self.assertEqual(layout["columns"], 3)
            self.assertEqual(layout["rows"], 2)
            self.assertEqual(layout["unused_slots"], [6])
            prompt = (run_dir / "prompts" / "actions" / "gesture.md").read_text(encoding="utf-8")
            self.assertIn("Output exactly 5 separate full-body animation frames", prompt)
            self.assertIn("Frame 5: settle into the ending pose", prompt)
            self.assertNotIn("Slots F6", prompt)
            self.assertNotIn("unused slots", prompt.lower())

    def test_prepare_rejects_excess_frame_actions_with_review_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--action-id",
                "too-long",
                "--action",
                "overplanned motion",
                "--frame-actions",
                "; ".join(f"beat {index}" for index in range(17)),
                cwd=project,
            )

            self.assertNotEqual(prepared.returncode, 0)
            self.assertIn("review the sequential plan", prepared.stderr)
            self.assertIn("delete or merge excessive duplicate beats", prepared.stderr)

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
                guide_rgb = guide.convert("RGB")
                self.assertNotEqual(guide_rgb.getpixel((34, 28)), (0, 255, 0))
                self.assertNotEqual(guide_rgb.getpixel((4, 4)), (0, 255, 0))

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

    def test_finalize_accepts_visible_registration_guide_base_sheet(self) -> None:
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
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = project / "wave-generated.png"
            self.make_grid(generated_source, chroma=DEFAULT_TEST_CHROMA, guide_canvas=True, guide_line_width=5)

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

            self.assertEqual(finalized.returncode, 0, finalized.stderr + finalized.stdout)
            review = json.loads((run_dir / "qa" / "wave-review.json").read_text(encoding="utf-8"))
            self.assertTrue(review["ok"], review)
            frame_manifest = json.loads((run_dir / "frames" / "frames-manifest.json").read_text(encoding="utf-8"))
            row = frame_manifest["rows"][0]
            self.assertEqual(row["method"], "components")
            self.assertEqual(row["guide_erase_policy"], "detected-safe-area-inner-box")
            self.assertTrue(row["detected_safe_boxes"])
            self.assertTrue(
                all(box["source"] == "detected-safe-area-inner-fill" for box in row["detected_safe_boxes"].values())
            )

    def test_finalize_removes_connected_neutral_safe_area_canvas(self) -> None:
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
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = project / "wave-generated.png"
            self.make_grid(
                generated_source,
                chroma=DEFAULT_TEST_CHROMA,
                guide_canvas=True,
                guide_line_width=5,
                guide_safe_fill="#FFFFFF",
                guide_inner_edge_fragments=True,
            )

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

            self.assertEqual(finalized.returncode, 0, finalized.stderr + finalized.stdout)
            for frame_path in sorted((run_dir / "frames" / "wave").glob("*.png")):
                with Image.open(frame_path) as frame:
                    rgba = frame.convert("RGBA")
                    alpha = rgba.getchannel("A")
                    wide_rows = [
                        y
                        for y in range(rgba.height)
                        if sum(
                            1
                            for x in range(rgba.width)
                            if alpha.getpixel((x, y)) > 0
                            and min(rgba.getpixel((x, y))[:3]) >= 232
                            and max(rgba.getpixel((x, y))[:3]) - min(rgba.getpixel((x, y))[:3]) <= 32
                        )
                        > rgba.width * 0.20
                    ]
                    self.assertFalse(wide_rows, f"{frame_path.name} retained guide canvas rows {wide_rows[:8]}")
                    dark_rows = [
                        y
                        for y in range(rgba.height)
                        if sum(
                            1
                            for x in range(rgba.width)
                            if alpha.getpixel((x, y)) > 0 and max(rgba.getpixel((x, y))[:3]) < 80
                        )
                        > rgba.width * 0.45
                    ]
                    self.assertFalse(dark_rows, f"{frame_path.name} retained guide edge rows {dark_rows[:8]}")

    def test_finalize_detects_non_blue_registration_safe_area_lines(self) -> None:
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
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = project / "wave-generated.png"
            self.make_grid(
                generated_source,
                chroma=DEFAULT_TEST_CHROMA,
                guide_canvas=True,
                guide_line_width=5,
                guide_line_color="#777777",
            )

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

            self.assertEqual(finalized.returncode, 0, finalized.stderr + finalized.stdout)
            frame_manifest = json.loads((run_dir / "frames" / "frames-manifest.json").read_text(encoding="utf-8"))
            row = frame_manifest["rows"][0]
            self.assertEqual(row["guide_erase_policy"], "detected-safe-area-inner-box")
            self.assertTrue(row["detected_safe_boxes"])
            self.assertTrue(
                all(box["source"] == "detected-safe-area-inner-fill" for box in row["detected_safe_boxes"].values())
            )

    def test_finalize_ignores_generated_content_in_unused_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            source_character = project / "source.png"
            Image.new("RGB", (64, 64), "red").save(source_character)
            frame_actions = [
                "ready stance",
                "lower the body",
                "move through the middle of the action",
                "recover toward balance",
                "settle into the ending pose",
            ]
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
                "gesture",
                "--action",
                "short gesture",
                "--frame-actions",
                "; ".join(frame_actions),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            generated_source = project / "gesture-generated.png"
            self.make_grid(
                generated_source,
                frames=len(frame_actions),
                columns=3,
                rows=2,
                chroma=DEFAULT_TEST_CHROMA,
                guide_canvas=True,
                extra_slot_content_indexes={5},
            )
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "gesture",
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
                "gesture",
                cwd=project,
            )

            self.assertEqual(finalized.returncode, 0, finalized.stderr + finalized.stdout)
            review = json.loads((run_dir / "qa" / "gesture-review.json").read_text(encoding="utf-8"))
            self.assertTrue(review["ok"], review)
            frames = sorted((run_dir / "frames" / "gesture").glob("*.png"))
            self.assertEqual(len(frames), len(frame_actions))
            frame_manifest = json.loads((run_dir / "frames" / "frames-manifest.json").read_text(encoding="utf-8"))
            row = frame_manifest["rows"][0]
            self.assertEqual(row["method"], "components")
            self.assertEqual(len(row["unused_slots"]), 1)
            self.assertGreater(row["unused_slots"][0]["nontransparent_pixels"], 0)

    def test_component_extraction_ignores_safe_area_line_remnants(self) -> None:
        image = Image.new("RGBA", (624, 312), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        layout = {
            "columns": 2,
            "rows": 1,
            "cell_width": 512,
            "cell_height": 512,
            "safe_margin_x": 30,
            "safe_margin_y": 24,
        }
        safe_x = round(30 * 312 / 512)
        draw.ellipse((90, 80, 210, 240), fill=(40, 120, 220, 255), outline=(10, 20, 30, 255), width=6)
        draw.line((312 - safe_x, 20, 312 - safe_x, 292), fill=(47, 128, 237, 255), width=2)

        components = character_components(connected_components(image), image, layout)

        self.assertEqual(len(components), 1)
        self.assertLess(components[0]["bbox"][2], 312 - safe_x)

    def test_chroma_rect_detector_finds_red_safe_area_and_ignores_blue_guide(self) -> None:
        cell = Image.new("RGB", (128, 128), "#f7f7f7")
        draw = ImageDraw.Draw(cell)
        draw.rectangle((0, 0, 127, 127), outline="#000000", width=2)
        draw.rectangle((10, 8, 118, 120), outline="#286DFF", width=3)
        draw.rectangle((14, 12, 114, 116), fill=(244, 2, 2))
        draw.rectangle((42, 36, 84, 92), fill=(40, 120, 220))
        draw.rectangle((1, 60, 126, 62), fill="#111111")

        box = detect_chroma_rect_in_slot(
            cell,
            (255, 0, 0),
            expected_left=10,
            expected_top=8,
            expected_right=118,
            expected_bottom=120,
        )

        self.assertIsNotNone(box)
        assert box is not None
        self.assertLessEqual(abs(box[0] - 14), 8)
        self.assertLessEqual(abs(box[1] - 12), 8)
        self.assertLessEqual(abs(box[2] - 115), 8)
        self.assertLessEqual(abs(box[3] - 117), 8)

    def test_chroma_rect_detector_rejects_unrelated_saturated_rectangle(self) -> None:
        cell = Image.new("RGB", (128, 128), "#f7f7f7")
        draw = ImageDraw.Draw(cell)
        draw.rectangle((14, 12, 114, 116), fill=(30, 80, 245))

        box = detect_chroma_rect_in_slot(
            cell,
            (255, 0, 0),
            expected_left=10,
            expected_top=8,
            expected_right=118,
            expected_bottom=120,
        )

        self.assertIsNone(box)

    def test_edge_background_fallback_rejects_unrelated_saturated_border(self) -> None:
        source = Image.new("RGBA", (80, 80), (255, 0, 0, 255))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 79, 2), fill=(30, 80, 245, 255))
        draw.rectangle((0, 77, 79, 79), fill=(30, 80, 245, 255))
        draw.rectangle((0, 0, 2, 79), fill=(30, 80, 245, 255))
        draw.rectangle((77, 0, 79, 79), fill=(30, 80, 245, 255))

        self.assertEqual(estimate_edge_background_color(source, (255, 0, 0)), (255, 0, 0))

    def test_background_threshold_uses_user_threshold(self) -> None:
        source = Image.new("RGBA", (80, 80), (244, 2, 2, 255))

        low = estimate_background_thresholds(source, (244, 2, 2), 64)
        high = estimate_background_thresholds(source, (244, 2, 2), 96)

        self.assertLess(low["possible"], high["possible"])
        self.assertLessEqual(low["possible"], 64)
        self.assertGreaterEqual(high["possible"], 96 * 0.65)

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
            self.assertEqual(base_job["regenerated_action_prompts"], ["prompts/actions/wave.md"])
            self.assertNotIn("image_creator_prompt_file", base_job)
            manifest = json.loads((run_dir / "animation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["chroma_key_status"], "ready")
            self.assertTrue((run_dir / "references" / "registration-guides" / "wave.png").is_file())
            jobs_after_prepare = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            wave_after_prepare = next(job for job in jobs_after_prepare["jobs"] if job["id"] == "wave")
            self.assertEqual(wave_after_prepare["status"], "ready")
            self.assertEqual(wave_after_prepare["prompt_status"], "ready-after-canonical-base")
            self.assertTrue(wave_after_prepare["prompt_regenerated_after_base"])

            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            chroma = tuple(manifest["chroma_key"]["rgb"])
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
            self.assertIn("Edit the attached registration guide into the animation action sheet", built_prompt.stdout)
            self.assertIn("references/registration-guides/wave.png", built_prompt.stdout)
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
            self.assertIn("prompt_sha256", wave)
            self.assertIn("source_sha256", wave)
            self.assertIn("output_sha256", wave)
            self.assertIn("image_creator_prompt_sha256", wave)
            self.assertFalse((run_dir / "prompts" / "image-creator").exists())
            self.assertNotIn("image_creator_prompt_file", wave)

    def test_record_accepts_generated_source_already_at_expected_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
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
                "; ".join(WAVE_BEATS),
                cwd=project,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            expected_output = run_dir / "generated" / "base-character.png"
            expected_output.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (96, 96), "#FFFFFF").save(expected_output)

            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "base-character",
                "--source",
                str(expected_output),
                cwd=project,
            )

            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            jobs = json.loads((run_dir / "animation-jobs.json").read_text(encoding="utf-8"))
            base_job = next(job for job in jobs["jobs"] if job["id"] == "base-character")
            self.assertEqual(base_job["status"], "complete")
            self.assertEqual(base_job["recorded_output"], "generated/base-character.png")
            self.assertTrue((run_dir / "references" / "canonical-base.png").is_file())

    def test_fit_to_frame_keeps_safe_inset(self) -> None:
        source = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        ImageDraw.Draw(source).rectangle((0, 0, 79, 79), fill=(20, 100, 220, 255))

        fitted = fit_to_frame(source, (64, 64), padding=0)
        bbox = fitted.getbbox()

        self.assertEqual(bbox, (5, 5, 59, 59))

    def test_chroma_cleanup_uses_connected_background_without_deleting_pixels(self) -> None:
        source = Image.new("RGB", (96, 96), DEFAULT_TEST_CHROMA)
        draw = ImageDraw.Draw(source)
        draw.rectangle((28, 24, 68, 68), fill=(40, 120, 220))
        draw.rectangle((44, 30, 48, 34), fill=(0, 150, 0))
        draw.rectangle((52, 30, 56, 34), fill=(0, 190, 190))
        draw.rectangle((34, 56, 62, 64), fill=(0, 150, 0))
        draw.rectangle((42, 58, 54, 62), fill=DEFAULT_TEST_CHROMA)
        draw.rectangle((42, 44, 54, 50), fill=(180, 0, 90))
        draw.rectangle((18, 78, 78, 82), fill=(0, 150, 0))
        draw.rectangle((18, 84, 78, 86), fill=(14, 102, 14))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)
        self.assertGreater(cleaned.getpixel((46, 32))[3], 0)
        self.assertEqual(cleaned.getpixel((54, 32)), (0, 190, 190, 255))
        self.assertEqual(cleaned.getpixel((48, 47)), (180, 0, 90, 255))
        self.assertEqual(cleaned.getpixel((48, 60))[3], 0)
        self.assertGreater(cleaned.getpixel((36, 60))[3], 0)
        self.assertLess(cleaned.getpixel((48, 80))[3], 255)
        self.assertGreater(cleaned.getpixel((48, 85))[3], 0)
        self.assertLess(cleaned.getpixel((48, 85))[1], 40)
        self.assertEqual(chroma_adjacent_count(cleaned, (0, 255, 0), 190), 0)

    def test_chroma_cleanup_uses_per_component_background_color(self) -> None:
        source = Image.new("RGB", (128, 64), (0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 61, 63), fill=(0, 255, 0))
        draw.rectangle((66, 0, 127, 63), fill=(12, 242, 8))
        draw.rectangle((18, 18, 43, 47), fill=(40, 120, 220))
        draw.rectangle((84, 18, 109, 47), fill=(40, 120, 220))
        draw.rectangle((30, 30, 35, 35), fill=(0, 190, 190))
        draw.rectangle((96, 30, 101, 35), fill=(0, 190, 190))
        draw.rectangle((22, 24, 23, 41), fill=(40, 190, 80))
        draw.rectangle((104, 24, 105, 41), fill=(50, 180, 70))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)
        self.assertEqual(cleaned.getpixel((124, 4))[3], 0)
        self.assertEqual(cleaned.getpixel((32, 32)), (0, 190, 190, 255))
        self.assertEqual(cleaned.getpixel((98, 32)), (0, 190, 190, 255))
        self.assertEqual(cleaned.getpixel((22, 32)), (40, 190, 80, 255))
        self.assertEqual(cleaned.getpixel((104, 32)), (50, 180, 70, 255))

    def test_chroma_cleanup_estimates_non_green_background_from_edges(self) -> None:
        source = Image.new("RGB", (96, 96), (42, 80, 238))
        draw = ImageDraw.Draw(source)
        draw.rectangle((26, 22, 70, 70), fill=(240, 210, 90))
        draw.rectangle((44, 34, 52, 42), fill=(44, 78, 232))
        draw.rectangle((42, 50, 54, 56), fill=(180, 0, 160))
        draw.rectangle((36, 62, 60, 64), fill=(42, 80, 238))
        draw.rectangle((28, 28, 34, 34), fill=(42, 90, 210))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 38))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 53)), (180, 0, 160, 255))
        self.assertGreater(cleaned.getpixel((31, 31))[3], 0)
        self.assertEqual(cleaned.getpixel((48, 63))[3], 0)

    def test_chroma_cleanup_uses_key_strength_for_dark_edge_pixels(self) -> None:
        for background, edge_color in (
            ((244, 2, 2), (150, 20, 9)),
            ((2, 224, 28), (24, 140, 30)),
            ((30, 54, 240), (22, 42, 144)),
        ):
            with self.subTest(background=background):
                source = Image.new("RGB", (80, 80), background)
                draw = ImageDraw.Draw(source)
                draw.rectangle((28, 22, 56, 58), fill=(70, 80, 95))
                draw.rectangle((26, 24, 27, 56), fill=edge_color)
                draw.rectangle((57, 24, 58, 56), fill=edge_color)
                draw.rectangle((38, 36, 44, 42), fill=edge_color)

                cleaned = remove_chroma_background(source, (0, 255, 0), 96)

                self.assertEqual(cleaned.getpixel((4, 4))[3], 0)
                self.assertLess(cleaned.getpixel((26, 40))[3], 255)
                self.assertLess(cleaned.getpixel((57, 40))[3], 255)
                self.assertEqual(cleaned.getpixel((41, 39)), (*edge_color, 255))
                self.assertEqual(cleaned.getpixel((42, 50)), (70, 80, 95, 255))

    def test_chroma_cleanup_removes_exterior_connected_dark_key_components(self) -> None:
        source = Image.new("RGB", (80, 80), (244, 2, 2))
        draw = ImageDraw.Draw(source)
        draw.rectangle((24, 20, 58, 58), fill=(70, 80, 95))
        draw.rectangle((20, 32, 24, 42), fill=(152, 20, 9))
        draw.rectangle((36, 34, 42, 40), fill=(152, 20, 9))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertLess(cleaned.getpixel((22, 37))[3], 255)
        self.assertEqual(cleaned.getpixel((39, 37)), (152, 20, 9, 255))

    def test_chroma_cleanup_removes_small_internal_dark_key_remnants(self) -> None:
        source = Image.new("RGB", (80, 80), (244, 2, 2))
        draw = ImageDraw.Draw(source)
        draw.rectangle((24, 20, 58, 58), fill=(70, 80, 95))
        draw.rectangle((25, 34, 27, 36), fill=(152, 20, 9))
        draw.rectangle((42, 34, 48, 40), fill=(152, 20, 9))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertEqual(cleaned.getpixel((26, 35)), (152, 20, 9, 255))
        self.assertEqual(cleaned.getpixel((45, 37)), (152, 20, 9, 255))

    def test_chroma_cleanup_preserves_internal_key_direction_details(self) -> None:
        body_color = (70, 80, 95)
        for background in ((244, 2, 2), (2, 224, 28), (30, 54, 240), (232, 12, 214)):
            remnant_color = tuple(round(body_color[index] * 0.68 + background[index] * 0.32) for index in range(3))
            with self.subTest(background=background):
                source = Image.new("RGB", (80, 80), background)
                draw = ImageDraw.Draw(source)
                draw.rectangle((24, 20, 58, 58), fill=body_color)
                draw.rectangle((25, 34, 29, 38), fill=remnant_color)
                draw.rectangle((40, 34, 48, 42), fill=remnant_color)

                cleaned = remove_chroma_background(source, (0, 255, 0), 96)

                self.assertEqual(cleaned.getpixel((27, 36)), (*remnant_color, 255))
                self.assertEqual(cleaned.getpixel((44, 38)), (*remnant_color, 255))

    def test_chroma_cleanup_preserves_light_spill_on_character_edges(self) -> None:
        source = Image.new("RGB", (80, 80), (2, 224, 28))
        draw = ImageDraw.Draw(source)
        draw.rectangle((24, 20, 58, 58), fill=(225, 225, 230))
        draw.rectangle((24, 34, 28, 38), fill=(149, 223, 181))
        draw.rectangle((30, 34, 34, 38), fill=(139, 175, 115))
        draw.rectangle((42, 34, 44, 36), fill=(14, 170, 33))

        cleaned = remove_chroma_background(source, (0, 255, 0), 96)

        self.assertGreater(cleaned.getpixel((26, 36))[3], 0)
        self.assertGreater(cleaned.getpixel((32, 36))[3], 0)
        self.assertEqual(cleaned.getpixel((43, 35))[3], 255)

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
