"""Repeatable subtitle-creator checks.

Run from the repository root with Python 3.11+ and uv:
    uv run python -m unittest discover -s tests -p 'test_subtitle_creator.py' -v

Each automated case creates its source, workspace, and destinations inside a TemporaryDirectory and removes them after the case. No STT, media, model access, third-party dependencies, or persistent environment configuration is required.
Successful runs must preserve source data, represent every source cue through translated groups or explicit omissions, and produce the exact expected text and timestamps. Invalid/incomplete work and refused writes must leave source, work, and existing outputs unchanged, without abandoned publication temporaries.

For the separately run behavioral evaluation, write BEHAVIORAL_SRT to an English SRT under a unique .codex-skills/subtitle-creator/<run-id>/ directory, prepare its source/work files, and give an independent latest-available Terra/max worker the skill and a request for Korean subtitles without supplying this rubric.
Assess natural contextual idioms, the 15/50 contrast, the I scream/ice cream exchange, removal of non-dialogue annotations while preserving inline speech, source coverage, and sentence boundaries. With no media supplied, the result must distinguish source-based timing from verified speech synchronization and must not claim STT use. Keep the worker result, final subtitles, and assessment in that run for reproduction; unittest does not execute or judge model output.
"""
from __future__ import annotations

import copy
from html import unescape
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills/subtitle-creator/scripts/subtitle_io.py"

BEHAVIORAL_SRT = """1
00:00:00,500 --> 00:00:02,000
[SOFT MUSIC]

2
00:00:02,100 --> 00:00:03,500
MAYA: When I said we should table

3
00:00:03,500 --> 00:00:05,000
the proposal, I meant discuss it later.

4
00:00:05,200 --> 00:00:08,000
LEO: Right. Not put it on the furniture.

5
00:00:08,100 --> 00:00:10,400
[door closes] MAYA: We have fifteen minutes,

6
00:00:10,400 --> 00:00:12,000
not fifty.

7
00:00:12,200 --> 00:00:13,500
LEO: I scream?

8
00:00:13,500 --> 00:00:15,800
MAYA: Ice cream. Two scoops, remember?

9
00:00:16,000 --> 00:00:17,000
[laughs]

10
00:00:17,200 --> 00:00:19,800
LEO: Then let's call it a day.

11
00:00:20,000 --> 00:00:22,800
MAYA: Once the backup finishes. We're not done yet.
"""

SOURCE_SRT = """10
00:00:01,000 --> 00:00:02,000
When I said


20
00:00:02,000 --> 00:00:03,400
we would go home.

30
00:00:04,000 --> 00:00:04,900
[Music]

40
00:00:05,100 --> 00:00:06,500
Bye. See you tomorrow.
"""

SOURCE_VTT = """WEBVTT source track
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0

STYLE
::cue { color: white; }

REGION
id:speakers
width:80%

NOTE preserved source context
Two people talking.

intro
00:01.000 --> 00:02.000 align:start
<v Maya>When I said

continuation
00:02.000 --> 00:03.400
<00:02.000>we would go home.

sound
00:04.000 --> 00:04.900
[Music]

farewell
00:05.100 --> 00:06.500
Bye. See you tomorrow.
"""


def accepted_work() -> dict:
    return {
        "version": 1,
        "target_language": "ko",
        "groups": [
            {"source_ids": ["s1", "s2"], "cues": [
                {"start_ms": 1000, "end_ms": 3400, "text": "집에 가자고\n말했을 때 말이야"},
            ]},
            {"source_ids": ["s4"], "cues": [
                {"start_ms": 5100, "end_ms": 5700, "text": "잘 가"},
                {"start_ms": 5700, "end_ms": 6500, "text": "내일 보자 👋"},
            ]},
        ],
        "omitted": [{"source_ids": ["s3"], "reason": "Non-dialogue music annotation."}],
        "pending": [],
        "notes": ["Timing follows source cues; matching audio was not supplied."],
    }


class SubtitleCreatorTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="subtitle-creator-tests-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def run_helper(self, *args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
            capture_output=True, text=True, encoding="utf-8", check=False,
            cwd=cwd or self.root,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def result(self, *args: str | Path, expected: int = 0, cwd: Path | None = None) -> dict:
        run = self.run_helper(*args, cwd=cwd)
        self.assertEqual(run.returncode, expected, run.stderr or run.stdout)
        self.assertNotIn("Traceback", run.stderr)
        return json.loads(run.stdout)

    def prepare(self, format_: str = "srt", name: str = "case") -> tuple[Path, Path]:
        directory = self.root / name
        directory.mkdir()
        source = directory / f"English source.{format_}"
        text = SOURCE_SRT if format_ == "srt" else SOURCE_VTT
        original = ("\ufeff" + text.replace("\n", "\r\n")).encode("utf-8")
        source.write_bytes(original)
        run = directory / "saved run"
        self.result("inspect", "--input", source, "--workdir", run)
        self.assertEqual(source.read_bytes(), original)
        return source, run

    def save_work(self, run: Path, work: dict) -> None:
        (run / "work.json").write_text(json.dumps(work, ensure_ascii=False), encoding="utf-8")

    def snapshot(self, *paths: Path) -> dict[Path, bytes]:
        return {path: path.read_bytes() for path in paths if path.exists()}

    def assert_preserved(self, snapshot: dict[Path, bytes]) -> None:
        for path, before in snapshot.items():
            self.assertEqual(path.read_bytes(), before, f"Changed protected data: {path}")
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_inspect_preserves_srt_vtt_source_evidence_and_optional_encoding(self) -> None:
        for format_ in ("srt", "vtt"):
            with self.subTest(format=format_):
                source, run = self.prepare(format_, format_)
                original = source.read_bytes()
                data = json.loads((run / "source.json").read_text())
                self.assertEqual([cue["id"] for cue in data["cues"]], ["s1", "s2", "s3", "s4"])
                self.assertEqual([(cue["start_ms"], cue["end_ms"]) for cue in data["cues"]],
                                 [(1000, 2000), (2000, 3400), (4000, 4900), (5100, 6500)])
                self.assertEqual(data["source"]["path"], str(source.resolve()))
                self.assertEqual(data["source"]["format"], format_)
                self.assertEqual(data["cues"][2]["text"], "[Music]")
                if format_ == "srt":
                    self.assertEqual(data["cues"][0]["identifier"], "10")
                else:
                    self.assertEqual(data["cues"][0]["text"], "<v Maya>When I said")
                    self.assertEqual(data["cues"][0]["settings"], "align:start")
                    self.assertTrue(data["cues"][1]["text"].startswith("<00:02.000>"))
                    self.assertEqual(len(data["metadata"]), 4)
                self.assertEqual(source.read_bytes(), original)
        legacy = self.root / "legacy.srt"
        legacy.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCafé\n".encode("cp1252"))
        data = self.result("inspect", "--input", legacy, "--encoding", "cp1252")
        self.assertEqual(data["cues"][0]["text"], "Café")
        self.assertFalse((self.root / ".codex-skills").exists())

    def test_merge_split_omission_and_exact_srt_vtt_publication(self) -> None:
        source, run = self.prepare()
        self.save_work(run, accepted_work())
        before = self.snapshot(source, run / "source.json", run / "work.json")
        expected = {
            "srt": "1\n00:00:01,000 --> 00:00:03,400\n집에 가자고\n말했을 때 말이야\n\n"
                   "2\n00:00:05,100 --> 00:00:05,700\n잘 가\n\n"
                   "3\n00:00:05,700 --> 00:00:06,500\n내일 보자 👋\n\n",
            "vtt": "WEBVTT\n\n00:00:01.000 --> 00:00:03.400\n집에 가자고\n말했을 때 말이야\n\n"
                   "00:00:05.100 --> 00:00:05.700\n잘 가\n\n"
                   "00:00:05.700 --> 00:00:06.500\n내일 보자 👋\n\n",
        }
        for format_, expected_text in expected.items():
            with self.subTest(format=format_):
                output = source.parent / f"Korean output.{format_}"
                data = self.result("export", "--workdir", run, "--output", output, "--media-duration-ms", "6500")
                self.assertTrue(data["export_ready"])
                self.assertTrue(data["publication_matches"])
                self.assertEqual(data["saved_path"], str(output.resolve()))
                self.assertEqual(data["metrics"]["assigned_source_cues"], 4)
                self.assertEqual(data["metrics"]["output_cues"], 3)
                self.assertEqual(output.read_text(encoding="utf-8"), expected_text)
                self.assertTrue(self.result("check", "--workdir", run, "--output", output)["publication_matches"])
        self.assert_preserved(before)

    def test_partial_work_resumes_without_reinitializing_or_replacing_source(self) -> None:
        source, run = self.prepare()
        initial = self.result("check", "--workdir", run, expected=1)
        self.assertTrue(initial["valid"])
        self.assertFalse(initial["complete"])
        partial = accepted_work()
        partial["groups"] = partial["groups"][:1]
        partial["pending"] = [{"source_ids": ["s4"], "reason": "Resolve the farewell wording."}]
        self.save_work(run, partial)
        before = self.snapshot(source, run / "source.json", run / "work.json")
        state = self.result("check", "--workdir", run, expected=1)
        self.assertEqual(state["unprocessed_ids"], ["s4"])
        refused = self.run_helper("inspect", "--input", source, "--workdir", run)
        self.assertEqual(refused.returncode, 2)
        self.assert_preserved(before)
        self.save_work(run, accepted_work())
        nested = self.root / "different working directory"
        nested.mkdir()
        output = source.parent / "resumed.ko.srt"
        self.assertTrue(self.result("export", "--workdir", run, "--output", output, cwd=nested)["export_ready"])
        self.assertEqual((run / "source.json").read_bytes(), before[run / "source.json"])
        self.assertEqual(json.loads((run / "work.json").read_text())["groups"][0], partial["groups"][0])
        self.assertEqual(source.read_bytes(), before[source])
        self.assertFalse((nested / ".codex-skills").exists())

    def test_invalid_or_incomplete_work_cannot_create_or_replace_output(self) -> None:
        cases = {
            "unprocessed speech": lambda work: work["groups"].pop(),
            "unset target": lambda work: work.update(target_language=""),
            "pending interpretation": lambda work: work["pending"].append({"source_ids": ["s1"], "reason": "Unclear."}),
            "unknown source": lambda work: work["groups"][0]["source_ids"].append("s999"),
            "duplicate in group": lambda work: work["groups"][0]["source_ids"].append("s1"),
            "translated and omitted": lambda work: work["omitted"].append({"source_ids": ["s1"], "reason": "Duplicate assignment."}),
            "unexplained omission": lambda work: work["omitted"][0].update(reason=""),
            "non-integer time": lambda work: work["groups"][0]["cues"][0].update(start_ms=1000.5),
            "boolean time": lambda work: work["groups"][0]["cues"][0].update(start_ms=True),
            "negative time": lambda work: work["groups"][0]["cues"][0].update(start_ms=-1),
            "empty duration": lambda work: work["groups"][0]["cues"][0].update(end_ms=1000),
            "empty text": lambda work: work["groups"][0]["cues"][0].update(text=" "),
            "blank payload line": lambda work: work["groups"][0]["cues"][0].update(text="첫째\n\n둘째"),
            "backwards sequence": lambda work: work["groups"].reverse(),
            "malformed groups": lambda work: work.update(groups={}),
        }
        for index, (name, change) in enumerate(cases.items()):
            with self.subTest(case=name):
                source, run = self.prepare(name=f"invalid-{index}")
                work = accepted_work()
                change(work)
                self.save_work(run, work)
                output = source.parent / "existing.ko.srt"
                output.write_bytes(b"Accepted prior output\n")
                before = self.snapshot(source, run / "source.json", run / "work.json", output)
                state = self.result("check", "--workdir", run, expected=1)
                self.assertFalse(state["export_ready"])
                blocked = self.result("export", "--workdir", run, "--output", output, "--overwrite", expected=1)
                self.assertFalse(blocked["export_ready"])
                new_output = source.parent / "new.ko.srt"
                self.result("export", "--workdir", run, "--output", new_output, expected=1)
                self.assertFalse(new_output.exists())
                self.assert_preserved(before)

    def test_malformed_json_and_subtitle_timing_report_controlled_input_errors(self) -> None:
        for filename in ("source.json", "work.json"):
            with self.subTest(file=filename):
                source, run = self.prepare(name=filename)
                self.save_work(run, accepted_work())
                (run / filename).write_text('{"version": 1,', encoding="utf-8")
                output = source.parent / "accepted.srt"
                output.write_bytes(b"Existing output")
                before = self.snapshot(source, run / "source.json", run / "work.json", output)
                for command in ("check", "export"):
                    args = [command, "--workdir", run]
                    if command == "export":
                        args += ["--output", output, "--overwrite"]
                    result = self.run_helper(*args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertTrue(result.stderr.startswith("error:"))
                    self.assertNotIn("Traceback", result.stderr)
                self.assert_preserved(before)
        malformed = {
            "minutes.srt": "1\n00:61:00,000 --> 00:62:00,000\nHello\n",
            "missing-separator.srt": "1\n00:00:01,000 --> 00:00:02,000\nHello\n2\n00:00:03,000 --> 00:00:04,000\nBye\n",
            "missing-header.vtt": "00:01.000 --> 00:02.000\nHello\n",
        }
        for name, payload in malformed.items():
            with self.subTest(source=name):
                source = self.root / name
                source.write_text(payload, encoding="utf-8")
                before = source.read_bytes()
                run = self.root / f"{name}-run"
                result = self.run_helper("inspect", "--input", source, "--workdir", run)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(run.exists())
                self.assertEqual(source.read_bytes(), before)

    def test_overwrite_is_explicit_and_source_or_work_paths_are_always_protected(self) -> None:
        source, run = self.prepare()
        self.save_work(run, accepted_work())
        output = source.parent / "existing.ko.srt"
        output.write_bytes(b"Accepted prior output")
        before = self.snapshot(source, run / "source.json", run / "work.json", output)
        refused = self.run_helper("export", "--workdir", run, "--output", output)
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assert_preserved(before)
        self.assertTrue(self.result("export", "--workdir", run, "--output", output, "--overwrite")["publication_matches"])
        self.assertNotEqual(output.read_bytes(), before[output])
        protected = self.snapshot(source, run / "source.json", run / "work.json")
        for path in protected:
            with self.subTest(protected=path.name):
                refused = self.run_helper("export", "--workdir", run, "--output", path, "--overwrite")
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assert_preserved(protected)

    def test_source_aliases_cannot_be_overwritten(self) -> None:
        source, run = self.prepare()
        self.save_work(run, accepted_work())
        before = self.snapshot(source, run / "source.json", run / "work.json")
        supported = 0
        for name, make_alias in (("symlink", lambda path: path.symlink_to(source)), ("hardlink", lambda path: os.link(source, path))):
            with self.subTest(alias=name):
                alias = source.parent / f"{name}.srt"
                try:
                    make_alias(alias)
                except (OSError, NotImplementedError):
                    continue
                supported += 1
                refused = self.run_helper("export", "--workdir", run, "--output", alias, "--overwrite")
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertEqual(alias.read_bytes(), before[source])
                self.assert_preserved(before)
        if not supported:
            self.skipTest("Filesystem cannot create source aliases")

    def test_literal_text_and_timing_like_dialogue_keep_their_display_meaning(self) -> None:
        source, run = self.prepare()
        work = accepted_work()
        literal = "<b>문자 그대로</b> &amp; & <\n00:00:01,000 --> 00:00:02,000"
        work["groups"][0]["cues"][0]["text"] = literal
        self.save_work(run, work)
        for format_ in ("srt", "vtt"):
            with self.subTest(format=format_):
                output = source.parent / f"literal.{format_}"
                result = self.result("export", "--workdir", run, "--output", output)
                self.assertTrue(result["publication_matches"])
                blocks = output.read_text().strip().split("\n\n")
                first_cue = blocks[0] if format_ == "srt" else blocks[1]
                payload = "\n".join(first_cue.split("\n")[2 if format_ == "srt" else 1:])
                self.assertEqual(unescape(payload), literal)
                self.assertNotIn("<b>", payload)
                self.assertIn("--&gt;", payload)
                self.assertEqual(result["metrics"]["output_cues"], 3)

    def test_changed_work_or_published_text_and_times_are_not_reported_as_matching(self) -> None:
        source, run = self.prepare()
        work = accepted_work()
        self.save_work(run, work)
        output = source.parent / "accepted.srt"
        self.result("export", "--workdir", run, "--output", output)
        published = output.read_bytes()
        for change in (lambda item: item.update(text="수정된 번역"), lambda item: item.update(end_ms=3300)):
            with self.subTest(change=change):
                updated = copy.deepcopy(work)
                change(updated["groups"][0]["cues"][0])
                self.save_work(run, updated)
                state = self.result("check", "--workdir", run, "--output", output, expected=1)
                self.assertFalse(state["publication_matches"])
                self.assertFalse(state["export_ready"])
                self.assertEqual(output.read_bytes(), published)
        self.save_work(run, work)
        output.write_bytes(published.replace("집에".encode(), "회사에".encode()))
        self.assertFalse(self.result("check", "--workdir", run, "--output", output, expected=1)["publication_matches"])

    def test_media_bounds_and_overlaps_are_distinguished_from_invalid_timing(self) -> None:
        source, run = self.prepare()
        work = accepted_work()
        work["groups"][1]["cues"][1]["start_ms"] = 5600
        self.save_work(run, work)
        state = self.result("check", "--workdir", run, "--media-duration-ms", "6500")
        self.assertTrue(state["export_ready"])
        self.assertEqual(state["metrics"]["overlaps"], [{"earlier_cue": 2, "cue": 3, "overlap_ms": 100}])
        self.assertTrue(state["warnings"])
        output = source.parent / "too-short-media.srt"
        before = self.snapshot(source, run / "source.json", run / "work.json")
        state = self.result("export", "--workdir", run, "--output", output, "--media-duration-ms", "6400", expected=1)
        self.assertFalse(state["valid"])
        self.assertFalse(output.exists())
        self.assert_preserved(before)

    def test_annotation_only_source_can_publish_an_explicitly_empty_track(self) -> None:
        source = self.root / "annotations.srt"
        source.write_text("1\n00:00:01,000 --> 00:00:02,000\n[Music]\n", encoding="utf-8")
        run = self.root / "annotation-run"
        self.result("inspect", "--input", source, "--workdir", run)
        self.save_work(run, {"version": 1, "target_language": "ko", "groups": [],
                             "omitted": [{"source_ids": ["s1"], "reason": "Non-dialogue music."}],
                             "pending": [], "notes": []})
        before = self.snapshot(source, run / "source.json", run / "work.json")
        for format_, expected in (("srt", ""), ("vtt", "WEBVTT\n\n")):
            with self.subTest(format=format_):
                output = self.root / f"empty.{format_}"
                state = self.result("export", "--workdir", run, "--output", output)
                self.assertTrue(state["publication_matches"])
                self.assertEqual(state["metrics"]["output_cues"], 0)
                self.assertEqual(output.read_text(), expected)
                self.assertTrue(self.result("check", "--workdir", run, "--output", output)["export_ready"])
        self.assert_preserved(before)


if __name__ == "__main__":
    unittest.main()
