"""GTK host for compiled declarative dialogs."""

import threading
import math
import json
import os
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
from dialog_style import DialogStyle
from dialog_layout import DialogLayout
from dialog_presentation import Presentation
from dialog_delivery import deliver, confirm_delivery


STYLE = """
.user-dialog {
  font-family: "Pretendard";
  font-size: 15px;
  --accent-bg-color: var(--accent-blue);
  --accent-color: oklab(from var(--accent-bg-color) var(--standalone-color-oklab));
  --accent-fg-color: white;
}
.user-dialog .title-1 { font-size: 22px; }
.user-dialog .monospace { font-family: "D2Coding"; font-size: 14px; }
.user-dialog .dialog-error { color: var(--error-color); }
.user-dialog .dialog-render-cover { background: var(--window-bg-color); }
.user-dialog .dialog-group { padding: 16px; }
.user-dialog .dialog-editor { border-radius: 10px; border: 1px solid alpha(currentColor, 0.12); padding: 10px; }
.user-dialog .dialog-document, .user-dialog .dialog-document text { background: transparent; }
.user-dialog .dialog-document-card { background: var(--view-bg-color); border: 1px solid alpha(currentColor, 0.08); border-radius: 14px; }
.user-dialog .dialog-document-header { padding: 8px 14px; }
.user-dialog .dialog-document-name { font-size: 0.9em; font-weight: 500; color: alpha(currentColor, 0.6); }
.user-dialog button.dialog-document-name { padding: 0; min-height: 0; }
.user-dialog button.dialog-document-name label { text-decoration: none; }
"""


