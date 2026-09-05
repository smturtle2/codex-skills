"""Compare actual Qt Widgets, GTK/libadwaita and Tk/ttk implementations.

Use the local interpreter containing the selected GUI library through uv:
uv run --no-project --python /usr/bin/python3 python preview_libraries.py qt
Other backends: gtk, tk. These are visual prototypes, not production requests.
"""

import json
import sys


def report(backend, format_value, audience, notes):
    print(json.dumps({"sample": backend, "format": format_value,
                      "audience": audience, "notes": notes}, ensure_ascii=False), flush=True)


def qt():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
        QRadioButton, QButtonGroup, QLineEdit, QTextEdit, QPushButton,
    )
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("01 · Qt Widgets — 분할형 작업 패널")
    window.resize(720, 490)
    window.setStyleSheet("QWidget {font-size:14px; color:#E6ECF5; background:#161D2A;} QLineEdit, QTextEdit {background:#222C3C; border:1px solid #39465B; border-radius:7px; padding:9px;} QPushButton {padding:10px 18px; border-radius:7px; background:#304566;} QPushButton:disabled {color:#76859A;} QRadioButton {padding:9px;}")
    root = QHBoxLayout(window)
    root.setContentsMargins(0, 0, 0, 0)
    sidebar = QFrame()
    sidebar.setFixedWidth(210)
    sidebar.setStyleSheet("QFrame {background:#101622;}")
    left = QVBoxLayout(sidebar)
    left.setContentsMargins(24, 30, 20, 24)
    for text in ["CODEX / REQUEST", "문서 구성", "codex-skills", "", "01   결과물 형식", "02   읽는 사람", "03   추가 요청"]:
        left.addWidget(QLabel(text))
    left.addStretch()
    left.addWidget(QLabel("Qt Widgets\n분할형 작업 패널"))
    root.addWidget(sidebar)
    right = QVBoxLayout()
    right.setContentsMargins(28, 24, 28, 24)
    heading = QLabel("작업 방향을 알려 주세요")
    heading.setStyleSheet("font-size:23px; font-weight:700;")
    right.addWidget(heading)
    right.addWidget(QLabel("세 가지 답변을 한 번에 전달합니다."))
    right.addSpacing(10)
    right.addWidget(QLabel("결과물 형식"))
    options = QHBoxLayout()
    group = QButtonGroup(window)
    for text in ["간단한 요약", "상세 보고서"]:
        item = QRadioButton(text)
        group.addButton(item)
        options.addWidget(item)
    right.addLayout(options)
    right.addWidget(QLabel("읽는 사람"))
    audience = QLineEdit()
    audience.setPlaceholderText("예: 프로젝트를 처음 보는 팀원")
    right.addWidget(audience)
    right.addWidget(QLabel("추가 요청 · 선택"))
    notes = QTextEdit()
    notes.setPlaceholderText("꼭 포함할 내용이나 원하는 말투")
    right.addWidget(notes)
    status = QLabel("디자인 샘플 · 실제 작업에는 적용되지 않습니다")
    status.setStyleSheet("font-size:11px; color:#9AAABD;")
    right.addWidget(status)
    row = QHBoxLayout()
    cancel = QPushButton("닫기")
    cancel.clicked.connect(window.close)
    send = QPushButton("답변 보내기  →")
    send.setEnabled(False)
    send.setStyleSheet("background:#AEC9FF; color:#142540; font-weight:700;")
    def validate():
        send.setEnabled(bool(group.checkedButton() and audience.text().strip()))
    group.buttonClicked.connect(validate)
    audience.textChanged.connect(validate)
    def submit():
        report("qt", group.checkedButton().text(), audience.text(), notes.toPlainText())
        status.setText("샘플 답변을 출력했습니다.")
    send.clicked.connect(submit)
    row.addWidget(cancel)
    row.addStretch()
    row.addWidget(send)
    right.addLayout(row)
    root.addLayout(right)
    area = app.primaryScreen().availableGeometry()
    window.move(area.x() + 30, area.y() + 80)
    window.show()
    app.exec()


