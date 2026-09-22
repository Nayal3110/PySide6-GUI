"""Splash screen"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QSplashScreen


def _get_version() -> str:
    try:
        return f"v{version('tdam')}"
    except PackageNotFoundError:
        return "v?"


_WIDTH = 420
_HEIGHT = 260


def show_splash(app: QApplication) -> QSplashScreen:
    """Create and show the splash screen, returning it for ``finish()``."""
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(_WIDTH, _HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Violet gradient background
    grad = QLinearGradient(0, 0, _WIDTH, _HEIGHT)
    grad.setColorAt(0.0, QColor("#1E1838"))
    grad.setColorAt(0.5, QColor("#2D2154"))
    grad.setColorAt(1.0, QColor("#0E0B16"))
    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, _WIDTH, _HEIGHT, 16, 16)

    # Title
    title_font = QFont("Segoe UI", 42, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.setPen(QColor("#9B6DFF"))
    painter.drawText(
        pixmap.rect().adjusted(0, -20, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter,
        "TDAM",
    )

    # Subtitle
    sub_font = QFont("Segoe UI", 14, QFont.Weight.Normal)
    painter.setFont(sub_font)
    painter.setPen(QColor("#B8A9D4"))
    painter.drawText(
        pixmap.rect().adjusted(0, 50, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter,
        "SUPSI-ISEA",
    )

    # Version
    ver_font = QFont("Segoe UI", 9)
    painter.setFont(ver_font)
    painter.setPen(QColor("#6B5B8D"))
    painter.drawText(
        pixmap.rect().adjusted(0, 0, -12, -10),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        _get_version(),
    )

    painter.end()

    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()

    return splash
