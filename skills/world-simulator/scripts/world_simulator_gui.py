#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import http.server
import json
import locale
import mimetypes
import os
import pathlib
import sys
import time
import urllib.parse
import webbrowser
from typing import Any

DEFAULT_ROOT = pathlib.Path("world-runs")
DEFAULT_SESSION = "default-world"
SESSION_DIRS = ("current", "world", "player", "story", "gm", "turns", "ui", "assets")
DEFAULT_THEME = {
    "app_background": "#f6f9ff",
    "panel_background": "#ffffff",
    "status_background": "#eef5ff",
    "input_background": "#ffffff",
    "text": "#102033",
    "muted_text": "#617089",
    "accent": "#2563eb",
    "accent_2": "#0891b2",
    "border": "#cbd9ee",
    "selection": "#bfdbfe",
    "button_text": "#ffffff",
    "disabled_background": "#e5edf8",
    "disabled_text": "#7b8798",
}


class WorldSimulatorError(ValueError):
    pass


def prepare_text_input_environment() -> None:
    lang = os.environ.get("LANG", "")
    lc_all = os.environ.get("LC_ALL", "")
    lc_ctype = os.environ.get("LC_CTYPE", "")

    if lc_all in {"C", "POSIX", "C.UTF-8", "C.utf8"} and lang and lang not in {"C", "POSIX"}:
        os.environ.pop("LC_ALL", None)
    if lang.lower().endswith(("utf-8", "utf8")) and lc_ctype in {"", "C", "POSIX", "C.UTF-8", "C.utf8"}:
        os.environ["LC_CTYPE"] = lang

    im_values = " ".join(
        os.environ.get(name, "")
        for name in ("GTK_IM_MODULE", "QT_IM_MODULE", "INPUT_METHOD", "XMODIFIERS")
    ).lower()
    if "fcitx" in im_values:
        os.environ.setdefault("XMODIFIERS", "@im=fcitx")

    try:
        locale.setlocale(locale.LC_CTYPE, "")
    except locale.Error:
        pass


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def atomic_write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def atomic_write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_session(root: pathlib.Path, session: str) -> pathlib.Path:
    session_path = pathlib.Path(session)
    if session_path.is_absolute() or len(session_path.parts) > 1:
        return session_path
    return root / session


def ui_path(session_path: pathlib.Path, name: str) -> pathlib.Path:
    return session_path / "ui" / name


def default_interface_language() -> str:
    language_sources = " ".join(
        value for value in (os.environ.get("LANG"), os.environ.get("LANGUAGE")) if value
    ).lower()
    if language_sources.startswith("ko") or ":ko" in language_sources:
        return "ko"
    return "en"


def normalized_language(value: Any) -> str:
    language = str(value or "").strip().lower()
    if language.startswith("ko"):
        return "ko"
    return "en"


def payload_language(latest: dict[str, Any] | None) -> str:
    if isinstance(latest, dict):
        return normalized_language(latest.get("language"))
    return default_interface_language()


def runtime_text(latest: dict[str, Any] | None, key: str, **values: Any) -> str:
    language = payload_language(latest)
    texts = {
        "ready": {"ko": "입력 대기 중", "en": "Ready"},
        "processing": {"ko": "Codex가 처리 중", "en": "Codex is processing"},
        "processing_button": {"ko": "처리 중...", "en": "Processing..."},
        "processing_detail": {
            "ko": "보낸 입력을 세계 상태와 숨은 진행에 반영하는 중입니다. 다음 장면이 준비되면 입력창이 비워집니다.",
            "en": "Codex is applying the submitted input to the world state. The input box will clear when the next scene is ready.",
        },
        "submitted": {
            "ko": "입력 제출됨; Codex가 처리 중",
            "en": "Input submitted; Codex is processing",
        },
        "turn_label": {"ko": "진행 중", "en": "In progress"},
    }
    template = texts.get(key, {}).get(language) or texts.get(key, {}).get("en") or key
    return template.format(**values)


def display_phase_label(phase: str, latest: dict[str, Any] | None) -> str:
    language = payload_language(latest)
    if language != "ko":
        return phase
    labels = {
        "world_concept": "세계 컨셉",
        "character_creation": "캐릭터 설정",
        "play": "진행",
    }
    return labels.get(phase, phase)


def section_kind(section: dict[str, Any]) -> str:
    raw_kind = str(section.get("kind", "")).lower()
    return "".join(ch for ch in raw_kind if ch.isalnum() or ch in {"-", "_"})


def validate_popup(popup: Any) -> None:
    if popup is None:
        return
    if not isinstance(popup, dict):
        raise WorldSimulatorError("popup must be a JSON object")
    if not str(popup.get("id") or "").strip():
        raise WorldSimulatorError("popup missing id")
    if not str(popup.get("title") or "").strip():
        raise WorldSimulatorError("popup missing title")
    has_content = any(str(popup.get(key) or "").strip() for key in ("markdown", "image_path", "caption"))
    if not has_content:
        raise WorldSimulatorError("popup requires markdown, image_path, or caption")


def initial_output(session_id: str) -> dict[str, Any]:
    language = default_interface_language()
    if language == "ko":
        history_markdown = (
            "# 세계 설정\n\n"
            "입력 영역에 세계 컨셉을 적어 보내세요. Codex가 그 언어를 따라 세계를 만들고, "
            "세계관에 맞는 화면 테마와 캐릭터 설정 단계로 이어갑니다."
        )
        status_body = "첫 세계 컨셉을 기다리는 중입니다."
        phase_label = "세계 컨셉"
        input_label = "자유 입력"
        theme = {
            "title": "월드 시뮬레이터",
            "history_title": "기록",
            "status_title": "상태",
            "input_title": "세계 컨셉",
            "input_placeholder": "세계 컨셉을 입력하세요.",
            "input_hint": "Enter: 보내기 · Shift+Enter: 줄바꿈",
            "send_label": "보내기",
            "processing_message": "Codex가 처리 중",
            "processing_detail": "보낸 입력을 세계 상태와 숨은 진행에 반영하는 중입니다. 다음 장면이 준비되면 입력창이 비워집니다.",
            "palette": DEFAULT_THEME,
        }
        status_message = "세계 컨셉 대기 중"
    else:
        history_markdown = (
            "# World Setup\n\n"
            "Submit a world concept in the input panel. Codex will create the world, choose a matching interface theme, "
            "and move into character setup."
        )
        status_body = "Waiting for the first world concept."
        phase_label = "World concept"
        input_label = "Free text"
        theme = {
            "title": "World Simulator",
            "history_title": "History",
            "status_title": "Status",
            "input_title": "World Concept",
            "input_placeholder": "Describe the world concept.",
            "send_label": "Send",
            "processing_message": "Codex is processing",
            "processing_detail": "Codex is applying the submitted input to the world state. The input box will clear when the next scene is ready.",
            "palette": DEFAULT_THEME,
        }
        status_message = "Waiting for world concept"
    return {
        "phase": "world_concept",
        "turn_id": 0,
        "language": language,
        "history_markdown": history_markdown,
        "status_sections": [
            {
                "kind": "setup",
                "title": "Session" if language == "en" else "세션",
                "body": status_body,
                "fields": [
                    {"label": "Session", "value": session_id},
                    {"label": "Phase" if language == "en" else "단계", "value": phase_label},
                    {"label": "Input" if language == "en" else "입력", "value": input_label},
                ],
                "tags": ["persistent", "open-ended"] if language == "en" else ["지속 세션", "자유 입력"],
            }
        ],
        "ui_theme": theme,
        "input_enabled": True,
        "status_message": status_message,
        "published_at": utc_timestamp(),
    }


def init_session(session_path: pathlib.Path) -> dict[str, Any]:
    for dirname in SESSION_DIRS:
        (session_path / dirname).mkdir(parents=True, exist_ok=True)

    session_id = session_path.name
    gui_state_path = ui_path(session_path, "gui_state.json")
    if not gui_state_path.exists():
        atomic_write_json(
            gui_state_path,
            {
                "session_id": session_id,
                "next_turn_id": 1,
                "phase": "world_concept",
                "draft": "",
                "updated_at": utc_timestamp(),
            },
        )

    latest_output_path = ui_path(session_path, "latest_output.json")
    if not latest_output_path.exists():
        atomic_write_json(latest_output_path, initial_output(session_id))

    current_note = session_path / "current" / "start-here.md"
    if not current_note.exists():
        atomic_write_text(
            current_note,
            "# Current Context\n\n"
            "Codex should keep this directory compact and update it with the minimum context needed to resume the next turn.\n",
        )

    return session_status(session_path)


