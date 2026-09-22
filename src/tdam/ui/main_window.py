"""Composes widgets and wires the worker thread."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..core.config import ensure_default_configs, load_vna_config
from ..core.state import AppState, ConnectionState
from ..core.worker import MeasurementWorker
from .theme import ThemeMode, build_stylesheet, get_colors
from .widgets import ControlPanel, InstrumentsHeader, LogPanel, StatusBar, TitleBar

RESOURCES = Path(__file__).parent / "resources"


def _get_base_dir() -> Path:
    """Return the base directory for config and data files.

    Uses the frozen executable's directory when built with PyInstaller,
    otherwise falls back to the project root (two levels above this file).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent.parent


_BASE_DIR = _get_base_dir()
_CONFIG_DIR = _BASE_DIR / "config"
_DATA_DIR = _BASE_DIR / "data"
_MEASURES_DIR = _DATA_DIR / "measures"


def _tinted_usb_icon(color: str, size: int = 24) -> QIcon:
    """Render the USB SVG icon tinted to *color*."""
    svg_text = (RESOURCES / "usb_icon.svg").read_text()
    svg_text = svg_text.replace('fill="currentColor"', f'fill="{color}"')
    renderer = QSvgRenderer(svg_text.encode())
    image = QImage(QSize(size + 16, size), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return QIcon(QPixmap.fromImage(image))


def _is_safe_measure_path(path: Path, root: Path) -> bool:
    """True if *path* resolves inside *root* — guard against opening files
    outside the measures directory (e.g. shortcuts)."""
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


class TDAMMainWindow(QMainWindow):
    """Main application window — wires widgets to the worker thread."""

    # Cross-thread signals to worker
    _sig_connect = Signal(str)          # ip_address (late-bound)
    _sig_disconnect = Signal()
    _sig_start = Signal(str, int, int)  # place, mean_count, interval_s
    _sig_stop = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._theme_mode = ThemeMode.DARK
        self._state = AppState()

        ensure_default_configs(_CONFIG_DIR)

        self._build_ui()
        self._apply_theme()
        self._load_initial_vna_config()
        self._setup_worker()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle("TDAM – SUPSI-ISEA")
        self.setMinimumSize(900, 800)
        self.resize(900, 800)

        self._title_bar = TitleBar()
        self._title_bar.theme_toggled.connect(self._toggle_theme)
        self._title_bar.mode_toggled.connect(self._on_mode_toggled)
        self._title_bar.start_clicked.connect(self._on_start_stop)

        self._instruments_header = InstrumentsHeader()

        self._control_panel = ControlPanel()
        self._control_panel.connect_clicked.connect(self._on_connect)
        self._control_panel.open_measurement_clicked.connect(self._on_open_measurement)

        self._log_panel = LogPanel()
        self._status_bar = StatusBar()

        # Layout: title | (control + log) | status
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 8)
        body_layout.setSpacing(10)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(self._instruments_header)
        left_layout.addWidget(self._control_panel, 1)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(left_panel, 0)
        content_layout.addWidget(self._log_panel, 1)

        body_layout.addWidget(content, 1)
        body_layout.addWidget(self._status_bar)
        root_layout.addWidget(body, 1)

        # Initial log line
        now_dt = datetime.now().astimezone()
        now = f"{now_dt.strftime('%Y-%m-%d %H:%M:%S.')}{now_dt.microsecond // 1000:03d}"
        self._log_panel.append(f"{now} : TDAM Acquisition tool started")

    # ── VNA config display ───────────────────────────────────────────

    def _load_initial_vna_config(self) -> None:
        try:
            cfg = load_vna_config(_CONFIG_DIR / "vna_config.toml")
        except Exception as exc:
            print(f"[TDAM] Failed to load VNA config: {exc}", file=sys.stderr)
            return
        self._control_panel.apply_vna_config(cfg)

    # ── Worker thread setup ──────────────────────────────────────────

    def _setup_worker(self) -> None:
        self._thread = QThread()
        self._worker = MeasurementWorker(
            state=self._state,
            config_dir=_CONFIG_DIR,
            data_dir=_DATA_DIR,
        )
        self._worker.moveToThread(self._thread)

        # UI → worker
        self._sig_connect.connect(self._worker.connect_instruments)
        self._sig_disconnect.connect(self._worker.disconnect_instruments)
        self._sig_start.connect(self._worker.start_measurement)
        self._sig_stop.connect(self._worker.request_stop)

        # Worker → UI
        self._worker.log_message.connect(self._on_log)
        self._worker.connection_status.connect(self._on_connection_status)
        self._worker.measurement_complete.connect(self._on_measurement_complete)
        self._worker.sequence_finished.connect(self._on_sequence_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.warning_occurred.connect(self._on_warning)

        # Let Qt clean up the thread object once it has finished
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    # ── Theme ────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        colors = get_colors(self._theme_mode)
        QApplication.instance().setStyleSheet(build_stylesheet(colors))

        if self._theme_mode is ThemeMode.DARK:
            self._title_bar.set_theme_icon("☀", "Switch to light theme")
        else:
            self._title_bar.set_theme_icon("☾", "Switch to dark theme")

        self._instruments_header.set_usb_icon(_tinted_usb_icon(colors.text_primary, 24))

    def _toggle_theme(self) -> None:
        self._theme_mode = (
            ThemeMode.LIGHT if self._theme_mode is ThemeMode.DARK else ThemeMode.DARK
        )
        self._apply_theme()

    # ── Mode toggle (Normal / Auto) ──────────────────────────────────

    def _on_mode_toggled(self, checked: bool) -> None:
        if checked:
            self._state.arm_auto()
        else:
            self._state.disarm_auto()

    # ── Connect / Disconnect ─────────────────────────────────────────

    def _on_connect(self) -> None:
        if self._state.connection is ConnectionState.CONNECTED:
            self._control_panel.set_connect_enabled(False)
            self._control_panel.set_connect_text("Disconnecting...")
            self._sig_disconnect.emit()
        else:
            self._control_panel.set_connect_enabled(False)
            self._control_panel.set_connect_text("Connecting...")
            self._sig_connect.emit(self._control_panel.ip_address())

    @Slot(bool, bool)
    def _on_connection_status(self, serial_ok: bool, vna_ok: bool) -> None:
        connected = serial_ok and vna_ok
        self._control_panel.set_connect_enabled(True)

        if connected:
            self._control_panel.set_connect_text("Disconnect")
            self._title_bar.set_start_enabled(True)
            if self._worker.vna_config is not None:
                self._control_panel.set_vna_labels(self._worker.vna_config)
        else:
            self._control_panel.set_connect_text("Connect")
            self._title_bar.set_start_enabled(False)
            self._title_bar.set_start_text("Start")

    # ── Start / Stop ─────────────────────────────────────────────────

    def _on_start_stop(self) -> None:
        if self._state.is_busy:
            self._sig_stop.emit()
            self._title_bar.set_start_text("Stopping...")
            self._title_bar.set_start_enabled(False)
        else:
            self._lock_ui()
            self._sig_start.emit(
                self._control_panel.place(),
                self._control_panel.mean_count(),
                self._control_panel.interval_s(),
            )

    @Slot(object)
    def _on_measurement_complete(self, result: object) -> None:
        if hasattr(result, "measure_id"):
            self._status_bar.set_measure_id(result.measure_id)

    @Slot()
    def _on_sequence_finished(self) -> None:
        self._unlock_ui()

        if self._state.auto_armed and self._state.connection is ConnectionState.CONNECTED:
            interval_s = self._control_panel.interval_s()
            self._on_log(f"Auto mode: next measurement in {interval_s}s")
            QTimer.singleShot(interval_s * 1000, self._auto_trigger)

    def _auto_trigger(self) -> None:
        """Fire the next auto measurement.

        The worker's ``try_start_measurement`` is the atomic gate — if a
        race lost the slot, the worker emits ``sequence_finished`` and the
        UI unlocks again. No ``is_busy`` pre-check needed.
        """
        if not self._state.auto_armed:
            return
        if self._state.connection is not ConnectionState.CONNECTED:
            return
        self._lock_ui()
        self._sig_start.emit(
            self._control_panel.place(),
            self._control_panel.mean_count(),
            self._control_panel.interval_s(),
        )

    # ── UI lock / unlock ─────────────────────────────────────────────

    def _lock_ui(self) -> None:
        self._title_bar.set_start_text("Stop")
        self._control_panel.set_connect_enabled(False)
        self._control_panel.set_inputs_enabled(False)
        self._title_bar.set_mode_enabled(False)

    def _unlock_ui(self) -> None:
        self._title_bar.set_start_text("Start")
        self._title_bar.set_start_enabled(True)
        self._control_panel.set_connect_enabled(True)
        self._control_panel.set_inputs_enabled(True)
        self._title_bar.set_mode_enabled(True)

    # ── Log / error / warning ────────────────────────────────────────

    @Slot(str, str)
    def _on_log(self, message: str, level: str = "INFO") -> None:
        self._log_panel.append(message, level)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "TDAM — Error", message)

    @Slot(str)
    def _on_warning(self, message: str) -> None:
        QMessageBox.warning(self, "TDAM — Warning", message)

    # ── Open measurement file ────────────────────────────────────────

    def _on_open_measurement(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Measurement", str(_MEASURES_DIR), "TSV files (*.tsv)"
        )
        if not path_str:
            return
        path = Path(path_str)
        if not _is_safe_measure_path(path, _MEASURES_DIR):
            QMessageBox.warning(
                self,
                "TDAM — Open Measurement",
                "Refusing to open files outside the measures directory.",
            )
            return
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ── Close ────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cleanly shut down worker thread before closing the window."""
        # Hard shutdown flag — worker bails at next iteration boundary and
        # skips slow cleanup (session_end file flush, trailing log marker).
        self._state.request_shutdown()

        if self._state.connection is ConnectionState.CONNECTED:
            # Detach the connection-status slot so a late update can't reach
            # widgets being torn down. Already-disconnected is harmless here.
            try:
                self._worker.connection_status.disconnect(self._on_connection_status)
            except (RuntimeError, TypeError):
                pass
            self._sig_disconnect.emit()

        # Give the worker up to 3s to bail at its next cancellation point.
        # If it's still stuck (e.g. blocked in a VNA TCP read), exit anyway —
        # the OS reclaims sockets and file handles on process exit. We do NOT
        # call terminate(): killing a thread mid-SCPI write can leave the VNA
        # in an unrecoverable state.
        self._thread.quit()
        if not self._thread.wait(3000):
            print(
                "[TDAM] Worker did not finish in 3s; exiting anyway.",
                file=sys.stderr,
            )

        super().closeEvent(event)
