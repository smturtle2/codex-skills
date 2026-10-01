"""Record immutable submissions and dispatch native admission and recovery."""

from contextlib import contextmanager
from pathlib import Path
import threading
import uuid

from dialog_connection import backend_for, require_owner, validate_user_message
from dialog_journal import SubmissionJournal, admitted, origin_identity
from dialog_state import read_state, save_state

UNCERTAIN = {"sending", "accepted", "unknown"}


@contextmanager
def submission_lock(directory, cancel, *, blocking=True):
    import fcntl
    with (Path(directory) / ".delivery-lock").open("a+b") as stream:
        while True:
            if cancel.is_set():
                raise InterruptedError("Response delivery cancelled")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not blocking:
                    yield False
                    return
                cancel.wait(0.1)
        try:
            yield True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def response_identity(state):
    delivery = state.setdefault("delivery", {})
    identity = delivery.get("response_id") or delivery.get("client_message_id")
    if not identity and delivery.get("status") in UNCERTAIN:
        raise ValueError("Missing saved response identity; uncertain input cannot be replayed")
    identity = identity or str(uuid.uuid4())
    validate_user_message(state["message"], identity)
    delivery.update(response_id=identity, client_message_id=identity)
    return identity


class DeliveryAttempt:
    """A native adapter updates one journal-backed submission through this API."""

    def __init__(self, directory, state, cancel, journal=None):
        self.directory, self.state, self.cancel = Path(directory), state, cancel
        self.journal = journal or SubmissionJournal(self.origin)

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
        return self.delivery["response_id"]

    def save(self):
        self.journal.save(self.directory, self.state)
        if self.directory.is_dir():
            save_state(self.directory, self.state)

    def prepare(self, kind, **receipt_state):
        if admitted(self.state):
            return
        self.delivery.update(status="pending", phase="prepared", kind=kind, **receipt_state)
        self.save()

    def sending(self):
        if admitted(self.state):
            return
        self.delivery.update(status="sending", phase="write_started")
        self.delivery.pop("error", None)
        self.save()

    def accepted(self, receipt):
        if admitted(self.state):
            return
        self.delivery.update(status="accepted", phase="awaiting_receipt", receipt=receipt)
        self.save()

    def unknown(self, error):
        if admitted(self.state):
            return
        self.delivery.update(status="unknown", phase="uncertain", error=str(error))
        self.save()

    def rejected(self, error):
        if admitted(self.state):
            return
        self.delivery.update(status="failed", phase="rejected", error=str(error))
        self.save()

    def waiting(self):
        if admitted(self.state):
            return
        self.delivery["observation"] = {"status": "waiting"}
        self.save()

    def observed(self, match):
        self.delivery.update(status="accepted", phase="admitted",
                             observation={"status": "observed", **match})
        self.delivery.pop("error", None)
        self.save()

    def unconfirmed(self, error):
        if admitted(self.state):
            return
        self.delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        self.save()


def restore_submission(directory, state, journal=None):
    """Restore delivery from its authority without changing the submitted answer."""
    identity = response_identity(state)
    journal = journal or SubmissionJournal(state["origin"])
    saved = journal.load(identity)
    if saved:
        old_directory, snapshot = saved
        if (old_directory != Path(directory).resolve() or snapshot["message"] != state["message"]
                or origin_identity(snapshot["origin"]) != origin_identity(state["origin"])
                or snapshot["request_id"] != state["request_id"]):
            raise ValueError("The submitted answer or popup identity changed")
        state["delivery"] = snapshot["delivery"]
        state["origin"] = snapshot["origin"]
        if Path(directory).is_dir():
            save_state(directory, state)
    return journal


@contextmanager
def saved_delivery(directory, state, cancel):
    with submission_lock(directory, cancel):
        state.update(read_state(directory))
        require_owner(state["origin"])
        journal = restore_submission(directory, state)
        attempt = DeliveryAttempt(directory, state, cancel, journal)
        try:
            yield attempt
        except Exception as error:
            if not admitted(state):
                if attempt.delivery.get("status") in UNCERTAIN:
                    attempt.unconfirmed(error)
                else:
                    attempt.rejected(error)


def _confirm(attempt):
    if not admitted(attempt.state):
        backend_for(attempt.origin).confirm(attempt)


def _recover_predecessor(attempt, directory, snapshot):
    """An abandoned origin slot is recovered without replaying native input."""
    if not directory.is_dir():
        predecessor = DeliveryAttempt(directory, snapshot, attempt.cancel, attempt.journal)
        if snapshot["delivery"].get("status") not in UNCERTAIN:
            predecessor.rejected("Sender stopped before native input was attempted")
        else:
            _confirm(predecessor)
        return
    with submission_lock(directory, attempt.cancel, blocking=False) as acquired:
        if not acquired:
            return
        saved = attempt.journal.load(snapshot["delivery"]["response_id"])
        if not saved:
            raise ValueError("Outstanding submission disappeared")
        predecessor = DeliveryAttempt(directory, saved[1], attempt.cancel, attempt.journal)
        if admitted(predecessor.state):
            predecessor.save()
        elif predecessor.delivery.get("status") in UNCERTAIN:
            _confirm(predecessor)
        else:
            predecessor.rejected("Sender stopped before native input was attempted")


def _claim_desktop(attempt):
    while True:
        if attempt.cancel.is_set():
            raise InterruptedError("Response delivery cancelled before native admission")
        previous = attempt.journal.claim(attempt.directory, attempt.state)
        if previous is None:
            return
        if attempt.delivery.get("phase") != "waiting_origin":
            attempt.delivery.update(status="pending", phase="waiting_origin")
            attempt.save()
        _recover_predecessor(attempt, *previous)
        attempt.cancel.wait(0.2)


def confirm_delivery(directory, state, cancel=None):
    """Reconcile a saved submission; never issue native input."""
    cancel = cancel if cancel is not None else threading.Event()
    with saved_delivery(directory, state, cancel) as attempt:
        if attempt.delivery.get("status") in UNCERTAIN and not admitted(state):
            _confirm(attempt)


def deliver(directory, state, cancel=None):
    """Serialize this popup and, on Desktop, its origin's admission window."""
    cancel = cancel if cancel is not None else threading.Event()
    with saved_delivery(directory, state, cancel) as attempt:
        if state.get("status") != "submitted" or admitted(state):
            return
        if attempt.delivery.get("status") in UNCERTAIN:
            return
        attempt.delivery.update(status="pending", phase="prepared")
        attempt.save()
        if attempt.origin["transport"] == "desktop-ipc":
            _claim_desktop(attempt)
        backend_for(attempt.origin).deliver(attempt)
