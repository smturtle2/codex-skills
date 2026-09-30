"""Editable drafts, typed field values and conditions share one conversion model."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import re


class FieldError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


@dataclass
class NormalizedValues:
    values: dict
    errors: dict


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)
    for option in node.get("options", []):
        for child in option.get("content", []):
            yield from walk(child)


def initial_value(node):
    return editable_value(node, node.get("value", False if node.get("format") == "boolean"
                                        else [] if node.get("multiple") else None))


def editable_value(node, value):
    # GTK editors own text, including incomplete numbers. Convert legacy numeric
    # drafts and authored numeric defaults once at the editor boundary, not on
    # keystrokes. Nonfinite legacy numbers become editable, invalid text too.
    if node.get("format") == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return deepcopy(value)


def editable_values(spec, values):
    return {node["id"]: editable_value(node, values[node["id"]])
            for node in walk(spec["body"])
            if node["type"] in {"input", "choice"} and node["id"] in values}


def empty(value):
    return value is None or value == "" or value == []


def normalize_values(spec, draft, base=None):
    """Convert without changing the draft; retain an error for every invalid field."""
    if isinstance(draft, NormalizedValues):
        return draft
    base = Path.cwd() if base is None else Path(base)
    values, errors = {}, {}
    for node in walk(spec["body"]):
        if node["type"] not in {"input", "choice"}:
            continue
        key, value = node["id"], draft.get(node["id"])
        values[key] = None
        if empty(value):
            values[key] = deepcopy(value)
            continue
        try:
            if node["type"] == "choice":
                selected = value if node.get("multiple") else [value]
                allowed = {option["value"] for option in node["options"]}
                if (not isinstance(selected, list) or any(not isinstance(item, str) or item not in allowed for item in selected)
                        or len(set(selected)) != len(selected)):
                    raise ValueError("invalid selection")
                value = deepcopy(value)
            elif node.get("format") == "boolean":
                if type(value) is not bool:
                    raise ValueError("expected boolean")
            elif node.get("format") == "number":
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    raise ValueError("invalid number")
                text = str(value).strip()
                try:
                    value = int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
                except (ValueError, OverflowError) as error:
                    raise ValueError("invalid number") from error
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("invalid number")
                if value < node.get("min", -math.inf) or value > node.get("max", math.inf):
                    raise ValueError("outside allowed range")
            elif not isinstance(value, str):
                raise ValueError("expected text")
            elif node.get("format") == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("use YYYY-MM-DD")
                try:
                    value = date.fromisoformat(value).isoformat()
                except ValueError as error:
                    raise ValueError("use YYYY-MM-DD") from error
            elif node.get("format") == "file":
                path = (base / Path(value).expanduser()).resolve()
                if not path.is_file():
                    raise ValueError("missing file")
                value = str(path)
            values[key] = value
        except ValueError as error:
            errors[key] = f"{node['label']}: {error}"
    return NormalizedValues(values, errors)


def _evaluate(condition, normalized):
    """Three-valued conditions keep invalid references unknown through negation."""
    if condition is None:
        return True
    if "all" in condition or "any" in condition:
        conjunction = "all" in condition
        results = [_evaluate(item, normalized) for item in condition["all" if conjunction else "any"]]
        decisive = False if conjunction else True
        if decisive in results:
            return decisive
        return None if None in results else not decisive
    if "not" in condition:
        result = _evaluate(condition["not"], normalized)
        return None if result is None else not result
    key = condition["ref"]
    if key in normalized.errors or key not in normalized.values:
        return None
    value = normalized.values[key]
    if "equals" in condition:
        return value == condition["equals"]
    if "contains" in condition:
        return isinstance(value, (str, list)) and condition["contains"] in value
    if "empty" in condition:
        return empty(value) == condition["empty"]
    return bool(value)


def matches(condition, values):
    normalized = values if isinstance(values, NormalizedValues) else NormalizedValues(values, {})
    return _evaluate(condition, normalized) is True


def condition_refs(condition):
    """Traverse condition operators, without interpreting literal comparison values."""
    if condition is None:
        return
    if 'all' in condition or 'any' in condition:
        for item in condition.get('all', condition.get('any')):
            yield from condition_refs(item)
    elif 'not' in condition:
        yield from condition_refs(condition['not'])
    else:
        yield condition['ref']


def option_selected(values, key, option):
    normalized = values if isinstance(values, NormalizedValues) else NormalizedValues(values, {})
    if key in normalized.errors:
        return False
    selected = normalized.values.get(key)
    return option in selected if isinstance(selected, list) else option == selected


def active_fields(spec, values):
    normalized = normalize_values(spec, values)
    def visit(node, groups):
        if not matches(node.get("visible_when"), normalized) or not matches(node.get("enabled_when"), normalized):
            return
        if node["type"] in {"input", "choice"}:
            yield node, groups
        if node.get("label") and node["type"] in {"group", "column"}:
            groups = [*groups, node["label"]]
        for child in node.get("children", []):
            yield from visit(child, groups)
        for option in node.get("options", []):
            if option_selected(normalized, node.get("id"), option["value"]):
                for child in option.get("content", []):
                    yield from visit(child, [*groups, option["label"]])
    yield from visit(spec["body"], [])


def validate_values(spec, values, required=True, base=None):
    normalized = normalize_values(spec, values, base)
    for node, _ in active_fields(spec, normalized):
        key = node["id"]
        if key in normalized.errors:
            raise FieldError(key, normalized.errors[key])
        if required and node.get("required") and empty(normalized.values.get(key)):
            raise FieldError(key, node.get("error", f"{node['label']}: required"))
    return normalized
