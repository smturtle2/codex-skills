#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime


IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy the newest generated image to a requested destination.",
    )
    parser.add_argument(
        "--since",
        required=True,
        type=float,
        help="Only consider images with mtime at or after this epoch timestamp.",
    )
    parser.add_argument(
        "--destination",
        help="Target file or directory. Defaults to the project root.",
    )
    parser.add_argument(
        "--project-root",
        help="Project root used when --destination is omitted.",
    )
    parser.add_argument(
        "--generated-root",
        action="append",
        help="Directory to search for generated images. May be passed multiple times.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination file.",
    )
    return parser.parse_args(argv)


def default_generated_roots() -> list[pathlib.Path]:
    roots: list[pathlib.Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        home = pathlib.Path(codex_home).expanduser()
        roots.extend([home / "generated_images", home])

    user_home = pathlib.Path.home() / ".codex"
    roots.extend([user_home / "generated_images", user_home])

    deduped: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            deduped.append(root)
            seen.add(resolved)
    return deduped


def project_root(explicit_root: str | None) -> pathlib.Path:
    if explicit_root:
        return pathlib.Path(explicit_root).expanduser().resolve()

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return pathlib.Path(result.stdout.strip()).resolve()
    return pathlib.Path.cwd().resolve()


def iter_images(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.exists():
        return []

    images: list[pathlib.Path] = []
    try:
        paths = root.rglob("*")
        for path in paths:
            try:
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                    images.append(path)
            except OSError:
                continue
    except OSError:
        return []
    return images


def newest_image(roots: list[pathlib.Path], since: float) -> pathlib.Path:
    candidates: list[tuple[int, pathlib.Path]] = []
    for root in roots:
        for path in iter_images(root.expanduser()):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime >= since:
                candidates.append((stat.st_mtime_ns, path))

    if not candidates:
        searched = ", ".join(str(root.expanduser()) for root in roots)
        raise FileNotFoundError(
            f"No generated image found at or after {since} in: {searched}",
        )

    candidates.sort(key=lambda item: (item[0], str(item[1])))
    return candidates[-1][1]


def default_filename(source: pathlib.Path) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = source.suffix.lower() or ".png"
    return f"image-creator-{stamp}{suffix}"


def resolve_destination(
    destination: str | None,
    root: pathlib.Path,
    source: pathlib.Path,
) -> pathlib.Path:
    if not destination:
        return root / default_filename(source)

    raw_destination = destination
    path = pathlib.Path(destination).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    is_directory = (
        raw_destination.endswith((os.sep, "/"))
        or path.exists()
        and path.is_dir()
        or not path.suffix
    )
    if is_directory:
        return path / default_filename(source)
    return path


def unique_path(path: pathlib.Path) -> pathlib.Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def copy_image(source: pathlib.Path, destination: pathlib.Path, overwrite: bool) -> pathlib.Path:
    final_path = destination if overwrite else unique_path(destination)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, final_path)
    return final_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    roots = (
        [pathlib.Path(root).expanduser() for root in args.generated_root]
        if args.generated_root
        else default_generated_roots()
    )

    try:
        source = newest_image(roots, args.since)
        destination = resolve_destination(
            args.destination,
            project_root(args.project_root),
            source,
        )
        saved = copy_image(source, destination, args.overwrite)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
