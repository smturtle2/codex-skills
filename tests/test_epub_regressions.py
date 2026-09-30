from __future__ import annotations

import contextlib
import io
import json
import posixpath
import re
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/epub-translator/scripts"
sys.path.insert(0, str(SCRIPTS))
import reading_flow
import epub_package
from epub_common import EpubTranslatorError, read_json, write_json
from epub_package import build, validate, verify_epub
from epub_resources import record_image
from epub_translate import ingest, main
from reading_flow import read_flow, record_legacy_recovery
from translation_state import TranslationState

XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"


def raster(format="JPEG", color="red"):
    payload = io.BytesIO()
    Image.new("RGB", (3, 3), color).save(payload, format=format)
    return payload.getvalue()


def make_source(path, body, *, chapter="chapter.xhtml", resources=(), metadata="", linear="yes", nav_body=None, body_attrs=""):
    rootfile = "OPS/book.opf"
    items = [f'<item id="chapter" href="{quote(chapter, safe="/")}" media-type="application/xhtml+xml"/>']
    files = {f"OPS/{chapter}": f'<html xmlns="{XHTML}"><body{body_attrs}>{body}</body></html>'.encode()}
    spine = f'<itemref idref="chapter" linear="{linear}"/>'
    if nav_body is not None:
        items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        files["OPS/nav.xhtml"] = f'<html xmlns="{XHTML}"><body>{nav_body}</body></html>'.encode()
        spine = '<itemref idref="nav" linear="no"/>' + spine
    for item_id, archive_path, media_type, payload, properties in resources:
        href = quote(posixpath.relpath(archive_path, "OPS"), safe="/")
        items.append(f'<item id="{item_id}" href="{href}" media-type="{media_type}" properties="{properties}"/>')
        files[archive_path] = payload
    files[rootfile] = (f'<package xmlns="{OPF}" xmlns:dc="{DC}" version="3.0" unique-identifier="bookid">'
        f'<metadata><dc:identifier id="bookid">source-book</dc:identifier><dc:title>Title</dc:title>'
        f'<dc:language>ja</dc:language>{metadata}</metadata><manifest>{"".join(items)}</manifest>'
        f'<spine>{spine}</spine></package>').encode()
    files["META-INF/container.xml"] = (f'<container xmlns="{CONTAINER}" version="1.0"><rootfiles>'
        f'<rootfile full-path="{rootfile}" media-type="application/oebps-package+xml"/></rootfiles></container>').encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, payload in files.items():
            archive.writestr(name, payload)


def start_run(root, body, **options):
    source, run = root / "source.epub", root / "run"
    make_source(source, body, **options)
    ingest(source, run, 5000, 1500)
    return run


def translate(run, *, replacements=None, preserve_existing=False):
    edition = read_json(run / "edition.json")
    edition.update(target_language="en", language_tag="en", text_direction="ltr")
    write_json(run / "edition.json", edition)
    for path in sorted((run / "chunks").glob("chunk-*.json")):
        destination = run / "translations" / path.name
        if preserve_existing and destination.exists():
            continue
        chunk = read_json(path)
        rows = [{"id": item["id"], "translation": (replacements or {}).get(item["source"], item["source"])} for item in chunk["items"]]
        write_json(destination, {"schema_version": chunk["schema_version"], "chunk_index": chunk["chunk_index"], "translations": rows})


def status(run):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = main(["status", "--workdir", str(run)])
    if result != 0:
        raise AssertionError(output.getvalue())
    return json.loads(output.getvalue())


def package(output):
    with zipfile.ZipFile(output) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(f".//{{{CONTAINER}}}rootfile").get("full-path")
        return rootfile, ET.fromstring(archive.read(rootfile))


def v2_paragraph(block, href, slot, source, *, anchors=(), spine_index=0):
    # Literal v2 shape observed from the previous exporter, not inferred from v3.
    return {"id": block, "kind": "paragraph", "href": href, "spine_index": spine_index,
            "anchors": list(anchors), "attr_slots": [], "children": [], "tokens": [
                {"type": "text", "id": slot, "source": source, "inline": []}], "text": source, "review_flags": []}


