"""Full-content text views that do not expose an unallocated layout's height."""

from gi.repository import Gtk


class ContentTextView(Gtk.TextView):
    def __init__(self, **kwargs):
        self._allocated_text_width = None
        super().__init__(**kwargs)

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.VERTICAL and self._allocated_text_width is None:
            # GtkTextView caches text height even before it has a real width.
            # Hidden pages can therefore report thousands of pixels of wrapping
            # at the initial one-pixel width. Let GTK allocate the actual width
            # before exposing that cache as this document's preferred height.
            return 0, 0, -1, -1
        minimum, natural, _, _ = Gtk.TextView.do_measure(self, orientation, for_size)
        return minimum, natural, -1, -1

    def do_size_allocate(self, width, height, baseline):
        previous = self._allocated_text_width
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        if width > 0:
            self._allocated_text_width = width
        if previous != self._allocated_text_width:
            self.queue_resize()
