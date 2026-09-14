"""File-backed content for the shared renderer; no request-specific code."""

import html
from pathlib import Path
import re
import xml.etree.ElementTree as ET

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".toml", ".yaml", ".yml", ".log"}


def inline(text, base=None):
    code = {}
    protected = []
    position = 0
    while True:
        opening = re.search(r"`+", text[position:])
        if opening is None:
            protected.append(text[position:])
            break
        opening_start = position + opening.start()
        opening_end = position + opening.end()
        run = text[opening_start:opening_end]
        closing = re.search(
            rf"(?<!`){re.escape(run)}(?!`)", text[opening_end:]
        )
        if closing is None:
            protected.append(text[position:])
            break
        closing_start = opening_end + closing.start()
        closing_end = opening_end + closing.end()
        protected.append(text[position:opening_start])
        token = f"__DIALOG_INLINE_CODE_{len(code)}__"
        while token in text or token in code:
            token += "_"
        code[token] = f"<tt>{html.escape(text[opening_end:closing_start])}</tt>"
        protected.append(token)
        position = closing_end
    text = html.escape("".join(protected))
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
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    for token, value in code.items():
        text = text.replace(token, value)
    return text


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


def copy_button(ui, text, tooltip):
    button = ui.Gtk.Button.new_from_icon_name("edit-copy-symbolic")
    button.add_css_class("flat")
    button.set_tooltip_text(tooltip)
    button.set_halign(ui.Gtk.Align.END)
    reset_source = None
    def reset():
        nonlocal reset_source
        reset_source = None
        button.set_icon_name("edit-copy-symbolic")
        button.set_tooltip_text(tooltip)
        return ui.GLib.SOURCE_REMOVE
    def copy(_):
        nonlocal reset_source
        ui.Gdk.Display.get_default().get_clipboard().set(text)
        if reset_source is not None:
            ui.GLib.source_remove(reset_source)
        button.set_icon_name("object-select-symbolic")
        button.set_tooltip_text("Copied")
        reset_source = ui.GLib.timeout_add(1500, reset)
    def unmap(_):
        if reset_source is not None:
            ui.GLib.source_remove(reset_source)
            reset()
    button.connect("clicked", copy)
    button.connect("unmap", unmap)
    return button


def code_block(ui, text, language="", title=None):
    """Standalone source content; copying preserves whitespace exactly."""
    Gtk = ui.Gtk
    block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    block.add_css_class("dialog-code-block")
    header = Gtk.Box(spacing=8)
    header.add_css_class("dialog-code-header")
    caption = label(ui, title or language or "Code")
    caption.add_css_class("caption")
    caption.add_css_class("dim-label")
    header.append(caption)
    header.append(copy_button(ui, text, "Copy code"))
    block.append(header)
    content = Gtk.TextView(editable=False, cursor_visible=False,
                           wrap_mode=Gtk.WrapMode.WORD_CHAR)
    content.add_css_class("dialog-document")
    content.add_css_class("monospace")
    content.set_accepts_tab(False)
    content.set_hexpand(True)
    content.set_left_margin(14)
    content.set_right_margin(14)
    content.set_bottom_margin(14)
    content.get_buffer().set_text(text)
    font = content.get_buffer().create_tag(None)
    content.get_buffer().apply_tag(font, content.get_buffer().get_start_iter(), content.get_buffer().get_end_iter())
    ui.style.bind(content, font)
    block.append(content)
    return block


