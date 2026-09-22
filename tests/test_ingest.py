"""Tests for the tdam_ingest script — log parsing and SQLite insertion."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import tdam_ingest  # noqa: E402

from src.tdam.core.database import SessionDB  # noqa: E402

SAMPLE_LOG = """
─── SESSION Airolo — 2026-04-21 14:32:00.123 +0200 ───
2026-04-21 14:32:01.123 | INFO    | VNA connected: TR1300 SN12345
2026-04-21 14:32:02.456 | WARNING | Low signal margin
2026-04-21 14:32:08.001 | ERROR   | [VNA_SCPI_ERROR] VNA query timeout
─── SESSION END — Reason: #STOP_MEASURE — 2026-04-21 14:35:12.456 +0200 ───

─── SESSION Lab — 2026-04-22 09:00:00.000 +0200 ───
2026-04-22 09:00:01.000 | INFO    | starting
─── SESSION END — Reason: #ERROR — 2026-04-22 09:01:00.000 +0200 ───
"""


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "log.log"
    p.write_text(SAMPLE_LOG, encoding="utf-8")
    return p


@pytest.fixture
def db() -> SessionDB:
    _db = SessionDB(db_path=":memory:")
    yield _db
    _db.close()


class TestParse:
    def test_parses_two_sessions(self, log_file: Path) -> None:
        sessions = tdam_ingest.parse_log_file(log_file)
        assert len(sessions) == 2

    def test_first_session_fields(self, log_file: Path) -> None:
        s = tdam_ingest.parse_log_file(log_file)[0]
        assert s.place == "Airolo"
        assert s.started_at == "2026-04-21 14:32:00.123"
        assert s.ended_at == "2026-04-21 14:35:12.456"
        assert s.closing_msg == "#STOP_MEASURE"
        assert len(s.entries) == 3

    def test_error_entry_keeps_error_type(self, log_file: Path) -> None:
        s = tdam_ingest.parse_log_file(log_file)[0]
        err = s.entries[2]
        assert err["level"] == "ERROR"
        assert err["error_type"] == "VNA_SCPI_ERROR"
        assert err["message"] == "VNA query timeout"

    def test_second_session_fields(self, log_file: Path) -> None:
        s = tdam_ingest.parse_log_file(log_file)[1]
        assert s.place == "Lab"
        assert s.started_at == "2026-04-22 09:00:00.000"
        assert s.closing_msg == "#ERROR"
        assert len(s.entries) == 1

    def test_short_offset_banner_parsed(self, tmp_path: Path) -> None:
        """The live logger writes a 3-char offset (``+02``); the parser must
        accept it as well as the 4-digit form."""
        short = (
            "─── SESSION Lab — 2026-04-21 10:00:00.000 +02 ───\n"
            "2026-04-21 10:00:01.000 | INFO    | started\n"
            "─── SESSION END — Reason: #STOP_MEASURE — 2026-04-21 10:01:00.000 +02 ───\n"
        )
        p = tmp_path / "log.log"
        p.write_text(short, encoding="utf-8")
        sessions = tdam_ingest.parse_log_file(p)
        assert len(sessions) == 1
        assert sessions[0].place == "Lab"
        assert sessions[0].started_at == "2026-04-21 10:00:00.000"
        assert sessions[0].closing_msg == "#STOP_MEASURE"

    def test_suffixed_session_id_parsed(self, tmp_path: Path) -> None:
        """A session id carrying a ``~N`` disambiguation suffix still parses."""
        log = "─── SESSION Lab — 2026-04-21 10:00:00.000~1 +02 ───\n"
        p = tmp_path / "log.log"
        p.write_text(log, encoding="utf-8")
        sessions = tdam_ingest.parse_log_file(p)
        assert len(sessions) == 1
        assert sessions[0].started_at == "2026-04-21 10:00:00.000~1"

    def test_unclosed_session_flushed(self, tmp_path: Path) -> None:
        unclosed = (
            "─── SESSION Lab — 2026-04-21 10:00:00.000 +0200 ───\n"
            "2026-04-21 10:00:01.000 | INFO    | started\n"
        )
        p = tmp_path / "log.log"
        p.write_text(unclosed, encoding="utf-8")
        sessions = tdam_ingest.parse_log_file(p)
        assert len(sessions) == 1
        assert sessions[0].ended_at is None
        assert sessions[0].closing_msg is None


class TestIngest:
    def test_inserts_session_and_entries(self, log_file: Path, db: SessionDB) -> None:
        sessions = tdam_ingest.parse_log_file(log_file)
        inserted, skipped = tdam_ingest.ingest_sessions(db, sessions)
        assert inserted == 2
        assert skipped == 0

        all_sessions = db.query_sessions()
        assert len(all_sessions) == 2
        assert all(s["ingested"] is True for s in all_sessions)

    def test_idempotent(self, log_file: Path, db: SessionDB) -> None:
        sessions = tdam_ingest.parse_log_file(log_file)
        tdam_ingest.ingest_sessions(db, sessions)
        # Re-run on the same data
        inserted, skipped = tdam_ingest.ingest_sessions(db, sessions)
        assert inserted == 0
        assert skipped == 2
        assert len(db.query_sessions()) == 2

    def test_error_entries_queryable(self, log_file: Path, db: SessionDB) -> None:
        sessions = tdam_ingest.parse_log_file(log_file)
        tdam_ingest.ingest_sessions(db, sessions)
        airolo = next(s for s in db.query_sessions() if s["place"] == "Airolo")
        errors = db.query_session_errors(airolo["id"])
        assert len(errors) == 1
        assert errors[0]["error_type"] == "VNA_SCPI_ERROR"
