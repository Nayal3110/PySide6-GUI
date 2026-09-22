"""SQLite-backed session and log storage.

The database is a single file (``data/tdam.db`` by default) — no server, no
container. It records one row per measurement session plus one row per log
message, mirroring the structured file log so external tooling can query it.

A session's primary key **is** its start timestamp (``local_now()`` —
``YYYY-MM-DD HH:MM:SS.mmm``), so the id is self-describing wherever it appears
(file-log banner, ``log_entries.session_id``, query arguments). There is no
separate ``started_at`` column. On the vanishingly rare chance two sessions
share a millisecond, the colliding id gets a ``~N`` suffix.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

_DEFAULT_PATH = "data/tdam.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    ended_at        TEXT,
    place           TEXT NOT NULL,
    config_snapshot TEXT NOT NULL DEFAULT '{}',
    closing_msg     TEXT,
    ingested        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS log_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    timestamp   TEXT NOT NULL,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    error_type  TEXT
);

CREATE INDEX IF NOT EXISTS idx_log_session ON log_entries(session_id);
CREATE INDEX IF NOT EXISTS idx_log_level   ON log_entries(level);
CREATE INDEX IF NOT EXISTS idx_log_error   ON log_entries(error_type) WHERE error_type IS NOT NULL;
"""


def local_now() -> str:
    """OS-local timestamp string — also the shape of a session id.

    Format: ``YYYY-MM-DD HH:MM:SS.mmm`` in the host's local timezone.
    The session-header line in the file log carries the timezone offset, so
    individual entries do not repeat it.
    """
    now = datetime.now().astimezone()
    return f"{now.strftime('%Y-%m-%d %H:%M:%S.')}{now.microsecond // 1000:03d}"


def local_offset() -> str:
    """Current local UTC offset, e.g. ``+02``."""
    return datetime.now().astimezone().strftime("%z")


class SessionDB:
    """SQLite-backed database for session logging and error tracking.

    Parameters
    ----------
    db_path : str | Path | None
        Path to the SQLite file. Falls back to the ``TDAM_DB_PATH`` environment
        variable, then ``data/tdam.db``. Pass ``":memory:"`` for an ephemeral
        in-memory database (used by tests).
    _conn : sqlite3.Connection | None
        Pre-built connection — the test-injection seam. When given, ``db_path``
        is ignored. ``SessionDB`` takes ownership and closes it in ``close()``.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        _conn: sqlite3.Connection | None = None,
    ) -> None:
        if _conn is not None:
            self._conn: sqlite3.Connection | None = _conn
        else:
            resolved = str(db_path or os.environ.get("TDAM_DB_PATH") or _DEFAULT_PATH)
            if resolved != ":memory:":
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(resolved)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Live runtime API ────────────────────────────────────────────────

    def create_session(self, place: str, config_snapshot: dict) -> str:
        """Create a new (open) session row and return its id (= start timestamp)."""
        return self._insert_session(
            local_now(),
            ended_at=None,
            place=place,
            config_snapshot=json.dumps(config_snapshot),
            closing_msg=None,
            ingested=0,
        )

    def log_entry(
        self,
        session_id: str,
        message: str,
        level: str = "INFO",
        error_type: str | None = None,
    ) -> None:
        """Insert a log entry for the given session."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO log_entries (session_id, timestamp, level, message, "
                "error_type) VALUES (?, ?, ?, ?, ?)",
                (session_id, local_now(), level, message, error_type),
            )

    def close_session(
        self, session_id: str, closing_msg: str = "#STOP_MEASURE"
    ) -> None:
        """Mark a session as ended."""
        with self._conn:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ?, closing_msg = ? WHERE id = ?",
                (local_now(), closing_msg, session_id),
            )

    # ── Ingestion API (file-log → DB tooling) ───────────────────────────

    def session_exists(self, started_at: str) -> bool:
        """True if a session with this start timestamp (id) already exists."""
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE id = ? LIMIT 1", (started_at,)
        ).fetchone()
        return row is not None

    def import_session(
        self,
        place: str,
        started_at: str,
        ended_at: str | None,
        closing_msg: str | None,
        entries: list[dict],
    ) -> str:
        """Insert a session reconstructed from a file log, plus its entries.

        The id is ``started_at``. Marked ``ingested = 1``. ``config_snapshot``
        is empty because file logs do not carry it. Returns the new id.
        """
        sid = self._insert_session(
            started_at,
            ended_at=ended_at,
            place=place,
            config_snapshot="{}",
            closing_msg=closing_msg,
            ingested=1,
        )
        if entries:
            with self._conn:
                self._conn.executemany(
                    "INSERT INTO log_entries (session_id, timestamp, level, "
                    "message, error_type) VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            sid,
                            e["timestamp"],
                            e["level"],
                            e["message"],
                            e.get("error_type"),
                        )
                        for e in entries
                    ],
                )
        return sid

    # ── Queries ─────────────────────────────────────────────────────────

    def query_sessions(self) -> list[dict]:
        """Return all sessions as a list of dicts, newest first (by id = start time)."""
        rows = self._conn.execute(
            "SELECT id, ended_at, place, config_snapshot, closing_msg, ingested "
            "FROM sessions ORDER BY id DESC"
        ).fetchall()
        return [self._session_row_to_dict(r) for r in rows]

    def query_session_errors(self, session_id: str) -> list[dict]:
        """Return all error log entries (``error_type`` set) for a session."""
        rows = self._conn.execute(
            "SELECT id, session_id, timestamp, level, message, error_type "
            "FROM log_entries WHERE session_id = ? AND error_type IS NOT NULL",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Internal ────────────────────────────────────────────────────────

    def _insert_session(
        self,
        base_id: str,
        *,
        ended_at: str | None,
        place: str,
        config_snapshot: str,
        closing_msg: str | None,
        ingested: int,
    ) -> str:
        """INSERT a session row, disambiguating the id with a ``~N`` suffix on
        the (essentially impossible) chance two sessions share a millisecond.
        Returns the id actually used.
        """
        for attempt in range(1000):
            sid = base_id if attempt == 0 else f"{base_id}~{attempt}"
            try:
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO sessions (id, ended_at, place, "
                        "config_snapshot, closing_msg, ingested) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (sid, ended_at, place, config_snapshot, closing_msg, ingested),
                    )
                return sid
            except sqlite3.IntegrityError as exc:
                if "UNIQUE" not in str(exc):
                    raise
                continue
        raise sqlite3.IntegrityError(
            f"could not allocate a unique session id for {base_id!r}"
        )

    @staticmethod
    def _session_row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["config_snapshot"] = json.loads(d["config_snapshot"] or "{}")
        d["ingested"] = bool(d["ingested"])
        return d

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the SQLite connection (idempotent)."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
