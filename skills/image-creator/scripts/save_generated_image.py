#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile


class SaveGeneratedImageError(Exception):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and copy an image_gen output file without modifying it.")
    parser.add_argument("--source", required=True, help="File path returned by image_gen.")
    parser.add_argument("--destination", required=True, help="Exact output file path.")
    parser.add_argument(
        "--require-transparency",
        action="store_true",
        help="Require a PNG with transparent and visible pixels; never remove a background.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing destination file.")
    parser.add_argument("--relative-to", help="With --json, include a POSIX path relative to this root.")
    parser.add_argument("--json", action="store_true", help="Print structured save metadata.")
    args = parser.parse_args(argv)
    if args.relative_to and not args.json:
        parser.error("--relative-to requires --json")
    return args


def resolved_path(raw: str) -> pathlib.Path:
    return pathlib.Path(raw).expanduser().resolve()


def validate_destination(destination: pathlib.Path, relative_to: str | None) -> pathlib.Path | None:
    if not relative_to:
        return None
    root = resolved_path(relative_to)
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise SaveGeneratedImageError(f"Destination is not under --relative-to root: {root}") from exc
    return root


def next_candidate(path: pathlib.Path, index: int) -> pathlib.Path:
    if index == 1:
        return path
    return path.with_name(f"{path.stem}-{index}{path.suffix}")


def publish(temp_path: pathlib.Path, destination: pathlib.Path, overwrite: bool) -> tuple[pathlib.Path, bool]:
    if overwrite:
        overwritten = destination.exists()
        os.replace(temp_path, destination)
        return destination, overwritten

    index = 1
    while True:
        candidate = next_candidate(destination, index)
        try:
            os.link(temp_path, candidate)
        except FileExistsError:
            index += 1
            continue
        temp_path.unlink()
        return candidate, False


def inspect_output(path: pathlib.Path, require_transparency: bool) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SaveGeneratedImageError("Pillow is required; run this helper through its uv project") from exc

    try:
        with Image.open(path) as image:
            metadata = {"format": image.format, "width": image.width, "height": image.height}
            if require_transparency:
                if image.format != "PNG":
                    raise SaveGeneratedImageError("Transparent output requires a PNG image_gen source file")
                # Decode alpha in memory, including PNG palette/tRNS transparency.
                # Never re-encode the source or alter its partially transparent edges.
                alpha_min, alpha_max = image.convert("RGBA").getchannel("A").getextrema()
                if alpha_min == 255:
                    raise SaveGeneratedImageError("Generated PNG contains no transparent pixels")
                if alpha_max == 0:
                    raise SaveGeneratedImageError("Generated PNG contains no visible pixels")
    except OSError as exc:
        raise SaveGeneratedImageError(f"image_gen source is not a readable image: {exc}") from exc
    return metadata


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    temp_path: pathlib.Path | None = None
    try:
        source = resolved_path(args.source)
        destination = resolved_path(args.destination)
        if not source.is_file():
            raise SaveGeneratedImageError(f"Source image not found: {source}")
        if args.require_transparency and destination.suffix.lower() != ".png":
            raise SaveGeneratedImageError("Transparent output destination must use a .png suffix")
        if args.overwrite and source == destination:
            raise SaveGeneratedImageError("Destination must not replace the image_gen source file")
        relative_root = validate_destination(destination, args.relative_to)
        destination.parent.mkdir(parents=True, exist_ok=True)

        suffix = ".png" if args.require_transparency else destination.suffix
        descriptor, raw_temp = tempfile.mkstemp(prefix=".image-creator-", suffix=suffix, dir=destination.parent)
        os.close(descriptor)
        temp_path = pathlib.Path(raw_temp)
        shutil.copyfile(source, temp_path)
        metadata = inspect_output(temp_path, args.require_transparency)
        saved, overwritten = publish(temp_path, destination, args.overwrite)
        temp_path = None
        relative_path = (
            pathlib.PurePosixPath(*saved.relative_to(relative_root).parts).as_posix() if relative_root else None
        )
    except (OSError, SaveGeneratedImageError) as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "overwritten": overwritten,
                    "relative_path": relative_path,
                    "saved_path": str(saved),
                    "suffix": saved.suffix.lower(),
                    "transparency_requested": args.require_transparency,
                    "transparency_verified": True if args.require_transparency else None,
                    **metadata,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
