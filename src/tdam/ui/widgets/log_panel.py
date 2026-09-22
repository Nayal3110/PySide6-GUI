"""Scrollable read-only log."""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

_LEVEL_COLORS = {
    "WARNING": "#E5C07B",  # yellow
    "ERROR": "#E06C75",    # red
}


class LogPanel(QWidget):
    """Auto-scrolling log display."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlaceholderText("Waiting for events...")
        layout.addWidget(self._text, 1)

    def append(self, message: str, level: str = "INFO") -> None:
        """Append *message* and keep the view scrolled to the bottom.

        WARNING/ERROR lines are colored; everything else uses the default
        text color.
        """
        color = _LEVEL_COLORS.get(level)
        if color is None:
            self._text.appendPlainText(message)
        else:
            self._text.appendHtml(
                f'<span style="color:{color};">{escape(message)}</span>'
            )
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
