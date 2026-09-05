#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"

FLOW_SCHEMA_VERSION = 2
TEXT_SCHEMA_VERSION = 3

DEFAULT_MAX_CHARS = 5000
DEFAULT_SOFT_MIN = 1500
SEAM_TAIL_CHARS = 240

TRANSPARENT_BLOCKS = {
    "body", "div", "section", "article", "main", "header", "footer",
    "center", "details", "summary",
}
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
INLINE_EM_TAGS = {"em", "i", "cite", "dfn", "var"}
INLINE_STRONG_TAGS = {"strong", "b"}
INLINE_SUBSUP = {"sub", "sup"}
WRAPPER_TAGS = {"span", "font", "small", "mark", "u", "s", "q", "abbr", "time", "kbd", "samp"}
EDITABLE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
IMAGE_SUFFIX_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
SKIP_TEXT_TAGS = {"script", "style"}
RUBY_NOTE_TAGS = {"rt", "rp"}
SEPARATOR_RE = re.compile(r"^[\s*#✦✧◆◇○●☆★※―─\-−·•․…~⁂❖※]+$")
FIXED_LAYOUT_CLASS_RE = re.compile(r"start-10em|vrtl|vert|tcy|sideways", re.IGNORECASE)
IDEOGRAPHIC_SPACE = "　"

NAV_HREF = "xhtml/nav.xhtml"
CSS_HREF = "style/target.css"

EDITION_KEYS = {"schema_version", "target_language", "language_tag", "page_progression_direction"}
LANG_RE = re.compile(r"^[a-z]{2,8}(-[a-zA-Z0-9]{1,8})*$")

# Attributes preserved as translatable slots on any node that keeps an output
# element. Flattened transparent wrappers (span etc.) have no output node and
# are intentionally excluded.
ATTR_SLOT_NAMES = ("title", "aria-label")


class EpubTranslatorError(RuntimeError):
    pass


def X(tag: str) -> str:
    return f"{{{XHTML_NS}}}{tag}"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EpubTranslatorError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EpubTranslatorError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def attr_value(el: ET.Element, name: str) -> str | None:
    for k, v in el.attrib.items():
        if local_name(k) == name:
            return v
    return None


def has_text(v: str | None) -> bool:
    return bool(v and v.strip())


