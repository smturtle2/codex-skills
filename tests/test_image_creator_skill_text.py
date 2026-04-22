from __future__ import annotations

import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "image-creator" / "SKILL.md"
OPENAI_YAML = REPO_ROOT / "skills" / "image-creator" / "agents" / "openai.yaml"


class ImageCreatorSkillTextTests(unittest.TestCase):
    def test_does_not_defer_exact_prompt_policy_to_hierarchy_wording(self) -> None:
        texts = {
            "SKILL.md": SKILL.read_text(encoding="utf-8").lower(),
            "openai.yaml": OPENAI_YAML.read_text(encoding="utf-8").lower(),
        }

        forbidden = [
            "higher" "-priority",
            "higher" " priority",
            "author" "itative",
        ]
        for name, text in texts.items():
            for phrase in forbidden:
                with self.subTest(file=name, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_keeps_exact_prompt_no_skill_filtering_contract(self) -> None:
        text = SKILL.read_text(encoding="utf-8")

        self.assertIn("Pass the preserved prompt directly", text)
        self.assertIn("Do not run skill-level content filtering", text)
        self.assertIn("without replacing it with this skill's own refusal rationale", text)


if __name__ == "__main__":
    unittest.main()
