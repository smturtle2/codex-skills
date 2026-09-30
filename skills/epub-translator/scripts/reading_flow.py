"""Ordered normalized reading flow, protected inline units, and versioned readers."""
from __future__ import annotations

import copy
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from epub_common import (CSS_HREF, DC_NS, EpubTranslatorError, FLOW_SCHEMA_VERSION, OPF_NS, TEXT_SCHEMA_VERSION, X,
                         archive_path, attr_value, canonical_archive_path, local_name, normalize_spaces, package_data,
                         parse_xml, read_json, safe_join, sha256_bytes, uri_path, utc_now, write_json, write_json_atomic)
from legacy_slots import dom_locations, source_slots

DEFAULT_MAX_CHARS = 5000
DEFAULT_SOFT_MIN = 1500
MARK_RE = re.compile(r"⟦(/?)(m\d+)(/?)⟧")
BLOCK_TAGS = {"body", "div", "section", "article", "main", "header", "footer", "center", "details", "summary", "p", "blockquote", "aside", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "figure", "figcaption", "hr"} | {f"h{i}" for i in range(1, 7)}
INLINE_TAGS = {"em": "em", "i": "em", "cite": "em", "dfn": "em", "var": "em", "strong": "strong", "b": "strong", "sub": "sub", "sup": "sup", "a": "a", "q": "q", "code": "code", "abbr": "abbr"}
OPAQUE_TAGS = {"svg", "math", "audio", "video", "object", "iframe", "embed"}
CONTAINER_KINDS = {"ul": "list", "ol": "list", "tr": "table_row", "td": "table_cell", "th": "table_cell", "li": "list_item", "figure": "figure", "table": "table", "blockquote": "blockquote", "aside": "aside", "thead": "thead", "tbody": "tbody", "tfoot": "tfoot"}
METADATA_FIELDS = ("title", "creator", "publisher", "description", "subject")


