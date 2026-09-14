"""Compile composable JSON views, resolve assets and own answer semantics."""

from copy import deepcopy
import json
from pathlib import Path
import re

class FieldError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


LAYOUTS = {"column", "row", "grid", "group", "tabs", "pages"}
TYPES = LAYOUTS | {"text", "markdown", "code", "file", "input", "choice", "button", "separator", "table"}


def initial_value(node):
    return deepcopy(node.get("value", False if node.get("format") == "boolean" else [] if node.get("multiple") else None))


def parse_json(text):
    def reject_constant(value):
        raise ValueError(f"Invalid JSON number: {value}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant,
                      object_pairs_hook=unique)


def read_json(path):
    return parse_json(path.read_text(encoding="utf-8"))


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)
    for option in node.get("options", []):
        for child in option.get("content", []):
            yield from walk(child)


def compile_request(request, base):
    if not isinstance(request, dict) or request.get("version", 1) != 1:
        raise ValueError("Request must be a version 1 JSON object")
    unknown = set(request) - {"version", "title", "subtitle", "body", "actions", "message", "width"}
    if unknown:
        raise ValueError(f"Unknown request keys: {', '.join(sorted(unknown))}")
    if not isinstance(request.get("title"), str) or not request["title"].strip():
        raise ValueError("A nonempty title is required")
    if not isinstance(request.get("width", 600), int) or not 300 <= request.get("width", 600) <= 2000:
        raise ValueError("width must be an integer from 300 to 2000")
    if not isinstance(request.get("message", {}), dict):
        raise ValueError("message must be an object")
    if set(request.get("message", {})) - {"title", "icon"}:
        raise ValueError("Unknown message presentation key")
    for key, value in request.get("message", {}).items():
        if not isinstance(value, str) or (key != "icon" and not value.strip()):
            raise ValueError(f"message.{key} must be a readable string")
    base = Path(base).resolve()

    def compile_node(node):
        if not isinstance(node, dict):
            raise ValueError("Every view node must be an object")
        node = deepcopy(node)
        if node.get("type") not in TYPES:
            raise ValueError(f"Unknown node type: {node.get('type')}")
        allowed = {"type", "id", "label", "visible_when", "enabled_when"}
        if node["type"] in LAYOUTS:
            allowed.add("children")
        if node["type"] in {"tabs", "pages"}:
            allowed.add("transition")
        allowed |= {"text": {"text", "ref"}, "markdown": {"text"}, "code": {"text", "language"}, "file": {"path"}, "input": {"format", "multiline", "required", "value", "min", "max", "placeholder", "error", "browse_label", "clear_label", "true_label", "false_label"},
                    "choice": {"options", "multiple", "required", "value", "error", "layout", "presentation"}, "separator": {"orientation"}, "table": {"columns", "rows"}, "button": {"action"}, "grid": {"columns"}, "pages": {"back_label", "next_label"}}.get(node["type"], set())
        if node["type"] in {"input", "choice"}:
            allowed.add("response_label")
        if set(node) - allowed:
            raise ValueError(f"Unknown {node['type']} properties: {sorted(set(node) - allowed)}")
        node["children"] = [compile_node(child) for child in node.get("children", [])]
        if "options" in node:
            node["options"] = [{**option, "content": [compile_node(child) for child in option.get("content", [])]}
                               for option in node["options"]]
        if node["type"] == "file":
            path = (base / Path(node["path"]).expanduser()).resolve()
            if not path.is_file():
                raise ValueError(f"File does not exist: {path}")
            node["path"] = str(path)
        return node

    result = deepcopy(request)
    result["body"] = compile_node(request["body"])
    result.setdefault("actions", [{"label": "Send", "action": {"type": "submit"}, "primary": True}])
    nodes = list(walk(result["body"]))
    ids = {}
    for node in nodes:
        kind = node["type"]
        if "transition" in node:
            transition = node["transition"]
            if (not isinstance(transition, dict)
                    or set(transition) - {"type", "duration"}
                    or transition.get("type", "none") not in {"none", "crossfade", "slide", "fade-through"}
                    or type(transition.get("duration", 120)) is not int
                    or not 0 <= transition.get("duration", 120) <= 1000):
                raise ValueError("transition needs type none/crossfade/slide/fade-through and duration 0..1000 ms")
        if "response_label" in node and (not isinstance(node["response_label"], str) or not node["response_label"].strip()):
            raise ValueError("response_label must be a nonempty string")
        if "label" in node and not isinstance(node["label"], str):
            raise ValueError("Labels must be strings")
        if kind == "text" and not isinstance(node.get("text", ""), str):
            raise ValueError("Text content must be a string")
        if kind == "markdown" and not isinstance(node.get("text"), str):
            raise ValueError("Markdown needs string text content")
        if kind == "code":
            if not isinstance(node.get("text"), str):
                raise ValueError("Code needs string text content")
            if "language" in node and not isinstance(node["language"], str):
                raise ValueError("Code language must be a string")
        for key in ("multiple", "multiline", "required"):
            if key in node and not isinstance(node[key], bool):
                raise ValueError(f"{key} must be boolean")
        if "id" in node:
            if not isinstance(node["id"], str) or not node["id"] or node["id"] in ids:
                raise ValueError(f"Invalid or duplicate id: {node.get('id')}")
            ids[node["id"]] = node
        if kind in {"input", "choice", "pages"} and "id" not in node:
            raise ValueError(f"{kind} needs an id")
        if kind in {"input", "choice", "button"} and not node.get("label"):
            raise ValueError(f"{kind} needs a readable label")
        if kind == "choice":
            if node.get("presentation", "list") not in {"list", "dropdown"}:
                raise ValueError("Choice presentation must be list or dropdown")
            if node.get("presentation") == "dropdown" and node.get("multiple"):
                raise ValueError("Dropdown choices are single selection")
            layout = node.get("layout", {"type": "column"})
            if not isinstance(layout, dict) or layout.get("type") not in {"column", "row", "grid"} or set(layout) - {"type", "columns"}:
                raise ValueError("Choice layout uses column, row or grid")
            if not isinstance(layout.get("columns", 2), int) or not 1 <= layout.get("columns", 2) <= 12:
                raise ValueError("Choice grid columns must be 1..12")
            options = node.get("options", [])
            values = [option.get("value") for option in options]
            if not options or any(not isinstance(value, str) or not value for value in values) or len(set(values)) != len(values):
                raise ValueError("Choice options need unique nonempty string values")
            if any(not isinstance(option.get("label"), str) or not option["label"] for option in options):
                raise ValueError("Every option needs a readable label")
        if kind == "input" and node.get("format", "text") not in {"text", "number", "date", "file", "boolean"}:
            raise ValueError("Input format must be text, number, date, file or boolean")
        if kind in {"tabs", "pages"} and (not node["children"] or any(not child.get("id") or not child.get("label") for child in node["children"])):
            raise ValueError("Tab/page children need id and label")
        if kind == "grid" and (not isinstance(node.get("columns", 2), int) or not 1 <= node.get("columns", 2) <= 12):
            raise ValueError("Grid columns must be 1..12")
        if kind == "separator" and node.get("orientation", "horizontal") not in {"horizontal", "vertical"}:
            raise ValueError("Separator orientation must be horizontal or vertical")
        if kind == "table":
            columns, rows = node.get("columns"), node.get("rows", [])
            if not isinstance(columns, list) or not columns or any(not isinstance(cell, str) for cell in columns):
                raise ValueError("Table columns must be a nonempty list of strings")
            if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(columns) or any(not isinstance(cell, str) for cell in row) for row in rows):
                raise ValueError("Table rows must contain one string per column")
        if kind == "input":
            for key in ("true_label", "false_label"):
                if key in node and (not isinstance(node[key], str) or not node[key].strip()):
                    raise ValueError(f"{key} must be a nonempty string")
            if node.get("format") == "boolean" and node.get("multiline"):
                raise ValueError("Boolean inputs cannot be multiline")
    def condition(value):
        if not isinstance(value, dict):
            raise ValueError("Conditions must be objects")
        if "all" in value or "any" in value:
            for entry in value.get("all", value.get("any")):
                condition(entry)
        elif "not" in value:
            condition(value["not"])
        elif value.get("ref") not in ids or ids[value["ref"]]["type"] not in {"input", "choice"}:
            raise ValueError(f"Condition references an unknown input: {value.get('ref')}")
        elif len(set(value) & {"equals", "contains", "empty"}) > 1 or set(value) - {"ref", "equals", "contains", "empty"}:
            raise ValueError("Unsupported condition operator")
    def action(value):
        if not isinstance(value, dict) or value.get("type") not in {"submit", "dismiss", "defer", "set", "toggle", "navigate"}:
            raise ValueError("Unknown action")
        if "include_values" in value and (value["type"] != "submit" or not isinstance(value["include_values"], bool)):
            raise ValueError("include_values is a boolean for submit actions only")
        if value["type"] == "set" and isinstance(value.get("value"), dict):
            if value["value"].get("ref") not in ids:
                raise ValueError("Unknown set value reference")
        if value["type"] in {"set", "toggle", "navigate"}:
            target = ids.get(value.get("target"))
            allowed = {"pages", "tabs"} if value["type"] == "navigate" else {"input", "choice"}
            if not target or target["type"] not in allowed:
                raise ValueError(f"Invalid action target: {value.get('target')}")
            if value["type"] == "toggle" and (target["type"] != "choice" or not target.get("multiple")):
                raise ValueError("toggle needs a multiple choice target")
            if value["type"] == "navigate" and value.get("page") not in {"next", "previous", *[child["id"] for child in target["children"]]}:
                raise ValueError("Unknown navigation destination")
    for node in nodes:
        if node["type"] == "text" and "ref" in node and (node["ref"] not in ids or ids[node["ref"]]["type"] not in {"input", "choice"}):
            raise ValueError(f"Unknown text binding: {node['ref']}")
    for node in nodes + result["actions"]:
        for key in ("visible_when", "enabled_when"):
            if key in node:
                condition(node[key])
        if "action" in node:
            action(node["action"])
        if node.get("type") == "button" and "action" not in node:
            raise ValueError("Button needs an action")
    for item in result["actions"]:
        if not isinstance(item.get("label"), str) or not item["label"].strip() or "action" not in item:
            raise ValueError("Footer actions need label and action")
    defaults = {node["id"]: initial_value(node) for node in nodes if node["type"] in {"input", "choice"}}
    validate_values(result, defaults, required=False)
    return result


