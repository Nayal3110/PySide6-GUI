"""Left-hand control panel: connect, VNA params readout, acquisition inputs."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.config import VNAConfig

_CONFIG_TOOLTIP = "Set via vna_config.toml"


@dataclass(frozen=True)
class _ValueLabelSpec:
    attr: str
    label: str


# VNA parameter rows — keep declaration close to the formatter that fills them.
_VNA_LABEL_SPECS: tuple[_ValueLabelSpec, ...] = (
    _ValueLabelSpec("_power_lbl", "Power [dBm]"),
    _ValueLabelSpec("_npoints_lbl", "Number of points"),
    _ValueLabelSpec("_if_filter_lbl", "IF Filter [Hz]"),
    _ValueLabelSpec("_freq_start_lbl", "Frequency start [MHz]"),
    _ValueLabelSpec("_freq_stop_lbl", "Frequency stop [MHz]"),
    _ValueLabelSpec("_average_lbl", "Average"),
)


def _h_separator() -> QFrame:
    sep = QFrame()
    sep.setObjectName("separator")
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    return sep


class ControlPanel(QWidget):
    """Connection / VNA parameters / acquisition inputs."""

    connect_clicked = Signal()
    open_measurement_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("controlPanel")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(8)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("connectBtn")
        self._connect_btn.setProperty("role", "primary")
        self._connect_btn.setFixedHeight(36)
        self._connect_btn.clicked.connect(self.connect_clicked)
        layout.addWidget(self._connect_btn)

        layout.addSpacing(4)

        # ── Connection ──
        layout.addWidget(self._section_title("CONNECTION"))
        layout.addWidget(_h_separator())

        conn_grid = self._make_grid()
        self._location_edit = self._add_text_field(conn_grid, 0, "Place of measure", "Airolo")
        self._ip_edit = self._add_text_field(conn_grid, 1, "IP address", "127.0.0.1")
        layout.addLayout(conn_grid)

        # ── VNA parameters (read-only display) ──
        layout.addSpacing(4)
        layout.addWidget(self._section_title("VNA PARAMETERS"))
        layout.addWidget(_h_separator())

        vna_grid = self._make_grid()
        for row, spec in enumerate(_VNA_LABEL_SPECS):
            label = self._add_value_label(vna_grid, row, spec.label, "—", _CONFIG_TOOLTIP)
            setattr(self, spec.attr, label)
        layout.addLayout(vna_grid)

        # ── Acquisition ──
        layout.addSpacing(4)
        layout.addWidget(self._section_title("ACQUISITION"))
        layout.addWidget(_h_separator())

        acq_grid = self._make_grid()
        self._nr_meas_spin = self._add_spin_field(acq_grid, 0, "Measures for mean", 10, 1, 30)
        self._aq_interval_spin = self._add_spin_field(acq_grid, 1, "Acq. interval [s]", 180, 1, 86400)
        layout.addLayout(acq_grid)

        # ── Actions ──
        layout.addSpacing(4)
        layout.addWidget(_h_separator())

        self._open_meas_btn = QPushButton("Open measurement")
        self._open_meas_btn.setFixedHeight(36)
        self._open_meas_btn.clicked.connect(self.open_measurement_clicked)
        layout.addWidget(self._open_meas_btn)

        layout.addStretch()

    # ── Public API ──────────────────────────────────────────────────

    def place(self) -> str:
        return self._location_edit.text().strip() or "Unknown"

    def ip_address(self) -> str:
        return self._ip_edit.text()

    def mean_count(self) -> int:
        return self._nr_meas_spin.value()

    def interval_s(self) -> int:
        return self._aq_interval_spin.value()

    def set_vna_labels(self, cfg: VNAConfig) -> None:
        self._power_lbl.setText(str(int(cfg.power_dbm)))
        self._npoints_lbl.setText(str(cfg.npoints))
        self._if_filter_lbl.setText(str(int(cfg.ifbw_hz)))
        self._freq_start_lbl.setText(str(int(cfg.fstart_mhz)))
        self._freq_stop_lbl.setText(str(int(cfg.fstop_mhz)))
        self._average_lbl.setText(str(cfg.average))

    def apply_vna_config(self, cfg: VNAConfig) -> None:
        """Update labels and sync the editable spin boxes from a config."""
        self.set_vna_labels(cfg)
        self._nr_meas_spin.setValue(cfg.mean_count)
        self._aq_interval_spin.setValue(cfg.interval_s)

    def set_connect_text(self, text: str) -> None:
        self._connect_btn.setText(text)

    def set_connect_enabled(self, enabled: bool) -> None:
        self._connect_btn.setEnabled(enabled)

    def set_inputs_enabled(self, enabled: bool) -> None:
        """Enable/disable the user-editable acquisition inputs."""
        self._location_edit.setEnabled(enabled)
        self._nr_meas_spin.setEnabled(enabled)
        self._aq_interval_spin.setEnabled(enabled)

    # ── Internal builders ───────────────────────────────────────────

    @staticmethod
    def _make_grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        return grid

    @staticmethod
    def _section_title(text: str) -> QLabel:
        title = QLabel(text)
        title.setProperty("role", "section-title")
        return title

    @staticmethod
    def _add_text_field(
        grid: QGridLayout, row: int, label: str, default: str
    ) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setProperty("role", "field-label")
        lbl.setFixedHeight(30)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        edit = QLineEdit(default)
        edit.setFixedHeight(30)
        edit.setMinimumWidth(90)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(edit, row, 1)
        return edit

    @staticmethod
    def _add_value_label(
        grid: QGridLayout, row: int, label: str, default: str, tooltip: str
    ) -> QLabel:
        lbl = QLabel(label)
        lbl.setProperty("role", "field-label")
        lbl.setFixedHeight(30)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        val = QLabel(default)
        val.setProperty("role", "field-value")
        val.setFixedHeight(30)
        val.setMinimumWidth(70)
        val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if tooltip:
            val.setToolTip(tooltip)
            lbl.setToolTip(tooltip)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(val, row, 1)
        return val

    @staticmethod
    def _add_spin_field(
        grid: QGridLayout, row: int, label: str, default: int, min_val: int, max_val: int
    ) -> QSpinBox:
        lbl = QLabel(label)
        lbl.setProperty("role", "field-label")
        lbl.setFixedHeight(30)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setFixedHeight(30)
        spin.setMinimumWidth(70)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        grid.addWidget(lbl, row, 0)
        grid.addWidget(spin, row, 1)
        return spin
