#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from typing import Any


REQUIRED_KEYS = {"name", "description", "developer_instructions"}
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


def normalized_nickname(value: str) -> str:
    return value.strip()


def validate_skills(skills: Any, errors: list[str]) -> None:
    if not isinstance(skills, dict) or not skills:
        errors.append("`skills` must be a non-empty table when present.")
        return

    config = skills.get("config")
    if config is None:
        return
    if not isinstance(config, list):
        errors.append("`skills.config` must be an array of tables.")
        return

    for index, entry in enumerate(config):
        label = f"`skills.config[{index}]`"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be a table.")
            continue
        if not isinstance(entry.get("enabled"), bool):
            errors.append(f"{label}.enabled must be a boolean.")
        for selector in ("name", "path"):
            value = entry.get(selector)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{label}.{selector} must be a non-empty string.")


def validate_mcp_servers(mcp_servers: Any, errors: list[str]) -> None:
    if not isinstance(mcp_servers, dict) or not mcp_servers:
        errors.append("`mcp_servers` must be a non-empty table when present.")
        return

    for server_name, server_config in mcp_servers.items():
        if not isinstance(server_name, str) or not server_name.strip():
            errors.append("Each MCP server name must be a non-empty string.")
        if not isinstance(server_config, dict):
            errors.append(f"MCP server `{server_name}` must map to a TOML table.")
            continue

        has_command = "command" in server_config
        has_url = "url" in server_config
        if has_command == has_url:
            errors.append(
                f"MCP server `{server_name}` must define exactly one transport: "
                "`command` or `url`."
            )
        for transport in ("command", "url"):
            value = server_config.get(transport)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(
                    f"MCP server `{server_name}` field `{transport}` must be a "
                    "non-empty string."
                )

        args = server_config.get("args")
        if args is not None and (
            not isinstance(args, list)
            or any(not isinstance(item, str) for item in args)
        ):
            errors.append(
                f"MCP server `{server_name}` field `args` must be an array of strings."
            )


def validate_agent_data(
    data: Any,
    intended_path: pathlib.Path,
    *,
    allow_builtin_override: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["Top-level TOML value must be a table."], warnings

    for key in sorted(REQUIRED_KEYS):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"`{key}` must be a non-empty string.")

    name = data.get("name")
    if isinstance(name, str) and name.strip():
        if not NAME_RE.fullmatch(name):
            warnings.append(
                "`name` does not follow the recommended lowercase ASCII naming style."
            )
        if name in BUILTIN_NAMES and not allow_builtin_override:
            errors.append(
                "`name` matches a built-in agent. Pass `--allow-builtin-override` only "
                "when that override is intentional."
            )
        if intended_path.stem != name:
            warnings.append(
                f"Filename stem `{intended_path.stem}` does not match agent name `{name}`."
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
                normalized = normalized_nickname(item)
                if normalized in seen:
                    errors.append(
                        "`nickname_candidates` must not contain case-sensitive "
                        "duplicates after trimming."
                    )
                seen.add(normalized)
                if not NICKNAME_RE.fullmatch(normalized):
                    errors.append(
                        "Nickname candidates may use only ASCII letters, digits, spaces, "
                        "hyphens, and underscores."
                    )

    for key in ("model", "model_reasoning_effort"):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"`{key}` must be a non-empty string when present.")

    sandbox_mode = data.get("sandbox_mode")
    if sandbox_mode is not None and (
        not isinstance(sandbox_mode, str)
        or sandbox_mode not in KNOWN_SANDBOX_MODES
    ):
        allowed = ", ".join(f"`{mode}`" for mode in sorted(KNOWN_SANDBOX_MODES))
        errors.append(f"`sandbox_mode` must be one of: {allowed}.")

    if "mcp_servers" in data:
        validate_mcp_servers(data["mcp_servers"], errors)
    if "skills" in data:
        validate_skills(data["skills"], errors)

    for text in collect_strings(data):
        placeholder_match = PLACEHOLDER_RE.search(text)
        if placeholder_match:
            warnings.append(f"Placeholder text found: `{placeholder_match.group(0)}`.")
        if GENERIC_FILLER_RE.search(text):
            warnings.append(
                "Generic filler detected (`helps with tasks` or `assists with work`)."
            )

    return errors, warnings


def native_codex_validation(
    contents: str,
    intended_path: pathlib.Path,
) -> tuple[list[str], list[str]]:
    codex = shutil.which("codex")
    if codex is None:
        return [], [
            "Native Codex validation is unavailable; additional configuration keys "
            "were not verified."
        ]

    try:
        with tempfile.TemporaryDirectory(prefix="subagent-creator-") as tmpdir:
            codex_home = pathlib.Path(tmpdir)
            agents_dir = codex_home / "agents"
            agents_dir.mkdir()
            candidate = agents_dir / "candidate.toml"
            candidate.write_text(contents, encoding="utf-8")

            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)
            result = subprocess.run(
                [codex, "doctor", "--json"],
                check=False,
                capture_output=True,
                text=True,
                cwd=codex_home,
                env=env,
                timeout=20,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], [
            "Native Codex validation could not run; additional configuration keys "
            f"were not verified ({exc})."
        ]

    try:
        report = json.loads(result.stdout)
        check = report["checks"]["config.load"]
        status = check["status"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [], [
            "Native Codex validation returned an unsupported report; additional "
            "configuration keys were not verified."
        ]

    if status == "ok":
        return [], []

    details = check.get("details")
    detail_text = json.dumps(details, ensure_ascii=False) if details is not None else ""
    summary = str(check.get("summary", ""))
    native_message = " ".join(part for part in (summary, detail_text) if part).strip()
    has_startup_warning = isinstance(details, dict) and "startup warning" in details
    if (
        status == "fail"
        or has_startup_warning
        or "malformed agent role definition" in native_message
    ):
        return [f"Codex rejected the agent definition: {native_message}"], []

    return [], [
        f"Native Codex config validation reported `{status}` without a recognizable "
        "candidate error; additional configuration keys were not fully verified."
    ]


def read_input(source: str) -> tuple[str | None, str | None]:
    try:
        if source == "-":
            return sys.stdin.buffer.read().decode("utf-8"), None
        return pathlib.Path(source).read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, f"Could not read `{source}` as UTF-8 TOML: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Codex custom-agent TOML file used by subagent-creator."
    )
    parser.add_argument("path", help="Path to the custom-agent TOML file, or `-` for stdin.")
    parser.add_argument(
        "--expected-path",
        help="Intended output path; required with stdin and used without creating it.",
    )
    parser.add_argument(
        "--allow-builtin-override",
        action="store_true",
        help="Allow names that intentionally override built-in agents.",
    )
    args = parser.parse_args()

    if args.path == "-" and not args.expected_path:
        parser.error("--expected-path is required when reading TOML from stdin")
    if args.path != "-" and args.expected_path:
        parser.error("--expected-path may only be used when reading TOML from stdin")

    contents, read_error = read_input(args.path)
    if read_error:
        print(f"ERROR: {read_error}", file=sys.stderr)
        return 1
    assert contents is not None

    intended_path = pathlib.Path(args.expected_path or args.path)
    try:
        data = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as exc:
        print(f"ERROR: TOML parse error: {exc}", file=sys.stderr)
        return 1

    errors, warnings = validate_agent_data(
        data,
        intended_path,
        allow_builtin_override=args.allow_builtin_override,
    )
    if not errors:
        native_errors, native_warnings = native_codex_validation(contents, intended_path)
        errors.extend(native_errors)
        warnings.extend(native_warnings)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        return 1

    print(f"OK: {intended_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
