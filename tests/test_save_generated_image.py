from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "image-creator" / "scripts" / "save_generated_image.py"


class SaveGeneratedImageTests(unittest.TestCase):
    def run_helper(
        self,
        *args: str,
        cwd: pathlib.Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def write_image(self, path: pathlib.Path, contents: bytes, mtime: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        os.utime(path, (mtime, mtime))

    def test_default_project_root_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            self.write_image(generated / "latest.png", b"new", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--project-root",
                str(root),
                "--generated-root",
                str(generated),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved.parent, root)
            self.assertEqual(saved.suffix, ".png")
            self.assertTrue(saved.name.startswith("image-creator-"))
            self.assertEqual(saved.read_bytes(), b"new")

    def test_explicit_file_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            destination = root / "assets" / "hero.png"
            self.write_image(generated / "latest.png", b"new", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(destination),
                "--generated-root",
                str(generated),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), b"new")

    def test_explicit_directory_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            destination = root / "assets"
            self.write_image(generated / "latest.webp", b"webp", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(destination),
                "--generated-root",
                str(generated),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved.parent, destination)
            self.assertEqual(saved.suffix, ".webp")
            self.assertEqual(saved.read_bytes(), b"webp")

    def test_relative_destination_uses_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outer = pathlib.Path(tmpdir)
            root = outer / "project"
            cwd = outer / "elsewhere"
            root.mkdir()
            cwd.mkdir()
            generated = outer / "generated"
            self.write_image(generated / "latest.png", b"new", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--project-root",
                str(root),
                "--destination",
                "assets/hero.png",
                "--generated-root",
                str(generated),
                cwd=cwd,
            )

            destination = root / "assets" / "hero.png"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), b"new")

    def test_collision_safe_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            destination = root / "hero.png"
            destination.write_bytes(b"old")
            self.write_image(generated / "latest.png", b"new", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(destination),
                "--generated-root",
                str(generated),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved, root / "hero-2.png")
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual(saved.read_bytes(), b"new")

    def test_since_filtering_uses_newest_matching_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            destination = root / "result.png"
            self.write_image(generated / "old.png", b"old", 10)
            self.write_image(generated / "new.png", b"new", 30)

            result = self.run_helper(
                "--since",
                "20",
                "--destination",
                str(destination),
                "--generated-root",
                str(generated),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_bytes(), b"new")

    def test_overwrite_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            generated = root / "generated"
            destination = root / "hero.png"
            destination.write_bytes(b"old")
            self.write_image(generated / "latest.png", b"new", 20)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(destination),
                "--generated-root",
                str(generated),
                "--overwrite",
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
