from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

from PIL import Image


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "epub-translator" / "scripts" / "epub_translate.py"


class EpubTranslatorTests(unittest.TestCase):
    def run_script(self, *args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def make_epub(self, path: pathlib.Path, *, nav_in_spine: bool = False, broken_link: bool = False) -> None:
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="item/volume.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        spine_itemrefs = '<itemref idref="p1"/>'
        if nav_in_spine:
            spine_itemrefs += '\n    <itemref idref="nav"/>'
        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">demo</dc:identifier>
    <dc:title>負けヒロインが多すぎる！</dc:title>
    <dc:creator>雨森たきび</dc:creator>
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="xhtml/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="p1" href="xhtml/p1.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="style/book.css" media-type="text/css"/>
    <item id="cover" href="image/cover.jpg" media-type="image/jpeg"/>
    <item id="photo" href="image/photo" media-type="image/jpeg"/>
    <item id="diagram" href="image/diagram.svg" media-type="image/svg+xml"/>
  </manifest>
  <spine page-progression-direction="rtl">
    {spine_itemrefs}
  </spine>
</package>
"""
        nav = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja" class="vrtl">
  <head><title>目次</title><link rel="stylesheet" type="text/css" href="../style/book.css"/></head>
  <body><nav epub:type="toc"><ol><li><a href="p1.xhtml">第一章</a></li></ol></nav>
  <p>古い目次</p></body>
</html>
"""
        # page: ruby/rt, tcy, fixed-offset class, ideographic space, em/link, aside anchor, inline + block
        # images, list/table containers, nested inline img, empty anchored paragraph, optional broken link
        broken = '<a href="p1.xhtml#missingfrag">壊</a>' if broken_link else ""
        page = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja" class="vrtl">
  <head><title>第一章</title><link rel="stylesheet" type="text/css" href="../style/book.css"/></head>
  <body>
    <h1>第一章</h1>
    <p>八奈見さんは<em>言った</em>。<a href="#note1">脚注</a>を見る。{broken}</p>
    <p class="start-10em"><span class="tcy">12</span><ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby>の本文　続き<img src="../image/cover.jpg" alt="表紙"/></p>
    <aside id="note1"><p>脚注本文</p></aside>
    <p>追加メモ</p>
    <p>追加メモ</p>
    <p>リスト項目<span><img src="../image/cover.jpg" alt="表紙"/></span></p>
    <ul><li>項目一</li><li>項目二</li></ul>
    <table><tr><th>見出</th><td>セル一</td></tr><tr><td>セル二</td><td>セル三</td></tr></table>
    <p id="target-only"></p>
    <section id="ch1"><p>セクションの内部</p></section>
    <p><a href="#ch1">セクションへのリンク</a></p>
    <p title="註">註釈付きテキスト</p>
    <figure><img src="../image/cover.jpg" alt="表紙"/><figcaption>図の説明</figcaption></figure>
    <img src="../image/photo" alt="写真" aria-label="アイコン"/>
  </body>
</html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("item/volume.opf", opf)
            archive.writestr("item/xhtml/nav.xhtml", nav)
            archive.writestr("item/xhtml/p1.xhtml", page)
            archive.writestr("item/style/book.css", ".vrtl { writing-mode: vertical-rl; } .start-10em{margin-inline-start:10em}")
            archive.writestr("item/image/cover.jpg", b"placeholder-cover")
            archive.writestr("item/image/photo", b"placeholder-photo")
            archive.writestr("item/image/diagram.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    def make_malicious_epub(self, path: pathlib.Path, href: str) -> None:
        """EPUB whose manifest points a content doc at `href` (e.g. /etc/passwd, ../../x)."""
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="item/volume.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">evil</dc:identifier>
    <dc:title>evil</dc:title>
    <dc:creator>evil</dc:creator>
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="p1" href="{href}" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="p1"/></spine>
</package>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("item/volume.opf", opf)

    def _write_all_translations(self, run_dir: pathlib.Path, *, divergent: bool = False) -> None:
        translations_dir = run_dir / "translations"
        translations_dir.mkdir(parents=True, exist_ok=True)
        mapping = {
            "負けヒロインが多すぎる！": "패배 히로인이 너무 많아!",
            "雨森たきび": "아마모리 타키비",
            "八奈見さんは": "야나미 씨는",
            "言った": "말했다",
            "。": "。",
            "脚注": "각주",
            "を見る。": "를 본다.",
            "壊": "깨",
            "12": "12",
            "漢": "한",
            "字": "자",
            "の本文 続き": "의 본문 이어짐",
            "の本文": "의 본문",
            "続き": "이어짐",
            "脚注本文": "각주 본문",
            "表紙": "표지",
            "写真": "사진",
            "追加メモ": "추가 메모",
            "リスト項目": "목록 항목",
            "項目一": "항목 1",
            "項目二": "항목 2",
            "見出": "제목",
            "セル一": "셀 1",
            "セル二": "셀 2",
            "セル三": "셀 3",
            "セクションの内部": "섹션 내부",
            "セクションへのリンク": "섹션 링크",
            "註": "주",
            "註釈付きテキスト": "주석 달린 텍스트",
            "図の説明": "그림 설명",
            "アイコン": "아이콘",
            "目次": "목차",
            "第一章": "제1장",
        }
        # order-independent substring fallback: longest key wins
        ordered = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
        seen: dict[str, int] = {}
        for chunk_path in sorted((run_dir / "chunks").glob("chunk-*.json")):
            chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
            rows = []
            for item in chunk["items"]:
                source = item["source"]
                if source in mapping:
                    tr = mapping[source]
                else:
                    tr = source
                    for k, v in ordered:
                        if k in source:
                            tr = v
                            break
                if divergent and source == "追加メモ":
                    seen[source] = seen.get(source, 0) + 1
                    if seen[source] == 2:
                        tr = "메모 추가"
                rows.append({"id": item["id"], "translation": tr})
            (translations_dir / chunk_path.name).write_text(
                json.dumps(
                    {"schema_version": 3, "chunk_index": chunk["chunk_index"], "translations": rows},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def _abs_html(self, output: pathlib.Path) -> str:
        with zipfile.ZipFile(output) as z:
            xhtml_names = [n for n in z.namelist() if n.endswith(".xhtml")]
            return "\n".join(z.read(n).decode("utf-8") for n in xhtml_names)

    def test_ingest_build_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub)

            inspected = self.run_script("inspect", "--epub", str(epub), "--json", cwd=root)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            counts = json.loads(inspected.stdout)["counts"]
            self.assertEqual(counts["images"], 3)
            self.assertEqual(counts["editable_images"], 2)
            self.assertEqual(counts["unsupported_images"], 1)

            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["flow_schema_version"], 2)
            self.assertEqual(manifest["text_schema_version"], 3)
            self.assertGreater(manifest["block_count"], 0)
            self.assertGreater(manifest["slot_count"], 0)
            flow = json.loads((run_dir / "flow" / "book.flow.json").read_text(encoding="utf-8"))
            self.assertGreater(flow["stats"]["rubies_collapsed"], 0)
            # no raw rt sources should leak into chunks
            chunk_sources = {item["source"] for p in (run_dir / "chunks").glob("chunk-*.json") for item in json.loads(p.read_text(encoding="utf-8"))["items"]}
            self.assertNotIn("かん", chunk_sources)
            self.assertNotIn("じ", chunk_sources)
            # slim item shape only
            for p in (run_dir / "chunks").glob("chunk-*.json"):
                for item in json.loads(p.read_text(encoding="utf-8"))["items"]:
                    self.assertTrue(set(item.keys()) <= {"id", "source", "block_id", "block_type", "href", "inline"}, item)
            kinds = {json.loads(p.read_text(encoding="utf-8"))["kind"] for p in (run_dir / "chunks").glob("chunk-*.json")}
            self.assertIn("prose", kinds)
            self.assertIn("peripheral", kinds)
            # nested alt must ride the peripheral chunk, not prose
            peripheral = next(p for p in (run_dir / "chunks").glob("chunk-*.json") if json.loads(p.read_text(encoding="utf-8"))["kind"] == "peripheral")
            peripheral_sources = {item["source"] for item in json.loads(peripheral.read_text(encoding="utf-8"))["items"]}
            self.assertIn("表紙", peripheral_sources)

            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            self.assertEqual(len(jobs), 2)
            self.assertTrue(jobs[0]["source_export"].endswith(".jpg"))
            self.assertTrue(all(j["media_type"] != "image/svg+xml" for j in jobs))

            self._write_all_translations(run_dir)
            replacement = root / "replacement.png"
            Image.new("RGB", (4, 4), "#ffffff").save(replacement)
            recorded = self.run_script("record-image", "--workdir", str(run_dir), "--image-id", jobs[0]["id"], "--replacement", str(replacement), cwd=root)
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            skipped = self.run_script("record-image", "--workdir", str(run_dir), "--image-id", jobs[1]["id"], "--skip-no-text", cwd=root)
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            recorded_jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            self.assertTrue((run_dir / recorded_jobs[0]["replacement_export"]).is_file())
            self.assertTrue((run_dir / recorded_jobs[1]["replacement_export"]).is_file())

            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(built.returncode, 0, built.stderr + built.stdout)
            validated = self.run_script("validate", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertTrue(json.loads(validated.stdout)["ok"])

            with zipfile.ZipFile(output) as z:
                names = z.namelist()
                self.assertEqual(names[0], "mimetype")
                self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                xhtml_names = [n for n in names if n.endswith(".xhtml")]
                self.assertTrue(xhtml_names)
                all_xhtml = "\n".join(z.read(n).decode("utf-8") for n in xhtml_names if "nav" not in n)
                # source-only residue must be gone
                self.assertNotIn("<rt", all_xhtml)
                self.assertNotIn("<ruby", all_xhtml)
                self.assertNotIn("start-10em", all_xhtml)
                self.assertNotIn("vrtl", all_xhtml)
                self.assertNotIn("　", all_xhtml)
                # meaningful content preserved
                self.assertIn("야나미 씨는", all_xhtml)
                self.assertIn("<em>말했다</em>", all_xhtml)
                self.assertIn('href="#note1"', all_xhtml)
                self.assertIn('id="note1"', all_xhtml)
                # semantic list/table wrappers restored
                self.assertIn("<ul>", all_xhtml)
                self.assertIn("<li>항목 1</li>", all_xhtml)
                self.assertIn("<table>", all_xhtml)
                self.assertIn("<td>셀 1</td>", all_xhtml)
                # both table rows preserved
                self.assertEqual(all_xhtml.count("<tr>"), 2)
                # nested inline alt translated
                self.assertIn('alt="표지"', all_xhtml)
                # anchor-only block emits its id (no more off-by-one)
                self.assertIn('id="target-only"', all_xhtml)
                # transparent container id preserved → anchor target survives
                self.assertIn('<section id="ch1">', all_xhtml)
                self.assertIn('href="#ch1"', all_xhtml)
                # title/aria-label reattached with translated values
                self.assertIn('title="주"', all_xhtml)
                self.assertIn('aria-label="아이콘"', all_xhtml)
                # figure wraps its figcaption (valid content model)
                self.assertIn("<figure>", all_xhtml)
                fig_region = re.search(r"<figure>.*?</figure>", all_xhtml, re.S)
                self.assertTrue(fig_region and "<figcaption>그림 설명</figcaption>" in fig_region.group(0))
                # images still there
                self.assertTrue(any("cover" in n for n in names))
                self.assertTrue(any("photo" in n for n in names))
                opf_text = z.read("OEBPS/content.opf").decode("utf-8")
                self.assertIn('page-progression-direction="ltr"', opf_text)
                css_text = z.read("OEBPS/style/target.css").decode("utf-8")
                self.assertIn("horizontal-tb", css_text)
                # nav regenerated from translated headings
                nav_text = z.read("OEBPS/xhtml/nav.xhtml").decode("utf-8")
                self.assertIn("제1장", nav_text)

    def test_build_fails_when_translation_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir)
            first = sorted((run_dir / "translations").glob("chunk-*.json"))[0]
            data = json.loads(first.read_text(encoding="utf-8"))
            data["translations"] = data["translations"][1:]
            first.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("missing translations", (built.stderr + built.stdout).lower())

    def test_build_flags_terminology_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir, divergent=True)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            for j in jobs:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(built.returncode, 0, built.stderr)
            report = json.loads((run_dir / "build-report.json").read_text(encoding="utf-8"))
            self.assertGreater(report["divergence_count"], 0)
            self.assertTrue(any(d["source"] == "追加メモ" and len(d["translations"]) > 1 for d in report["divergences"]))

    def test_status_reports_seam(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            chunk_paths = sorted((run_dir / "chunks").glob("chunk-*.json"))
            first = json.loads(chunk_paths[0].read_text(encoding="utf-8"))
            rows = [{"id": it["id"], "translation": it["source"] + "-ko"} for it in first["items"]]
            (run_dir / "translations" / chunk_paths[0].name).write_text(
                json.dumps({"schema_version": 3, "chunk_index": first["chunk_index"], "translations": rows}, ensure_ascii=False),
                encoding="utf-8",
            )
            status = self.run_script("status", "--workdir", str(run_dir), cwd=root)
            self.assertEqual(status.returncode, 0, status.stderr)
            info = json.loads(status.stdout)
            self.assertEqual(info["last_finished_chunk"], first["chunk_index"])
            self.assertTrue(info["seam_tail"])
            self.assertEqual(info["next_chunk"], chunk_paths[1] and json.loads(chunk_paths[1].read_text(encoding="utf-8"))["chunk_index"])

    def test_path_traversal_read_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "evil.epub"
            run_dir = root / "run"
            self.make_malicious_epub(epub, "/etc/passwd")
            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            # no crash; the hostile doc is skipped and never parsed off the unpacked sandbox
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            flow = json.loads((run_dir / "flow" / "book.flow.json").read_text(encoding="utf-8"))
            self.assertEqual(flow["blocks"], [])
            self.assertTrue(all(d.get("unsafe") or d.get("missing") for d in flow["documents"]))

    def test_path_traversal_write_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "evil.epub"
            run_dir = root / "run"
            output = root / "out.epub"
            self.make_malicious_epub(epub, "xhtml/../../evil.xhtml")
            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            self._write_all_translations(run_dir)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("unsafe document href", (built.stderr + built.stdout).lower())
            for candidate in (root / "evil.xhtml", run_dir / "evil.xhtml"):
                self.assertFalse(candidate.exists())

    def test_edition_invalid_enum_fails_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            edition = json.loads((run_dir / "edition.json").read_text(encoding="utf-8"))
            edition["page_progression_direction"] = "vertical"
            (run_dir / "edition.json").write_text(json.dumps(edition, ensure_ascii=False), encoding="utf-8")
            self._write_all_translations(run_dir)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            for j in jobs:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("page_progression_direction", (built.stderr + built.stdout).lower())

    def test_unresolved_image_job_blocks_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("unresolved image job", (built.stderr + built.stdout).lower())

    def test_cross_document_broken_link_fails_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub, broken_link=True)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            for j in jobs:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("broken internal links", (built.stderr + built.stdout).lower())

    def test_nav_in_spine_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            output = root / "translated.epub"
            self.make_epub(epub, nav_in_spine=True)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            for j in jobs:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(built.returncode, 0, built.stderr)
            with zipfile.ZipFile(output) as z:
                nav_text = z.read("OEBPS/xhtml/nav.xhtml").decode("utf-8")
            self.assertIn("제1장", nav_text)
            self.assertNotIn("古い目次", nav_text)

    def test_build_refuses_output_equal_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "source.epub"
            run_dir = root / "run"
            self.make_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self._write_all_translations(run_dir)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            for j in jobs:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            original = epub.read_bytes()
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(epub), cwd=root)
            self.assertNotEqual(built.returncode, 0)
            self.assertIn("must differ", (built.stderr + built.stdout).lower())
            self.assertEqual(epub.read_bytes(), original)


    def make_tiny_epub(self, path: pathlib.Path, *, no_spine: bool = False, no_body: bool = False, missing_image: bool = False) -> None:
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        spine_inner = "" if no_spine else "\n    <itemref idref=\"p1\"/>"
        image_item = '<item id="gone" href="image/missing.jpg" media-type="image/jpeg"/>' if missing_image else '<item id="cover" href="image/cover.jpg" media-type="image/jpeg"/>'
        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">tiny</dc:identifier>
    <dc:title>小型本</dc:title>
    <dc:creator>小さな人</dc:creator>
    <dc:language>ja</dc:language>
  </metadata>
  <manifest>
    <item id="p1" href="xhtml/p1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="xhtml/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {image_item}
  </manifest>
  <spine page-progression-direction="ltr">{spine_inner}
  </spine>
