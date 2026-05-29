from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "podcast-writer" / "scripts" / "fetch_youtube_transcript.py"
SKILL = REPO_ROOT / "skills" / "podcast-writer" / "SKILL.md"
RUBRIC = REPO_ROOT / "skills" / "podcast-writer" / "references" / "evaluation-rubric.md"
OPENAI_YAML = REPO_ROOT / "skills" / "podcast-writer" / "agents" / "openai.yaml"

spec = importlib.util.spec_from_file_location("fetch_youtube_transcript", SCRIPT)
fetch_youtube_transcript = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["fetch_youtube_transcript"] = fetch_youtube_transcript
spec.loader.exec_module(fetch_youtube_transcript)


class PodcastWriterTests(unittest.TestCase):
    def test_extract_video_id_from_common_youtube_urls(self) -> None:
        video_id = "dQw4w9WgXcQ"
        cases = [
            video_id,
            f"https://www.youtube.com/watch?v={video_id}",
            f"https://www.youtube.com/watch?v={video_id}&list=abc",
            f"https://youtu.be/{video_id}?si=share",
            f"https://www.youtube.com/shorts/{video_id}",
            f"https://www.youtube.com/embed/{video_id}",
            f"https://www.youtube.com/live/{video_id}?feature=share",
        ]

        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(fetch_youtube_transcript.extract_video_id(value), video_id)

    def test_extract_video_id_rejects_invalid_sources(self) -> None:
        for value in (
            "",
            "https://example.com/watch?v=dQw4w9WgXcQ",
            "https://notyoutu.be/dQw4w9WgXcQ",
            "too-short",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    fetch_youtube_transcript.extract_video_id(value)

    def test_normalize_segments_preserves_cues_and_removes_adjacent_duplicates(self) -> None:
        segments = fetch_youtube_transcript.normalize_segments(
            [
                {"text": " first line\ncontinues ", "start": 0, "duration": 1.2},
                {"text": "[Music]", "start": 1.2, "duration": 2},
                {"text": "first line continues", "start": 3.2, "duration": 1},
                {"text": "new point", "start": 4.2, "duration": 1},
            ]
        )

        self.assertEqual([segment.text for segment in segments], ["first line continues", "[Music]", "first line continues", "new point"])
        self.assertEqual(
            fetch_youtube_transcript.transcript_to_text(segments),
            "first line continues\n[Music]\nfirst line continues\nnew point",
        )

    def test_require_usable_segments_rejects_empty_cleanup_result(self) -> None:
        with self.assertRaises(fetch_youtube_transcript.TranscriptError):
            fetch_youtube_transcript.require_usable_segments([], "dQw4w9WgXcQ")

    def test_skill_contract_mentions_strict_all_pass_evaluation(self) -> None:
        contents = SKILL.read_text(encoding="utf-8")

        self.assertIn("subagent", contents)
        self.assertIn("Create a fresh independent evaluator subagent for every evaluation attempt", contents)
        self.assertIn("Do not reuse the same evaluator thread", contents)
        self.assertIn("Never re-use the previous evaluator for re-evaluation", contents)
        self.assertIn("Revise and re-evaluate with a fresh independent evaluator until every rubric item is `PASS`", contents)
        self.assertIn("Do not report the task complete while the evaluator returns any `FAIL`", contents)
        self.assertIn("You are an independent strict podcast script content-quality evaluator.", contents)
        self.assertIn("USER INSTRUCTIONS:", contents)
        self.assertIn("SOURCE NOTES:", contents)
        self.assertIn("CANDIDATE SCRIPT:", contents)
        self.assertIn("{{USER_INSTRUCTIONS}}", contents)
        self.assertIn("{{SOURCE_NOTES}}", contents)
        self.assertIn("{{CANDIDATE_SCRIPT}}", contents)
        self.assertIn("Do not leave template variables", contents)
        self.assertNotIn("[Paste", contents)
        self.assertIn("Assessment: ...", contents)
        self.assertIn("Criterion Result: PASS|FAIL", contents)
        self.assertIn("Do not output a criterion-level `PASS` or `FAIL` before the assessment text", contents)
        self.assertNotIn("Reason:", contents)
        self.assertIn("Do not use speaker labels", contents)
        self.assertIn("Quote full URLs in shells such as zsh", contents)
        self.assertIn("It preserves transcript segment text", contents)
        self.assertIn("fetch_youtube_transcript.py", contents)

    def test_rubric_requires_evaluation_before_result_and_all_pass(self) -> None:
        contents = RUBRIC.read_text(encoding="utf-8")

        self.assertIn("Every item must be marked `PASS` or `FAIL`", contents)
        self.assertIn("RESULT: PASS` is allowed only when every item is `PASS`", contents)
        self.assertIn("When uncertain, choose `FAIL`", contents)
        self.assertLess(contents.index("EVALUATION:"), contents.index("RESULT: PASS|FAIL"))
        self.assertLess(contents.index("Assessment: ..."), contents.index("Criterion Result: PASS|FAIL"))
        self.assertNotIn("Reason:", contents)
        for criterion in (
            "Source Fidelity",
            "Content Selection",
            "Insight And Interpretation",
            "Logical Coherence",
            "Non-Repetition",
            "User Intent Fit",
            "Overall Content Value",
        ):
            self.assertIn(criterion, contents)

    def test_openai_yaml_default_prompt_mentions_skill(self) -> None:
        contents = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertIn("display_name: \"Podcast Writer\"", contents)
        self.assertIn("$podcast-writer", contents)


if __name__ == "__main__":
    unittest.main()
