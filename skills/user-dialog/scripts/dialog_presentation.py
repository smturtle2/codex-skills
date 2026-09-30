"""Own content readiness, layout settlement, transitions and focus restoration."""

from gi.repository import GLib, Gtk
from dialog_layout import documents_ready


def transition_options(value=None):
    if value is None:
        return {'type': 'fade-through', 'duration': 320}
    kind = value.get('type', 'none')
    return {'type': kind, 'duration': value.get('duration', 320 if kind == 'fade-through' else 120)}


def select_page(stack, name):
    if not stack.get_child_by_name(name) or name == stack.get_visible_child_name():
        return
    ui = getattr(stack, 'dialog_ui', None)
    if ui and ui._built and not ui._updating:
        names = [page.get_name() for page in stack.get_pages()]
        current = stack.get_visible_child_name()
        direction = 1 if current not in names or names.index(name) > names.index(current) else -1
        ui.presentation.change(lambda: stack.set_visible_child_name(name),
                               transition=stack.dialog_transition, direction=direction,
                               focus=stack.get_child_by_name(name))
    else:
        stack.set_visible_child_name(name)


def page_switcher(stack, children):
    switcher = Gtk.Box(spacing=0, homogeneous=True)
    switcher.add_css_class('linked')
    buttons, group = {}, None
    for child in children:
        button = Gtk.ToggleButton(label=child['label'])
        if group is not None:
            button.set_group(group)
        else:
            group = button
        button.connect('clicked', lambda _, name=child['id']: select_page(stack, name))
        switcher.append(button)
        buttons[child['id']] = button
    def sync(*args):
        name = stack.get_visible_child_name()
        if name in buttons:
            buttons[name].set_active(True)
    stack.connect('notify::visible-child', sync)
    sync()
    return switcher


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
        self.focus_target = None
        self.started = 0
        self.transition = transition_options()
        self.direction = 1
        self.initial_display = False
        self.pending = []

    def initial(self):
        self.initial_display = True
        self.transition = {'type': 'crossfade', 'duration': 160}
        self.cover = Gtk.Box()
        self.cover.add_css_class('dialog-render-cover')
        self._attach_cover()
        self._start()

    def picture(self):
        paintable = Gtk.WidgetPaintable.new(self.ui.scroller).get_current_image()
        picture = Gtk.Picture.new_for_paintable(paintable)
        picture.set_content_fit(Gtk.ContentFit.FILL)
        picture.set_can_shrink(True)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        return picture

    def _attach_cover(self):
        self.cover.set_hexpand(True)
        self.cover.set_vexpand(True)
        self.ui.body_overlay.add_overlay(self.cover)
        # WebKit stays mapped and paintable until the new content is ready.
        self.holding = True

    def change(self, swap, complete=None, *, transition=None, direction=1, focus=None):
        if self.busy:
            self.pending.append((swap, complete, transition, direction, focus))
            return
        self.initial_display = False
        self.transition = transition_options(transition)
        self.direction = direction
        self.focus_target = focus
        # Only this overlay animates settled viewport snapshots. The real page
        # stacks never animate behind the cover while documents load or resize.
        self.cover = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        self.cover.add_named(self.picture(), 'old')
        self._attach_cover()
        self.callback = complete
        self._start()
        try:
            swap()
        except Exception:
            self.cancel()
            raise

    def _start(self):
        ui = self.ui
        self.focus = ui.window.get_focus()
        self.busy = True
        self.phase = 'preparing'
        self.started = GLib.get_monotonic_time()
        self.stable = 0
        self.geometry = None
        self.action_sensitive = ui.actions.get_sensitive()
        self.content_sensitive = ui.content.get_sensitive()
        ui.actions.set_sensitive(False)
        ui.content.set_sensitive(False)
        self.tick = ui.window.add_tick_callback(self.advance)

    def settled(self):
        ui = self.ui
        if not documents_ready(ui.content):
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
        if self.phase in {'preparing', 'settling'}:
            if now - self.started > 10_000_000:
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
            ui.content.set_sensitive(self.content_sensitive)
            settings = Gtk.Settings.get_default()
            if (self.transition['type'] == 'none' or not self.transition['duration']
                    or settings and not settings.get_property('gtk-enable-animations')):
                self.finish()
                return GLib.SOURCE_REMOVE
            self.started = now
            if self.initial_display:
                self.phase = 'initial-in'
            elif self.transition['type'] == 'fade-through':
                ui.scroller.set_opacity(0)
                self.phase = 'out'
            else:
                self.cover.add_named(self.picture(), 'new')
                kind = self.transition['type']
                effect = (Gtk.StackTransitionType.CROSSFADE if kind == 'crossfade' else
                          Gtk.StackTransitionType.SLIDE_LEFT if self.direction > 0 else Gtk.StackTransitionType.SLIDE_RIGHT)
                self.cover.set_transition_type(effect)
                self.cover.set_transition_duration(self.transition['duration'])
                self.cover.set_visible_child_name('new')
                ui.scroller.set_opacity(0)
                self.phase = 'native'
        elapsed = (now - self.started) / 1000
        duration = self.transition['duration']
        if self.phase == 'native':
            if self.cover.get_transition_running():
                return GLib.SOURCE_CONTINUE
            self.finish()
            return GLib.SOURCE_REMOVE
        if self.phase == 'out':
            progress = min(1, elapsed / max(1, duration * 0.375))
            self.cover.set_opacity(1 - progress)
            if progress == 1:
                ui.body_overlay.remove_overlay(self.cover)
                self.cover = None
                self.phase = 'in'
                self.started = now
            return GLib.SOURCE_CONTINUE
        length = duration if self.phase == 'initial-in' else duration * 0.625
        progress = min(1, elapsed / max(1, length))
        if self.phase == 'initial-in':
            self.cover.set_opacity((1 - progress) ** 2)
        else:
            ui.scroller.set_opacity(1 - (1 - progress) ** 2)
        if progress < 1:
            return GLib.SOURCE_CONTINUE
        self.finish()
        return GLib.SOURCE_REMOVE

    def finish(self):
        initial, previous, target = self.initial_display, self.focus, self.focus_target
        callback, self.callback = self.callback, None
        pending, self.pending = self.pending, []
        self.cancel()
        if target is not None:
            self.ui.focus(target)
        elif initial:
            self.ui.focus()
        elif previous and previous.get_root() == self.ui.window and previous.get_mapped():
            previous.grab_focus()
        else:
            self.ui.focus()
        if callback:
            callback()
        if pending and not self.ui._finished:
            swap, complete, transition, direction, focus = pending.pop(0)
            self.pending.extend(pending)
            self.change(swap, complete, transition=transition, direction=direction, focus=focus)

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
        self.focus = None
        self.focus_target = None
        self.pending.clear()
