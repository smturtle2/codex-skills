"""File-backed content for the shared renderer; no request-specific code."""

from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".toml", ".yaml", ".yml", ".log"}


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
        ui.Gdk.Display.get_default().get_clipboard().set(text() if callable(text) else text)
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
    """Use the same code renderer as Markdown while preserving exact source."""
    from dialog_document import compile_code
    from dialog_document_view import DocumentView
    return DocumentView(ui, text, ui.view_dir, display={'copy_code': True},
                        document=compile_code(text, language, title))


def markdown_document(ui, text, base, title="Markdown", path=None, display=None, segments=None):
    """One body renderer with independent, optional presentation controls."""
    from gi.repository import Pango
    from dialog_document_view import DocumentView
    options = {key: path is not None for key in ('title', 'border', 'copy_source', 'copy_code')}
    options.update(display or {})
    Gtk = ui.Gtk
    document = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    if options['border']:
        document.add_css_class("dialog-document-card")
    content = DocumentView(ui, text, base, display=options, segments=segments)
    if options['title'] or options['copy_source']:
        header = Gtk.Box(spacing=8)
        header.add_css_class("dialog-document-header")
        if options['title']:
            if path is not None:
                heading = Gtk.LinkButton.new_with_label(path.as_uri(), title)
            else:
                heading = label(ui, title)
            caption = heading.get_child() if path is not None else heading
            caption.set_wrap(False)
            caption.set_ellipsize(Pango.EllipsizeMode.END)
            caption.set_xalign(0)
            heading.set_tooltip_text(str(path) if path is not None else title)
            heading.add_css_class("dialog-document-name")
            heading.set_halign(Gtk.Align.FILL)
            heading.set_hexpand(True)
            header.append(heading)
        else:
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            header.append(spacer)
        if options['copy_source']:
            header.append(copy_button(ui, lambda: content.source, "Copy Markdown source"))
        document.append(header)
    document.append(content)
    document.set_text = content.set_text
    return document


def file_content(ui, path, title=None, display=None):
    path = Path(path)
    box = ui.Gtk.Box(orientation=ui.Gtk.Orientation.VERTICAL, spacing=8)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        box.append(picture(ui, path))
    elif path.suffix.lower() in TEXT_SUFFIXES:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"Document too large to preview: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".md", ".markdown"}:
            return markdown_document(ui, text, path.parent, title or path.name, path, display=display)
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
