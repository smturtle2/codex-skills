"""Compose client-specific response emphasis, preserving answer text."""

from pathlib import Path
from string import punctuation

from dialog_values import active_fields, validate_values

MARKDOWN_ESCAPES = str.maketrans({character: "\\" + character for character in punctuation})


def _label(value):
    return str(value).replace("\r", " ").replace("\n", " ")


def _bold_label(text):
    content = text.strip()
    if not content:
        return text
    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    # Literal padding must not turn a generated label into indented code.
    leading = "".join(f"&#{ord(character)};" for character in leading)
    trailing = "".join(f"&#{ord(character)};" for character in trailing)
    return leading + "**" + content.translate(MARKDOWN_ESCAPES) + "**" + trailing


def format_response(spec, values, button_label=None, *, include_values=True, markdown=False):
    if include_values:
        values = validate_values(spec, values)
    parts, elements = [], []
    offset = 0

    def append(text, *, emphasis=False):
        nonlocal offset
        if emphasis and markdown:
            text = _bold_label(text)
        end = offset + len(text.encode("utf-8"))
        if emphasis and not markdown and end > offset:
            elements.append({"byteRange": {"start": offset, "end": end}})
        parts.append(text)
        offset = end

    style = spec.get("message", {})
    title = _label(style.get("title", spec["title"]))
    source = " ".join(part for part in (style.get("icon", "💬"), "Popup response") if part)
    append(f"[{_label(source)} · {title}]", emphasis=True)
    append("\n")
    for node, _ in (active_fields(spec, values) if include_values else ()):
        value = values.values.get(node["id"])
        if value in (None, "", []):
            continue
        if node["type"] == "choice":
            selected = value if node.get("multiple") else [value]
            value = ", ".join(_label(option["label"]) for option in node["options"] if option["value"] in selected)
        elif node.get("format") == "boolean":
            value = _label(node.get("true_label", "On") if value else node.get("false_label", "Off"))
        elif node.get("format") == "file":
            path = Path(value).resolve()
            value = f"{path.name}\n{path}"
        append("\n")
        append(_label(node.get("response_label", node["label"])), emphasis=True)
        append("\n" + str(value) + "\n")
    if button_label:
        append("\n")
        append(f"→ {_label(button_label)}", emphasis=True)
        append("\n")
    return {"type": "text", "text": "".join(parts), "text_elements": elements}
