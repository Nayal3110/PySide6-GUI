"""Unified logger for TDAM — writes to file, emits Qt signal, and logs to DB.

File format (``log.log``) — pipe-delimited. Times are in OS local timezone;
the session-header line carries the UTC offset for unambiguous interpretation.
The timestamp on the SESSION line is also the session's database id::

    ─── SESSION Airolo — 2026-04-21 16:32:00.123 +0200 ───
    2026-04-21 16:32:01.123 | INFO    | VNA connected: TR1300 SN12345
    2026-04-21 16:32:08.001 | ERROR   | [VNA_SCPI_ERROR] VNA query timeout
    ─── SESSION END — Reason: #STOP_MEASURE — 2026-04-21 16:35:12.456 +0200 ───
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .database import SessionDB
from .database import local_now as _local_now
from .database import local_offset as _local_offset

_LEVEL_WIDTH = 7  # widest level name is "WARNING"


class TDAMLogger(QObject):
    """Emits ``log_signal`` for the UI to consume, writes structured lines
    to a text file, and optionally inserts into the SQLite database.
    """

    log_signal = Signal(str, str)  # (line, level)
    ui_warning_signal = Signal(str)  # opt-in popup-worthy warnings

    def __init__(
        self,
        log_dir: Path,
        db: SessionDB | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / "log.log"
        self._db = db
        self._session_id: str | None = None

        # Keep file handle open for the lifetime of the logger
        try:
            self._file = open(self._log_path, "a", encoding="utf-8")
        except OSError:
            self._file = None

    @property
    def file_ok(self) -> bool:
        """True if the log file is writable."""
        return self._file is not None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        self._session_id = value

    def log(
        self,
        message: str,
        level: str = "INFO",
        error_type: str | None = None,
    ) -> None:
        """Log a message to all destinations.

        Parameters
        ----------
        message : str
            The log message.
        level : str
            One of INFO, WARNING, ERROR, DATA, MARKER.
        error_type : str | None
            If not None, marks this as an error entry with a specific type
            (e.g. ``SERIAL_TIMEOUT``, ``VNA_CONNECT_FAIL``).
        """
        is_marker = level == "MARKER"
        ts = _local_now()
        prefix = f"[{error_type}] " if error_type else ""

        if is_marker:
            file_line = message
            ui_line = message
        else:
            file_line = f"{ts} | {level:<{_LEVEL_WIDTH}} | {prefix}{message}"
            ui_line = f"{ts} - {prefix}{message}"

        # 1) File
        self._write_line(file_line)

        # 2) Qt signal for UI
        self.log_signal.emit(ui_line, level)

        # 3) Database — first failure prints once to stderr and disables the
        # sink so a broken DB doesn't silently lose entries forever.
        if self._db is not None and self._session_id is not None:
            try:
                self._db.log_entry(
                    self._session_id,
                    message,
                    level=level,
                    error_type=error_type,
                )
            except Exception as exc:
                self._write_line(
                    f"{_local_now()} | WARNING | "
                    f"DB logging disabled after error: {exc}"
                )
                self._db = None

    def log_marker(self, marker: str) -> None:
        """Write a raw marker line (e.g. ``#START_MEASURE``) to all sinks."""
        self.log(marker, level="MARKER")

    def warn_ui(self, ui_message: str, *, log_message: str | None = None) -> None:
        """Log at WARNING level *and* surface a popup to the UI.

        If *log_message* is given, the file/DB record uses it (e.g. with
        full exception detail) while the UI popup keeps the short text.
        """
        self.log(log_message or ui_message, level="WARNING")
        self.ui_warning_signal.emit(ui_message)

    def session_start(self, session_id: str | None, place: str) -> None:
        """Write a session-start banner to the file log.

        The banner's timestamp is the session's database id when there is one
        (so the log line and the DB row carry the exact same value); if the DB
        is unavailable it falls back to the wall clock.
        """
        ts = session_id or _local_now()
        self._write_line(f"\n─── SESSION {place} — {ts} {_local_offset()} ───")

    def session_end(self, closing_msg: str = "#STOP_MEASURE") -> None:
        """Write a session-end banner to the file log."""
        self._write_line(
            f"─── SESSION END — Reason: {closing_msg} — {_local_now()} {_local_offset()} ───\n"
        )

    def _write_line(self, line: str) -> None:
        if self._file is None:
            return
        try:
            self._file.write(line + "\n")
            self._file.flush()
        except OSError:
            pass

    def close(self) -> None:
        """Close the log file handle (call when the logger is no longer needed)."""
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