def matches(condition, values):
    if condition is None:
        return True
    if "all" in condition:
        return all(matches(item, values) for item in condition["all"])
    if "any" in condition:
        return any(matches(item, values) for item in condition["any"])
    if "not" in condition:
        return not matches(condition["not"], values)
    value = values.get(condition["ref"])
    if "equals" in condition:
        return value == condition["equals"]
    if "contains" in condition:
        return isinstance(value, (str, list)) and condition["contains"] in value
    if "empty" in condition:
        return (value in (None, "", [])) == condition["empty"]
    return bool(value)


def active_fields(spec, values):
    def visit(node, groups):
        if not matches(node.get("visible_when"), values) or not matches(node.get("enabled_when"), values):
            return
        if node["type"] in {"input", "choice"}:
            yield node, groups
        if node.get("label") and node["type"] in {"group", "column"}:
            groups = [*groups, node["label"]]
        for child in node.get("children", []):
            yield from visit(child, groups)
        for option in node.get("options", []):
            selected = values.get(node.get("id"))
            if option["value"] == selected or isinstance(selected, list) and option["value"] in selected:
                for child in option.get("content", []):
                    yield from visit(child, [*groups, option["label"]])
    yield from visit(spec["body"], [])


def validate_values(spec, values, required=True):
    from datetime import date
    import math
    for node, _ in active_fields(spec, values):
        value = values.get(node["id"])
        def fail(message):
            raise FieldError(node["id"], message)
        if value in (None, "", []):
            if required and node.get("required"):
                fail(node.get("error", f"{node['label']}: required"))
            continue
        if node["type"] == "choice":
            selected = value if node.get("multiple") else [value]
            valid = [option["value"] for option in node["options"]]
            if not isinstance(selected, list) or any(item not in valid for item in selected) or len(set(selected)) != len(selected):
                fail(f"{node['label']}: invalid selection")
        elif node.get("format") == "boolean":
            if not isinstance(value, bool):
                fail(f"{node['label']}: expected boolean")
        elif node.get("format") == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                fail(f"{node['label']}: invalid number")
            if value < node.get("min", -math.inf) or value > node.get("max", math.inf):
                fail(f"{node['label']}: outside allowed range")
        elif not isinstance(value, str):
            fail(f"{node['label']}: expected text")
        elif node.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                fail(f"{node['label']}: use YYYY-MM-DD")
        elif node.get("format") == "file" and not Path(value).is_file():
            fail(f"{node['label']}: missing file")


def escape(text):
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", str(text)).replace("\n", " ")


def format_response(spec, values, button_label=None, *, include_values=True):
    """Markdown presentation follows the view; typed prose stays verbatim."""
    if include_values:
        validate_values(spec, values)
    style = spec.get("message", {})
    title = style.get("title", spec["title"])
    source = " ".join(part for part in (style.get("icon", "💬"), "Popup response") if part)
    lines = [f"**[{escape(source)} · {escape(title)}]**"]
    for node, _ in (active_fields(spec, values) if include_values else ()):
        value = values.get(node["id"])
        if value in (None, "", []):
            continue
        label = escape(node.get("response_label", node["label"]))
        if node["type"] == "choice":
            selected = value if node.get("multiple") else [value]
            value = ", ".join(escape(option["label"]) for option in node["options"] if option["value"] in selected)
        elif node.get("format") == "boolean":
            value = escape(node.get("true_label", "On") if value else node.get("false_label", "Off"))
        elif node.get("format") == "file":
            path = Path(value).resolve()
            value = f"[{escape(path.name)}](<{path}>)"
        lines += ["", f"**{label}**  ", str(value)]
    if button_label:
        lines += ["", f"**→ {escape(button_label)}**"]
    return "\n".join(lines) + "\n"
