"""Non-overlapping fade transitions for native content containers."""

from gi.repository import GLib, Gtk


class FadeTransition:
    """Run a two-part fade on a widget, applying only the latest pending swap."""

    def __init__(self, widget, duration=320):
        self.widget = widget
        self.duration = duration
        self._phase = None
        self._pending_swap = None
        self._on_complete = None
        self._tick = None
        self._started = 0
        self._start_opacity = 1

    @property
    def active(self):
        return self._phase is not None

    @property
    def phase(self):
        return self._phase

    def run(self, swap, on_complete=None):
        """Queue ``swap`` and animate it, replacing any older pending swap."""
        self._pending_swap = swap
        self._on_complete = on_complete
        if not self._animations_enabled():
            self.finish()
            return
        if self._phase == 'out':
            return
        self._begin('out')

    def finish(self):
        """Complete the pending swap immediately and restore full opacity."""
        swap = self._pending_swap
        callback = self._on_complete
        self._pending_swap = None
        self._on_complete = None
        self._stop_tick()
        self._phase = None
        try:
            if swap is not None:
                swap()
        except Exception:
            self.widget.set_opacity(1)
            raise
        self.widget.set_opacity(1)
        if callback is not None:
            callback()

    def cancel(self):
        """Cancel the pending operation without invoking its completion hook."""
        self._pending_swap = None
        self._on_complete = None
        self._stop_tick()
        self._phase = None
        self.widget.set_opacity(1)

    def _animations_enabled(self):
        settings = Gtk.Settings.get_default()
        return bool(
            self.widget.get_mapped()
            and self.duration
            and (settings is None or settings.get_property('gtk-enable-animations'))
        )

    def _begin(self, phase):
        self._phase = phase
        self._started = GLib.get_monotonic_time()
        self._start_opacity = self.widget.get_opacity()
        if self._tick is None:
            self._tick = self.widget.add_tick_callback(self._advance)

    def _stop_tick(self):
        if self._tick is not None:
            self.widget.remove_tick_callback(self._tick)
            self._tick = None

    def _advance(self, widget, clock):
        elapsed = (GLib.get_monotonic_time() - self._started) / 1000
        length = self.duration * (0.375 if self._phase == 'out' else 0.625)
        progress = min(1, elapsed / max(1, length))
        if self._phase == 'out':
            self.widget.set_opacity(self._start_opacity * (1 - progress))
            if progress < 1:
                return GLib.SOURCE_CONTINUE
            swap, self._pending_swap = self._pending_swap, None
            try:
                if swap is not None:
                    swap()
            except Exception:
                self.cancel()
                raise
            if self._phase is None:
                return GLib.SOURCE_REMOVE
            self._phase = 'in'
            self._started = GLib.get_monotonic_time()
            return GLib.SOURCE_CONTINUE

        self.widget.set_opacity(1 - (1 - progress) ** 2)
        if progress < 1:
            return GLib.SOURCE_CONTINUE
        self.finish()
        return GLib.SOURCE_REMOVE


class FadeStack(Gtk.Stack):
    def __init__(self, duration=320):
        super().__init__(transition_type=Gtk.StackTransitionType.NONE, vhomogeneous=False)
        self.duration = duration
        self.target = None
        self.transition = FadeTransition(self, duration)
        self.connect('unmap', self.finish)

    @property
    def phase(self):
        return self.transition.phase

    def select(self, name):
        if not self.get_child_by_name(name):
            return
        if not self.transition.active and name == self.get_visible_child_name():
            return
        self.target = name
        self.transition.run(lambda: self.set_visible_child_name(name))

    def finish(self, *args):
        self.transition.finish()


def select_page(stack, name):
    if isinstance(stack, FadeStack):
        stack.select(name)
    else:
        stack.set_visible_child_name(name)


class FadeGroup:
    """Animate a set of changed widgets using their window's frame clock."""

    def __init__(self, clock_widget, widgets):
        self.clock_widget = clock_widget
        self.widgets = list(dict.fromkeys(widgets))
        self.opacity = 1

    def get_opacity(self):
        return self.opacity

    def set_opacity(self, value):
        self.opacity = value
        for widget in self.widgets:
            widget.set_opacity(value)

    def get_mapped(self):
        return self.clock_widget.get_mapped()

    def add_tick_callback(self, callback):
        return self.clock_widget.add_tick_callback(callback)

    def remove_tick_callback(self, identifier):
        self.clock_widget.remove_tick_callback(identifier)


def fade_switcher(stack, children):
    switcher = Gtk.Box(spacing=0, homogeneous=True)
    switcher.add_css_class('linked')
    buttons = {}
    group = None
    for child in children:
        button = Gtk.ToggleButton(label=child['label'])
        if group is not None:
            button.set_group(group)
        else:
            group = button
        button.connect('clicked', lambda _, name=child['id']: stack.select(name))
        switcher.append(button)
        buttons[child['id']] = button

    def sync(*args):
        name = stack.target if stack.phase else stack.get_visible_child_name()
        if name in buttons:
            buttons[name].set_active(True)

    stack.connect('notify::visible-child', sync)
    sync()
    return switcher