</package>
"""
        body = "" if no_body else "<p>本文</p><p><ruby>漢<rt>かん</rt>字</ruby></p>"
        page_body = "" if no_body else f"<body>{body}</body>"
        page = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja"><head><title>本体</title></head>{page_body}</html>
"""
        nav = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目次</title></head><body><nav epub:type="toc"/></body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/xhtml/p1.xhtml", page)
            archive.writestr("OEBPS/xhtml/nav.xhtml", nav)
            if not missing_image:
                archive.writestr("OEBPS/image/cover.jpg", b"placeholder-cover")

    def _translate_every_item(self, run_dir: pathlib.Path) -> None:
        tdir = run_dir / "translations"
        tdir.mkdir(parents=True, exist_ok=True)
        for chunk_path in sorted((run_dir / "chunks").glob("chunk-*.json")):
            chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
            rows = [{"id": it["id"], "translation": it["source"] + "-ko"} for it in chunk["items"]]
            (tdir / chunk_path.name).write_text(
                json.dumps({"schema_version": 3, "chunk_index": chunk["chunk_index"], "translations": rows}, ensure_ascii=False),
                encoding="utf-8",
            )

    def test_ruby_elements_stat(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "tiny.epub"
            run_dir = root / "run"
            self.make_tiny_epub(epub)
            self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            flow = json.loads((run_dir / "flow" / "book.flow.json").read_text(encoding="utf-8"))
            self.assertEqual(flow["stats"]["ruby_elements"], 1)
            self.assertEqual(flow["stats"]["rubies_collapsed"], 1)

    def test_no_spine_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "tiny.epub"
            run_dir = root / "run"
            self.make_tiny_epub(epub, no_spine=True)
            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["spine_hrefs"]), {"xhtml/p1.xhtml", "xhtml/nav.xhtml"})

    def test_empty_body_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "tiny.epub"
            run_dir = root / "run"
            output = root / "out.epub"
            self.make_tiny_epub(epub, no_body=True)
            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            flow = json.loads((run_dir / "flow" / "book.flow.json").read_text(encoding="utf-8"))
            self.assertTrue(flow["documents"] and flow["documents"][0].get("no_body"))
            self._translate_every_item(run_dir)
            for j in json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]:
                self.run_script("record-image", "--workdir", str(run_dir), "--image-id", j["id"], "--skip-no-text", cwd=root)
            built = self.run_script("build", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(built.returncode, 0, built.stderr)

    def test_missing_image_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            epub = root / "tiny.epub"
            run_dir = root / "run"
            self.make_tiny_epub(epub, missing_image=True)
            ingested = self.run_script("ingest", "--epub", str(epub), "--workdir", str(run_dir), cwd=root)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            jobs_data = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(jobs_data["jobs"], [])
            self.assertTrue(any(u["id"] == "gone" and u.get("missing") for u in jobs_data["unsupported"]))
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["unsupported_image_count"], 1)


if __name__ == "__main__":
    unittest.main()