def turn_id(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    value = payload.get("turn_id", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def session_status(session_path: pathlib.Path) -> dict[str, Any]:
    pending = read_json(ui_path(session_path, "pending_input.json"), None)
    latest = read_json(ui_path(session_path, "latest_output.json"), None)
    ack = read_json(ui_path(session_path, "input_ack.json"), None)
    gui_state = read_json(ui_path(session_path, "gui_state.json"), None)
    heartbeat = read_json(ui_path(session_path, "heartbeat.json"), None)
    pending_turn = turn_id(pending)
    latest_turn = turn_id(latest)
    return {
        "session_path": str(session_path),
        "session_id": session_path.name,
        "exists": session_path.exists(),
        "phase": (latest or gui_state or {}).get("phase"),
        "pending_turn_id": pending_turn or None,
        "latest_output_turn_id": latest_turn or None,
        "acknowledged_turn_id": turn_id(ack) or None,
        "has_unprocessed_input": bool(pending_turn and pending_turn > latest_turn),
        "gui_heartbeat": heartbeat,
        "status_message": (latest or {}).get("status_message"),
    }


def wait_for_input(session_path: pathlib.Path, poll_interval: float) -> dict[str, Any]:
    init_session(session_path)
    while True:
        pending = read_json(ui_path(session_path, "pending_input.json"), None)
        latest = read_json(ui_path(session_path, "latest_output.json"), None)
        if isinstance(pending, dict) and turn_id(pending) > turn_id(latest):
            ack = {
                "session_id": session_path.name,
                "turn_id": turn_id(pending),
                "status": "processing",
                "acknowledged_at": utc_timestamp(),
            }
            atomic_write_json(ui_path(session_path, "input_ack.json"), ack)
            return pending
        time.sleep(poll_interval)


def publish_output(session_path: pathlib.Path, payload_path: pathlib.Path) -> dict[str, Any]:
    init_session(session_path)
    payload = read_json(payload_path)
    if not isinstance(payload, dict):
        raise WorldSimulatorError("output payload must be a JSON object")
    if "history_markdown" not in payload:
        raise WorldSimulatorError("output payload missing history_markdown")
    if "status_sections" not in payload:
        raise WorldSimulatorError("output payload missing status_sections")
    if "turn_id" not in payload:
        raise WorldSimulatorError("output payload missing turn_id")
    if "language" not in payload:
        raise WorldSimulatorError("output payload missing language")
    validate_popup(payload.get("popup"))
    payload.setdefault("phase", "play")
    payload.setdefault("input_enabled", True)
    payload.setdefault("status_message", runtime_text(payload, "ready"))
    payload["published_at"] = utc_timestamp()
    atomic_write_json(ui_path(session_path, "latest_output.json"), payload)
    record_popup_display_asset(session_path, payload)
    return session_status(session_path)


def display_text(value: Any) -> str:
    return str(value).replace("\\n", "\n")


def normalized_theme(latest: dict[str, Any] | None) -> dict[str, Any]:
    raw_theme = latest.get("ui_theme") if isinstance(latest, dict) else None
    raw_theme = raw_theme if isinstance(raw_theme, dict) else {}
    raw_palette = raw_theme.get("palette") if isinstance(raw_theme.get("palette"), dict) else {}
    palette = DEFAULT_THEME | {key: str(value) for key, value in raw_palette.items()}
    language = payload_language(latest)
    defaults = {
        "ko": {
            "title": "월드 시뮬레이터",
            "history_title": "기록",
            "status_title": "상태",
            "input_title": "입력",
            "input_hint": "Enter: 보내기 · Shift+Enter: 줄바꿈",
            "input_placeholder": "자유롭게 입력하세요.",
            "send_label": "보내기",
            "processing_message": "Codex가 진행 중",
            "processing_detail": runtime_text(latest, "processing_detail"),
            "popup_close_label": "닫기",
            "open_image_label": "이미지 열기",
            "download_image_label": "이미지 다운로드",
        },
        "en": {
            "title": "World Simulator",
            "history_title": "History",
            "status_title": "Status",
            "input_title": "Input",
            "input_hint": "Enter: send · Shift+Enter: new line",
            "input_placeholder": "Type freely.",
            "send_label": "Send",
            "processing_message": "Codex is processing",
            "processing_detail": runtime_text(latest, "processing_detail"),
            "popup_close_label": "Close",
            "open_image_label": "Open image",
            "download_image_label": "Download image",
        },
    }[language]
    return {
        "title": str(raw_theme.get("title") or defaults["title"]),
        "history_title": str(raw_theme.get("history_title") or defaults["history_title"]),
        "status_title": str(raw_theme.get("status_title") or defaults["status_title"]),
        "input_title": str(raw_theme.get("input_title") or defaults["input_title"]),
        "input_hint": str(raw_theme.get("input_hint") or defaults["input_hint"]),
        "input_placeholder": str(raw_theme.get("input_placeholder") or defaults["input_placeholder"]),
        "send_label": str(raw_theme.get("send_label") or defaults["send_label"]),
        "processing_message": str(raw_theme.get("processing_message") or defaults["processing_message"]),
        "processing_detail": str(raw_theme.get("processing_detail") or defaults["processing_detail"]),
        "popup_close_label": str(raw_theme.get("popup_close_label") or defaults["popup_close_label"]),
        "open_image_label": str(raw_theme.get("open_image_label") or defaults["open_image_label"]),
        "download_image_label": str(raw_theme.get("download_image_label") or defaults["download_image_label"]),
        "header_icon": str(raw_theme.get("header_icon") or ""),
        "history_icon": str(raw_theme.get("history_icon") or ""),
        "status_icon": str(raw_theme.get("status_icon") or ""),
        "input_icon": str(raw_theme.get("input_icon") or ""),
        "palette": palette,
    }


def decorated_label(icon: str, label: str) -> str:
    return f"{icon} {label}" if icon else label


def section_icon(section: dict[str, Any]) -> str:
    return str(section.get("icon") or "").strip()


def simple_markdown_to_html(markdown: Any, title_icon: str = "") -> str:
    text = display_text(markdown).strip()
    if not text:
        return ""

    html_parts: list[str] = []
    list_items: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_parts.append("<p>" + "<br>".join(html.escape(line) for line in paragraph) + "</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            html_parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            label = decorated_label(title_icon, html.escape(stripped[2:].strip()))
            html_parts.append(f"<h1>{label}</h1>")
        elif stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("- "):
            flush_paragraph()
            list_items.append(html.escape(stripped[2:].strip()))
        else:
            flush_list()
            paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n".join(html_parts)


def html_document(body: str, theme: dict[str, Any], compact: bool = False) -> str:
    palette = theme["palette"]
    paragraph_size = "13px" if compact else "15px"
    line_height = "1.45" if compact else "1.62"
    h1_size = "18px" if compact else "24px"
    return f"""
    <html>
    <head>
      <style>
        body {{
          margin: 0;
          color: {palette["text"]};
          font-family: "Noto Sans CJK KR", "NanumGothic", "Apple SD Gothic Neo", sans-serif;
          font-size: {paragraph_size};
          line-height: {line_height};
        }}
        h1 {{
          margin: 0 0 14px 0;
          color: {palette["accent"]};
          font-size: {h1_size};
          font-weight: 800;
        }}
        h2 {{
          margin: 14px 0 8px 0;
          color: {palette["accent_2"]};
          font-size: 16px;
          font-weight: 750;
        }}
        p {{
          margin: 0 0 13px 0;
        }}
        ul {{
          margin: 4px 0 8px 20px;
          padding: 0;
        }}
        li {{
          margin: 4px 0;
        }}
        .section-card {{
          margin: 0 0 12px 0;
          padding: 10px 11px;
          border: 1px solid {palette["border"]};
          border-radius: 8px;
          background: {palette["panel_background"]};
        }}
        .section-card.player {{
          border-left: 4px solid {palette["accent"]};
          background: {palette["status_background"]};
        }}
        .section-card.setup {{
          border-left: 4px solid {palette["accent"]};
        }}
        .section-card.world,
        .section-card.scene,
        .section-card.clock,
        .section-card.threat {{
          border-left: 4px solid {palette["accent_2"]};
          background: {palette["input_background"]};
        }}
        .section-title {{
          margin-bottom: 8px;
          color: {palette["accent"]};
          font-weight: 800;
          letter-spacing: 0;
        }}
        .field-row {{
          margin: 7px 0;
          padding: 7px 8px;
          border-left: 3px solid {palette["accent"]};
          background: {palette["status_background"]};
        }}
        .field-label {{
          color: {palette["muted_text"]};
          font-size: 11px;
          font-weight: 750;
        }}
        .field-value {{
          color: {palette["text"]};
          font-weight: 750;
          margin-top: 2px;
        }}
        .tag {{
          display: inline-block;
          margin: 3px 4px 3px 0;
          padding: 3px 7px;
          border: 1px solid {palette["border"]};
          border-radius: 7px;
          background: {palette["input_background"]};
          color: {palette["accent"]};
          font-size: 12px;
          font-weight: 750;
        }}
        .meter {{
          margin: 8px 0;
        }}
        .meter-label {{
          color: {palette["muted_text"]};
          font-size: 11px;
          font-weight: 750;
        }}
        .meter-track {{
          margin-top: 4px;
          height: 8px;
          border-radius: 4px;
          background: {palette["border"]};
        }}
        .meter-fill {{
          height: 8px;
          border-radius: 4px;
          background: {palette["accent_2"]};
        }}
      </style>
    </head>
    <body>{body}</body>
    </html>
    """


def render_status_html(sections: Any, theme: dict[str, Any]) -> str:
    if not isinstance(sections, list):
        sections = [sections]
    cards: list[str] = []
    for section in sections:
        if isinstance(section, dict):
            title = str(section.get("title", theme["status_title"])).strip() or theme["status_title"]
            icon = section_icon(section)
            kind = section_kind(section)
            kind_class = f" {html.escape(kind)}" if kind else ""
            content = simple_markdown_to_html(section.get("body", ""), title_icon="")
            fields = section.get("fields")
            if fields:
                rows = []
                for field in fields:
                    if isinstance(field, dict):
                        label = html.escape(str(field.get("label", "")).strip())
                        value = html.escape(display_text(field.get("value", "")).strip())
                        if label and value:
                            rows.append(
                                '<div class="field-row">'
                                f'<div class="field-label">{label}</div>'
                                f'<div class="field-value">{value}</div>'
                                "</div>"
                            )
                content += "".join(rows)
            tags = section.get("tags")
            if isinstance(tags, list) and tags:
                content += "".join(f'<span class="tag">{html.escape(str(tag))}</span>' for tag in tags)
            meters = section.get("meters")
            if isinstance(meters, list):
                meter_parts = []
                for meter in meters:
                    if not isinstance(meter, dict):
                        continue
                    label = html.escape(str(meter.get("label", "")).strip())
                    try:
                        value = float(meter.get("value", 0))
                        maximum = float(meter.get("max", 1))
                    except (TypeError, ValueError):
                        continue
                    if maximum <= 0:
                        continue
                    percent = max(0, min(100, int((value / maximum) * 100)))
                    meter_parts.append(
                        '<div class="meter">'
                        f'<div class="meter-label">{label} {int(value)}/{int(maximum)}</div>'
                        '<div class="meter-track">'
                        f'<div class="meter-fill" style="width: {percent}%"></div>'
                        "</div></div>"
                    )
                content += "".join(meter_parts)
            cards.append(
                f'<div class="section-card{kind_class}">'
                f'<div class="section-title">{html.escape(decorated_label(icon, title))}</div>'
                f"{content}</div>"
            )
        else:
            cards.append(
                '<div class="section-card">'
                f"{simple_markdown_to_html(section)}</div>"
            )
    return html_document("".join(cards), theme, compact=True)


def format_section(section: Any) -> str:
    if isinstance(section, str):
        return display_text(section)
    if not isinstance(section, dict):
        return display_text(section)
    title = str(section.get("title", "")).strip()
    body = section.get("body", "")
    fields = section.get("fields")
    parts: list[str] = []
    if title:
        parts.append(title)
        parts.append("-" * min(len(title), 32))
    if fields:
        for field in fields:
            if isinstance(field, dict):
                label = str(field.get("label", "")).strip()
                value = display_text(field.get("value", "")).strip()
                if label and value:
                    parts.append(f"{label}: {value}")
                elif value:
                    parts.append(value)
    if isinstance(body, list):
        parts.extend(display_text(item) for item in body)
    elif body:
        parts.append(display_text(body))
    return "\n".join(parts).strip()


def popup_key(popup: Any) -> str:
    if not isinstance(popup, dict):
        return ""
    raw_key = str(popup.get("id") or "").strip()
    if raw_key:
        return raw_key
    if popup:
        return json.dumps(popup, ensure_ascii=False, sort_keys=True)
    return ""


def popup_plain_text(popup: dict[str, Any]) -> str:
    parts: list[str] = []
    title = str(popup.get("title") or "").strip()
    markdown = display_text(popup.get("markdown") or "").strip()
    image_path = str(popup.get("image_path") or "").strip()
    caption = display_text(popup.get("caption") or "").strip()
    if title:
        parts.append(title)
        parts.append("=" * min(len(title), 40))
    if image_path:
        parts.append(f"[asset] {image_path}")
    if markdown:
        parts.append(markdown)
    if caption:
        parts.append(caption)
    return "\n\n".join(parts).strip()


def render_popup_html(popup: dict[str, Any], theme: dict[str, Any], session_path: pathlib.Path) -> str:
    parts: list[str] = []
    image_path = str(popup.get("image_path") or "").strip()
    if image_path:
        try:
            asset_uri = resolve_asset_path(session_path, image_path).as_uri()
            alt = html.escape(str(popup.get("title") or popup.get("caption") or "popup image"))
            parts.append(f'<img src="{html.escape(asset_uri)}" alt="{alt}" style="max-width: 100%; margin-bottom: 12px;">')
        except WorldSimulatorError:
            parts.append(f"<p>{html.escape(image_path)}</p>")
    markdown = popup.get("markdown")
    if markdown:
        parts.append(simple_markdown_to_html(markdown, title_icon=str(popup.get("icon") or "")))
    caption = display_text(popup.get("caption") or "").strip()
    if caption:
        parts.append(f'<p style="color: {theme["palette"]["muted_text"]};">{html.escape(caption)}</p>')
    return html_document("".join(parts), theme)


def run_qt_gui(session_path: pathlib.Path) -> None:
    init_session(session_path)
    prepare_text_input_environment()
    try:
        from PyQt6.QtCore import Qt, QTimer, pyqtSignal
        from PyQt6.QtGui import QFont, QFontDatabase, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication,
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QSplitter,
            QTextBrowser,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ImportError(f"PyQt6 is not available: {exc}") from exc

    app = QApplication.instance() or QApplication([sys.argv[0]])

    def choose_qt_font(size: int) -> QFont:
        try:
            available = set(QFontDatabase.families())
        except TypeError:
            available = set(QFontDatabase().families())
        for family in (
            "Noto Sans Mono CJK KR",
            "Noto Sans CJK KR",
            "NanumGothicCoding",
            "NanumGothic",
            "D2Coding",
            "WenQuanYi Zen Hei",
        ):
            if family in available:
                return QFont(family, size)
        return QFont("monospace", size)

    class InputTextEdit(QTextEdit):
        submit_requested = pyqtSignal()

        def keyPressEvent(self, event: Any) -> None:
            is_return = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            wants_newline = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if is_return and not wants_newline:
                self.submit_requested.emit()
                return
            super().keyPressEvent(event)

    class SimulatorWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.session_path = session_path
            self.last_output_text = ""
            self.last_popup_key = ""
            self.popup_dialog: Any = None
            self.help_dialog: Any = None
            self.latest_output: dict[str, Any] = {}
            self.current_theme = normalized_theme({})
            self.awaiting_clear_turn = 0

            self.setWindowTitle(f"World Simulator - {session_path.name}")
            self.resize(980, 680)
            self.setMinimumSize(720, 480)
            self.apply_theme(self.current_theme)

            body_font = choose_qt_font(11)
            status_font = choose_qt_font(10)

            root_layout = QVBoxLayout(self)
            root_layout.setContentsMargins(14, 12, 14, 14)
            root_layout.setSpacing(10)

            top_layout = QHBoxLayout()
            top_layout.setContentsMargins(0, 0, 0, 0)
            top_layout.setSpacing(8)
            self.top_label = QLabel("World Simulator")
            self.top_label.setObjectName("topBar")
            self.state_badge = QLabel("")
            self.state_badge.setObjectName("stateBadge")
            top_layout.addWidget(self.top_label, 1)
            top_layout.addWidget(self.state_badge)
            root_layout.addLayout(top_layout)

            self.processing_banner = QLabel("")
            self.processing_banner.setObjectName("processingBanner")
            self.processing_banner.setWordWrap(True)
            self.processing_banner.setVisible(False)
            root_layout.addWidget(self.processing_banner)

            splitter = QSplitter()
            root_layout.addWidget(splitter, 1)

            history_panel = QWidget()
            history_layout = QVBoxLayout(history_panel)
            history_layout.setContentsMargins(0, 0, 0, 0)
            history_layout.setSpacing(5)
            self.history_title = QLabel("History")
            self.history_title.setObjectName("panelTitle")
            history_layout.addWidget(self.history_title)
            self.history = QTextEdit()
            self.history.setReadOnly(True)
            self.history.setFont(body_font)
            history_layout.addWidget(self.history)
            splitter.addWidget(history_panel)

            status_panel = QWidget()
            status_layout = QVBoxLayout(status_panel)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(5)
            self.status_title = QLabel("Status")
            self.status_title.setObjectName("panelTitle")
            status_layout.addWidget(self.status_title)
            self.status = QTextEdit()
            self.status.setObjectName("statusView")
            self.status.setReadOnly(True)
            self.status.setFont(status_font)
            self.status.setMinimumWidth(250)
            status_layout.addWidget(self.status)
            splitter.addWidget(status_panel)
            splitter.setStretchFactor(0, 4)
            splitter.setStretchFactor(1, 1)

            input_header = QHBoxLayout()
            input_header.setContentsMargins(0, 0, 0, 0)
            self.input_title = QLabel("Input")
            self.input_title.setObjectName("panelTitle")
            self.input_hint = QLabel("Enter: send · Shift+Enter: new line")
            self.input_hint.setObjectName("inputHint")
            self.help_button = QPushButton("?")
            self.help_button.setFixedSize(30, 30)
            self.help_button.clicked.connect(self.render_help_popup)
            input_header.addWidget(self.input_title)
            input_header.addStretch(1)
            input_header.addWidget(self.input_hint)
            input_header.addWidget(self.help_button)
            root_layout.addLayout(input_header)

            input_row = QHBoxLayout()
            input_row.setContentsMargins(0, 0, 0, 0)
            input_row.setSpacing(8)

            self.input_box = InputTextEdit()
            self.input_box.setObjectName("inputBox")
            self.input_box.setFixedHeight(104)
            self.input_box.setFont(body_font)
            self.input_box.setPlaceholderText("Type freely.")
            self.input_box.textChanged.connect(self.schedule_draft_save)
            self.input_box.submit_requested.connect(self.submit_input)
            input_row.addWidget(self.input_box, 1)

            self.submit_button = QPushButton("Send")
            self.submit_button.setFixedSize(112, 104)
            self.submit_button.clicked.connect(self.submit_input)
            input_row.addWidget(self.submit_button)
            root_layout.addLayout(input_row)

            self.draft_timer = QTimer(self)
            self.draft_timer.setSingleShot(True)
            self.draft_timer.timeout.connect(self.save_draft)

            self.poll_timer = QTimer(self)
            self.poll_timer.timeout.connect(self.poll)
            self.poll_timer.start(1000)

            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            self.awaiting_clear_turn = int_value(gui_state.get("submitted_turn_waiting_clear"))
            draft = gui_state.get("draft", "")
            if draft:
                self.input_box.setPlainText(str(draft))

            self.poll()
            self.input_box.setFocus(Qt.FocusReason.OtherFocusReason)

        def apply_theme(self, theme: dict[str, Any]) -> None:
            palette = theme["palette"]
            self.setStyleSheet(
                f"""
                QWidget {{ background: {palette["app_background"]}; color: {palette["text"]}; }}
                QLabel#topBar {{
                    background: {palette["accent"]};
                    color: {palette["button_text"]};
                    border-radius: 7px;
                    padding: 11px 14px;
                    font-size: 16px;
                    font-weight: 800;
                }}
                QLabel#stateBadge {{
                    background: {palette["panel_background"]};
                    color: {palette["accent"]};
                    border: 1px solid {palette["accent"]};
                    border-radius: 7px;
                    padding: 10px 14px;
                    font-size: 13px;
                    font-weight: 800;
                }}
                QLabel#processingBanner {{
                    background: {palette["status_background"]};
                    color: {palette["text"]};
                    border: 1px solid {palette["accent_2"]};
                    border-radius: 7px;
                    padding: 9px 12px;
                    font-size: 13px;
                    font-weight: 750;
                }}
                QLabel#panelTitle {{
                    color: {palette["accent"]};
                    font-size: 13px;
                    font-weight: 800;
                    padding: 0 2px 3px 2px;
                }}
                QLabel#inputHint {{
                    color: {palette["muted_text"]};
                    font-size: 12px;
                    padding: 0 2px;
                }}
                QTextEdit {{
                    background: {palette["panel_background"]};
                    color: {palette["text"]};
                    border: 1px solid {palette["border"]};
                    border-radius: 7px;
                    padding: 12px;
                    selection-background-color: {palette["selection"]};
                }}
                QTextEdit#statusView {{
                    background: {palette["status_background"]};
                }}
                QTextEdit#inputBox {{
                    background: {palette["input_background"]};
                }}
                QTextEdit#inputBox:focus {{
                    border-color: {palette["accent_2"]};
                }}
                QPushButton {{
                    background: {palette["accent"]};
                    color: {palette["button_text"]};
                    border: 1px solid {palette["accent"]};
                    border-radius: 7px;
                    padding: 8px 12px;
                    font-weight: 750;
                }}
                QPushButton:hover {{ background: {palette["accent_2"]}; }}
                QPushButton:disabled {{
                    background: {palette["disabled_background"]};
                    border-color: {palette["border"]};
                    color: {palette["disabled_text"]};
                }}
                QSplitter::handle {{ background: {palette["border"]}; }}
                QSplitter::handle:hover {{ background: {palette["accent_2"]}; }}
                """
            )

        def schedule_draft_save(self) -> None:
            self.draft_timer.start(400)

        def save_draft(self) -> None:
            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            gui_state.setdefault("session_id", self.session_path.name)
            gui_state.setdefault("next_turn_id", 1)
            gui_state["draft"] = self.input_box.toPlainText()
            gui_state["updated_at"] = utc_timestamp()
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)

        def submit_input(self) -> None:
            text = self.input_box.toPlainText().strip()
            if not text:
                return
            latest = read_json(ui_path(self.session_path, "latest_output.json"), {}) or {}
            pending = read_json(ui_path(self.session_path, "pending_input.json"), {}) or {}
            if turn_id(pending) > turn_id(latest):
                self.render_enabled_state(False, runtime_text(latest, "processing"))
                return

            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            next_turn = max(
                int(gui_state.get("next_turn_id", 1) or 1),
                turn_id(latest) + 1,
                turn_id(pending) + 1,
            )
            phase = str(latest.get("phase") or gui_state.get("phase") or "world_concept")
            payload = {
                "session_id": self.session_path.name,
                "turn_id": next_turn,
                "phase": phase,
                "text": text,
                "created_at": utc_timestamp(),
            }
            atomic_write_json(ui_path(self.session_path, "pending_input.json"), payload)
            gui_state.update(
                {
                    "session_id": self.session_path.name,
                    "next_turn_id": next_turn + 1,
                    "phase": phase,
                    "draft": text,
                    "submitted_turn_waiting_clear": next_turn,
                    "updated_at": utc_timestamp(),
                }
            )
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)
            self.awaiting_clear_turn = next_turn
            self.render_enabled_state(False, runtime_text(latest, "submitted", turn=next_turn))

        def clear_processed_submission(self, latest: dict[str, Any]) -> None:
            if not self.awaiting_clear_turn:
                return
            if turn_id(latest) < self.awaiting_clear_turn or not bool(latest.get("input_enabled", True)):
                return
            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            self.awaiting_clear_turn = 0
            gui_state["draft"] = ""
            gui_state["submitted_turn_waiting_clear"] = 0
            gui_state["updated_at"] = utc_timestamp()
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)
            self.input_box.blockSignals(True)
            self.input_box.clear()
            self.input_box.blockSignals(False)

        def poll(self) -> None:
            atomic_write_json(
                ui_path(self.session_path, "heartbeat.json"),
                {
                    "session_id": self.session_path.name,
                    "pid": os.getpid(),
                    "backend": "qt",
                    "updated_at": utc_timestamp(),
                },
            )
            latest = read_json(ui_path(self.session_path, "latest_output.json"), {}) or {}
            self.latest_output = latest
            output_text = json.dumps(latest, ensure_ascii=False, sort_keys=True)
            if output_text != self.last_output_text:
                self.last_output_text = output_text
                self.render_latest(latest)

            pending = read_json(ui_path(self.session_path, "pending_input.json"), {}) or {}
            is_processing = turn_id(pending) > turn_id(latest)
            can_input = not is_processing and bool(latest.get("input_enabled", True))
            if can_input:
                self.clear_processed_submission(latest)
            if is_processing:
                message = runtime_text(latest, "processing")
            else:
                message = str(latest.get("status_message") or runtime_text(latest, "ready"))
            self.render_enabled_state(can_input, message)

        def render_latest(self, latest: dict[str, Any]) -> None:
            self.current_theme = normalized_theme(latest)
            self.apply_theme(self.current_theme)
            self.history_title.setText(
                decorated_label(self.current_theme["history_icon"], self.current_theme["history_title"])
            )
            self.status_title.setText(
                decorated_label(self.current_theme["status_icon"], self.current_theme["status_title"])
            )
            self.input_title.setText(
                decorated_label(self.current_theme["input_icon"], self.current_theme["input_title"])
            )
            self.input_hint.setText(self.current_theme["input_hint"])
            self.input_box.setPlaceholderText(self.current_theme["input_placeholder"])
            history_text = display_text(latest.get("history_markdown", ""))
            sections = latest.get("status_sections", [])
            if not isinstance(sections, list):
                sections = [sections]
            self.history.setHtml(
                html_document(
                    simple_markdown_to_html(history_text, title_icon=self.current_theme["header_icon"]),
                    self.current_theme,
                )
            )
            self.history.moveCursor(QTextCursor.MoveOperation.End)
            self.status.setHtml(render_status_html(sections, self.current_theme))
            self.render_popup(latest)

        def render_popup(self, latest: dict[str, Any]) -> None:
            popup = latest.get("popup")
            key = popup_key(popup)
            if not key:
                self.last_popup_key = ""
                return
            if not isinstance(popup, dict) or key == self.last_popup_key:
                return
            self.last_popup_key = key
            if self.popup_dialog is not None:
                self.popup_dialog.close()
            dialog = QDialog(self)
            dialog.setWindowTitle(str(popup.get("title") or self.current_theme["title"]))
            dialog.resize(680, 480)
            layout = QVBoxLayout(dialog)
            browser = QTextBrowser()
            browser.setHtml(render_popup_html(popup, self.current_theme, self.session_path))
            layout.addWidget(browser, 1)
            close_button = QPushButton(self.current_theme["popup_close_label"])
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button)
            dialog.finished.connect(lambda _result: setattr(self, "popup_dialog", None))
            self.popup_dialog = dialog
            dialog.show()

        def render_help_popup(self) -> None:
            popup = command_help_popup(self.session_path, self.latest_output)
            if self.help_dialog is not None:
                self.help_dialog.close()
            dialog = QDialog(self)
            dialog.setWindowTitle(str(popup["title"]))
            dialog.resize(680, 480)
            layout = QVBoxLayout(dialog)
            browser = QTextBrowser()
            browser.setHtml(render_popup_html(popup, self.current_theme, self.session_path))
            layout.addWidget(browser, 1)
            close_button = QPushButton(self.current_theme["popup_close_label"])
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button)
            dialog.finished.connect(lambda _result: setattr(self, "help_dialog", None))
            self.help_dialog = dialog
            dialog.show()

        def render_enabled_state(self, enabled: bool, message: str) -> None:
            phase = str(self.latest_output.get("phase") or "world_concept")
            phase_label = display_phase_label(phase, self.latest_output)
            self.top_label.setText(
                f"{decorated_label(self.current_theme['header_icon'], self.current_theme['title'])}"
                f"  ·  {session_path.name}  ·  {phase_label}"
            )
            self.state_badge.setText(message)
            self.processing_banner.setVisible(not enabled)
            self.processing_banner.setText(
                f"{self.current_theme['processing_message']} · {self.current_theme['processing_detail']}"
            )
            self.input_box.setReadOnly(not enabled)
            self.submit_button.setEnabled(enabled)
            self.submit_button.setText(
                self.current_theme["send_label"] if enabled else runtime_text(self.latest_output, "processing_button")
            )
            if enabled and not self.input_box.hasFocus():
                self.input_box.setFocus(Qt.FocusReason.OtherFocusReason)

    window = SimulatorWindow()
    window.show()
    app.exec()


