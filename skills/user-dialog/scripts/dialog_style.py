"""Shared code typography and theme updates for a dialog's lifetime."""

from gi.repository import Adw, Gdk, Gtk, Pango


class DialogStyle:
    def __init__(self, css):
        self.css = css
        self.targets = []
        self.manager = Adw.StyleManager.get_default()
        self.provider = Gtk.CssProvider()
        self.display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(self.display, self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.signals = [self.manager.connect("notify::dark", self.refresh)]
        if self.manager.find_property("monospace-font-name"):
            self.signals.append(self.manager.connect("notify::monospace-font-name", self.refresh))
        self.refresh()

    def refresh(self, *args):
        self.background = "#303030" if self.manager.get_dark() else "#f0f0f0"
        if self.manager.find_property("monospace-font-name"):
            self.font = Pango.FontDescription.from_string(self.manager.get_property("monospace-font-name"))
        else:
            probe = Gtk.TextView(monospace=True)
            self.font = probe.get_pango_context().get_font_description().copy()
        self.provider.load_from_data(self.css.replace("CODE_BACKGROUND", self.background).encode())
        for view, tags in self.targets:
            self.apply(view, tags)

    def bind(self, view, *tags):
        self.targets.append((view, tags))
        self.apply(view, tags)

    def apply(self, view, tags):
        for tag in tags:
            tag.set_property("font-desc", self.font)
        if hasattr(view, "code_color"):
            view.code_color.parse(self.background)
        view.queue_resize()
        view.queue_draw()

    def prune(self, root):
        self.targets[:] = [(view, tags) for view, tags in self.targets if view.get_root() == root]

    def close(self):
        for signal in self.signals:
            self.manager.disconnect(signal)
        self.signals.clear()
        self.targets.clear()
        Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)
