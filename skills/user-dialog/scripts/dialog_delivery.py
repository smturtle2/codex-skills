"""Persist one ordinary user-message attempt and recover receipts without replay."""

from contextlib import contextmanager
from pathlib import Path
import threading
import uuid

from dialog_connection import backend_for, require_owner, validate_user_message
from dialog_state import read_state, save_state

UNCERTAIN = {"sending", "accepted", "unknown"}


@contextmanager
def submission_lock(directory, cancel):
    """Serialize attempts for this popup, including independent launcher processes."""
    import fcntl
    with (Path(directory) / ".delivery-lock").open("a+b") as stream:
        while True:
            if cancel.is_set():
                raise InterruptedError("Response delivery cancelled")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                cancel.wait(0.1)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def saved_delivery(directory, state, cancel):
    """Read and update submission state under the same per-popup lock."""
    with submission_lock(directory, cancel):
        state.update(read_state(directory))
        try:
            yield
        except Exception as error:
            delivery = state.setdefault("delivery", {})
            if delivery.get("status") in UNCERTAIN:
                delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
            else:
                delivery.update(status="failed", error=str(error))
            save_state(directory, state)

class DeliveryAttempt:
    """Persist shared state; native sequencing belongs to the selected backend."""

    def __init__(self, directory, state, cancel, origin_cancel=None):
        self.directory, self.state, self.cancel = directory, state, cancel
        self.origin_cancel = origin_cancel

    @property
    def origin(self):
        return self.state["origin"]

    @property
    def message(self):
        return self.state["message"]

    @property
    def delivery(self):
        return self.state["delivery"]

    @property
    def client_id(self):
        return self.delivery["client_message_id"]

    def save(self):
        save_state(self.directory, self.state)

    def sending(self):
        client_id = self.client_id
        self.state["delivery"] = {"status": "sending", "client_message_id": client_id}
        self.save()

    def accepted(self, receipt):
        self.delivery.update(status="accepted", receipt=receipt)
        self.save()

    def unknown(self, error):
        self.delivery.update(status="unknown", error=str(error))
        self.save()

    def rejected(self, error):
        self.delivery.update(status="failed", error=str(error))
        self.save()

    def waiting(self):
        self.delivery["observation"] = {"status": "waiting"}
        self.save()

    def observed(self, match):
        self.delivery.update(status="accepted", observation={"status": "observed", **match})
        self.delivery.pop("error", None)
        self.save()

    def unconfirmed(self, error):
        self.delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        self.save()


def confirm_delivery(directory, state, cancel=None):
    """Dispatch receipt recovery without allowing another input attempt."""
    cancel = cancel if cancel is not None else threading.Event()
    with saved_delivery(directory, state, cancel):
        if state.get("delivery", {}).get("status") not in UNCERTAIN:
            return
        require_owner(state["origin"])
        if (state["delivery"]["status"] == "accepted"
                and state["delivery"].get("observation", {}).get("status") == "observed"):
            return
        if not state["delivery"].get("client_message_id"):
            raise ValueError("Missing saved response identity; this send cannot be recovered")
        validate_user_message(state["message"], state["delivery"]["client_message_id"])
        backend_for(state["origin"]).confirm(DeliveryAttempt(directory, state, cancel))


def deliver(directory, state, cancel=None, *, origin_cancel=None):
    """Serialize one response identity, then dispatch its complete native workflow."""
    cancel = cancel if cancel is not None else threading.Event()
    with saved_delivery(directory, state, cancel):
        delivery = state.setdefault("delivery", {})
        if delivery.get("status") in UNCERTAIN or state.get("status") != "submitted":
            return
        require_owner(state["origin"])
        client_id = delivery.get("client_message_id") or str(uuid.uuid4())
        validate_user_message(state["message"], client_id)
        delivery["client_message_id"] = client_id
        save_state(directory, state)
        backend_for(state["origin"]).deliver(DeliveryAttempt(directory, state, cancel, origin_cancel))
