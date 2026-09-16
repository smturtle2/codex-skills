"""Shared code typography and theme updates for a dialog's lifetime."""

from gi.repository import Adw, Gdk, Gtk, Pango

from dialog_fonts import register_fonts


class DialogStyle:
    def __init__(self, css):
        register_fonts()
        self.css = css
        self.targets = []
        self.manager = Adw.StyleManager.get_default()
        self.provider = Gtk.CssProvider()
        self.display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(self.display, self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.signals = [self.manager.connect("notify::dark", self.refresh)]
        self.refresh()

    def refresh(self, *args):
        self.font = Pango.FontDescription.from_string("D2Coding")
        self.font.set_absolute_size(14 * Pango.SCALE)
        self.provider.load_from_data(self.css.encode())
        for view in self.targets:
            self.apply(view)

    def bind(self, view):
        self.targets.append(view)
        self.apply(view)

    def apply(self, view):
        if hasattr(view, 'document_theme'):
            view.document_theme(self.manager.get_dark())
        view.queue_resize()
        view.queue_draw()

    def prune(self, root):
        self.targets[:] = [view for view in self.targets if view.get_root() == root]

    def close(self):
        for signal in self.signals:
            self.manager.disconnect(signal)
        self.signals.clear()
        self.targets.clear()
        Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)
