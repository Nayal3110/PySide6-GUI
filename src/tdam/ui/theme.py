"""Theme definitions and QSS stylesheet generation for TDAM."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ThemeMode(Enum):
    DARK = auto()
    LIGHT = auto()


@dataclass(frozen=True)
class ThemeColors:
    # Backgrounds
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_input: str

    # Text
    text_primary: str
    text_secondary: str
    text_disabled: str

    # Accent
    accent: str
    accent_hover: str
    accent_pressed: str

    # Borders
    border: str
    border_focus: str

    # Status
    status_connected: str
    status_disconnected: str

    # Log area
    log_bg: str
    log_text: str
    log_timestamp: str


DARK = ThemeColors(
    bg_primary="#0E0B16",
    bg_secondary="#16122A",
    bg_tertiary="#1E1838",
    bg_input="#252042",
    text_primary="#E4E0F0",
    text_secondary="#9B93B8",
    text_disabled="#524B6E",
    accent="#9B6DFF",
    accent_hover="#B08AFF",
    accent_pressed="#7C4FE0",
    border="#2E2650",
    border_focus="#9B6DFF",
    status_connected="#48BB78",
    status_disconnected="#6B6385",
    log_bg="#0B0918",
    log_text="#A89DC8",
    log_timestamp="#9B6DFF",
)

LIGHT = ThemeColors(
    bg_primary="#F5F3FA",
    bg_secondary="#FFFFFF",
    bg_tertiary="#EDE8F7",
    bg_input="#FFFFFF",
    text_primary="#1E1535",
    text_secondary="#6B5E8A",
    text_disabled="#A89DC0",
    accent="#7B4FCF",
    accent_hover="#8F63E0",
    accent_pressed="#6A3EBA",
    border="#D0C8E4",
    border_focus="#7B4FCF",
    status_connected="#2F855A",
    status_disconnected="#A89DC0",
    log_bg="#FFFFFF",
    log_text="#3B2D5C",
    log_timestamp="#7B4FCF",
)


def get_colors(mode: ThemeMode) -> ThemeColors:
    return DARK if mode is ThemeMode.DARK else LIGHT


def build_stylesheet(c: ThemeColors) -> str:
    return f"""
    /* ── Global ────────────────────────────────────────── */
    * {{
        font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
        font-size: 13px;
        outline: none;
    }}

    QMainWindow {{
        background-color: {c.bg_primary};
    }}

    /* ── Title bar area ────────────────────────────────── */
    #titleBar {{
        background-color: {c.bg_secondary};
        border-bottom: 1px solid {c.border};
        padding: 0px;
    }}
    #titleLabel {{
        color: {c.accent};
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    #subtitleLabel {{
        color: {c.text_secondary};
        font-size: 11px;
        font-weight: 400;
    }}

    /* ── Tab-like header ───────────────────────────────── */
    #instrumentsHeader {{
        background-color: {c.bg_tertiary};
        border: 1px solid {c.border};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    #instrumentsHeaderLabel {{
        color: {c.text_primary};
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* ── Panels / Cards ────────────────────────────────── */
    #controlPanel {{
        background-color: {c.bg_secondary};
        border: 1px solid {c.border};
        border-radius: 8px;
    }}
    #logPanel {{
        background-color: {c.log_bg};
        border: 1px solid {c.border};
        border-radius: 8px;
    }}

    /* ── Labels ────────────────────────────────────────── */
    QLabel {{
        color: {c.text_primary};
        background: transparent;
        border: none;
    }}
    QLabel[role="field-label"] {{
        color: {c.text_secondary};
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel[role="field-value"] {{
        color: {c.text_secondary};
        font-size: 13px;
        font-weight: 500;
    }}
    QLabel[role="section-title"] {{
        color: {c.accent};
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* ── Line Edits ────────────────────────────────────── */
    QLineEdit {{
        background-color: {c.bg_input};
        color: {c.text_primary};
        border: 1px solid {c.border};
        border-radius: 5px;
        padding: 5px 10px;
        selection-background-color: {c.accent};
        selection-color: #FFFFFF;
    }}
    QLineEdit:focus {{
        border: 1px solid {c.border_focus};
    }}
    QLineEdit:read-only {{
        background-color: {c.bg_tertiary};
        color: {c.text_secondary};
    }}
    QLineEdit:disabled {{
        color: {c.text_disabled};
        background-color: {c.bg_tertiary};
    }}

    /* ── Spin Boxes ────────────────────────────────────── */
    QSpinBox, QDoubleSpinBox {{
        background-color: {c.bg_input};
        color: {c.text_primary};
        border: 1px solid {c.border};
        border-radius: 5px;
        padding: 5px 8px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c.border_focus};
    }}
    QSpinBox:read-only, QDoubleSpinBox:read-only {{
        background-color: {c.bg_tertiary};
        color: {c.text_secondary};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 0px;
        border: none;
    }}

    /* ── Push Buttons ──────────────────────────────────── */
    QPushButton {{
        background-color: {c.bg_tertiary};
        color: {c.text_primary};
        border: 1px solid {c.border};
        border-radius: 5px;
        padding: 2px 18px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {c.accent_hover};
        color: #FFFFFF;
        border-color: {c.accent_hover};
    }}
    QPushButton:pressed {{
        background-color: {c.accent_pressed};
        color: #FFFFFF;
        border-color: {c.accent_pressed};
    }}
    QPushButton:disabled {{
        background-color: {c.bg_tertiary};
        color: {c.text_disabled};
        border-color: {c.border};
    }}

    /* Primary accent button */
    QPushButton[role="primary"] {{
        background-color: {c.accent};
        color: #FFFFFF;
        border: 1px solid {c.accent};
        font-weight: 600;
    }}
    QPushButton[role="primary"]:hover {{
        background-color: {c.accent_hover};
        border-color: {c.accent_hover};
    }}
    QPushButton[role="primary"]:pressed {{
        background-color: {c.accent_pressed};
        border-color: {c.accent_pressed};
    }}
    QPushButton[role="primary"]:disabled {{
        background-color: {c.bg_tertiary};
        color: {c.text_disabled};
        border-color: {c.border};
    }}

    /* Connect button */
    QPushButton#connectBtn {{
        border-radius: 5px;
        padding: 7px 24px;
        font-weight: 600;
    }}

    /* ── Mode toggle button (Normal / Auto) ──────────── */
    QPushButton#modeToggle {{
        background-color: {c.bg_tertiary};
        color: {c.text_secondary};
        border: 1px solid {c.border};
        border-radius: 15px;
        padding: 4px 16px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#modeToggle:hover {{
        background-color: {c.bg_input};
        color: {c.text_primary};
        border-color: {c.accent};
    }}
    QPushButton#modeToggle:checked {{
        background-color: {c.accent};
        color: #FFFFFF;
        border-color: {c.accent};
    }}
    QPushButton#modeToggle:checked:hover {{
        background-color: {c.accent_hover};
        border-color: {c.accent_hover};
    }}

    /* ── Text Edit (log area) ──────────────────────────── */
    QTextEdit, QPlainTextEdit {{
        background-color: {c.log_bg};
        color: {c.log_text};
        border: none;
        border-radius: 6px;
        padding: 8px;
        font-family: "Cascadia Code", "Consolas", "Fira Code", monospace;
        font-size: 12px;
    }}

    /* ── Scrollbars ────────────────────────────────────── */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c.border};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c.text_disabled};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background-color: transparent;
        height: 8px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {c.border};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {c.text_disabled};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ── Status bar ────────────────────────────────────── */
    #statusBar {{
        background-color: {c.bg_secondary};
        border-top: 1px solid {c.border};
    }}
    #statusLabel {{
        color: {c.text_secondary};
        font-size: 11px;
    }}

    /* ── Separator lines ───────────────────────────────── */
    #separator {{
        background-color: {c.border};
    }}

    /* ── Theme toggle button ───────────────────────────── */
    QPushButton#themeBtn {{
        background: transparent;
        border: none;
        padding: 4px;
        border-radius: 4px;
        font-size: 16px;
        color: {c.text_secondary};
    }}
    QPushButton#themeBtn:hover {{
        background-color: {c.bg_tertiary};
        color: {c.accent};
    }}

    /* ── Tooltips ───────────────────────────────────────── */
    QToolTip {{
        background-color: {c.bg_secondary};
        color: {c.text_primary};
        border: 1px solid {c.border};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    """
