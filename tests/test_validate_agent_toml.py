from __future__ import annotations

import pathlib
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "subagent-creator" / "scripts" / "validate_agent_toml.py"


class ValidateAgentTomlTests(unittest.TestCase):
    def run_validator(
        self,
        file_name: str,
        contents: str,
        *extra_args: str,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / file_name
            path.write_text(textwrap.dedent(contents).lstrip(), encoding="utf-8")
            return subprocess.run(
                ["python3", str(SCRIPT), str(path), *extra_args],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

    def test_accepts_valid_agent_file(self) -> None:
        result = self.run_validator(
            "release-notes.toml",
            '''
            name = "release-notes"
            description = """
            Use `release-notes` for release-note drafting.
            Summarize shipped changes and call out missing evidence.
            Rules:
            - Stay within the provided scope.
            - Do not edit workspace artifacts.
            """
            developer_instructions = """
            Prioritize accuracy and explicit evidence.
            Return concise notes with open questions when evidence is missing.
            Do not edit files.
            """
            sandbox_mode = "read-only"
            ''',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_rejects_unknown_top_level_keys(self) -> None:
        result = self.run_validator(
            "qa-agent.toml",
            """
            name = "qa-agent"
            description = "Use `qa-agent` for QA."
            developer_instructions = "Validate behavior."
            approval_policy = "never"
            """,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown top-level keys", result.stderr)

    def test_rejects_duplicate_nicknames(self) -> None:
        result = self.run_validator(
            "docs-auditor.toml",
            """
            name = "docs-auditor"
            description = "Use `docs-auditor` for documentation audits."
            developer_instructions = "Audit docs and report issues."
            nickname_candidates = ["Echo", "Echo"]
            """,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not contain duplicates", result.stderr)

    def test_builtin_override_requires_flag(self) -> None:
        blocked = self.run_validator(
            "explorer.toml",
            """
            name = "explorer"
            description = "Use `explorer` for code mapping."
            developer_instructions = "Map code paths."
            """,
        )
        allowed = self.run_validator(
            "explorer.toml",
            """
            name = "explorer"
            description = "Use `explorer` for code mapping."
            developer_instructions = "Map code paths."
            """,
            "--allow-builtin-override",
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)


if __name__ == "__main__":
    unittest.main()
