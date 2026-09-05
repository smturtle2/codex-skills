"""Three distinct GTK4 visual designs for one multi-question request.

uv run --no-project --python /usr/bin/python3 python preview_gtk_designs.py
The selected interpreter needs PyGObject and GTK4. No libadwaita is used.
"""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk


CSS = """
window { font-family: sans-serif; font-size: 14px; }
.messenger { background: #f2f5f9; color: #263244; }
.messenger headerbar { background: white; box-shadow: none; border-bottom: 1px solid #e5eaf0; }
.messenger .avatar { background: #5264e9; color: white; border-radius: 22px; min-width: 42px; min-height: 42px; font-weight: 800; }
.messenger .bubble { background: white; border-radius: 3px 19px 19px 19px; padding: 17px 20px; }
.messenger .bubble label { color: #263244; }
.messenger .response { margin-left: 34px; }
.messenger .pick { border: 1px solid #ccd5e8; background: white; color: #405270; border-radius: 22px; padding: 10px 16px; box-shadow: none; }
.messenger .pick:checked { background: #5264e9; color: white; border-color: #5264e9; }
.messenger entry { background: white; border: 1px solid #dbe2ef; border-radius: 16px; padding: 9px 13px; color: #263244; }
.messenger textview, .messenger textview text { background: white; color: #263244; }
.messenger .input-frame { background: white; border: 1px solid #dbe2ef; border-radius: 16px; padding: 9px; }
.messenger .primary { background: #5264e9; color: white; border: 0; border-radius: 24px; padding: 13px 23px; font-weight: 700; }
.messenger .footer { background: white; border-top: 1px solid #e5eaf0; }
.messenger .muted { color: #788699; }
.editorial { background: #fbf8f1; color: #302e28; }
.editorial headerbar { background: #fbf8f1; border-bottom: 1px solid #d9d2c5; box-shadow: none; }
.editorial .hero { font-family: serif; font-size: 39px; font-weight: 400; letter-spacing: -1px; }
.editorial .eyebrow { color: #85715a; font-family: monospace; font-size: 11px; letter-spacing: 2px; }
.editorial .number { color: #a78157; font-family: serif; font-size: 29px; }
.editorial .pick { background: transparent; color: #3e382f; border: 1px solid #cfc3b0; border-radius: 0; padding: 17px; box-shadow: none; }
.editorial .pick:checked { background: #383a32; color: #fbf8f1; border-color: #383a32; }
.editorial entry { background: transparent; color: #302e28; border: 0; border-bottom: 1px solid #9d927f; border-radius: 0; padding: 11px 0; box-shadow: none; }
.editorial textview, .editorial textview text { background: #f3eee3; color: #302e28; }
.editorial .input-frame { background: #f3eee3; padding: 10px; border: 0; border-radius: 0; }
.editorial .primary { background: #383a32; color: #fbf8f1; border: 0; border-radius: 0; padding: 14px 24px; }
.editorial .footer { border-top: 1px solid #d9d2c5; }
.editorial .muted { color: #8b8172; }
.editorial separator { background: #d9d2c5; min-height: 1px; }
.dashboard { background: #111820; color: #dce6ed; font-size: 13px; }
.dashboard headerbar { background: #111820; color: #a8bac7; border-bottom: 1px solid #2b3a46; box-shadow: none; }
.dashboard .rail { background: #0b1118; border-right: 1px solid #2b3a46; }
.dashboard .rail-item { padding: 10px 13px; color: #91a3b5; font-family: monospace; }
.dashboard .active { background: #173941; color: #88e5d0; border-left: 3px solid #66d6bc; }
.dashboard .hero { font-size: 26px; font-weight: 750; }
.dashboard .eyebrow { font-family: monospace; color: #66d6bc; font-size: 11px; letter-spacing: 2px; }
.dashboard .tile { background: #19232e; border: 1px solid #2b3a46; border-radius: 8px; padding: 17px; }
.dashboard .pick { background: #101921; color: #b8cbd8; border: 1px solid #344959; border-radius: 5px; padding: 10px 13px; box-shadow: none; }
.dashboard .pick:checked { background: #1e494b; color: #9df2db; border-color: #66d6bc; }
.dashboard entry { background: #111a23; color: #dce6ed; border: 1px solid #344959; border-radius: 5px; padding: 8px 11px; }
.dashboard textview, .dashboard textview text { background: #111a23; color: #dce6ed; }
.dashboard .input-frame { background: #111a23; border: 1px solid #344959; border-radius: 5px; padding: 8px; }
.dashboard .primary { background: #66d6bc; color: #10221e; border: 0; border-radius: 5px; padding: 12px 19px; font-weight: 750; }
.dashboard .footer { background: #111820; border-top: 1px solid #2b3a46; }
.dashboard .muted { color: #8297a8; }
.dashboard .counter { font-family: monospace; font-size: 29px; color: #66d6bc; }
.title { font-size: 17px; font-weight: 700; }
.small { font-size: 11px; }
.bold { font-weight: 700; }
button.primary:disabled { opacity: 0.38; }
button:focus-visible, entry:focus-visible { outline: 2px solid #8f9df4; outline-offset: 2px; }
"""