class FlowBuilder:
    def __init__(self) -> None:
        self.blocks: list[dict] = []
        self.atoms: list[dict] = []
        self.units = 0
        self.markers = 0
        self.locations: dict[int, str] = {}
        self.positions: dict[tuple[int, str], str] = {}
        self.stats = {"rubies_collapsed": 0, "ruby_elements": 0, "wrappers_flattened": 0, "ideographic_spaces_normalized": 0, "unsupported_inline_media": 0}

    def atom(self, source: str, kind: str, href: str, **extra) -> str:
        atom_id = f"a{len(self.atoms) + 1:06d}"
        self.atoms.append({"id": atom_id, "source": normalize_spaces(source), "kind": kind, "href": href, **extra})
        return atom_id

    def location(self, element: ET.Element, position: str, href: str) -> str:
        return self.positions.get((id(element), position), f"{href}:{self.locations.get(id(element), 'mixed')}:{position}")

    def attrs(self, el: ET.Element, href: str) -> list[dict]:
        slots = []
        for name in ("title", "aria-label"):
            value = attr_value(el, name)
            if value and value.strip():
                slots.append({"attr": name, "id": self.atom(value, "attribute", href, attr=name, location=self.location(el, "@" + name, href)), "source": normalize_spaces(value)})
        return slots

    def semantic_attrs(self, el: ET.Element) -> dict:
        return {key: value for key, value in el.attrib.items() if local_name(key) in ("id", "dir", "lang", "role")}

    def image(self, el: ET.Element, href: str) -> dict:
        alt = attr_value(el, "alt") or ""
        data = {"src": attr_value(el, "src") or "", "alt_source": alt,
                "anchors": [attr_value(el, "id")] if attr_value(el, "id") else []}
        if alt.strip():
            data["alt_id"] = self.atom(alt, "alt", href, location=self.location(el, "@alt", href))
        data["attr_slots"] = self.attrs(el, href)
        return data

    def unit(self, el: ET.Element, href: str) -> dict:
        parts: list[dict] = []
        marks: dict[str, dict] = {}

        def mark(data: dict, opening: bool = False) -> str:
            self.markers += 1
            key = f"m{self.markers:06d}"
            marks[key] = data
            parts.append({"marker": f"⟦{key}⟧" if opening else f"⟦{key}/⟧"})
            return key

        def emit(text: str | None, location: str) -> None:
            if not text:
                return
            self.stats["ideographic_spaces_normalized"] += text.count("\u3000")
            text = re.sub(r"[ \t\r\n\f\v]+", " ", text.replace("\u3000", " "))
            grouped = "⟦" in text or "⟧" in text
            atom_id = self.atom(text, "text", href, location=location) if text.strip() else None
            if grouped and atom_id:
                parts.append({"atom_id": atom_id, "legacy_text": text})
            start = len(parts)
            for fragment in re.split(r"([⟦⟧])", text):
                if fragment in ("⟦", "⟧"):
                    mark({"kind": "literal", "value": fragment})
                elif fragment:
                    part = {"text": fragment}
                    if fragment.strip() and not grouped:
                        part["atom_id"] = atom_id
                    parts.append(part)
            if grouped:
                for part in parts[start:]:
                    part["legacy_skip"] = True

        def walk(parent: ET.Element) -> None:
            emit(parent.text, self.location(parent, "text", href))
            for child in parent:
                tag = local_name(child.tag)
                if tag in ("script", "style", "rt", "rp"):
                    if tag in ("rt", "rp"):
                        self.stats["rubies_collapsed"] += 1
                elif tag == "ruby":
                    self.stats["ruby_elements"] += 1
                    walk(child)
                elif tag == "img":
                    mark({"kind": "image", **self.image(child, href)})
                elif tag == "br":
                    mark({"kind": "br", "attrs": self.semantic_attrs(child), "attr_slots": self.attrs(child, href)})
                elif tag in OPAQUE_TAGS:
                    opaque = copy.deepcopy(child)
                    opaque.tail = None
                    mark({"kind": "opaque", "source_xml": ET.tostring(opaque, encoding="unicode")})
                    self.stats["unsupported_inline_media"] += 1
                elif tag in INLINE_TAGS:
                    attrs = self.semantic_attrs(child)
                    if tag == "a" and attr_value(child, "href") is not None:
                        attrs["href"] = attr_value(child, "href")
                    if attr_value(child, "id"):
                        attrs["id"] = attr_value(child, "id")
                    key = mark({"kind": "inline", "tag": INLINE_TAGS[tag], "attrs": attrs, "attr_slots": self.attrs(child, href)}, True)
                    walk(child)
                    parts.append({"marker": f"⟦/{key}⟧"})
                else:
                    attrs = self.semantic_attrs(child)
                    slots = self.attrs(child, href)
                    key = mark({"kind": "inline", "tag": "span", "attrs": attrs, "attr_slots": slots}, True) if attrs or slots else None
                    if attr_value(child, "class") or attr_value(child, "style"):
                        self.stats["wrappers_flattened"] += 1
                    walk(child)
                    if key:
                        parts.append({"marker": f"⟦/{key}⟧"})
                emit(child.tail, self.location(child, "tail", href))

        walk(el)
        source = "".join(part.get("text", part.get("marker", "")) for part in parts).strip()
        unit_id = None
        if any(part.get("atom_id") for part in parts):
            self.units += 1
            unit_id = f"u{self.units:06d}"
        return {"id": unit_id, "source": source, "parts": parts, "markers": marks}

    def node(self, el: ET.Element, href: str) -> str | None:
        tag = local_name(el.tag)
        if tag in ("script", "style", "nav"):
            return None
        node = {"id": f"b{len(self.blocks) + 1:06d}", "kind": CONTAINER_KINDS.get(tag, "section"), "href": href,
                "anchors": [attr_value(el, "id")] if attr_value(el, "id") else [], "content": [], "attr_slots": []}
        self.blocks.append(node)
        if tag == "img":
            node.update(kind="image", image=self.image(el, href))
            return node["id"]
        if tag in OPAQUE_TAGS:
            opaque = copy.deepcopy(el)
            opaque.tail = None
            node.update(kind="opaque", source_xml=ET.tostring(opaque, encoding="unicode"))
            self.stats["unsupported_inline_media"] += 1
            return node["id"]
        if tag == "hr":
            node["kind"] = "separator"
        elif tag.startswith("h") and tag[1:] in tuple(str(i) for i in range(1, 7)):
            node.update(kind="heading", level=int(tag[1:]), unit=self.unit(el, href))
        elif tag in ("p", "figcaption"):
            node.update(kind="paragraph" if tag == "p" else "figcaption", unit=self.unit(el, href))
        elif tag in ("li", "td", "th", "blockquote", "aside") and not any(local_name(c.tag) in BLOCK_TAGS for c in el):
            node["unit"] = self.unit(el, href)
        else:
            node["attr_slots"] = self.attrs(el, href)
            buffer = ET.Element("p")

            def append_text(text: str | None, source: ET.Element, position: str) -> None:
                if text:
                    if len(buffer):
                        buffer[-1].tail = (buffer[-1].tail or "") + text
                    else:
                        buffer.text = (buffer.text or "") + text
                        self.positions[(id(buffer), "text")] = self.location(source, position, href)

            def flush() -> None:
                nonlocal buffer
                if normalize_spaces("".join(buffer.itertext())) or any(local_name(c.tag) in {"img", "br"} | OPAQUE_TAGS or attr_value(c, "id") for c in buffer.iter()):
                    child = self.node(buffer, href)
                    if child:
                        node["content"].append({"type": "node", "node_id": child})
                buffer = ET.Element("p")

            append_text(el.text, el, "text")
            for child in el:
                cname = local_name(child.tag)
                if cname in BLOCK_TAGS or cname in OPAQUE_TAGS:
                    flush()
                    child_id = self.node(child, href)
                    if child_id:
                        node["content"].append({"type": "node", "node_id": child_id})
                elif cname not in ("script", "style", "nav"):
                    inline = copy.deepcopy(child)
                    inline.tail = None
                    for original, copied in zip(child.iter(), inline.iter()):
                        self.locations[id(copied)] = self.locations.get(id(original), "mixed")
                    buffer.append(inline)
                append_text(child.tail, child, "tail")
            flush()
        if not node["attr_slots"]:
            node["attr_slots"] = self.attrs(el, href)
        if tag in ("ul", "ol"):
            node["ordered"] = tag == "ol"
        if tag in ("td", "th"):
            node["header"] = tag == "th"
        return node["id"]