def normalize_text(v: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", v)


def normalize_spaces(value: str, stats: dict | None = None) -> str:
    if IDEOGRAPHIC_SPACE in value and stats is not None:
        stats["ideographic_spaces_normalized"] += value.count(IDEOGRAPHIC_SPACE)
    value = value.replace(IDEOGRAPHIC_SPACE, " ")
    value = re.sub(r"[ \t\r\n\f\v]+", " ", value)
    return value.strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_join(base: Path, internal: str) -> Path:
    base_resolved = base.resolve()
    candidate = (base / internal).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise EpubTranslatorError(f"unsafe EPUB path: {internal}") from exc
    return candidate


def safe_extract(epub: Path, dest: Path) -> None:
    with zipfile.ZipFile(epub) as archive:
        for info in archive.infolist():
            if info.is_dir():
                safe_join(dest, info.filename).mkdir(parents=True, exist_ok=True)
                continue
            target = safe_join(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def parse_xml(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        raise EpubTranslatorError(f"could not parse XML: {path}: {exc}") from exc


def register_ns(default_ns: str) -> None:
    ET.register_namespace("", default_ns)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("epub", EPUB_NS)


def write_xml(path: Path, tree: ET.ElementTree, default_ns: str) -> None:
    register_ns(default_ns)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def container_rootfile(epub_root: Path) -> str:
    tree = parse_xml(epub_root / "META-INF" / "container.xml")
    rf = tree.getroot().find(f".//{{{CONTAINER_NS}}}rootfile")
    if rf is None or not rf.get("full-path"):
        raise EpubTranslatorError("META-INF/container.xml has no rootfile")
    return rf.get("full-path", "")


def opf_root(epub_root: Path, rootfile: str) -> tuple[Path, ET.ElementTree, ET.Element]:
    p = safe_join(epub_root, rootfile)
    t = parse_xml(p)
    return p, t, t.getroot()


def manifest_items(opf: ET.Element) -> list[dict]:
    m = opf.find(f"{{{OPF_NS}}}manifest")
    if m is None:
        raise EpubTranslatorError("OPF manifest missing")
    out = []
    for item in m.findall(f"{{{OPF_NS}}}item"):
        out.append({
            "id": item.get("id", ""),
            "href": item.get("href", ""),
            "media_type": item.get("media-type", ""),
            "properties": item.get("properties", ""),
        })
    return out


def spine_info(opf: ET.Element) -> dict:
    s = opf.find(f"{{{OPF_NS}}}spine")
    if s is None:
        return {"page_progression_direction": None, "idrefs": []}
    return {
        "page_progression_direction": s.get("page-progression-direction"),
        "idrefs": [r.get("idref", "") for r in s.findall(f"{{{OPF_NS}}}itemref")],
    }


def metadata_value(opf: ET.Element, tag: str) -> str | None:
    el = opf.find(f".//{{{DC_NS}}}{tag}")
    if el is None or el.text is None:
        return None
    return el.text.strip()


def full_internal(rootfile: str, href: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(rootfile), href))


def inspect_epub(epub: Path) -> dict:
    with zipfile.ZipFile(epub) as z:
        names = z.namelist()
        with z.open("META-INF/container.xml") as f:
            rootfile = ET.parse(f).getroot().find(f".//{{{CONTAINER_NS}}}rootfile").get("full-path", "")  # type: ignore
        with z.open(rootfile) as f:
            opf = ET.parse(f).getroot()
    items = manifest_items(opf)
    images = [x for x in items if x["media_type"].startswith("image/")]
    editable = [x for x in images if x["media_type"] in EDITABLE_IMAGE_TYPES]
    unsupported = [x for x in images if x["media_type"] not in EDITABLE_IMAGE_TYPES]
    xhtml = [x for x in items if x["media_type"] == "application/xhtml+xml"]
    css = [x for x in items if x["media_type"] == "text/css"]
    return {
        "epub": str(epub),
        "entry_count": len(names),
        "rootfile": rootfile,
        "title": metadata_value(opf, "title"),
        "creator": metadata_value(opf, "creator"),
        "language": metadata_value(opf, "language"),
        "spine": spine_info(opf),
        "counts": {
            "images": len(images),
            "editable_images": len(editable),
            "unsupported_images": len(unsupported),
            "xhtml": len(xhtml),
            "css": len(css),
            "manifest_items": len(items),
        },
        "images": [
            {"id": x["id"], "href": full_internal(rootfile, x["href"]), "media_type": x["media_type"], "editable": x["media_type"] in EDITABLE_IMAGE_TYPES}
            for x in images
        ],
    }


# ---------------------------------------------------------------------------
# Flow IR extraction — node tree
#
# A node tree replaces the flat block list with explicit ownership:
#   - every node captures its element's id -> `anchors` and title/aria-label ->
#     `attr_slots` in ONE place (node construction), so no per-tag branch can
#     forget them (section ids, <a id>, title/aria-label are preserved);
#   - containers own their children by id, so rendering and packing follow
#     `children` with no scan-ahead, no container_id/row side refs, and no
#     orphan li/td (a table_cell/list_item can only exist as a child);
#   - render, link validation, and chunk packing read the same tree.

@dataclass
class FlowBuilder:
    stats: dict
    block_counter: int = 0
    slot_counter: int = 0
    blocks: list = field(default_factory=list)

    def next_block_id(self) -> str:
        self.block_counter += 1
        return f"b{self.block_counter:06d}"

    def next_slot_id(self) -> str:
        self.slot_counter += 1
        return f"t{self.slot_counter:06d}"

    def add(self, node: dict) -> None:
        self.blocks.append(node)

    def blocks_by_id(self) -> dict[str, dict]:
        return {b["id"]: b for b in self.blocks}


def _is_separator_text(text: str) -> bool:
    return bool(text) and bool(SEPARATOR_RE.match(text))


def _text_token(ctx: FlowBuilder, source: str, inline_stack: list[dict]) -> dict | None:
    norm = normalize_spaces(source, ctx.stats)
    if not norm:
        return None
    return {"type": "text", "id": ctx.next_slot_id(), "source": norm, "inline": list(inline_stack)}


def capture_attrs(el: ET.Element, ctx: FlowBuilder) -> list[dict]:
    """title/aria-label on an element that keeps an output node."""
    out: list[dict] = []
    for attr in ATTR_SLOT_NAMES:
        v = el.get(attr)
        if v and v.strip():
            norm = normalize_spaces(v, ctx.stats)
            if norm:
                out.append({"attr": attr, "id": ctx.next_slot_id(), "source": norm})
    return out


def inline_tokens(el: ET.Element, ctx: FlowBuilder, inline_stack: list[dict], anchors: list[str]) -> list[dict]:
    """The single recursive inline walker shared by every leaf node.

    Handles ruby collapse (base text only, rt/rp counted in stats), wrapper
    flattening (fixed-layout classes + writing-mode), emphasis/link stacks,
    <br>, and <img> — an image always carries an alt slot plus its own
    title/aria-label slots, so nested images never leak into prose.
    """
    out: list[dict] = []

    def emit(text: str) -> None:
        tok = _text_token(ctx, text, inline_stack)
        if tok is not None:
            out.append(tok)

    if has_text(el.text):
        emit(el.text or "")
    for child in list(el):
        cname = local_name(child.tag)
        if cname in SKIP_TEXT_TAGS:
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname in RUBY_NOTE_TAGS:
            ctx.stats["rubies_collapsed"] += 1
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname == "ruby":
            ctx.stats["ruby_elements"] += 1
            if has_text(child.text):
                emit(child.text or "")
            for rc in list(child):
                if local_name(rc.tag) in RUBY_NOTE_TAGS:
                    ctx.stats["rubies_collapsed"] += 1
                else:
                    out.extend(inline_tokens(rc, ctx, inline_stack, anchors))
                    if has_text(rc.tail):
                        emit(rc.tail or "")
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname == "br":
            out.append({"type": "br"})
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname == "img":
            src = attr_value(child, "src") or child.get("src") or ""
            alt = attr_value(child, "alt") or child.get("alt") or ""
            tok = {"type": "image", "src": src, "alt_source": normalize_spaces(alt, ctx.stats)}
            if tok["alt_source"]:
                tok["alt_id"] = ctx.next_slot_id()
            attr = capture_attrs(child, ctx)
            if attr:
                tok["attr_slots"] = attr
            iid = attr_value(child, "id")
            if iid:
                tok["anchor"] = iid
                anchors.append(iid)
            out.append(tok)
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname in WRAPPER_TAGS:
            cls = attr_value(child, "class") or child.get("class") or ""
            style = attr_value(child, "style") or child.get("style") or ""
            if FIXED_LAYOUT_CLASS_RE.search(cls) or "writing-mode" in style:
                ctx.stats["wrappers_flattened"] += 1
            iid = attr_value(child, "id")
            if iid:
                anchors.append(iid)
            # transparent: recurse with the same stack; recursion emits child.text
            out.extend(inline_tokens(child, ctx, inline_stack, anchors))
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname in INLINE_EM_TAGS or cname in INLINE_STRONG_TAGS or cname in INLINE_SUBSUP:
            tag = "em" if cname in INLINE_EM_TAGS else ("strong" if cname in INLINE_STRONG_TAGS else cname)
            new_stack = inline_stack + [{"tag": tag}]
            out.extend(inline_tokens(child, ctx, new_stack, anchors))
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        if cname == "a":
            href = attr_value(child, "href") or child.get("href") or ""
            aid = attr_value(child, "id")
            if aid:
                anchors.append(aid)  # pre-order: before descendants
            new_stack = inline_stack + [{"tag": "a", "href": href}]
            out.extend(inline_tokens(child, ctx, new_stack, anchors))
            if has_text(child.tail):
                emit(child.tail or "")
            continue
        # unknown inline element — flatten transparently
        iid = attr_value(child, "id")
        if iid:
            anchors.append(iid)
        out.extend(inline_tokens(child, ctx, inline_stack, anchors))
        if has_text(child.tail):
            emit(child.tail or "")
    return out


def _leaf_node(el: ET.Element, ctx: FlowBuilder, doc_href: str, spine_index: int, kind: str, *, tokens: list[dict] | None = None, extra_anchors: list[str] | None = None, **extra) -> dict | None:
    el_id = attr_value(el, "id")
    anchors: list[str] = ([el_id] if el_id else []) + (extra_anchors or [])
    if tokens is None:
        tokens = inline_tokens(el, ctx, [], anchors)
    attr_slots = capture_attrs(el, ctx)
    text = " ".join(t["source"] for t in tokens if t["type"] == "text")
    text = normalize_spaces(text, ctx.stats) if text else ""
    if not tokens and not anchors and not attr_slots:
        return None
    kind_eff = kind
    if not tokens and anchors:
        kind_eff = "anchor_only" if not attr_slots else kind
    node = {
        "id": ctx.next_block_id(),
        "kind": kind_eff,
        "href": doc_href,
        "spine_index": spine_index,
        "anchors": anchors,
        "attr_slots": attr_slots,
        "children": [],
        "tokens": tokens,
        "text": text,
        "review_flags": [],
        **extra,
    }
    ctx.add(node)
    return node


def _image_node(el: ET.Element, ctx: FlowBuilder, doc_href: str, spine_index: int) -> dict | None:
    src = attr_value(el, "src") or el.get("src") or ""
    alt = attr_value(el, "alt") or el.get("alt") or ""
    tok = {"type": "image", "src": src, "alt_source": normalize_spaces(alt, ctx.stats)}
    if tok["alt_source"]:
        tok["alt_id"] = ctx.next_slot_id()
    attr = capture_attrs(el, ctx)
    if attr:
        tok["attr_slots"] = attr
    el_id = attr_value(el, "id")
    if not (tok.get("alt_id") or tok["alt_source"] or tok.get("attr_slots") or el_id):
        return None
    node = {
        "id": ctx.next_block_id(),
        "kind": "image",
        "href": doc_href,
        "spine_index": spine_index,
        "anchors": [el_id] if el_id else [],
        "attr_slots": [],  # image attrs live on the token, not duplicated here
        "children": [],
        "tokens": [tok],
        "text": "",
        "review_flags": [],
    }
    ctx.add(node)
    return node


def _container_node(el: ET.Element, ctx: FlowBuilder, doc_href: str, spine_index: int, kind: str, *, ordered: bool | None = None) -> dict | None:
    """A structure node owning child nodes. Its subtree is packed and rendered
    as one atomic unit. Captures the element's own id and attrs, and recurses
    into element children only (interleaved text is dropped, per HTML flow)."""
    el_id = attr_value(el, "id")
    node = {
        "id": ctx.next_block_id(),
        "kind": kind,
        "href": doc_href,
        "spine_index": spine_index,
        "anchors": [el_id] if el_id else [],
        "attr_slots": capture_attrs(el, ctx),
        "children": [],
        "tokens": [],
        "text": "",
        "review_flags": [],
    }
    if ordered is not None:
        node["ordered"] = ordered
    ctx.add(node)
    for child_el in list(el):
        cname = local_name(child_el.tag)
        if cname in SKIP_TEXT_TAGS:
            continue
        child = node_from_element(child_el, ctx, doc_href, spine_index)
        if child is not None:
            node["children"].append(child["id"])
    if not node["children"] and not node["anchors"] and not node["attr_slots"] and kind not in ("figure",):
        # empty transparent wrapper — drop (it is the last appended node)
        ctx.blocks.pop()
        return None
    if kind == "figure" and not node["children"] and not node["anchors"] and not node["attr_slots"]:
        ctx.blocks.pop()
        return None
    return node


def _table_node(el: ET.Element, ctx: FlowBuilder, doc_href: str, spine_index: int) -> dict | None:
    node = _container_node(el, ctx, doc_href, spine_index, "table")
    # table already recursed into <tr>/<td> children via node_from_element
    return node


def node_from_element(el: ET.Element, ctx: FlowBuilder, doc_href: str, spine_index: int) -> dict | None:
    cname = local_name(el.tag)
    if cname in SKIP_TEXT_TAGS:
        return None
    if cname == "nav":
        return None
    if cname in TRANSPARENT_BLOCKS:
        return _container_node(el, ctx, doc_href, spine_index, "section")
    if cname in HEADING_TAGS:
        return _leaf_node(el, ctx, doc_href, spine_index, "heading", level=HEADING_TAGS[cname])
    if cname == "p":
        visible = "".join(el.itertext()) if list(el) else (el.text or "")
        visible = normalize_spaces(visible)
        if visible and _is_separator_text(visible):
            return _leaf_node(el, ctx, doc_href, spine_index, "separator", tokens=[{"type": "sep"}])
        return _leaf_node(el, ctx, doc_href, spine_index, "paragraph")
    if cname == "blockquote":
        if any(local_name(c.tag) in HEADING_TAGS or local_name(c.tag) in ("p", "ul", "ol", "table", "blockquote") for c in list(el)):
            return _container_node(el, ctx, doc_href, spine_index, "blockquote")
        return _leaf_node(el, ctx, doc_href, spine_index, "blockquote")
    if cname == "aside":
        if any(local_name(c.tag) in HEADING_TAGS or local_name(c.tag) in ("p", "ul", "ol", "table") for c in list(el)):
            return _container_node(el, ctx, doc_href, spine_index, "aside")
        return _leaf_node(el, ctx, doc_href, spine_index, "aside")
    if cname in ("ul", "ol"):
        return _container_node(el, ctx, doc_href, spine_index, "list", ordered=(cname == "ol"))
    if cname == "table":
        return _table_node(el, ctx, doc_href, spine_index)
    if cname == "tr":
        return _container_node(el, ctx, doc_href, spine_index, "table_row")
    if cname in ("td", "th"):
        return _leaf_node(el, ctx, doc_href, spine_index, "table_cell", header=(cname == "th"))
    if cname in ("li",):
        # treat the whole <li> as one translatable cell (flat tokens)
        return _leaf_node(el, ctx, doc_href, spine_index, "list_item")
    if cname == "figure":
        return _container_node(el, ctx, doc_href, spine_index, "figure")
    if cname == "figcaption":
        return _leaf_node(el, ctx, doc_href, spine_index, "figcaption")
    if cname == "img":
        return _image_node(el, ctx, doc_href, spine_index)
    if cname == "hr":
        el_id = attr_value(el, "id")
        return _leaf_node(el, ctx, doc_href, spine_index, "separator", tokens=[{"type": "sep"}], extra_anchors=[el_id] if el_id else [])
    # fallback: text-bearing element -> paragraph leaf, else recurse as section
    if has_text(el.text) or any(has_text(c.text) or has_text(c.tail) for c in el.iter() if c is not el):
        return _leaf_node(el, ctx, doc_href, spine_index, "paragraph")
    return _container_node(el, ctx, doc_href, spine_index, "section")


def build_flow(unpacked: Path, rootfile: str, spine_hrefs: list[str], manifest_by_href: dict) -> tuple[dict, dict]:
    stats = {"rubies_collapsed": 0, "ruby_elements": 0, "wrappers_flattened": 0, "ideographic_spaces_normalized": 0}
    ctx = FlowBuilder(stats)
    documents: list[dict] = []
    opf_dir = posixpath.dirname(rootfile)
    for spine_index, href in enumerate(spine_hrefs):
        internal = posixpath.normpath(posixpath.join(opf_dir, href))
        try:
            xhtml_path = safe_join(unpacked, internal)
        except EpubTranslatorError as exc:
            documents.append({"href": href, "internal": internal, "roots": [], "unsafe": str(exc)})
            continue
        if not xhtml_path.is_file():
            documents.append({"href": href, "internal": internal, "roots": [], "missing": True})
            continue
        try:
            tree = parse_xml(xhtml_path)
        except EpubTranslatorError:
            documents.append({"href": href, "internal": internal, "roots": [], "parse_error": True})
            continue
        root = tree.getroot()
        body = None
        for el in root.iter():
            if local_name(el.tag) == "body":
                body = el
                break
        if body is None:
            documents.append({"href": href, "internal": internal, "roots": [], "no_body": True})
            continue
        before = len(ctx.blocks)
        roots: list[str] = []
        for child in list(body):
            cname = local_name(child.tag)
            if cname in SKIP_TEXT_TAGS:
                continue
            node = node_from_element(child, ctx, href, spine_index)
            if node is not None:
                roots.append(node["id"])
        documents.append({"href": href, "internal": internal, "roots": roots})
    flow = {
        "schema_version": FLOW_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "stats": stats,
        "documents": documents,
        "blocks": ctx.blocks,
    }
    return flow, stats


def collect_metadata_segments(opf_root_el: ET.Element, rootfile: str) -> list[dict]:
    segs = []
    counter = 0

    def nid():
        nonlocal counter
        counter += 1
        return f"m{counter:06d}"

    wanted = ["title", "creator", "publisher", "description", "subject"]
    for tag in wanted:
        for el in opf_root_el.iter():
            if local_name(el.tag) != tag:
                continue
            if el.tag.split("}")[0].strip("{") != DC_NS:
                continue
            if not has_text(el.text):
                continue
            segs.append({"id": nid(), "kind": "opf_metadata", "field": tag, "source": normalize_text(el.text or ""), "href": rootfile})
    return segs


# ---------------------------------------------------------------------------
# Chunk writer (slim schema v3) — atomic units from the node tree

def _subtree_ids(blocks_by_id: dict[str, dict], node_id: str, out: list[str]) -> None:
    out.append(node_id)
    for c in blocks_by_id[node_id].get("children", []):
        _subtree_ids(blocks_by_id, c, out)


def _collect_items(node: dict, blocks_by_id: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Return (prose_items, peripheral_items) for a node and its subtree."""
    prose: list[dict] = []
    peripheral: list[dict] = []
    stack = [node]
    while stack:
        n = stack.pop()
        for s in n.get("attr_slots", []):
            peripheral.append({"id": s["id"], "source": s["source"], "block_id": n["id"], "block_type": n["kind"], "href": n.get("href")})
        for tok in n.get("tokens", []):
            if tok["type"] == "text":
                item = {"id": tok["id"], "source": tok["source"], "block_id": n["id"], "block_type": n["kind"], "href": n.get("href")}
                if tok.get("inline"):
                    item["inline"] = tok["inline"]
                prose.append(item)
            elif tok["type"] == "image":
                if tok.get("alt_id"):
                    peripheral.append({"id": tok["alt_id"], "source": tok["alt_source"], "block_id": n["id"], "block_type": n["kind"], "href": n.get("href")})
                for s in tok.get("attr_slots", []):
                    peripheral.append({"id": s["id"], "source": s["source"], "block_id": n["id"], "block_type": n["kind"], "href": n.get("href")})
        for c in n.get("children", []):
            stack.append(blocks_by_id[c])
    return prose, peripheral


def chunk_units(flow: dict) -> list[str]:
    """Depth-first unit ids: a container + its whole subtree is ONE atomic unit."""
    blocks_by_id = {b["id"]: b for b in flow["blocks"]}
    units: list[str] = []

    def walk(nid: str) -> None:
        units.append(nid)
        node = blocks_by_id[nid]
        if node.get("children"):
            return  # container absorbs its subtree into one unit

    for doc in flow.get("documents", []):
        for rid in doc.get("roots", []):
            walk(rid)
    return units


def write_chunks(flow: dict, metadata_segs: list[dict], chunks_dir: Path, max_chars: int = DEFAULT_MAX_CHARS, soft_min: int = DEFAULT_SOFT_MIN) -> dict:
    chunks_dir.mkdir(parents=True, exist_ok=True)
    for p in chunks_dir.glob("chunk-*.json"):
        p.unlink()

    blocks_by_id = {b["id"]: b for b in flow["blocks"]}
    peripheral_items: list[dict] = []
    for seg in metadata_segs:
        peripheral_items.append({"id": seg["id"], "source": seg["source"], "block_id": None, "block_type": "metadata", "href": seg["href"]})

    # units with their items, in reading order
    unit_items: list[tuple[str, list[dict]]] = []
    for unit in chunk_units(flow):
        prose, peripheral = _collect_items(blocks_by_id[unit], blocks_by_id)
        peripheral_items.extend(peripheral)
        unit_items.append((unit, prose))

    chunks_meta: list[dict] = []
    idx = 1
    if peripheral_items:
        p = chunks_dir / f"chunk-{idx:04d}.json"
        write_json(p, {"schema_version": TEXT_SCHEMA_VERSION, "chunk_index": idx, "kind": "peripheral", "items": peripheral_items})
        chunks_meta.append({"chunk_index": idx, "kind": "peripheral", "item_count": len(peripheral_items), "chars": sum(len(x["source"]) for x in peripheral_items)})
        idx += 1

    cur: list[dict] = []
    cur_chars = 0
    cur_units: list[str] = []

    def flush():
        nonlocal cur, cur_chars, cur_units, idx
        if not cur:
            return
        p = chunks_dir / f"chunk-{idx:04d}.json"
        write_json(p, {"schema_version": TEXT_SCHEMA_VERSION, "chunk_index": idx, "kind": "prose", "items": list(cur)})
        chunks_meta.append({"chunk_index": idx, "kind": "prose", "item_count": len(cur), "chars": cur_chars, "units": list(cur_units)})
        idx += 1
        cur = []
        cur_chars = 0
        cur_units = []

    for unit, items in unit_items:
        unit_kind = blocks_by_id[unit]["kind"]
        unit_chars = sum(len(it["source"]) for it in items)
        is_break = unit_kind in ("heading", "separator")
        if cur and cur_chars >= soft_min:
            if is_break:
                flush()
            elif cur_chars + unit_chars > max_chars:
                flush()
        cur.extend(items)
        cur_chars += unit_chars
        cur_units.append(unit)
        if unit_kind == "separator" and cur_chars >= soft_min:
            flush()
    flush()

    if not chunks_meta:
        p = chunks_dir / f"chunk-{idx:04d}.json"
        write_json(p, {"schema_version": TEXT_SCHEMA_VERSION, "chunk_index": idx, "kind": "prose", "items": []})
        chunks_meta.append({"chunk_index": idx, "kind": "prose", "item_count": 0, "chars": 0, "units": []})

    return {"chunks": chunks_meta, "total_items": sum(len(items) for _, items in unit_items) + len(peripheral_items), "prose_items": sum(len(items) for _, items in unit_items), "peripheral_items": len(peripheral_items)}


# ---------------------------------------------------------------------------
# Edition policy

def write_edition_template(workdir: Path, flow: dict, inspect: dict) -> Path:
    p = workdir / "edition.json"
    if p.exists():
        return p
    template = {
        "schema_version": 1,
        "target_language": None,
        "language_tag": "ko",
        "page_progression_direction": "ltr",
    }
    write_json(p, template)
    return p


def validate_edition(edition: dict) -> list[str]:
    errors = []
    for k in edition:
        if k not in EDITION_KEYS:
            errors.append(f"edition.json: unknown key {k!r} (allowed: {sorted(EDITION_KEYS)})")
    sv = edition.get("schema_version")
    if sv is not None and sv != 1:
        errors.append(f"edition.json: schema_version must be 1 (got {sv!r})")
    ppd = edition.get("page_progression_direction")
    if ppd is not None and ppd not in ("ltr", "rtl"):
        errors.append(f"edition.json: page_progression_direction must be 'ltr' or 'rtl' (got {ppd!r})")
    for key in ("target_language", "language_tag"):
        val = edition.get(key)
        if val is not None and (not isinstance(val, str) or not LANG_RE.fullmatch(val)):
            errors.append(f"edition.json: {key} must be a BCP-47 language tag (got {val!r})")
    return errors


# ---------------------------------------------------------------------------
# Image jobs

def export_images(unpacked: Path, rootfile: str, manifest: list[dict], workdir: Path) -> dict:
    images_dir = workdir / "images" / "source"
    images_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    unsupported = []
    opf_dir = posixpath.dirname(rootfile)
    for item in manifest:
        mt = item["media_type"]
        if not mt.startswith("image/"):
            continue
        internal = posixpath.normpath(posixpath.join(opf_dir, item["href"]))
        if mt not in EDITABLE_IMAGE_TYPES:
            unsupported.append({"id": item["id"], "href": internal, "media_type": mt})
            continue
        try:
            src_path = safe_join(unpacked, internal)
        except EpubTranslatorError as exc:
            unsupported.append({"id": item["id"], "href": internal, "media_type": mt, "unsafe": str(exc)})
            continue
        if not src_path.is_file():
            unsupported.append({"id": item["id"], "href": internal, "media_type": mt, "missing": True})
            continue
        suffix = IMAGE_SUFFIX_BY_TYPE.get(mt, ".bin")
        job_id = f"img{len(jobs)+1:04d}"
        dest = images_dir / f"{job_id}{suffix}"
        shutil.copy2(src_path, dest)
        jobs.append({
            "id": job_id,
            "manifest_id": item["id"],
            "href": internal,
            "media_type": mt,
            "source_export": str(dest.relative_to(workdir)),
            "status": "pending_review",
            "sha256": sha256_bytes(dest.read_bytes()),
        })
    jobs_path = workdir / "image-jobs.json"
    write_json(jobs_path, {"generated_at": utc_now(), "jobs": jobs, "unsupported": unsupported})
    return {"jobs": jobs, "unsupported": unsupported}


# ---------------------------------------------------------------------------
# Commands

def cmd_inspect(args) -> int:
    epub = Path(args.epub)
    if not epub.is_file():
        raise EpubTranslatorError(f"EPUB not found: {epub}")
    info = inspect_epub(epub)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"title: {info['title']}")
        print(f"language: {info['language']}")
        print(f"counts: {info['counts']}")
    return 0


def cmd_ingest(args) -> int:
    epub = Path(args.epub)
    workdir = Path(args.workdir)
    if not epub.is_file():
        raise EpubTranslatorError(f"EPUB not found: {epub}")
    workdir.mkdir(parents=True, exist_ok=True)
    unpacked = workdir / "unpacked"
    if unpacked.exists():
        shutil.rmtree(unpacked)
    unpacked.mkdir(parents=True)
    safe_extract(epub, unpacked)
    rootfile = container_rootfile(unpacked)
    _opf_path, tree, root = opf_root(unpacked, rootfile)
    manifest = manifest_items(root)
    spine = spine_info(root)
    id_to_href = {m["id"]: m["href"] for m in manifest}
    spine_hrefs = [id_to_href[i] for i in spine["idrefs"] if i in id_to_href]
    if not spine_hrefs:
        spine_hrefs = [m["href"] for m in manifest if m["media_type"] == "application/xhtml+xml"]

    flow, stats = build_flow(unpacked, rootfile, spine_hrefs, {m["href"]: m for m in manifest})
    flow_dir = workdir / "flow"
    flow_dir.mkdir(parents=True, exist_ok=True)
    write_json(flow_dir / "book.flow.json", flow)

    metadata_segs = collect_metadata_segments(root, rootfile)
    chunk_info = write_chunks(flow, metadata_segs, workdir / "chunks", max_chars=args.max_chars, soft_min=args.soft_min)

    inspect = inspect_epub(epub)
    export = export_images(unpacked, rootfile, manifest, workdir)
    write_edition_template(workdir, flow, inspect)

    (workdir / "translations").mkdir(parents=True, exist_ok=True)

    total_slots = 0
    for b in flow["blocks"]:
        total_slots += len(b.get("attr_slots", []))
        for t in b.get("tokens", []):
            if t["type"] == "text":
                total_slots += 1
            elif t["type"] == "image":
                if t.get("alt_id"):
                    total_slots += 1
                total_slots += len(t.get("attr_slots", []))
    manifest_out = {
        "generated_at": utc_now(),
        "epub": str(epub.resolve()),
        "rootfile": rootfile,
        "flow_schema_version": FLOW_SCHEMA_VERSION,
        "text_schema_version": TEXT_SCHEMA_VERSION,
        "spine_hrefs": spine_hrefs,
        "block_count": len(flow["blocks"]),
        "slot_count": total_slots,
        "chunk_count": len(chunk_info["chunks"]),
        "chunks": chunk_info["chunks"],
        "total_items": chunk_info["total_items"],
        "prose_items": chunk_info["prose_items"],
        "peripheral_items": chunk_info["peripheral_items"],
        "image_job_count": len(export["jobs"]),
        "unsupported_image_count": len(export["unsupported"]),
        "flow_stats": stats,
        "inspect": inspect,
    }
    write_json(workdir / "manifest.json", manifest_out)
    notes_path = workdir / "translation-notes.md"
    if not notes_path.exists():
        notes_path.write_text(
            "# Translation notes\n\n> Compact, reusable state. Update after each chunk.\n\n"
            "## Rolling summary\n\n- (fill after chunk 1: where we are, open threads)\n\n"
            "## Glossary (source → target)\n\n| source | target | note |\n|---|---|---|\n|  |  |  |\n\n"
            "## Style\n\n- Narration: \n- Dialogue: \n- Punctuation: \n",
            encoding="utf-8",
        )
    print(json.dumps({"ok": True, "manifest": str(workdir / "manifest.json"), "flow": str(flow_dir / "book.flow.json"), "chunks": str(workdir / "chunks"), "edition": str(workdir / "edition.json")}, ensure_ascii=False, indent=2))
    return 0


def _load_chunk_sources(workdir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    cdir = workdir / "chunks"
    if not cdir.is_dir():
        return out
    for p in sorted(cdir.glob("chunk-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for it in data.get("items", []):
            out[it["id"]] = it.get("source", "")
    return out


def _read_translation_map(workdir: Path) -> dict[str, str]:
    tdir = workdir / "translations"
    mapping: dict[str, str] = {}
    if not tdir.is_dir():
        return mapping
    for p in sorted(tdir.glob("chunk-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in data.get("translations", []):
            tid = row.get("id")
            tr = row.get("translation")
            if tr is None:
                continue
            if not tid:
                continue
            if tid in mapping:
                raise EpubTranslatorError(f"duplicate translation id across files: {tid}")
            mapping[tid] = tr if isinstance(tr, str) else ""
    return mapping


def cmd_status(args) -> int:
    workdir = Path(args.workdir)
    manifest = read_json(workdir / "manifest.json")
    sources = _load_chunk_sources(workdir)
    tmap = _read_translation_map(workdir)
    total = len(sources)
    done = sum(1 for k in sources if k in tmap and tmap[k] != "")
    cdir = workdir / "chunks"
    last_done = None
    seam = ""
    if cdir.is_dir():
        for p in sorted(cdir.glob("chunk-*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            items = data.get("items", [])
            if not items:
                continue
            if all(it["id"] in tmap for it in items):
                last_done = data.get("chunk_index")
                tail_parts = []
                chars = 0
                for it in reversed(items):
                    tr = tmap.get(it["id"], "")
                    if not tr:
                        continue
                    tail_parts.append(tr)
                    chars += len(tr)
                    if chars >= SEAM_TAIL_CHARS:
                        break
                seam = " ".join(reversed(tail_parts))[-SEAM_TAIL_CHARS:]
    nxt = None
    if cdir.is_dir():
        for p in sorted(cdir.glob("chunk-*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            items = data.get("items", [])
            if any(it["id"] not in tmap for it in items):
                nxt = data.get("chunk_index")
                break
    result = {
        "total_items": total,
        "translated_items": done,
        "remaining": total - done,
        "last_finished_chunk": last_done,
        "next_chunk": nxt,
        "seam_tail": seam,
        "manifest": manifest.get("generated_at"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_record_image(args) -> int:
    workdir = Path(args.workdir)
    jobs_path = workdir / "image-jobs.json"
    data = read_json(jobs_path)
    jobs = data.get("jobs", [])
    job = next((j for j in jobs if j["id"] == args.image_id), None)
    if job is None:
        raise EpubTranslatorError(f"unknown image job id: {args.image_id}")
    review_dir = workdir / "images" / "replacements"
    review_dir.mkdir(parents=True, exist_ok=True)
    if args.skip_no_text:
        src = workdir / job["source_export"]
        if not src.is_file():
            raise EpubTranslatorError(f"source export missing: {src}")
        dest = review_dir / src.name
        shutil.copy2(src, dest)
        job["status"] = "skipped_no_text"
        job["replacement_export"] = str(dest.relative_to(workdir))
        job["resolved_at"] = utc_now()
    else:
        if not args.replacement:
            raise EpubTranslatorError("--replacement is required unless --skip-no-text is set")
        rep = Path(args.replacement)
        if not rep.is_file():
            raise EpubTranslatorError(f"replacement not found: {rep}")
        dest = review_dir / f"{job['id']}{rep.suffix or '.png'}"
        shutil.copy2(rep, dest)
        job["status"] = "edited"
        job["replacement_export"] = str(dest.relative_to(workdir))
        job["sha256_after"] = sha256_bytes(dest.read_bytes())
        job["resolved_at"] = utc_now()
    write_json(jobs_path, data)
    print(json.dumps({"ok": True, "job": job}, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Build helpers (ElementTree structural generation over the node tree)

CANONICAL_CSS = """\
/* generated target-edition stylesheet — horizontal, responsive */
html, body { writing-mode: horizontal-tb; direction: ltr; margin: 0; padding: 0; }
body { font-family: serif; line-height: 1.8; max-width: 40em; margin: 0 auto; padding: 1.2em 1em; }
h1, h2, h3, h4, h5, h6 { line-height: 1.35; margin: 1.6em 0 0.6em; font-weight: bold; }
p { margin: 0.9em 0; text-align: justify; hanging-punctuation: allow-end; }
blockquote { margin: 1em 0 1em 1.2em; padding-left: 0.8em; border-left: 2px solid #ccc; color: #333; }
ul, ol { margin: 0.8em 0; padding-left: 1.6em; }
li { margin: 0.4em 0; }
table { border-collapse: collapse; margin: 1em 0; }
td, th { border: 1px solid #ccc; padding: 0.4em 0.6em; }
figure { margin: 1.2em 0; text-align: center; }
figure img { max-width: 100%; height: auto; display: inline-block; }
.separator { text-align: center; margin: 1.6em 0; color: #888; letter-spacing: 0.4em; }
a { color: inherit; text-decoration: underline; text-underline-offset: 0.15em; }
em { font-style: italic; }
strong { font-weight: bold; }
sup, sub { font-size: 0.8em; }
"""


def _clean_text(s: str) -> str:
    s = s.replace(IDEOGRAPHIC_SPACE, " ")
    s = re.sub(r"[ \t\r\n\f\v]+", " ", s).strip()
    s = re.sub(r" ([。．、，.。!?:;)\]」』])", r"\1", s)
    return s


def _append_text(el: ET.Element, text: str) -> None:
    if len(el) == 0:
        el.text = (el.text or "") + text
    else:
        el[-1].tail = (el[-1].tail or "") + text


def _append_inline(el: ET.Element, text: str, inline: list[dict]) -> None:
    text = _clean_text(text)
    if not text:
        return
    if not inline:
        _append_text(el, text)
        return
    parent = el
    for wrap in inline:
        child = ET.SubElement(parent, wrap["tag"])
        if wrap["tag"] == "a":
            child.set("href", wrap.get("href", ""))
        parent = child
    parent.text = (parent.text or "") + text


def _apply_attr_slots(el: ET.Element, slots: list[dict], tmap: dict[str, str]) -> None:
    for s in slots or []:
        tr = tmap.get(s["id"])
        el.set(s["attr"], tr if tr is not None else s["source"])


def _append_token(el: ET.Element, tok: dict, tmap: dict[str, str]) -> None:
    ttype = tok["type"]
    if ttype == "text":
        tmap_text = tmap.get(tok["id"])
        src = tmap_text if tmap_text is not None else tok.get("source", "")
        _append_inline(el, str(src), tok.get("inline", []))
    elif ttype == "image":
        img = ET.SubElement(el, X("img"))
        img.set("src", tok.get("src", ""))
        alt = ""
        if tok.get("alt_id"):
            alt = str(tmap.get(tok["alt_id"]) or tok.get("alt_source", ""))
        else:
            alt = tok.get("alt_source", "")
        img.set("alt", alt)
        _apply_attr_slots(img, tok.get("attr_slots"), tmap)
    elif ttype == "br":
        ET.SubElement(el, X("br"))
    elif ttype == "sep":
        psep = ET.SubElement(el, X("span"))
        psep.set("class", "separator")
        psep.text = "⁂"


def _append_anchors(el: ET.Element, anchors: list[str], *, first_as_id: bool = True) -> None:
    if not anchors:
        return
    rest = anchors[1:] if first_as_id else anchors
    if first_as_id:
        el.set("id", anchors[0])
    for a in rest:
        sp = ET.SubElement(el, X("span"))
        sp.set("id", a)


def render_node(node: dict, parent_el: ET.Element, blocks_by_id: dict[str, dict], tmap: dict[str, str], edition: dict) -> None:
    kind = node["kind"]
    anchors = node.get("anchors", [])
    attr_slots = node.get("attr_slots", [])

    if kind == "section":
        if not anchors and not attr_slots:
            for c in node.get("children", []):
                render_node(blocks_by_id[c], parent_el, blocks_by_id, tmap, edition)
            return
        el = ET.SubElement(parent_el, X("section"))
        _append_anchors(el, anchors)
        _apply_attr_slots(el, attr_slots, tmap)
        for c in node.get("children", []):
            render_node(blocks_by_id[c], el, blocks_by_id, tmap, edition)
        return
    if kind == "anchor_only":
        for a in anchors:
            sp = ET.Element(X("span"))
            sp.set("id", a)
            parent_el.append(sp)
        return
    if kind == "separator":
        el = ET.SubElement(parent_el, X("p"))
        el.set("class", "separator")
        el.text = "⁂"
        _append_anchors(el, anchors)
        return
    if kind == "image":
        if not node.get("tokens"):
            return
        tok = node["tokens"][0]
        el = ET.SubElement(parent_el, X("img"))
        el.set("src", tok.get("src", ""))
        alt = ""
        if tok.get("alt_id"):
            alt = str(tmap.get(tok["alt_id"]) or tok.get("alt_source", ""))
        else:
            alt = tok.get("alt_source", "")
        el.set("alt", alt)
        _apply_attr_slots(el, tok.get("attr_slots"), tmap)
        if anchors:
            el.set("id", anchors[0])
        return

    # tagged nodes
    if kind == "list":
        el = ET.SubElement(parent_el, X("ol" if node.get("ordered") else "ul"))
    elif kind == "table":
        el = ET.SubElement(parent_el, X("table"))
    elif kind == "table_row":
        el = ET.SubElement(parent_el, X("tr"))
    elif kind == "figure":
        el = ET.SubElement(parent_el, X("figure"))
    elif kind == "heading":
        el = ET.SubElement(parent_el, X(f"h{node.get('level', 1)}"))
    elif kind == "paragraph":
        el = ET.SubElement(parent_el, X("p"))
    elif kind == "list_item":
        el = ET.SubElement(parent_el, X("li"))
    elif kind == "table_cell":
        el = ET.SubElement(parent_el, X("th" if node.get("header") else "td"))
    elif kind == "figcaption":
        el = ET.SubElement(parent_el, X("figcaption"))
    elif kind in ("blockquote", "aside"):
        el = ET.SubElement(parent_el, X(kind))
    else:
        el = ET.SubElement(parent_el, X("p"))

    _append_anchors(el, anchors)
    _apply_attr_slots(el, attr_slots, tmap)

    children = node.get("children", [])
    if kind == "table":
        tbody = ET.SubElement(el, X("tbody"))
        for c in children:
            render_node(blocks_by_id[c], tbody, blocks_by_id, tmap, edition)
        return
    if children:
        if kind in ("blockquote", "aside"):
            # blockquote/aside containers render their block children directly
            for c in children:
                render_node(blocks_by_id[c], el, blocks_by_id, tmap, edition)
        else:
            for c in children:
                render_node(blocks_by_id[c], el, blocks_by_id, tmap, edition)
        return
    # leaf: tokens go into the element (blockquote/aside leaves need an inner <p>)
    container = el
    if kind in ("blockquote", "aside"):
        inner = ET.SubElement(el, X("p"))
        container = inner
    for tok in node.get("tokens", []):
        _append_token(container, tok, tmap)


def node_heading_text(node: dict, tmap: dict[str, str]) -> str:
    for tok in node.get("tokens", []):
        if tok["type"] == "text":
            tr = tmap.get(tok["id"])
            if tr:
                return str(tr)
            return str(tok.get("source", ""))
    return node.get("text", "")


def render_document(doc_href: str, roots: list[str], blocks_by_id: dict[str, dict], tmap: dict[str, str], edition: dict) -> ET.Element:
    lang = edition.get("language_tag") or "ko"
    html = ET.Element(X("html"))
    html.set("lang", lang)
    html.set("xml:lang", lang)
    head = ET.SubElement(html, X("head"))
    title = ET.SubElement(head, X("title"))
    title_node = next((blocks_by_id[r] for r in roots if blocks_by_id[r]["kind"] == "heading" and blocks_by_id[r].get("level") == 1), None)
    title.text = node_heading_text(title_node, tmap) if title_node else doc_href
    link = ET.SubElement(head, X("link"))
    link.set("rel", "stylesheet")
    link.set("type", "text/css")
    css_rel = posixpath.relpath(CSS_HREF, posixpath.dirname(doc_href)) if posixpath.dirname(doc_href) else CSS_HREF
    link.set("href", css_rel)
    body = ET.SubElement(html, X("body"))
    for r in roots:
        render_node(blocks_by_id[r], body, blocks_by_id, tmap, edition)
    return html


def build_nav_xhtml(headings: list[dict], edition: dict) -> ET.Element:
    lang = edition.get("language_tag") or "ko"
    html = ET.Element(X("html"))
    html.set("lang", lang)
    html.set("xml:lang", lang)
    head = ET.SubElement(html, X("head"))
    t = ET.SubElement(head, X("title"))
    t.text = "Table of Contents"
    link = ET.SubElement(head, X("link"))
    link.set("rel", "stylesheet")
    link.set("type", "text/css")
    link.set("href", posixpath.relpath(CSS_HREF, posixpath.dirname(NAV_HREF)))
    body = ET.SubElement(html, X("body"))
    nav = ET.SubElement(body, X("nav"))
    nav.set(f"{{{EPUB_NS}}}type", "toc")
    nav.set("id", "toc")
    h1 = ET.SubElement(nav, X("h1"))
    h1.text = "Contents"
    ol = ET.SubElement(nav, X("ol"))
    if headings:
        for h in headings:
            li = ET.SubElement(ol, X("li"))
            a = ET.SubElement(li, X("a"))
            a.set("href", h["href"])
            a.text = h["text"] or "Section"
    else:
        li = ET.SubElement(ol, X("li"))
        a = ET.SubElement(li, X("a"))
        a.set("href", "#")
        a.text = "Start"
    return html


def build_opf(title_out: str, creator_out: str, lang_out: str, ppd: str, manifest_items_out: list[dict], spine_idrefs: list[str]) -> ET.Element:
    pkg = ET.Element(f"{{{OPF_NS}}}package")
    pkg.set("version", "3.0")
    pkg.set("unique-identifier", "bookid")
    pkg.set("xml:lang", lang_out)
    pkg.set("lang", lang_out)
    metadata = ET.SubElement(pkg, f"{{{OPF_NS}}}metadata")
    ident = ET.SubElement(metadata, f"{{{DC_NS}}}identifier")
    ident.set("id", "bookid")
    ident.text = f"urn:uuid:generated-{hashlib.md5(title_out.encode()).hexdigest()[:8]}"
    title = ET.SubElement(metadata, f"{{{DC_NS}}}title")
    title.text = title_out
    if creator_out:
        cr = ET.SubElement(metadata, f"{{{DC_NS}}}creator")
        cr.text = creator_out
    lang = ET.SubElement(metadata, f"{{{DC_NS}}}language")
    lang.text = lang_out
    mod = ET.SubElement(metadata, f"{{{OPF_NS}}}meta")
    mod.set("property", "dcterms:modified")
    mod.text = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = ET.SubElement(pkg, f"{{{OPF_NS}}}manifest")
    for it in manifest_items_out:
        item = ET.SubElement(manifest, f"{{{OPF_NS}}}item")
        item.set("id", it["id"])
        item.set("href", it["href"])
        item.set("media-type", it["media_type"])
        if it.get("properties"):
            item.set("properties", it["properties"])
    spine = ET.SubElement(pkg, f"{{{OPF_NS}}}spine")
    spine.set("page-progression-direction", ppd)
    for idref in spine_idrefs:
        ir = ET.SubElement(spine, f"{{{OPF_NS}}}itemref")
        ir.set("idref", idref)
    return pkg


def resolve_target(href: str, doc_href: str) -> tuple[str, str] | None:
    """Resolve an <a href> to (target_doc, fragment) or None for external links."""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", href):
        return None
    path, _, frag = href.partition("#")
    if not path:
        target_doc = doc_href
    else:
        target_doc = posixpath.normpath(posixpath.join(posixpath.dirname(doc_href), path))
    return target_doc, frag


def cmd_build(args) -> int:
    workdir = Path(args.workdir)
    output = Path(args.output)
    flow = read_json(workdir / "flow" / "book.flow.json")
    edition = read_json(workdir / "edition.json") if (workdir / "edition.json").is_file() else {}
    manifest = read_json(workdir / "manifest.json")
    sources = _load_chunk_sources(workdir)
    tmap = _read_translation_map(workdir)

    # edition schema
    errors = validate_edition(edition)
    if errors:
        raise EpubTranslatorError("; ".join(errors))

    # completeness
    missing = [sid for sid in sources if sid not in tmap]
    if missing:
        report = {
            "ok": False,
            "generated_at": utc_now(),
            "missing_translations": sorted(missing)[:200],
            "missing_count": len(missing),
            "reason": "One or more translation rows are missing. Copy every id from chunks into translations.",
        }
        write_json(workdir / "build-report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        raise EpubTranslatorError(f"build failed: {len(missing)} missing translations (e.g. {missing[:3]})")

    # image jobs must be resolved before building a publishable EPUB
    jobs_data = read_json(workdir / "image-jobs.json") if (workdir / "image-jobs.json").is_file() else {"jobs": []}
    pending = [j["id"] for j in jobs_data.get("jobs", []) if j.get("status") in (None, "pending_review")]
    if pending:
        raise EpubTranslatorError(f"build failed: unresolved image job(s): {pending} — resolve each with record-image before building")

    empty_suspect = [sid for sid, src in sources.items() if src.strip() and not (tmap.get(sid, "").strip())]
    untranslated = [sid for sid, src in sources.items() if src.strip() and tmap.get(sid, "").strip() == src.strip()]

    # terminology divergence: same normalized source -> multiple translations
    by_source: dict[str, set[str]] = defaultdict(set)
    source_to_ids: dict[str, list[str]] = defaultdict(list)
    for sid, src in sources.items():
        tr = (tmap.get(sid, "") or "").strip()
        if not src.strip() or not tr:
            continue
        key = normalize_spaces(normalize_text(src))
        by_source[key].add(tr)
        source_to_ids[key].append(sid)
    divergences = []
    for src_norm, trs in by_source.items():
        if len(trs) > 1 and len(source_to_ids[src_norm]) > 1:
            divergences.append({"source": src_norm, "translations": sorted(trs), "ids": sorted(source_to_ids[src_norm])[:10], "occurrences": len(source_to_ids[src_norm])})

    # link graph validation — anchors come from the same node tree that renders
    doc_hrefs = {d["href"] for d in flow.get("documents", [])}
    anchors_by_doc: dict[str, set[str]] = defaultdict(set)
    for b in flow.get("blocks", []):
        for a in b.get("anchors", []):
            anchors_by_doc[b.get("href", "")].add(a)
    broken_links = []
    for b in flow.get("blocks", []):
        for tok in b.get("tokens", []):
            if tok["type"] != "text":
                continue
            for inline in tok.get("inline", []):
                href = inline.get("href", "")
                if not href:
                    continue
                target = resolve_target(href, b.get("href", ""))
                if target is None:
                    continue
                target_doc, frag = target
                if target_doc not in doc_hrefs:
                    broken_links.append({"slot": tok["id"], "href": href, "block": b["id"], "reason": f"missing document {target_doc}"})
                elif frag and frag not in anchors_by_doc[target_doc]:
                    broken_links.append({"slot": tok["id"], "href": href, "block": b["id"], "reason": f"missing fragment #{frag} in {target_doc}"})

    report = {
        "ok": True,
        "generated_at": utc_now(),
        "total_items": len(sources),
        "untranslated_candidates": sorted(untranslated)[:200],
        "untranslated_count": len(untranslated),
        "empty_translations": sorted(empty_suspect)[:50],
        "divergences": divergences[:50],
        "divergence_count": len(divergences),
        "broken_links": broken_links[:100],
        "broken_link_count": len(broken_links),
        "flow_stats": flow.get("stats", {}),
        "missing_translations": [],
    }
    if broken_links:
        report["ok"] = False
        report["reason"] = f"{len(broken_links)} internal link(s) point to missing anchors"
        write_json(workdir / "build-report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        raise EpubTranslatorError(f"build failed: broken internal links: {broken_links[:3]}")

    # never overwrite the source EPUB
    src_abs = Path(manifest.get("epub", "")).resolve() if manifest.get("epub") else None
    if src_abs and output.resolve() == src_abs:
        raise EpubTranslatorError(f"build failed: output path must differ from the source EPUB ({output})")

    # --- generate new EPUB ---
    build_dir = workdir / "build_epub"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    opf_dir = build_dir / "OEBPS"

    ordered_hrefs: list[str] = [d["href"] for d in flow.get("documents", []) if d.get("href")]
    rendered_hrefs = [h for h in ordered_hrefs if h != NAV_HREF]
    blocks_by_id = {b["id"]: b for b in flow["blocks"]}

    manifest_items_out: list[dict] = []
    spine_idrefs: list[str] = []
    for idx, href in enumerate(rendered_hrefs):
        try:
            out_path = safe_join(opf_dir, href)
        except EpubTranslatorError as exc:
            raise EpubTranslatorError(f"build failed: unsafe document href {href!r} ({exc})") from exc
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = next((d for d in flow.get("documents", []) if d["href"] == href), None)
        roots = doc.get("roots", []) if doc else []
        root = render_document(href, roots, blocks_by_id, tmap, edition)
        write_xml(out_path, ET.ElementTree(root), XHTML_NS)
        item_id = f"doc{idx + 1:04d}"
        manifest_items_out.append({"id": item_id, "href": href, "media_type": "application/xhtml+xml"})
        spine_idrefs.append(item_id)

    # nav — regenerate from translated headings (never a stale source TOC)
    headings = []
    for href in rendered_hrefs:
        doc = next((d for d in flow.get("documents", []) if d["href"] == href), None)
        for rid in (doc.get("roots", []) if doc else []):
            stack = [blocks_by_id[rid]]
            while stack:
                node = stack.pop()
                if node["kind"] == "heading":
                    headings.append({"href": href, "text": node_heading_text(node, tmap), "level": node.get("level", 1)})
                for c in node.get("children", []):
                    stack.append(blocks_by_id[c])
    nav_root = build_nav_xhtml(headings, edition)
    nav_path = safe_join(opf_dir, NAV_HREF)
    nav_path.parent.mkdir(parents=True, exist_ok=True)
    write_xml(nav_path, ET.ElementTree(nav_root), XHTML_NS)
    manifest_items_out.append({"id": "nav", "href": NAV_HREF, "media_type": "application/xhtml+xml", "properties": "nav"})

    css_path = safe_join(opf_dir, CSS_HREF)
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text(CANONICAL_CSS, encoding="utf-8")
    manifest_items_out.append({"id": "css", "href": CSS_HREF, "media_type": "text/css"})

    for job in jobs_data.get("jobs", []):
        src_rel = job.get("replacement_export") if job.get("status") in ("edited", "skipped_no_text") else job.get("source_export")
        if not src_rel:
            continue
        src_path = workdir / src_rel
        if not src_path.is_file():
            continue
        dest_rel = job.get("href", f"image/{src_path.name}")
        try:
            dest_path = safe_join(opf_dir, dest_rel)
        except EpubTranslatorError as exc:
            raise EpubTranslatorError(f"build failed: unsafe image href {dest_rel!r} ({exc})") from exc
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        mt = job.get("media_type", "image/jpeg")
        manifest_items_out.append({"id": job.get("manifest_id") or job["id"], "href": dest_rel, "media_type": mt})

    # OPF + container
    src_title = manifest.get("inspect", {}).get("title") or ""
    src_creator = manifest.get("inspect", {}).get("creator") or ""
    title_tr = next((tmap[sid] for sid, src in sources.items() if sid.startswith("m") and src == src_title), None)
    creator_tr = next((tmap[sid] for sid, src in sources.items() if sid.startswith("m") and src == src_creator), None)
    title_out = title_tr or src_title or "Untitled"
    creator_out = creator_tr or src_creator or ""
    lang_out = edition.get("language_tag") or "ko"
    ppd = edition.get("page_progression_direction") or "ltr"
    opf_root_el = build_opf(title_out, creator_out, lang_out, ppd, manifest_items_out, spine_idrefs)
    opf_path = opf_dir / "content.opf"
    write_xml(opf_path, ET.ElementTree(opf_root_el), OPF_NS)

    meta_inf = build_dir / "META-INF"
    meta_inf.mkdir(parents=True, exist_ok=True)
    (meta_inf / "container.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>\n",
        encoding="utf-8",
    )

    report["spine_hrefs"] = ordered_hrefs
    report["image_jobs"] = len(jobs_data.get("jobs", []))
    write_json(workdir / "build-report.json", report)

    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for root, dirs, files in os.walk(build_dir):
            dirs.sort()
            files.sort()
            for fname in files:
                fpath = Path(root) / fname
                arc = fpath.relative_to(build_dir).as_posix()
                if arc == "mimetype":
                    continue
                z.write(fpath, arc, compress_type=zipfile.ZIP_DEFLATED)
    print(json.dumps({"ok": True, "output": str(output), "report": str(workdir / "build-report.json")}, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args) -> int:
    workdir = Path(args.workdir) if args.workdir else None
    output = Path(args.output) if args.output else None
    issues: list[str] = []
    if output and output.is_file():
        try:
            with zipfile.ZipFile(output) as z:
                names = z.namelist()
                if not names or names[0] != "mimetype":
                    issues.append("mimetype must be first entry")
                else:
                    info = z.getinfo("mimetype")
                    if info.compress_type != zipfile.ZIP_STORED:
                        issues.append("mimetype must be uncompressed")
                    if z.read("mimetype") != b"application/epub+zip":
                        issues.append("mimetype content mismatch")
                if "META-INF/container.xml" not in names:
                    issues.append("container.xml missing")
                if "OEBPS/content.opf" not in names:
                    issues.append("OEBPS/content.opf missing")
                for name in names:
                    if name.endswith(".xhtml"):
                        try:
                            with z.open(name) as f:
                                ET.parse(f)
                        except ET.ParseError as exc:
                            issues.append(f"invalid XHTML {name}: {exc}")
                            break
        except zipfile.BadZipFile as exc:
            issues.append(f"not a valid zip: {exc}")
    elif output:
        issues.append(f"output not found: {output}")

    build_report = None
    if workdir and (workdir / "build-report.json").is_file():
        build_report = json.loads((workdir / "build-report.json").read_text(encoding="utf-8"))

    ok = not issues and (build_report is None or build_report.get("ok", True))
    result = {
        "ok": ok,
        "issues": issues,
        "build_report": build_report,
        "output": str(output) if output else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="epub_translate.py")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("inspect", help="Summarize a source EPUB")
    a.add_argument("--epub", required=True)
    a.add_argument("--json", action="store_true")

    b = sub.add_parser("ingest", help="Extract flow IR and write translation chunks")
    b.add_argument("--epub", required=True)
    b.add_argument("--workdir", required=True)
    b.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    b.add_argument("--soft-min", type=int, default=DEFAULT_SOFT_MIN)

    c = sub.add_parser("status", help="Progress plus seam tail")
    c.add_argument("--workdir", required=True)

    d = sub.add_parser("record-image", help="Resolve one image job")
    d.add_argument("--workdir", required=True)
    d.add_argument("--image-id", required=True)
    d.add_argument("--replacement", default=None)
    d.add_argument("--skip-no-text", action="store_true")

    e = sub.add_parser("build", help="Generate a brand-new target EPUB")
    e.add_argument("--workdir", required=True)
    e.add_argument("--output", required=True)

    f = sub.add_parser("validate", help="Light package check")
    f.add_argument("--workdir", required=True)
    f.add_argument("--output", required=True)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            return cmd_inspect(args)
        if args.command == "ingest":
            return cmd_ingest(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "record-image":
            return cmd_record_image(args)
        if args.command == "build":
            return cmd_build(args)
        if args.command == "validate":
            return cmd_validate(args)
        raise EpubTranslatorError(f"unknown command: {args.command}")
    except EpubTranslatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())