def label(value, *classes):
    widget = Gtk.Label(label=value, xalign=0, wrap=True)
    for name in classes:
        widget.add_css_class(name)
    return widget


def col(spacing=12, margin=0):
    widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for side in ("top", "bottom", "start", "end"):
        getattr(widget, f"set_margin_{side}")(margin)
    return widget


def row(spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


class Design:
    def __init__(self, app, theme, name, width, height):
        self.theme = theme
        self.name = name
        self.selected = None
        self.counter = None
        self.window = Gtk.ApplicationWindow(application=app, title=name)
        self.window.add_css_class(theme)
        self.window.set_default_size(width, height)
        header = Gtk.HeaderBar()
        header.set_title_widget(label(name, "small", "bold"))
        self.window.set_titlebar(header)
        self.root = col(0)
        self.window.set_child(self.root)
        self.audience = Gtk.Entry(placeholder_text="예: 프로젝트를 처음 보는 팀원")
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.send = Gtk.Button(label="답변 보내기")
        self.send.add_css_class("primary")
        self.send.set_sensitive(False)
        self.send.connect("clicked", self.submit)
        self.audience.connect("changed", self.update)
        self.status = label("시각 시안 · 실제 작업에 적용되지 않습니다", "muted", "small")

    def choices(self):
        box = row(10)
        first = None
        for title in ("간단한 요약", "상세 보고서"):
            button = Gtk.ToggleButton(label=title, hexpand=True)
            button.add_css_class("pick")
            if first:
                button.set_group(first)
            first = button
            button.connect("toggled", self.choose, title)
            box.append(button)
        return box

    def choose(self, button, title):
        if button.get_active():
            self.selected = title
            self.update()

    def update(self, *args):
        count = int(bool(self.selected)) + int(bool(self.audience.get_text().strip()))
        self.send.set_sensitive(count == 2)
        if self.counter:
            self.counter.set_label(f"{count} / 2")

    def notes_field(self):
        frame = Gtk.Frame()
        frame.add_css_class("input-frame")
        pane = Gtk.ScrolledWindow(min_content_height=75)
        pane.set_child(self.notes)
        frame.set_child(pane)
        return frame

    def body(self, content):
        pane = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        pane.set_child(content)
        self.root.append(pane)

    def footer(self, title):
        box = col(10, 18)
        box.add_css_class("footer")
        actions = row()
        self.status.set_hexpand(True)
        actions.append(self.status)
        self.send.set_label(title)
        actions.append(self.send)
        box.append(actions)
        self.root.append(box)

    def submit(self, button):
        buffer = self.notes.get_buffer()
        print(json.dumps({"sample": self.theme, "answers": {
            "format": self.selected, "audience": self.audience.get_text(),
            "notes": buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        }}, ensure_ascii=False), flush=True)
        self.status.set_label("샘플 답변을 출력했습니다")

    def messenger(self):
        content = col(18, 24)
        identity = row(12)
        avatar = label("  C  ", "avatar")
        identity.append(avatar)
        name = col(3)
        name.append(label("Codex", "title"))
        name.append(label("codex-skills · 답변을 기다리는 중", "muted", "small"))
        identity.append(name)
        content.append(identity)
        bubble = col(7)
        bubble.add_css_class("bubble")
        bubble.append(label("마스터, 세 가지만 알려 주세요.", "title"))
        bubble.append(label("답변을 모아서 문서 작업을 이어갈게요."))
        content.append(bubble)
        for question, control in [
            ("어떤 형태로 정리할까요?", self.choices()),
            ("누가 읽을 문서인가요?", self.audience),
            ("더 부탁할 내용이 있나요? · 선택", self.notes_field()),
        ]:
            section = col(10)
            section.add_css_class("response")
            section.append(label(question, "bold"))
            section.append(control)
            content.append(section)
        self.body(content)
        self.footer("함께 보내기  ↑")

    def editorial(self):
        content = col(24, 34)
        content.append(label("CODEX  /  WORKING BRIEF", "eyebrow"))
        content.append(label("좋은 문서는\n좋은 질문에서.", "hero"))
        content.append(label("문서의 방향을 잡기 위한 짧은 브리프입니다.\n필요한 답변을 이 페이지에 담아 주세요.", "muted"))
        for index, question, control in [
            ("01", "문서의 깊이를 정해 주세요", self.choices()),
            ("02", "이 문서를 읽는 사람", self.audience),
            ("03", "남기고 싶은 부탁 · 선택", self.notes_field()),
        ]:
            content.append(Gtk.Separator())
            line = row(20)
            number = label(index, "number")
            number.set_valign(Gtk.Align.START)
            line.append(number)
            section = col(12)
            section.set_hexpand(True)
            section.append(label(question, "bold"))
            section.append(control)
            line.append(section)
            content.append(line)
        self.body(content)
        self.footer("브리프 전달하기  →")

    def dashboard(self):
        split = row(0)
        split.set_vexpand(True)
        rail = col(12, 18)
        rail.add_css_class("rail")
        rail.set_size_request(155, -1)
        rail.append(label("C / WORKSPACE", "eyebrow"))
        rail.append(label("codex-skills", "bold"))
        for title in ("문서 구성", "자료 · 참고", "결과물"):
            item = label(title, "rail-item")
            if title == "문서 구성":
                item.add_css_class("active")
            rail.append(item)
        space = Gtk.Box(vexpand=True)
        rail.append(space)
        rail.append(label("필수 답변", "muted", "small"))
        self.counter = label("0 / 2", "counter")
        rail.append(self.counter)
        split.append(rail)
        content = col(18, 24)
        content.set_hexpand(True)
        content.append(label("REQUEST  /  001", "eyebrow"))
        content.append(label("문서 작업 설정", "hero"))
        content.append(label("질문을 한곳에서 확인하고 작업을 재개하세요.", "muted"))
        first = col(12)
        first.add_css_class("tile")
        first.append(label("01   결과물 형식", "bold"))
        first.append(self.choices())
        content.append(first)
        second = col(12)
        second.add_css_class("tile")
        second.append(label("02   읽는 사람", "bold"))
        second.append(self.audience)
        content.append(second)
        third = col(12)
        third.add_css_class("tile")
        third.append(label("03   추가 요청", "bold"))
        third.append(self.notes_field())
        content.append(third)
        pane = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        pane.set_child(content)
        split.append(pane)
        self.root.append(split)
        self.footer("답변 제출  →")


app = Gtk.Application(application_id="local.codex.GtkVisualDesignSamples")
windows = []


def activate(application):
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for theme, name, width, height in [
        ("messenger", "GTK A · 메신저", 520, 750),
        ("editorial", "GTK B · 에디토리얼", 650, 830),
        ("dashboard", "GTK C · 워크스페이스", 820, 730),
    ]:
        design = Design(application, theme, name, width, height)
        getattr(design, theme)()
        windows.append(design)
        design.window.present()


app.connect("activate", activate)
app.run([sys.argv[0]])
