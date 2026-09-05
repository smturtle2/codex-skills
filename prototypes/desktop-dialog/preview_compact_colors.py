"""Compact libadwaita palette and subtle styling explorations."""

import sys

from preview_adwaita_refined import Adw, Gdk, Gtk, Refined, CSS, column, text


PALETTES = """
.palette-blue {
  --accent-bg-color: #3584e4;
  --accent-fg-color: #ffffff;
  --accent-color: #1c71d8;
}
.palette-sage {
  --accent-bg-color: #4e806a;
  --accent-fg-color: #ffffff;
  --accent-color: #3b7058;
}
.palette-sage .step-label {
  color: var(--accent-color);
  background: alpha(var(--accent-bg-color), 0.08);
  border-radius: 8px;
  padding: 7px 10px;
}
.palette-sage .title-1 { font-weight: 600; }
.palette-sage .boxed-list { border-radius: 14px; }
.palette-sage button.suggested-action { border-radius: 18px; }
.palette-plum {
  --accent-bg-color: #865479;
  --accent-fg-color: #ffffff;
  --accent-color: #7d466e;
}
.palette-plum .step-label { color: var(--accent-color); font-weight: 700; }
.palette-plum .title-1 { font-size: 22px; }
.palette-plum .section-heading {
  border-left: 3px solid var(--accent-bg-color);
  padding-left: 12px;
}
.palette-plum progressbar progress { min-height: 3px; }
.palette-plum progressbar trough { min-height: 3px; }
"""


class ColorSample(Refined):
    def __init__(self, app, palette, name):
        self.palette = palette
        super().__init__(app, "compact", name, 480, 540)
        self.window.add_css_class(f"palette-{palette}")

    def intro(self, title, subtitle):
        box = column(0, 0)
        if self.palette == "plum":
            box.add_css_class("section-heading")
        box.append(text(title, "title-1"))
        return box


app = Adw.Application(application_id="local.codex.CompactColorPreviews")
windows = []


def activate(application):
    provider = Gtk.CssProvider()
    provider.load_from_data((CSS + PALETTES).encode())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for palette, name in [("blue", "A · 블루 / 기본"),
                          ("sage", "B · 세이지 / 부드럽게"),
                          ("plum", "C · 플럼 / 또렷하게")]:
        sample = ColorSample(application, palette, name)
        windows.append(sample)
        sample.build()


app.connect("activate", activate)
app.run([sys.argv[0]])
