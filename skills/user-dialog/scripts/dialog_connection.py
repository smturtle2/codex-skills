"""Select one native backend and validate the originating conversation identity."""

import os
from pathlib import Path
import uuid


class RpcError(ValueError):
    """An RPC error is not proof that submitted input was rolled back."""

    def __init__(self, error):
        self.code = error.get("code")
        self.data = error.get("data")
        super().__init__(error.get("message", "Native input request failed"))


def validate_user_message(message, client_id):
    """Accept one saved ordinary text input and its correlation identity."""
    if (not isinstance(message, dict) or message.get("type") != "text"
            or not isinstance(message.get("text"), str) or not isinstance(client_id, str)):
        raise ValueError("User-message submission requires ordinary text and a saved UUID")
    try:
        uuid.UUID(client_id)
    except ValueError as error:
        raise ValueError("User-message submission requires a saved UUID") from error


def host_transport():
    return "desktop-ipc" if "CODEX_APP_TOOLS_PIPE_PATH" in os.environ else "app-server"


def codex_home():
    return str(Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve())


def require_owner(origin):
    """Check saved identity without discovering or contacting a native server."""
    thread_id = os.environ.get("CODEX_THREAD_ID")
    session_id = os.environ.get("CODEX_SESSION_ID")
    if not thread_id or thread_id != origin.get("thread_id") or session_id and session_id != thread_id:
        raise ValueError("This dialog belongs to a different Codex task")
    if origin.get("transport") != host_transport() or origin.get("home") != codex_home():
        raise ValueError("This dialog belongs to a different Codex connection")


def backend_for(origin=None):
    """Dispatch once; backend modules own their complete native workflow."""
    transport = origin["transport"] if origin is not None else host_transport()
    if transport == "desktop-ipc":
        import dialog_desktop
        return dialog_desktop
    if transport == "app-server":
        import dialog_cli
        return dialog_cli
    raise ValueError("Unsupported dialog transport")


def open_connection(origin, cancel=None):
    require_owner(origin)
    return backend_for(origin).connection(origin, cancel)


def capture_origin():
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    uuid.UUID(thread_id)
    origin = {"transport": host_transport(), "thread_id": thread_id, "home": codex_home()}
    try:
        return backend_for(origin).capture_origin(origin)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot reach the originating Codex task ({origin['transport']}): {error}") from error
