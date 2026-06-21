from __future__ import annotations

import base64
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "image-creator" / "scripts" / "save_generated_image.py"

PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
NEWER_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC"
)
PNG_BYTES = base64.b64decode(PNG_BASE64)
NEWER_PNG_BYTES = base64.b64decode(NEWER_PNG_BASE64)


class SaveGeneratedImageTests(unittest.TestCase):
    def run_helper(
        self,
        *args: str,
        cwd: pathlib.Path,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        run_env = os.environ.copy()
        run_env.pop("CODEX_THREAD_ID", None)
        run_env.pop("CODEX_HOME", None)
        if env:
            run_env.update(env)

        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
            cwd=cwd,
            env=run_env,
        )

    def write_rollout(self, path: pathlib.Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def image_record(
        self,
        timestamp: str,
        result: str | None,
        payload_type: str = "image_generation_call",
    ) -> dict:
        payload = {
            "type": payload_type,
            "status": "generating",
        }
        if result is not None:
            payload["result"] = result
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": payload,
        }

    def create_state_db(
        self,
        codex_home: pathlib.Path,
        thread_id: str,
        rollout_path: pathlib.Path,
    ) -> None:
        codex_home.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(codex_home / "state_5.sqlite") as connection:
            connection.execute(
                "create table threads (id text primary key, rollout_path text, cwd text)",
            )
            connection.execute(
                "insert into threads (id, rollout_path, cwd) values (?, ?, ?)",
                (thread_id, str(rollout_path), str(rollout_path.parent)),
            )

    def test_rollout_payload_saves_explicit_file_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            rollout = root / "rollout.jsonl"
            destination = root / "assets" / "hero.png"
            self.write_rollout(
                rollout,
                [self.image_record("1970-01-01T00:00:20Z", PNG_BASE64)],
            )

            result = self.run_helper(
                "--since",
                "10",
                "--rollout-path",
                str(rollout),
                "--destination",
                str(destination),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), PNG_BYTES)

    def test_rollout_since_filtering_uses_newest_matching_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            rollout = root / "rollout.jsonl"
            destination = root / "result.png"
            self.write_rollout(
                rollout,
                [
                    self.image_record("1970-01-01T00:00:10Z", PNG_BASE64),
                    self.image_record("1970-01-01T00:00:30Z", NEWER_PNG_BASE64),
                ],
            )

            result = self.run_helper(
                "--since",
                "20",
                "--rollout-path",
                str(rollout),
                "--destination",
                str(destination),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_bytes(), NEWER_PNG_BYTES)

    def test_rollout_uses_later_line_for_matching_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            rollout = root / "rollout.jsonl"
            destination = root / "result.png"
            self.write_rollout(
                rollout,
                [
                    self.image_record("1970-01-01T00:00:20Z", PNG_BASE64),
                    self.image_record(
                        "1970-01-01T00:00:20Z",
                        NEWER_PNG_BASE64,
                        payload_type="image_generation_end",
                    ),
                ],
            )

            result = self.run_helper(
                "--since",
                "10",
                "--rollout-path",
                str(rollout),
                "--destination",
                str(destination),
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_bytes(), NEWER_PNG_BYTES)

    def test_auto_lookup_uses_codex_thread_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            codex_home = root / "codex-home"
            rollout = root / "rollout.jsonl"
            destination = root / "result.png"
            thread_id = "thread-1"
            self.write_rollout(
                rollout,
                [self.image_record("1970-01-01T00:00:20Z", PNG_BASE64)],
            )
            self.create_state_db(codex_home, thread_id, rollout)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(destination),
                cwd=root,
                env={
                    "CODEX_HOME": str(codex_home),
                    "CODEX_THREAD_ID": thread_id,
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_bytes(), PNG_BYTES)

    def test_base64_stdin_default_project_root_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)

            result = self.run_helper(
                "--base64-stdin",
                "--project-root",
                str(root),
                input_text=PNG_BASE64,
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved.parent, root)
            self.assertEqual(saved.suffix, ".png")
            self.assertTrue(saved.name.startswith("image-creator-"))
            self.assertEqual(saved.read_bytes(), PNG_BYTES)

    def test_base64_stdin_explicit_directory_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            destination = root / "assets"

            result = self.run_helper(
                "--base64-stdin",
                "--destination",
                str(destination),
                input_text=PNG_BASE64,
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved.parent, destination)
            self.assertEqual(saved.suffix, ".png")
            self.assertEqual(saved.read_bytes(), PNG_BYTES)

    def test_relative_destination_uses_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outer = pathlib.Path(tmpdir)
            root = outer / "project"
            cwd = outer / "elsewhere"
            root.mkdir()
            cwd.mkdir()

            result = self.run_helper(
                "--base64-stdin",
                "--project-root",
                str(root),
                "--destination",
                "assets/hero.png",
                input_text=PNG_BASE64,
                cwd=cwd,
            )

            destination = root / "assets" / "hero.png"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), PNG_BYTES)

    def test_base64_stdin_collision_safe_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            destination = root / "hero.png"
            destination.write_bytes(b"old")

            result = self.run_helper(
                "--base64-stdin",
                "--destination",
                str(destination),
                input_text=PNG_BASE64,
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            saved = pathlib.Path(result.stdout.strip())
            self.assertEqual(saved, root / "hero-2.png")
            self.assertEqual(destination.read_bytes(), b"old")
            self.assertEqual(saved.read_bytes(), PNG_BYTES)

    def test_base64_stdin_overwrite_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            destination = root / "hero.png"
            destination.write_bytes(b"old")

            result = self.run_helper(
                "--base64-stdin",
                "--destination",
                str(destination),
                "--overwrite",
                input_text=PNG_BASE64,
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pathlib.Path(result.stdout.strip()), destination)
            self.assertEqual(destination.read_bytes(), PNG_BYTES)

    def test_invalid_base64_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)

            result = self.run_helper(
                "--base64-stdin",
                "--destination",
                str(root / "bad.png"),
                input_text="not image base64",
                cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid image base64 payload", result.stderr)

    def test_missing_rollout_payload_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            rollout = root / "rollout.jsonl"
            self.write_rollout(
                rollout,
                [self.image_record("1970-01-01T00:00:05Z", PNG_BASE64)],
            )

            result = self.run_helper(
                "--since",
                "10",
                "--rollout-path",
                str(rollout),
                "--destination",
                str(root / "missing.png"),
                cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No image_gen payload found", result.stderr)

    def test_missing_current_thread_rollout_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)

            result = self.run_helper(
                "--since",
                "10",
                "--destination",
                str(root / "missing.png"),
                cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CODEX_THREAD_ID is not set", result.stderr)


if __name__ == "__main__":
    unittest.main()