def gtk():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk
    app = Adw.Application(application_id="local.codex.DialogLibraryPreview")
    def activate(app):
        window = Adw.ApplicationWindow(application=app)
        window.set_title("02 · GTK / libadwaita — 네이티브 카드 폼")
        window.set_default_size(500, 570)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="문서 구성", subtitle="GTK / libadwaita"))
        toolbar.add_top_bar(header)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(24)
        title = Gtk.Label(label="작업 방향을 알려 주세요", xalign=0)
        title.add_css_class("title-1")
        box.append(title)
        description = Gtk.Label(label="codex-skills · 세 가지 답변을 한 번에 전달합니다.", xalign=0, wrap=True)
        description.add_css_class("dim-label")
        box.append(description)
        required = Adw.PreferencesGroup(title="필요한 정보")
        model = Gtk.StringList.new(["선택해 주세요", "간단한 요약", "상세 보고서"])
        format_row = Adw.ComboRow(title="결과물 형식", model=model)
        required.add(format_row)
        audience = Adw.EntryRow(title="읽는 사람")
        required.add(audience)
        box.append(required)
        optional = Adw.PreferencesGroup(title="추가 요청", description="원하는 말투나 꼭 포함할 내용 · 선택")
        notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        notes.set_top_margin(12)
        notes.set_left_margin(12)
        notes.set_right_margin(12)
        scroll = Gtk.ScrolledWindow(min_content_height=110)
        scroll.set_child(notes)
        frame = Gtk.Frame()
        frame.set_child(scroll)
        optional.add(frame)
        box.append(optional)
        status = Gtk.Label(label="디자인 샘플 · 실제 작업에는 적용되지 않습니다", wrap=True)
        status.add_css_class("dim-label")
        box.append(status)
        send = Gtk.Button(label="답변 보내기")
        send.add_css_class("suggested-action")
        send.add_css_class("pill")
        send.set_halign(Gtk.Align.END)
        send.set_sensitive(False)
        def validate(*args):
            send.set_sensitive(format_row.get_selected() > 0 and bool(audience.get_text().strip()))
        format_row.connect("notify::selected", validate)
        audience.connect("changed", validate)
        def submit(button):
            buffer = notes.get_buffer()
            report("gtk", model.get_string(format_row.get_selected()), audience.get_text(),
                   buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))
            status.set_text("샘플 답변을 출력했습니다.")
        send.connect("clicked", submit)
        box.append(send)
        toolbar.set_content(box)
        window.set_content(toolbar)
        window.present()
    app.connect("activate", activate)
    app.run([sys.argv[0]])


def tk():
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    window.title("03 · Tk / ttk — 클래식 대화상자")
    window.geometry("590x490+1250+120")
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", font=("sans-serif", 11))
    outer = ttk.Frame(window, padding=22)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="문서 구성", font=("sans-serif", 21, "bold")).pack(anchor="w")
    ttk.Label(outer, text="codex-skills  |  Tk / ttk", padding=(0, 6, 0, 16)).pack(anchor="w")
    notebook = ttk.Notebook(outer)
    notebook.pack(fill="both", expand=True)
    form = ttk.Frame(notebook, padding=18)
    extra = ttk.Frame(notebook, padding=18)
    notebook.add(form, text="  기본 정보  ")
    notebook.add(extra, text="  추가 요청 (선택)  ")
    format_value = tk.StringVar()
    audience = tk.StringVar()
    group = ttk.LabelFrame(form, text="결과물 형식", padding=14)
    group.pack(fill="x", pady=(0, 20))
    for text in ["간단한 요약", "상세 보고서"]:
        ttk.Radiobutton(group, text=text, variable=format_value, value=text).pack(anchor="w", pady=5)
    ttk.Label(form, text="읽는 사람").pack(anchor="w", pady=(0, 8))
    ttk.Entry(form, textvariable=audience, font=("sans-serif", 12)).pack(fill="x")
    ttk.Label(extra, text="꼭 포함할 내용이나 원하는 말투").pack(anchor="w", pady=(0, 10))
    notes = tk.Text(extra, height=6, font=("sans-serif", 12), wrap="word", relief="solid", borderwidth=1)
    notes.pack(fill="both", expand=True)
    status = tk.StringVar(value="디자인 샘플 · 실제 작업에는 적용되지 않습니다")
    ttk.Label(outer, textvariable=status, padding=(0, 14, 0, 10)).pack(anchor="w")
    buttons = ttk.Frame(outer)
    buttons.pack(fill="x")
    def submit():
        report("tk", format_value.get(), audience.get(), notes.get("1.0", "end-1c"))
        status.set("샘플 답변을 출력했습니다.")
    send = ttk.Button(buttons, text="답변 보내기", command=submit, state="disabled")
    send.pack(side="right")
    ttk.Button(buttons, text="닫기", command=window.destroy).pack(side="right", padx=8)
    def validate(*args):
        send.configure(state="normal" if format_value.get() and audience.get().strip() else "disabled")
    format_value.trace_add("write", validate)
    audience.trace_add("write", validate)
    window.mainloop()


if __name__ == "__main__":
    backends = {"qt": qt, "gtk": gtk, "tk": tk}
    if len(sys.argv) != 2 or sys.argv[1] not in backends:
        raise SystemExit("Choose one backend: qt | gtk | tk")
    backends[sys.argv[1]]()
