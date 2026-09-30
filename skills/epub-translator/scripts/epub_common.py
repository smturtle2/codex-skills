"""Shared EPUB data and path contracts; no translation or publication policy."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import posixpath
import re
import zipfile
import os
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
FLOW_SCHEMA_VERSION = 3
TEXT_SCHEMA_VERSION = 4
NAV_HREF = "xhtml/nav.xhtml"
CSS_HREF = "style/target.css"
EDITABLE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
IMAGE_SUFFIX_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}


class EpubTranslatorError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EpubTranslatorError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EpubTranslatorError(f"JSON must be an object: {path}")
    return value


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".epub-state-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def X(tag: str) -> str:
    return f"{{{XHTML_NS}}}{tag}"


def attr_value(el: ET.Element, name: str) -> str | None:
    return next((v for k, v in el.attrib.items() if local_name(k) == name), None)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_join(base: Path, internal: str) -> Path:
    base = base.resolve()
    result = (base / internal).resolve()
    try:
        result.relative_to(base)
    except ValueError as exc:
        raise EpubTranslatorError(f"unsafe EPUB path: {internal}") from exc
    return result


def parse_xml(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise EpubTranslatorError(f"could not parse XML {path}: {exc}") from exc


def write_xml(path: Path, root: ET.Element, ns: str) -> None:
    ET.register_namespace("", ns)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("epub", EPUB_NS)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def package_data(unpacked: Path) -> tuple[str, ET.Element, list[dict], list[str]]:
    container = parse_xml(unpacked / "META-INF/container.xml").getroot()
    rootfile_el = container.find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile_el is None or not rootfile_el.get("full-path"):
        raise EpubTranslatorError("META-INF/container.xml has no rootfile")
    rootfile = rootfile_el.get("full-path", "")
    opf = parse_xml(safe_join(unpacked, rootfile)).getroot()
    manifest = opf.find(f"{{{OPF_NS}}}manifest")
    if manifest is None:
        raise EpubTranslatorError("OPF manifest missing")
    items = [{"id": el.get("id", ""), "href": el.get("href", ""),
              "media_type": el.get("media-type", ""), "properties": el.get("properties", "")}
             for el in manifest.findall(f"{{{OPF_NS}}}item")]
    spine = opf.find(f"{{{OPF_NS}}}spine")
    ids = [el.get("idref", "") for el in spine] if spine is not None else []
    by_id = {item["id"]: item for item in items}
    hrefs = [by_id[i]["href"] for i in ids if i in by_id]
    if not hrefs:
        hrefs = [item["href"] for item in items if item["media_type"] == "application/xhtml+xml"]
    return rootfile, opf, items, hrefs


def archive_path(rootfile: str, href: str) -> str:
    return canonical_archive_path(rootfile, unquote(urlsplit(href).path))


def canonical_archive_path(rootfile: str, path: str) -> str:
    """Join already-decoded paths; never decode a filesystem path twice."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(rootfile), path))


def uri_path(path: str, fragment: str | None = None) -> str:
    result = quote(path, safe="/")
    return result + ("#" + quote(fragment, safe="") if fragment else "")


def resolve_reference(href: str, document: str) -> tuple[str, str] | None:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(parts.path))) if parts.path else document
    return target, unquote(parts.fragment)


def safe_extract(epub: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(epub) as archive:
            for info in archive.infolist():
                target = safe_join(destination, info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
    except (OSError, zipfile.BadZipFile) as exc:
        raise EpubTranslatorError(f"could not extract EPUB: {exc}") from exc
