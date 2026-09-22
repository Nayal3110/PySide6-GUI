"""Tests for the SQLite session database."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from src.tdam.core.database import SessionDB, local_now, local_offset

# Format used by both live runtime and the file-log ingest path:
# "YYYY-MM-DD HH:MM:SS.mmm" (no T, no timezone — offset is on the session header).
# This is also the shape of a session id.
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")
_OFFSET_RE = re.compile(r"^[+-]\d{2}$")


@pytest.fixture
def db() -> SessionDB:
    """Return a SessionDB backed by an in-memory SQLite database."""
    _db = SessionDB(db_path=":memory:")
    yield _db
    _db.close()


class TestSessionDB:
    def test_create_session_id_is_start_timestamp(self, db: SessionDB) -> None:
        sid = db.create_session(place="Airolo", config_snapshot={})
        # Bare id (no collision) is exactly a "YYYY-MM-DD HH:MM:SS.mmm" string.
        assert _TS_RE.match(sid)

    def test_create_and_query_session(self, db: SessionDB) -> None:
        sid = db.create_session(place="Airolo", config_snapshot={"npoints": 1001})

        sessions = db.query_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid
        assert sessions[0]["place"] == "Airolo"
        assert sessions[0]["ended_at"] is None
        assert sessions[0]["ingested"] is False
        assert sessions[0]["config_snapshot"] == {"npoints": 1001}

    def test_close_session(self, db: SessionDB) -> None:
        sid = db.create_session(place="Locarno", config_snapshot={})
        db.close_session(sid, "#STOP_MEASURE")

        sessions = db.query_sessions()
        assert sessions[0]["ended_at"] is not None
        assert sessions[0]["closing_msg"] == "#STOP_MEASURE"

    def test_log_entry(self, db: SessionDB) -> None:
        sid = db.create_session(place="Bellinzona", config_snapshot={})
        db.log_entry(sid, "Test message", level="INFO")
        db.log_entry(sid, "VNA failed", level="ERROR", error_type="VNA_CONNECT_FAIL")

        errors = db.query_session_errors(sid)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "VNA_CONNECT_FAIL"
        assert errors[0]["message"] == "VNA failed"

    def test_multiple_sessions(self, db: SessionDB) -> None:
        s1 = db.create_session(place="A", config_snapshot={})
        s2 = db.create_session(place="B", config_snapshot={})
        assert s1 != s2  # distinct ids even if created in the same millisecond

        sessions = db.query_sessions()
        assert len(sessions) == 2
        assert sessions[0]["place"] == "B"  # newest (largest id) first

    def test_same_millisecond_collision_gets_suffix(self, db: SessionDB) -> None:
        """Two sessions importing the same start timestamp: the second gets a
        ``~1`` suffix instead of failing the PRIMARY KEY constraint."""
        ts = "2026-04-21 14:32:00.123"
        a = db.import_session(place="A", started_at=ts, ended_at=None,
                              closing_msg=None, entries=[])
        b = db.import_session(place="B", started_at=ts, ended_at=None,
                              closing_msg=None, entries=[])
        assert a == ts
        assert b == ts + "~1"
        assert len(db.query_sessions()) == 2

    def test_import_session(self, db: SessionDB) -> None:
        sid = db.import_session(
            place="Airolo",
            started_at="2026-04-21 14:32:00.123",
            ended_at="2026-04-21 14:35:12.456",
            closing_msg="#STOP_MEASURE",
            entries=[
                {"timestamp": "2026-04-21 14:32:01.123", "level": "INFO", "message": "ok"},
                {
                    "timestamp": "2026-04-21 14:32:08.001",
                    "level": "ERROR",
                    "message": "VNA query timeout",
                    "error_type": "VNA_SCPI_ERROR",
                },
            ],
        )
        assert sid == "2026-04-21 14:32:00.123"
        sess = db.query_sessions()[0]
        assert sess["id"] == sid
        assert sess["ingested"] is True
        assert sess["closing_msg"] == "#STOP_MEASURE"

        errors = db.query_session_errors(sid)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "VNA_SCPI_ERROR"

    def test_session_exists(self, db: SessionDB) -> None:
        assert db.session_exists("2026-04-21 14:32:00.123") is False
        db.import_session(
            place="Airolo",
            started_at="2026-04-21 14:32:00.123",
            ended_at=None,
            closing_msg=None,
            entries=[],
        )
        assert db.session_exists("2026-04-21 14:32:00.123") is True
        assert db.session_exists("2026-04-21 14:32:00.999") is False

    def test_close_idempotent(self, db: SessionDB) -> None:
        db.close()
        db.close()  # should not raise

    def test_conn_injection(self) -> None:
        conn = sqlite3.connect(":memory:")
        d = SessionDB(_conn=conn)
        sid = d.create_session(place="X", config_snapshot={})
        assert d.query_sessions()[0]["id"] == sid
        d.close()

    def test_persists_to_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "tdam.db"
        d1 = SessionDB(db_path=db_path)
        sid = d1.create_session(place="Airolo", config_snapshot={})
        d1.close()

        d2 = SessionDB(db_path=db_path)
        sessions = d2.query_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid
        d2.close()

    def test_timestamp_format_matches_file_log(self, db: SessionDB) -> None:
        """The session id and entry timestamps must match the ingest-script
        format so the same session pushed live and later ingested deduplicates.
        """
        sid = db.create_session(place="Airolo", config_snapshot={})
        db.log_entry(sid, "msg", level="ERROR", error_type="X")
        db.close_session(sid, "#STOP_MEASURE")

        sess = db.query_sessions()[0]
        assert _TS_RE.match(sess["id"])
        assert _TS_RE.match(sess["ended_at"])

        entry = db.query_session_errors(sid)[0]
        assert _TS_RE.match(entry["timestamp"])

    def test_local_now_format(self) -> None:
        assert _TS_RE.match(local_now())

    def test_local_offset_format(self) -> None:
        assert _OFFSET_RE.match(local_offset())
