from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, PngImagePlugin


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "image-creator" / "scripts" / "save_generated_image.py"
BACKGROUND = (0, 183, 255)


class SaveGeneratedImageTests(unittest.TestCase):
    def run_helper(
        self,
        *args: str,
        cwd: pathlib.Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        merged_env["XDG_CACHE_HOME"] = str(cwd / ".cache")
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=merged_env,
        )

    def make_source(self, path: pathlib.Path) -> None:
        image = Image.new("RGB", (24, 24), BACKGROUND)
        ImageDraw.Draw(image).rectangle((6, 6, 17, 17), fill=(220, 40, 40))
        image.save(path)

    def test_copy_preserves_source_and_avoids_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            self.make_source(source)
            destination.write_bytes(b"old")

            result = self.run_helper(
                "--source",
                str(source),
                "--destination",
                str(destination),
                "--relative-to",
                str(root),
                "--json",
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                set(payload),
                {"overwritten", "relative_path", "saved_path", "suffix", "format", "width", "height",
                 "transparency_requested", "transparency_verified"},
            )
            self.assertEqual(pathlib.Path(payload["saved_path"]), root / "hero-2.png")
            self.assertEqual(payload["relative_path"], "hero-2.png")
            self.assertEqual(source.read_bytes(), (root / "hero-2.png").read_bytes())
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertFalse(payload["overwritten"])
            self.assertFalse(payload["transparency_requested"])
            self.assertIsNone(payload["transparency_verified"])
            self.assertEqual((payload["format"], payload["width"], payload["height"]), ("PNG", 24, 24))

            overwritten = self.run_helper(
                "--source",
                str(source),
                "--destination",
                str(destination),
                "--overwrite",
                "--json",
                cwd=root,
            )
            self.assertEqual(overwritten.returncode, 0, overwritten.stderr)
            self.assertTrue(json.loads(overwritten.stdout)["overwritten"])
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_relative_root_is_checked_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "outside" / "hero.png"
            self.make_source(source)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination),
                "--relative-to", str(root / "session"), "--json", cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())

    def test_native_transparency_preserves_bytes_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            image = Image.new("RGBA", (24, 24), (0, 183, 255, 0))
            image.putpixel((10, 10), (0, 183, 255, 128))
            image.putpixel((11, 10), (220, 40, 40, 255))
            info = PngImagePlugin.PngInfo()
            info.add_text("Description", "Native alpha with a blue translucent foreground")
            image.save(source, pnginfo=info)
            original = source.read_bytes()

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination),
                "--require-transparency", "--json", cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["transparency_requested"])
            self.assertTrue(payload["transparency_verified"])
            self.assertEqual(destination.read_bytes(), original)
            self.assertEqual(source.read_bytes(), original)
            with Image.open(destination) as saved:
                self.assertEqual(saved.getpixel((10, 10)), (0, 183, 255, 128))
                self.assertEqual(saved.info["Description"], "Native alpha with a blue translucent foreground")

    def test_palette_transparency_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            image = Image.new("P", (24, 24), 0)
            image.putpalette([0, 183, 255, 220, 40, 40] + [0] * 762)
            image.putpixel((10, 10), 1)
            image.save(source, transparency=0)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination),
                "--require-transparency", cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_failed_verification_preserves_destination_and_cleans_temporary_file(self) -> None:
        cases = [
            ("RGB", (220, 40, 40), "PNG", "no transparent pixels"),
            ("RGBA", (220, 40, 40, 255), "PNG", "no transparent pixels"),
            ("RGBA", (220, 40, 40, 0), "PNG", "no visible pixels"),
            ("RGB", (220, 40, 40), "JPEG", "requires a PNG"),
        ]
        for mode, color, file_format, error in cases:
            with self.subTest(mode=mode, color=color, file_format=file_format):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = pathlib.Path(tmpdir)
                    source = root / "source.png"
                    destination = root / "hero.png"
                    Image.new(mode, (24, 24), color).save(source, format=file_format)
                    original = source.read_bytes()
                    destination.write_bytes(b"existing asset")

                    result = self.run_helper(
                        "--source", str(source), "--destination", str(destination),
                        "--require-transparency", "--overwrite", cwd=root,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
                    self.assertEqual(destination.read_bytes(), b"existing asset")
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(set(root.iterdir()), {source, destination})

    def test_transparent_output_requires_png_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.jpg"
            self.make_source(source)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination),
                "--require-transparency", cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".png suffix", result.stderr)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