def markdown(ui, text, base, *, code_copy=False):
    """Selectable formatted content, independent of document presentation."""
    from gi.repository import Pango
    from dialog_markdown_view import MarkdownView
    Gtk = ui.Gtk
    view = MarkdownView(ui.style.background)
    view.add_css_class("dialog-document")
    view.set_hexpand(True)
    view.set_accepts_tab(False)
    view.set_pixels_below_lines(6)
    buffer = view.get_buffer()
    tags = {
        'b': buffer.create_tag(None, weight=Pango.Weight.BOLD),
        'i': buffer.create_tag(None, style=Pango.Style.ITALIC),
        'tt': buffer.create_tag(None, family="monospace"),
    }
    headings = [buffer.create_tag(None, weight=Pango.Weight.BOLD, scale=scale,
                                  pixels_above_lines=8, pixels_below_lines=6)
                for scale in (1.5, 1.25, 1.1, 1.0, 1.0, 1.0)]
    code_style = buffer.create_tag(None, family="monospace",
                                  left_margin=16, right_margin=16, pixels_below_lines=3)
    code_top = buffer.create_tag(None, pixels_above_lines=10, pixels_below_lines=12)
    code_caption = buffer.create_tag(None, scale=0.85, foreground="#808080", right_margin=60)
    code_bottom = buffer.create_tag(None, pixels_below_lines=16)
    paragraph_gap = buffer.create_tag(None, pixels_below_lines=12)
    paragraph_top = buffer.create_tag(None, pixels_above_lines=12)
    ui.style.bind(view, tags['tt'], code_style)
    links = {}
    def append(value, active=()):
        start = buffer.get_char_count()
        buffer.insert(buffer.get_end_iter(), value)
        for tag in active:
            buffer.apply_tag(tag, buffer.get_iter_at_offset(start), buffer.get_end_iter())
    def formatted(value, active=()):
        try:
            root = ET.fromstring('<root>' + inline(value, base) + '</root>')
        except ET.ParseError:
            append(value, active)
            return
        def visit(node, inherited):
            current = inherited
            if node.tag in tags:
                current = (*current, tags[node.tag])
            elif node.tag == 'a':
                tag = buffer.create_tag(None, underline=Pango.Underline.SINGLE)
                links[tag] = node.attrib['href']
                current = (*current, tag)
            if node.text:
                append(node.text, current)
            for child in node:
                visit(child, current)
                if child.tail:
                    append(child.tail, current)
        visit(root, active)
    def embed(widget):
        anchor = buffer.create_child_anchor(buffer.get_end_iter())
        view.add_child_at_anchor(widget, anchor)
    code, table, code_language = None, [], ""
    def flush_table():
        if not table:
            return
        rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in table]
        rows = [row for row in rows if not all(re.fullmatch(r':?-+:?', cell.replace(' ', '')) for cell in row)]
        width = max((len(row) for row in rows), default=0)
        lengths = [max((len(row[i]) if i < len(row) else 0 for row in rows), default=0) for i in range(width)]
        for index, row in enumerate(rows):
            line = '  '.join(value.ljust(lengths[i]) for i, value in enumerate(row)).rstrip()
            formatted(line, (tags['tt'], tags['b']) if index == 0 else (tags['tt'],))
            append('\n')
        table.clear()
    def flush_code():
        value = '\n'.join(code)
        start = buffer.get_char_count()
        button = None
        if code_copy:
            append((code_language or "Code") + '\n', (code_caption,))
            button = copy_button(ui, value, "Copy code")
        append(value + '\n', (tags['tt'],))
        buffer.apply_tag(code_style, buffer.get_iter_at_offset(start), buffer.get_end_iter())
        buffer.apply_tag(code_top, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(start + 1))
        last_line = buffer.get_iter_at_offset(buffer.get_char_count() - 1)
        last_line.set_line_offset(0)
        buffer.apply_tag(code_bottom, last_line, buffer.get_end_iter())
        view.add_code_region(start, buffer.get_char_count(), button)
        # A following paragraph supplies its own gap; avoid an empty text line.
    pending_gap = False
    for line in text.splitlines():
        gap_before = None
        if code is None and not line.strip():
            flush_table()
            pending_gap = True
            continue
        if pending_gap and buffer.get_char_count():
            previous = buffer.get_iter_at_offset(buffer.get_char_count() - 1)
            previous.set_line_offset(0)
            # Code regions already own their bottom padding.
            if not view.code_regions or view.code_regions[-1][1] != buffer.get_char_count():
                buffer.apply_tag(paragraph_gap, previous, buffer.get_end_iter())
            else:
                gap_before = buffer.get_char_count()
        pending_gap = False
        if line.lstrip().startswith('```'):
            flush_table()
            if code is None:
                code = []
                code_language = line.lstrip()[3:].strip()
            else:
                flush_code()
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if line.strip().startswith('|'):
            table.append(line)
            continue
        flush_table()
        image = re.fullmatch(r'\s*!\[([^\]]*)\]\(([^)]+)\)\s*', line)
        if image:
            path = (base / image[2]).resolve()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                embed(picture(ui, path))
            else:
                append(image[1] or image[2])
        else:
            heading = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading:
                formatted(heading[2], (headings[len(heading[1]) - 1],))
            else:
                formatted(re.sub(r'^\s*[-*+]\s+', '• ', line))
        append('\n')
        if gap_before is not None:
            buffer.apply_tag(paragraph_top, buffer.get_iter_at_offset(gap_before), buffer.get_end_iter())
    flush_table()
    if code is not None:
        flush_code()
    # The final separator is structural, not an extra visible paragraph.
    count = buffer.get_char_count()
    if count:
        buffer.delete(buffer.get_iter_at_offset(count - 1), buffer.get_end_iter())
        view.code_regions = [(start, min(end, count - 1), button)
                             for start, end, button in view.code_regions if start < count - 1]
    def follow_link(gesture, count, x, y):
        if count != 1 or buffer.get_selection_bounds():
            return
        bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, position = view.get_iter_at_location(bx, by)
        if found:
            for tag in position.get_tags():
                if tag in links:
                    ui.Gio.AppInfo.launch_default_for_uri(links[tag], None)
                    break
    click = Gtk.GestureClick()
    click.set_button(1)
    click.connect('released', follow_link)
    view.add_controller(click)
    return view