def build_flow(unpacked: Path, rootfile: str, spine_hrefs: list[str], items: list[dict]) -> dict:
    builder = FlowBuilder()
    _, source_opf, _, _ = package_data(unpacked)
    spine_element = source_opf.find(f"{{{OPF_NS}}}spine")
    by_manifest_id = {item["id"]: item for item in items}
    linear_by_href = {by_manifest_id[el.get("idref")]["href"]: el.get("linear", "yes") for el in spine_element if el.get("idref") in by_manifest_id} if spine_element is not None else {}
    documents = []
    hrefs = list(dict.fromkeys(spine_hrefs + [item["href"] for item in items if item["media_type"] == "application/xhtml+xml" and "nav" not in item["properties"].split()]))
    for source_href in hrefs:
        item = next((i for i in items if i["href"] == source_href), {})
        if "nav" in item.get("properties", "").split():
            continue
        href = posixpath.relpath(archive_path(rootfile, source_href), posixpath.dirname(rootfile) or ".")
        internal = canonical_archive_path(rootfile, href)
        doc = {"href": href, "source_href": source_href, "manifest_id": item.get("id"), "internal": internal, "roots": [],
               "in_spine": source_href in spine_hrefs, "linear": linear_by_href.get(source_href, "yes")}
        documents.append(doc)
        try:
            tree = parse_xml(safe_join(unpacked, internal))
        except EpubTranslatorError as exc:
            doc["source_error"] = str(exc)
            continue
        body = next((el for el in tree.getroot().iter() if local_name(el.tag) == "body"), None)
        if body is None:
            doc["source_error"] = f"document has no body: {href}"
            continue
        builder.locations = dom_locations(tree.getroot())
        builder.positions = {}
        node_id = builder.node(body, href)
        if node_id:
            doc["roots"].append(node_id)
    _, opf, _, _ = package_data(unpacked)
    metadata = []
    for field in METADATA_FIELDS:
        occurrence = 0
        for element in opf.findall(f".//{{{DC_NS}}}{field}"):
            if element.text and element.text.strip():
                metadata.append({"field": field, "id": builder.atom(element.text, "metadata", rootfile, field=field, location=f"{rootfile}:metadata:{field}:{occurrence}"), "source": element.text,
                                 "attrs": dict(element.attrib)})
                occurrence += 1
    return {"schema_version": FLOW_SCHEMA_VERSION, "generated_at": utc_now(), "documents": documents, "blocks": builder.blocks,
            "atoms": builder.atoms, "metadata": metadata, "stats": builder.stats}


