"""Replay v2 slot allocation at exact DOM locations, without rewriting a run.

This is deliberately version-specific: v2 omitted container text/tails and ruby
note tails. Those omissions must not shift ownership of already translated IDs.
"""
from __future__ import annotations

import re
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET

from epub_common import DC_NS, EpubTranslatorError, archive_path, attr_value, local_name, normalize_spaces, package_data, parse_xml, safe_join

TRANSPARENT = {"body", "div", "section", "article", "main", "header", "footer", "center", "details", "summary"}
SEPARATOR_RE = re.compile(r"^[\s*#✦✧◆◇○●☆★※―─\-−·•․…~⁂❖※]+$")


def dom_locations(root: ET.Element) -> dict[int, str]:
    result = {}
    def walk(element, path):
        result[id(element)] = path
        for index, child in enumerate(element):
            walk(child, f"{path}/{index}")
    walk(root, "0")
    return result


def source_slots(unpacked: Path, rootfile: str, spine_hrefs: list[str]) -> dict:
    slots = {}
    counter = 0
    block_counter = 0
    for source_href in spine_hrefs:
        try:
            root = parse_xml(safe_join(unpacked, archive_path(rootfile, source_href))).getroot()
        except EpubTranslatorError:
            continue  # The new reader retains this source error and blocks build.
        href = posixpath.relpath(archive_path(rootfile, source_href), posixpath.dirname(rootfile) or ".")
        locations = dom_locations(root)
        body = next((el for el in root.iter() if local_name(el.tag) == "body"), None)
        if body is None:
            continue

        def capture(text, kind, element, position, owned):
            nonlocal counter
            if text and text.strip():
                counter += 1
                slot_id = f"t{counter:06d}"
                slots[slot_id] = {"source": normalize_spaces(text), "kind": kind, "href": href,
                                  "location": f"{href}:{locations[id(element)]}:{position}"}
                owned.append(slot_id)

        def attrs(element, owned):
            for name in ("title", "aria-label"):
                capture(attr_value(element, name), "attribute", element, "@" + name, owned)

        def image(element, owned):
            capture(attr_value(element, "alt"), "alt", element, "@alt", owned)
            attrs(element, owned)

        def inline(element, owned):
            capture(element.text, "text", element, "text", owned)
            for child in element:
                name = local_name(child.tag)
                if name == "img":
                    image(child, owned)
                elif name == "ruby":
                    capture(child.text, "text", child, "text", owned)
                    for ruby_child in child:
                        if local_name(ruby_child.tag) not in ("rt", "rp"):
                            inline(ruby_child, owned)
                            capture(ruby_child.tail, "text", ruby_child, "tail", owned)
                elif name not in ("script", "style", "rt", "rp", "br"):
                    inline(child, owned)
                capture(child.tail, "text", child, "tail", owned)

        def own(ids, block_id):
            for slot_id in ids:
                slots[slot_id]["block_id"] = block_id

        def visit(element):
            nonlocal block_counter
            name = local_name(element.tag)
            if name in ("script", "style", "nav"):
                return False
            owned = []
            container = name in TRANSPARENT | {"ul", "ol", "table", "tr", "figure"}
            if name in ("blockquote", "aside"):
                allowed = {"p", "ul", "ol", "table"} | {f"h{i}" for i in range(1, 7)}
                if name == "blockquote":
                    allowed.add("blockquote")
                container = any(local_name(child.tag) in allowed for child in element)
            if name not in TRANSPARENT | {"ul", "ol", "table", "tr", "figure", "blockquote", "aside", "p", "li", "td", "th", "figcaption", "img", "hr"} | {f"h{i}" for i in range(1, 7)}:
                container = not (element.text and element.text.strip() or any((child.text and child.text.strip()) or (child.tail and child.tail.strip()) for child in element.iter() if child is not element))
            if container:
                attrs(element, owned)
                block_counter += 1
                own(owned, f"b{block_counter:06d}")
                children = [visit(child) for child in element if local_name(child.tag) not in ("script", "style")]
                return bool(any(children) or attr_value(element, "id") or owned)
            if name == "img":
                image(element, owned)
                present = bool(owned or attr_value(element, "id"))
            else:
                separator = name == "hr" or (name == "p" and SEPARATOR_RE.fullmatch(normalize_spaces("".join(element.itertext()))))
                if not separator:
                    inline(element, owned)
                attrs(element, owned)
                present = bool(owned or attr_value(element, "id") or separator or any(local_name(child.tag) in ("br", "img") or attr_value(child, "id") for child in element.iter() if child is not element))
            if present:
                block_counter += 1
                own(owned, f"b{block_counter:06d}")
            return present

        for child in body:
            visit(child)
    _, opf, _, _ = package_data(unpacked)
    metadata_counter = 0
    for field in ("title", "creator", "publisher", "description", "subject"):
        occurrence = 0
        for element in opf.findall(f".//{{{DC_NS}}}{field}"):
            if element.text and element.text.strip():
                metadata_counter += 1
                slots[f"m{metadata_counter:06d}"] = {"source": normalize_spaces(element.text), "kind": "metadata", "href": rootfile,
                                                       "location": f"{rootfile}:metadata:{field}:{occurrence}"}
                occurrence += 1
    return slots