def legacy_run(root, *, recover=True, nav_text=None):
    nav_body = None if nav_text is None else '<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc"><ol/></nav>'
    if nav_text:
        nav_body += f"<p>{nav_text}</p>"
    body = '<p id="old-paragraph">Same</p>'
    if recover:
        body = f"<section>Same{body}</section>"
    run = start_run(root, body, nav_body=nav_body, body_attrs=' title="New recovery attribute"' if recover else "")
    blocks, documents, items = [], [], []
    if nav_text is not None:
        roots = []
        if nav_text:
            roots = ["b000001"]
            blocks.append(v2_paragraph("b000001", "nav.xhtml", "t000001", nav_text))
            items.append({"id": "t000001", "source": nav_text, "block_id": "b000001", "block_type": "paragraph", "href": "nav.xhtml"})
        documents.append({"href": "nav.xhtml", "internal": "OPS/nav.xhtml", "roots": roots})
    first = 2 if nav_text else 1
    paragraph = f"b{first + int(recover):06d}"
    slot = "t000002" if nav_text else "t000001"
    if recover:
        blocks.append({"id": f"b{first:06d}", "kind": "section", "href": "chapter.xhtml", "spine_index": int(nav_text is not None),
                       "anchors": [], "attr_slots": [], "children": [paragraph], "tokens": [], "text": "", "review_flags": []})
    blocks.append(v2_paragraph(paragraph, "chapter.xhtml", slot, "Same", anchors=["old-paragraph"], spine_index=int(nav_text is not None)))
    documents.append({"href": "chapter.xhtml", "internal": "OPS/chapter.xhtml", "roots": [f"b{first:06d}"]})
    items.append({"id": slot, "source": "Same", "block_id": paragraph, "block_type": "paragraph", "href": "chapter.xhtml"})
    write_json(run / "flow/book.flow.json", {"schema_version": 2, "generated_at": "legacy-fixture", "documents": documents,
        "blocks": blocks, "stats": {"rubies_collapsed": 0, "ruby_elements": 0, "wrappers_flattened": 0, "ideographic_spaces_normalized": 0}})
    for path in (run / "chunks").glob("*.json"):
        path.unlink()
    write_json(run / "chunks/chunk-0001.json", {"schema_version": 3, "chunk_index": 1, "kind": "peripheral", "items": [
        {"id": "m000001", "source": "Title", "block_id": None, "block_type": "metadata", "href": "OPS/book.opf"}]})
    write_json(run / "chunks/chunk-0002.json", {"schema_version": 3, "chunk_index": 2, "kind": "prose", "items": items})
    translate(run, replacements={"Same": "Original paragraph", nav_text: "Retired navigation"} if nav_text else {"Same": "Original paragraph"})
    return run, slot


