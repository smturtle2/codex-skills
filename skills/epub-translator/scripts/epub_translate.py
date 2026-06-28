#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
from __future__ import annotations

import argparse
import datetime as dt
import json
import posixpath
import re
import shutil
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"

TEXT_SCHEMA_VERSION = 2
TEXT_ATTRS = ("alt", "title", "aria-label")
SKIP_TEXT_TAGS = {"script", "style"}
RUBY_NOTE_TAGS = {"rt", "rp"}
STRUCTURE_MARKER_TAGS = {"br", "hr", "img"}
TARGET_STRUCTURE_PRESERVED_ATTRS = {"id", "href", "src"}
READING_UNIT_TAGS = {
    "article",
    "aside",
    "blockquote",
    "caption",
    "dd",
    "div",
    "dt",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "nav",
    "p",
    "section",
    "td",
    "th",
    "title",
}
EDITABLE_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMAGE_SUFFIX_BY_MEDIA_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class EpubTranslatorError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def has_text_content(value: str | None) -> bool:
    return bool(value and value.strip())


def safe_join(base: Path, internal_name: str) -> Path:
    base_resolved = base.resolve()
    candidate = (base / internal_name).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise EpubTranslatorError(f"Unsafe EPUB path: {internal_name}") from exc
    return candidate


