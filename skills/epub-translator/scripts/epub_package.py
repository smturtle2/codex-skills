"""Build and independently verify EPUB packages before atomic publication."""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import posixpath
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from epub_common import (CONTAINER_NS, DC_NS, EDITABLE_IMAGE_TYPES, EPUB_NS, EpubTranslatorError, OPF_NS, X, XHTML_NS,
                         archive_path, attr_value, canonical_archive_path, local_name, package_data, read_json,
                         resolve_reference, safe_join, sha256_bytes, uri_path, utc_now, write_json, write_xml)
from epub_resources import PublishedResources, image_media_type, read_ledger
from reading_flow import read_flow, render_document
from translation_state import TranslationState, read_edition

CANONICAL_CSS = """html, body { writing-mode: horizontal-tb; margin: 0; padding: 0; }
body { font-family: serif; line-height: 1.8; max-width: 40em; margin: auto; padding: 1.2em 1em; }
h1,h2,h3,h4,h5,h6 { line-height: 1.35; margin: 1.6em 0 .6em; }
p { margin: .9em 0; text-align: start; }
blockquote { margin: 1em; padding-inline-start: .8em; border-inline-start: 2px solid #ccc; }
ul,ol { padding-inline-start: 1.6em; } table { border-collapse: collapse; margin: 1em 0; }
td,th { border: 1px solid #ccc; padding: .4em .6em; }
figure { margin: 1.2em 0; text-align: center; } img,svg { max-width: 100%; height: auto; }
a { color: inherit; } em { font-style: italic; } strong { font-weight: bold; }
"""


def verify_epub(path: Path) -> dict:
    """Check bytes/manifest/reference graph; no dependence on a cached report."""
    issues = []
    documents = {}
    resources = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            name_set = set(names)
            if len(names) != len(name_set):
                issues.append("duplicate ZIP entry names")
            for name in names:
                safe_join(Path("/epub-package"), name)
                if name.startswith("/") or "\\" in name:
                    issues.append(f"invalid archive path: {name}")
            if not names or names[0] != "mimetype" or archive.read("mimetype") != b"application/epub+zip" or archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                issues.append("mimetype must be first, uncompressed, and application/epub+zip")
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile_el = container.find(f".//{{{CONTAINER_NS}}}rootfile")
            if rootfile_el is None or not rootfile_el.get("full-path"):
                raise EpubTranslatorError("container has no rootfile")
            rootfile = rootfile_el.get("full-path", "")
            safe_join(Path("/epub-package"), rootfile)
            opf = ET.fromstring(archive.read(rootfile))
            opf_ids = [attr_value(element, "id") for element in opf.iter() if attr_value(element, "id")]
            if len(opf_ids) != len(set(opf_ids)):
                issues.append("duplicate OPF ids")
            for element in opf.iter():
                refines = element.get("refines", "")
                if refines.startswith("#") and refines[1:] not in opf_ids:
                    issues.append(f"metadata refinement has no target: {refines}")
            metadata = opf.find(f"{{{OPF_NS}}}metadata")
            if opf.get("version") != "3.0" or metadata is None:
                issues.append("target OPF must have EPUB 3 metadata")
            if metadata is not None:
                identifier = opf.get("unique-identifier")
                if not any(el.get("id") == identifier and el.text for el in metadata.findall(f"{{{DC_NS}}}identifier")):
                    issues.append("OPF unique identifier is missing")
                for field in ("title", "language"):
                    if not any(el.text and el.text.strip() for el in metadata.findall(f"{{{DC_NS}}}{field}")):
                        issues.append(f"OPF {field} missing")
            manifest = opf.find(f"{{{OPF_NS}}}manifest")
            if manifest is None:
                raise EpubTranslatorError("OPF manifest missing")
            by_id = {}
            by_path = {}
            nav_count = 0
            for item in manifest:
                item_id, href, mt = item.get("id"), item.get("href"), item.get("media-type")
                if not item_id or not href or not mt or item_id in by_id:
                    issues.append("missing or duplicate manifest id/href/media-type")
                    continue
                target = archive_path(rootfile, href)
                safe_join(Path("/epub-package"), target)
                if target in by_path:
                    issues.append(f"duplicate manifest resource: {target}")
                by_id[item_id] = item
                by_path[target] = item
                if target not in name_set:
                    issues.append(f"manifest resource missing: {target}")
                    continue
                payload = archive.read(target)
                resources[target] = sha256_bytes(payload)
                if mt in EDITABLE_IMAGE_TYPES:
                    with tempfile.TemporaryDirectory(prefix="epub-raster-check-") as directory:
                        image_path = Path(directory) / "payload"
                        image_path.write_bytes(payload)
                        actual = image_media_type(image_path)
                    if actual != mt:
                        issues.append(f"image MIME/payload mismatch: {target}: {mt} != {actual}")
                if mt in ("application/xhtml+xml", "image/svg+xml"):
                    root = ET.fromstring(payload)
                    documents[target] = root
                    if mt == "application/xhtml+xml" and root.tag != X("html"):
                        issues.append(f"XHTML document has no XHTML html root: {target}")
                if "nav" in item.get("properties", "").split():
                    nav_count += 1
                    root = documents.get(target)
                    if root is None or not any(el.get(f"{{{EPUB_NS}}}type") == "toc" for el in root.iter()):
                        issues.append("navigation document has no toc nav")
            if nav_count != 1:
                issues.append("exactly one navigation document is required")
            spine = opf.find(f"{{{OPF_NS}}}spine")
            if spine is None or not list(spine):
                issues.append("spine is missing or empty")
            else:
                for item in spine:
                    target = by_id.get(item.get("idref"))
                    if target is None or target.get("media-type") != "application/xhtml+xml":
                        issues.append(f"invalid spine item: {item.get('idref')}")
            anchors = {}
            for name, root in documents.items():
                ids = [attr_value(el, "id") for el in root.iter() if attr_value(el, "id")]
                if len(ids) != len(set(ids)):
                    issues.append(f"duplicate anchors: {name}")
                anchors[name] = set(ids)
            for name, root in documents.items():
                for element in root.iter():
                    for key, href in element.attrib.items():
                        reference_attr = local_name(key) in ("href", "src", "poster") or (local_name(element.tag) == "object" and local_name(key) == "data")
                        if not reference_attr or not href:
                            continue
                        reference = resolve_reference(href, name)
                        if reference is None:
                            continue
                        target, fragment = reference
                        if target not in name_set or target not in by_path:
                            issues.append(f"broken internal link/resource: {name}: {href}")
                        elif fragment and fragment not in anchors.get(target, set()):
                            issues.append(f"missing fragment: {name}: {href}")
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile, EpubTranslatorError) as exc:
        issues.append(str(exc))
    return {"ok": not issues, "issues": issues, "resource_sha256": resources}


