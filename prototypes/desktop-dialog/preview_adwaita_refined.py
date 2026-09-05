"""Subtle libadwaita variations, all preserving the same three-step UX.

uv run --no-project --python /usr/bin/python3 python preview_adwaita_refined.py
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from preview_adwaita import Sample, column, text


CSS = """
.refined-compact .title-1 { font-size: 21px; }
.refined-compact .subtitle { font-size: 12px; }
.refined-compact .step-label { font-size: 11px; font-weight: 600; }
.refined-airy .title-1 { font-size: 25px; font-weight: 650; }
.refined-airy .subtitle { font-size: 13px; line-height: 1.4; }
.refined-airy .step-label { font-size: 12px; }
.refined-focus .title-1 { font-size: 23px; }
.refined-focus .subtitle { font-size: 12px; }
.refined-focus .step-label { color: @accent_color; font-weight: 700; font-size: 11px; }
.refined-focus .section-icon { color: @accent_color; background: alpha(@accent_color, 0.09); border-radius: 12px; padding: 11px; }
"""


class Refined(Sample):
    def __init__(self, application, key, name, width, height):
        self.variant = key
        super().__init__(application, key, name, width, height)
        self.window.add_css_class(f"refined-{key}")
        self.window.set_title(name)
        self.preferred_width = width

    def intro(self, title, subtitle):
        box = column(8 if self.variant != "airy" else 12, 0)
        if self.variant == "focus":
            icon = Gtk.Image.new_from_icon_name("document-edit-symbolic")
            icon.set_pixel_size(24)
            icon.set_halign(Gtk.Align.START)
            icon.add_css_class("section-icon")
            box.append(icon)
        box.append(text(title, "title-1"))
        return box

    def notes_group(self):
        group = Adw.PreferencesGroup(title="03  추가 요청 · 선택", description="꼭 포함할 내용이나 원하는 말투를 적어 주세요.")
        frame = Gtk.Frame()
        self.notes.set_size_request(-1, 110)
        frame.set_child(self.notes)
        group.add(frame)
        return group

    def build(self):
        self.wizard(scroll_content=False)
        content = self.toolbar.get_content()
        inset = {"compact": 18, "airy": 32, "focus": 25}[self.variant]
        for side in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{side}")(inset)
        content.set_spacing({"compact": 15, "airy": 26, "focus": 20}[self.variant])
        self.step.add_css_class("step-label")
        # Stack transitions clip at their viewport. Native cards paint shadows
        # outside their measured bounds, so reserve space inside each page.
        child = content.get_first_child()
        while child:
            if isinstance(child, Gtk.Stack):
                for stack_page in child.get_pages():
                    page = stack_page.get_child()
                    page.set_margin_start(8)
                    page.set_margin_end(8)
                    page.set_margin_top(6)
                    page.set_margin_bottom(12)
            child = child.get_next_sibling()
        # The homogeneous stack measures all steps, including the final page.
        # Allow the window to contain their natural height instead of clipping
        # them into an arbitrarily sized scrolling viewport.
        minimum, natural, _, _ = self.toolbar.measure(Gtk.Orientation.VERTICAL, self.preferred_width)
        self.window.set_default_size(self.preferred_width, max(minimum, natural) + 32)
        self.window.present()


application = Adw.Application(application_id="local.codex.AdwaitaRefinedSamples")
windows = []


def activate(app):
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    variants = [
        ("compact", "A · 아담하게", 470, 500),
        ("airy", "B · 여유롭게", 550, 620),
        ("focus", "C · 은은한 강조", 510, 580),
    ]
    for key, name, width, height in (variants if "--all" in sys.argv else variants[:1]):
        sample = Refined(app, key, name, width, height)
        windows.append(sample)
        sample.build()


if __name__ == "__main__":
    application.connect("activate", activate)
    application.run([sys.argv[0]])
