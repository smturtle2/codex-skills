# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compose a dialog from JSON and send Markdown to its originating Codex task."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid

from dialog_state import encode, read_state, run_lock, save_state
from dialog_spec import compile_request, read_json, parse_json, TYPES
from dialog_delivery import capture_origin, require_owner, deliver, confirm_delivery
from dialog_updates import send_update


PROBE = """
import json, sys
if sys.version_info < (3, 11):
    raise RuntimeError('Python 3.11 or newer is required')
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
if (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 16):
    raise RuntimeError('GTK 4.16 or newer is required')
if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 6):
    raise RuntimeError('libadwaita 1.6 or newer is required')
print(json.dumps({'python': sys.executable, 'gtk': [Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()], 'adwaita': [Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version()]}))
"""


def candidates(explicit):
    if explicit:
        return [explicit]
    configured = os.environ.get("USER_DIALOG_PYTHON")
    if configured:
        return [configured]
    paths = [sys.executable, shutil.which("python3"), shutil.which("python")]
    if sys.platform == "darwin":
        paths += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
    elif os.name == "nt":
        paths += [str(Path(os.environ.get("SystemDrive", "C:") + "/") / "msys64" / "ucrt64" / "bin" / "python.exe")]
    else:
        paths += ["/usr/bin/python3", "/usr/local/bin/python3"]
    return list(dict.fromkeys(path for path in paths if path))


def python_environment(executable):
    environment = os.environ.copy()
    if os.name == "nt":
        binary = str(Path(executable).absolute().parent)
        environment["PATH"] = binary + os.pathsep + environment.get("PATH", "")
        environment["PYGI_DLL_PATH"] = binary + os.pathsep + environment.get("PYGI_DLL_PATH", "")
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def find_python(explicit=None):
    failures = []
    for candidate in candidates(explicit):
        executable = shutil.which(candidate) or candidate
        if not Path(executable).is_file():
            continue
        try:
            process = subprocess.run([executable, "-c", PROBE], capture_output=True,
                                     text=True, encoding="utf-8", timeout=20,
                                     env=python_environment(executable))
            if process.returncode == 0:
                return json.loads(process.stdout)
            failures.append({"python": executable, "error": process.stderr.strip()})
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            failures.append({"python": executable, "error": str(error)})
    raise ValueError("No compatible GTK Python found. See references/view-contract.md#runtime; "
                     "select one with --python or USER_DIALOG_PYTHON. " + encode(failures))


def read_request(source):
    if source == "-":
        request = parse_json(sys.stdin.read())
    else:
        request = read_json(Path(source).expanduser().resolve())
    return request


def load_request(source, base=None):
    return compile_request(read_request(source), Path.cwd() if base is None else Path(base).expanduser().resolve())


def summary(directory, state):
    result = {"request_id": state["request_id"], "status": state["status"],
              "run_dir": str(directory), "delivery": state.get("delivery", {}).get("status"),
              "revision": state.get("revision", 0)}
    if "update" in state:
        result["update"] = state["update"]
    if state.get("delivery", {}).get("observation"):
        result["observation"] = state["delivery"]["observation"]
    if state.get("delivery", {}).get("error"):
        result["error"] = state["delivery"]["error"]
    if state.get("response", {}).get("error"):
        result["error"] = state["response"]["error"]
    return result