def build_opf(source: ET.Element, flow: dict, translations: dict, edition: dict, items: list[dict], spine: list[str], fingerprint: str) -> ET.Element:
    used = {attr_value(element, "id") for element in source.iter() if attr_value(element, "id")} | {row["id"] for row in items}
    identifier_id = unique_id("translation-bookid", used)
    package = ET.Element(f"{{{OPF_NS}}}package", {"version": "3.0", "unique-identifier": identifier_id, "{http://www.w3.org/XML/1998/namespace}lang": edition["language_tag"]})
    if source.get("prefix"):
        package.set("prefix", source.get("prefix"))
    original = source.find(f"{{{OPF_NS}}}metadata")
    metadata = copy.deepcopy(original) if original is not None else ET.Element(f"{{{OPF_NS}}}metadata")
    package.append(metadata)
    slots = {}
    for entry in flow.get("metadata", []):
        slots.setdefault(entry["field"], []).append(entry)
    for element in list(metadata):
        field = local_name(element.tag)
        if element.tag.startswith(f"{{{DC_NS}}}") and field in slots and element.text and element.text.strip():
            entry = slots[field].pop(0)
            element.text = translations[entry["id"]]
            if "{http://www.w3.org/XML/1998/namespace}lang" in element.attrib:
                element.set("{http://www.w3.org/XML/1998/namespace}lang", edition["language_tag"])
        if element.tag == f"{{{DC_NS}}}language" or element.get("property") == "dcterms:modified" or element.get("property", "").startswith("rendition:"):
            metadata.remove(element)
    ET.SubElement(metadata, f"{{{DC_NS}}}identifier", {"id": identifier_id}).text = "urn:sha256:" + fingerprint
    ET.SubElement(metadata, f"{{{DC_NS}}}language").text = edition["language_tag"]
    ET.SubElement(metadata, f"{{{OPF_NS}}}meta", {"property": "dcterms:modified"}).text = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = ET.SubElement(package, f"{{{OPF_NS}}}manifest")
    for row in items:
        attrs = {"id": row["id"], "href": row["href"], "media-type": row["media_type"]}
        if row.get("properties"):
            attrs["properties"] = row["properties"]
        ET.SubElement(manifest, f"{{{OPF_NS}}}item", attrs)
    spine_element = ET.SubElement(package, f"{{{OPF_NS}}}spine", {"page-progression-direction": edition["page_progression_direction"]})
    for entry in spine:
        ET.SubElement(spine_element, f"{{{OPF_NS}}}itemref", entry)
    return package


def unique_id(preferred: str, occupied: set) -> str:
    candidate = preferred
    index = 2
    while candidate in occupied:
        candidate = f"{preferred}-{index}"
        index += 1
    occupied.add(candidate)
    return candidate


