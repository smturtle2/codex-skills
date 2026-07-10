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
SCRIPT = REPO_ROOT / "skills" / "image-creator" / "scripts" / "save_generated_image.py"
MATTE = (0, 183, 255)


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
        image = Image.new("RGB", (24, 24), MATTE)
        ImageDraw.Draw(image).rectangle((6, 6, 17, 17), fill=(220, 40, 40))
        image.save(path)

    def fake_rembg(
        self,
        root: pathlib.Path,
        *,
        fail_gpu: bool = False,
        opaque_output: bool = False,
    ) -> tuple[pathlib.Path, pathlib.Path]:
        script = root / "fake-rembg"
        calls = root / "rembg-calls.txt"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import pathlib
                import sys
                from PIL import Image

                calls = pathlib.Path({str(calls)!r})
                previous = calls.read_text() if calls.exists() else ""
                calls.write_text(previous + " ".join(sys.argv[1:]) + "\\n")
                if {fail_gpu!r} and "CUDAExecutionProvider" in " ".join(sys.argv):
                    raise SystemExit(9)
                source = pathlib.Path(sys.argv[-2])
                output = pathlib.Path(sys.argv[-1])
                image = Image.open(source).convert("RGBA")
                pixels = image.load()
                for y in range(image.height):
                    for x in range(image.width):
                        red, green, blue, alpha = pixels[x, y]
                        if max(abs(red - {MATTE[0]}), abs(green - {MATTE[1]}), abs(blue - {MATTE[2]})) <= 2:
                            pixels[x, y] = (red, green, blue, 0)
                pixels[0, 0] = ({MATTE[0]}, {MATTE[1] - 20}, {MATTE[2]}, 255)
                if {opaque_output!r}:
                    image.convert("RGB").save(output, format="PNG")
                else:
                    image.save(output, format="PNG")
                """
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script, calls

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
                {"overwritten", "relative_path", "saved_path", "suffix", "transparent"},
            )
            self.assertEqual(pathlib.Path(payload["saved_path"]), root / "hero-2.png")
            self.assertEqual(payload["relative_path"], "hero-2.png")
            self.assertEqual(source.read_bytes(), (root / "hero-2.png").read_bytes())
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertFalse(payload["overwritten"])

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

    def test_transparent_png_cleans_matte_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            self.make_source(source)
            rembg, _ = self.fake_rembg(root)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination), "--transparent", "--json",
                cwd=root, env={"IMAGE_CREATOR_REMBG_BIN": str(rembg)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["transparent"])
            with Image.open(destination) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.convert("RGBA").getpixel((0, 0))[3], 0)
                self.assertGreater(image.convert("RGBA").getpixel((10, 10))[3], 0)
            with Image.open(source) as image:
                self.assertEqual(image.mode, "RGB")

    def test_gpu_failure_retries_once_on_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            self.make_source(source)
            rembg, calls = self.fake_rembg(root, fail_gpu=True)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination), "--transparent",
                cwd=root,
                env={
                    "IMAGE_CREATOR_REMBG_BIN": str(rembg),
                    "IMAGE_CREATOR_REMBG_PROVIDERS": "CUDAExecutionProvider,CPUExecutionProvider",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            logged = calls.read_text(encoding="utf-8")
            self.assertEqual(logged.count("-m birefnet-general-lite"), 2)
            self.assertIn("CUDAExecutionProvider", logged)
            self.assertIn("CPUExecutionProvider", logged)

    def test_opaque_rembg_output_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source = root / "source.png"
            destination = root / "hero.png"
            self.make_source(source)
            rembg, _ = self.fake_rembg(root, opaque_output=True)

            result = self.run_helper(
                "--source", str(source), "--destination", str(destination), "--transparent",
                cwd=root, env={"IMAGE_CREATOR_REMBG_BIN": str(rembg)},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
