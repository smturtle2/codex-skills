"""Durable submission records and Desktop admission ownership across projects."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

from dialog_state import encode


def origin_identity(origin):
    return (origin["transport"], str(Path(origin["home"]).resolve()),
            origin.get("host_id", "local"), origin["thread_id"])


def admission_key(origin):
    # A chat opened from another project still has the same admission owner.
    return hashlib.sha256(encode(origin_identity(origin)[1:]).encode()).hexdigest()


def admitted(state):
    delivery = state.get("delivery", {})
    return delivery.get("observation", {}).get("status") == "observed"


class SubmissionJournal:
    """The journal is authoritative; state.json is the popup's readable mirror."""

    def __init__(self, origin):
        self.origin = origin
        self.key = admission_key(origin)
        directory = Path(origin["home"]) / "user-dialog"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = directory / "delivery.sqlite3"
        with self.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS submissions (
                response_id TEXT PRIMARY KEY, origin_key TEXT NOT NULL,
                run_dir TEXT NOT NULL, snapshot TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS outstanding (
                origin_key TEXT PRIMARY KEY, response_id TEXT NOT NULL
                REFERENCES submissions(response_id))""")
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _record(connection, response_id):
        row = connection.execute("SELECT run_dir, snapshot FROM submissions WHERE response_id=?",
                                 (response_id,)).fetchone()
        return (Path(row[0]), json.loads(row[1])) if row else None

    def load(self, response_id):
        with self.transaction() as connection:
            record = self._record(connection, response_id)
        if record and origin_identity(record[1]["origin"]) != origin_identity(self.origin):
            raise ValueError("Submission journal belongs to a different Codex task")
        return record

    def _save(self, connection, directory, state):
        if origin_identity(state["origin"]) != origin_identity(self.origin):
            raise ValueError("Submission destination changed")
        response_id = state["delivery"]["response_id"]
        previous = self._record(connection, response_id)
        if previous:
            old_directory, old = previous
            if (old_directory != Path(directory).resolve()
                    or origin_identity(old["origin"]) != origin_identity(state["origin"])
                    or old["request_id"] != state["request_id"] or old["message"] != state["message"]):
                raise ValueError("A saved submission cannot change its popup, destination or content")
            if admitted(old):
                state["delivery"] = old["delivery"]
        connection.execute("""INSERT INTO submissions VALUES (?, ?, ?, ?)
            ON CONFLICT(response_id) DO UPDATE SET snapshot=excluded.snapshot""",
                           (response_id, self.key, str(Path(directory).resolve()), encode(state)))

    def save(self, directory, state):
        with self.transaction() as connection:
            self._save(connection, directory, state)
            if admitted(state) or state["delivery"].get("status") == "failed":
                connection.execute("DELETE FROM outstanding WHERE origin_key=? AND response_id=?",
                                   (self.key, state["delivery"]["response_id"]))

    def claim(self, directory, state):
        """Atomically save the entire submission and acquire its admission slot."""
        response_id = state["delivery"]["response_id"]
        with self.transaction() as connection:
            row = connection.execute("SELECT response_id FROM outstanding WHERE origin_key=?",
                                     (self.key,)).fetchone()
            if row and row[0] != response_id:
                previous = self._record(connection, row[0])
                if previous is None:
                    raise ValueError("The outstanding submission record is missing")
                return previous
            self._save(connection, directory, state)
            connection.execute("INSERT OR IGNORE INTO outstanding VALUES (?, ?)",
                               (self.key, response_id))
        return None