def input_fingerprint(flow: dict, state: TranslationState, edition: dict, resources: PublishedResources) -> str:
    value = {"flow": flow, "translations": state.translations, "edition": edition,
             "source_opf": sha256_bytes((resources.workdir / "unpacked" / resources.rootfile).read_bytes()), "rootfile": resources.rootfile,
             "resources": [{"id": row["id"], "path": row["output_archive_path"], "href": row["output_opf_href"], "properties": row["properties"],
                            "media_type": row["output_media_type"], "sha256": row["selected_sha256"]} for row in resources.rows]}
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def generated_hrefs(flow: dict, resources: PublishedResources) -> tuple[str, str]:
    occupied = {doc["href"] for doc in flow["documents"]} | set(resources.by_source)
    index = 1
    while True:
        prefix = ".translation" if index == 1 else f".translation-{index}"
        nav, css = f"{prefix}/nav.xhtml", f"{prefix}/target.css"
        if nav not in occupied and css not in occupied:
            return nav, css
        index += 1


def prepare_inputs(workdir: Path, flow: dict | None = None, state: TranslationState | None = None) -> tuple[dict, TranslationState, dict, PublishedResources]:
    flow = read_flow(workdir) if flow is None else flow
    state = TranslationState(workdir, flow) if state is None else state
    state.require_complete()
    edition = read_edition(workdir)
    problems = [doc["source_error"] for doc in flow["documents"] if doc.get("source_error")]
    if problems:
        raise EpubTranslatorError("source document requires recovery: " + "; ".join(problems))
    jobs = read_json(workdir / "image-jobs.json")
    resources = PublishedResources(workdir, read_ledger(workdir), jobs)
    return flow, state, edition, resources


