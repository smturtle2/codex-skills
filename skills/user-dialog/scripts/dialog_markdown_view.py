"""Code surfaces around a continuous, selectable Markdown text buffer."""

from gi.repository import Gdk, Graphene, Gsk, Gtk


class MarkdownView(Gtk.TextView):
    def __init__(self, background):
        super().__init__(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.code_regions = []
        self.code_color = Gdk.RGBA()
        self.code_color.parse(background)

    def add_code_region(self, start, end, button=None):
        self.code_regions.append((start, end, button))
        if button is not None:
            self.add_overlay(button, 0, 0)

    def bounds(self, start, end):
        buffer = self.get_buffer()
        top, _ = self.get_line_yrange(buffer.get_iter_at_offset(start))
        bottom, height = self.get_line_yrange(buffer.get_iter_at_offset(end - 1))
        return top, bottom + height

    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        for start, end, button in self.code_regions:
            if button is not None:
                top, _ = self.bounds(start, end)
                _, natural, _, _ = button.measure(Gtk.Orientation.HORIZONTAL, -1)
                self.move_overlay(button, max(0, width - natural - 8), top + 4)

    def do_snapshot(self, snapshot):
        for start, end, _ in self.code_regions:
            top, bottom = self.bounds(start, end)
            _, y = self.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, 0, top)
            rect = Graphene.Rect()
            rect.init(0, y, self.get_width(), bottom - top)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, 10)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(self.code_color, rect)
            snapshot.pop()
        Gtk.TextView.do_snapshot(self, snapshot)
