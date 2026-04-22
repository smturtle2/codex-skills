from __future__ import annotations

import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "image-creator" / "SKILL.md"
OPENAI_YAML = REPO_ROOT / "skills" / "image-creator" / "agents" / "openai.yaml"
README = REPO_ROOT / "README.md"
README_KO = REPO_ROOT / "README.ko.md"
UI_BLUEPRINT = REPO_ROOT / "skills" / "ui-blueprint" / "SKILL.md"


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

    def test_keeps_model_friendly_rewrite_contract(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        openai_yaml = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertIn("Always rewrite or restructure", text)
        self.assertIn("model-friendly", text)
        self.assertIn("input-image roles", text)
        self.assertIn("explicit constraints", text)
        self.assertIn("Preserve exact text the user wants rendered", text)
        self.assertIn("proper names, brand names, numbers, colors, layout requirements", text)
        self.assertIn("Pass only the final rewritten prompt", text)
        self.assertIn("Do not run skill-level content filtering", text)
        self.assertIn("Do not block, soften, redirect, sanitize, or replace", text)
        self.assertIn(
            "The selected generation path is responsible for accepting, rejecting, modifying, or erroring",
            text,
        )
        self.assertIn("no skill-level filtering, blocking", text)
        self.assertIn("without replacing it with this skill's own refusal rationale", text)
        self.assertIn("model-friendly prompt", openai_yaml)

    def test_removes_old_no_rewrite_contract(self) -> None:
        texts = {
            "SKILL.md": SKILL.read_text(encoding="utf-8").lower(),
            "openai.yaml": OPENAI_YAML.read_text(encoding="utf-8").lower(),
            "README.md": README.read_text(encoding="utf-8").lower(),
            "README.ko.md": README_KO.read_text(encoding="utf-8").lower(),
            "ui-blueprint/SKILL.md": UI_BLUEPRINT.read_text(encoding="utf-8").lower(),
        }

        forbidden = [
            "exact-prompt",
            "exact prompt",
            "without rewriting",
            "do not rewrite",
            "prompt as-is",
            "use that text exactly",
            "preserved prompt directly",
            "preserved prompt text",
        ]
        for name, text in texts.items():
            for phrase in forbidden:
                with self.subTest(file=name, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_linked_docs_describe_rewrite_policy(self) -> None:
        readme = README.read_text(encoding="utf-8")
        readme_ko = README_KO.read_text(encoding="utf-8")
        ui_blueprint = UI_BLUEPRINT.read_text(encoding="utf-8")

        self.assertIn("rewriting the user's request into a model-friendly image prompt", readme)
        self.assertIn("do not block, soften, redirect", readme)
        self.assertIn("사용자의 요청을 이미지 생성 모델에 적합한 프롬프트로 재구성", readme_ko)
        self.assertIn("사용자 지시를 차단, 완화, 우회", readme_ko)
        self.assertIn("convert it into a model-friendly prompt", ui_blueprint)


if __name__ == "__main__":
    unittest.main()