def build(workdir: Path, output: Path) -> dict:
    flow = read_flow(workdir)
    state = TranslationState(workdir, flow)
    report = {**state.report(), "ok": False, "generated_at": utc_now(), "broken_links": [], "broken_link_count": 0}
    write_json(workdir / "build-report.json", report)
    flow, state, edition, resources = prepare_inputs(workdir)
    manifest = read_json(workdir / "manifest.json")
    if manifest.get("epub") and output.resolve() == Path(manifest["epub"]).resolve():
        raise EpubTranslatorError("build failed: output path must differ from the source EPUB")
    rootfile, source_opf, source_items, _ = package_data(workdir / "unpacked")
    used_ids = {attr_value(element, "id") for element in source_opf.iter() if attr_value(element, "id")}
    nav_id = next((item["id"] for item in source_items if "nav" in item["properties"].split()), None) or unique_id("navigation", used_ids)
    css_id = unique_id("translation-css", used_ids)
    nav_href, css_href = generated_hrefs(flow, resources)
    rendering_edition = {**edition, "_css_href": css_href}
    fingerprint = input_fingerprint(flow, state, edition, resources)
    flow = copy.deepcopy(flow)
    for node in flow["blocks"]:
        if node["kind"] == "heading" and not node["anchors"]:
            node["anchors"] = ["toc-" + node["id"]]
    temp_archive = None
    try:
        with tempfile.TemporaryDirectory(prefix="epub-build-", dir=workdir) as directory:
            build_directory = Path(directory)
            items, spine, headings = [], [], []
            document_hashes = {}
            for index, doc in enumerate(flow["documents"], 1):
                document = render_document(doc, flow, state.translations, rendering_edition, resources.resolve_image)
                internal = canonical_archive_path(rootfile, doc["href"])
                destination = safe_join(build_directory, internal)
                write_xml(destination, document, XHTML_NS)
                document_hashes[internal] = sha256_bytes(destination.read_bytes())
                properties = []
                if any(el.tag.startswith("{http://www.w3.org/2000/svg}") for el in document.iter()):
                    properties.append("svg")
                if any(el.tag.startswith("{http://www.w3.org/1998/Math/MathML}") for el in document.iter()):
                    properties.append("mathml")
                item_id = doc.get("manifest_id") or unique_id(f"doc{index:04d}", used_ids)
                items.append({"id": item_id, "href": uri_path(doc["href"]), "media_type": "application/xhtml+xml", "properties": " ".join(properties)})
                if doc.get("in_spine", True):
                    spine.append({"idref": item_id, "linear": doc.get("linear", "yes")})
                for element in document.iter():
                    tag = local_name(element.tag)
                    if tag in tuple(f"h{i}" for i in range(1, 7)):
                        headings.append({"path": doc["href"], "fragment": element.get("id", ""), "text": "".join(element.itertext())})
            title = next((state.translations[entry["id"]] for entry in flow.get("metadata", []) if entry["field"] == "title"), "")
            nav = ET.Element(X("html"), {"lang": edition["language_tag"], "dir": edition["text_direction"]})
            ET.SubElement(ET.SubElement(nav, X("head")), X("title")).text = title
            toc = ET.SubElement(ET.SubElement(nav, X("body")), X("nav"), {f"{{{EPUB_NS}}}type": "toc", "id": "toc"})
            ET.SubElement(toc, X("h1")).text = title
            ol = ET.SubElement(toc, X("ol"))
            for heading in headings or [{"path": doc["href"], "text": title or doc["href"]} for doc in flow["documents"] if doc.get("in_spine", True)]:
                href = uri_path(posixpath.relpath(heading["path"], posixpath.dirname(nav_href)), heading.get("fragment"))
                ET.SubElement(ET.SubElement(ol, X("li")), X("a"), {"href": href}).text = heading["text"]
            write_xml(safe_join(build_directory, canonical_archive_path(rootfile, nav_href)), nav, XHTML_NS)
            css_path = safe_join(build_directory, canonical_archive_path(rootfile, css_href))
            css_path.parent.mkdir(parents=True, exist_ok=True)
            css_path.write_text(CANONICAL_CSS, encoding="utf-8")
            items.extend([{"id": nav_id, "href": nav_href, "media_type": "application/xhtml+xml", "properties": "nav"}, {"id": css_id, "href": css_href, "media_type": "text/css"}])
            items.extend(resources.copy_to(build_directory))
            package = build_opf(source_opf, flow, state.translations, edition, items, spine, fingerprint)
            write_xml(safe_join(build_directory, rootfile), package, OPF_NS)
            container = ET.Element(f"{{{CONTAINER_NS}}}container", {"version": "1.0"})
            ET.SubElement(ET.SubElement(container, f"{{{CONTAINER_NS}}}rootfiles"), f"{{{CONTAINER_NS}}}rootfile", {"full-path": rootfile, "media-type": "application/oebps-package+xml"})
            write_xml(build_directory / "META-INF/container.xml", container, CONTAINER_NS)
            output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".epub-translator-", suffix=".epub", dir=output.parent)
            os.close(descriptor)
            temp_archive = Path(temporary_name)
            with zipfile.ZipFile(temp_archive, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for path in sorted(build_directory.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(build_directory).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
            validation = verify_epub(temp_archive)
            for row in resources.rows:
                if validation["resource_sha256"].get(row["output_archive_path"]) != row["selected_sha256"]:
                    validation["issues"].append(f"packaged resource differs from selected payload: {row['output_archive_path']}")
            for path, digest in document_hashes.items():
                if validation["resource_sha256"].get(path) != digest:
                    validation["issues"].append(f"packaged document differs from rendered payload: {path}")
            validation["ok"] = not validation["issues"]
            if not validation["ok"]:
                report.update(ok=False, broken_links=validation["issues"], broken_link_count=len(validation["issues"]))
                raise EpubTranslatorError("build failed: broken internal links or invalid package: " + "; ".join(validation["issues"][:10]))
            report.update(ok=True, input_fingerprint=fingerprint, output_sha256=sha256_bytes(temp_archive.read_bytes()),
                          rootfile=rootfile, spine_hrefs=[d["href"] for d in flow["documents"] if d.get("in_spine", True)],
                          document_sha256=document_hashes, image_jobs=len(read_json(workdir / "image-jobs.json").get("jobs", [])),
                          resource_sha256={row["output_archive_path"]: row["selected_sha256"] for row in resources.rows},
                          package_validation=validation, flow_stats=flow["stats"], output=str(output.resolve()))
            os.replace(temp_archive, output)
            temp_archive = None
    except (OSError, EpubTranslatorError) as exc:
        report.update(ok=False, reason=str(exc))
        raise EpubTranslatorError(str(exc)) from exc
    finally:
        if temp_archive:
            temp_archive.unlink(missing_ok=True)
        write_json(workdir / "build-report.json", report)
    return {"ok": True, "output": str(output), "report": str(workdir / "build-report.json")}


def validate(workdir: Path, output: Path) -> dict:
    package = verify_epub(output)
    issues = list(package["issues"])
    try:
        flow, state, edition, resources = prepare_inputs(workdir)
        for row in resources.rows:
            if package["resource_sha256"].get(row["output_archive_path"]) != row["selected_sha256"]:
                issues.append(f"published resource differs from selected payload: {row['output_archive_path']}")
        report = read_json(workdir / "build-report.json")
        if report.get("input_fingerprint") != input_fingerprint(flow, state, edition, resources):
            issues.append("output was not built from the current validated translation state")
        if not output.is_file() or report.get("output_sha256") != sha256_bytes(output.read_bytes()):
            issues.append("output bytes differ from the successfully built artifact")
    except EpubTranslatorError as exc:
        issues.append(str(exc))
    return {"ok": not issues, "issues": issues, "output": str(output), "package_validation": package}
