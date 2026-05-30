from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "podcast-writer" / "scripts" / "fetch_youtube_transcript.py"
GPU_SCRIPT = REPO_ROOT / "skills" / "podcast-writer" / "scripts" / "transcribe_youtube_gpu.py"
SKILL = REPO_ROOT / "skills" / "podcast-writer" / "SKILL.md"
RUBRIC = REPO_ROOT / "skills" / "podcast-writer" / "references" / "evaluation-rubric.md"
OPENAI_YAML = REPO_ROOT / "skills" / "podcast-writer" / "agents" / "openai.yaml"

spec = importlib.util.spec_from_file_location("fetch_youtube_transcript", SCRIPT)
fetch_youtube_transcript = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["fetch_youtube_transcript"] = fetch_youtube_transcript
spec.loader.exec_module(fetch_youtube_transcript)

gpu_spec = importlib.util.spec_from_file_location("transcribe_youtube_gpu", GPU_SCRIPT)
transcribe_youtube_gpu = importlib.util.module_from_spec(gpu_spec)
assert gpu_spec.loader is not None
sys.modules["transcribe_youtube_gpu"] = transcribe_youtube_gpu
gpu_spec.loader.exec_module(transcribe_youtube_gpu)


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

    def test_gpu_transcription_helper_requires_cuda(self) -> None:
        self.assertEqual(transcribe_youtube_gpu.require_cuda_gpu(lambda: 1), 1)
        with self.assertRaises(transcribe_youtube_gpu.GpuTranscriptionError):
            transcribe_youtube_gpu.require_cuda_gpu(lambda: 0)

    def test_gpu_transcription_helper_uses_youtube_url_for_video_ids(self) -> None:
        self.assertEqual(
            transcribe_youtube_gpu.source_to_download_url("dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(
            transcribe_youtube_gpu.source_to_download_url("https://youtu.be/dQw4w9WgXcQ"),
            "https://youtu.be/dQw4w9WgXcQ",
        )

    def test_gpu_transcription_helper_declares_uv_cuda_dependencies(self) -> None:
        contents = GPU_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("nvidia-cublas-cu12", contents)
        self.assertIn("nvidia-cudnn-cu12", contents)
        self.assertIn("faster-whisper", contents)
        self.assertIn("yt-dlp", contents)
        self.assertNotIn("keep-audio", contents)

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
        self.assertIn("{{SOURCE_NOTES_PATH}}", contents)
        self.assertIn("{{CANDIDATE_SCRIPT_PATH}}", contents)
        self.assertIn("file paths, not pasted full script text", contents)
        self.assertIn("Do not paste the full script content into the prompt", contents)
        self.assertIn("must be readable local file paths", contents)
        self.assertNotIn("{{SOURCE_NOTES}}", contents)
        self.assertNotIn("{{CANDIDATE_SCRIPT}}", contents)
        self.assertIn("Do not leave template variables", contents)
        self.assertNotIn("[Paste", contents)
        self.assertIn("Assessment: ...", contents)
        self.assertIn("Criterion Result: PASS|FAIL", contents)
        self.assertIn("Do not output a criterion-level `PASS` or `FAIL` before the assessment text", contents)
        self.assertIn("Your first output line must be exactly `EVALUATION:`", contents)
        self.assertIn("treat that evaluator output as invalid and failed", contents)
        self.assertIn("before the assessment text", contents)
        self.assertNotIn("Reason:", contents)
        self.assertIn("Do not use speaker labels", contents)
        self.assertIn("Blend all provided sources into one unified podcast script", contents)
        self.assertIn("Do not mention source boundaries in the final script", contents)
        self.assertIn("Do not structure the final script as source-by-source explanation", contents)
        self.assertIn("Source Integration", contents)
        self.assertIn("./scripts/<descriptive-name>.txt", contents)
        self.assertIn("Do not save the podcast output inside `skills/podcast-writer/scripts/`", contents)
        self.assertIn("delete temporary working files", contents)
        self.assertIn("Do not delete user-provided original source files", contents)
        self.assertIn("Quote full URLs in shells such as zsh", contents)
        self.assertIn("It preserves transcript segment text", contents)
        self.assertIn("fetch_youtube_transcript.py", contents)
        self.assertIn("transcribe_youtube_gpu.py", contents)
        self.assertIn("must fail instead of using CPU when CUDA is unavailable", contents)
        self.assertIn("The default model is `turbo`", contents)

    def test_rubric_requires_evaluation_before_result_and_all_pass(self) -> None:
        contents = RUBRIC.read_text(encoding="utf-8")

        self.assertIn("Every item must be marked `PASS` or `FAIL`", contents)
        self.assertIn("RESULT: PASS` is allowed only when every item is `PASS`", contents)
        self.assertIn("When uncertain, choose `FAIL`", contents)
        self.assertIn("The first output line must be exactly `EVALUATION:`", contents)
        self.assertIn("evaluation is invalid and must be treated as `FAIL`", contents)
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
            "Source Integration",
            "Overall Content Value",
        ):
            self.assertIn(criterion, contents)

    def test_openai_yaml_default_prompt_mentions_skill(self) -> None:
        contents = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertIn("display_name: \"Podcast Writer\"", contents)
        self.assertIn("$podcast-writer", contents)


if __name__ == "__main__":
    unittest.main()