def ordered_nodes(flow: dict):
    by_id = {node["id"]: node for node in flow["blocks"]}
    def visit(node_id):
        node = by_id[node_id]
        yield node
        for item in node.get("content", []):
            if item["type"] == "node":
                yield from visit(item["node_id"])
    for doc in flow["documents"]:
        for node_id in doc["roots"]:
            yield from visit(node_id)


def write_chunks(flow: dict, directory: Path, max_chars: int = DEFAULT_MAX_CHARS, soft_min: int = DEFAULT_SOFT_MIN) -> dict:
    if max_chars <= 0 or soft_min < 0 or soft_min > max_chars:
        raise EpubTranslatorError("chunk limits require 0 <= soft-min <= max-chars and max-chars > 0")
    chunks: list[dict] = []
    peripheral = [{"id": atom["id"], "source": atom["source"], "block_id": None, "block_type": atom["kind"], "href": atom["href"]}
                  for atom in flow["atoms"] if atom["kind"] != "text"]
    if peripheral:
        chunks.append({"kind": "peripheral", "items": peripheral})
    current: list[dict] = []
    count = 0
    oversized = []
    for node in ordered_nodes(flow):
        unit = node.get("unit")
        if not unit or not unit.get("id"):
            continue
        item = {"id": unit["id"], "source": unit["source"], "block_id": node["id"], "block_type": node["kind"], "href": node["href"]}
        if unit["markers"]:
            item["markers"] = unit["markers"]
        size = len(item["source"])
        if current and (count + size > max_chars or (node["kind"] == "heading" and count >= soft_min)):
            chunks.append({"kind": "prose", "items": current})
            current, count = [], 0
        current.append(item)
        count += size
        if size > max_chars:
            oversized.append(unit["id"])
    if current or not chunks:
        chunks.append({"kind": "prose", "items": current})
    directory.mkdir(parents=True, exist_ok=True)
    metadata = []
    for index, chunk in enumerate(chunks, 1):
        write_json(directory / f"chunk-{index:04d}.json", {"schema_version": TEXT_SCHEMA_VERSION, "chunk_index": index, **chunk})
        metadata.append({"chunk_index": index, "kind": chunk["kind"], "item_count": len(chunk["items"]), "chars": sum(len(i["source"]) for i in chunk["items"])})
    return {"chunks": metadata, "total_items": sum(c["item_count"] for c in metadata),
            "prose_items": sum(c["item_count"] for c in metadata if c["kind"] == "prose"), "peripheral_items": len(peripheral), "oversized_units": oversized}


def marker_parts(text: str, markers: dict) -> list[tuple[str, str]]:
    """Validate conservation, spelling, and nesting before any rendering."""
    result = []
    stack = []
    used = set()
    offset = 0
    for match in MARK_RE.finditer(text):
        plain = text[offset:match.start()]
        if "⟦" in plain or "⟧" in plain:
            raise EpubTranslatorError("unrecognized protected marker syntax")
        result.append(("text", plain))
        closing, key, atomic = match.groups()
        if key not in markers:
            raise EpubTranslatorError(f"unknown protected marker {key}")
        paired = markers[key]["kind"] == "inline"
        if closing:
            if atomic or not paired or not stack or stack.pop() != key:
                raise EpubTranslatorError(f"incorrect marker nesting at {key}")
            result.append(("close", key))
        else:
            if key in used or bool(atomic) == paired:
                raise EpubTranslatorError(f"duplicate or incorrect marker {key}")
            used.add(key)
            if paired:
                stack.append(key)
            result.append(("open" if paired else "atomic", key))
        offset = match.end()
    plain = text[offset:]
    if "⟦" in plain or "⟧" in plain:
        raise EpubTranslatorError("unrecognized protected marker syntax")
    result.append(("text", plain))
    if stack or used != set(markers):
        raise EpubTranslatorError("missing or unclosed protected markers")
    return result


