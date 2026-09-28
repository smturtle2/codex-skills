"""Persist, submit and confirm user messages without replaying uncertain sends."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import threading
import uuid

from dialog_connection import AppServer, RpcError, require_owner
from dialog_observer import ResponseReader
from dialog_state import save_state

UNCERTAIN = {"sending", "accepted", "unknown"}


@contextmanager
def submission_lock(origin, cancel):
    import fcntl
    key = hashlib.sha256((origin["home"] + origin["thread_id"]).encode()).hexdigest()
    directory = Path(origin["home"]) / "user-dialog-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / key).open("a+b") as stream:
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


def observe_response(directory, state, reader):
    delivery = state["delivery"]
    delivery["observation"] = {"status": "waiting"}
    save_state(directory, state)
    try:
        match = reader.wait(delivery, state["message"]["text"])
        delivery.update(status="accepted", observation={"status": "observed", **match})
        delivery.pop("error", None)
    except Exception as error:
        delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
    save_state(directory, state)


def confirm_delivery(directory, state, cancel=None):
    """Confirm only, including a process interrupted after persisting 'sending'."""
    delivery = state.get("delivery", {})
    if delivery.get("status") not in UNCERTAIN:
        return
    try:
        if "boundary_item_id" not in delivery:
            raise ValueError("Missing saved pre-send history position")
        with AppServer(state["origin"], cancel) as server:
            observe_response(directory, state, ResponseReader(server))
    except Exception as error:
        delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        save_state(directory, state)


def deliver(directory, state, cancel=None):
    if state.get("delivery", {}).get("status") in UNCERTAIN or state.get("status") != "submitted":
        return
    cancel = cancel if cancel is not None else threading.Event()
    try:
        require_owner(state["origin"])
        with submission_lock(state["origin"], cancel), AppServer(state["origin"], cancel) as server:
            reader = ResponseReader(server)
            client_id = state["delivery"].get("client_message_id") or str(uuid.uuid4())
            boundary = reader.bookmark()
            for attempt in range(3):
                turn_id = server.active_turn()
                params = {"threadId": state["origin"]["thread_id"], "clientUserMessageId": client_id,
                          "input": [state["message"]]}
                method = "turn/steer" if turn_id else "turn/start"
                if turn_id:
                    params["expectedTurnId"] = turn_id
                server.check()
                state["delivery"] = {"status": "sending", "client_message_id": client_id,
                                     "boundary_item_id": boundary, "method": method}
                save_state(directory, state)
                try:
                    receipt = server.call(method, params)
                except RpcError as error:
                    if not error.rejected():
                        state["delivery"].update(status="unknown", error=str(error))
                        save_state(directory, state)
                        raise
                    state["delivery"].update(status="failed", error=str(error))
                    save_state(directory, state)
                    if method == "turn/steer" and error.turn_changed() and attempt < 2:
                        continue
                    return
                except Exception as error:
                    state["delivery"].update(status="unknown", error=str(error))
                    save_state(directory, state)
                    raise
                state["delivery"].update(status="accepted", receipt=receipt)
                save_state(directory, state)
                observe_response(directory, state, reader)
                return
    except Exception as error:
        delivery = state.setdefault("delivery", {})
        if delivery.get("status") in UNCERTAIN:
            delivery["observation"] = {"status": "unconfirmed", "error": str(error)}
        else:
            delivery.update(status="failed", error=str(error))
        save_state(directory, state)
