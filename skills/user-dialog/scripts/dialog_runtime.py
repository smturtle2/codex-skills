"""GTK host for an agent-authored build(ui) function."""

import importlib.util
import json
from pathlib import Path
import sys
import traceback

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from dialog_state import encode, finish_state, read_state, run_lock, save_state
from dialog_keyboard import Keyboard


STYLE = """
.user-dialog {
  --accent-bg-color: var(--accent-blue);
  --accent-color: oklab(from var(--accent-bg-color) var(--standalone-color-oklab));
  --accent-fg-color: white;
}
.user-dialog .title-1 { font-size: 21px; }
.user-dialog .dialog-error { color: var(--error-color); }
"""


class Dialog:
    def __init__(self, app, directory, state):
        self.app, self.run_dir, self.state = app, directory, state
        self.view_dir = Path(state["view"]).parent
        self.request_id = state["request_id"]
        self.Gtk, self.Adw, self.GLib, self.Gdk, self.Gio = Gtk, Adw, GLib, Gdk, Gio
        self.window = Adw.ApplicationWindow(application=app, title=state["title"])
        self.window.add_css_class("user-dialog")
        self.window.connect("close-request", self._close)
        self.toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=state["title"], subtitle=state["subtitle"]))
        self.toolbar.add_top_bar(header)
        self.window.set_content(self.toolbar)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.content, f"set_margin_{side}")(26)
        self.content.set_vexpand(True)
        self.toolbar.set_content(self.content)
        self.error = Gtk.Label(wrap=True, xalign=0)
        self.error.add_css_class("dialog-error")
        self.error.set_visible(False)
        self.actions = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("bottom", "start", "end"):
            getattr(self.footer, f"set_margin_{side}")(18)
        self.footer.append(self.error)
        self.footer.append(self.actions)
        self.footer.set_visible(False)
        self.toolbar.add_bottom_bar(self.footer)
        self._bindings = {}
        self._validator = None
        self._finished = False
        self._built = False
        self._preferred_width = 470
        self._checkpoint_source = 0
        self._keyboard = Keyboard(self)

    def set_content(self, widget):
        if not isinstance(widget, Gtk.Widget):
            raise TypeError("set_content requires a Gtk.Widget")
        while self.content.get_first_child():
            self.content.remove(self.content.get_first_child())
        self.content.append(widget)
        self._keyboard.prepare(widget)
        if self._built:
            self.refit()
            self.focus()

    def focus(self, widget=None):
        self._keyboard.focus(widget)

    def set_default_action(self, button):
        self._keyboard.set_default(button)

    def keyboard(self, widget, *, activates_default=None, accepts_tab=None):
        self._keyboard.configure(widget, activates_default=activates_default, accepts_tab=accepts_tab)

    def bind(self, name, read, write=None):
        if not isinstance(name, str) or not name or name in self._bindings:
            raise ValueError("Binding names must be unique non-empty strings")
        if not callable(read) or (write is not None and not callable(write)):
            raise TypeError("Bindings require callable readers and optional writers")
        self._bindings[name] = (read, write)

    def collect(self):
        values = {name: read() for name, (read, _) in self._bindings.items()}
        # Validate without coercing user-defined values or accepting NaN.
        return json.loads(encode(values))

    def set_validator(self, callback):
        if not callable(callback):
            raise TypeError("Validator must be callable")
        self._validator = callback

    def action(self, action_id, label, *, primary=False, callback=None, default=None):
        if not isinstance(action_id, str) or not action_id or not isinstance(label, str) or not label:
            raise ValueError("An action needs a non-empty ID and visible label")
        button = Gtk.Button(label=label)
        if primary:
            button.add_css_class("suggested-action")
        button.connect("clicked", lambda *_: callback() if callback else self.submit(action=action_id))
        self.actions.append(button)
        self.footer.set_visible(True)
        if default is True or (default is None and primary):
            self.set_default_action(button)
        return button

    def message(self, value):
        self.error.set_text(value or "")
        self.error.set_visible(bool(value))
        self.footer.set_visible(bool(value) or self.actions.get_first_child() is not None)
        if self._built:
            self.refit()

    def checkpoint(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        values = self.collect()
        if values != self.state.get("draft"):
            self.state["draft"] = values
            save_state(self.run_dir, self.state)
        return GLib.SOURCE_CONTINUE

    def submit(self, values=None, *, action="submit"):
        if self._finished:
            return
        collected = self.collect() if values is None else values
        encode(collected)
        if self._validator:
            message = self._validator(collected)
            if message is not None:
                if not isinstance(message, str):
                    raise TypeError("Validator must return a user-facing string or None")
                self.message(message)
                return
        self._finish("submitted", collected, action)

    def dismiss(self):
        self._finish("dismissed", None)

    def defer(self):
        self._finish("deferred", None)

    def _finish(self, status, values, action=None):
        if self._finished:
            return
        self.checkpoint()
        finish_state(self.run_dir, self.state, status, values, action)
        self._finished = True
        if self._checkpoint_source:
            GLib.source_remove(self._checkpoint_source)
        self.window.destroy()
        self.app.quit()

    def _close(self, window):
        self.dismiss()
        return True

    def refit(self, width=None):
        self._keyboard.prepare(self.content)
        if width is not None:
            if not isinstance(width, int) or width < 1:
                raise ValueError("Width must be a positive integer")
            self._preferred_width = width
        minimum, _, _, _ = self.toolbar.measure(Gtk.Orientation.HORIZONTAL, -1)
        actual_width = max(self._preferred_width, minimum)
        minimum, natural, _, _ = self.toolbar.measure(Gtk.Orientation.VERTICAL, actual_width)
        actual_height = max(minimum, natural) + 32
        display = self.window.get_display()
        surface = self.window.get_surface()
        monitor = display.get_monitor_at_surface(surface) if surface else display.get_monitors().get_item(0)
        if monitor:
            bounds = monitor.get_geometry()
            if actual_width > bounds.width - 64 or actual_height > bounds.height - 80:
                raise ValueError(f"View needs {actual_width}x{actual_height} logical pixels; "
                                 "adapt its composition to fit the display before presenting it")
        self.window.set_default_size(actual_width, actual_height)
        return GLib.SOURCE_REMOVE

    def open(self):
        view = Path(self.state["view"])
        sys.path.insert(0, str(view.parent))
        spec = importlib.util.spec_from_file_location("user_dialog_view", view)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load view: {view}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        build = getattr(module, "build", None)
        if not callable(build):
            raise ValueError("View module must define build(ui)")
        returned = build(self)
        if returned is not None:
            self.set_content(returned)
        if not self.content.get_first_child():
            raise ValueError("build(ui) must return a widget or call ui.set_content(widget)")
        for name, (_, write) in self._bindings.items():
            if write is not None and name in self.state["draft"]:
                write(self.state["draft"][name])
        self._built = True
        self.checkpoint()
        self.refit()
        self._checkpoint_source = GLib.timeout_add(500, self.checkpoint)
        self.window.present()
        GLib.idle_add(self.refit)
        GLib.idle_add(self._keyboard.opened)


def main():
    directory = Path(sys.argv[1]).resolve()
    state = read_state(directory)
    app = Adw.Application(application_id="local.codex.UserDialog", flags=Gio.ApplicationFlags.NON_UNIQUE)
    dialog = None

    def fail(exc_type, error, tb):
        traceback.print_exception(exc_type, error, tb, file=sys.stderr)
        try:
            current = read_state(directory)
            if current.get("response") is None:
                finish_state(directory, current, "error", None, error=str(error))
        finally:
            if dialog:
                dialog._finished = True
                dialog.window.destroy()
            app.quit()

    sys.excepthook = fail

    def activate(application):
        nonlocal dialog
        if dialog:
            dialog.window.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        dialog = Dialog(application, directory, state)
        dialog.open()

    app.connect("activate", activate)
    app.run([sys.argv[0]])
    return 0


if __name__ == "__main__":
    with run_lock(Path(sys.argv[1]).resolve(), ".window-lock"):
        raise SystemExit(main())