def run_tk_gui(session_path: pathlib.Path) -> None:
    init_session(session_path)
    prepare_text_input_environment()
    try:
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - environment dependent
        raise WorldSimulatorError(f"tkinter is required to launch the GUI: {exc}") from exc

    def choose_text_font(root: tk.Tk, size: int) -> tuple[str, int]:
        available = set(tkfont.families(root))
        for family in (
            "Noto Sans Mono CJK KR",
            "Noto Sans CJK KR",
            "NanumGothicCoding",
            "NanumGothic",
            "D2Coding",
            "WenQuanYi Zen Hei",
        ):
            if family in available:
                return (family, size)
        return ("TkFixedFont", size)

    class SimulatorApp:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.session_path = session_path
            self.last_output_text = ""
            self.last_popup_key = ""
            self.popup_window: Any = None
            self.help_window: Any = None
            self.draft_after_id: str | None = None
            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            self.awaiting_clear_turn = int_value(gui_state.get("submitted_turn_waiting_clear"))
            self.latest_output: dict[str, Any] = {}
            self.body_font = choose_text_font(root, 11)
            self.status_font = choose_text_font(root, 10)

            root.title(f"World Simulator - {session_path.name}")
            root.geometry("980x680")
            root.minsize(720, 480)
            root.configure(bg="#f6f3ea")

            self.top_label = tk.Label(
                root,
                text="World Simulator",
                anchor="w",
                bg="#f6f3ea",
                fg="#242424",
                padx=12,
                pady=8,
            )
            self.top_label.grid(row=0, column=0, sticky="ew")

            main = tk.Frame(root, bg="#f6f3ea")
            main.grid(row=1, column=0, sticky="nsew", padx=10)
            main.columnconfigure(0, weight=4)
            main.columnconfigure(1, weight=1)
            main.rowconfigure(0, weight=1)

            self.history = tk.Text(
                main,
                wrap="word",
                bg="#fffdf7",
                fg="#202124",
                insertbackground="#202124",
                relief="flat",
                padx=14,
                pady=12,
                font=self.body_font,
            )
            self.history.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            self.history.configure(state="disabled")

            self.status = tk.Text(
                main,
                wrap="word",
                width=32,
                bg="#fffdf7",
                fg="#202124",
                relief="flat",
                padx=12,
                pady=12,
                font=self.status_font,
            )
            self.status.grid(row=0, column=1, sticky="nsew")
            self.status.configure(state="disabled")

            input_frame = tk.Frame(root, bg="#f6f3ea")
            input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
            input_frame.columnconfigure(0, weight=1)

            self.input_box = tk.Text(
                input_frame,
                height=5,
                wrap="word",
                bg="#fffdf7",
                fg="#202124",
                insertbackground="#202124",
                relief="flat",
                padx=12,
                pady=10,
                font=self.body_font,
            )
            self.input_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.input_box.bind("<KeyRelease>", self.schedule_draft_save)

            self.submit_button = ttk.Button(input_frame, text="Submit", command=self.submit_input)
            self.submit_button.grid(row=0, column=1, sticky="ns")

            self.help_button = ttk.Button(input_frame, text="?", command=self.render_help_popup, width=3)
            self.help_button.grid(row=0, column=2, sticky="ns", padx=(8, 0))

            root.columnconfigure(0, weight=1)
            root.rowconfigure(1, weight=1)

            draft = gui_state.get("draft", "")
            if draft:
                self.input_box.insert("1.0", str(draft))

            self.poll()

        def schedule_draft_save(self, _event: Any = None) -> None:
            if self.draft_after_id is not None:
                self.root.after_cancel(self.draft_after_id)
            self.draft_after_id = self.root.after(400, self.save_draft)

        def save_draft(self) -> None:
            self.draft_after_id = None
            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            gui_state.setdefault("session_id", self.session_path.name)
            gui_state.setdefault("next_turn_id", 1)
            gui_state["draft"] = self.input_box.get("1.0", "end-1c")
            gui_state["updated_at"] = utc_timestamp()
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)

        def submit_input(self) -> None:
            text = self.input_box.get("1.0", "end-1c").strip()
            if not text:
                return
            latest = read_json(ui_path(self.session_path, "latest_output.json"), {}) or {}
            pending = read_json(ui_path(self.session_path, "pending_input.json"), {}) or {}
            if turn_id(pending) > turn_id(latest):
                self.render_enabled_state(False, runtime_text(latest, "processing"))
                return

            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            next_turn = max(
                int(gui_state.get("next_turn_id", 1) or 1),
                turn_id(latest) + 1,
                turn_id(pending) + 1,
            )
            phase = str(latest.get("phase") or gui_state.get("phase") or "world_concept")
            payload = {
                "session_id": self.session_path.name,
                "turn_id": next_turn,
                "phase": phase,
                "text": text,
                "created_at": utc_timestamp(),
            }
            atomic_write_json(ui_path(self.session_path, "pending_input.json"), payload)
            gui_state.update(
                {
                    "session_id": self.session_path.name,
                    "next_turn_id": next_turn + 1,
                    "phase": phase,
                    "draft": text,
                    "submitted_turn_waiting_clear": next_turn,
                    "updated_at": utc_timestamp(),
                }
            )
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)
            self.awaiting_clear_turn = next_turn
            self.render_enabled_state(False, runtime_text(latest, "submitted", turn=next_turn))

        def clear_processed_submission(self, latest: dict[str, Any]) -> None:
            if not self.awaiting_clear_turn:
                return
            if turn_id(latest) < self.awaiting_clear_turn or not bool(latest.get("input_enabled", True)):
                return
            gui_state = read_json(ui_path(self.session_path, "gui_state.json"), {}) or {}
            self.awaiting_clear_turn = 0
            gui_state["draft"] = ""
            gui_state["submitted_turn_waiting_clear"] = 0
            gui_state["updated_at"] = utc_timestamp()
            atomic_write_json(ui_path(self.session_path, "gui_state.json"), gui_state)
            if str(self.input_box.cget("state")) != "normal":
                self.input_box.configure(state="normal")
            self.input_box.delete("1.0", "end")

        def poll(self) -> None:
            atomic_write_json(
                ui_path(self.session_path, "heartbeat.json"),
                {
                    "session_id": self.session_path.name,
                    "pid": os.getpid(),
                    "updated_at": utc_timestamp(),
                },
            )
            latest = read_json(ui_path(self.session_path, "latest_output.json"), {}) or {}
            self.latest_output = latest
            output_text = json.dumps(latest, ensure_ascii=False, sort_keys=True)
            if output_text != self.last_output_text:
                self.last_output_text = output_text
                self.render_latest(latest)

            pending = read_json(ui_path(self.session_path, "pending_input.json"), {}) or {}
            is_processing = turn_id(pending) > turn_id(latest)
            can_input = not is_processing and bool(latest.get("input_enabled", True))
            if can_input:
                self.clear_processed_submission(latest)
            if is_processing:
                message = runtime_text(latest, "processing")
            else:
                message = str(latest.get("status_message") or runtime_text(latest, "ready"))
            self.render_enabled_state(can_input, message)
            self.root.after(1000, self.poll)

        def render_latest(self, latest: dict[str, Any]) -> None:
            history_text = display_text(latest.get("history_markdown", ""))
            sections = latest.get("status_sections", [])
            if not isinstance(sections, list):
                sections = [sections]
            status_text = "\n\n".join(filter(None, (format_section(section) for section in sections)))

            self.history.configure(state="normal")
            self.history.delete("1.0", "end")
            self.history.insert("1.0", history_text)
            self.history.configure(state="disabled")
            self.history.see("end")

            self.status.configure(state="normal")
            self.status.delete("1.0", "end")
            self.status.insert("1.0", status_text)
            self.status.configure(state="disabled")
            self.render_popup(latest)

        def render_popup(self, latest: dict[str, Any]) -> None:
            popup = latest.get("popup")
            key = popup_key(popup)
            if not key:
                self.last_popup_key = ""
                return
            if not isinstance(popup, dict) or key == self.last_popup_key:
                return
            self.last_popup_key = key
            if self.popup_window is not None:
                try:
                    self.popup_window.destroy()
                except Exception:
                    pass
                self.popup_window = None
            popup_window = tk.Toplevel(self.root)
            popup_window.title(str(popup.get("title") or "Popup"))
            popup_window.geometry("680x480")
            popup_window.configure(bg="#f6f9ff")
            popup_window.columnconfigure(0, weight=1)
            popup_window.rowconfigure(0, weight=1)
            text_widget = tk.Text(
                popup_window,
                wrap="word",
                bg="#ffffff",
                fg="#102033",
                padx=14,
                pady=12,
                relief="flat",
                font=self.body_font,
            )
            text_widget.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
            text_widget.insert("1.0", popup_plain_text(popup))
            text_widget.configure(state="disabled")
            def close_popup_window() -> None:
                self.popup_window = None
                popup_window.destroy()

            close_button = ttk.Button(
                popup_window,
                text=str(normalized_theme(latest)["popup_close_label"]),
                command=close_popup_window,
            )
            close_button.grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))
            popup_window.protocol("WM_DELETE_WINDOW", close_popup_window)
            self.popup_window = popup_window

        def render_help_popup(self) -> None:
            if self.help_window is not None:
                try:
                    self.help_window.destroy()
                except Exception:
                    pass
                self.help_window = None
            popup = command_help_popup(self.session_path, self.latest_output)
            help_window = tk.Toplevel(self.root)
            help_window.title(str(popup["title"]))
            help_window.geometry("680x480")
            help_window.configure(bg="#f6f9ff")
            help_window.columnconfigure(0, weight=1)
            help_window.rowconfigure(0, weight=1)
            text_widget = tk.Text(
                help_window,
                wrap="word",
                bg="#ffffff",
                fg="#102033",
                padx=14,
                pady=12,
                relief="flat",
                font=self.body_font,
            )
            text_widget.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
            text_widget.insert("1.0", popup_plain_text(popup))
            text_widget.configure(state="disabled")

            def close_help_window() -> None:
                self.help_window = None
                help_window.destroy()

            close_button = ttk.Button(
                help_window,
                text=str(normalized_theme(self.latest_output)["popup_close_label"]),
                command=close_help_window,
            )
            close_button.grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))
            help_window.protocol("WM_DELETE_WINDOW", close_help_window)
            self.help_window = help_window

        def render_enabled_state(self, enabled: bool, message: str) -> None:
            phase = str(self.latest_output.get("phase") or "world_concept")
            phase_label = display_phase_label(phase, self.latest_output)
            self.top_label.configure(
                text=f"{session_path.name} · {phase_label} · {message}"
            )
            input_state = "normal" if enabled else "disabled"
            button_state = "normal" if enabled else "disabled"
            if str(self.input_box.cget("state")) != input_state:
                self.input_box.configure(state=input_state)
            self.submit_button.configure(state=button_state)

    root = tk.Tk()
    SimulatorApp(root)
    root.mainloop()


