"""Source-package inspection and one canonical ledger for resource publication."""
from __future__ import annotations

import posixpath
import shutil
import tempfile
from pathlib import Path
from epub_common import (DC_NS, EDITABLE_IMAGE_TYPES, EpubTranslatorError, IMAGE_SUFFIX_BY_TYPE, OPF_NS, archive_path,
                         local_name, package_data, parse_xml, read_json, resolve_reference, safe_extract, safe_join,
                         sha256_bytes, uri_path, utc_now, write_json)


def image_media_type(path: Path) -> str:
    from PIL import Image
    try:
        with Image.open(path) as image:
            image.load()
            media = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}.get(image.format)
        if not media:
            raise EpubTranslatorError(f"unsupported replacement image format: {path}")
        return media
    except (OSError, ValueError) as exc:
        raise EpubTranslatorError(f"unreadable raster image {path}: {exc}") from exc


def inspect_epub(epub: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="epub-inspect-") as directory:
        unpacked = Path(directory)
        safe_extract(epub, unpacked)
        rootfile, opf, items, spine_hrefs = package_data(unpacked)
        spine = opf.find(f"{{{OPF_NS}}}spine")
        images = [item for item in items if item["media_type"].startswith("image/")]
        def metadata(field):
            element = opf.find(f".//{{{DC_NS}}}{field}")
            return element.text.strip() if element is not None and element.text else None
        return {"epub": str(epub), "entry_count": sum(1 for p in unpacked.rglob("*") if p.is_file()), "rootfile": rootfile,
                "title": metadata("title"), "creator": metadata("creator"), "language": metadata("language"),
                "spine": {"page_progression_direction": spine.get("page-progression-direction") if spine is not None else None,
                          "idrefs": [el.get("idref", "") for el in spine] if spine is not None else []},
                "counts": {"images": len(images), "editable_images": sum(i["media_type"] in EDITABLE_IMAGE_TYPES for i in images),
                           "unsupported_images": sum(i["media_type"] not in EDITABLE_IMAGE_TYPES for i in images),
                           "xhtml": sum(i["media_type"] == "application/xhtml+xml" for i in items), "css": sum(i["media_type"] == "text/css" for i in items), "manifest_items": len(items)},
                "images": [{"id": i["id"], "href": archive_path(rootfile, i["href"]), "media_type": i["media_type"], "editable": i["media_type"] in EDITABLE_IMAGE_TYPES} for i in images]}


def source_ledger(unpacked: Path, rootfile: str, items: list[dict]) -> dict:
    resources = []
    _, source_opf, _, _ = package_data(unpacked)
    cover_id = next((element.get("content") for element in source_opf.iter() if local_name(element.tag) == "meta" and element.get("name") == "cover"), None)
    for item in items:
        if item["media_type"] in ("application/xhtml+xml", "application/x-dtbncx+xml"):
            continue
        resolved = resolve_reference(item["href"], rootfile)
        if resolved is None:
            raise EpubTranslatorError(f"remote manifest resource needs explicit handling: {item['href']}")
        internal = archive_path(rootfile, item["href"])
        resource = {"id": item["id"], "source_archive_path": internal,
                    "source_opf_path": posixpath.relpath(internal, posixpath.dirname(rootfile) or "."),
                    "source_media_type": item["media_type"], "properties": item["properties"]}
        if item["id"] == cover_id:
            resource["properties"] = " ".join(dict.fromkeys(item["properties"].split() + ["cover-image"]))
        try:
            path = safe_join(unpacked, internal)
            if not path.is_file():
                resource["source_error"] = "missing source resource"
            else:
                resource["source_sha256"] = sha256_bytes(path.read_bytes())
                if item["media_type"] in EDITABLE_IMAGE_TYPES:
                    resource["source_media_type"] = image_media_type(path)
                elif item["media_type"] == "image/svg+xml":
                    if local_name(parse_xml(path).getroot().tag) != "svg":
                        raise EpubTranslatorError(f"SVG resource has no svg root: {internal}")
        except EpubTranslatorError as exc:
            resource["source_error"] = str(exc)
        resources.append(resource)
    return {"schema_version": 1, "rootfile": rootfile, "resources": resources}


def export_resources(unpacked: Path, rootfile: str, items: list[dict], workdir: Path) -> tuple[dict, dict]:
    ledger = source_ledger(unpacked, rootfile, items)
    jobs, unsupported = [], []
    for resource in ledger["resources"]:
        mt = resource["source_media_type"]
        if not mt.startswith("image/"):
            continue
        if mt not in EDITABLE_IMAGE_TYPES or resource.get("source_error"):
            unsupported.append({"id": resource["id"], "href": resource["source_archive_path"], "media_type": mt,
                                **({"missing": True, "source_error": resource["source_error"]} if resource.get("source_error") else {})})
            continue
        job_id = f"img{len(jobs) + 1:04d}"
        destination = workdir / "images/source" / f"{job_id}{IMAGE_SUFFIX_BY_TYPE[mt]}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_join(unpacked, resource["source_archive_path"]), destination)
        jobs.append({"id": job_id, "manifest_id": resource["id"], "href": resource["source_archive_path"], "media_type": mt,
                     "source_export": str(destination.relative_to(workdir)), "status": "pending_review", "sha256": resource["source_sha256"]})
    jobs_data = {"generated_at": utc_now(), "jobs": jobs, "unsupported": unsupported}
    write_json(workdir / "resources.json", ledger)
    write_json(workdir / "image-jobs.json", jobs_data)
    return ledger, jobs_data