def safe_extract(epub: Path, destination: Path) -> None:
    with zipfile.ZipFile(epub) as archive:
        for info in archive.infolist():
            if info.is_dir():
                safe_join(destination, info.filename).mkdir(parents=True, exist_ok=True)
                continue
            target = safe_join(destination, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def parse_xml(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        raise EpubTranslatorError(f"Could not parse XML: {path}") from exc


def register_namespaces(default_ns: str) -> None:
    ET.register_namespace("", default_ns)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("epub", EPUB_NS)


def write_xml(path: Path, tree: ET.ElementTree, default_ns: str) -> None:
    register_namespaces(default_ns)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def container_rootfile(epub_root: Path) -> str:
    container_path = epub_root / "META-INF" / "container.xml"
    tree = parse_xml(container_path)
    rootfile = tree.getroot().find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise EpubTranslatorError("META-INF/container.xml has no rootfile full-path")
    return rootfile.get("full-path", "")


def opf_root(epub_root: Path, rootfile: str) -> tuple[Path, ET.ElementTree, ET.Element]:
    path = safe_join(epub_root, rootfile)
    tree = parse_xml(path)
    return path, tree, tree.getroot()


def manifest_items(opf: ET.Element) -> list[dict]:
    manifest = opf.find(f"{{{OPF_NS}}}manifest")
    if manifest is None:
        raise EpubTranslatorError("OPF manifest missing")
    items: list[dict] = []
    for item in manifest.findall(f"{{{OPF_NS}}}item"):
        items.append(
            {
                "id": item.get("id", ""),
                "href": item.get("href", ""),
                "media_type": item.get("media-type", ""),
                "properties": item.get("properties", ""),
            }
        )
    return items


def spine_info(opf: ET.Element) -> dict:
    spine = opf.find(f"{{{OPF_NS}}}spine")
    if spine is None:
        return {"page_progression_direction": None, "idrefs": []}
    return {
        "page_progression_direction": spine.get("page-progression-direction"),
        "idrefs": [itemref.get("idref", "") for itemref in spine.findall(f"{{{OPF_NS}}}itemref")],
    }


def metadata_value(opf: ET.Element, tag: str) -> str | None:
    value = opf.find(f".//{{{DC_NS}}}{tag}")
    if value is None or value.text is None:
        return None
    return value.text.strip()


def full_internal_path(rootfile: str, manifest_href: str) -> str:
    opf_dir = posixpath.dirname(rootfile)
    return posixpath.normpath(posixpath.join(opf_dir, manifest_href))


def inspect_epub(epub: Path) -> dict:
    with zipfile.ZipFile(epub) as archive:
        names = archive.namelist()
        with zipfile.ZipFile(epub) as source, source.open("META-INF/container.xml") as container:
            container_xml = ET.parse(container)
        rootfile = container_xml.getroot().find(f".//{{{CONTAINER_NS}}}rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise EpubTranslatorError("META-INF/container.xml has no rootfile full-path")
        rootfile_path = rootfile.get("full-path", "")
        with archive.open(rootfile_path) as opf_file:
            opf_tree = ET.parse(opf_file)
    root = opf_tree.getroot()
    items = manifest_items(root)
    images = [item for item in items if item["media_type"].startswith("image/")]
    editable_images = [item for item in images if item["media_type"] in EDITABLE_IMAGE_MEDIA_TYPES]
    unsupported_images = [item for item in images if item["media_type"] not in EDITABLE_IMAGE_MEDIA_TYPES]
    xhtml = [item for item in items if item["media_type"] == "application/xhtml+xml"]
    css = [item for item in items if item["media_type"] == "text/css"]
    return {
        "epub": str(epub),
        "entry_count": len(names),
        "rootfile": rootfile_path,
        "title": metadata_value(root, "title"),
        "creator": metadata_value(root, "creator"),
        "language": metadata_value(root, "language"),
        "spine": spine_info(root),
        "counts": {
            "images": len(images),
            "editable_images": len(editable_images),
            "unsupported_images": len(unsupported_images),
            "xhtml": len(xhtml),
            "css": len(css),
            "manifest_items": len(items),
        },
        "images": [
            {
                "id": item["id"],
                "href": full_internal_path(rootfile_path, item["href"]),
                "media_type": item["media_type"],
                "editable": item["media_type"] in EDITABLE_IMAGE_MEDIA_TYPES,
            }
            for item in images
        ],
    }


def element_at_path(root: ET.Element, path: list[int]) -> ET.Element:
    element = root
    for index in path:
        children = list(element)
        if index >= len(children):
            raise EpubTranslatorError(f"XML path no longer exists: {path}")
        element = children[index]
    return element


def path_key(path: list[int]) -> str:
    return "/".join(str(part) for part in path) if path else "."


def collect_xhtml_segments(
    tree: ET.ElementTree,
    href: str,
    next_id,
) -> tuple[list[dict], dict[str, list[dict]]]:
    root = tree.getroot()
    segments: list[dict] = []
    unit_parts: dict[str, list[dict]] = {}

    def add_segment(
        kind: str,
        path: list[int],
        source: str,
        unit_key: str,
        attr: str | None = None,
        child_index: int | None = None,
        tag: str | None = None,
        after_tag: str | None = None,
    ) -> None:
        segment = {
            "id": next_id(),
            "kind": kind,
            "href": href,
            "path": path,
            "source": normalize_text(source),
            "context_before": "",
            "context_after": "",
            "_unit_key": unit_key,
        }
        if tag:
            segment["tag"] = tag
        if attr:
            segment["attribute"] = attr
        if child_index is not None:
            segment["child_index"] = child_index
        if after_tag:
            segment["after_tag"] = after_tag
        segments.append(segment)
        part = {
            "type": "slot",
            "segment_id": segment["id"],
            "kind": kind,
            "source": segment["source"],
        }
        if tag:
            part["tag"] = tag
        if attr:
            part["attribute"] = attr
        if after_tag:
            part["after_tag"] = after_tag
        unit_parts.setdefault(unit_key, []).append(part)

    def add_marker(unit_key: str, child: ET.Element) -> None:
        name = local_name(child.tag)
        marker = {"type": "marker", "tag": name}
        for attr in ("href", "src", "alt", "title"):
            if child.get(attr):
                marker[attr] = child.get(attr)
        unit_parts.setdefault(unit_key, []).append(marker)

    def visit(element: ET.Element, path: list[int], current_unit: str | None = None) -> None:
        name = local_name(element.tag)
        if name in SKIP_TEXT_TAGS or name in RUBY_NOTE_TAGS:
            return
        if name in READING_UNIT_TAGS or current_unit is None:
            current_unit = f"{href}:text:{path_key(path)}"
        for attr in TEXT_ATTRS:
            if has_text_content(element.get(attr)):
                add_segment(
                    "xhtml_attribute",
                    path,
                    element.get(attr) or "",
                    f"{href}:attr:{path_key(path)}:{attr}",
                    attr,
                    tag=name,
                )
        if has_text_content(element.text):
            add_segment("xhtml_text", path, element.text or "", current_unit, tag=name)
        for index, child in enumerate(list(element)):
            child_name = local_name(child.tag)
            if child_name in STRUCTURE_MARKER_TAGS:
                add_marker(current_unit, child)
            visit(child, [*path, index], current_unit)
            if has_text_content(child.tail):
                add_segment(
                    "xhtml_tail",
                    path,
                    child.tail or "",
                    current_unit,
                    child_index=index,
                    tag=name,
                    after_tag=child_name,
                )

    visit(root, [])
    for index, segment in enumerate(segments):
        if index > 0:
            segment["context_before"] = segments[index - 1]["source"]
        if index + 1 < len(segments):
            segment["context_after"] = segments[index + 1]["source"]
    return segments, unit_parts


def unit_source_from_parts(parts: list[dict]) -> str:
    rendered: list[str] = []
    for part in parts:
        if part["type"] == "slot":
            rendered.append(part["source"])
        elif part["type"] == "marker":
            rendered.append(f"[{part['tag']}]")
    return normalize_text("".join(rendered))


def build_text_units(segments: list[dict], unit_parts: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for segment in segments:
        unit_key = segment.get("_unit_key")
        if not unit_key:
            continue
        if unit_key not in grouped:
            grouped[unit_key] = []
            order.append(unit_key)
        grouped[unit_key].append(segment)

    units: list[dict] = []
    for index, unit_key in enumerate(order, start=1):
        unit_segments = grouped[unit_key]
        parts = unit_parts.get(unit_key, [])
        units.append(
            {
                "id": f"u{index:06d}",
                "source": unit_source_from_parts(parts),
                "segment_ids": [segment["id"] for segment in unit_segments],
                "parts": parts,
            }
        )
        for segment in unit_segments:
            segment["unit_id"] = f"u{index:06d}"
            segment.pop("_unit_key", None)
    for segment in segments:
        segment.pop("_unit_key", None)
    return units


def collect_opf_segments(
    tree: ET.ElementTree,
    href: str,
    next_id,
) -> list[dict]:
    root = tree.getroot()
    wanted = {"title", "creator", "publisher", "description", "subject"}
    segments: list[dict] = []

    def visit(element: ET.Element, path: list[int]) -> None:
        if local_name(element.tag) in wanted and has_text_content(element.text):
            source = element.text or ""
            segments.append(
                {
                    "id": next_id(),
                    "kind": "opf_metadata",
                    "href": href,
                    "path": path,
                    "source": normalize_text(source),
                    "context_before": "",
                    "context_after": "",
                    "unit_id": "metadata",
                }
            )
        for index, child in enumerate(list(element)):
            visit(child, [*path, index])

    visit(root, [])
    return segments


def chunk_segments(
    segments: list[dict],
    units: list[dict],
    chunks_dir: Path,
    max_chars: int = 6000,
    max_segments: int = 80,
) -> int:
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunk: list[dict] = []
    chunk_units: list[dict] = []
    char_count = 0
    index = 1

    def flush() -> None:
        nonlocal chunk, chunk_units, char_count, index
        if not chunk:
            return
        write_json(
            chunks_dir / f"chunk-{index:04d}.json",
            {
                "schema_version": TEXT_SCHEMA_VERSION,
                "chunk_index": index,
                "units": chunk_units,
                "segments": chunk,
            },
        )
        index += 1
        chunk = []
        chunk_units = []
        char_count = 0

    segments_by_unit: dict[str, list[dict]] = {}
    for segment in segments:
        unit_id = segment.get("unit_id")
        if unit_id:
            segments_by_unit.setdefault(unit_id, []).append(segment)

    metadata_segments = segments_by_unit.get("metadata", [])
    if metadata_segments:
        metadata_unit = {
            "id": "metadata",
            "source": "\n".join(segment["source"] for segment in metadata_segments),
            "segment_ids": [segment["id"] for segment in metadata_segments],
            "parts": [
                {
                    "type": "slot",
                    "segment_id": segment["id"],
                    "kind": segment["kind"],
                    "source": segment["source"],
                }
                for segment in metadata_segments
            ],
        }
        units_in_order = [metadata_unit, *units]
    else:
        units_in_order = units

    for unit in units_in_order:
        unit_segments = segments_by_unit.get(unit["id"], [])
        size = sum(len(segment["source"]) for segment in unit_segments)
        if chunk and (char_count + size > max_chars or len(chunk) + len(unit_segments) > max_segments):
            flush()
        chunk_units.append(unit)
        chunk.extend(unit_segments)
        char_count += size
    flush()
    return index - 1


def make_segment_id_factory():
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"t{counter:06d}"

    return next_id


def prepare_run(args: argparse.Namespace) -> int:
    epub = Path(args.epub).expanduser().resolve()
    workdir = Path(args.workdir).expanduser().resolve()
    if not epub.is_file():
        raise EpubTranslatorError(f"EPUB not found: {epub}")
    if workdir.exists() and any(workdir.iterdir()):
        raise EpubTranslatorError(f"Workdir already exists and is not empty: {workdir}")

    workdir.mkdir(parents=True, exist_ok=True)
    unpacked = workdir / "unpacked"
    safe_extract(epub, unpacked)
    shutil.copy2(epub, workdir / "source.epub")

    rootfile = container_rootfile(unpacked)
    _opf_path, opf_tree, opf = opf_root(unpacked, rootfile)
    items = manifest_items(opf)
    next_id = make_segment_id_factory()

    xhtml_items = [item for item in items if item["media_type"] == "application/xhtml+xml"]
    xhtml_by_id = {item["id"]: item for item in xhtml_items}
    ordered_xhtml: list[dict] = []
    seen_xhtml_ids: set[str] = set()
    for idref in spine_info(opf)["idrefs"]:
        item = xhtml_by_id.get(idref)
        if item:
            ordered_xhtml.append(item)
            seen_xhtml_ids.add(item["id"])
    for item in xhtml_items:
        if item["id"] not in seen_xhtml_ids:
            ordered_xhtml.append(item)
    documents = [
        {
            **item,
            "href": full_internal_path(rootfile, item["href"]),
            "opf_href": item["href"],
        }
        for item in ordered_xhtml
    ]
    all_images = [
        {
            **item,
            "href": full_internal_path(rootfile, item["href"]),
            "opf_href": item["href"],
        }
        for item in items
        if item["media_type"].startswith("image/")
    ]
    editable_images = [image for image in all_images if image["media_type"] in EDITABLE_IMAGE_MEDIA_TYPES]
    unsupported_images = [
        {
            "manifest_id": image["id"],
            "href": image["href"],
            "opf_href": image["opf_href"],
            "media_type": image["media_type"],
            "reason": "unsupported_image_media_type",
        }
        for image in all_images
        if image["media_type"] not in EDITABLE_IMAGE_MEDIA_TYPES
    ]

    segments = collect_opf_segments(opf_tree, rootfile, next_id)
    unit_parts: dict[str, list[dict]] = {}
    for document in documents:
        doc_path = safe_join(unpacked, document["href"])
        doc_segments, doc_unit_parts = collect_xhtml_segments(
            parse_xml(doc_path),
            document["href"],
            next_id,
        )
        segments.extend(doc_segments)
        unit_parts.update(doc_unit_parts)

    units = build_text_units(segments, unit_parts)
    chunk_count = chunk_segments(
        segments,
        units,
        workdir / "chunks",
    )
    (workdir / "translations").mkdir(parents=True, exist_ok=True)
    write_json(
        workdir / "segment-index.json",
        {"schema_version": TEXT_SCHEMA_VERSION, "units": units, "segments": segments},
    )

    image_jobs = []
    image_source_dir = workdir / "images" / "source"
    image_source_dir.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(editable_images, start=1):
        source_path = safe_join(unpacked, image["href"])
        suffix = IMAGE_SUFFIX_BY_MEDIA_TYPE.get(image["media_type"], Path(image["href"]).suffix or ".img")
        job_id = f"img{index:04d}"
        export_path = image_source_dir / f"{job_id}{suffix}"
        if source_path.is_file():
            shutil.copy2(source_path, export_path)
        image_jobs.append(
            {
                "id": job_id,
                "manifest_id": image["id"],
                "href": image["href"],
                "opf_href": image["opf_href"],
                "media_type": image["media_type"],
                "source_export": str(export_path.relative_to(workdir)),
                "status": "pending_review",
                "updated_at": utc_now(),
            }
        )

    run_manifest = {
        "schema_version": 2,
        "created_at": utc_now(),
        "source_epub": str(epub),
        "rootfile": rootfile,
        "text_status": "prepared",
        "text_schema_version": TEXT_SCHEMA_VERSION,
        "target_structure_status": "not_started",
        "segment_count": len(segments),
        "unit_count": len(units),
        "chunk_count": chunk_count,
        "documents": documents,
        "image_count": len(image_jobs),
        "unsupported_image_count": len(unsupported_images),
        "unsupported_images": unsupported_images,
        "output_epub": None,
    }
    write_json(workdir / "manifest.json", run_manifest)
    write_json(workdir / "image-jobs.json", {"schema_version": 2, "jobs": image_jobs})
    print(workdir)
    return 0


def read_segments(workdir: Path) -> list[dict]:
    index_path = workdir / "segment-index.json"
    if index_path.is_file():
        return read_json(index_path)["segments"]
    segments: list[dict] = []
    for chunk_path in sorted((workdir / "chunks").glob("chunk-*.json")):
        segments.extend(read_json(chunk_path).get("segments", []))
    return segments


def read_translation_map(translations_dir: Path) -> dict[str, str]:
    translations: dict[str, str] = {}
    for path in sorted(translations_dir.glob("chunk-*.json")):
        data = read_json(path)
        if data.get("schema_version") != TEXT_SCHEMA_VERSION:
            raise EpubTranslatorError(
                f"Translation file schema_version must be {TEXT_SCHEMA_VERSION}: {path}"
            )
        if "translations" not in data or not isinstance(data["translations"], list):
            raise EpubTranslatorError(f"Translation file must contain translations[]: {path}")
        rows = data["translations"]
        for row in rows:
            segment_id = row.get("id")
            if not segment_id or "translation" not in row:
                raise EpubTranslatorError(f"Translation row must contain id and translation: {path}")
            if segment_id in translations:
                raise EpubTranslatorError(f"Duplicate translation id: {segment_id}")
            translations[segment_id] = normalize_text(str(row["translation"]))
    return translations


def preserve_boundary_whitespace(source: str, translation: str) -> str:
    if not source.strip() or not translation.strip():
        return translation
    leading_count = len(source) - len(source.lstrip())
    trailing_count = len(source) - len(source.rstrip())
    leading = source[:leading_count]
    trailing = source[len(source) - trailing_count :] if trailing_count else ""
    return f"{leading}{translation.strip()}{trailing}"


def subtree_target_text(element: ET.Element) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        if node.text:
            parts.append(normalize_text(node.text))
        for child in list(node):
            child_name = local_name(child.tag)
            if child_name in STRUCTURE_MARKER_TAGS:
                parts.append(f"[{child_name}]")
            visit(child)
            if child.tail:
                parts.append(normalize_text(child.tail))

    visit(element)
    return "".join(parts).strip()


def element_attributes(element: ET.Element) -> dict[str, str]:
    return {local_name(name): value for name, value in sorted(element.attrib.items())}


def iter_subtree(element: ET.Element):
    yield element
    for child in list(element):
        yield from iter_subtree(child)


def preserved_references(elements: list[ET.Element]) -> list[dict]:
    refs: set[tuple[str, str]] = set()
    for element in elements:
        for node in iter_subtree(element):
            for name, value in node.attrib.items():
                attr = local_name(name)
                if attr in TARGET_STRUCTURE_PRESERVED_ATTRS and value:
                    refs.add((attr, value))
    return [{"attribute": attr, "value": value} for attr, value in sorted(refs)]


def serialize_xhtml(element: ET.Element) -> str:
    register_namespaces(XHTML_NS)
    return ET.tostring(element, encoding="unicode", short_empty_elements=True)


def target_structure_child_summary(child: ET.Element, path: list[int], index: int) -> dict:
    return {
        "index": index,
        "path": path_key(path),
        "tag": local_name(child.tag),
        "attributes": element_attributes(child),
        "text": subtree_target_text(child),
        "preserved_references": preserved_references([child]),
        "xhtml": serialize_xhtml(child),
    }


def target_structure_blocks(root: ET.Element) -> list[dict]:
    blocks: list[dict] = []

    def visit(element: ET.Element, path: list[int]) -> None:
        children = list(element)
        if children:
            blocks.append(
                {
                    "path": path_key(path),
                    "tag": local_name(element.tag),
                    "attributes": element_attributes(element),
                    "text": subtree_target_text(element),
                    "preserved_references": preserved_references([element]),
                    "children": [
                        target_structure_child_summary(child, [*path, index], index)
                        for index, child in enumerate(children)
                    ],
                }
            )
        for index, child in enumerate(children):
            visit(child, [*path, index])

    visit(root, [])
    return blocks


def export_target_structure(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    manifest = read_json(workdir / "manifest.json")
    if manifest.get("text_status") != "applied":
        raise EpubTranslatorError("Text translations must be applied before exporting target structure")
    unpacked = workdir / "unpacked"
    rootfile = manifest.get("rootfile") or container_rootfile(unpacked)
    documents = []
    for document in manifest.get("documents", []):
        href = document.get("href")
        if not isinstance(href, str):
            continue
        doc_path = resolve_layout_href(unpacked, rootfile, href)
        tree = parse_xml(doc_path)
        root = tree.getroot()
        documents.append(
            {
                "href": href,
                "root_tag": local_name(root.tag),
                "blocks": target_structure_blocks(root),
            }
        )
    write_json(
        output,
        {
            "schema_version": 1,
            "workdir": str(workdir),
            "documents": documents,
        },
    )
    print(output)
    return 0


def parse_xhtml_fragment(fragment: str) -> list[ET.Element]:
    if not isinstance(fragment, str):
        raise EpubTranslatorError("target-structure replacement xhtml must be a string")
    wrapper_source = f'<wrapper xmlns="{XHTML_NS}">{fragment}</wrapper>'
    try:
        wrapper = ET.fromstring(wrapper_source)
    except ET.ParseError as exc:
        raise EpubTranslatorError(f"Invalid target-structure XHTML fragment: {exc}") from exc
    if wrapper.text and wrapper.text.strip():
        raise EpubTranslatorError("target-structure XHTML fragment must contain element children, not root text")
    children = list(wrapper)
    for child in children:
        for node in iter_subtree(child):
            if local_name(node.tag) in SKIP_TEXT_TAGS:
                raise EpubTranslatorError("target-structure XHTML fragment must not contain script or style")
    return children


def apply_target_structure_replacements(root: ET.Element, replacements: list) -> list[str]:
    if not isinstance(replacements, list):
        raise EpubTranslatorError("target-structure replacements must be a list")
    parsed: list[tuple[list[int], int, int, str]] = []
    for replacement in replacements:
        if not isinstance(replacement, dict):
            raise EpubTranslatorError("target-structure replacement entries must be objects")
        if "parent_path" not in replacement:
            raise EpubTranslatorError("target-structure replacement requires parent_path")
        parent_path = parse_layout_path(replacement["parent_path"])
        start = replacement.get("start")
        end = replacement.get("end")
        fragment = replacement.get("xhtml")
        if not isinstance(start, int) or not isinstance(end, int):
            raise EpubTranslatorError("target-structure start and end must be integers")
        if start < 0 or end < start:
            raise EpubTranslatorError("target-structure replacement has invalid start/end range")
        if not isinstance(fragment, str):
            raise EpubTranslatorError("target-structure replacement requires string xhtml")
        parsed.append((parent_path, start, end, fragment))

    changes: list[str] = []
    for parent_path, start, end, fragment in sorted(parsed, key=lambda item: (item[0], item[1]), reverse=True):
        parent = element_at_path(root, parent_path)
        children = list(parent)
        if end > len(children):
            raise EpubTranslatorError(
                f"target-structure range exceeds child count at {path_key(parent_path)}: {start}:{end}"
            )
        original_children = children[start:end]
        new_children = parse_xhtml_fragment(fragment)
        required_refs = {
            (ref["attribute"], ref["value"])
            for ref in preserved_references(original_children)
        }
        new_refs = {
            (ref["attribute"], ref["value"])
            for ref in preserved_references(new_children)
        }
        missing_refs = sorted(required_refs - new_refs)
        if missing_refs:
            missing = ", ".join(f"{attr}={value}" for attr, value in missing_refs[:8])
            raise EpubTranslatorError(f"target-structure replacement drops preserved references: {missing}")
        parent[start:end] = new_children
        changes.append(f"{path_key(parent_path)}[{start}:{end}]")
    return changes


def apply_target_structure(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    plan_path = Path(args.plan).expanduser().resolve()
    if not plan_path.is_file():
        raise EpubTranslatorError(f"Target structure plan not found: {plan_path}")
    plan = read_json(plan_path)
    if plan.get("schema_version") != 1:
        raise EpubTranslatorError("target-structure-plan schema_version must be 1")
    documents = plan.get("documents", [])
    if not isinstance(documents, list):
        raise EpubTranslatorError("target-structure-plan documents must be a list")
    unpacked = workdir / "unpacked"
    if not unpacked.is_dir():
        raise EpubTranslatorError(f"Unpacked EPUB not found: {unpacked}")
    manifest_path = workdir / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("text_status") != "applied":
        raise EpubTranslatorError("Text translations must be applied before target structure")
    rootfile = manifest.get("rootfile") or container_rootfile(unpacked)

    changes: list[str] = []
    for document in documents:
        if not isinstance(document, dict):
            raise EpubTranslatorError("target-structure documents entries must be objects")
        href = document.get("href")
        if not isinstance(href, str):
            raise EpubTranslatorError("target-structure document requires string href")
        doc_path = resolve_layout_href(unpacked, rootfile, href)
        tree = parse_xml(doc_path)
        root = tree.getroot()
        document_changes = apply_target_structure_replacements(root, document.get("replacements", []))
        if document_changes:
            write_xml(doc_path, tree, XHTML_NS)
            changes.extend(f"xhtml:{href}:{change}" for change in document_changes)

    manifest["target_structure_status"] = "applied"
    manifest["target_structure_applied_at"] = utc_now()
    manifest["target_structure_plan"] = str(plan_path)
    manifest["target_structure_change_count"] = len(changes)
    write_json(manifest_path, manifest)
    summary = {
        "target_structure_status": "applied",
        "change_count": len(changes),
        "changes": changes,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def apply_segments_to_tree(tree: ET.ElementTree, segments: list[dict], translations: dict[str, str]) -> None:
    root = tree.getroot()
    for segment in segments:
        translation = translations[segment["id"]]
        element = element_at_path(root, segment["path"])
        kind = segment["kind"]
        if kind == "xhtml_text":
            element.text = preserve_boundary_whitespace(segment["source"], translation)
        elif kind == "xhtml_tail":
            child_index = segment.get("child_index")
            if child_index is None:
                raise EpubTranslatorError(f"xhtml_tail segment missing child_index: {segment['id']}")
            children = list(element)
            if child_index >= len(children):
                raise EpubTranslatorError(f"XML child index no longer exists: {segment['path']}[{child_index}]")
            children[child_index].tail = preserve_boundary_whitespace(segment["source"], translation)
        elif kind == "opf_metadata":
            element.text = translation
        elif kind == "xhtml_attribute":
            element.set(segment["attribute"], translation)
        else:
            raise EpubTranslatorError(f"Unsupported segment kind: {kind}")


def apply_text(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    translations_dir = Path(args.translations).expanduser().resolve()
    manifest = read_json(workdir / "manifest.json")
    unpacked = workdir / "unpacked"
    rootfile = manifest["rootfile"]
    segments = read_segments(workdir)
    translations = read_translation_map(translations_dir)
    missing = [segment["id"] for segment in segments if segment["id"] not in translations]
    if missing:
        raise EpubTranslatorError(f"Missing translations for {len(missing)} segments: {', '.join(missing[:8])}")
    known_ids = {segment["id"] for segment in segments}
    unknown = [segment_id for segment_id in translations if segment_id not in known_ids]
    if unknown:
        raise EpubTranslatorError(f"Unknown translation ids: {', '.join(unknown[:8])}")

    opf_segments = [segment for segment in segments if segment["kind"] == "opf_metadata"]
    if opf_segments:
        opf_path, opf_tree, _opf = opf_root(unpacked, rootfile)
        apply_segments_to_tree(opf_tree, opf_segments, translations)
        write_xml(opf_path, opf_tree, OPF_NS)

    by_doc: dict[str, list[dict]] = {}
    for segment in segments:
        if segment["kind"].startswith("xhtml_"):
            by_doc.setdefault(segment["href"], []).append(segment)

    for href, doc_segments in sorted(by_doc.items()):
        doc_path = safe_join(unpacked, href)
        tree = parse_xml(doc_path)
        apply_segments_to_tree(tree, doc_segments, translations)
        write_xml(doc_path, tree, XHTML_NS)

    manifest["text_status"] = "applied"
    manifest["text_applied_at"] = utc_now()
    manifest["target_structure_status"] = "pending"
    write_json(workdir / "manifest.json", manifest)
    print(f"Applied {len(segments)} translated text segments")
    return 0


def copy_image_verbatim(source: Path, destination: Path, media_type: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if media_type not in EDITABLE_IMAGE_MEDIA_TYPES:
        raise EpubTranslatorError(f"Unsupported editable image media type: {media_type}")
    shutil.copy2(source, destination)
    return "copied-verbatim"


def record_image(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    jobs_path = workdir / "image-jobs.json"
    jobs_data = read_json(jobs_path)
    jobs = jobs_data["jobs"]
    job = next((item for item in jobs if item["id"] == args.image_id), None)
    if job is None:
        raise EpubTranslatorError(f"Unknown image id: {args.image_id}")

    actions = [bool(args.replacement), bool(args.skip_no_text)]
    if sum(actions) != 1:
        raise EpubTranslatorError("Choose exactly one of --replacement or --skip-no-text")

    if args.skip_no_text:
        job["status"] = "skipped_no_text"
    else:
        replacement = Path(args.replacement).expanduser().resolve()
        if not replacement.is_file():
            raise EpubTranslatorError(f"Replacement image not found: {replacement}")
        destination = safe_join(workdir / "unpacked", job["href"])
        mode = copy_image_verbatim(replacement, destination, job["media_type"])
        job["status"] = "edited"
        job["replacement_source"] = str(replacement)
        job["replacement_mode"] = mode
    job["updated_at"] = utc_now()
    write_json(jobs_path, jobs_data)
    print(f"{job['id']} {job['status']}")
    return 0


def parse_layout_path(value) -> list[int]:
    if value in (None, "", "."):
        return []
    if isinstance(value, list):
        path = value
    elif isinstance(value, str):
        path = value.split("/")
    else:
        raise EpubTranslatorError(f"Invalid XHTML layout path: {value!r}")
    result: list[int] = []
    for part in path:
        if part in ("", "."):
            continue
        try:
            index = int(part)
        except (TypeError, ValueError) as exc:
            raise EpubTranslatorError(f"Invalid XHTML layout path component: {part!r}") from exc
        if index < 0:
            raise EpubTranslatorError(f"Invalid negative XHTML layout path component: {part!r}")
        result.append(index)
    return result


def resolve_layout_href(unpacked: Path, rootfile: str, href: str) -> Path:
    if not href:
        raise EpubTranslatorError("Layout href must not be empty")
    direct = safe_join(unpacked, href)
    if direct.exists():
        return direct
    opf_relative = safe_join(unpacked, full_internal_path(rootfile, href))
    if opf_relative.exists():
        return opf_relative
    raise EpubTranslatorError(f"Layout href not found in unpacked EPUB: {href}")


def css_hrefs(unpacked: Path, rootfile: str) -> list[str]:
    _opf_path, _opf_tree, opf = opf_root(unpacked, rootfile)
    return [
        full_internal_path(rootfile, item["href"])
        for item in manifest_items(opf)
        if item["media_type"] == "text/css"
    ]


def replace_css_declarations(css: str, replacements: dict) -> str:
    for property_name, value in replacements.items():
        if not isinstance(property_name, str) or not isinstance(value, str):
            raise EpubTranslatorError("CSS replace_declarations must map strings to strings")
        pattern = re.compile(
            rf"(?i)(?P<prefix>(^|[;{{])\s*{re.escape(property_name)}\s*:\s*)[^;}}]+"
        )
        css = pattern.sub(lambda match: f"{match.group('prefix')}{value}", css)
    return css


def remove_css_declarations(css: str, property_names: list) -> str:
    for property_name in property_names:
        if not isinstance(property_name, str):
            raise EpubTranslatorError("CSS remove_declarations must contain strings")
        pattern = re.compile(
            rf"(?i)(?P<prefix>^|[;{{])\s*{re.escape(property_name)}\s*:[^;}}]+;?"
        )
        css = pattern.sub(lambda match: match.group("prefix"), css)
    return css


def apply_opf_layout(unpacked: Path, rootfile: str, opf_plan: dict | None) -> list[str]:
    if not opf_plan:
        return []
    if not isinstance(opf_plan, dict):
        raise EpubTranslatorError("layout-plan opf must be an object")
    opf_path, opf_tree, opf = opf_root(unpacked, rootfile)
    spine = opf.find(f"{{{OPF_NS}}}spine")
    if spine is None:
        raise EpubTranslatorError("OPF spine missing")
    changes: list[str] = []
    if "page_progression_direction" in opf_plan:
        value = opf_plan["page_progression_direction"]
        if value is None:
            if "page-progression-direction" in spine.attrib:
                spine.attrib.pop("page-progression-direction", None)
                changes.append("opf.page-progression-direction removed")
        elif value in {"ltr", "rtl"}:
            spine.set("page-progression-direction", value)
            changes.append(f"opf.page-progression-direction={value}")
        else:
            raise EpubTranslatorError("opf.page_progression_direction must be ltr, rtl, or null")
    if changes:
        write_xml(opf_path, opf_tree, OPF_NS)
    return changes


def apply_css_layout(unpacked: Path, rootfile: str, css_plan: list | None) -> list[str]:
    if not css_plan:
        return []
    if not isinstance(css_plan, list):
        raise EpubTranslatorError("layout-plan css must be a list")
    changes: list[str] = []
    for entry in css_plan:
        if not isinstance(entry, dict):
            raise EpubTranslatorError("layout-plan css entries must be objects")
        href = entry.get("href")
        if not isinstance(href, str):
            raise EpubTranslatorError("layout-plan css entry requires string href")
        targets = css_hrefs(unpacked, rootfile) if href == "*" else [href]
        if not targets:
            raise EpubTranslatorError("layout-plan css wildcard matched no CSS files")
        replacements = entry.get("replace_declarations", {})
        removals = entry.get("remove_declarations", [])
        append = entry.get("append", "")
        if not isinstance(replacements, dict):
            raise EpubTranslatorError("layout-plan css replace_declarations must be an object")
        if not isinstance(removals, list):
            raise EpubTranslatorError("layout-plan css remove_declarations must be a list")
        if not isinstance(append, str):
            raise EpubTranslatorError("layout-plan css append must be a string")
        for target in targets:
            css_path = resolve_layout_href(unpacked, rootfile, target)
            before = css_path.read_text(encoding="utf-8")
            after = remove_css_declarations(before, removals)
            after = replace_css_declarations(after, replacements)
            if append:
                after = after.rstrip() + "\n\n" + append.rstrip() + "\n"
            if after != before:
                css_path.write_text(after, encoding="utf-8")
                changes.append(f"css:{target}")
    return changes


def apply_xhtml_layout(unpacked: Path, rootfile: str, xhtml_plan: list | None) -> list[str]:
    if not xhtml_plan:
        return []
    if not isinstance(xhtml_plan, list):
        raise EpubTranslatorError("layout-plan xhtml must be a list")
    changes: list[str] = []
    for entry in xhtml_plan:
        if not isinstance(entry, dict):
            raise EpubTranslatorError("layout-plan xhtml entries must be objects")
        href = entry.get("href")
        if not isinstance(href, str):
            raise EpubTranslatorError("layout-plan xhtml entry requires string href")
        xhtml_path = resolve_layout_href(unpacked, rootfile, href)
        tree = parse_xml(xhtml_path)
        root = tree.getroot()
        changed = False
        for update in entry.get("set_attributes", []):
            if not isinstance(update, dict):
                raise EpubTranslatorError("xhtml set_attributes entries must be objects")
            attributes = update.get("attributes", {})
            if not isinstance(attributes, dict):
                raise EpubTranslatorError("xhtml set_attributes.attributes must be an object")
            element = element_at_path(root, parse_layout_path(update.get("path", ".")))
            for name, value in attributes.items():
                if not isinstance(name, str):
                    raise EpubTranslatorError("xhtml attribute names must be strings")
                if value is None:
                    if name in element.attrib:
                        element.attrib.pop(name, None)
                        changed = True
                else:
                    element.set(name, str(value))
                    changed = True
        for update in entry.get("remove_attributes", []):
            if not isinstance(update, dict):
                raise EpubTranslatorError("xhtml remove_attributes entries must be objects")
            names = update.get("names", [])
            if not isinstance(names, list):
                raise EpubTranslatorError("xhtml remove_attributes.names must be a list")
            element = element_at_path(root, parse_layout_path(update.get("path", ".")))
            for name in names:
                if not isinstance(name, str):
                    raise EpubTranslatorError("xhtml remove_attributes.names must contain strings")
                if name in element.attrib:
                    element.attrib.pop(name, None)
                    changed = True
        if changed:
            write_xml(xhtml_path, tree, XHTML_NS)
            changes.append(f"xhtml:{href}")
    return changes


def apply_layout(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    plan_path = Path(args.plan).expanduser().resolve()
    if not plan_path.is_file():
        raise EpubTranslatorError(f"Layout plan not found: {plan_path}")
    plan = read_json(plan_path)
    if plan.get("schema_version") != 1:
        raise EpubTranslatorError("layout-plan schema_version must be 1")
    unpacked = workdir / "unpacked"
    if not unpacked.is_dir():
        raise EpubTranslatorError(f"Unpacked EPUB not found: {unpacked}")
    manifest_path = workdir / "manifest.json"
    manifest = read_json(manifest_path)
    rootfile = manifest.get("rootfile") or container_rootfile(unpacked)
    changes: list[str] = []
    changes.extend(apply_opf_layout(unpacked, rootfile, plan.get("opf")))
    changes.extend(apply_css_layout(unpacked, rootfile, plan.get("css")))
    changes.extend(apply_xhtml_layout(unpacked, rootfile, plan.get("xhtml")))
    manifest["layout_status"] = "applied"
    manifest["layout_applied_at"] = utc_now()
    manifest["layout_plan"] = str(plan_path)
    manifest["layout_change_count"] = len(changes)
    write_json(manifest_path, manifest)
    summary = {"layout_status": "applied", "change_count": len(changes), "changes": changes}
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def package_epub(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    unpacked = workdir / "unpacked"
    output = Path(args.output).expanduser().resolve()
    manifest_path = workdir / "manifest.json"
    manifest = read_json(manifest_path)
    source_epub = Path(manifest["source_epub"]).expanduser().resolve()
    run_source = (workdir / "source.epub").resolve()
    if output == source_epub or output == run_source:
        raise EpubTranslatorError("Refusing to overwrite the source EPUB")
    mimetype = unpacked / "mimetype"
    if not mimetype.is_file():
        raise EpubTranslatorError("Unpacked EPUB has no mimetype file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(unpacked.rglob("*")):
            if not path.is_file() or path == mimetype:
                continue
            archive.write(
                path,
                path.relative_to(unpacked).as_posix(),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    manifest["output_epub"] = str(output)
    manifest["packaged_at"] = utc_now()
    write_json(manifest_path, manifest)
    print(output)
    return 0


def validate_epub_archive(output: Path) -> list[str]:
    errors: list[str] = []
    if not output.is_file():
        return [f"Output EPUB not found: {output}"]
    try:
        with zipfile.ZipFile(output) as archive:
            infos = archive.infolist()
            if not infos or infos[0].filename != "mimetype":
                errors.append("mimetype must be the first ZIP entry")
            elif infos[0].compress_type != zipfile.ZIP_STORED:
                errors.append("mimetype must be stored without compression")
            try:
                if archive.read("mimetype") != b"application/epub+zip":
                    errors.append("mimetype content must be application/epub+zip")
            except KeyError:
                errors.append("mimetype file missing")
            try:
                container = ET.parse(archive.open("META-INF/container.xml"))
                rootfile = container.getroot().find(f".//{{{CONTAINER_NS}}}rootfile")
                if rootfile is None or not rootfile.get("full-path"):
                    errors.append("container.xml rootfile missing")
                    return errors
                rootfile_path = rootfile.get("full-path", "")
                opf_tree = ET.parse(archive.open(rootfile_path))
            except (KeyError, ET.ParseError) as exc:
                errors.append(f"Could not parse EPUB container/OPF: {exc}")
                return errors
            root = opf_tree.getroot()
            items = manifest_items(root)
            ids = {item["id"] for item in items}
            root_dir = posixpath.dirname(rootfile_path)
            names = set(archive.namelist())
            for item in items:
                href = posixpath.normpath(posixpath.join(root_dir, item["href"]))
                if href not in names:
                    errors.append(f"Manifest href missing from archive: {href}")
            for idref in spine_info(root)["idrefs"]:
                if idref not in ids:
                    errors.append(f"Spine idref has no manifest item: {idref}")
    except zipfile.BadZipFile as exc:
        errors.append(f"Invalid ZIP archive: {exc}")
    return errors


def validate_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    errors: list[str] = []
    manifest = read_json(workdir / "manifest.json")
    jobs = read_json(workdir / "image-jobs.json")["jobs"]

    if manifest.get("text_status") != "applied":
        errors.append("Text translations have not been applied")
    if manifest.get("target_structure_status") != "applied":
        errors.append("Target structure has not been applied")
    if not manifest.get("packaged_at") or not manifest.get("output_epub"):
        errors.append("EPUB has not been packaged by this run")
    else:
        packaged_output = Path(manifest["output_epub"]).expanduser().resolve()
        if packaged_output != output:
            errors.append(f"Validation output does not match packaged output: {packaged_output}")
        elif output.exists():
            packaged_at = dt.datetime.fromisoformat(manifest["packaged_at"])
            output_mtime = dt.datetime.fromtimestamp(output.stat().st_mtime, dt.UTC)
            if output_mtime < packaged_at - dt.timedelta(seconds=1):
                errors.append("Output EPUB appears older than the recorded package step")
    resolved_image_statuses = {"skipped_no_text", "edited"}
    unresolved = [job for job in jobs if job.get("status") not in resolved_image_statuses]
    if unresolved:
        errors.append(
            "Image jobs still unreviewed: "
            + ", ".join(f"{job['id']}={job.get('status')}" for job in unresolved[:10])
        )
    errors.extend(validate_epub_archive(output))

    summary = {
        "ok": not errors,
        "errors": errors,
        "segment_count": manifest.get("segment_count", 0),
        "image_jobs": {
            status: sum(1 for job in jobs if job.get("status") == status)
            for status in sorted({job.get("status", "unknown") for job in jobs})
        },
        "unsupported_images": manifest.get("unsupported_image_count", 0),
        "output": str(output),
    }
    write_json(workdir / "validation.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "EPUB mechanics helper: inspect, prepare safe text slots, apply completed "
            "translations, export and apply explicit target-structure plans, apply "
            "layout plans, record finished image results, package, and validate."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect EPUB structure")
    inspect_parser.add_argument("--epub", required=True)
    inspect_parser.add_argument("--json", action="store_true", help="Print JSON output")
    inspect_parser.set_defaults(func=lambda args: print_inspect(args))

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Unpack an EPUB and extract safe text slots and image jobs",
    )
    prepare_parser.add_argument("--epub", required=True)
    prepare_parser.add_argument("--workdir", required=True)
    prepare_parser.set_defaults(func=prepare_run)

    apply_parser = subparsers.add_parser(
        "apply-text",
        help="Apply completed chunk JSON text to the unpacked EPUB",
    )
    apply_parser.add_argument("--workdir", required=True)
    apply_parser.add_argument("--translations", required=True)
    apply_parser.set_defaults(func=apply_text)

    export_structure_parser = subparsers.add_parser(
        "export-target-structure",
        help="Export translated XHTML structure blocks for Codex-authored target-structure planning",
    )
    export_structure_parser.add_argument("--workdir", required=True)
    export_structure_parser.add_argument("--output", required=True)
    export_structure_parser.set_defaults(func=export_target_structure)

    target_structure_parser = subparsers.add_parser(
        "apply-target-structure",
        help="Apply an explicit Codex-authored target-structure XHTML plan",
    )
    target_structure_parser.add_argument("--workdir", required=True)
    target_structure_parser.add_argument("--plan", required=True)
    target_structure_parser.set_defaults(func=apply_target_structure)

    layout_parser = subparsers.add_parser(
        "apply-layout",
        help="Apply an explicit mechanical target-edition layout plan",
    )
    layout_parser.add_argument("--workdir", required=True)
    layout_parser.add_argument("--plan", required=True)
    layout_parser.set_defaults(func=apply_layout)

    image_parser = subparsers.add_parser(
        "record-image",
        help="Record no-text or finished replacement image results",
    )
    image_parser.add_argument("--workdir", required=True)
    image_parser.add_argument("--image-id", required=True)
    image_parser.add_argument("--replacement", help="Finished replacement image to embed")
    image_parser.add_argument(
        "--skip-no-text",
        action="store_true",
        help="Mark image as having no text to replace",
    )
    image_parser.set_defaults(func=record_image)

    package_parser = subparsers.add_parser(
        "package",
        help="Package the EPUB run into a new EPUB",
    )
    package_parser.add_argument("--workdir", required=True)
    package_parser.add_argument("--output", required=True)
    package_parser.set_defaults(func=package_epub)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an EPUB translation run mechanically",
    )
    validate_parser.add_argument("--workdir", required=True)
    validate_parser.add_argument("--output", required=True)
    validate_parser.set_defaults(func=validate_run)
    return parser


def print_inspect(args: argparse.Namespace) -> int:
    data = inspect_epub(Path(args.epub).expanduser().resolve())
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"EPUB: {data['epub']}")
        print(f"Rootfile: {data['rootfile']}")
        print(f"Language: {data['language']}")
        print(f"Title: {data['title']}")
        print(f"Counts: {data['counts']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except EpubTranslatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
