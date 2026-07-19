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

    def test_accepts_additional_config_keys(self) -> None:
        result = self.run_validator(
            "qa-agent.toml",
            MINIMAL_AGENT + '\napproval_policy = "never"\nweb_search = "live"\n',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Unknown top-level keys", result.stderr)

    def test_stdin_preview_uses_expected_path_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            intended = pathlib.Path(tmpdir) / "qa-agent.toml"
            result = self.run_stdin_validator(intended, MINIMAL_AGENT)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"OK: {intended}", result.stdout)
            self.assertFalse(intended.exists())

    def test_stdin_requires_expected_path(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "-"],
            input=textwrap.dedent(MINIMAL_AGENT).lstrip(),
            check=False,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--expected-path is required", result.stderr)

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

    def test_rejects_duplicate_nicknames_after_normalization(self) -> None:
        result = self.run_validator(
            "docs-auditor.toml",
            '''
            name = "docs-auditor"
            description = "Use `docs-auditor` for documentation audits."
            developer_instructions = "Audit docs and report issues."
            nickname_candidates = ["Echo Team", " Echo Team "]
            ''',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicates after trimming", result.stderr)

    def test_accepts_case_and_internal_space_distinct_nicknames(self) -> None:
        result = self.run_validator(
            "docs-auditor.toml",
            '''
            name = "docs-auditor"
            description = "Use `docs-auditor` for documentation audits."
            developer_instructions = "Audit docs and report issues."
            nickname_candidates = ["Echo Team", "echo team", "Echo  Team"]
            ''',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_accepts_nickname_whitespace_trimmed_by_runtime(self) -> None:
        result = self.run_validator(
            "docs-auditor.toml",
            MINIMAL_AGENT.replace('name = "qa-agent"', 'name = "docs-auditor"')
            + 'nickname_candidates = ["\\tEcho Team\\t"]\n',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_invalid_sandbox_mode(self) -> None:
        result = self.run_validator(
            "qa-agent.toml", MINIMAL_AGENT + '\nsandbox_mode = "container"\n'
        )
        wrong_type = self.run_validator(
            "qa-agent.toml", MINIMAL_AGENT + "\nsandbox_mode = [\"read-only\"]\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("`sandbox_mode` must be one of", result.stderr)
        self.assertNotEqual(wrong_type.returncode, 0)
        self.assertNotIn("Traceback", wrong_type.stderr)

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

    def test_name_filename_and_prose_quality_are_warnings(self) -> None:
        result = self.run_validator(
            "different.toml",
            '''
            name = "Documentation Agent"
            description = "TODO: helps with tasks and inspect <svg>."
            developer_instructions = "Validate behavior."
            ''',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recommended lowercase ASCII", result.stdout)
        self.assertIn("does not match agent name", result.stdout)
        self.assertIn("Placeholder text found: `TODO`", result.stdout)
        self.assertIn("Generic filler detected", result.stdout)

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

    def test_io_errors_do_not_emit_tracebacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), tmpdir],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not read", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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