def source_fingerprint(unpacked: Path, rootfile: str, items: list[dict]) -> str:
    payload = bytearray()
    for name in sorted({rootfile} | {archive_path(rootfile, i["href"]) for i in items if i["media_type"] == "application/xhtml+xml"}):
        path = safe_join(unpacked, name)
        payload.extend(name.encode())
        if path.is_file():
            payload.extend(path.read_bytes())
    return sha256_bytes(bytes(payload))


def read_flow(workdir: Path) -> dict:
    persisted = read_json(workdir / "flow/book.flow.json")
    version = persisted.get("schema_version")
    if version == FLOW_SCHEMA_VERSION:
        manifest = read_json(workdir / "manifest.json")
        if manifest.get("source_fingerprint"):
            rootfile, _, items, _ = package_data(workdir / "unpacked")
            if manifest["source_fingerprint"] != source_fingerprint(workdir / "unpacked", rootfile, items):
                raise EpubTranslatorError("unpacked source changed after ingest; restore it or explicitly create a new run")
        return persisted
    if version != 2:
        raise EpubTranslatorError(f"unsupported flow schema_version: {version!r}")
    unpacked = workdir / "unpacked"
    rootfile, _, items, spine = package_data(unpacked)
    fingerprint = source_fingerprint(unpacked, rootfile, items)
    recovery_path = workdir / "legacy-recovery.json"
    if recovery_path.is_file():
        recovered = read_json(recovery_path)
        if recovered.get("schema_version") != 1 or recovered.get("source_fingerprint") != fingerprint:
            raise EpubTranslatorError("legacy recovery source changed; preserve existing rows and rerun recover after source review")
        flow = recovered["flow"]
        flow["recovery_recorded"] = recovered.get("complete", False)
        flow["recovery_plan"] = recovered.get("chunks", [])
        return flow
    fresh = build_flow(unpacked, rootfile, spine, items)
    fresh["generated_at"] = persisted.get("generated_at", "legacy")
    old_atoms = {}
    for block in persisted.get("blocks", []):
        for attr in block.get("attr_slots", []):
            old_atoms[attr["id"]] = {**attr, "kind": "attribute", "href": block["href"], "block_id": block["id"]}
        for token in block.get("tokens", []):
            if token["type"] == "text":
                old_atoms[token["id"]] = {**token, "kind": "text", "href": block["href"], "block_id": block["id"]}
            elif token["type"] == "image":
                if token.get("alt_id"):
                    old_atoms[token["alt_id"]] = {"source": token["alt_source"], "kind": "alt", "href": block["href"], "block_id": block["id"]}
                for attr in token.get("attr_slots", []):
                    old_atoms[attr["id"]] = {**attr, "kind": "attribute", "href": block["href"], "block_id": block["id"]}
    for path in sorted((workdir / "chunks").glob("chunk-*.json")):
        for item in read_json(path).get("items", []):
            if item["id"].startswith("m"):
                old_atoms[item["id"]] = {**item, "kind": "metadata"}
    mapping = {}
    replay = source_slots(unpacked, rootfile, spine)
    fresh_locations = {atom["location"]: atom for atom in fresh["atoms"]}
    nav_hrefs = {posixpath.relpath(archive_path(rootfile, item["href"]), posixpath.dirname(rootfile) or ".")
                for item in items if "nav" in item["properties"].split()}
    for old_id, atom in old_atoms.items():
        context = replay.get(old_id)
        if context is None or context["kind"] != atom["kind"] or context["source"] != normalize_spaces(atom["source"]) or (atom.get("block_id") and context.get("block_id") != atom["block_id"]):
            raise EpubTranslatorError(f"legacy slot ownership cannot be verified for {old_id}; preserve rows and review/restore source before explicit recovery")
        target = fresh_locations.get(context["location"])
        if target is None and context["href"] in nav_hrefs:
            fresh["atoms"].append({"id": old_id, **context, "retired_navigation": True})
            continue
        if target is None or target["source"] != context["source"]:
            raise EpubTranslatorError(f"legacy source location cannot be retained for {old_id}; preserve rows and review unsupported media or explicitly start a new run")
        mapping[target["id"]] = old_id
    recovered_items = []
    for atom in fresh["atoms"]:
        if atom["id"] not in mapping and not atom.get("retired_navigation"):
            rid = f"r{len(recovered_items) + 1:06d}"
            mapping[atom["id"]] = rid
            recovered_items.append({"id": rid, "source": atom["source"], "block_id": None, "block_type": atom["kind"], "href": atom["href"]})
    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {k: rewrite(v) for k, v in value.items()}
        for name in ("atom_id", "alt_id", "slot_id"):
            if result.get(name) in mapping:
                result[name] = mapping[result[name]]
        if "source" in result and result.get("id") in mapping:
            result["id"] = mapping[result["id"]]
        return result
    fresh = rewrite(fresh)
    fresh.update(legacy=True, source_fingerprint=fingerprint, recovery_items=recovered_items, recovery_recorded=False)
    for node in fresh["blocks"]:
        if "unit" in node:
            node["unit"]["legacy"] = True
    return fresh