def read_ledger(workdir: Path) -> dict:
    path = workdir / "resources.json"
    if path.is_file():
        ledger = read_json(path)
        if ledger.get("schema_version") != 1 or not isinstance(ledger.get("resources"), list):
            raise EpubTranslatorError("unsupported or malformed resource ledger")
        return ledger
    rootfile, _, items, _ = package_data(workdir / "unpacked")
    return source_ledger(workdir / "unpacked", rootfile, items)


def record_image(workdir: Path, image_id: str, replacement: Path | None, skip: bool) -> dict:
    if skip == bool(replacement):
        raise EpubTranslatorError("choose exactly one of --replacement and --skip-no-text")
    data = read_json(workdir / "image-jobs.json")
    job = next((j for j in data.get("jobs", []) if j["id"] == image_id), None)
    if job is None:
        raise EpubTranslatorError(f"unknown image job id: {image_id}")
    source = safe_join(workdir, job["source_export"]) if skip else replacement
    if source is None or not source.is_file():
        raise EpubTranslatorError(f"replacement/source image not found: {source}")
    mt = image_media_type(source)
    if skip and job.get("sha256") != sha256_bytes(source.read_bytes()):
        raise EpubTranslatorError("source export changed; restore the ingested image or record an explicit replacement")
    destination = workdir / "images/replacements" / f"{image_id}{IMAGE_SUFFIX_BY_TYPE[mt]}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    job.update(status="skipped_no_text" if skip else "edited", replacement_export=str(destination.relative_to(workdir)),
               replacement_media_type=mt, sha256_after=sha256_bytes(destination.read_bytes()), resolved_at=utc_now())
    write_json(workdir / "image-jobs.json", data)
    return job


class PublishedResources:
    def __init__(self, workdir: Path, ledger: dict, jobs_data: dict) -> None:
        self.workdir = workdir
        self.rootfile = ledger["rootfile"]
        job_rows = jobs_data.get("jobs", [])
        if not isinstance(job_rows, list) or any(not isinstance(job, dict) for job in job_rows):
            raise EpubTranslatorError("malformed image jobs")
        jobs = {j["manifest_id"]: j for j in job_rows}
        if len(jobs) != len(job_rows) or len({job["id"] for job in job_rows}) != len(job_rows):
            raise EpubTranslatorError("duplicate image jobs")
        editable_ids = {resource["id"] for resource in ledger["resources"] if resource["source_media_type"] in EDITABLE_IMAGE_TYPES and not resource.get("source_error")}
        if set(jobs) != editable_ids:
            raise EpubTranslatorError("image jobs do not match the resource ledger")
        self.rows = []
        self.by_source = {}
        for resource in ledger["resources"]:
            if resource.get("source_error"):
                raise EpubTranslatorError(f"source resource {resource['source_archive_path']}: {resource['source_error']}")
            job = jobs.get(resource["id"])
            original = safe_join(workdir / "unpacked", resource["source_archive_path"])
            if resource.get("source_sha256") and (not original.is_file() or sha256_bytes(original.read_bytes()) != resource["source_sha256"]):
                raise EpubTranslatorError(f"ingested resource changed: {resource['source_archive_path']}; restore it or use an explicit image replacement")
            if job is not None:
                if job.get("status") not in ("edited", "skipped_no_text"):
                    raise EpubTranslatorError(f"build failed: unresolved image job {job['id']}")
                relative = job.get("replacement_export")
                if not relative:
                    raise EpubTranslatorError(f"resolved image job has no replacement: {job['id']}")
                source = safe_join(workdir, relative)
            else:
                source = safe_join(workdir / "unpacked", resource["source_archive_path"])
            if not source.is_file():
                raise EpubTranslatorError(f"selected resource payload missing: {source}")
            if job and job.get("sha256_after") and sha256_bytes(source.read_bytes()) != job["sha256_after"]:
                raise EpubTranslatorError(f"recorded replacement changed: {job['id']}; record the intended replacement again")
            media_type = image_media_type(source) if resource["source_media_type"] in EDITABLE_IMAGE_TYPES else resource["source_media_type"]
            # Keeping source OPF-relative resource URIs preserves references inside
            # unchanged SVG/media payloads. MIME describes actual bytes, not suffix.
            path = resource["source_opf_path"]
            href = uri_path(path)
            safe_join(Path("/epub-output"), resource["source_archive_path"])
            row = {**resource, "selected_payload_path": source, "output_opf_path": path, "output_opf_href": href, "output_media_type": media_type,
                   "output_archive_path": resource["source_archive_path"],
                   "selected_sha256": sha256_bytes(source.read_bytes()), "status": job["status"] if job else "preserved"}
            if path in self.by_source:
                raise EpubTranslatorError(f"duplicate resource URI: {href}")
            self.rows.append(row)
            self.by_source[path] = row

    def resolve_image(self, href: str, document: str) -> str:
        reference = resolve_reference(href, document)
        if reference is None:
            return href
        target, fragment = reference
        resource = self.by_source.get(target)
        if resource is None:
            raise EpubTranslatorError(f"image reference has no resource: {document}: {href}")
        result = posixpath.relpath(resource["output_opf_path"], posixpath.dirname(document) or ".")
        return uri_path(result, fragment)

    def copy_to(self, build_directory: Path) -> list[dict]:
        manifest = []
        for index, row in enumerate(self.rows, 1):
            destination = safe_join(build_directory, row["output_archive_path"])
            if destination.exists():
                raise EpubTranslatorError(f"resource collides with generated file: {row['output_opf_href']}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["selected_payload_path"], destination)
            manifest.append({"id": row["id"], "href": row["output_opf_href"], "media_type": row["output_media_type"],
                             "properties": row["properties"]})
        return manifest