def run_dialog(args):
    if args.command == "update":
        directory = Path(args.run_dir).expanduser().resolve()
        state = read_state(directory)
        spec = read_request(args.request)
        compile_request(spec, Path(state['base']))
        result = send_update(directory, spec, expected_revision=args.revision, timeout=args.timeout)
        print(encode(result))
        return 0 if result.get("status") in {"queued", "applied"} else 1
    if args.command == "show":
        if args.render_image and not args.preview:
            raise ValueError("--render-image requires --preview")
        spec = load_request(args.request)
        origin = None if args.preview else capture_origin()
        runtime = find_python(args.python)
        directory = Path(args.run_dir or Path.cwd() / ".codex-skills" / "user-dialog" / uuid.uuid4().hex).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
    else:
        directory = Path(args.run_dir).expanduser().resolve()
    with run_lock(directory):
        with run_lock(directory, ".window-lock"):
            pass
        if args.command == "show":
            if (directory / "state.json").exists():
                raise ValueError("Run already exists; use resume or a new directory")
            state = {"version": 2, "request_id": uuid.uuid4().hex, "status": "pending",
                     "spec": spec, "base": str(Path.cwd()), "origin": origin,
                     "title": spec["title"], "subtitle": spec.get("subtitle", ""),
                     "draft": {}, "response": {}, "revision": 0,
                     "delivery": {"status": "preview" if args.preview else "pending"}}
            if args.render_image:
                state["render_image"] = str(Path(args.render_image).expanduser().resolve())
        else:
            state = read_state(directory)
            if state.get("origin"):
                require_owner(state["origin"])
            if args.command in {"deliver", "confirm"}:
                if not state.get("origin"):
                    raise ValueError("Preview runs cannot be delivered")
                operation = confirm_delivery if args.command == "confirm" else deliver
                operation(directory, state)
                print(encode(summary(directory, state)))
                return 0 if state["delivery"].get("observation", {}).get("status") == "observed" else 1
            if state["status"] == "submitted":
                print(encode(summary(directory, state)))
                return 0
            runtime = find_python(args.python)
            state.update(status="pending", response={})
        save_state(directory, state)
        command = [runtime["python"], str(Path(__file__).with_name("dialog_runtime.py")), str(directory)]
        with (directory / "renderer.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen(command, env=python_environment(runtime["python"]),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
        # Wait for readiness, not the user's answer. Renderer owns the run lock
        # after startup; detached lifetime survives the originating tool call.
        import time
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = read_state(directory)
            if current["status"] != "pending" or process.poll() is not None:
                break
            time.sleep(0.05)
        current = read_state(directory)
        if current["status"] == "pending" and process.poll() is not None:
            from dialog_state import finish_state
            finish_state(directory, current, "error", None, error=f"Renderer exited during startup ({process.returncode}); see renderer.log")
        print(encode(summary(directory, current)))
        return 1 if current["status"] == "error" else 0


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Locate Python with GTK and libadwaita")
    doctor.add_argument("--python")
    doctor.add_argument("--delivery", action="store_true", help="Read-only check of the originating desktop connection")
    show = commands.add_parser("show", help="Open a composed JSON view")
    show.add_argument("request", help="JSON file or - for stdin")
    show.add_argument("--preview", action="store_true", help="Render without Codex delivery; save message.md")
    show.add_argument("--render-image", help="With --preview, export the rendered widget to PNG and close")
    show.add_argument("--run-dir", help="Workspace (default: .codex-skills/user-dialog/<unique-id> from the project working directory)")
    show.add_argument("--python")
    resume = commands.add_parser("resume", help="Reopen a saved draft or return its submitted result")
    resume.add_argument("run_dir")
    resume.add_argument("--python")
    status = commands.add_parser("status", help="Read state without opening a window")
    status.add_argument("run_dir")
    validation = commands.add_parser("validate", help="Compile a JSON request without opening it")
    validation.add_argument("request")
    commands.add_parser("elements", help="List composable basic element types")
    delivery = commands.add_parser("deliver", help="Retry a confirmed pre-send failure from its originating task")
    delivery.add_argument("run_dir")
    confirmation = commands.add_parser("confirm", help="Recheck a submitted response without resending")
    confirmation.add_argument("run_dir")
    update = commands.add_parser("update", help="Queue an update for an open dialog")
    update.add_argument("run_dir")
    update.add_argument("request", help="JSON file or - for stdin")
    update.add_argument("--revision", type=int)
    update.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    try:
        if args.command == "elements":
            print(encode({"elements": sorted(TYPES)}))
            return 0
        if args.command == "validate":
            spec = load_request(args.request)
            print(encode({"status": "valid", "title": spec["title"]}))
            return 0
        if args.command == "doctor":
            result = {"status": "available", **find_python(args.python)}
            if args.delivery:
                origin = capture_origin()
                result["origin"] = {key: origin[key] for key in ("thread_id", "host_id", "title")}
            print(encode(result))
            return 0
        if args.command == "status":
            directory = Path(args.run_dir).expanduser().resolve()
            print(encode(summary(directory, read_state(directory))))
            return 0
        return run_dialog(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(encode({"status": "error", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
