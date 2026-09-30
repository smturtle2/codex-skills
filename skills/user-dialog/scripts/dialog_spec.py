"""Compile authored JSON views and resolve their assets and references."""

from copy import deepcopy
import json
import math
from pathlib import Path

from dialog_values import FieldError, active_fields, condition_refs, initial_value, matches, validate_values, walk

LAYOUTS = {"column", "row", "grid", "group", "tabs", "pages"}
TYPES = LAYOUTS | {"markdown", "code", "file", "input", "choice", "button", "separator", "table"}


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
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            reject_constant(text)
        return value
    return json.loads(text, parse_constant=reject_constant, parse_float=finite_float,
                      object_pairs_hook=unique)


def read_json(path):
    return parse_json(path.read_text(encoding="utf-8"))


def validate_dependencies(spec):
    """Controllers must remain reachable when a dependent field is invalid."""
    nodes = list(walk(spec['body']))
    dependencies = {node['id']: set() for node in nodes if node['type'] in {'input', 'choice'}}
    for node in nodes:
        fields = {child['id'] for child in walk(node) if child['type'] in {'input', 'choice'}}
        refs = set(condition_refs(node.get('visible_when')))
        refs.update(condition_refs(node.get('enabled_when')))
        internal = fields & refs
        if internal:
            owner = node.get('id') or node.get('label') or node['type']
            raise ValueError(f"Condition on {owner} depends on its own field or descendant: {', '.join(sorted(internal))}")
        for key in fields:
            dependencies[key].update(refs)
        if node['type'] == 'choice':
            for option in node['options']:
                for child in option.get('content', []):
                    for nested in walk(child):
                        if nested['type'] in {'input', 'choice'}:
                            dependencies[nested['id']].add(node['id'])
    done, visiting = set(), []
    def visit(key):
        if key in visiting:
            cycle = visiting[visiting.index(key):] + [key]
            raise ValueError('Cyclic field conditions: ' + ' -> '.join(cycle))
        if key in done:
            return
        visiting.append(key)
        for source in sorted(dependencies[key]):
            visit(source)
        visiting.pop()
        done.add(key)
    for key in sorted(dependencies):
        visit(key)


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
        allowed |= {"markdown": {"text", "ref", "display"}, "code": {"text", "language"}, "file": {"path", "display"}, "input": {"format", "multiline", "required", "value", "min", "max", "placeholder", "error", "browse_label", "clear_label", "true_label", "false_label"},
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
        if kind == "markdown":
            if ('text' in node) == ('ref' in node):
                raise ValueError('Markdown needs exactly one of text or ref')
            if 'text' in node and not isinstance(node['text'], str):
                raise ValueError('Markdown text must be a string')
        if 'display' in node:
            display = node['display']
            if (not isinstance(display, dict) or set(display) - {'title', 'border', 'copy_source', 'copy_code'}
                    or any(type(value) is not bool for value in display.values())):
                raise ValueError('display accepts boolean title, border, copy_source, copy_code')
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
            for key in ("min", "max"):
                if key in node and (isinstance(node[key], bool) or not isinstance(node[key], (int, float))
                                    or isinstance(node[key], float) and not math.isfinite(node[key])):
                    raise ValueError(f"{key} must be a finite number")
            if node.get("min", -math.inf) > node.get("max", math.inf):
                raise ValueError("min must not exceed max")
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
            source = ids.get(value["value"].get("ref"))
            if not source or source['type'] not in {'input', 'choice'}:
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
        if node["type"] == "markdown" and "ref" in node and (not isinstance(node['ref'], str) or node["ref"] not in ids or ids[node["ref"]]["type"] not in {"input", "choice"}):
            raise ValueError(f"Unknown Markdown binding: {node['ref']}")
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
    validate_dependencies(result)
    defaults = {node["id"]: initial_value(node) for node in nodes if node["type"] in {"input", "choice"}}
    validate_values(result, defaults, required=False, base=base)
    return result
