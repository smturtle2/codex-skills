from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

from PIL import Image, ImageDraw


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "skills" / "animation-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))

REMOVAL_MATTE = (0, 183, 255)
WAVE_BEATS = [
    "start in a relaxed friendly pose",
    "raise the right hand to shoulder height",
    "lift the right hand beside the head",
    "tilt the raised hand outward",
    "tilt the raised hand inward",
    "return to the relaxed friendly pose",
]

from animation_common import recommended_grid  # noqa: E402


class AnimationCreatorTests(unittest.TestCase):
    def run_script(
        self,
        script: str,
        *args: str,
        cwd: pathlib.Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=merged_env,
        )

    def fake_rembg_env(self, root: pathlib.Path) -> dict[str, str]:
        fake = root / "fake-rembg"
        calls = root / "fake-rembg-calls.txt"
        fake.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import pathlib
                import sys
                from PIL import Image

                calls = pathlib.Path({str(calls)!r})
                with calls.open("a", encoding="utf-8") as handle:
                    handle.write(" ".join(sys.argv[1:]) + "\\n")
                source = pathlib.Path(sys.argv[-2])
                output = pathlib.Path(sys.argv[-1])
                image = Image.open(source).convert("RGBA")
                pixels = image.load()
                for y in range(image.height):
                    for x in range(image.width):
                        r, g, b, a = pixels[x, y]
                        if abs(r - {REMOVAL_MATTE[0]}) <= 2 and abs(g - {REMOVAL_MATTE[1]}) <= 2 and abs(b - {REMOVAL_MATTE[2]}) <= 2:
                            pixels[x, y] = (0, 0, 0, 0)
                pixels[0, 0] = ({max(0, REMOVAL_MATTE[0] - 8)}, {max(0, REMOVAL_MATTE[1] - 8)}, {REMOVAL_MATTE[2]}, 255)
                output.parent.mkdir(parents=True, exist_ok=True)
                image.save(output, format="PNG")
                """
            ),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        return {
            "ANIMATION_CREATOR_REMBG_BIN": str(fake),
            "XDG_CACHE_HOME": str(root / "cache"),
        }

    def make_base(self, path: pathlib.Path) -> None:
        image = Image.new("RGB", (320, 320), REMOVAL_MATTE)
        draw = ImageDraw.Draw(image)
        draw.ellipse((104, 44, 216, 156), fill=(40, 120, 220), outline=(10, 20, 30), width=8)
        draw.rounded_rectangle((112, 148, 208, 280), radius=20, fill=(50, 140, 230), outline=(10, 20, 30), width=8)
        image.save(path)

    def make_action_sheet(
        self,
        path: pathlib.Path,
        *,
        frames: int = len(WAVE_BEATS),
        columns: int = 4,
        rows: int = 3,
        size: int = 312,
        draw_outer_borders: bool = True,
        draw_inner_guide_lines: bool = False,
    ) -> None:
        image = Image.new("RGB", (columns * size, rows * size), REMOVAL_MATTE)
        draw = ImageDraw.Draw(image)
        if draw_outer_borders:
            for row in range(rows):
                for column in range(columns):
                    left = column * size
                    top = row * size
                    draw.rectangle((left, top, left + size - 1, top + size - 1), outline="#111111", width=4)
        for index in range(frames):
            left = (index % columns) * size
            top = (index // columns) * size
            if draw_inner_guide_lines:
                draw.line((left, top + size // 2, left + size - 1, top + size // 2), fill="#111111", width=3)
            cx = left + size // 2
            cy = top + size // 2
            radius = 70 + index * 5
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=(40, 120 + index * 10, 220),
                outline=(10, 20, 30),
                width=8,
            )
        image.save(path)

    def read_json(self, path: pathlib.Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_project_local_prepare_record_and_finalize_rembg_matte_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            project = root / "project"
            project.mkdir()
            env = self.fake_rembg_env(root)

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
                env=env,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            manifest_path = run_dir / "animation_manifest.json"
            jobs_path = run_dir / "animation-jobs.json"
            manifest = self.read_json(manifest_path)
            self.assertEqual(manifest["background_mode"], "rembg-matte")
            self.assertNotIn("chroma_key", manifest)
            self.assertNotIn("chroma_key_status", manifest)
            self.assertEqual(manifest["removal_background"]["hex"], "#00B7FF")
            self.assertEqual(manifest["background_removal"]["engine"], "rembg")
            self.assertEqual(manifest["background_removal"]["required"], True)
            self.assertEqual(manifest["background_removal"]["model"], "birefnet-general-lite")
            self.assertIn(manifest["background_removal"]["backend"], {"cuda", "rocm", "cpu"})
            self.assertIn("available_providers", manifest["background_removal"])
            self.assertIn("selected_providers", manifest["background_removal"])
            self.assertEqual(manifest["animation"]["states"][0]["frame_actions"], WAVE_BEATS)

            base_prompt = (run_dir / "prompts" / "base-character.md").read_text(encoding="utf-8")
            action_prompt = (run_dir / "prompts" / "actions" / "wave.md").read_text(encoding="utf-8")
            self.assertIn("removable matte background", base_prompt)
            self.assertIn("#00B7FF", base_prompt)
            self.assertIn("rembg removal", action_prompt)
            self.assertIn("Keep the outer black cell grid/border lines", action_prompt)
            self.assertIn("Do not draw inner safe-area rectangles", action_prompt)
            self.assertIn("Keep the attached registration guide as the canvas template", action_prompt)
            self.assertIn("Preserve the guide's 4:3 canvas framing", action_prompt)
            self.assertIn("Preserve the guide's exactly 4 columns and 3 rows", action_prompt)
            self.assertNotIn("Target canvas ratio", action_prompt)
            self.assertNotIn("overall grid aspect ratio", action_prompt)
            self.assertNotIn("1536x1024", action_prompt)
            self.assertNotIn("chroma", base_prompt.lower())
            self.assertNotIn("chroma", action_prompt.lower())

            base_source = root / "base-generated.png"
            self.make_base(base_source)
            recorded_base = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "base-character",
                "--source",
                str(base_source),
                cwd=project,
                env=env,
            )
            self.assertEqual(recorded_base.returncode, 0, recorded_base.stderr)
            self.assertTrue((run_dir / "generated" / "raw" / "base-character.png").is_file())
            with Image.open(run_dir / "references" / "canonical-base.png") as canonical:
                self.assertEqual(canonical.convert("RGBA").getpixel((0, 0)), (*REMOVAL_MATTE, 255))

            jobs_after_base = self.read_json(jobs_path)
            base_job = next(job for job in jobs_after_base["jobs"] if job["id"] == "base-character")
            wave_job = next(job for job in jobs_after_base["jobs"] if job["id"] == "wave")
            self.assertNotIn("background_removal", base_job)
            self.assertEqual(wave_job["status"], "ready")
            self.assertEqual(wave_job["prompt_status"], "ready-after-canonical-base")
            self.assertNotIn("chroma_key_hex", wave_job)

            built_prompt = self.run_script(
                "build_generation_prompt.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                cwd=project,
                env=env,
            )
            self.assertEqual(built_prompt.returncode, 0, built_prompt.stderr)
            self.assertIn("registration guide edit template", built_prompt.stdout)
            self.assertIn("preserve its 4:3 layout", built_prompt.stdout.lower())
            self.assertIn("Remove only inner guide marks", built_prompt.stdout)
            self.assertNotIn("chroma", built_prompt.stdout.lower())

            action_source = root / "wave-generated.png"
            self.make_action_sheet(action_source)
            recorded_action = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(action_source),
                cwd=project,
                env=env,
            )
            self.assertEqual(recorded_action.returncode, 0, recorded_action.stderr)
            self.assertTrue((run_dir / "generated" / "raw" / "wave.png").is_file())
            jobs_after_action = self.read_json(jobs_path)
            wave_job = next(job for job in jobs_after_action["jobs"] if job["id"] == "wave")
            self.assertEqual(wave_job["background_removal"]["scope"], "action-sheet-slots")
            self.assertEqual(wave_job["background_removal"]["model"], "birefnet-general-lite")
            self.assertIn(wave_job["background_removal"]["backend"], {"cuda", "rocm", "cpu"})
            self.assertIn("selected_providers", wave_job["background_removal"])
            self.assertEqual(wave_job["background_removal"]["slot_count"], len(WAVE_BEATS))
            self.assertEqual(wave_job["background_removal"]["source_sheet_size"], [1248, 936])
            fake_calls = (root / "fake-rembg-calls.txt").read_text(encoding="utf-8")
            self.assertIn("-m birefnet-general-lite", fake_calls)
            self.assertEqual(
                wave_job["background_removal"]["border_strip"]["policy"],
                "strip-outer-black-cell-borders-before-rembg",
            )
            self.assertTrue((run_dir / "generated" / "rembg-work" / "wave" / "000-border-stripped.png").is_file())
            cleanup = wave_job["background_removal"]["matte_residue_cleanup"]
            self.assertEqual(cleanup["matte_hex"], "#00B7FF")
            self.assertGreater(cleanup["pixels_changed"], 0)
            self.assertTrue((run_dir / "generated" / "rembg-work" / "wave" / "000.png").is_file())
            with Image.open(run_dir / "generated" / "wave.png") as sheet:
                self.assertEqual(sheet.convert("RGBA").getpixel((0, 0))[3], 0)

            finalized = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                cwd=project,
                env=env,
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr + finalized.stdout)
            frames = sorted((run_dir / "frames" / "wave").glob("*.png"))
            self.assertEqual(len(frames), len(WAVE_BEATS))
            for frame_path in frames:
                with Image.open(frame_path) as frame:
                    rgba = frame.convert("RGBA")
                    self.assertIsNotNone(rgba.getbbox())
                    self.assertEqual(rgba.getpixel((0, 0))[3], 0)
            self.assertTrue((run_dir / "final" / "wave.webp").is_file())
            frame_manifest = self.read_json(run_dir / "frames" / "frames-manifest.json")
            self.assertEqual(frame_manifest["rows"][0]["method"], "components")
            self.assertEqual(frame_manifest["rows"][0]["background_removal"], "required-rembg-before-extraction")

    def test_source_character_is_preserved_during_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            project = root / "project"
            project.mkdir()
            source = root / "source.png"
            self.make_base(source)

            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source),
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
            manifest = self.read_json(run_dir / "animation_manifest.json")
            self.assertNotIn("base_background_removal", manifest)
            self.assertTrue((run_dir / "generated" / "raw" / "base-character.png").is_file())
            with Image.open(run_dir / "references" / "canonical-base.png") as canonical:
                self.assertEqual(canonical.convert("RGBA").getpixel((0, 0)), (*REMOVAL_MATTE, 255))

    def test_prepare_rejects_chroma_key_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            result = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS),
                "--chroma-key",
                "#00FF00",
                cwd=project,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrecognized arguments", result.stderr)

    def test_prepare_requires_frame_actions_for_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            result = self.run_script(
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
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("frame actions must be planned", result.stderr)

    def test_prepare_rejects_frame_count_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            result = self.run_script(
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
                "ready; anticipate; move",
                cwd=project,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrecognized arguments", result.stderr)

    def test_recommended_grid_sizes_fit_codex_imagegen_cell_budget(self) -> None:
        for frame_count in range(1, 13):
            grid = recommended_grid(frame_count)
            width = grid["columns"] * grid["cell_width"]
            height = grid["rows"] * grid["cell_height"]
            with self.subTest(frame_count=frame_count):
                self.assertEqual((grid["columns"], grid["rows"]), (4, 3))
                self.assertEqual(grid["cell_count"], 12)
                self.assertLessEqual(max(width, height), 1448)
                self.assertEqual(grid["cell_width"], grid["cell_height"])
                self.assertLessEqual(max(width, height) / min(width, height), 3)
                self.assertEqual(len(grid["unused_slots"]), 12 - frame_count)
        grid = recommended_grid(10)
        self.assertEqual((grid["columns"], grid["rows"]), (4, 3))
        self.assertEqual((grid["cell_width"], grid["cell_height"]), (362, 362))
        with self.assertRaises(SystemExit):
            recommended_grid(13)

    def test_finalize_rejects_generated_sheet_with_wrong_guide_aspect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            project = root / "project"
            project.mkdir()
            env = self.fake_rembg_env(root)
            source = root / "source.png"
            self.make_base(source)
            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source),
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS[:4]),
                cwd=project,
                env=env,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            wrong = root / "wrong.png"
            Image.new("RGB", (1672, 941), REMOVAL_MATTE).save(wrong)
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(wrong),
                cwd=project,
                env=env,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            finalized = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                cwd=project,
                env=env,
            )
            self.assertNotEqual(finalized.returncode, 0)
            self.assertIn("does not match layout guide", finalized.stderr)

    def test_finalize_rejects_copied_inner_registration_guide_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            project = root / "project"
            project.mkdir()
            env = self.fake_rembg_env(root)
            source = root / "source.png"
            self.make_base(source)
            prepared = self.run_script(
                "prepare_animation_run.py",
                "--project-root",
                str(project),
                "--character-name",
                "Demo Bot",
                "--source-character",
                str(source),
                "--action-id",
                "wave",
                "--action",
                "friendly waving loop",
                "--frame-actions",
                "; ".join(WAVE_BEATS),
                cwd=project,
                env=env,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            run_dir = pathlib.Path(prepared.stdout.strip())
            action_source = root / "wave-with-guide.png"
            self.make_action_sheet(action_source, draw_inner_guide_lines=True)
            recorded = self.run_script(
                "record_animation_result.py",
                "--run-dir",
                str(run_dir),
                "--job-id",
                "wave",
                "--source",
                str(action_source),
                cwd=project,
                env=env,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            finalized = self.run_script(
                "finalize_animation_run.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                cwd=project,
                env=env,
            )
            self.assertNotEqual(finalized.returncode, 0)
            self.assertIn("visible grid, guide, or border lines", finalized.stderr)

    def test_validate_flags_nearly_opaque_background(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir)
            run_dir = project / "run"
            frames_dir = run_dir / "frames" / "wave"
            frames_dir.mkdir(parents=True)
            manifest = {
                "run_dir": str(run_dir),
                "frame_width": 64,
                "frame_height": 64,
                "background_mode": "rembg-matte",
                "animation": {
                    "frame_size": [64, 64],
                    "frame_count": 1,
                    "format": "webp",
                    "states": [
                        {
                            "name": "wave",
                            "row": 0,
                            "frames": 1,
                            "frame_actions": ["opaque hold"],
                            "layout": {"columns": 1, "rows": 1},
                        }
                    ],
                },
            }
            (run_dir / "animation_manifest.json").parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "animation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(frames_dir / "000.png")
            result = self.run_script(
                "validate_animation.py",
                "--run-dir",
                str(run_dir),
                "--action-id",
                "wave",
                "--json-out",
                str(run_dir / "review.json"),
                cwd=project,
            )
            self.assertNotEqual(result.returncode, 0)
            validation = self.read_json(run_dir / "review.json")
            self.assertTrue(any("nearly opaque" in error for error in validation["errors"]))


if __name__ == "__main__":
    unittest.main()
