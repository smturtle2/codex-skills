from __future__ import annotations

import json
import pathlib
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

    def make_epub(self, path: pathlib.Path) -> None:
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="item/volume.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        opf = """<?xml version="1.0" encoding="UTF-8"?>
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
    <itemref idref="p1"/>
  </spine>
</package>
"""
        nav = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja" class="vrtl">
  <head><title>目次</title><link rel="stylesheet" type="text/css" href="../style/book.css"/></head>
  <body><nav epub:type="toc"><ol><li><a href="p1.xhtml">第一章</a></li></ol></nav></body>
</html>
"""
        page = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja" class="vrtl">
  <head><title>第一章</title><link rel="stylesheet" type="text/css" href="../style/book.css"/></head>
  <body>
    <p>八奈見さんは<em>言った</em>。<a href="#note1">脚注</a>を見る。</p>
    <p><ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby>の本文<img src="../image/cover.jpg" alt="表紙"/></p>
    <aside id="note1"><p>脚注本文</p></aside>
    <img src="../image/photo" alt="写真"/>
  </body>
</html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("item/volume.opf", opf)
            archive.writestr("item/xhtml/nav.xhtml", nav)
            archive.writestr("item/xhtml/p1.xhtml", page)
            archive.writestr("item/style/book.css", ".vrtl { writing-mode: vertical-rl; }")
            archive.writestr("item/image/cover.jpg", b"placeholder")
            archive.writestr("item/image/photo", b"placeholder")
            archive.writestr("item/image/diagram.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    def write_translations(self, run_dir: pathlib.Path) -> None:
        translations_dir = run_dir / "translations"
        for chunk_path in sorted((run_dir / "chunks").glob("chunk-*.json")):
            chunk = json.loads(chunk_path.read_text(encoding="utf-8"))
            rows = []
            for segment in chunk["segments"]:
                source = segment["source"]
                if "負けヒロイン" in source:
                    translation = "패배 히로인이 너무 많아!"
                elif "雨森" in source:
                    translation = "아마모리 타키비"
                elif "八奈見" in source:
                    translation = "야나미 씨는"
                elif source == "言った":
                    translation = "말했다"
                elif source == "脚注":
                    translation = "각주"
                elif source == "を見る。":
                    translation = "를 본다."
                elif source == "漢":
                    translation = "한"
                elif source == "字":
                    translation = "자"
                elif source == "の本文":
                    translation = "의 본문"
                elif "脚注本文" in source:
                    translation = "각주 본문"
                elif "表紙" in source:
                    translation = "표지"
                elif "写真" in source:
                    translation = "사진"
                elif "目次" in source:
                    translation = "목차"
                elif source == "。":
                    translation = "."
                else:
                    translation = "제1장"
                rows.append({"id": segment["id"], "translation": translation})
            (translations_dir / chunk_path.name).write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "chunk_index": chunk["chunk_index"],
                        "translations": rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    def test_prepare_apply_package_validate_epub(self) -> None:
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

            prepared = self.run_script(
                "prepare",
                "--epub",
                str(epub),
                "--workdir",
                str(run_dir),
                cwd=root,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["text_schema_version"], 2)
            self.assertGreater(manifest["segment_count"], 0)
            self.assertEqual(manifest["unsupported_image_count"], 1)
            chunks = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_dir / "chunks").glob("chunk-*.json"))
            ]
            kinds = {segment["kind"] for chunk in chunks for segment in chunk["segments"]}
            sources = {segment["source"] for chunk in chunks for segment in chunk["segments"]}
            units = [unit for chunk in chunks for unit in chunk["units"]]
            self.assertTrue(units)
            self.assertTrue(any("八奈見さんは言った。脚注を見る。" in unit["source"] for unit in units))
            self.assertTrue(any(part.get("tag") == "img" for unit in units for part in unit.get("parts", [])))
            self.assertIn("xhtml_text", kinds)
            self.assertIn("xhtml_tail", kinds)
            self.assertNotIn("xhtml_block", kinds)
            self.assertNotIn("かん", sources)
            self.assertNotIn("じ", sources)
            jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            self.assertEqual(len(jobs), 2)
            self.assertTrue(all(job["media_type"] != "image/svg+xml" for job in jobs))
            self.assertEqual(jobs[0]["status"], "pending_review")
            self.assertTrue(jobs[1]["source_export"].endswith(".jpg"))

            self.write_translations(run_dir)
            applied = self.run_script(
                "apply-text",
                "--workdir",
                str(run_dir),
                "--translations",
                str(run_dir / "translations"),
                cwd=root,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            page = (run_dir / "unpacked" / "item" / "xhtml" / "p1.xhtml").read_text(encoding="utf-8")
            self.assertIn("야나미 씨는", page)
            self.assertIn("<em>말했다</em>", page)
            self.assertIn('href="#note1"', page)
            self.assertIn('src="../image/cover.jpg"', page)
            self.assertIn("<rt>かん</rt>", page)
            self.assertIn("<rt>じ</rt>", page)
            self.assertIn('alt="표지"', page)
            self.assertNotIn("codex-epub-translator.css", page)

            replacement = root / "replacement.png"
            Image.new("RGB", (4, 4), "#ffffff").save(replacement)
            recorded = self.run_script(
                "record-image",
                "--workdir",
                str(run_dir),
                "--image-id",
                jobs[0]["id"],
                "--replacement",
                str(replacement),
                cwd=root,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            skipped = self.run_script(
                "record-image",
                "--workdir",
                str(run_dir),
                "--image-id",
                jobs[1]["id"],
                "--skip-no-text",
                cwd=root,
            )
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            recorded_jobs = json.loads((run_dir / "image-jobs.json").read_text(encoding="utf-8"))["jobs"]
            edited_export = run_dir / recorded_jobs[0]["replacement_export"]
            skipped_export = run_dir / recorded_jobs[1]["replacement_export"]
            self.assertTrue(edited_export.is_file())
            self.assertTrue(skipped_export.is_file())
            self.assertEqual(skipped_export.read_bytes(), (run_dir / jobs[1]["source_export"]).read_bytes())

            packaged = self.run_script("package", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(packaged.returncode, 0, packaged.stderr)

            validated = self.run_script("validate", "--workdir", str(run_dir), "--output", str(output), cwd=root)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            validation = json.loads(validated.stdout)
            self.assertTrue(validation["ok"])


if __name__ == "__main__":
    unittest.main()
