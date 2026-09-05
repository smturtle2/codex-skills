# /// script
# requires-python = ">=3.11"
# dependencies = ["PySide6-Essentials>=6.8,<7"]
# ///
"""Visual samples for desktop communication; no production transport.

Run locally: uv run --script skills/desktop-dialog/scripts/preview_dialog.py
These are interactive visual samples; selections do not change settings.
"""

import json
from pathlib import Path
import sys

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
        QVBoxLayout, QWidget, QTextEdit,
    )
except ImportError:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
        QVBoxLayout, QWidget, QTextEdit,
    )


class Header(QFrame):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()


THEMES = [
    dict(id="A", name="Quiet card", subtitle="차분한 라이트 카드", bg="#FFFFFF",
         fg="#202723", muted="#7A827D", accent="#28785B", soft="#EFF5F1", line="#E2E8E3"),
    dict(id="B", name="Night console", subtitle="선명한 다크 패널", bg="#171B24",
         fg="#F0F3FA", muted="#939CAE", accent="#ABBFFF", soft="#252E43", line="#343D50"),
    dict(id="C", name="Warm note", subtitle="따뜻한 메모 스타일", bg="#FFF8E9",
         fg="#493B2D", muted="#91816C", accent="#99512D", soft="#F4E8D1", line="#E7D7B8"),
    dict(id="D", name="Signal", subtitle="강조색이 있는 컴팩트 패널", bg="#F5F3FF",
         fg="#2D2445", muted="#81758F", accent="#7050CC", soft="#E8E1FA", line="#DCD3F0"),
]


def label(text, size, color, bold=False):
    item = QLabel(text)
    item.setWordWrap(True)
    item.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:{700 if bold else 400}; background:transparent; border:0;")
    return item


class Preview(QWidget):
    def __init__(self, theme):
        super().__init__()
        t = theme
        self.setWindowTitle(f"UI 시안 {t['id']} · {t['name']}")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(f"QFrame#panel {{background:{t['bg']}; border:1px solid {t['line']}; border-radius:{8 if t['id'] == 'B' else 20}px;}}")
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 18, 26, 22)
        layout.setSpacing(12)
        header = Header()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(label(f"{t['id']}  /  {t['name']}", 12, t['accent'], True))
        row.addStretch()
        close = QPushButton("×")
        close.setFixedSize(28, 28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"border:0; background:transparent; color:{t['muted']}; font-size:22px;")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addWidget(header)
        if t['id'] == 'D':
            bar = label("  ●  YOUR INPUT IS NEEDED", 11, "#FFFFFF", True)
            bar.setStyleSheet(f"background:{t['accent']}; color:white; border-radius:7px; padding:9px; font-size:11px; font-weight:700;")
            layout.addWidget(bar)
        else:
            layout.addWidget(label("CODEX  /  codex-skills" if t['id'] == 'B' else "Codex · codex-skills", 11, t['muted']))
        layout.addWidget(label("작업 전에 세 가지만 알려 주세요", 22, t['fg'], True))
        layout.addWidget(label("한 번에 답하면 문서 구성을 이어서 정리하겠습니다.", 12, t['muted']))
        layout.addWidget(label("01  결과물은 어느 정도로 정리할까요?", 13, t['fg'], True))
        choices = QHBoxLayout() if t['id'] in ('A', 'D') else QVBoxLayout()
        choices.setSpacing(8)
        self.selected = None
        self.options = []
        for text in ("간단한 요약", "자세한 설명"):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
            button.setStyleSheet(f"QPushButton {{background:{t['bg']}; color:{t['fg']}; border:1px solid {t['line']}; border-radius:9px; padding:8px 14px; text-align:left; font-size:13px;}} QPushButton:hover {{background:{t['soft']};}} QPushButton:checked {{background:{t['soft']}; border:1px solid {t['accent']}; color:{t['accent']};}}")
            button.clicked.connect(lambda checked, b=button: self.select(b))
            self.options.append(button)
            choices.addWidget(button)
        layout.addLayout(choices)
        layout.addWidget(label("02  누가 읽는 문서인가요?", 13, t['fg'], True))
        self.audience = QTextEdit()
        self.audience.setPlaceholderText("예: 프로젝트를 처음 보는 팀원")
        self.audience.setFixedHeight(58)
        self.audience.setStyleSheet(f"background:{t['bg']}; color:{t['fg']}; border:1px solid {t['line']}; border-radius:8px; padding:8px; font-size:13px;")
        layout.addWidget(self.audience)
        layout.addWidget(label("03  꼭 포함할 내용이 있나요?  ·  선택", 13, t['fg'], True))
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("자유롭게 적어 주세요.")
        self.notes.setFixedHeight(65)
        self.notes.setStyleSheet(self.audience.styleSheet())
        layout.addWidget(self.notes)
        self.audience.textChanged.connect(lambda: self.send.setEnabled(bool(self.selected and self.audience.toPlainText().strip())))
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(label("UI 미리보기 · 설정은 바뀌지 않습니다", 10, t['muted']))
        footer.addStretch()
        self.send = QPushButton("한 번에 보내기  →")
        self.send.setEnabled(False)
        self.send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send.setStyleSheet(f"QPushButton {{background:{t['accent']}; color:{'#171B24' if t['id'] == 'B' else '#FFFFFF'}; border:0; border-radius:9px; padding:11px 15px; font-size:12px; font-weight:700;}} QPushButton:disabled {{background:{t['soft']}; color:{t['muted']};}}")
        self.send.clicked.connect(lambda: self.submit(t))
        footer.addWidget(self.send)
        layout.addLayout(footer)

    def select(self, button):
        for other in self.options:
            other.setChecked(other is button)
        self.selected = button.text()
        self.send.setEnabled(bool(self.audience.toPlainText().strip()))

    def submit(self, theme):
        print(json.dumps({"sample": theme['id'], "answers": {"format": self.selected, "audience": self.audience.toPlainText(), "notes": self.notes.toPlainText()}}, ensure_ascii=False), flush=True)
        self.send.setText("전송됨 ✓")
        self.send.setEnabled(False)


