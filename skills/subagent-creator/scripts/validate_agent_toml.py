#!/usr/bin/env python3

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tomllib
from typing import Any


REQUIRED_KEYS = {"name", "description", "developer_instructions"}
OPTIONAL_KEYS = {
    "nickname_candidates",
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
    "mcp_servers",
    "skills",
}
ALLOWED_TOP_LEVEL_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS
BUILTIN_NAMES = {"default", "worker", "explorer"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
NICKNAME_RE = re.compile(r"^[A-Za-z0-9 _-]+$")
PLACEHOLDER_RE = re.compile(r"<[^>\n]+>|\bTODO\b")
GENERIC_FILLER_RE = re.compile(r"\b(helps with tasks|assists with work)\b", re.IGNORECASE)
KNOWN_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}


def collect_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(collect_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(collect_strings(item))
    return strings


def validate_agent(
    path: pathlib.Path,
    *,
    allow_builtin_override: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"TOML parse error: {exc}"], warnings

    if not isinstance(data, dict):
        return ["Top-level TOML value must be a table."], warnings

    unknown_keys = sorted(set(data) - ALLOWED_TOP_LEVEL_KEYS)
    if unknown_keys:
        errors.append(
            "Unknown top-level keys: " + ", ".join(f"`{key}`" for key in unknown_keys)
        )

    for key in sorted(REQUIRED_KEYS):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"`{key}` must be a non-empty string.")

    name = data.get("name")
    if isinstance(name, str):
        if not NAME_RE.fullmatch(name):
            errors.append(
                "`name` must use lowercase letters, digits, hyphens, or underscores."
            )
        if name in BUILTIN_NAMES and not allow_builtin_override:
            errors.append(
                "`name` matches a built-in agent. Pass `--allow-builtin-override` only "
                "when that override is intentional."
            )
        if path.stem != name:
            warnings.append(
                f"Filename stem `{path.stem}` does not match agent name `{name}`."
            )

    nickname_candidates = data.get("nickname_candidates")
    if nickname_candidates is not None:
        if not isinstance(nickname_candidates, list) or not nickname_candidates:
            errors.append("`nickname_candidates` must be a non-empty array of strings.")
        else:
            seen: set[str] = set()
            for item in nickname_candidates:
                if not isinstance(item, str) or not item.strip():
                    errors.append("Each nickname candidate must be a non-empty string.")
                    continue
                if item in seen:
                    errors.append("`nickname_candidates` must not contain duplicates.")
                seen.add(item)
                if not NICKNAME_RE.fullmatch(item):
                    errors.append(
                        "Nickname candidates may use only ASCII letters, digits, spaces, "
                        "hyphens, and underscores."
                    )

    for key in ("model", "model_reasoning_effort", "sandbox_mode"):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"`{key}` must be a non-empty string when present.")

    sandbox_mode = data.get("sandbox_mode")
    if isinstance(sandbox_mode, str) and sandbox_mode not in KNOWN_SANDBOX_MODES:
        warnings.append(
            f"`sandbox_mode` is `{sandbox_mode}`. Confirm that this value is supported "
            "by the current Codex release."
        )

    mcp_servers = data.get("mcp_servers")
    if mcp_servers is not None:
        if not isinstance(mcp_servers, dict) or not mcp_servers:
            errors.append("`mcp_servers` must be a non-empty table when present.")
        else:
            for server_name, server_config in mcp_servers.items():
                if not isinstance(server_name, str) or not server_name.strip():
                    errors.append("Each MCP server name must be a non-empty string.")
                if not isinstance(server_config, dict):
                    errors.append(
                        f"MCP server `{server_name}` must map to a TOML table."
                    )

    skills = data.get("skills")
    if skills is not None:
        if not isinstance(skills, dict) or not skills:
            errors.append("`skills` must be a non-empty table when present.")
        elif "config" not in skills:
            warnings.append(
                "`skills` is present without a `config` entry. Confirm that the shape "
                "matches current Codex config syntax."
            )

    for text in collect_strings(data):
        placeholder_match = PLACEHOLDER_RE.search(text)
        if placeholder_match:
            errors.append(
                f"Placeholder text found: `{placeholder_match.group(0)}`."
            )
        if GENERIC_FILLER_RE.search(text):
            warnings.append(
                "Generic filler detected (`helps with tasks` or `assists with work`)."
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Codex custom-agent TOML file used by subagent-creator."
    )
    parser.add_argument("path", help="Path to the custom-agent TOML file.")
    parser.add_argument(
        "--allow-builtin-override",
        action="store_true",
        help="Allow names that intentionally override built-in agents.",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    errors, warnings = validate_agent(
        path,
        allow_builtin_override=args.allow_builtin_override,
    )

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        return 1

    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