class EpubRegressionTests(unittest.TestCase):
    def test_mixed_flow_conserves_units_and_wrapped_opaque_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = io.BytesIO()
            with wave.open(audio, "wb") as wav:
                wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\x00\x00" * 8)
            body = ('lead<h1>Begin</h1><span><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg></span>'
                '<section>Section<p>Whole <em><span title="Hint" aria-label="Label" id="inline-label">sentence</span></em> end'
                '<br id="line-break" title="Break"/><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>'
                '<img src="cover.jpg" alt="Cover"/></p>tail</section><span><audio src="tone.wav"/></span><p>After</p><p>⟦⟧</p>End')
            run = start_run(root, body, resources=[("cover", "OPS/cover.jpg", "image/jpeg", raster(), ""),
                ("tone", "OPS/tone.wav", "audio/wav", audio.getvalue(), "")])
            chunks = [read_json(path) for path in sorted((run / "chunks").glob("*.json"))]
            prose = [item for chunk in chunks if chunk["kind"] == "prose" for item in chunk["items"]]
            self.assertEqual([item["source"] for item in prose[:3]], ["lead", "Begin", "Section"])
            self.assertEqual(len([item for item in prose if item["source"].startswith("Whole ")]), 1)
            translate(run)
            for job in read_json(run / "image-jobs.json")["jobs"]:
                record_image(run, job["id"], None, True)
            output = root / "result.epub"
            build(run, output)
            with zipfile.ZipFile(output) as archive:
                target = ET.fromstring(archive.read("OPS/chapter.xhtml"))
            def events(element):
                result = []
                if element.text and element.text.strip():
                    result.append(("text", element.text.strip()))
                for child in element:
                    tag = child.tag.rsplit("}", 1)[-1]
                    result.extend([("media", tag)] if tag in ("svg", "audio", "math", "img", "br") else events(child))
                    if child.tail and child.tail.strip():
                        result.append(("text", child.tail.strip()))
                return result
            source_body = ET.fromstring(f'<body xmlns="{XHTML}">{body}</body>')
            self.assertEqual(events(target.find(f"{{{XHTML}}}body")), events(source_body))
            self.assertEqual(target.find(".//{http://www.w3.org/2000/svg}path").get("d"), "M0 0L1 1")
            self.assertEqual(target.find(f'.//{{{XHTML}}}span[@id="inline-label"]').get("aria-label"), "Label")
            self.assertEqual(target.find(f'.//{{{XHTML}}}br[@id="line-break"]').get("title"), "Break")
            self.assertTrue(verify_epub(output)["ok"])
            whole = next(item for item in prose if item["source"].startswith("Whole "))
            for path in (run / "translations").glob("*.json"):
                data = read_json(path)
                for row in data["translations"]:
                    if row["id"] == whole["id"]:
                        row["translation"] = "".join(re.findall(r"⟦[^⟧]*⟧", whole["source"]))
                        write_json(path, data)
            self.assertIn("empty translated prose", " ".join(TranslationState(run, read_flow(run)).errors))

    def test_uri_layout_replacement_mime_and_publication_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
            run = start_run(root, '<p><img src="../../images/cover%23100%25.jpg" alt="Cover"/><img src="diagram%231.svg"/></p>',
                chapter="chapter files/p%#.xhtml", linear="no", resources=[
                    ("cover", "images/cover#100%.jpg", "image/jpeg", raster(), ""),
                    ("diagram", "OPS/chapter files/diagram#1.svg", "image/svg+xml", svg, "")],
                metadata='<dc:identifier id="translation-bookid">collision-one</dc:identifier>'
                    '<dc:identifier id="translation-bookid-2">collision-two</dc:identifier><meta name="cover" content="cover"/>')
            initial = status(run)
            self.assertTrue(initial["valid"])
            self.assertFalse(initial["text_complete"])
            self.assertFalse(initial["build_ready"])
            translate(run)
            ready_text = status(run)
            self.assertTrue(ready_text["text_complete"])
            self.assertFalse(ready_text["build_ready"])
            self.assertIn("unresolved image", " ".join(ready_text["build_blockers"]))
            replacement = root / "replacement.bin"
            replacement.write_bytes(raster("PNG", "blue"))
            record_image(run, "img0001", replacement, False)
            self.assertTrue(status(run)["build_ready"])
            output = root / "result.epub"
            build(run, output)
            rootfile, opf = package(output)
            self.assertEqual(rootfile, "OPS/book.opf")
            ids = [element.get("id") for element in opf.iter() if element.get("id")]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertNotIn(opf.get("unique-identifier"), ("translation-bookid", "translation-bookid-2"))
            identifier = opf.find(f'.//{{{DC}}}identifier[@id="{opf.get("unique-identifier")}"]')
            self.assertTrue(identifier.text.startswith("urn:sha256:"))
            manifest = {element.get("id"): element for element in opf.findall(f".//{{{OPF}}}item")}
            self.assertEqual(manifest["cover"].get("href"), "../images/cover%23100%25.jpg")
            self.assertEqual(manifest["cover"].get("media-type"), "image/png")
            self.assertIn("cover-image", manifest["cover"].get("properties", "").split())
            self.assertEqual(opf.find(f".//{{{OPF}}}itemref").get("linear"), "no")
            with zipfile.ZipFile(output) as archive:
                chapter = ET.fromstring(archive.read("OPS/chapter files/p%#.xhtml"))
                refs = [element.get("src") for element in chapter.findall(f".//{{{XHTML}}}img")]
                self.assertEqual(refs, ["../../images/cover%23100%25.jpg", "diagram%231.svg"])
                for href in refs:
                    parts = urlsplit(href)
                    self.assertFalse(parts.fragment)
                    target = posixpath.normpath(posixpath.join("OPS/chapter files", unquote(parts.path)))
                    self.assertIn(target, archive.namelist())
                with Image.open(io.BytesIO(archive.read("images/cover#100%.jpg"))) as image:
                    self.assertEqual(image.format, "PNG")
                self.assertEqual(archive.read("OPS/chapter files/diagram#1.svg"), svg)
            self.assertTrue(validate(run, output)["ok"])
            original_output = output.read_bytes()
            real_copy = epub_package.PublishedResources.copy_to
            def corrupt_copy(resources, directory):
                manifest = real_copy(resources, directory)
                (directory / "images/cover#100%.jpg").write_bytes(raster("PNG", "green"))
                return manifest
            with patch.object(epub_package.PublishedResources, "copy_to", new=corrupt_copy):
                with self.assertRaisesRegex(EpubTranslatorError, "packaged resource differs"):
                    build(run, output)
            self.assertEqual(output.read_bytes(), original_output)

    def test_legacy_ownership_and_interrupted_recovery_preserve_existing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, original_slot = legacy_run(root)
            originals = {path: path.read_bytes() for folder in ("chunks", "translations") for path in (run / folder).glob("*.json")}
            flow = read_flow(run)
            paragraph = next(node for node in flow["blocks"] if "old-paragraph" in node["anchors"])
            self.assertEqual([part["atom_id"] for part in paragraph["unit"]["parts"] if part.get("atom_id")], [original_slot])
            recovered_text = next(item for item in flow["recovery_items"] if item["block_type"] == "text")
            self.assertEqual(recovered_text["source"], "Same")
            real_write = reading_flow.write_json_atomic
            def interrupt(path, data):
                if path.parent.name == "chunks" and data.get("legacy_recovery") and data["kind"] == "prose":
                    raise OSError("interrupted after recovery plan and first chunk")
                real_write(path, data)
            with patch.object(reading_flow, "write_json_atomic", side_effect=interrupt):
                with self.assertRaises(OSError):
                    record_legacy_recovery(run, flow)
            persisted = {path: path.read_bytes() for path in (run / "chunks").glob("*.json")}
            record_legacy_recovery(run, read_flow(run))
            self.assertEqual(record_legacy_recovery(run, read_flow(run)), [])
            for path, before in {**originals, **persisted}.items():
                self.assertEqual(path.read_bytes(), before)
            state = TranslationState(run, read_flow(run))
            self.assertEqual(state.errors, [])
            self.assertEqual(state.translations[original_slot], "Original paragraph")
            all_ids = [item["id"] for path in (run / "chunks").glob("*.json") for item in read_json(path)["items"]]
            self.assertEqual(len(all_ids), len(set(all_ids)))
            translate(run, replacements={"Same": "Recovered wrapper", "New recovery attribute": "Translated attribute"}, preserve_existing=True)
            output = root / "result.epub"
            build(run, output)
            with zipfile.ZipFile(output) as archive:
                target = ET.fromstring(archive.read("OPS/chapter.xhtml"))
            self.assertEqual(target.find(f'.//{{{XHTML}}}p[@id="old-paragraph"]').text, "Original paragraph")
            self.assertIn("Recovered wrapper", "".join(target.itertext()))
            self.assertTrue(any(element.get("title") == "Translated attribute" for element in target.iter()))
            for path, before in originals.items():
                self.assertEqual(path.read_bytes(), before)

    def test_legacy_navigation_before_content_keeps_observed_slot_allocation(self):
        for nav_text in ("", "Old toc"):
            with self.subTest(nav_text=nav_text), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                run, original_slot = legacy_run(root, recover=False, nav_text=nav_text)
                originals = {path: path.read_bytes() for path in (run / "translations").glob("*.json")}
                flow = read_flow(run)
                paragraph = next(node for node in flow["blocks"] if "old-paragraph" in node["anchors"])
                self.assertEqual([part["atom_id"] for part in paragraph["unit"]["parts"] if part.get("atom_id")], [original_slot])
                self.assertEqual(TranslationState(run, flow).errors, [])
                output = root / "result.epub"
                build(run, output)
                with zipfile.ZipFile(output) as archive:
                    target = ET.fromstring(archive.read("OPS/chapter.xhtml"))
                    self.assertEqual(target.find(f'.//{{{XHTML}}}p[@id="old-paragraph"]').text, "Original paragraph")
                    self.assertFalse(any(b"Retired navigation" in archive.read(name) for name in archive.namelist() if name.endswith(".xhtml")))
                for path, before in originals.items():
                    self.assertEqual(path.read_bytes(), before)

    def test_validate_checks_current_inputs_and_output_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = start_run(root, "<p>Paragraph</p>", resources=[("diagram", "OPS/diagram.svg", "image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "")])
            translate(run)
            output = root / "result.epub"
            build(run, output)
            self.assertTrue(validate(run, output)["ok"])
            changes = [
                (run / "translations/chunk-0001.json", lambda data: data["translations"][0].update(translation="Changed title")),
                (run / "edition.json", lambda data: data.update(text_direction="rtl")),
                (run / "resources.json", lambda data: data["resources"][0].update(properties="remote-resources")),
            ]
            for path, change in changes:
                with self.subTest(path=path.name):
                    before = path.read_bytes()
                    data = read_json(path)
                    change(data)
                    write_json(path, data)
                    try:
                        result = validate(run, output)
                        self.assertFalse(result["ok"])
                        self.assertIn("current validated translation state", " ".join(result["issues"]))
                    finally:
                        path.write_bytes(before)
            original = output.read_bytes()
            output.write_bytes(original + b"unexpected bytes")
            self.assertFalse(validate(run, output)["ok"])

    def test_failed_final_package_check_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = start_run(root, '<p><a href="#missing">Link</a></p>')
            translate(run)
            output = root / "result.epub"
            output.write_bytes(b"previous artifact")
            with self.assertRaisesRegex(EpubTranslatorError, "broken internal"):
                build(run, output)
            self.assertEqual(output.read_bytes(), b"previous artifact")
            self.assertEqual(list(root.glob(".epub-translator-*.epub")), [])


if __name__ == "__main__":
    unittest.main()
