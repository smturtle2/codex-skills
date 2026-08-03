from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "podcast-writer" / "scripts" / "fetch_youtube_transcript.py"
GPU_SCRIPT = REPO_ROOT / "skills" / "podcast-writer" / "scripts" / "transcribe_youtube_gpu.py"

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

if __name__ == "__main__":
    unittest.main()
