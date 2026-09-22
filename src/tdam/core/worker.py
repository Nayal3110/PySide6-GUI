"""QThread-based measurement worker — bridges backend and UI."""

from __future__ import annotations

import sqlite3
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .config import VNAConfig, load_meas_config, load_trvna_path, load_vna_config
from .database import SessionDB
from .logger import TDAMLogger
from .measurement import MeasurementSequence, save_tsv
from .process_launcher import TRVNAError, ensure_trvna_running, is_process_running
from .serial_device import SerialDevice, SerialError
from .state import AppState, ConnectionState
from .vna_client import VNAClient


class MeasurementWorker(QObject):
    """Runs on a dedicated QThread to keep the UI responsive.

    All hardware I/O (serial, TCP, file writes) happens here.
    Communication with the UI is exclusively through signals/slots.
    """

    # Signals → UI
    log_message = Signal(str, str)  # (line, level)
    connection_status = Signal(bool, bool)  # (serial_ok, vna_ok)
    measurement_complete = Signal(object)  # MeasurementResult
    sequence_finished = Signal()
    error_occurred = Signal(str)    # critical — aborts operation
    warning_occurred = Signal(str)  # non-critical — operation continues

    def __init__(
        self,
        state: AppState,
        config_dir: Path,
        data_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._ip_address: str = "127.0.0.1"

        self._serial: SerialDevice | None = None
        self._vna: VNAClient | None = None
        self._vna_config: VNAConfig | None = None
        self._db: SessionDB | None = None
        self._logger: TDAMLogger | None = None

    # ── Connection ──────────────────────────────────────────────────

    @Slot(str)
    def connect_instruments(self, ip_address: str = "") -> None:
        """Discovery and connection sequence (runs on worker thread).

        ``ip_address`` is taken fresh from the UI on each connect attempt
        so edits made between sessions are honoured.
        """
        if ip_address:
            self._ip_address = ip_address
        self._state.set_connection(ConnectionState.CONNECTING)
        serial_ok = False
        vna_ok = False

        try:
            # Ensure clean slate
            self._close_all()

            # Database — a local SQLite file in data/. Always on; on the rare
            # unwritable-path case we fall back to file-log-only.
            db_init_error: str | None = None
            try:
                self._db = SessionDB(db_path=self._data_dir / "tdam.db")
            except (OSError, sqlite3.Error) as exc:
                self._db = None
                db_init_error = f"SQLite init failed — DB logging disabled: {exc}"

            # Logger — on a read-only log dir the constructor can raise; falling
            # through to the generic VNA error would mis-classify the cause.
            log_dir = self._data_dir / "log"
            try:
                self._logger = TDAMLogger(log_dir, db=self._db)
            except OSError as exc:
                self._logger = None
                print(f"[TDAM] Logger init failed: {exc}", file=sys.stderr)
                raise RuntimeError(f"Could not initialise logger: {exc}") from exc
            self._logger.log_signal.connect(self.log_message)
            self._logger.ui_warning_signal.connect(self.warning_occurred)
            if not self._logger.file_ok:
                self._logger.log(
                    "Could not open log file — UI log only.", level="WARNING"
                )
            if db_init_error:
                self._logger.log(db_init_error, level="WARNING")

            # Load VNA config
            vna_cfg_path = self._config_dir / "vna_config.toml"
            self._vna_config = load_vna_config(vna_cfg_path)

            # 1) Launch TRVNA
            trvna_path = load_trvna_path(self._config_dir / "trvna_path.toml")
            already_running = is_process_running(trvna_path.name)
            try:
                ensure_trvna_running(trvna_path)
                if already_running:
                    self._logger.log(f"TRVNA already running: {trvna_path}")
                else:
                    self._logger.log(f"TRVNA started: {trvna_path}")
                    time.sleep(0.7)
            except Exception as exc:
                self._logger.log(
                    f"TRVNA not available: {exc}",
                    level="ERROR",
                    error_type="CONFIG_ERROR",
                )
                raise

            # 2) VNA TCP
            self._vna = VNAClient(self._ip_address)
            idn = self._vna.connect()
            self._vna.assert_ready(timeout_s=12)
            vna_ok = True

            self._logger.log("VNA ready and RF ON")
            self._logger.log(f"VNA connected: {idn}")

            try:
                temp = self._vna.get_temperature()
                self._logger.log(f"VNA Temp: {temp} °C")
            except Exception as exc:
                self._logger.log(
                    f"VNA temperature unavailable: {exc}", level="WARNING"
                )

            # Configure VNA
            self._vna.configure(self._vna_config)

            # 3) Serial
            try:
                self._serial = SerialDevice.discover()
                serial_ok = True
                self._logger.log("Serial connected")
            except SerialError as exc:
                self._logger.log(
                    f"Serial port not found: {exc}",
                    level="ERROR",
                    error_type="SERIAL_DISCOVERY_FAIL",
                )
                raise

            # 4) Load meas config
            meas_path = self._config_dir / "meas_config.toml"
            load_meas_config(meas_path)  # validate it loads
            self._logger.log("Measure configuration loaded")

            self._state.set_connection(ConnectionState.CONNECTED)
            self._logger.log("CONNECT ALL: READY")

        except Exception as exc:
            self._state.set_connection(ConnectionState.ERROR)
            msg = f"CONNECT ALL ERROR: {exc}"

            # Determine error type and a short user-facing label
            if isinstance(exc, SerialError):
                error_type = "SERIAL_DISCOVERY_FAIL"
                short = "Serial port not found."
            elif isinstance(exc, TRVNAError):
                error_type = "TRVNA_LAUNCH_FAIL"
                short = "Could not launch TRVNA."
            else:
                error_type = "VNA_CONNECT_FAIL"
                short = "Could not connect to the VNA."

            if self._logger:
                self._logger.log(msg, level="ERROR", error_type=error_type)
            self._rollback()
            self.error_occurred.emit(f"{short} See log for details.")

        self.connection_status.emit(serial_ok, vna_ok)

    @Slot()
    def disconnect_instruments(self) -> None:
        """Cleanly disconnect all instruments."""
        self._state.request_stop()
        if self._logger:
            self._logger.log("CONNECT ALL: disconnected")
        self._close_all()
        self._state.set_connection(ConnectionState.DISCONNECTED)
        self._state.disarm_auto()
        self.connection_status.emit(False, False)

    # ── Measurement ─────────────────────────────────────────────────

    @Slot(str, int, int)
    def start_measurement(self, place: str, mean_count: int, interval_s: int) -> None:
        """Run a measurement sequence (runs on worker thread).

        ``try_start_measurement`` is the atomic ticket; if another
        measurement already holds it (e.g. an auto-trigger raced a
        manual click), emit ``sequence_finished`` so the UI unlocks
        instead of staying stuck on "Stop".
        """
        if not self._state.try_start_measurement():
            self._logger.log("Start ignored — measurement already running", level="WARNING")
            self.sequence_finished.emit()
            return

        session_started = False
        closing_msg = "#STOP_MEASURE"

        try:
            session_started, closing_msg = self._run_one_session(
                place, mean_count, interval_s
            )
        except Exception as exc:
            closing_msg = "#ERROR"
            if self._logger:
                self._logger.log(
                    f"Measurement error: {exc}",
                    level="ERROR",
                    error_type="MEASUREMENT_ERROR",
                )
            self.error_occurred.emit("Measurement aborted. See log for details.")
        finally:
            # On app shutdown, skip session_end (file flush) and the
            # sequence_finished emit (UI is being torn down anyway).
            shutting_down = self._state.is_shutdown_requested()
            if not shutting_down and session_started and self._logger is not None:
                self._logger.session_end(closing_msg)
                self._logger.session_id = None
            self._state.finish_measurement()
            if not shutting_down:
                self.sequence_finished.emit()

    def _run_one_session(
        self, place: str, mean_count: int, interval_s: int
    ) -> tuple[bool, str]:
        """Execute one measurement session end-to-end.

        Returns ``(session_started, closing_msg)`` so the caller's ``finally``
        block can write the matching session-end banner.
        """
        if (
            self._vna is None
            or self._serial is None
            or self._logger is None
            or self._vna_config is None
        ):
            raise RuntimeError("Instruments not connected")

        # Reload meas config (user might have loaded a new one)
        commands = load_meas_config(self._config_dir / "meas_config.toml")

        # Override mean_count and interval from UI
        cfg = replace(
            self._vna_config, interval_s=interval_s, mean_count=mean_count
        )

        session_id = self._open_db_session(place, cfg)
        self._logger.session_start(session_id, place)

        seq = MeasurementSequence(
            serial=self._serial,
            vna=self._vna,
            commands=commands,
            config=cfg,
            state=self._state,
            logger=self._logger,
            place=place,
        )
        result = seq.run()

        if result.data_blocks:
            tsv_path = save_tsv(result, self._data_dir / "measures")
            self._logger.log(f"Measure saved: {tsv_path.name}")

        self._close_db_session(session_id, "#STOP_MEASURE")
        self.measurement_complete.emit(result)

        return True, "#STOP_MEASURE"

    def _open_db_session(self, place: str, cfg: VNAConfig) -> str | None:
        """Create a DB session if the database is available; return its id or None."""
        if self._db is None or self._logger is None:
            return None
        try:
            session_id = self._db.create_session(
                place=place, config_snapshot=asdict(cfg)
            )
        except Exception as exc:
            self._logger.log(f"DB create_session failed: {exc}", level="WARNING")
            return None
        self._logger.session_id = session_id
        return session_id

    def _close_db_session(
        self, session_id: str | None, closing_msg: str
    ) -> None:
        """Close a DB session best-effort; the file log is the source of truth."""
        if self._db is None or session_id is None or self._logger is None:
            return
        try:
            self._db.close_session(session_id, closing_msg)
        except Exception as exc:
            self._logger.log(f"DB close_session failed: {exc}", level="WARNING")

    @Slot()
    def request_stop(self) -> None:
        """Request the current measurement to stop."""
        self._state.request_stop()
        if self._logger:
            self._logger.log("STOP requested by user", error_type="USER_STOP")

    # ── Internal ────────────────────────────────────────────────────

    def _rollback(self) -> None:
        """Close all resources without resetting the connection state.

        The caller is responsible for setting the appropriate state
        (ERROR or DISCONNECTED) before or after calling this method.
        """
        self._close_all()

    def _close_all(self) -> None:
        if self._logger is not None:
            self._logger.close()
            self._logger = None
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        if self._vna is not None:
            self._vna.close()
            self._vna = None
        if self._db is not None:
            self._db.close()
            self._db = None

    @property
    def vna_config(self) -> VNAConfig | None:
        return self._vna_config
