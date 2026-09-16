"""Reveal settled content and keep the previous viewport visible during changes."""

from gi.repository import GLib, Gtk
from dialog_layout import documents_ready


class Presentation:
    def __init__(self, ui):
        self.ui = ui
        self.busy = False
        self.holding = False
        self.tick = None
        self.cover = None
        self.callback = None
        self.phase = None
        self.stable = 0
        self.geometry = None
        self.focus = None
        self.started = 0
        self.duration = 160

    def initial(self):
        self.initial_display = True
        self.cover = Gtk.Box()
        self.cover.add_css_class('dialog-render-cover')
        self.cover.set_hexpand(True)
        self.cover.set_vexpand(True)
        self.ui.body_overlay.add_overlay(self.cover)
        self.holding = True
        self._start('preparing')

    def change(self, swap, complete=None):
        if self.busy:
            raise ValueError('A display transition is already in progress')
        ui = self.ui
        self.initial_display = False
        paintable = Gtk.WidgetPaintable.new(ui.scroller).get_current_image()
        self.cover = Gtk.Picture.new_for_paintable(paintable)
        self.cover.set_content_fit(Gtk.ContentFit.FILL)
        self.cover.set_can_shrink(True)
        self.cover.set_hexpand(True)
        self.cover.set_vexpand(True)
        ui.body_overlay.add_overlay(self.cover)
        # Keep the browser mapped and paintable behind the cover. Opacity zero
        # can suspend its animation frames and prevent a readiness message.
        self.holding = True
        self.callback = complete
        self._start('preparing')
        try:
            swap()
        except Exception:
            self.cancel()
            raise

    def _start(self, phase):
        self.focus = self.ui.window.get_focus()
        self.busy = True
        self.phase = phase
        self.started = GLib.get_monotonic_time()
        self.stable = 0
        self.geometry = None
        self.action_sensitive = self.ui.actions.get_sensitive()
        self.content_sensitive = self.ui.content.get_sensitive()
        self.ui.actions.set_sensitive(False)
        self.ui.content.set_sensitive(False)
        self.tick = self.ui.window.add_tick_callback(self.advance)

    def settled(self):
        ui = self.ui
        if not documents_ready(ui.content):
            self.stable = 0
            return False
        from dialog_reconcile import descendants
        if any(w.get_transition_running() for w in descendants(ui.content) if isinstance(w, Gtk.Stack)):
            self.stable = 0
            return False
        geometry = (ui.window.get_width(), ui.window.get_height(),
                    ui.scroller.get_vadjustment().get_upper(),
                    tuple((d.web.get_width(), d.web.get_height()) for d in ui.documents if d.get_mapped()))
        self.stable = self.stable + 1 if geometry == self.geometry else 0
        self.geometry = geometry
        return self.stable >= 2

    def advance(self, widget, clock):
        ui = self.ui
        if ui._finished:
            self.cancel()
            return GLib.SOURCE_REMOVE
        now = GLib.get_monotonic_time()
        if self.phase in {'initial', 'preparing', 'settling'}:
            if now - self.started > 10_000_000:
                # A broken browser must not leave an invisible, focused window.
                ui.message('Some content could not finish rendering.', error=True)
                self.finish()
                return GLib.SOURCE_REMOVE
            if not self.settled():
                ui.window.queue_draw()
                return GLib.SOURCE_CONTINUE
            if self.phase == 'preparing':
                self.holding = False
                ui.refit()
                self.phase = 'settling'
                self.stable = 0
                self.geometry = None
                return GLib.SOURCE_CONTINUE
            self.phase = 'initial-in' if self.initial_display else 'out'
            if not self.initial_display:
                ui.scroller.set_opacity(0)
            ui.content.set_sensitive(self.content_sensitive)
            self.started = now
            settings = Gtk.Settings.get_default()
            if settings and not settings.get_property('gtk-enable-animations'):
                self.finish()
                return GLib.SOURCE_REMOVE
        elapsed = (now - self.started) / 1000
        if self.phase == 'out':
            progress = min(1, elapsed / 60)
            self.cover.set_opacity(1 - progress)
            if progress == 1:
                ui.body_overlay.remove_overlay(self.cover)
                self.cover = None
                self.phase = 'in'
                self.started = now
            return GLib.SOURCE_CONTINUE
        progress = min(1, elapsed / self.duration)
        if self.phase == 'initial-in':
            self.cover.set_opacity((1 - progress) ** 2)
        else:
            ui.scroller.set_opacity(1 - (1 - progress) ** 2)
        if progress < 1:
            return GLib.SOURCE_CONTINUE
        self.finish()
        return GLib.SOURCE_REMOVE

    def finish(self):
        initial = self.initial_display
        callback, self.callback = self.callback, None
        self.cancel()
        if initial:
            self.ui.focus()
        elif self.focus and self.focus.get_root() == self.ui.window and self.focus.get_mapped():
            self.focus.grab_focus()
        if callback:
            callback()

    def cancel(self):
        if self.tick is not None:
            self.ui.window.remove_tick_callback(self.tick)
            self.tick = None
        if self.cover:
            self.ui.body_overlay.remove_overlay(self.cover)
            self.cover = None
        self.ui.window.set_opacity(1)
        self.ui.scroller.set_opacity(1)
        if self.busy:
            self.ui.actions.set_sensitive(self.action_sensitive)
            self.ui.content.set_sensitive(self.content_sensitive)
        self.busy = False
        self.holding = False
        self.phase = None
        self.callback = None
