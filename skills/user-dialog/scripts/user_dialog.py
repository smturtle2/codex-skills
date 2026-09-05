# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run a custom libadwaita view through uv and return its response as JSON."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid

from dialog_state import encode, finish_state, read_state, run_lock, save_state


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
    raise ValueError("No compatible GTK Python found. See references/runtime-setup.md; "
                     "select one with --python or USER_DIALOG_PYTHON. " + encode(failures))


def run_dialog(args):
    if args.command == "show":
        view = Path(args.view).expanduser().resolve()
        if not view.is_file():
            raise ValueError(f"View does not exist: {view}")
        directory = Path(args.run_dir or Path.cwd() / "dialog-runs" / uuid.uuid4().hex).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
    else:
        directory = Path(args.run_dir).expanduser().resolve()
    with run_lock(directory):
        # An earlier launcher's abrupt exit must not allow a second window
        # to take over a still-running renderer's state.
        with run_lock(directory, ".window-lock"):
            pass
        if args.command == "show":
            if (directory / "state.json").exists():
                raise ValueError("Run directory already contains a dialog; use resume or a new directory")
            runtime = find_python(args.python)
            state = {"version": 1, "request_id": uuid.uuid4().hex, "status": "pending",
                     "view": str(view), "title": args.title, "subtitle": args.subtitle,
                     "draft": {}, "response": None}
        else:
            state = read_state(directory)
            if state["status"] == "submitted":
                print(encode(state["response"]))
                return 0
            runtime = find_python(args.python)
            state.update(status="pending", response=None)
        save_state(directory, state)
        print(f"Dialog: {directory}", file=sys.stderr, flush=True)
        command = [runtime["python"], str(Path(__file__).with_name("dialog_runtime.py")), str(directory)]
        process = subprocess.Popen(command, env=python_environment(runtime["python"]),
                                   stdout=sys.stderr)
        try:
            process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        state = read_state(directory)
        if state.get("response") is None:
            finish_state(directory, state, "error", None,
                         error=f"Dialog process stopped without a response (exit {process.returncode}); draft retained")
        response = state["response"]
        print(encode(response), flush=True)
        return 1 if response["status"] == "error" else 0


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Locate Python with GTK and libadwaita")
    doctor.add_argument("--python")
    show = commands.add_parser("show", help="Open an agent-authored view")
    show.add_argument("view")
    show.add_argument("--title", required=True)
    show.add_argument("--subtitle", default="")
    show.add_argument("--run-dir")
    show.add_argument("--python")
    resume = commands.add_parser("resume", help="Reopen a saved draft or return its submitted result")
    resume.add_argument("run_dir")
    resume.add_argument("--python")
    status = commands.add_parser("status", help="Read state without opening a window")
    status.add_argument("run_dir")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(encode({"status": "available", **find_python(args.python)}))
            return 0
        if args.command == "status":
            print(encode(read_state(Path(args.run_dir).expanduser().resolve())))
            return 0
        return run_dialog(args)
    except (OSError, ValueError, KeyError) as error:
        print(encode({"status": "error", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
