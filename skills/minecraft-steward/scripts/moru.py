#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=15.0"]
# ///
"""Operate MoruBridge and Minecraft Server Management Protocol without storing secrets."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import ssl
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

import websockets


class MoruError(RuntimeError):
    """A safe, user-facing failure while using a Moru endpoint."""


SAFE_SERVER_PROPERTIES = {
    "difficulty",
    "enforce-whitelist",
    "gamemode",
    "max-players",
    "motd",
    "online-mode",
    "player-idle-timeout",
    "simulation-distance",
    "spawn-protection",
    "view-distance",
    "white-list",
}

PROFILE_TEMPLATE = """# Keep token VALUES out of this file. Export the named environment variables instead.
[bridge]
url = "http://127.0.0.1:25576"
token_env = "MORU_BRIDGE_TOKEN"

[msmp]
# Enable this section only after configuring Minecraft Server Management Protocol.
url = "ws://127.0.0.1:25585"
token_env = "MORU_MSMP_TOKEN"

[context]
# server_root = "/absolute/path/to/your/server"
# guide_paths = ["/absolute/path/to/server-guide.md"]
"""


@dataclass(frozen=True)
class Endpoint:
    url: str
    token_env: str

    def token(self) -> str:
        value = os.environ.get(self.token_env, "")
        if not value:
            raise MoruError(f"environment variable {self.token_env} is not set")
        return value


@dataclass(frozen=True)
class Profile:
    path: pathlib.Path
    bridge: Endpoint
    msmp: Endpoint | None
    server_root: pathlib.Path | None
    guide_paths: tuple[pathlib.Path, ...]


def _endpoint(data: dict[str, Any], section: str, schemes: set[str]) -> Endpoint:
    value = data.get(section)
    if not isinstance(value, dict):
        raise MoruError(f"profile requires [{section}]")
    url = value.get("url")
    token_env = value.get("token_env")
    if not isinstance(url, str) or not isinstance(token_env, str) or not token_env:
        raise MoruError(f"[{section}] requires string url and token_env")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in schemes or not parsed.hostname:
        allowed = ", ".join(sorted(schemes))
        raise MoruError(f"[{section}].url must use {allowed} and include a host")
    return Endpoint(url=url.rstrip("/"), token_env=token_env)


def load_profile(path: str) -> Profile:
    profile_path = pathlib.Path(path).expanduser().resolve()
    try:
        with profile_path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise MoruError(f"profile does not exist: {profile_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MoruError(f"invalid TOML profile: {exc}") from exc
    if not isinstance(data, dict):
        raise MoruError("profile must be a TOML table")

    context = data.get("context", {})
    if not isinstance(context, dict):
        raise MoruError("[context] must be a table")
    root_value = context.get("server_root")
    server_root = pathlib.Path(root_value).expanduser().resolve() if isinstance(root_value, str) else None
    guide_values = context.get("guide_paths", [])
    if not isinstance(guide_values, list) or not all(isinstance(item, str) for item in guide_values):
        raise MoruError("context.guide_paths must be an array of paths")

    msmp = _endpoint(data, "msmp", {"ws", "wss"}) if "msmp" in data else None
    return Profile(
        path=profile_path,
        bridge=_endpoint(data, "bridge", {"http", "https"}),
        msmp=msmp,
        server_root=server_root,
        guide_paths=tuple(pathlib.Path(item).expanduser().resolve() for item in guide_values),
    )


def json_output(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def http_json(endpoint: Endpoint, method: str, path: str, body: bytes | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {endpoint.token()}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
    request = urllib.request.Request(endpoint.url + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise MoruError(f"bridge returned HTTP {exc.code}: {response_body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise MoruError(f"cannot reach MoruBridge: {exc.reason}") from exc
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MoruError("MoruBridge returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise MoruError("MoruBridge returned a non-object JSON value")
    return value


def cursor_path(profile: Profile, selected: str | None) -> pathlib.Path:
    if selected:
        return pathlib.Path(selected).expanduser().resolve()
    return profile.path.parent / ".moru-cursor.json"


def read_cursor(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"after": 0, "bridge_id": None}
    except json.JSONDecodeError as exc:
        raise MoruError(f"invalid cursor file: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("after", 0), int):
        raise MoruError(f"invalid cursor file: {path}")
    return value


def save_cursor(path: pathlib.Path, bridge_id: str | None, after: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps({"bridge_id": bridge_id, "after": after}) + "\n", encoding="utf-8")
    temp_path.replace(path)


def command_wait(profile: Profile, args: argparse.Namespace) -> None:
    state_path = cursor_path(profile, args.cursor)
    state = read_cursor(state_path)
    after = args.after if args.after is not None else int(state.get("after", 0))
    query = urllib.parse.urlencode({"after": after, "limit": args.limit, "wait": args.wait_seconds})
    response = http_json(profile.bridge, "GET", f"/v1/events?{query}")
    bridge_id = response.get("bridge_id")
    if state.get("bridge_id") and bridge_id and state["bridge_id"] != bridge_id and args.after is None:
        after = 0
        response = http_json(profile.bridge, "GET", f"/v1/events?{urllib.parse.urlencode({'after': 0, 'limit': args.limit, 'wait': 0})}")
        bridge_id = response.get("bridge_id")
    events = response.get("events", [])
    if not isinstance(events, list):
        raise MoruError("MoruBridge events response is invalid")
    event_ids = [item.get("id") for item in events if isinstance(item, dict) and isinstance(item.get("id"), int)]
    next_after = max(event_ids, default=after)
    save_cursor(state_path, bridge_id if isinstance(bridge_id, str) else None, next_after)
    response["next_after"] = next_after
    response["cursor_file"] = str(state_path)
    json_output(response)


def command_respond(profile: Profile, args: argparse.Namespace) -> None:
    if bool(args.public) == bool(args.direct):
        raise MoruError("choose exactly one of --public or --direct")
    if args.direct and not args.direct_message:
        raise MoruError("direct responses require a message after the player UUID")
    fields = {
        "action_id": str(uuid.uuid4()),
        "type": "public" if args.public else "direct",
        "message": args.public or args.direct_message,
    }
    if args.direct:
        fields["player_uuid"] = args.direct
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    json_output(http_json(profile.bridge, "POST", "/v1/actions", encoded))


def command_context(profile: Profile, args: argparse.Namespace) -> None:
    query = urllib.parse.urlencode({"player_uuid": args.player, "limit": args.limit})
    json_output(http_json(profile.bridge, "GET", f"/v1/context?{query}"))


def command_health(profile: Profile, _: argparse.Namespace) -> None:
    json_output(http_json(profile.bridge, "GET", "/v1/health"))


def parse_properties(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in SAFE_SERVER_PROPERTIES:
            values[key] = value
    return values


def command_snapshot(profile: Profile, args: argparse.Namespace) -> None:
    root = pathlib.Path(args.server_root).expanduser().resolve() if args.server_root else profile.server_root
    if root is None:
        raise MoruError("set context.server_root in the profile or pass --server-root")
    if not root.is_dir():
        raise MoruError(f"server root does not exist: {root}")
    plugins_dir = root / "plugins"
    plugins = sorted(item.name for item in plugins_dir.glob("*.jar")) if plugins_dir.is_dir() else []
    json_output(
        {
            "server_root": str(root),
            "server_properties": parse_properties(root / "server.properties"),
            "plugins": plugins,
        }
    )


def command_guide(profile: Profile, _: argparse.Namespace) -> None:
    if not profile.guide_paths:
        raise MoruError("set context.guide_paths in the profile")
    for path in profile.guide_paths:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise MoruError(f"guide does not exist: {path}") from exc
        if len(content.encode("utf-8")) > 128_000:
            raise MoruError(f"guide is too large: {path}")
        print(f"# Source: {path}\n\n{content.rstrip()}\n")


async def msmp_call(endpoint: Endpoint, method: str, params: Any) -> dict[str, Any]:
    request_id = 1
    request: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        request["params"] = params
    headers = {"Authorization": f"Bearer {endpoint.token()}"}
    ssl_context = ssl.create_default_context() if endpoint.url.startswith("wss://") else None
    try:
        async with websockets.connect(endpoint.url, additional_headers=headers, ssl=ssl_context, open_timeout=15) as socket:
            await socket.send(json.dumps(request))
            async with asyncio.timeout(25):
                async for raw_message in socket:
                    response = json.loads(raw_message)
                    if isinstance(response, dict) and response.get("id") == request_id:
                        return response
    except OSError as exc:
        raise MoruError(f"cannot reach MSMP: {exc}") from exc
    except websockets.WebSocketException as exc:
        raise MoruError(f"MSMP connection failed: {exc}") from exc
    raise MoruError("MSMP did not return a response")


def command_msmp(profile: Profile, args: argparse.Namespace) -> None:
    if profile.msmp is None:
        raise MoruError("profile has no [msmp] section")
    try:
        params = json.loads(args.params) if args.params is not None else None
    except json.JSONDecodeError as exc:
        raise MoruError("--params must be valid JSON") from exc
    json_output(asyncio.run(msmp_call(profile.msmp, args.method, params)))


def command_init_profile(args: argparse.Namespace) -> None:
    output = pathlib.Path(args.output).expanduser().resolve()
    if output.exists() and not args.force:
        raise MoruError(f"profile already exists: {output}; use --force to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(PROFILE_TEMPLATE, encoding="utf-8")
    print(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Moru TOML profile")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_profile = subparsers.add_parser("init-profile", help="write a token-free example profile")
    init_profile.add_argument("--output", required=True)
    init_profile.add_argument("--force", action="store_true")

    subparsers.add_parser("health", help="read MoruBridge health")

    wait = subparsers.add_parser("wait", help="block until bridge events arrive")
    wait.add_argument("--after", type=int)
    wait.add_argument("--cursor")
    wait.add_argument("--limit", type=int, default=16, choices=range(1, 65))
    wait.add_argument("--wait-seconds", type=int, default=25, choices=range(0, 26))

    respond = subparsers.add_parser("respond", help="send an authored Moru message")
    group = respond.add_mutually_exclusive_group(required=True)
    group.add_argument("--public", metavar="TEXT")
    group.add_argument("--direct", metavar="PLAYER_UUID")
    respond.add_argument("direct_message", nargs="?")

    context = subparsers.add_parser("context", help="read bounded recent context")
    context.add_argument("--player", required=True)
    context.add_argument("--limit", type=int, default=12, choices=range(1, 21))

    snapshot = subparsers.add_parser("snapshot", help="read non-secret server facts")
    snapshot.add_argument("--server-root")

    subparsers.add_parser("guide", help="print configured operator guide files")

    msmp = subparsers.add_parser("msmp", help="make one explicit MSMP JSON-RPC call")
    msmp.add_argument("--method", required=True)
    msmp.add_argument("--params")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init-profile":
            command_init_profile(args)
            return 0
        if not args.profile:
            raise MoruError("--profile is required for this command")
        profile = load_profile(args.profile)
        commands = {
            "health": command_health,
            "wait": command_wait,
            "respond": command_respond,
            "context": command_context,
            "snapshot": command_snapshot,
            "guide": command_guide,
            "msmp": command_msmp,
        }
        commands[args.command](profile, args)
    except MoruError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
