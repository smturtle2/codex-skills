"""Native keyboard behavior shared by custom dialog views."""

import sys

from gi.repository import Adw, Gdk, GLib, Gtk


class Keyboard:
    def __init__(self, ui):
        self.ui = ui
        self.initial_focus = None
        self.default = None
        self._default_signals = []
        self._configured = set()
        self._overrides = {}
        controller = Gtk.EventControllerKey()
        # Let native controls, popovers and input methods handle keys first.
        controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        controller.connect("key-pressed", self._key)
        ui.window.add_controller(controller)
        submit = Gtk.EventControllerKey()
        # TextView consumes modified Return as an editing command. Intercept
        # only the explicit submit chord before it reaches the editor.
        submit.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        submit.connect("key-pressed", self._submit_key)
        ui.window.add_controller(submit)

    def _key(self, controller, keyval, keycode, state):
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_Escape and not modifiers:
            self.ui.dismiss()
            return True
        return False

    def _submit_key(self, controller, keyval, keycode, state):
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        submit_modifiers = {Gdk.ModifierType.CONTROL_MASK}
        if sys.platform == "darwin":
            submit_modifiers.add(Gdk.ModifierType.META_MASK)
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and modifiers in submit_modifiers:
            button = self.default
            if button and button.get_mapped() and button.is_sensitive():
                button.activate()
            # Never insert a newline when the submission shortcut is disabled.
            return True
        return False

    def set_default(self, widget):
        if widget is not None and not isinstance(widget, Gtk.Button):
            raise TypeError("Default action must be a Gtk.Button or None")
        for target, signal in self._default_signals:
            target.disconnect(signal)
        self._default_signals.clear()
        self.default = widget
        if widget:
            for name in ("map", "unmap", "notify::visible", "notify::sensitive"):
                self._default_signals.append((widget, widget.connect(name, self._sync_default)))
        self._sync_default()

    def _sync_default(self, *args):
        widget = self.default
        active = widget and widget.get_mapped() and widget.is_sensitive()
        self.ui.window.set_default_widget(widget if active else None)

    def configure(self, widget, *, activates_default=None, accepts_tab=None):
        if activates_default is not None and not isinstance(widget, (Gtk.Entry, Adw.EntryRow)):
            raise TypeError("activates_default requires a Gtk.Entry or Adw.EntryRow")
        if accepts_tab is not None and not isinstance(widget, Gtk.TextView):
            raise TypeError("accepts_tab requires a Gtk.TextView")
        options = self._overrides.setdefault(widget, {})
        if activates_default is not None:
            options["activates_default"] = bool(activates_default)
        if accepts_tab is not None:
            options["accepts_tab"] = bool(accepts_tab)
        self._apply(widget)

    def _apply(self, widget):
        options = self._overrides.get(widget, {})
        if isinstance(widget, (Gtk.Entry, Adw.EntryRow)):
            widget.set_activates_default(options.get("activates_default", True))
        if isinstance(widget, Gtk.TextView):
            widget.set_accepts_tab(options.get("accepts_tab", False))

    def prepare(self, root):
        if root not in self._configured:
            self._configured.add(root)
            self._apply(root)
            if isinstance(root, Gtk.Stack):
                root.connect("notify::visible-child", self._page_changed)
        # EntryRow owns its embedded text control; configure through its API.
        if isinstance(root, (Adw.EntryRow, Gtk.Entry, Gtk.TextView)):
            return
        child = root.get_first_child()
        while child:
            self.prepare(child)
            child = child.get_next_sibling()

    def _page_changed(self, stack, param):
        page = stack.get_visible_child()
        if page:
            self.prepare(page)
            if self.ui._built:
                GLib.idle_add(self._focus, page)

    def focus(self, widget=None):
        if widget is not None and not isinstance(widget, Gtk.Widget):
            raise TypeError("Focus target must be a Gtk.Widget or None")
        if not self.ui._built:
            self.initial_focus = widget
        else:
            GLib.idle_add(self._focus, widget)

    def _focus(self, widget=None):
        if self.ui._finished:
            return GLib.SOURCE_REMOVE
        if widget and widget.get_root() == self.ui.window and widget.is_visible() and widget.is_sensitive():
            if widget.grab_focus():
                return GLib.SOURCE_REMOVE
            self.ui.window.set_focus(None)
            if widget.child_focus(Gtk.DirectionType.TAB_FORWARD):
                return GLib.SOURCE_REMOVE
        # child_focus advances relative to the current focus; clear it when
        # choosing the first control, rather than accidentally skipping it.
        self.ui.window.set_focus(None)
        if not self.ui.content.child_focus(Gtk.DirectionType.TAB_FORWARD):
            self.ui.actions.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return GLib.SOURCE_REMOVE

    def opened(self):
        self._sync_default()
        return self._focus(self.initial_focus)
