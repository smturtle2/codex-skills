"""Four libadwaita layouts for the same multi-question request.

uv run --no-project --python /usr/bin/python3 python preview_adwaita.py
Requires GTK4/libadwaita and PyGObject in the chosen interpreter.
"""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk


def column(spacing=16, margin=24):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(margin)
    return box


def text(value, css=None):
    label = Gtk.Label(label=value, xalign=0, wrap=True)
    if css:
        label.add_css_class(css)
    return label


def scroll(child):
    pane = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    pane.set_child(child)
    return pane


class Sample:
    def __init__(self, app, number, name, width, height):
        self.number = number
        self.choice = None
        self.window = Adw.ApplicationWindow(application=app)
        self.window.set_title(f"GTK 시안 {number} · {name}")
        self.window.set_default_size(width, height)
        self.toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=name, subtitle="codex-skills"))
        self.toolbar.add_top_bar(header)
        self.window.set_content(self.toolbar)
        self.audience = Adw.EntryRow(title="누가 읽는 문서인가요?")
        self.audience.connect("changed", lambda *args: self.update())
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.notes.set_top_margin(12)
        self.notes.set_bottom_margin(12)
        self.notes.set_left_margin(12)
        self.notes.set_right_margin(12)
        self.status = text("", "dim-label")
        self.status.set_visible(False)
        self.send = Gtk.Button(label="한 번에 보내기")
        self.send.add_css_class("suggested-action")
        self.send.set_sensitive(False)
        self.send.connect("clicked", self.submit)
        self.summary = None
        self.step = None

    def update(self):
        ready = bool(self.choice and self.audience.get_text().strip())
        self.send.set_sensitive(ready)
        if self.summary:
            self.summary.set_label(f"형식   {self.choice or '아직 선택하지 않았어요'}\n\n대상   {self.audience.get_text() or '아직 입력하지 않았어요'}")

    def submit(self, button):
        buffer = self.notes.get_buffer()
        print(json.dumps({"sample": self.number, "answers": {
            "format": self.choice, "audience": self.audience.get_text(),
            "notes": buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False),
        }}, ensure_ascii=False), flush=True)
        self.status.set_label("답변을 받았습니다.")
        self.status.set_visible(True)

    def format_group(self):
        group = Adw.PreferencesGroup(title="01  결과물 형식")
        previous = None
        for name, desc in [("간단한 요약", "핵심 결론을 빠르게 읽는 한 페이지"),
                           ("상세 보고서", "배경과 근거까지 함께 읽는 문서")]:
            row = Adw.ActionRow(title=name, subtitle=desc)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if previous:
                check.set_group(previous)
            previous = check
            check.connect("toggled", lambda item, value=name: self.choose(item, value))
            row.add_prefix(check)
            row.set_activatable_widget(check)
            group.add(row)
        return group

    def choose(self, item, value):
        if item.get_active():
            self.choice = value
            self.update()

    def audience_group(self):
        group = Adw.PreferencesGroup(title="02  읽는 사람", description="예: 프로젝트를 처음 보는 팀원")
        group.add(self.audience)
        return group

    def notes_group(self):
        group = Adw.PreferencesGroup(title="03  추가 요청 · 선택", description="꼭 포함할 내용이나 원하는 말투를 적어 주세요.")
        frame = Gtk.Frame()
        pane = Gtk.ScrolledWindow(min_content_height=95)
        pane.set_child(self.notes)
        frame.set_child(pane)
        group.add(frame)
        return group

    def footer(self):
        box = column(10, 18)
        box.append(self.status)
        row = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        close = Gtk.Button(label="닫기")
        close.connect("clicked", lambda *args: self.window.close())
        row.append(close)
        row.append(self.send)
        box.append(row)
        self.toolbar.add_bottom_bar(box)

    def intro(self, title, subtitle):
        box = column(7, 0)
        box.append(text(title, "title-1"))
        box.append(text(subtitle, "dim-label"))
        return box

    def form(self):
        box = column(22)
        box.append(self.intro("작업 전에 알려 주세요", "codex-skills · 필요한 내용을 한눈에 확인합니다."))
        box.append(self.format_group())
        box.append(self.audience_group())
        box.append(self.notes_group())
        self.toolbar.set_content(scroll(box))
        self.footer()

    def wizard(self, scroll_content=True):
        box = column(22)
        progress = Gtk.ProgressBar(fraction=1 / 3)
        box.append(progress)
        self.step = text("1 / 3 · 결과물 형식", "dim-label")
        box.append(self.step)
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand=True)
        titles = ["어떤 형태로 정리할까요?", "누가 읽을 예정인가요?", "추가로 부탁할 것이 있나요?"]
        for index, widget in enumerate([self.format_group(), self.audience_group(), self.notes_group()]):
            page = column(28, 0)
            page.append(self.intro(titles[index], "입력한 내용은 이전·다음으로 이동해도 유지됩니다."))
            page.append(widget)
            stack.add_named(page, str(index))
        box.append(stack)
        row = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        previous = Gtk.Button(label="이전")
        following = Gtk.Button(label="다음")
        previous.set_sensitive(False)
        def move(delta):
            index = max(0, min(2, int(stack.get_visible_child_name()) + delta))
            stack.set_visible_child_name(str(index))
            progress.set_fraction((index + 1) / 3)
            self.step.set_label(f"{index + 1} / 3 · {['결과물 형식', '읽는 사람', '추가 요청'][index]}")
            previous.set_sensitive(index > 0)
            following.set_sensitive(index < 2)
            self.send.set_visible(index == 2)
        previous.connect("clicked", lambda *args: move(-1))
        following.connect("clicked", lambda *args: move(1))
        row.append(previous)
        row.append(following)
        box.append(row)
        self.toolbar.set_content(scroll(box) if scroll_content else box)
        self.footer()
        self.send.set_visible(False)

    def compare(self):
        box = column(22)
        box.append(self.intro("나란히 보고 선택하세요", "문서 방향을 고른 뒤, 아래에서 세부 요청을 함께 답합니다."))
        cards = Gtk.Box(spacing=16, homogeneous=True)
        previous = None
        for name, icon, copy in [("간단한 요약", "view-list-symbolic", "한 페이지\n핵심 결론 중심\n빠른 공유에 적합"),
                                  ("상세 보고서", "text-x-generic-symbolic", "여러 페이지\n배경과 근거 포함\n차근차근 검토")]:
            card = column(14, 20)
            card.add_css_class("card")
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_pixel_size(40)
            image.set_halign(Gtk.Align.START)
            card.append(image)
            card.append(text(name, "title-2"))
            card.append(text(copy, "dim-label"))
            check = Gtk.CheckButton(label="이 형식 선택")
            if previous:
                check.set_group(previous)
            previous = check
            check.connect("toggled", lambda item, value=name: self.choose(item, value))
            card.append(check)
            cards.append(card)
        box.append(cards)
        box.append(self.audience_group())
        box.append(self.notes_group())
        self.toolbar.set_content(scroll(box))
        self.footer()

    def sidebar(self):
        split = Gtk.Box()
        left = column(22, 22)
        left.set_size_request(210, -1)
        left.add_css_class("view")
        left.append(text("문서 구성", "title-2"))
        left.append(text("codex-skills", "dim-label"))
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        navigator = Gtk.StackSidebar(stack=stack, vexpand=True)
        left.append(navigator)
        left.append(text("현재 답변", "heading"))
        self.summary = text("", "dim-label")
        left.append(self.summary)
        split.append(left)
        split.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        for index, (title, widget) in enumerate([
            ("결과물 형식", self.format_group()),
            ("읽는 사람", self.audience_group()),
            ("추가 요청", self.notes_group()),
        ]):
            page = column(26, 30)
            page.append(self.intro(title, "섹션을 자유롭게 오가며 답변을 완성하세요."))
            page.append(widget)
            stack.add_titled(scroll(page), str(index), title)
        split.append(stack)
        self.toolbar.set_content(split)
        self.footer()
        self.update()


app = Adw.Application(application_id="local.codex.AdwaitaLayoutSamples")
samples = []


def activate(application):
    for number, name, width, height, method in [
        ("A", "한 페이지 폼", 510, 740, "form"),
        ("B", "단계별 입력", 520, 600, "wizard"),
        ("C", "비교·선택", 680, 760, "compare"),
        ("D", "사이드바 작업창", 790, 570, "sidebar"),
    ]:
        sample = Sample(application, number, name, width, height)
        getattr(sample, method)()
        samples.append(sample)
        sample.window.present()


if __name__ == "__main__":
    app.connect("activate", activate)
    app.run([sys.argv[0]])
