"""Bottom status bar showing the current measurement ID."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class StatusBar(QWidget):
    """Status strip with the active measurement ID display."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        label = QLabel("ID ACTUAL MEASURE")
        label.setObjectName("statusLabel")
        layout.addStretch()
        layout.addWidget(label)

        self._measure_id_edit = QLineEdit()
        self._measure_id_edit.setFixedWidth(220)
        self._measure_id_edit.setReadOnly(True)
        self._measure_id_edit.setPlaceholderText("—")
        layout.addWidget(self._measure_id_edit)

    def set_measure_id(self, measure_id: str) -> None:
        self._measure_id_edit.setText(measure_id)