class Dialog:
    def __init__(self, app, directory, state):
        self.app, self.run_dir, self.state = app, directory, state
        self.view_dir = Path(state["base"])
        self._submitting = False
        self._updating = False
        self.live = None
        self.documents = set()
        self._layout_source = 0
        self._layout_last = None
        self._delivery_cancel = threading.Event()
        self.request_id = state["request_id"]
        self.Gtk, self.Adw, self.GLib, self.Gdk, self.Gio = Gtk, Adw, GLib, Gdk, Gio
        self.style = DialogStyle(STYLE)
        self.window = Adw.ApplicationWindow(application=app, title=state["title"])
        self.window.add_css_class("user-dialog")
        self.window.connect("close-request", self._close)
        self.toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(title=state["title"], subtitle=state["subtitle"])
        header.set_title_widget(self.window_title)
        self.toolbar.add_top_bar(header)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.toolbar)
        self.window.set_content(self.toast_overlay)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.content, f"set_margin_{side}")(26)
        self.content.set_vexpand(True)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.content)
        self.scroller.set_propagate_natural_height(True)
        self.scroller.set_max_content_height(720)
        self.body_overlay = Gtk.Overlay()
        self.body_overlay.set_child(self.scroller)
        self.toolbar.set_content(self.body_overlay)
        self.status_label = Gtk.Label(wrap=True, xalign=0)
        self.status_label.set_visible(False)
        self._sending_source = 0
        self._submit_button = None
        self._submit_overlay = None
        self._retry_available = False
        self.actions = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("bottom", "start", "end"):
            getattr(self.footer, f"set_margin_{side}")(18)
        self.footer.append(self.status_label)
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
        self.layout = DialogLayout(self)
        self.presentation = Presentation(self)

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
        button.connect("clicked", lambda button: callback(button) if callback else self.submit(action=action_id, button=button))
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
        self.footer.set_visible(bool(value) or self.actions.get_first_child() is not None)
        if self._built and self.state["status"] != "submitted":
            self.refit()

    def prepare_sending(self, button):
        self._submit_button = button
        if button is None:
            return
        classes = button.get_css_classes()
        original = button.get_child()
        button.set_child(None)
        overlay = Gtk.Overlay()
        overlay.set_child(original)
        original.set_opacity(0)
        self.sending_indicator = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.sending_dots = [Gtk.Label(label="•") for _ in range(3)]
        for dot in self.sending_dots:
            self.sending_indicator.append(dot)
        overlay.add_overlay(self.sending_indicator)
        self.retry_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        self.retry_icon.set_halign(Gtk.Align.CENTER)
        self.retry_icon.set_valign(Gtk.Align.CENTER)
        self.retry_icon.set_visible(False)
        overlay.add_overlay(self.retry_icon)
        button.set_child(overlay)
        button.set_css_classes(classes)
        self._submit_overlay = overlay

    def set_sending(self, active):
        if self._sending_source:
            GLib.source_remove(self._sending_source)
            self._sending_source = 0
        if self._submit_overlay is None:
            return
        self.sending_indicator.set_visible(active)
        self.retry_icon.set_visible(not active and self._retry_available)
        if active:
            self._submit_button.set_tooltip_text(None)
            started = GLib.get_monotonic_time()
            def animate():
                elapsed = (GLib.get_monotonic_time() - started) / 1_000_000
                for index, dot in enumerate(self.sending_dots):
                    wave = (1 + math.cos(math.tau * (elapsed / 1.2 - index / 3))) / 2
                    dot.set_opacity(0.25 + 0.75 * wave)
                return GLib.SOURCE_CONTINUE
            animate()
            self._sending_source = GLib.timeout_add(50, animate)

    def schedule_checkpoint(self):
        if not self._checkpoint_source and not self._finished and self.state['status'] != 'submitted':
            self._checkpoint_source = GLib.timeout_add(300, self.flush_checkpoint)

    def flush_checkpoint(self):
        self._checkpoint_source = 0
        if self._updating or any(d.dialog_dragging for d in self.documents):
            self.schedule_checkpoint()
        else:
            self.checkpoint()
        return GLib.SOURCE_REMOVE

    def checkpoint(self):
        if self._updating:
            return GLib.SOURCE_CONTINUE
        if self._finished or self.state["status"] == "submitted":
            self._checkpoint_source = 0
            return GLib.SOURCE_REMOVE
        values = self.collect()
        if values != self.state.get("draft"):
            self.state["draft"] = values
            save_state(self.run_dir, self.state)
        return GLib.SOURCE_CONTINUE

    def submit(self, values=None, *, action="submit", include_values=True, button=None):
        if self._finished or self._submitting or self.state["status"] == "submitted":
            return
        collected = (self.collect() if values is None else values) if include_values else {}
        if include_values and self._validator:
            message = self._validator(collected)
            if message is not None:
                self.message(message, error=True)
                return
        if self.live:
            self.live.close()
        self.state["message"] = format_response(self.state["spec"], collected, action, include_values=include_values)
        (self.run_dir / "message.md").write_text(self.state["message"], encoding="utf-8")
        self.checkpoint()
        finish_state(self.run_dir, self.state, "submitted", collected, action)
        if not self.state.get("origin"):
            self.close()
            return
        self.view.freeze_inputs()
        self.prepare_sending(button)
        self.start_delivery()

    def start_delivery(self, *, confirm_only=False):
        if self._finished or self._submitting:
            return
        self._submitting = True
        self._delivery_cancel.clear()
        self._retry_available = False
        if self._submit_button:
            self._submit_button.set_sensitive(False)
        self.set_sending(True)
        def send():
            try:
                operation = confirm_delivery if confirm_only else deliver
                operation(self.run_dir, self.state, self._delivery_cancel)
            except Exception as error:
                self.state["delivery"]["observation"] = {"status": "unconfirmed", "error": str(error)}
                save_state(self.run_dir, self.state)
            GLib.idle_add(self.delivery_finished)
        threading.Thread(target=send, daemon=False).start()

    def delivery_finished(self):
        if self._finished:
            return GLib.SOURCE_REMOVE
        self._submitting = False
        delivery = self.state["delivery"]
        if delivery.get("observation", {}).get("status") == "observed":
            self.finish_delivery()
        else:
            self._retry_available = (delivery["status"] in {"accepted", "unknown"}
                                     and "boundary_item_id" in delivery)
            self.set_sending(False)
            if self._submit_button:
                self._submit_button.set_sensitive(self._retry_available)
                self._submit_button.set_tooltip_text(
                    "Response not confirmed. Click to check again without resending."
                    if self._retry_available else "Delivery failed. Your answer is saved.")
                if not self._retry_available:
                    self._submit_overlay.get_child().set_opacity(1)
            toast = Adw.Toast.new("Response not confirmed. Your answer is saved.")
            self.toast_overlay.add_toast(toast)
        return GLib.SOURCE_REMOVE

    def finish_delivery(self):
        self.close()
        return GLib.SOURCE_REMOVE

    def dismiss(self):
        self._finish("dismissed", None)

    def defer(self):
        self._finish("deferred", None)

    def close(self):
        if self.live:
            self.live.close()
        self._delivery_cancel.set()
        self._finished = True
        self.set_sending(False)
        if self._checkpoint_source:
            GLib.source_remove(self._checkpoint_source)
        if self._layout_source:
            GLib.source_remove(self._layout_source)
        self.layout.close()
        self.presentation.cancel()
        for document in list(self.documents):
            document.close_document()
        self.style.close()
        self.window.destroy()
        self.app.quit()

    def _finish(self, status, values, action=None):
        if self._finished:
            return
        if self.state["status"] != "submitted":
            self.checkpoint()
            finish_state(self.run_dir, self.state, status, values, action)
        self.close()

    def _close(self, window):
        if self.state["status"] == "submitted":
            self.close()
        else:
            self.dismiss()
        return True

    def refit(self, width=None):
        return self.layout.fit(width)

    def open(self):
        self.view = View(self, self.state["spec"])
        self.set_content(self.view.build())
        self._built = True
        self.checkpoint()
        self.refit()
        self.presentation.initial()
        self.window.present()
        self.state["status"] = "open"
        from dialog_state import save_state
        save_state(self.run_dir, self.state)
        from dialog_live import LiveUpdates
        self.live = LiveUpdates(self)
        if os.environ.get('USER_DIALOG_DEBUG_LAYOUT') == '1':
            self._layout_source = GLib.timeout_add(50, self.trace_layout)
        GLib.idle_add(self.refit)
        GLib.idle_add(self._keyboard.opened)
        if self.state.get("render_image") and not self.state.get("origin"):
            GLib.timeout_add(300, self.render_image)

    def prune_widgets(self):
        """Drop detached view bookkeeping after a committed or rejected update."""
        for document in list(self.documents):
            if document.get_root() != self.window:
                document.close_document()
        self.style.prune(self.window)
        self._keyboard.prune()
        self.layout.prune()

    def trace_layout(self):
        """Opt-in geometry diagnostics; never records content or answers."""
        from dialog_reconcile import descendants
        records = []
        for path, (node, widget) in self.view.records.items():
            records.append({'path': list(path), 'type': node['type'], 'size': [widget.get_width(), widget.get_height()],
                            'mapped': widget.get_mapped(), 'opacity': widget.get_opacity(),
                            'documents': [[w.web.get_width(), w.web.get_height(), w._height, w.dialog_ready, w.metrics]
                                          for w in descendants(widget) if hasattr(w, 'dialog_ready')],
                            'text_views': [[w.get_width(), w.get_height(), w.get_vadjustment().get_value(),
                                            w.get_vadjustment().get_upper()]
                                           for w in descendants(widget) if isinstance(w, Gtk.TextView)]})
        result = {'window': [self.window.get_width(), self.window.get_height()],
                  'scroll': [self.scroller.get_vadjustment().get_value(), self.scroller.get_vadjustment().get_upper()],
                  'nodes': records}
        encoded = encode(result)
        if encoded != self._layout_last:
            with (self.run_dir / 'layout.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(encoded + '\n')
            self._layout_last = encoded
        return GLib.SOURCE_CONTINUE

    def render_image(self):
        """Export this renderer's own widget tree, without reading the desktop."""
        if self._finished:
            return GLib.SOURCE_REMOVE
        from dialog_layout import documents_ready
        if not documents_ready(self.content):
            return GLib.SOURCE_CONTINUE
        if self.presentation.busy:
            return GLib.SOURCE_CONTINUE
        paintable = Gtk.WidgetPaintable.new(self.window)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, self.window.get_width(), self.window.get_height())
        node = snapshot.to_node()
        if node is None:
            raise RuntimeError("Widget has no rendered content")
        texture = self.window.get_renderer().render_texture(node, None)
        path = Path(self.state["render_image"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not texture.save_to_png(str(path)):
            raise RuntimeError(f"Cannot save rendered widget: {path}")
        self.dismiss()
        return GLib.SOURCE_REMOVE


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
