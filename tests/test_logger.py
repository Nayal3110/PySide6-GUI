"""Tests for unified TDAM logger."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tdam.core.database import SessionDB
from src.tdam.core.logger import TDAMLogger


@pytest.fixture
def db() -> SessionDB:
    """Return a SessionDB backed by an in-memory SQLite database."""
    _db = SessionDB(db_path=":memory:")
    yield _db
    _db.close()


class TestTDAMLogger:
    def test_log_writes_to_file(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.log("hello world")
        logger.close()
        log_file = tmp_path / "log" / "log.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "hello world" in content

    def test_log_creates_dir(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "new_log_dir"
        logger = TDAMLogger(log_dir)
        assert log_dir.is_dir()
        logger.close()

    def test_log_writes_to_db(self, db: SessionDB, tmp_path: Path) -> None:
        sid = db.create_session(place="Test", config_snapshot={})
        logger = TDAMLogger(tmp_path / "log", db=db)
        logger.session_id = sid
        logger.log("test msg", level="ERROR", error_type="VNA_SCPI_ERROR")

        errors = db.query_session_errors(sid)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "VNA_SCPI_ERROR"
        logger.close()

    def test_log_without_db(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.log("no db")  # should not raise
        logger.close()

    def test_log_without_session_id(self, db: SessionDB, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log", db=db)
        logger.log("no session")  # should not write to DB (no session_id)
        logger.close()

    def test_session_id_property(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        assert logger.session_id is None
        logger.session_id = "abc123"
        assert logger.session_id == "abc123"
        logger.close()

    def test_log_marker(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.log_marker("#START_MEASURE\tID\t20240101")
        logger.close()
        log_file = tmp_path / "log" / "log.log"
        content = log_file.read_text()
        assert "#START_MEASURE" in content

    def test_close_idempotent(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.close()
        logger.close()  # should not raise

    def test_pipe_delimited_format(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.log("plain msg")
        logger.log("warn msg", level="WARNING")
        logger.log("err msg", level="ERROR", error_type="VNA_SCPI_ERROR")
        logger.close()
        content = (tmp_path / "log" / "log.log").read_text()
        # Three pipe-delimited lines: ts | level | message
        assert " | INFO    | plain msg" in content
        assert " | WARNING | warn msg" in content
        assert " | ERROR   | [VNA_SCPI_ERROR] err msg" in content

    def test_session_banners(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.session_start("2026-04-21 14:32:00.123", "Airolo")
        logger.log("inside session")
        logger.session_end("#STOP_MEASURE")
        logger.close()
        content = (tmp_path / "log" / "log.log").read_text(encoding="utf-8")
        # Banner: "\u2500\u2500\u2500 SESSION Airolo \u2014 2026-04-21 14:32:00.123 +0x \u2500\u2500\u2500"
        assert "SESSION Airolo \u2014 2026-04-21 14:32:00.123 " in content
        assert "SESSION END \u2014 Reason: #STOP_MEASURE" in content
        assert "inside session" in content

    def test_warn_ui_emits_signal_and_logs(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        captured: list[str] = []
        logger.ui_warning_signal.connect(captured.append)
        logger.warn_ui("antenna config missing")
        logger.close()
        # File contains the warning line
        content = (tmp_path / "log" / "log.log").read_text(encoding="utf-8")
        assert " | WARNING | antenna config missing" in content
        # And the signal fired with the bare message
        assert captured == ["antenna config missing"]

    def test_warn_ui_with_separate_log_message(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        captured: list[str] = []
        logger.ui_warning_signal.connect(captured.append)
        logger.warn_ui(
            "VNA temperature unavailable.",
            log_message="VNA temperature unavailable: timeout after 3s",
        )
        logger.close()
        content = (tmp_path / "log" / "log.log").read_text(encoding="utf-8")
        # File log keeps the detailed message
        assert "VNA temperature unavailable: timeout after 3s" in content
        # UI signal gets the short one
        assert captured == ["VNA temperature unavailable."]

    def test_session_banner_without_db(self, tmp_path: Path) -> None:
        logger = TDAMLogger(tmp_path / "log")
        logger.session_start(None, "Lab")  # no DB \u2192 banner falls back to wall clock
        logger.session_end()
        logger.close()
        content = (tmp_path / "log" / "log.log").read_text(encoding="utf-8")
        assert "SESSION Lab \u2014 " in content
