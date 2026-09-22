"""Instruments header strip with a tinted USB icon slot."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class InstrumentsHeader(QWidget):
    """Header band with the section label and a USB indicator icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("instrumentsHeader")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        label = QLabel("Instruments")
        label.setObjectName("instrumentsHeaderLabel")
        layout.addWidget(label)

        self._usb_icon_label = QLabel()
        self._usb_icon_label.setFixedSize(24, 24)
        layout.addWidget(self._usb_icon_label)

        layout.addStretch()

    def set_usb_icon(self, icon: QIcon, size: int = 24) -> None:
        self._usb_icon_label.setPixmap(icon.pixmap(QSize(size, size)))
