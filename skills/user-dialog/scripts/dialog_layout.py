"""Size the host from content after GTK has validated text layout."""

from gi.repository import GLib, Gtk


class DialogLayout:
    def __init__(self, ui):
        self.ui = ui
        self.source = 0
        self.signals = {}

    def prepare(self, widget):
        if isinstance(widget, Gtk.TextView) and not widget.get_editable() and widget not in self.signals:
            adjustment = widget.get_vadjustment()
            self.signals[widget] = (adjustment, adjustment.connect('changed', self.request))
        child = widget.get_first_child()
        while child:
            self.prepare(child)
            child = child.get_next_sibling()

    def request(self, *args):
        if not self.source and not self.ui._finished:
            # GtkTextView validates wrapped text asynchronously. Measure after
            # its validation idles, not while its cached content height is zero.
            self.source = GLib.idle_add(self.settle, priority=GLib.PRIORITY_LOW)

    def settle(self):
        self.source = 0
        self.fit()
        return GLib.SOURCE_REMOVE

    def fit(self, width=None):
        ui = self.ui
        if ui._finished or ui.state['status'] == 'submitted':
            return GLib.SOURCE_REMOVE
        ui._keyboard.prepare(ui.content)
        self.prepare(ui.content)
        if width is not None:
            if not isinstance(width, int) or width < 1:
                raise ValueError('Width must be a positive integer')
            ui._preferred_width = width
        display, surface = ui.window.get_display(), ui.window.get_surface()
        monitor = display.get_monitor_at_surface(surface) if surface else display.get_monitors().get_item(0)
        bounds = monitor.get_geometry() if monitor else None
        if bounds:
            ui.scroller.set_max_content_height(min(720, max(160, bounds.height - 220)))
        minimum, _, _, _ = ui.toolbar.measure(Gtk.Orientation.HORIZONTAL, -1)
        actual_width = max(ui._preferred_width, minimum)
        if bounds:
            actual_width = min(actual_width, max(300, bounds.width - 64))
        minimum, natural, _, _ = ui.toolbar.measure(Gtk.Orientation.VERTICAL, actual_width)
        actual_height = max(minimum, natural) + 32
        if bounds:
            actual_height = min(actual_height, max(250, bounds.height - 80))
        ui.window.set_default_size(actual_width, actual_height)
        return GLib.SOURCE_REMOVE

    def prune(self):
        for widget, (adjustment, handler) in list(self.signals.items()):
            if widget.get_root() != self.ui.window:
                adjustment.disconnect(handler)
                del self.signals[widget]

    def close(self):
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        for adjustment, handler in self.signals.values():
            adjustment.disconnect(handler)
        self.signals.clear()
