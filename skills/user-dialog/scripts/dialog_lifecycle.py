"""Coordinate the popup's lifetime with its launcher, independently of delivery."""

import subprocess
import time

from dialog_state import finish_state, read_state, save_state


def renderer_stopped(directory, error):
    """Read the final saved record only after the renderer can no longer write."""
    state = read_state(directory)
    status = state["status"]
    if (status in {"dismissed", "deferred", "error"}
            or status == "submitted" and state.get("delivery", {}).get("status")
            in {"accepted", "unknown", "failed"}):
        return state
    if status == "submitted":
        delivery = state.setdefault("delivery", {})
        delivery.update(status="unknown" if delivery.get("status") == "sending" else "failed",
                        observation={"status": "unconfirmed", "error": error}, error=error)
        save_state(directory, state)
    else:
        finish_state(directory, state, "error", None, error=error)
    return state


def wait_for_renderer(directory, process):
    """Return after GUI readiness; the popup owns its independent lifetime."""
    startup_deadline = time.monotonic() + 15
    ready = False
    while True:
        state = read_state(directory)
        status = state["status"]
        ready = ready or state.get("renderer_ready", status == "open")
        if status in {"dismissed", "deferred", "error"}:
            return state
        if ready:
            return state
        if process.poll() is not None:
            # The renderer may have saved its final state between our read and
            # exit check. Never replace that final answer with a stale snapshot.
            error = f"Renderer exited before completing the dialog ({process.returncode}); see renderer.log"
            return renderer_stopped(directory, error)
        if not ready and time.monotonic() >= startup_deadline:
            if read_state(directory).get("renderer_ready"):
                continue
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            return renderer_stopped(directory, "Renderer did not become ready; saved answers retained; see renderer.log")
        time.sleep(0.05)