def legacy_recovery_chunks(workdir: Path, flow: dict) -> list[dict]:
    if not flow.get("recovery_items") or flow.get("recovery_recorded"):
        return []
    if "recovery_plan" in flow:
        return [chunk for chunk in flow["recovery_plan"] if not (workdir / "chunks" / f"chunk-{chunk['chunk_index']:04d}.json").exists()]
    indices = [read_json(p).get("chunk_index", 0) for p in (workdir / "chunks").glob("chunk-*.json")]
    result = []
    for kind in ("peripheral", "prose"):
        items = [item for item in flow["recovery_items"] if (item["block_type"] == "text") == (kind == "prose")]
        if items:
            result.append({"schema_version": 3, "chunk_index": max(indices, default=0) + len(result) + 1, "kind": kind, "items": items, "legacy_recovery": True})
    return result


def record_legacy_recovery(workdir: Path, flow: dict) -> list[str]:
    if flow.get("recovery_recorded"):
        return []
    plan = flow.get("recovery_plan", legacy_recovery_chunks(workdir, flow))
    plan_path = workdir / "legacy-recovery.json"
    snapshot = copy.deepcopy(flow)
    snapshot.pop("recovery_plan", None)
    envelope = {"schema_version": 1, "source_fingerprint": flow["source_fingerprint"], "flow": snapshot, "chunks": plan, "complete": False}
    write_json_atomic(plan_path, envelope)
    paths = []
    for chunk in plan:
        path = workdir / "chunks" / f"chunk-{chunk['chunk_index']:04d}.json"
        if path.exists():
            if read_json(path) != chunk:
                raise EpubTranslatorError(f"recovery must not replace mismatching existing chunk: {path}")
            continue
        write_json_atomic(path, chunk)
        paths.append(str(path))
    flow["recovery_recorded"] = True
    envelope["flow"]["recovery_recorded"] = True
    envelope["complete"] = True
    write_json_atomic(plan_path, envelope)
    return paths


