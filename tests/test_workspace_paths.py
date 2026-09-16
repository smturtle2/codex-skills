from __future__ import annotations

import argparse
from contextlib import chdir, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills/user-dialog/scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills/world-simulator/scripts"))

import user_dialog
from worldsim import cli as world_cli


class WorkspacePathsTests(unittest.TestCase):
    def test_dialog_runs_keep_project_asset_base_and_resume_original_paths(self):
        # Replace only the native renderer; compile requests and persist actual run files.
        def launch_renderer(command, **kwargs):
            directory = Path(command[-1])
            state = user_dialog.read_state(directory)
            state["status"] = "open"
            user_dialog.save_state(directory, state)
            return Mock(poll=lambda: None)

        def invoke(args):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(user_dialog.run_dialog(args), 0)
            return json.loads(output.getvalue())

        with tempfile.TemporaryDirectory() as temp, chdir(temp), patch.object(
            user_dialog, "find_python", return_value={"python": sys.executable}
        ), patch.object(user_dialog.subprocess, "Popen", side_effect=launch_renderer):
            project = Path.cwd()
            (project / "source.md").write_text("Source", encoding="utf-8")
            request = project / "request.json"
            request.write_text(json.dumps({
                "title": "Workspace test",
                "body": {"type": "column", "children": [
                    {"type": "file", "path": "source.md"},
                    {"type": "input", "id": "notes", "label": "Notes"},
                ]},
            }), encoding="utf-8")
            args = argparse.Namespace(command="show", request=str(request), run_dir=None,
                                      preview=True, render_image=None, python=None)
            first = Path(invoke(args)["run_dir"])
            second = Path(invoke(args)["run_dir"])
            self.assertEqual(first.parent, project / ".codex-skills/user-dialog")
            self.assertEqual(second.parent, first.parent)
            self.assertNotEqual(first, second)
            self.assertFalse((project / "dialog-runs").exists())

            args.run_dir = "dialog-runs/legacy"
            legacy = Path(invoke(args)["run_dir"])
            self.assertEqual(legacy, project / "dialog-runs/legacy")
            state = user_dialog.read_state(legacy)
            state["draft"] = {"notes": "Keep this answer"}
            user_dialog.save_state(legacy, state)
            nested = project / "nested"
            nested.mkdir()
            with chdir(nested):
                resumed = invoke(argparse.Namespace(command="resume", run_dir=str(legacy), python=None))
            saved = user_dialog.read_state(legacy)
            self.assertEqual(resumed["run_dir"], str(legacy))
            self.assertEqual(saved["base"], str(project))
            self.assertEqual(saved["draft"], {"notes": "Keep this answer"})
            self.assertTrue((first / "state.json").is_file())
            self.assertTrue((second / "state.json").is_file())
            self.assertFalse((nested / ".codex-skills").exists())

    def test_world_sessions_are_isolated_and_legacy_roots_still_resume(self):
        # Only bypass the blocking HTTP server; use the real CLI and SQLite storage.
        with tempfile.TemporaryDirectory() as temp, chdir(temp), patch.object(world_cli, "serve") as serve:
            project = Path.cwd()
            parser = world_cli.build_parser()
            world_cli.run(parser.parse_args(["start", "--no-open-browser"]))
            first = serve.call_args.args[0]
            world_cli.run(parser.parse_args(["start", "--no-open-browser"]))
            second = serve.call_args.args[0]
            self.assertEqual(first.parent, project / ".codex-skills/world-simulator")
            self.assertEqual(second.parent, first.parent)
            self.assertNotEqual(first, second)
            self.assertTrue((first / "world.sqlite3").is_file())
            self.assertTrue((second / "world.sqlite3").is_file())
            self.assertFalse((project / "world-runs").exists())

            world_cli.run(parser.parse_args(["start", "--root", "world-runs", "--no-open-browser"]))
            legacy = serve.call_args.args[0]
            asset = legacy / "assets/kept.txt"
            asset.write_text("Retained world asset", encoding="utf-8")
            nested = project / "nested"
            nested.mkdir()
            with chdir(nested):
                world_cli.run(parser.parse_args([
                    "start", "--root", str(legacy.parent), "--session", legacy.name,
                    "--no-open-browser",
                ]))
                self.assertEqual(serve.call_args.args[0], legacy)
                # Selecting the first session must work even though the second became active.
                with redirect_stdout(io.StringIO()) as output:
                    world_cli.run(parser.parse_args([
                        "status", "--root", str(first.parent), "--session", first.name,
                    ]))
                self.assertEqual(json.loads(output.getvalue())["session_id"], first.name)
            self.assertEqual(asset.read_text(encoding="utf-8"), "Retained world asset")
            self.assertFalse((nested / ".codex-skills").exists())


if __name__ == "__main__":
    unittest.main()
