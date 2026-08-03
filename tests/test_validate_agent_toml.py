from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "subagent-creator" / "scripts" / "validate_agent_toml.py"
MINIMAL_AGENT = '''
name = "qa-agent"
description = "Use `qa-agent` for QA."
developer_instructions = "Validate behavior."
'''


class ValidateAgentTomlTests(unittest.TestCase):
    def run_validator(
        self,
        file_name: str,
        contents: str,
        *extra_args: str,
        codex_script: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            path = root / file_name
            path.write_text(textwrap.dedent(contents).lstrip(), encoding="utf-8")
            env = os.environ.copy()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            if codex_script is not None:
                codex = bin_dir / "codex"
                codex.write_text(textwrap.dedent(codex_script).lstrip(), encoding="utf-8")
                codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
            env["PATH"] = str(bin_dir)
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path), *extra_args],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=env,
            )

    def run_stdin_validator(
        self,
        intended_path: pathlib.Path,
        contents: str,
        *extra_args: str,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        with tempfile.TemporaryDirectory() as tmpdir:
            env["PATH"] = tmpdir
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "-",
                    "--expected-path",
                    str(intended_path),
                    *extra_args,
                ],
                input=textwrap.dedent(contents).lstrip(),
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=env,
            )

    def test_accepts_valid_agent_file(self) -> None:
        result = self.run_validator(
            "release-notes.toml",
            '''
            name = "release-notes"
            description = "Use `release-notes` for release-note drafting."
            developer_instructions = "Prioritize accuracy and explicit evidence."
            sandbox_mode = "read-only"
            ''',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_stdin_preview_uses_expected_path_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            intended = pathlib.Path(tmpdir) / "qa-agent.toml"
            result = self.run_stdin_validator(intended, MINIMAL_AGENT)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"OK: {intended}", result.stdout)
            self.assertFalse(intended.exists())

    def test_rejects_missing_and_wrong_required_metadata(self) -> None:
        result = self.run_validator(
            "qa-agent.toml",
            '''
            name = 12
            description = " "
            ''',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("`name` must be a non-empty string", result.stderr)
        self.assertIn("`description` must be a non-empty string", result.stderr)
        self.assertIn("`developer_instructions` must be a non-empty string", result.stderr)

    def test_validates_skills_config_shape(self) -> None:
        invalid = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT + '\n[[skills.config]]\npath = "/tmp/a/SKILL.md"\n',
        )
        valid = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT
            + '\n[[skills.config]]\npath = "/tmp/a/SKILL.md"\nenabled = false\n',
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("enabled must be a boolean", invalid.stderr)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_validates_mcp_minimum_transport_shape(self) -> None:
        missing = self.run_validator(
            "qa-agent.toml", MINIMAL_AGENT + "\n[mcp_servers.docs]\nenabled = true\n"
        )
        both = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT
            + '\n[mcp_servers.docs]\ncommand = "server"\nurl = "https://example.test"\n',
        )
        valid = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT
            + '\n[mcp_servers.docs]\ncommand = "server"\nargs = ["--stdio"]\n',
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertNotEqual(both.returncode, 0)
        self.assertIn("exactly one transport", missing.stderr)
        self.assertIn("exactly one transport", both.stderr)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_builtin_override_requires_flag(self) -> None:
        contents = '''
        name = "explorer"
        description = "Use `explorer` for code mapping."
        developer_instructions = "Map code paths."
        '''
        blocked = self.run_validator("explorer.toml", contents)
        allowed = self.run_validator(
            "explorer.toml", contents, "--allow-builtin-override"
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_native_codex_uses_config_load_not_process_exit(self) -> None:
        result = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT,
            codex_script='''
            #!/bin/sh
            printf '%s' '{"checks":{"config.load":{"status":"ok","summary":"config loaded","details":{}}}}'
            exit 7
            ''',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Native Codex validation", result.stdout)

    def test_native_candidate_warning_is_an_error(self) -> None:
        result = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT,
            codex_script='''
            #!/bin/sh
            printf '%s' '{"checks":{"config.load":{"status":"warning","summary":"config loaded","details":{"startup warning":"Ignoring malformed agent role definition: invalid config"}}}}'
            exit 0
            ''',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex rejected the agent definition", result.stderr)

    def test_missing_or_incompatible_codex_is_a_qualified_warning(self) -> None:
        missing = self.run_validator("qa-agent.toml", MINIMAL_AGENT)
        incompatible = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT,
            codex_script='''
            #!/bin/sh
            printf '%s' 'not-json'
            ''',
        )
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("additional configuration keys were not verified", missing.stdout)
        self.assertEqual(incompatible.returncode, 0, incompatible.stderr)
        self.assertIn("unsupported report", incompatible.stdout)


if __name__ == "__main__":
    unittest.main()