def append_text(parent: ET.Element, text: str) -> None:
    if len(parent):
        parent[-1].tail = (parent[-1].tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def apply_attrs(element: ET.Element, slots: list[dict], translations: dict) -> None:
    for slot in slots:
        element.set(slot["attr"], translations[slot["id"]])


def render_unit(unit: dict, parent: ET.Element, translations: dict, image_renderer) -> None:
    markers = unit["markers"]
    if unit.get("legacy"):
        events = []
        for part in unit["parts"]:
            if part.get("legacy_skip"):
                continue
            if "marker" in part:
                match = MARK_RE.fullmatch(part["marker"])
                closing, key, atomic = match.groups()
                events.append(("close" if closing else ("atomic" if atomic else "open"), key))
            elif part.get("atom_id"):
                source = part.get("legacy_text", part.get("text", ""))
                target = translations[part["atom_id"]]
                leading = " " if source.startswith(" ") and not target[:1].isspace() else ""
                trailing = " " if source.endswith(" ") and not target[-1:].isspace() else ""
                events.append(("text", leading + target + trailing))
            else:
                events.append(("text", part["text"]))
    else:
        text = translations[unit["id"]] if unit.get("id") else unit["source"]
        events = marker_parts(text, markers)
    stack = [parent]
    for kind, value in events:
        if kind == "text":
            append_text(stack[-1], value)
        elif kind == "close":
            stack.pop()
        elif kind == "open":
            mark = markers[value]
            element = ET.SubElement(stack[-1], X(mark["tag"]), mark.get("attrs", {}))
            apply_attrs(element, mark.get("attr_slots", []), translations)
            stack.append(element)
        else:
            mark = markers[value]
            if mark["kind"] == "image":
                image_renderer(mark, stack[-1])
            elif mark["kind"] == "anchor":
                ET.SubElement(stack[-1], X("span"), {"id": mark["id"]})
            elif mark["kind"] == "br":
                element = ET.SubElement(stack[-1], X("br"), mark.get("attrs", {}))
                apply_attrs(element, mark.get("attr_slots", []), translations)
            elif mark["kind"] == "literal":
                append_text(stack[-1], mark["value"])
            elif mark["kind"] == "opaque":
                stack[-1].append(ET.fromstring(mark["source_xml"]))


def render_document(doc: dict, flow: dict, translations: dict, edition: dict, resolve_image) -> ET.Element:
    html = ET.Element(X("html"), {"lang": edition["language_tag"], "{http://www.w3.org/XML/1998/namespace}lang": edition["language_tag"], "dir": edition["text_direction"]})
    head = ET.SubElement(html, X("head"))
    ET.SubElement(head, X("title")).text = doc["href"]
    css_href = uri_path(posixpath.relpath(edition.get("_css_href", CSS_HREF), posixpath.dirname(doc["href"]) or "."))
    ET.SubElement(head, X("link"), {"rel": "stylesheet", "type": "text/css", "href": css_href})
    body = ET.SubElement(html, X("body"))
    by_id = {node["id"]: node for node in flow["blocks"]}
    def image(data, parent):
        attrs = {"src": resolve_image(data["src"], doc["href"]), "alt": translations[data["alt_id"]] if data.get("alt_id") else data.get("alt_source", "")}
        if data.get("anchors"):
            attrs["id"] = data["anchors"][0]
        element = ET.SubElement(parent, X("img"), attrs)
        apply_attrs(element, data.get("attr_slots", []), translations)
    def node(node_id, parent):
        item = by_id[node_id]
        kind = item["kind"]
        if kind == "section" and not item["anchors"] and not item["attr_slots"]:
            element = parent
        elif kind == "image":
            image(item["image"], parent)
            return
        elif kind == "opaque":
            parent.append(ET.fromstring(item["source_xml"]))
            return
        else:
            tag = {"heading": f"h{item.get('level', 1)}", "paragraph": "p", "list": "ol" if item.get("ordered") else "ul", "list_item": "li", "table_row": "tr", "table_cell": "th" if item.get("header") else "td", "separator": "hr"}.get(kind, kind)
            element = ET.SubElement(parent, X(tag))
            if item["anchors"]:
                element.set("id", item["anchors"][0])
            apply_attrs(element, item["attr_slots"], translations)
        if item.get("unit"):
            render_unit(item["unit"], element, translations, image)
        for content in item["content"]:
            node(content["node_id"], element)
    for node_id in doc["roots"]:
        node(node_id, body)
    return html
