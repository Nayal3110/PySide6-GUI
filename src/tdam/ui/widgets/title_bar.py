"""Application title bar — title, theme toggle, mode toggle, start/stop button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class TitleBar(QWidget):
    """Top bar with theme toggle, Normal/Auto toggle and primary Start/Stop button."""

    theme_toggled = Signal()
    mode_toggled = Signal(bool)
    start_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        title = QLabel("TDAM")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        subtitle = QLabel("SUPSI-ISEA")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(subtitle)

        layout.addStretch()

        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("themeBtn")
        self._theme_btn.setFixedSize(32, 32)
        self._theme_btn.setToolTip("Toggle dark / light theme")
        self._theme_btn.clicked.connect(self.theme_toggled)
        layout.addWidget(self._theme_btn)

        self._mode_toggle = QPushButton("Normal")
        self._mode_toggle.setObjectName("modeToggle")
        self._mode_toggle.setCheckable(True)
        self._mode_toggle.setChecked(False)
        self._mode_toggle.setFixedSize(100, 30)
        self._mode_toggle.setToolTip("Toggle between Normal and Auto measure mode")
        self._mode_toggle.toggled.connect(self._on_mode_toggled)
        layout.addWidget(self._mode_toggle)

        layout.addSpacing(12)

        self._start_btn = QPushButton("Start")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.setFixedSize(100, 32)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self.start_clicked)
        layout.addWidget(self._start_btn)

    # ── Public API ──────────────────────────────────────────────────

    def set_theme_icon(self, text: str, tooltip: str) -> None:
        self._theme_btn.setText(text)
        self._theme_btn.setToolTip(tooltip)

    def set_start_text(self, text: str) -> None:
        self._start_btn.setText(text)

    def set_start_enabled(self, enabled: bool) -> None:
        self._start_btn.setEnabled(enabled)

    def set_mode_enabled(self, enabled: bool) -> None:
        self._mode_toggle.setEnabled(enabled)

    def is_mode_checked(self) -> bool:
        return self._mode_toggle.isChecked()

    # ── Internal ────────────────────────────────────────────────────

    def _on_mode_toggled(self, checked: bool) -> None:
        self._mode_toggle.setText("Auto" if checked else "Normal")
        self.mode_toggled.emit(checked)