WEB_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>World Simulator</title>
  <style>
    :root {
      --app: #f6f9ff;
      --panel: #ffffff;
      --status: #eef5ff;
      --input: #ffffff;
      --text: #102033;
      --muted: #617089;
      --accent: #2563eb;
      --accent2: #0891b2;
      --border: #cbd9ee;
      --selection: #bfdbfe;
      --buttonText: #ffffff;
      --disabled: #e5edf8;
      --disabledText: #7b8798;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      height: 100vh;
      overflow: hidden;
      color: var(--text);
      background: var(--app);
      font-family: "Noto Sans CJK KR", "NanumGothic", "Apple SD Gothic Neo", system-ui, sans-serif;
      letter-spacing: 0;
    }
    .shell {
      height: 100vh;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      overflow: hidden;
    }
    .hud {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto;
      gap: 10px;
      align-items: stretch;
    }
    .brand, .state-badge, .panel, .input-deck, .processing {
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel) 92%, white);
      box-shadow: 0 12px 28px rgba(43, 34, 24, .08);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 62px;
      padding: 12px 16px;
      border-left: 5px solid var(--accent);
    }
    .sigil {
      display: grid;
      place-items: center;
      min-width: 38px;
      height: 38px;
      border: 1px solid var(--accent);
      color: var(--accent);
      background: var(--status);
      font-size: 20px;
      font-weight: 800;
    }
    .title {
      font-size: 20px;
      font-weight: 850;
      line-height: 1.1;
    }
    .meta {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .state-badge {
      min-width: 190px;
      padding: 10px 14px;
      display: grid;
      align-content: center;
      border-left: 5px solid var(--accent2);
    }
    .state-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
    }
    .state-text {
      margin-top: 4px;
      color: var(--accent);
      font-size: 15px;
      font-weight: 850;
    }
    .processing {
      display: flex;
      align-items: center;
      gap: 10px;
      max-height: 0;
      padding: 0 14px;
      border-width: 0 1px;
      border-color: transparent;
      background: var(--status);
      color: var(--text);
      font-weight: 800;
      overflow: hidden;
      opacity: 0;
      transition: max-height .18s ease, padding .18s ease, opacity .18s ease;
    }
    .processing.on {
      max-height: 70px;
      padding: 10px 14px;
      border-width: 1px;
      border-color: var(--accent2);
      opacity: 1;
    }
    .pulse {
      width: 11px;
      height: 11px;
      border-radius: 999px;
      background: var(--accent2);
      box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent2) 40%, transparent);
      animation: pulse 1.2s infinite;
    }
    @keyframes pulse {
      70% { box-shadow: 0 0 0 10px transparent; }
      100% { box-shadow: 0 0 0 0 transparent; }
    }
    .main {
      min-height: 0;
      flex: 1 1 auto;
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(360px, .95fr);
      gap: 12px;
      overflow: hidden;
    }
    .panel {
      min-height: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      overflow: hidden;
    }
    .panel-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--accent);
      font-size: 14px;
      font-weight: 850;
      background: color-mix(in srgb, var(--panel) 84%, var(--status));
    }
    .content {
      min-height: 0;
      overflow: auto;
      padding: 18px 20px;
      scrollbar-color: var(--accent) var(--status);
    }
    .panel:first-child .content {
      background: var(--panel);
    }
    #history {
      font-size: 15px;
      line-height: 1.62;
    }
    #history h1 {
      margin: 0 0 12px;
      color: var(--accent);
      font-size: 22px;
      line-height: 1.2;
    }
    #history h2 {
      margin: 18px 0 8px;
      color: var(--accent2);
      font-size: 18px;
    }
    #history p { margin: 0 0 15px; }
    .history-turn {
      margin: 0 0 28px;
      padding: 0;
      border: 0;
    }
    .history-turn:last-child {
      border-bottom: 0;
      margin-bottom: 0;
    }
    .history-turn-meta {
      display: inline-flex;
      margin: 0 0 12px;
      padding: 4px 9px;
      border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
      border-radius: 999px;
      background: color-mix(in srgb, var(--status) 52%, white);
      color: var(--accent);
      font-size: 12px;
      font-weight: 900;
    }
    #history .dialogue {
      margin: 10px 0 14px;
      padding: 8px 10px;
      border-left: 3px solid var(--accent2);
      background: color-mix(in srgb, var(--status) 42%, white);
      font-weight: 780;
    }
    #history strong {
      color: var(--accent);
      font-weight: 900;
    }
    #history code,
    .popup-body code {
      padding: 1px 5px;
      border: 1px solid color-mix(in srgb, var(--border) 80%, white);
      background: color-mix(in srgb, var(--status) 66%, white);
      color: var(--accent);
      font-family: "Noto Sans Mono CJK KR", "D2Coding", monospace;
      font-size: .92em;
      font-weight: 800;
    }
    #history ul { margin: 6px 0 14px 22px; padding: 0; }
    .status-card {
      margin: 0 0 10px;
      padding: 11px;
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent);
      background: color-mix(in srgb, var(--panel) 86%, var(--status));
    }
    .status-card h3 {
      margin: 0 0 9px;
      color: var(--accent);
      font-size: 14px;
      font-weight: 900;
    }
    .status-card p {
      margin: 0 0 10px;
      color: var(--text);
      font-size: 13px;
      line-height: 1.5;
    }
    .field {
      display: grid;
      grid-template-columns: 76px minmax(0, 1fr);
      gap: 8px;
      align-items: baseline;
      margin: 0;
      padding: 7px 0;
      border-top: 1px solid color-mix(in srgb, var(--border) 72%, transparent);
      background: transparent;
    }
    .field-label {
      color: var(--muted);
      font-size: 10px;
      font-weight: 850;
    }
    .field-value {
      margin-top: 0;
      font-size: 12px;
      font-weight: 760;
      line-height: 1.42;
    }
    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .tag {
      padding: 3px 7px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--status) 58%, white);
      color: var(--accent);
      font-size: 11px;
      font-weight: 850;
    }
    .meter {
      margin: 10px 0;
    }
    .meter-head {
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 11px;
      font-weight: 850;
    }
    .meter-track {
      height: 9px;
      margin-top: 5px;
      background: var(--border);
      overflow: hidden;
    }
    .meter-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }
    .meter.tone-good .meter-fill {
      background: linear-gradient(90deg, #0f766e, #22c55e);
    }
    .meter.tone-warning .meter-fill {
      background: linear-gradient(90deg, #2563eb, #f59e0b);
    }
    .meter.tone-danger .meter-fill {
      background: linear-gradient(90deg, #2563eb, #dc2626);
    }
    .status-card.primary {
      border-left-color: var(--accent);
      background: linear-gradient(180deg, color-mix(in srgb, var(--status) 82%, white), var(--panel));
    }
    .status-card.primary h3 {
      font-size: 15px;
    }
    .status-card.primary .meters {
      display: grid;
      gap: 9px;
      margin-top: 10px;
    }
    .status-card.primary .meter {
      margin: 0;
      padding: 8px;
      background: color-mix(in srgb, var(--status) 56%, white);
    }
    .status-card.player {
      position: relative;
      overflow: hidden;
      padding: 13px;
      border-left: 1px solid color-mix(in srgb, var(--accent) 55%, var(--border));
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--status) 88%, white), var(--panel) 58%),
        var(--panel);
      box-shadow: 0 10px 22px rgba(37, 99, 235, .08);
    }
    .status-card.player::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }
    .player-profile {
      display: grid;
      grid-template-columns: 46px minmax(0, 1fr);
      gap: 11px;
      align-items: center;
      margin: 0 0 11px;
      padding-bottom: 11px;
      border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
    }
    .player-emblem {
      display: grid;
      width: 46px;
      height: 46px;
      place-items: center;
      border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
      background:
        radial-gradient(circle at 30% 20%, color-mix(in srgb, var(--accent) 18%, white), transparent 52%),
        color-mix(in srgb, var(--status) 72%, white);
      color: var(--accent);
      font-size: 20px;
      font-weight: 900;
    }
    .player-id h3 {
      margin: 0;
      color: var(--accent);
      font-size: 18px;
      line-height: 1.2;
      font-weight: 950;
    }
    .player-subtitle {
      margin-top: 3px;
      color: var(--text);
      font-size: 12px;
      font-weight: 850;
    }
    .player-summary {
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
      font-weight: 760;
    }
    .player-vitals {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin: 0 0 9px;
    }
    .player-vital {
      min-width: 0;
      padding: 8px;
      border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--border));
      background: color-mix(in srgb, var(--status) 64%, white);
    }
    .player-vital.tone-warning {
      border-color: color-mix(in srgb, #f59e0b 38%, var(--border));
      background: color-mix(in srgb, #fef3c7 48%, white);
    }
    .player-vital.tone-danger {
      border-color: color-mix(in srgb, #dc2626 34%, var(--border));
      background: color-mix(in srgb, #fee2e2 42%, white);
    }
    .player-vital.tone-good {
      border-color: color-mix(in srgb, #0f766e 36%, var(--border));
      background: color-mix(in srgb, #ccfbf1 42%, white);
    }
    .player-vital span,
    .player-slot span {
      display: block;
      color: var(--muted);
      font-size: 10px;
      font-weight: 900;
    }
    .player-vital strong,
    .player-slot strong {
      display: block;
      margin-top: 3px;
      color: var(--text);
      font-size: 12px;
      line-height: 1.35;
      font-weight: 900;
    }
    .player-attributes {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 6px;
      margin: 0 0 9px;
    }
    .player-attribute {
      min-width: 0;
      padding: 7px 5px;
      border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--border));
      background: color-mix(in srgb, var(--panel) 70%, var(--status));
      text-align: center;
    }
    .player-attribute span {
      display: block;
      color: var(--muted);
      font-size: 9px;
      font-weight: 900;
    }
    .player-attribute strong {
      display: block;
      margin-top: 3px;
      color: var(--accent);
      font-size: 14px;
      line-height: 1;
      font-weight: 950;
    }
    .player-groups {
      display: grid;
      gap: 8px;
      margin-top: 9px;
    }
    .player-group {
      padding: 8px;
      border: 1px solid color-mix(in srgb, var(--border) 82%, white);
      background: color-mix(in srgb, var(--panel) 80%, var(--status));
    }
    .player-group-title {
      margin-bottom: 7px;
      color: var(--accent);
      font-size: 11px;
      font-weight: 950;
    }
    .player-group-items {
      display: grid;
      gap: 5px;
    }
    .player-group-item {
      display: grid;
      grid-template-columns: 76px minmax(0, 1fr);
      gap: 7px;
      align-items: baseline;
      min-width: 0;
      padding-top: 5px;
      border-top: 1px solid color-mix(in srgb, var(--border) 62%, transparent);
    }
    .player-group-item:first-child {
      padding-top: 0;
      border-top: 0;
    }
    .player-group-item span {
      color: var(--muted);
      font-size: 10px;
      font-weight: 850;
    }
    .player-group-item strong {
      min-width: 0;
      color: var(--text);
      font-size: 12px;
      line-height: 1.35;
      font-weight: 850;
    }
    .player-slots {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 7px;
      margin-top: 8px;
    }
    .player-slot {
      min-width: 0;
      padding: 8px;
      border: 1px solid color-mix(in srgb, var(--border) 82%, white);
      background: color-mix(in srgb, var(--panel) 76%, var(--status));
    }
    .player-slot.wide {
      grid-column: 1 / -1;
    }
    .player-flags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 9px;
    }
    .player-flag {
      padding: 3px 7px;
      border: 1px solid color-mix(in srgb, var(--accent) 24%, var(--border));
      background: white;
      color: var(--accent);
      font-size: 10px;
      font-weight: 900;
    }
    .status-card.clock,
    .status-card.threat,
    .status-card.resource,
    .status-card.relationship,
    .status-card.objective {
      border-left-color: var(--accent2);
    }
    .status-card.world {
      border-left-color: color-mix(in srgb, var(--accent2) 78%, var(--border));
      background: color-mix(in srgb, var(--panel) 88%, var(--status));
    }
    .status-card.setup {
      border-left-color: color-mix(in srgb, var(--accent) 78%, var(--border));
      background: color-mix(in srgb, var(--panel) 90%, var(--status));
    }
    .status-card.scene {
      border-left-color: color-mix(in srgb, var(--accent) 72%, var(--border));
    }
    .status-card.inventory {
      border-left-color: var(--muted);
    }
    .input-deck {
      padding: 12px;
      border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
      box-shadow: 0 -10px 24px rgba(43, 34, 24, .07);
    }
    .input-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 850;
    }
    .input-tools {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .help-button {
      width: 30px;
      min-width: 30px;
      height: 30px;
      min-height: 30px;
      padding: 0;
      border-radius: 999px;
      border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
      background: color-mix(in srgb, var(--panel) 82%, var(--status));
      color: var(--accent);
      font-size: 16px;
      font-weight: 950;
      line-height: 1;
    }
    .help-button:hover:not(:disabled) {
      border-color: var(--accent);
      background: var(--status);
    }
    .input-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 128px;
      gap: 10px;
      align-items: stretch;
    }
    textarea {
      width: 100%;
      min-height: 108px;
      resize: vertical;
      border: 1px solid var(--border);
      background: var(--input);
      color: var(--text);
      padding: 12px;
      font: inherit;
      line-height: 1.5;
      outline: none;
    }
    textarea:focus {
      border-color: var(--accent2);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent2) 18%, transparent);
    }
    textarea[readonly] {
      background: color-mix(in srgb, var(--input) 78%, var(--disabled));
      color: var(--muted);
    }
    button {
      min-height: 108px;
      border: 1px solid var(--accent);
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 92%, white), var(--accent));
      color: var(--buttonText);
      font: inherit;
      font-size: 16px;
      font-weight: 900;
      cursor: pointer;
    }
    button:hover:not(:disabled) {
      border-color: var(--accent2);
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent2) 88%, white), var(--accent2));
    }
    button:disabled {
      cursor: wait;
      background: var(--disabled);
      border-color: var(--border);
      color: var(--disabledText);
    }
    .popup-layer {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      place-items: center;
      padding: 28px;
      background:
        linear-gradient(180deg, rgba(244, 248, 255, .42), rgba(16, 32, 51, .20)),
        rgba(16, 32, 51, .16);
      backdrop-filter: blur(4px);
    }
    .popup-layer.on {
      display: grid;
    }
    .popup-dialog {
      width: min(860px, 100%);
      max-height: min(78vh, 760px);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
      border-top: 4px solid var(--accent);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      box-shadow: 0 26px 70px rgba(16, 32, 51, .24);
      overflow: hidden;
    }
    .popup-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      min-height: 54px;
      padding: 12px 14px 12px 16px;
      border-bottom: 1px solid var(--border);
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--status) 86%, white), var(--panel));
    }
    .popup-title {
      min-width: 0;
      color: var(--accent);
      font-size: 16px;
      font-weight: 950;
      line-height: 1.25;
    }
    .popup-close {
      min-width: 72px;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: color-mix(in srgb, var(--panel) 86%, var(--status));
      color: var(--accent);
      font-size: 13px;
      font-weight: 900;
    }
    .popup-close:hover {
      border-color: var(--accent);
      background: var(--status);
    }
    .popup-body {
      min-height: 0;
      overflow: auto;
      padding: 20px 22px 22px;
      background: linear-gradient(180deg, var(--panel), color-mix(in srgb, var(--panel) 92%, var(--status)));
      font-size: 14px;
      line-height: 1.58;
    }
    .popup-body h1 {
      margin: 0 0 12px;
      color: var(--accent);
      font-size: 22px;
      line-height: 1.2;
    }
    .popup-body h2 {
      margin: 16px 0 8px;
      color: var(--accent2);
      font-size: 17px;
    }
    .popup-body p {
      margin: 0 0 13px;
    }
    .popup-body ul {
      margin: 6px 0 14px 22px;
      padding: 0;
    }
    .popup-image {
      display: block;
      max-width: 100%;
      max-height: 58vh;
      margin: 0 auto 12px;
      border: 1px solid var(--border);
      background: var(--status);
      object-fit: contain;
    }
    .popup-caption {
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
    }
    .popup-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 14px;
    }
    .popup-actions a,
    .asset-row button,
    .asset-row a {
      min-height: 30px;
      padding: 7px 10px;
      border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--border));
      border-radius: 6px;
      background: color-mix(in srgb, var(--panel) 86%, var(--status));
      color: var(--accent);
      font-size: 12px;
      font-weight: 900;
      text-decoration: none;
    }
    .asset-list {
      display: grid;
      gap: 9px;
      margin-top: 10px;
    }
    .asset-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: color-mix(in srgb, var(--status) 48%, white);
    }
    .asset-title {
      color: var(--text);
      font-size: 13px;
      font-weight: 900;
    }
    .asset-path {
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 760;
      overflow-wrap: anywhere;
    }
    .asset-controls {
      display: inline-flex;
      gap: 6px;
      align-items: center;
    }
    @media (max-width: 860px) {
      .shell { padding: 10px; }
      .hud, .main, .input-row { grid-template-columns: 1fr; }
      .player-vitals, .player-slots, .player-attributes { grid-template-columns: 1fr; }
      .state-badge { min-width: 0; }
      button { min-height: 58px; }
      .help-button { min-height: 30px; }
      .asset-row { grid-template-columns: 1fr; }
      .popup-layer { padding: 12px; }
      .popup-dialog { max-height: 84vh; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="hud">
      <section class="brand">
        <div class="sigil" id="headerIcon">◆</div>
        <div>
          <div class="title" id="appTitle">World Simulator</div>
          <div class="meta" id="metaLine">session · phase · turn</div>
        </div>
      </section>
      <section class="state-badge">
        <div class="state-label" id="stateLabel">STATE</div>
        <div class="state-text" id="stateText">Ready</div>
      </section>
    </header>
    <div class="processing" id="processingBanner"><span class="pulse"></span><span id="processingText"></span></div>
    <section class="main">
      <article class="panel">
        <div class="panel-title"><span id="historyTitle">History</span></div>
        <div class="content" id="history"></div>
      </article>
      <aside class="panel">
        <div class="panel-title"><span id="statusTitle">Status</span></div>
        <div class="content" id="status"></div>
      </aside>
    </section>
    <section class="input-deck">
      <div class="input-head">
        <span id="inputTitle">Input</span>
        <span class="input-tools">
          <span class="hint" id="inputHint"></span>
          <button class="help-button" id="helpButton" type="button" aria-label="Help">?</button>
        </span>
      </div>
      <div class="input-row">
        <textarea id="inputBox"></textarea>
        <button id="sendButton" type="button">Send</button>
      </div>
    </section>
  </main>
  <section class="popup-layer" id="popupLayer" aria-hidden="true">
    <article class="popup-dialog" id="popupDialog" role="dialog" aria-modal="true" aria-labelledby="popupTitle">
      <header class="popup-head">
        <div class="popup-title" id="popupTitle"></div>
        <button class="popup-close" id="popupClose" type="button">Close</button>
      </header>
      <div class="popup-body" id="popupBody"></div>
    </article>
  </section>
  <script>window.__INITIAL_STATE__ = __INITIAL_STATE_JSON__;</script>
  <script>
    const els = {
      headerIcon: document.getElementById("headerIcon"),
      appTitle: document.getElementById("appTitle"),
      metaLine: document.getElementById("metaLine"),
      stateLabel: document.getElementById("stateLabel"),
      stateText: document.getElementById("stateText"),
      processingBanner: document.getElementById("processingBanner"),
      processingText: document.getElementById("processingText"),
      historyTitle: document.getElementById("historyTitle"),
      statusTitle: document.getElementById("statusTitle"),
      inputTitle: document.getElementById("inputTitle"),
      inputHint: document.getElementById("inputHint"),
      helpButton: document.getElementById("helpButton"),
      history: document.getElementById("history"),
      status: document.getElementById("status"),
      inputBox: document.getElementById("inputBox"),
      sendButton: document.getElementById("sendButton"),
      popupLayer: document.getElementById("popupLayer"),
      popupDialog: document.getElementById("popupDialog"),
      popupTitle: document.getElementById("popupTitle"),
      popupBody: document.getElementById("popupBody"),
      popupClose: document.getElementById("popupClose"),
    };
    let lastOutput = "";
    let localSubmittedTurn = 0;
    let draftTimer = 0;
    let activePopupKey = "";
    let dismissedPopupKey = "";
    let lastData = window.__INITIAL_STATE__ || {};

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function text(value) {
      return String(value ?? "").replaceAll("\\n", "\n");
    }
    function label(icon, value) {
      return `${icon ? escapeHtml(icon) + " " : ""}${escapeHtml(value || "")}`;
    }
    function inlineMarkdown(value) {
      return escapeHtml(value)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    }
    function paragraphHtml(lines) {
      const raw = lines.join("\n");
      const body = lines.map(inlineMarkdown).join("<br>");
      if (/^[\"“”'‘’「『]/.test(raw.trim())) {
        return `<p class="dialogue">${body}</p>`;
      }
      return `<p>${body}</p>`;
    }
    function markdown(value, icon) {
      const lines = text(value).trim().split(/\r?\n/);
      const out = [];
      let para = [];
      let list = [];
      const flushPara = () => {
        if (para.length) out.push(paragraphHtml(para));
        para = [];
      };
      const flushList = () => {
        if (list.length) out.push(`<ul>${list.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
        list = [];
      };
      for (const raw of lines) {
        const line = raw.trim();
        if (!line) { flushPara(); flushList(); continue; }
        if (line.startsWith("# ")) {
          flushPara(); flushList();
          out.push(`<h1>${label(icon, line.slice(2).trim())}</h1>`);
        } else if (line.startsWith("## ")) {
          flushPara(); flushList();
          const heading = line.slice(3).trim();
          out.push(`<h2>${escapeHtml(heading)}</h2>`);
        } else if (line.startsWith("- ")) {
          flushPara();
          list.push(line.slice(2).trim());
        } else {
          flushList();
          para.push(line);
        }
      }
      flushPara(); flushList();
      return out.join("");
    }
    function renderHistory(latest, theme) {
      if (Array.isArray(latest.history_turns) && latest.history_turns.length) {
        return latest.history_turns.map(turn => {
          const labelText = turn.label || "";
          const labelHtml = labelText ? `<div class="history-turn-meta">${escapeHtml(labelText)}</div>` : "";
          return `<section class="history-turn">${labelHtml}${markdown(turn.markdown || "", theme.header_icon || "")}</section>`;
        }).join("");
      }
      return markdown(latest.history_markdown || "", theme.header_icon || "");
    }
    function applyTheme(theme) {
      const palette = theme.palette || {};
      const vars = {
        app_background: "--app",
        panel_background: "--panel",
        status_background: "--status",
        input_background: "--input",
        text: "--text",
        muted_text: "--muted",
        accent: "--accent",
        accent_2: "--accent2",
        border: "--border",
        selection: "--selection",
        button_text: "--buttonText",
        disabled_background: "--disabled",
        disabled_text: "--disabledText",
      };
      for (const [key, cssVar] of Object.entries(vars)) {
        if (palette[key]) document.documentElement.style.setProperty(cssVar, palette[key]);
      }
    }
    function toneClass(value) {
      const tone = String(value || "neutral").toLowerCase().replace(/[^a-z]/g, "");
      return ["good", "warning", "danger", "neutral"].includes(tone) ? ` tone-${tone}` : "";
    }
    function playerItem(item, className) {
      const value = text(item.value);
      const wide = value.length > 18 ? " wide" : "";
      return `<div class="${className}${wide}${toneClass(item.tone)}"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(value)}</strong></div>`;
    }
    function renderStatus(sections) {
      const list = Array.isArray(sections) ? sections : [sections];
      return list.map((section, index) => {
        if (!section || typeof section !== "object") return `<section class="status-card"><p>${escapeHtml(section)}</p></section>`;
        const kind = String(section.kind || "").toLowerCase().replace(/[^a-z0-9_-]/g, "");
        const rawFields = Array.isArray(section.fields) ? section.fields.filter(field => field && typeof field === "object") : [];
        const fields = rawFields.map(field => {
          if (!field || typeof field !== "object") return "";
          return `<div class="field${toneClass(field.tone)}"><div class="field-label">${escapeHtml(field.label)}</div><div class="field-value">${escapeHtml(text(field.value))}</div></div>`;
        }).join("");
        const playerSlots = rawFields.map(field => playerItem(field, "player-slot")).join("");
        const vitals = Array.isArray(section.vitals) ? section.vitals.filter(vital => vital && typeof vital === "object").map(vital => (
          playerItem(vital, "player-vital")
        )).join("") : "";
        const stats = Array.isArray(section.stats) ? section.stats.filter(stat => stat && typeof stat === "object").map(stat => (
          `<div class="player-attribute${toneClass(stat.tone)}"><span>${escapeHtml(stat.label)}</span><strong>${escapeHtml(text(stat.value))}</strong></div>`
        )).join("") : "";
        const groups = Array.isArray(section.groups) ? section.groups.filter(group => group && typeof group === "object").map(group => {
          const items = Array.isArray(group.items) ? group.items.filter(item => item && typeof item === "object").map(item => (
            `<div class="player-group-item${toneClass(item.tone)}"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(text(item.value))}</strong></div>`
          )).join("") : "";
          if (!items) return "";
          const groupTitle = label(group.icon, group.title || "");
          return `<div class="player-group"><div class="player-group-title">${groupTitle}</div><div class="player-group-items">${items}</div></div>`;
        }).join("") : "";
        const tags = Array.isArray(section.tags) && section.tags.length
          ? `<div class="tags">${section.tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>`
          : "";
        const playerFlags = Array.isArray(section.tags) && section.tags.length
          ? `<div class="player-flags">${section.tags.map(tag => `<span class="player-flag">${escapeHtml(tag)}</span>`).join("")}</div>`
          : "";
        const meters = Array.isArray(section.meters) ? section.meters.map(meter => {
          const value = Number(meter.value || 0);
          const max = Math.max(1, Number(meter.max || 1));
          const pct = Math.max(0, Math.min(100, Math.round((value / max) * 100)));
          return `<div class="meter${toneClass(meter.tone)}"><div class="meter-head"><span>${escapeHtml(meter.label)}</span><span>${value}/${max}</span></div><div class="meter-track"><div class="meter-fill" style="width:${pct}%"></div></div></div>`;
        }).join("") : "";
        const body = Array.isArray(section.body) ? section.body.join("\n") : (section.body || "");
        const meterBlock = meters ? `<div class="meters">${meters}</div>` : "";
        if (kind === "player") {
          const icon = `<div class="player-emblem">${escapeHtml(section.icon || "◆")}</div>`;
          const subtitle = section.subtitle ? `<div class="player-subtitle">${escapeHtml(section.subtitle)}</div>` : "";
          const summary = section.summary ? `<div class="player-summary">${escapeHtml(text(section.summary))}</div>` : "";
          const vitalBlock = vitals ? `<div class="player-vitals">${vitals}</div>` : "";
          const statsBlock = stats ? `<div class="player-attributes">${stats}</div>` : "";
          const slotBlock = playerSlots ? `<div class="player-slots">${playerSlots}</div>` : "";
          const groupsBlock = groups ? `<div class="player-groups">${groups}</div>` : "";
          return `<section class="status-card${index === 0 ? " primary" : ""} player"><div class="player-profile">${icon}<div class="player-id"><h3>${escapeHtml(section.title)}</h3>${subtitle}${summary}</div></div>${meterBlock}${vitalBlock}${statsBlock}${body ? markdown(body, "") : ""}${slotBlock}${groupsBlock}${playerFlags}</section>`;
        }
        return `<section class="status-card${index === 0 ? " primary" : ""}${kind ? ` ${kind}` : ""}"><h3>${label(section.icon, section.title)}</h3>${meterBlock}${body ? markdown(body, "") : ""}${fields}${tags}</section>`;
      }).join("");
    }
    function closePopup() {
      dismissedPopupKey = activePopupKey;
      els.popupLayer.classList.remove("on");
      els.popupLayer.setAttribute("aria-hidden", "true");
    }
    function popupAssetUrl(path) {
      return `/asset?path=${encodeURIComponent(String(path || ""))}`;
    }
    function assetRows(assets, help) {
      if (!Array.isArray(assets) || !assets.length) {
        return `<p>${escapeHtml(help.empty_assets || "No saved display images yet.")}</p>`;
      }
      return `<div class="asset-list">${assets.map((asset, index) => {
        const title = text(asset.title || asset.image_path || "");
        const path = text(asset.image_path || "");
        const caption = text(asset.caption || "");
        const captionHtml = caption ? `<div class="asset-path">${inlineMarkdown(caption)}</div>` : "";
        const url = popupAssetUrl(path);
        return `<div class="asset-row">
          <div>
            <div class="asset-title">${escapeHtml(title || path)}</div>
            ${captionHtml}
            <div class="asset-path">${escapeHtml(help.path_label || "Path")}: <code>${escapeHtml(path)}</code></div>
          </div>
          <div class="asset-controls">
            <button type="button" data-asset-index="${index}">${escapeHtml(help.open_label || "Open")}</button>
            <a href="${escapeHtml(url)}" download>${escapeHtml(help.download_label || "Download")}</a>
          </div>
        </div>`;
      }).join("")}</div>`;
    }
    function bindAssetOpeners(assets, theme) {
      els.popupBody.querySelectorAll("[data-asset-index]").forEach(button => {
        button.addEventListener("click", () => {
          const index = Number(button.getAttribute("data-asset-index"));
          const asset = Array.isArray(assets) ? assets[index] : null;
          if (!asset) return;
          renderPopup({
            id: `saved-display:${asset.image_path}:${Date.now()}`,
            title: asset.title || asset.image_path || "Display",
            image_path: asset.image_path,
            caption: asset.caption || "",
          }, theme);
        });
      });
    }
    function renderHelpPopup(data, theme) {
      const latest = data.latest || {};
      const language = latest.language === "ko" ? "ko" : "en";
      const fallback = {
        title: language === "ko" ? "도움말" : "Help",
        markdown: language === "ko"
          ? "## 명령어\n\n- `/show 요청`: 현재 세계에서 볼 수 있는 표시물을 Codex에게 요청합니다."
          : "## Commands\n\n- `/show request`: ask Codex to display a visible artifact available in the current world.",
        assets_title: language === "ko" ? "저장된 표시물" : "Saved Displays",
        empty_assets: language === "ko" ? "아직 저장된 표시 이미지가 없습니다." : "No saved display images yet.",
        open_label: language === "ko" ? "열기" : "Open",
        download_label: language === "ko" ? "다운로드" : "Download",
        path_label: language === "ko" ? "경로" : "Path",
      };
      const help = data.command_help || fallback;
      const assets = Array.isArray(data.display_assets) ? data.display_assets : [];
      activePopupKey = "__command_help__";
      dismissedPopupKey = "";
      els.popupDialog.className = "popup-dialog command-help";
      els.popupTitle.innerHTML = label("?", help.title || fallback.title);
      els.popupBody.innerHTML = `${markdown(help.markdown || fallback.markdown, "")}<h2>${escapeHtml(help.assets_title || fallback.assets_title)}</h2>${assetRows(assets, help)}`;
      els.popupClose.textContent = theme.popup_close_label || (language === "ko" ? "닫기" : "Close");
      bindAssetOpeners(assets, theme);
      els.popupLayer.classList.add("on");
      els.popupLayer.setAttribute("aria-hidden", "false");
      els.popupClose.focus();
    }
    function renderPopup(popup, theme) {
      if (!popup || typeof popup !== "object") {
        activePopupKey = "";
        dismissedPopupKey = "";
        els.popupLayer.classList.remove("on");
        els.popupLayer.setAttribute("aria-hidden", "true");
        return;
      }
      const key = String(popup.id || JSON.stringify(popup));
      if (!key || dismissedPopupKey === key) return;
      const title = text(popup.title || "");
      const body = Array.isArray(popup.markdown) ? popup.markdown.join("\n") : text(popup.markdown || popup.body || "");
      const caption = text(popup.caption || "");
      const imagePath = popup.image_path || popup.image || "";
      if (!title && !body && !caption && !imagePath) return;
      const kind = String(popup.kind || "").toLowerCase().replace(/[^a-z0-9_-]/g, "");
      els.popupDialog.className = `popup-dialog${kind ? ` ${kind}` : ""}`;
      els.popupTitle.innerHTML = label(popup.icon, title || theme.title || "Display");
      const imageUrl = imagePath ? popupAssetUrl(imagePath) : "";
      const imageHtml = imagePath ? `<img class="popup-image" src="${imageUrl}" alt="${escapeHtml(title || caption || "popup image")}">` : "";
      const actionHtml = imagePath
        ? `<div class="popup-actions"><a href="${escapeHtml(imageUrl)}" target="_blank" rel="noopener">${escapeHtml(theme.open_image_label || "Open image")}</a><a href="${escapeHtml(imageUrl)}" download>${escapeHtml(theme.download_image_label || "Download image")}</a><code>${escapeHtml(imagePath)}</code></div>`
        : "";
      const bodyHtml = body ? markdown(body, popup.icon || "") : "";
      const captionHtml = caption ? `<div class="popup-caption">${inlineMarkdown(caption)}</div>` : "";
      els.popupBody.innerHTML = `${imageHtml}${actionHtml}${bodyHtml}${captionHtml}`;
      els.popupClose.textContent = theme.popup_close_label || "Close";
      activePopupKey = key;
      dismissedPopupKey = "";
      els.popupLayer.classList.add("on");
      els.popupLayer.setAttribute("aria-hidden", "false");
      els.popupClose.focus();
    }
    function render(data) {
      lastData = data;
      const latest = data.latest || {};
      const theme = data.theme || {};
      applyTheme(theme);
      document.title = theme.title || "World Simulator";
      els.headerIcon.textContent = theme.header_icon || "◆";
      els.appTitle.textContent = theme.title || "World Simulator";
      els.historyTitle.innerHTML = label(theme.history_icon, theme.history_title || "History");
      els.statusTitle.innerHTML = label(theme.status_icon, theme.status_title || "Status");
      els.inputTitle.innerHTML = label(theme.input_icon, theme.input_title || "Input");
      els.inputHint.textContent = theme.input_hint || "";
      els.inputBox.placeholder = theme.input_placeholder || "";
      const outputKey = JSON.stringify(latest);
      if (outputKey !== lastOutput) {
        lastOutput = outputKey;
        els.history.innerHTML = renderHistory(latest, theme);
        els.status.innerHTML = renderStatus(latest.status_sections || []);
        const turns = els.history.querySelectorAll(".history-turn");
        if (turns.length) {
          turns[turns.length - 1].scrollIntoView({block: "start"});
        } else {
          els.history.scrollTop = els.history.scrollHeight;
        }
        renderPopup(latest.popup, theme);
      }
      const language = latest.language === "ko" ? "ko" : "en";
      els.helpButton.setAttribute("aria-label", (data.command_help && data.command_help.button_label) || (language === "ko" ? "도움말" : "Help"));
      els.metaLine.textContent = `${data.session_id} · ${data.phase_label || latest.phase || ""}`;
      els.stateLabel.textContent = language === "ko" ? "상태" : "STATE";
      els.stateText.textContent = data.processing ? (theme.processing_message || data.status_message) : (data.status_message || "");
      els.processingBanner.classList.toggle("on", Boolean(data.processing));
      els.processingText.textContent = `${theme.processing_message || data.status_message || ""} · ${theme.processing_detail || ""}`;
      els.inputBox.readOnly = Boolean(data.processing) || !latest.input_enabled;
      els.sendButton.disabled = Boolean(data.processing) || !latest.input_enabled;
      els.sendButton.textContent = data.processing ? (language === "ko" ? "처리 중..." : "Processing...") : (theme.send_label || "Send");
      if (data.clear_input || (localSubmittedTurn && Number(latest.turn_id || 0) >= localSubmittedTurn && !data.processing && latest.input_enabled)) {
        els.inputBox.value = "";
        localSubmittedTurn = 0;
        els.inputBox.focus();
      } else if (!els.inputBox.value && data.gui_state && data.gui_state.draft) {
        els.inputBox.value = data.gui_state.draft;
      }
    }
    async function poll() {
      try {
        const response = await fetch("/api/state", {cache: "no-store"});
        render(await response.json());
      } catch (error) {
        els.stateText.textContent = "Connection lost";
      }
    }
    async function submitInput() {
      const value = els.inputBox.value.trim();
      if (!value) return;
      const response = await fetch("/api/submit", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: value}),
      });
      const data = await response.json();
      if (data.submitted_turn_id) localSubmittedTurn = data.submitted_turn_id;
      render(data);
    }
    function saveDraftSoon() {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(() => {
        fetch("/api/draft", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text: els.inputBox.value}),
        }).catch(() => {});
      }, 350);
    }
    els.popupClose.addEventListener("click", closePopup);
    els.helpButton.addEventListener("click", () => {
      renderHelpPopup(lastData, lastData.theme || {});
    });
    els.popupLayer.addEventListener("click", event => {
      if (event.target === els.popupLayer) closePopup();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && els.popupLayer.classList.contains("on")) closePopup();
    });
    els.sendButton.addEventListener("click", submitInput);
    els.inputBox.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitInput();
      }
    });
    els.inputBox.addEventListener("input", saveDraftSoon);
    if (window.__INITIAL_STATE__) render(window.__INITIAL_STATE__);
    poll();
    setInterval(poll, 900);
  </script>
</body>
</html>
"""


def web_html(session_path: pathlib.Path) -> str:
    initial_state = json.dumps(web_state(session_path), ensure_ascii=False).replace("</", "<\\/")
    return WEB_HTML.replace("__INITIAL_STATE_JSON__", initial_state)


def phase_label_for_language(phase: str, latest: dict[str, Any] | None) -> str:
    return display_phase_label(phase, latest)


def web_state(session_path: pathlib.Path) -> dict[str, Any]:
    init_session(session_path)
    latest = read_json(ui_path(session_path, "latest_output.json"), {}) or {}
    pending = read_json(ui_path(session_path, "pending_input.json"), {}) or {}
    gui_state = read_json(ui_path(session_path, "gui_state.json"), {}) or {}
    display_assets = list_display_assets(session_path)
    processing = turn_id(pending) > turn_id(latest)
    clear_input = False
    waiting_clear = int_value(gui_state.get("submitted_turn_waiting_clear"))
    if waiting_clear and not processing and turn_id(latest) >= waiting_clear and bool(latest.get("input_enabled", True)):
        gui_state["draft"] = ""
        gui_state["submitted_turn_waiting_clear"] = 0
        gui_state["updated_at"] = utc_timestamp()
        atomic_write_json(ui_path(session_path, "gui_state.json"), gui_state)
        clear_input = True
    atomic_write_json(
        ui_path(session_path, "heartbeat.json"),
        {
            "session_id": session_path.name,
            "pid": os.getpid(),
            "backend": "web",
            "updated_at": utc_timestamp(),
        },
    )
    phase = str(latest.get("phase") or gui_state.get("phase") or "world_concept")
    message = runtime_text(latest, "processing") if processing else str(latest.get("status_message") or runtime_text(latest, "ready"))
    return {
        "session_id": session_path.name,
        "session_path": str(session_path),
        "latest": latest,
        "pending": pending,
        "gui_state": gui_state,
        "display_assets": display_assets,
        "command_help": command_help_payload(payload_language(latest), display_assets),
        "theme": normalized_theme(latest),
        "processing": processing,
        "clear_input": clear_input,
        "phase_label": phase_label_for_language(phase, latest),
        "status_message": message,
    }


def submit_web_input(session_path: pathlib.Path, text_value: str) -> dict[str, Any]:
    text_value = text_value.strip()
    if not text_value:
        raise WorldSimulatorError("input text is empty")
    latest = read_json(ui_path(session_path, "latest_output.json"), {}) or {}
    pending = read_json(ui_path(session_path, "pending_input.json"), {}) or {}
    if turn_id(pending) > turn_id(latest):
        state = web_state(session_path)
        state["error"] = runtime_text(latest, "processing")
        return state
    gui_state = read_json(ui_path(session_path, "gui_state.json"), {}) or {}
    next_turn = max(
        int(gui_state.get("next_turn_id", 1) or 1),
        turn_id(latest) + 1,
        turn_id(pending) + 1,
    )
    phase = str(latest.get("phase") or gui_state.get("phase") or "world_concept")
    payload = {
        "session_id": session_path.name,
        "turn_id": next_turn,
        "phase": phase,
        "text": text_value,
        "created_at": utc_timestamp(),
    }
    atomic_write_json(ui_path(session_path, "pending_input.json"), payload)
    gui_state.update(
        {
            "session_id": session_path.name,
            "next_turn_id": next_turn + 1,
            "phase": phase,
            "draft": text_value,
            "submitted_turn_waiting_clear": next_turn,
            "updated_at": utc_timestamp(),
        }
    )
    atomic_write_json(ui_path(session_path, "gui_state.json"), gui_state)
    state = web_state(session_path)
    state["submitted_turn_id"] = next_turn
    return state


def save_web_draft(session_path: pathlib.Path, text_value: str) -> dict[str, Any]:
    gui_state = read_json(ui_path(session_path, "gui_state.json"), {}) or {}
    gui_state.setdefault("session_id", session_path.name)
    gui_state.setdefault("next_turn_id", 1)
    gui_state["draft"] = text_value
    gui_state["updated_at"] = utc_timestamp()
    atomic_write_json(ui_path(session_path, "gui_state.json"), gui_state)
    return {"ok": True}


def display_assets_registry_path(session_path: pathlib.Path) -> pathlib.Path:
    return ui_path(session_path, "display_assets.json")


def read_display_assets_registry(session_path: pathlib.Path) -> dict[str, Any]:
    try:
        registry = read_json(display_assets_registry_path(session_path), {}) or {}
    except json.JSONDecodeError:
        return {}
    return registry if isinstance(registry, dict) else {}


def resolve_asset_path(session_path: pathlib.Path, requested_path: str) -> pathlib.Path:
    if not requested_path:
        raise WorldSimulatorError("asset path is empty")
    candidate = pathlib.Path(requested_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (session_path / candidate).resolve()
    asset_root = (session_path / "assets").resolve()
    try:
        resolved.relative_to(asset_root)
    except ValueError as exc:
        raise WorldSimulatorError("asset path must stay inside the session assets directory") from exc
    if not resolved.is_file():
        raise WorldSimulatorError("asset not found")
    return resolved


def normalized_asset_reference(session_path: pathlib.Path, requested_path: str) -> str:
    resolved = resolve_asset_path(session_path, requested_path)
    relative = resolved.relative_to(session_path.resolve())
    return pathlib.PurePosixPath(*relative.parts).as_posix()


def list_display_assets(session_path: pathlib.Path) -> list[dict[str, Any]]:
    registry = read_display_assets_registry(session_path)
    raw_items = registry.get("items")
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        image_path = str(raw_item.get("image_path") or "").strip()
        if not image_path:
            continue
        try:
            normalized_path = normalized_asset_reference(session_path, image_path)
        except WorldSimulatorError:
            continue
        item = {
            "id": str(raw_item.get("id") or normalized_path),
            "title": str(raw_item.get("title") or pathlib.Path(normalized_path).name),
            "image_path": normalized_path,
            "caption": str(raw_item.get("caption") or ""),
            "request": str(raw_item.get("request") or ""),
            "subject": str(raw_item.get("subject") or ""),
            "purpose": str(raw_item.get("purpose") or ""),
            "visible_scope": str(raw_item.get("visible_scope") or ""),
            "reuse_key": str(raw_item.get("reuse_key") or ""),
            "canon_refs": string_list(raw_item.get("canon_refs")),
            "reuse_tags": string_list(raw_item.get("reuse_tags")),
            "reuse_notes": str(raw_item.get("reuse_notes") or ""),
            "turn_id": int_value(raw_item.get("turn_id")),
            "created_at": str(raw_item.get("created_at") or ""),
            "last_seen_at": str(raw_item.get("last_seen_at") or ""),
        }
        items.append(item)
    return items


def command_help_payload(language: str, display_assets: list[dict[str, Any]]) -> dict[str, Any]:
    if normalized_language(language) == "ko":
        return {
            "title": "도움말",
            "markdown": (
                "## 명령어\n\n"
                "- `/show 요청`: 현재 세계에서 볼 수 있는 지도, 기록, 이미지, 시트 같은 표시물을 Codex에게 요청합니다.\n"
                "- Codex가 만든 표시 이미지는 이 세션에 저장되며, 아래 저장된 표시물 목록에서 다시 열 수 있습니다."
            ),
            "assets_title": "저장된 표시물",
            "empty_assets": "아직 저장된 표시 이미지가 없습니다.",
            "open_label": "열기",
            "download_label": "다운로드",
            "path_label": "경로",
            "button_label": "도움말",
        }
    return {
        "title": "Help",
        "markdown": (
            "## Commands\n\n"
            "- `/show request`: ask Codex to display a visible map, record, image, sheet, or other artifact available in the current world.\n"
            "- Display images created by Codex are saved in this session and can be reopened from the saved displays list below."
        ),
        "assets_title": "Saved Displays",
        "empty_assets": "No saved display images yet.",
        "open_label": "Open",
        "download_label": "Download",
        "path_label": "Path",
        "button_label": "Help",
    }


def command_help_popup(session_path: pathlib.Path, latest: dict[str, Any]) -> dict[str, Any]:
    display_assets = list_display_assets(session_path)
    help_payload = command_help_payload(payload_language(latest), display_assets)
    lines = [str(help_payload["markdown"]), "", f"## {help_payload['assets_title']}"]
    if display_assets:
        for asset in display_assets:
            title = str(asset.get("title") or asset.get("image_path") or "")
            image_path = str(asset.get("image_path") or "")
            caption = str(asset.get("caption") or "")
            detail = f" - {caption}" if caption else ""
            lines.append(f"- {title}: `{image_path}`{detail}")
    else:
        lines.append(str(help_payload["empty_assets"]))
    return {
        "id": "__command_help__",
        "title": str(help_payload["title"]),
        "markdown": "\n".join(lines),
    }


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def display_asset_metadata(popup: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = popup.get("display_asset")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    return {
        "request": str(metadata.get("request") or existing.get("request") or ""),
        "subject": str(metadata.get("subject") or existing.get("subject") or ""),
        "purpose": str(metadata.get("purpose") or existing.get("purpose") or ""),
        "visible_scope": str(metadata.get("visible_scope") or existing.get("visible_scope") or ""),
        "reuse_key": str(metadata.get("reuse_key") or existing.get("reuse_key") or ""),
        "canon_refs": string_list(metadata.get("canon_refs") or existing.get("canon_refs")),
        "reuse_tags": string_list(metadata.get("reuse_tags") or existing.get("reuse_tags")),
        "reuse_notes": str(metadata.get("reuse_notes") or existing.get("reuse_notes") or ""),
    }


def record_popup_display_asset(session_path: pathlib.Path, payload: dict[str, Any]) -> None:
    popup = payload.get("popup")
    if not isinstance(popup, dict):
        return
    image_path = str(popup.get("image_path") or "").strip()
    if not image_path:
        return
    try:
        normalized_path = normalized_asset_reference(session_path, image_path)
    except WorldSimulatorError:
        return

    existing_items = list_display_assets(session_path)
    existing = next((item for item in existing_items if item.get("image_path") == normalized_path), {})
    now = utc_timestamp()
    metadata = display_asset_metadata(popup, existing)
    item = {
        "id": str(popup.get("id") or existing.get("id") or normalized_path),
        "title": str(popup.get("title") or existing.get("title") or pathlib.Path(normalized_path).name),
        "image_path": normalized_path,
        "caption": str(popup.get("caption") or existing.get("caption") or ""),
        **metadata,
        "turn_id": turn_id(payload),
        "created_at": str(existing.get("created_at") or payload.get("published_at") or now),
        "last_seen_at": now,
    }
    items = [item] + [other for other in existing_items if other.get("image_path") != normalized_path]
    atomic_write_json(
        display_assets_registry_path(session_path),
        {
            "session_id": session_path.name,
            "items": items,
            "updated_at": now,
        },
    )


def run_web_gui(session_path: pathlib.Path, host: str, port: int, open_browser: bool) -> None:
    init_session(session_path)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: Any) -> None:
            return

        def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def send_file(self, path: pathlib.Path) -> None:
            data = path.read_bytes()
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def read_body_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                data = web_html(session_path).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path == "/api/state":
                self.send_json(web_state(session_path))
                return
            if parsed.path == "/asset":
                try:
                    params = urllib.parse.parse_qs(parsed.query)
                    asset_path = resolve_asset_path(session_path, str((params.get("path") or [""])[0]))
                    self.send_file(asset_path)
                except Exception as exc:
                    self.send_error(404, str(exc))
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                payload = self.read_body_json()
                if parsed.path == "/api/submit":
                    self.send_json(submit_web_input(session_path, str(payload.get("text") or "")))
                    return
                if parsed.path == "/api/draft":
                    self.send_json(save_web_draft(session_path, str(payload.get("text") or "")))
                    return
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)
                return
            self.send_error(404)

    server = None
    selected_port = port
    for candidate in range(port, port + 30):
        try:
            server = http.server.ThreadingHTTPServer((host, candidate), Handler)
            selected_port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise WorldSimulatorError(f"no available port from {port} to {port + 29}")
    url = f"http://{host}:{selected_port}/"
    print(f"world-simulator web GUI: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def run_gui(session_path: pathlib.Path, backend: str, host: str, port: int, open_browser: bool) -> None:
    if backend in {"auto", "web"}:
        run_web_gui(session_path, host, port, open_browser)
        return
    if backend in {"auto", "qt"}:
        try:
            run_qt_gui(session_path)
            return
        except ImportError:
            if backend == "qt":
                raise
    run_tk_gui(session_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="World Simulator GUI and Codex bridge")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--gui", action="store_true", help="Launch the GUI")
    mode.add_argument("--init-session", action="store_true", help="Create a session skeleton")
    mode.add_argument("--status", action="store_true", help="Print session status JSON")
    mode.add_argument("--wait-for-input", action="store_true", help="Block until the GUI submits input")
    mode.add_argument("--publish-output", metavar="PAYLOAD_JSON", help="Publish Codex output to the GUI")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Session root directory")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="Session slug or explicit session path")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval for --wait-for-input")
    parser.add_argument("--backend", choices=("auto", "web", "qt", "tk"), default="auto", help="GUI backend")
    parser.add_argument("--host", default="127.0.0.1", help="Web GUI host")
    parser.add_argument("--port", type=int, default=8765, help="Web GUI port")
    parser.add_argument("--no-open-browser", action="store_true", help="Do not open a browser for the web GUI")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    session_path = resolve_session(pathlib.Path(args.root), args.session)

    try:
        if args.init_session:
            print(json.dumps(init_session(session_path), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.status:
            init_session(session_path)
            print(json.dumps(session_status(session_path), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.wait_for_input:
            payload = wait_for_input(session_path, args.poll_interval)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.publish_output:
            status = publish_output(session_path, pathlib.Path(args.publish_output))
            print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.gui:
            run_gui(session_path, args.backend, args.host, args.port, not args.no_open_browser)
            return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"world-simulator: {exc}", file=sys.stderr)
        return 1

    parser.error("no mode selected")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