class Pattern(QWidget):
    def __init__(self, index):
        super().__init__()
        names = ["작은 호출 카드", "바로 답하는 카드", "상세 검토창", "대기 질문 패널"]
        sizes = [(380, 210), (460, 430), (530, 510), (360, 510)]
        self.setWindowTitle(f"구조 시안 {index + 1} · {names[index]}")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(*sizes[index])
        self.setStyleSheet("QWidget {background:#FAFBFC; color:#26322E;} QPushButton {background:#EAF1ED; border:1px solid #D9E5DE; border-radius:8px; padding:10px 14px; font-size:12px;} QPushButton:hover {background:#DDEBE3;} QTextEdit {background:white; border:1px solid #CDDCD3; border-radius:10px; padding:10px; font-size:14px;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 22)
        root.setSpacing(12)
        head = Header()
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(label(f"{index + 1:02d}  /  {names[index]}", 11, "#5A7969", True))
        h.addStretch()
        x = QPushButton("×")
        x.setFixedSize(30, 30)
        x.setStyleSheet("border:0; padding:0; font-size:20px;")
        x.clicked.connect(self.close)
        h.addWidget(x)
        root.addWidget(head)
        root.addWidget(label("Codex  ·  codex-skills  ·  UI 샘플", 10, "#819188"))
        self.feedback = label("", 11, "#28785B")

        def actions(items):
            row = QHBoxLayout()
            for text in items:
                b = QPushButton(text)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda checked, name=text: self.feedback.setText(f"‘{name}’ 선택 · 샘플 동작입니다"))
                row.addWidget(b)
            root.addLayout(row)

        if index == 0:
            root.addWidget(label("답변을 기다리고 있어요", 21, "#203D2F", True))
            root.addWidget(label("결과물 형식을 선택하면 작업을 이어갑니다.", 12, "#64796D"))
            actions(["질문 보기", "나중에"])
        elif index == 1:
            root.addWidget(label("어떤 결과물이 필요하세요?", 22, "#203D2F", True))
            root.addWidget(label("공유 대상에 맞춰 문서의 길이를 정하려고 합니다.", 13, "#64796D"))
            actions(["한 페이지 요약", "상세 보고서"])
            root.addWidget(label("또는 직접 알려 주세요", 11, "#64796D"))
            editor = QTextEdit()
            editor.setPlaceholderText("예: 팀에 공유할 거라 결론과 근거만 짧게 정리해 줘.")
            root.addWidget(editor)
            actions(["나중에", "답변 보내기"])
        elif index == 2:
            root.addWidget(label("이 구성으로 정리할까요?", 23, "#203D2F", True))
            root.addWidget(label("결정 전에 맥락과 결과를 함께 확인하는 화면", 12, "#64796D"))
            detail = QFrame()
            detail.setStyleSheet("QFrame {background:#EFF4F1; border-radius:12px;}")
            content = QVBoxLayout(detail)
            content.setContentsMargins(18, 16, 18, 16)
            for heading, body in [("제안", "요약 → 주요 근거 → 다음 단계"),
                                  ("이유", "팀원이 짧게 읽고 결정을 내릴 수 있도록 합니다."),
                                  ("결과물", "공유용 문서 한 개 · 약 2페이지")]:
                content.addWidget(label(heading, 11, "#678473", True))
                content.addWidget(label(body, 14, "#263B30"))
            root.addWidget(detail)
            editor = QTextEdit()
            editor.setPlaceholderText("바꾸고 싶은 부분이 있다면 적어 주세요.")
            editor.setMaximumHeight(80)
            root.addWidget(editor)
            actions(["수정 요청", "이 구성 사용"])
        else:
            root.addWidget(label("기다리는 질문  3", 24, "#203D2F", True))
            root.addWidget(label("돌아왔을 때 한곳에서 이어서 답합니다.", 12, "#64796D"))
            for title, body in [("codex-skills", "팝업 디자인을 선택해 주세요"),
                                ("팀 공유 문서", "누가 읽는 문서인가요?"),
                                ("이미지 작업", "사용할 원본 이미지가 필요해요")]:
                card = QPushButton(f"{title}\n\n{body}    →")
                card.setMinimumHeight(80)
                card.setStyleSheet("text-align:left; background:white; border:1px solid #DDE7E1; border-radius:10px; padding:14px;")
                card.clicked.connect(lambda checked, name=title: self.feedback.setText(f"{name} · 질문 열기 미리보기"))
                root.addWidget(card)
            actions(["지금은 접어두기"])
        root.addStretch()
        root.addWidget(self.feedback)


app = QApplication(sys.argv)
app.setFont(QFont("Noto Sans CJK KR", 10))
area = app.primaryScreen().availableGeometry()
windows = []
for index, theme in enumerate(THEMES):
    window = Pattern(index) if "--patterns" in sys.argv else Preview(theme)
    window.move(area.x() + max(0, (area.width() - 2020) // 2) + index * 505,
                area.y() + max(0, (area.height() - 560) // 2))
    window.show()
    windows.append(window)
if "--capture-dir" in sys.argv:
    destination = Path(sys.argv[sys.argv.index("--capture-dir") + 1])
    destination.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    for index, window in enumerate(windows):
        window.grab().save(str(destination / f"sample-{index + 1}.png"))
    sys.exit(0)
sys.exit(app.exec())
