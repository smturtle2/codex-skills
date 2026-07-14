#!/usr/bin/env python3
"""Build MoruBridge with a Paper server JAR as the compile classpath."""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
BRIDGE_DIR = SKILL_DIR / "assets" / "moru-bridge"


def run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"required command is not installed: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"command failed with exit code {exc.returncode}: {' '.join(command[:2])}") from exc


def contains_bukkit_api(jar_path: pathlib.Path) -> bool:
    result = subprocess.run(["jar", "--list", "--file", str(jar_path)], capture_output=True, text=True, check=False)
    return result.returncode == 0 and "org/bukkit/Bukkit.class" in result.stdout


def find_server_root(path: pathlib.Path) -> pathlib.Path | None:
    for candidate in (path.parent, *path.parents):
        if (candidate / "libraries").is_dir():
            return candidate
    return None


def compile_classpath(paper_jar: pathlib.Path) -> str:
    server_root = find_server_root(paper_jar)
    if contains_bukkit_api(paper_jar) and server_root is None:
        return str(paper_jar)
    if server_root is None:
        raise RuntimeError("Paper bootstrap JAR needs its server libraries/ directory beside it")
    api_jars = [paper_jar] if contains_bukkit_api(paper_jar) else sorted(
        (server_root / "libraries" / "io" / "papermc" / "paper" / "paper-api").glob("*/*.jar")
    )
    if not api_jars:
        raise RuntimeError("could not find paper-api in the server libraries directory")
    library_jars = sorted((server_root / "libraries").rglob("*.jar"))
    return os.pathsep.join(map(str, [*api_jars, *library_jars]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-jar", required=True, type=pathlib.Path, help="the target server's Paper bootstrap or API JAR")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("MoruBridge.jar"))
    parser.add_argument("--java-release", default="25", help="class-file release supported by the target server JVM")
    args = parser.parse_args()

    paper_jar = args.paper_jar.expanduser().resolve()
    output = args.output.expanduser().resolve()
    sources = sorted((BRIDGE_DIR / "src" / "main" / "java").rglob("*.java"))
    resources = BRIDGE_DIR / "src" / "main" / "resources"
    if not paper_jar.is_file():
        parser.error(f"Paper JAR does not exist: {paper_jar}")
    if not sources or not (resources / "plugin.yml").is_file():
        parser.error("bundled MoruBridge source is incomplete")

    with tempfile.TemporaryDirectory(prefix="moru-bridge-") as temp_dir:
        classes = pathlib.Path(temp_dir) / "classes"
        classes.mkdir()
        run(
            [
                "javac",
                "--release",
                args.java_release,
                "-classpath",
                compile_classpath(paper_jar),
                "-d",
                str(classes),
                *map(str, sources),
            ]
        )
        shutil.copytree(resources, classes, dirs_exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        run(["jar", "--create", "--file", str(output), "-C", str(classes), "."])

    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
