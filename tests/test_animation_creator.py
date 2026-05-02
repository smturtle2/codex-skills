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

from animation_common import chroma_adjacent_count, fit_to_frame, remove_chroma_background  # noqa: E402


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
        frames: int = 6,
        size: int = 512,
        columns: int = 3,
        rows: int = 2,
        artifacts: bool = False,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (columns * size, rows * size), DEFAULT_TEST_CHROMA)
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

    def test_project_local_prepare_and_end_to_end_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project = pathlib.Path(tmpdir) / "project"
            project.mkdir()

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
            self.assertTrue((run_dir / "references" / "layout-guides" / "wave.png").is_file())
            with Image.open(run_dir / "references" / "layout-guides" / "wave.png") as guide:
                self.assertEqual(guide.size, (1536, 1024))
            action_prompt = (run_dir / "prompts" / "actions" / "wave.md").read_text(encoding="utf-8")
            self.assertIn("animation frame grid", action_prompt)
            self.assertNotIn("horizontal animation strip", action_prompt)
            self.assertIn("contact shadow", action_prompt)
            self.assertIn("oval floor shadow", action_prompt)
            self.assertIn("Do not draw floor cues", action_prompt)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["animation"]["layout"]["columns"], 3)
            self.assertEqual(manifest["animation"]["layout"]["rows"], 2)
            self.assertEqual(manifest["animation"]["layout"]["working_cell_size"], [512, 512])
            self.assertEqual(manifest["animation"]["states"][0]["layout"]["order"], "left-to-right-top-to-bottom")

            generated_source = pathlib.Path(tmpdir) / "wave-generated.png"
            self.make_grid(generated_source, artifacts=True)
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

            for command in (
                ("extract_frames.py", "--run-dir", str(run_dir), "--action-id", "wave"),
                ("compose_animation.py", "--run-dir", str(run_dir), "--action-id", "wave"),
                ("make_contact_sheet.py", "--run-dir", str(run_dir), "--action-id", "wave"),
                ("render_preview.py", "--run-dir", str(run_dir), "--action-id", "wave", "--formats", "gif", "--write-final"),
                ("validate_animation.py", "--run-dir", str(run_dir), "--action-id", "wave"),
            ):
                result = self.run_script(command[0], *command[1:], cwd=project)
                self.assertEqual(result.returncode, 0, f"{command[0]}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

            frames = sorted((run_dir / "frames" / "wave").glob("*.webp"))
            self.assertEqual(len(frames), 6)
            observed_sizes = []
            for frame_path in frames:
                with Image.open(frame_path) as frame:
                    rgba = frame.convert("RGBA")
                    bbox = rgba.getbbox()
                    self.assertIsNotNone(bbox)
                    observed_sizes.append(bbox[2] - bbox[0])
                    self.assertEqual(chroma_adjacent_count(rgba, (0, 255, 0), 190), 0)
            self.assertEqual(observed_sizes, sorted(observed_sizes))
            self.assertTrue((run_dir / "final" / "wave-frames.png").is_file())
            self.assertTrue((run_dir / "final" / "wave.gif").is_file())
            self.assertTrue((run_dir / "final" / "wave-validation.json").is_file())
            self.assertTrue((run_dir / "qa" / "wave-contact-sheet.png").is_file())
            self.assertTrue((run_dir / "qa" / "previews" / "wave.gif").is_file())
            validation = json.loads((run_dir / "final" / "wave-validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["ok"], validation)

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
