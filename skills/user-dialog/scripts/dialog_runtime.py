"""GTK host for compiled declarative dialogs."""

import threading
import math
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
from dialog_spec import format_response
from dialog_view import View
from dialog_delivery import deliver


STYLE = """
.user-dialog {
  --accent-bg-color: var(--accent-blue);
  --accent-color: oklab(from var(--accent-bg-color) var(--standalone-color-oklab));
  --accent-fg-color: white;
}
.user-dialog .title-1 { font-size: 21px; }
.user-dialog .dialog-error { color: var(--error-color); }
.user-dialog .dialog-group { padding: 16px; }
.user-dialog .dialog-editor { border-radius: 10px; border: 1px solid alpha(currentColor, 0.12); padding: 10px; }
"""


class Dialog:
    def __init__(self, app, directory, state):
        self.app, self.run_dir, self.state = app, directory, state
        self.view_dir = Path(state["base"])
        self._submitting = False
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
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.content)
        self.scroller.set_propagate_natural_height(True)
        self.scroller.set_max_content_height(720)
        self.toolbar.set_content(self.scroller)
        self.status_label = Gtk.Label(wrap=True, xalign=0)
        self.status_label.set_visible(False)
        self.sending_indicator = Gtk.Box(spacing=5, halign=Gtk.Align.START)
        self.sending_dots = [Gtk.Label(label="•") for _ in range(3)]
        for dot in self.sending_dots:
            self.sending_indicator.append(dot)
        self.sending_indicator.set_visible(False)
        self._sending_source = 0
        self.actions = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("bottom", "start", "end"):
            getattr(self.footer, f"set_margin_{side}")(18)
        self.footer.append(self.status_label)
        self.footer.append(self.sending_indicator)
        self.footer.append(self.actions)
        self.footer.set_visible(False)
        self.toolbar.add_bottom_bar(self.footer)
        self._bindings = {}
        self._validator = None
        self._finished = False
        self._built = False
        self._preferred_width = state["spec"].get("width", 600)
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

    def message(self, value, *, error=False):
        if error:
            self.status_label.add_css_class("dialog-error")
        else:
            self.status_label.remove_css_class("dialog-error")
        self.status_label.set_text(value or "")
        self.status_label.set_visible(bool(value))
        self.footer.set_visible(bool(value) or self.sending_indicator.get_visible() or self.actions.get_first_child() is not None)
        if self._built:
            self.refit()

    def set_sending(self, active):
        if self._sending_source:
            GLib.source_remove(self._sending_source)
            self._sending_source = 0
        self.sending_indicator.set_visible(active)
        if active:
            self.message(None)
            started = GLib.get_monotonic_time()
            def animate():
                elapsed = (GLib.get_monotonic_time() - started) / 1_000_000
                for index, dot in enumerate(self.sending_dots):
                    wave = (1 + math.cos(math.tau * (elapsed / 1.2 - index / 3))) / 2
                    dot.set_opacity(0.25 + 0.75 * wave)
                return GLib.SOURCE_CONTINUE
            animate()
            self._sending_source = GLib.timeout_add(50, animate)

    def checkpoint(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        values = self.collect()
        if values != self.state.get("draft"):
            self.state["draft"] = values
            save_state(self.run_dir, self.state)
        return GLib.SOURCE_CONTINUE

    def submit(self, values=None, *, action="submit", include_values=True):
        if self._finished or self._submitting:
            return
        collected = (self.collect() if values is None else values) if include_values else {}
        if include_values and self._validator:
            message = self._validator(collected)
            if message is not None:
                self.message(message, error=True)
                return
        self.state["message"] = format_response(self.state["spec"], collected, action, include_values=include_values)
        (self.run_dir / "message.md").write_text(self.state["message"], encoding="utf-8")
        self.checkpoint()
        finish_state(self.run_dir, self.state, "submitted", collected, action)
        if not self.state.get("origin"):
            self.close()
            return
        self._submitting = True
        self.content.set_sensitive(False)
        self.actions.set_sensitive(False)
        self.set_sending(True)
        def send():
            try:
                deliver(self.run_dir, self.state)
            except Exception as error:
                self.state["delivery"] = {"status": "unknown", "error": str(error)}
            GLib.idle_add(self.delivery_finished)
        threading.Thread(target=send, daemon=False).start()

    def delivery_finished(self):
        delivery = self.state["delivery"]
        if delivery.get("observation", {}).get("status") == "observed":
            self.finish_delivery()
        else:
            self.set_sending(False)
            if delivery["status"] == "accepted":
                self.message("Sent, but the response could not be confirmed in task history. "
                             "Your answer is saved. You can close this window.", error=True)
            else:
                self.message("Delivery was not confirmed. Your answer is saved. " + delivery.get("error", ""), error=True)
            self._submitting = False
        return GLib.SOURCE_REMOVE

    def finish_delivery(self):
        self.close()
        return GLib.SOURCE_REMOVE

    def dismiss(self):
        self._finish("dismissed", None)

    def defer(self):
        self._finish("deferred", None)

    def close(self):
        self._finished = True
        self.set_sending(False)
        if self._checkpoint_source:
            GLib.source_remove(self._checkpoint_source)
        self.window.destroy()
        self.app.quit()

    def _finish(self, status, values, action=None):
        if self._finished or self._submitting:
            return
        if self.state["status"] != "submitted":
            self.checkpoint()
            finish_state(self.run_dir, self.state, status, values, action)
        self.close()

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
            actual_width = min(actual_width, max(300, bounds.width - 64))
            actual_height = min(actual_height, max(250, bounds.height - 80))
            self.scroller.set_max_content_height(min(720, max(160, bounds.height - 220)))
        self.window.set_default_size(actual_width, actual_height)
        return GLib.SOURCE_REMOVE

    def open(self):
        self.view = View(self, self.state["spec"])
        self.set_content(self.view.build())
        self._built = True
        self.checkpoint()
        self.refit()
        self._checkpoint_source = GLib.timeout_add(500, self.checkpoint)
        self.window.present()
        self.state["status"] = "open"
        from dialog_state import save_state
        save_state(self.run_dir, self.state)
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
            if not current.get("response"):
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

    import signal
    def interrupted(signum, frame):
        if dialog and dialog._submitting:
            # Delivery may already have reached Codex. Preserve uncertain state.
            return
        current = read_state(directory)
        if current["status"] != "submitted":
            finish_state(directory, current, "error", None, error="Renderer interrupted; draft retained")
        if dialog:
            dialog.close()
        else:
            app.quit()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    app.connect("activate", activate)
    app.run([sys.argv[0]])
    return 0


if __name__ == "__main__":
    with run_lock(Path(sys.argv[1]).resolve(), ".window-lock"):
        raise SystemExit(main())