def markdown_document(ui, text, base, title="Markdown", path=None):
    """Document identity and actions above content in the main reading flow."""
    from gi.repository import Pango
    Gtk = ui.Gtk
    document = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    document.add_css_class("dialog-document-card")
    header = Gtk.Box(spacing=8)
    header.add_css_class("dialog-document-header")
    icon = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
    icon.add_css_class("dim-label")
    header.append(icon)
    if path is not None:
        heading = Gtk.LinkButton.new_with_label(path.as_uri(), title)
        heading.set_tooltip_text(str(path))
    else:
        heading = label(ui, title)
    title_label = heading.get_child() if path is not None else heading
    title_label.set_wrap(False)
    title_label.set_ellipsize(Pango.EllipsizeMode.END)
    title_label.set_xalign(0)
    heading.set_tooltip_text(str(path) if path is not None else title)
    heading.add_css_class("dialog-document-name")
    heading.set_halign(Gtk.Align.FILL)
    heading.set_hexpand(True)
    header.append(heading)
    header.append(copy_button(ui, text, "Copy Markdown source"))
    document.append(header)
    content = markdown(ui, text, base, code_copy=True)
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(content, f'set_margin_{side}')(18 if side != 'top' else 4)
    document.append(content)
    return document


def file_content(ui, path, title=None):
    path = Path(path)
    box = ui.Gtk.Box(orientation=ui.Gtk.Orientation.VERTICAL, spacing=8)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        box.append(picture(ui, path))
    elif path.suffix.lower() in TEXT_SUFFIXES:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"Document too large to preview: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".md", ".markdown"}:
            return markdown_document(ui, text, path.parent, title or path.name, path)
        else:
            scroller = ui.Gtk.ScrolledWindow()
            scroller.set_policy(ui.Gtk.PolicyType.NEVER, ui.Gtk.PolicyType.AUTOMATIC)
            scroller.set_min_content_height(100)
            scroller.set_max_content_height(340)
            scroller.set_propagate_natural_height(True)
            scroller.set_child(label(ui, text))
            box.append(scroller)
    link = ui.Gtk.LinkButton.new_with_label(path.as_uri(), path.name)
    link.set_halign(ui.Gtk.Align.START)
    box.append(link)
    return box
