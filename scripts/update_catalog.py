# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6,<7"]
# ///
"""Refresh only the marked skill lists in both root READMEs."""

from pathlib import Path
import argparse
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- skills:start -->"
END = "<!-- skills:end -->"


def metadata(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError(f"Missing skill frontmatter: {path.relative_to(ROOT)}")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict):
        raise ValueError(f"Invalid skill frontmatter: {path.relative_to(ROOT)}")
    for field in ("name", "description"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"Missing {field}: {path.relative_to(ROOT)}")
    if data["name"] != path.parent.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", data["name"]):
        raise ValueError(f"Skill name must match its lowercase folder name: {path.relative_to(ROOT)}")
    return data


def summary(guide: Path, fallback: str) -> str:
    if guide.exists():
        # The first paragraph after the title is also the catalog description.
        match = re.search(r"^# [^\n]+\n\s*\n([^\n]+(?:\n[^\n]+)*)", guide.read_text(encoding="utf-8"), re.M)
        if match:
            return " ".join(match[1].split())
    return " ".join(fallback.split())


def catalog(skills: list[tuple[Path, dict]], korean: bool) -> str:
    entries = []
    for path, data in skills:
        name = data["name"]
        source = path.relative_to(ROOT).as_posix()
        guide = ROOT / "docs" / "skills" / f"{name}{'.ko' if korean else ''}.md"
        links = [("지침" if korean else "Instructions", source)]
        if guide.exists():
            links.insert(0, ("사용 가이드" if korean else "Guide", guide.relative_to(ROOT).as_posix()))
        install = guide.relative_to(ROOT).as_posix() + "#install" if guide.exists() else "#install"
        links.append(("설치" if korean else "Install", install))
        description = summary(guide, data["description"])
        entries.append(f"### {name}\n\n{description}\n\n" + " · ".join(f"[{label}]({url})" for label, url in links))
    return "\n\n".join(entries) or ("아직 등록된 스킬이 없습니다." if korean else "No skills are listed yet.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report stale catalogs without changing files")
    args = parser.parse_args()
    try:
        skills = [(path, metadata(path)) for path in sorted((ROOT / "skills").glob("*/SKILL.md"))]
        updates = []
        for filename, korean in (("README.md", False), ("README.ko.md", True)):
            path = ROOT / filename
            old = path.read_text(encoding="utf-8")
            if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
                raise ValueError(f"Expected one ordered catalog marker pair in {filename}")
            before, rest = old.split(START, 1)
            _, after = rest.split(END, 1)
            new = before + START + "\n\n" + catalog(skills, korean) + "\n\n" + END + after
            if old != new:
                updates.append((path, new))
        # Prepare both languages before writing so malformed input changes neither.
        if args.check:
            for path, _ in updates:
                print(f"Stale catalog: {path.name}", file=sys.stderr)
            if updates:
                return 1
        else:
            for path, new in updates:
                path.write_text(new, encoding="utf-8")
                print(f"Updated {path.name}")
        print(f"Catalogs cover {len(skills)} skills.")
        return 0
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Catalog error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
