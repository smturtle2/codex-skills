"""File-backed content for the shared renderer; no request-specific code."""

import html
from pathlib import Path
import re

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".toml", ".yaml", ".yml", ".log"}


def inline(text, base=None):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<tt>\1</tt>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    def link(match):
        from urllib.parse import urlparse
        caption, href = match[1], html.unescape(match[2])
        parsed = urlparse(href)
        if not parsed.scheme and base is not None:
            href = (base / href).resolve().as_uri()
        elif parsed.scheme not in {"http", "https", "mailto"}:
            return match[0]
        return f'<a href="{html.escape(href, quote=True)}">{caption}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)


def label(ui, text, markup=False):
    widget = ui.Gtk.Label(xalign=0, wrap=True, selectable=True)
    widget.set_hexpand(True)
    if markup:
        widget.set_markup(text)
    else:
        widget.set_text(text)
    return widget


def picture(ui, path):
    widget = ui.Gtk.Picture.new_for_filename(str(path))
    widget.set_can_shrink(True)
    widget.set_content_fit(ui.Gtk.ContentFit.CONTAIN)
    widget.set_size_request(120, 140)
    widget.set_hexpand(True)
    return widget


def markdown(ui, text, base):
    box = ui.Gtk.Box(orientation=ui.Gtk.Orientation.VERTICAL, spacing=10)
    code = None
    table = []
    def flush_table():
        if table:
            grid = ui.Gtk.Grid(column_spacing=18, row_spacing=8)
            row = 0
            for line in table:
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in cells):
                    continue
                for column, cell in enumerate(cells):
                    widget = label(ui, inline(cell, base), True)
                    if row == 0:
                        widget.add_css_class("heading")
                    grid.attach(widget, column, row, 1, 1)
                row += 1
            box.append(grid)
            table.clear()
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            flush_table()
            if code is None:
                code = []
            else:
                block = label(ui, "\n".join(code))
                block.add_css_class("monospace")
                box.append(block)
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        image = re.fullmatch(r"\s*!\[([^\]]*)\]\(([^)]+)\)\s*", line)
        if image:
            flush_table()
            path = (base / image[2]).resolve()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                box.append(picture(ui, path))
            else:
                box.append(label(ui, image[1] or image[2]))
        elif "|" in line and line.strip().startswith("|"):
            table.append(line)
        elif line.strip():
            flush_table()
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                block = label(ui, inline(heading[2], base), True)
                block.add_css_class("title-2" if len(heading[1]) < 3 else "heading")
            else:
                line = re.sub(r"^\s*[-*+]\s+", "• ", line)
                block = label(ui, inline(line, base), True)
            box.append(block)
    flush_table()
    if code is not None:
        box.append(label(ui, "\n".join(code)))
    return box


def file_content(ui, path):
    path = Path(path)
    box = ui.Gtk.Box(orientation=ui.Gtk.Orientation.VERTICAL, spacing=8)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        box.append(picture(ui, path))
    elif path.suffix.lower() in TEXT_SUFFIXES:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"Document too large to preview: {path}")
        text = path.read_text(encoding="utf-8")
        content = markdown(ui, text, path.parent) if path.suffix.lower() in {".md", ".markdown"} else label(ui, text)
        scroller = ui.Gtk.ScrolledWindow()
        scroller.set_policy(ui.Gtk.PolicyType.NEVER, ui.Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(100)
        scroller.set_max_content_height(340)
        scroller.set_propagate_natural_height(True)
        scroller.set_child(content)
        box.append(scroller)
    link = ui.Gtk.LinkButton.new_with_label(path.as_uri(), path.name)
    link.set_halign(ui.Gtk.Align.START)
    box.append(link)
    return box
