#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


DEFAULT_MATTE = "#00B7FF"
DEFAULT_MODEL = "birefnet-general-lite"
MATTE_CLEAR_DISTANCE = 24
MATTE_FADE_DISTANCE = 72


class SaveGeneratedImageError(Exception):
    pass


def matte_color(raw: str) -> str:
    value = raw.upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", value):
        raise argparse.ArgumentTypeError("matte must use #RRGGBB format")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy or post-process an image_gen output file.")
    parser.add_argument("--source", required=True, help="File path returned by image_gen.")
    parser.add_argument("--destination", required=True, help="Exact output file path.")
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="Remove the generated matte background.",
    )
    parser.add_argument(
        "--matte",
        type=matte_color,
        default=DEFAULT_MATTE,
        help="Generated matte color in #RRGGBB format.",
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


def provider_sets() -> list[tuple[str, list[str]]]:
    override = os.environ.get("IMAGE_CREATOR_REMBG_PROVIDERS")
    if override:
        available = [item.strip() for item in override.split(",") if item.strip()]
    else:
        try:
            import onnxruntime as ort

            available = list(ort.get_available_providers())
        except ImportError:
            available = ["CPUExecutionProvider"]

    if "CUDAExecutionProvider" in available:
        return [("cuda", ["CUDAExecutionProvider", "CPUExecutionProvider"]), ("cpu", ["CPUExecutionProvider"])]
    if "ROCMExecutionProvider" in available:
        return [("rocm", ["ROCMExecutionProvider", "CPUExecutionProvider"]), ("cpu", ["CPUExecutionProvider"])]
    return [("cpu", ["CPUExecutionProvider"])]


def rembg_binary() -> str:
    override = os.environ.get("IMAGE_CREATOR_REMBG_BIN")
    if override:
        candidate = resolved_path(override)
        if not candidate.is_file():
            raise SaveGeneratedImageError(f"IMAGE_CREATOR_REMBG_BIN does not exist: {candidate}")
        return str(candidate)
    command = shutil.which("rembg")
    if not command:
        raise SaveGeneratedImageError("rembg is unavailable; run this helper through its uv project")
    return command


def model_cache() -> pathlib.Path:
    cache_home = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache"))
    return (cache_home / "codex-skills" / "image-creator" / "rembg-models").expanduser().resolve()


def run_rembg(source: pathlib.Path, output: pathlib.Path) -> None:
    cache = model_cache()
    cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["U2NET_HOME"] = str(cache)
    failures: list[str] = []
    for backend, providers in provider_sets():
        output.unlink(missing_ok=True)
        command = [
            rembg_binary(),
            "i",
            "-m",
            DEFAULT_MODEL,
            "-x",
            json.dumps({"providers": providers}),
            "-a",
            str(source),
            str(output),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
        if result.returncode == 0 and output.is_file():
            return
        detail = (result.stderr or result.stdout).strip().splitlines()
        failures.append(f"{backend}: {detail[-1] if detail else f'exit {result.returncode}'}")
    raise SaveGeneratedImageError("rembg failed (" + "; ".join(failures) + ")")


def matte_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def validate_png_source(path: pathlib.Path) -> None:
    if path.suffix.lower() != ".png":
        raise SaveGeneratedImageError("Transparent processing requires a PNG image_gen source file")
    try:
        from PIL import Image

        with Image.open(path) as image:
            if image.format != "PNG":
                raise SaveGeneratedImageError("Transparent processing requires a PNG image_gen source file")
    except ImportError as exc:
        raise SaveGeneratedImageError("Pillow is required for transparent output") from exc
    except OSError as exc:
        raise SaveGeneratedImageError(f"image_gen source is not a readable PNG: {exc}") from exc


def clean_and_validate_alpha(path: pathlib.Path, matte: str) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SaveGeneratedImageError("Pillow is required for transparent output") from exc

    target = matte_rgb(matte)
    try:
        with Image.open(path) as opened:
            if opened.format != "PNG" or "A" not in opened.getbands():
                raise SaveGeneratedImageError("rembg output must be a PNG with an alpha channel")
            image = opened.convert("RGBA")
    except OSError as exc:
        raise SaveGeneratedImageError(f"rembg output is not a readable image: {exc}") from exc

    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            distance = max(abs(red - target[0]), abs(green - target[1]), abs(blue - target[2]))
            if distance <= MATTE_CLEAR_DISTANCE:
                pixels[x, y] = (0, 0, 0, 0)
            elif distance <= MATTE_FADE_DISTANCE:
                fade = (distance - MATTE_CLEAR_DISTANCE) / (MATTE_FADE_DISTANCE - MATTE_CLEAR_DISTANCE)
                pixels[x, y] = (red, green, blue, min(alpha, round(alpha * fade)))

    alpha_min, alpha_max = image.getchannel("A").getextrema()
    if alpha_min == 255:
        raise SaveGeneratedImageError("transparent output contains no transparent pixels")
    if alpha_max == 0:
        raise SaveGeneratedImageError("transparent output contains no visible pixels")
    image.save(path, format="PNG")


def prepare_output(source: pathlib.Path, temp_path: pathlib.Path, transparent: bool, matte: str) -> None:
    if transparent:
        run_rembg(source, temp_path)
        clean_and_validate_alpha(temp_path, matte)
    else:
        shutil.copyfile(source, temp_path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    temp_path: pathlib.Path | None = None
    try:
        source = resolved_path(args.source)
        destination = resolved_path(args.destination)
        if not source.is_file():
            raise SaveGeneratedImageError(f"Source image not found: {source}")
        if args.transparent and destination.suffix.lower() != ".png":
            raise SaveGeneratedImageError("Transparent output destination must use a .png suffix")
        if args.transparent:
            validate_png_source(source)
        if args.overwrite and source == destination:
            raise SaveGeneratedImageError("Destination must not replace the image_gen source file")
        relative_root = validate_destination(destination, args.relative_to)
        destination.parent.mkdir(parents=True, exist_ok=True)

        suffix = ".png" if args.transparent else destination.suffix
        descriptor, raw_temp = tempfile.mkstemp(prefix=".image-creator-", suffix=suffix, dir=destination.parent)
        os.close(descriptor)
        temp_path = pathlib.Path(raw_temp)
        temp_path.unlink()
        prepare_output(source, temp_path, args.transparent, args.matte)
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
                    "transparent": bool(args.transparent),
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
