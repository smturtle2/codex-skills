# /// script
# requires-python = ">=3.11"
# dependencies = ["CairoSVG>=2.8,<3"]
# ///
"""Render full-color skill icons from the SVG sources used by the catalog."""

import argparse
from pathlib import Path

import cairosvg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check PNGs without writing files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stale = []
    sources = sorted((root / "skills").glob("*/assets/icon.svg"))
    for source in sources:
        target = source.with_name("icon-large.png")
        rendered = cairosvg.svg2png(url=str(source), output_width=256, output_height=256)
        if args.check:
            if not target.exists() or target.read_bytes() != rendered:
                stale.append(str(target.relative_to(root)))
        else:
            target.write_bytes(rendered)
    if stale:
        parser.exit(1, "Outdated icons:\n" + "\n".join(stale) + "\n")
    print(f"{'Checked' if args.check else 'Rendered'} {len(sources)} skill icons.")


if __name__ == "__main__":
    main()
