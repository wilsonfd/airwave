# -*- coding: utf-8 -*-
"""Visual language for AirWave (matches the app icon: deep navy + glass blue/violet)."""
from __future__ import annotations

from PySide6.QtGui import QColor

BG = "#050912"
BG2 = "#080E1A"
CARD = "#0B1423"
CARD_SOFT = "#091120"
CARD_HOVER = "#0F1B2E"
BORDER = "#172640"
BORDER_SOFT = "#132139"
TEXT = "#E9F0FB"
TEXT_SOFT = "#C3D1E6"
MUTED = "#7C8FAE"
DIM = "#4B5C78"
ACCENT = "#6AA9FF"
ACCENT_2 = "#8F7BFF"
VIOLET = "#B18CFF"
MINT = "#5FE3B6"
AMBER = "#F5BE6B"
RED = "#FF7D8C"


def qcolor(hex_or_name: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_or_name)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


QSS = f"""
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QWidget#Root {{ background: transparent; }}
QFrame#Card {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 18px;
}}
QFrame#SubCard {{
    background-color: {CARD_SOFT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}
QFrame#InfoBox {{
    background-color: #0C1A2B;
    border: 1px solid #173253;
    border-radius: 12px;
}}
QFrame#Divider {{
    background-color: {BORDER_SOFT};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLabel {{ background: transparent; }}
QLabel#AppTitle {{
    font-size: 24px;
    font-weight: 700;
    color: #FFFFFF;
}}
QLabel#Subtitle {{ color: {MUTED}; font-size: 11px; }}
QLabel#Section {{
    color: #DCE7F7;
    font-size: 12px;
    font-weight: 700;
}}
QLabel#SectionHint {{ color: {DIM}; font-size: 10px; }}
QLabel#FieldLabel {{ color: {MUTED}; font-size: 10px; font-weight: 600; }}
QLabel#Detail {{ color: {MUTED}; font-size: 10px; }}
QLabel#Hint {{ color: #8FA6C7; font-size: 10px; }}
QLabel#Version {{ color: #3F506B; font-size: 10px; }}
QLabel#Chip {{
    background-color: #101D30;
    border: 1px solid #1B2E4A;
    border-radius: 10px;
    padding: 3px 8px;
    color: #8FA6C7;
    font-size: 10px;
    font-weight: 600;
}}
QLabel#KindSystem {{
    background-color: #102A3A;
    border: 1px solid #1B4A5E;
    border-radius: 8px;
    padding: 2px 7px;
    color: #7FD8F0;
    font-size: 9px;
    font-weight: 700;
}}
QLabel#KindVirtual {{
    background-color: #1A203C;
    border: 1px solid #333A6A;
    border-radius: 8px;
    padding: 2px 7px;
    color: #B9A7FF;
    font-size: 9px;
    font-weight: 700;
}}
QLabel#KindInput {{
    background-color: #1E2433;
    border: 1px solid #303B52;
    border-radius: 8px;
    padding: 2px 7px;
    color: #9FB0CA;
    font-size: 9px;
    font-weight: 700;
}}
QLabel#MetricValue {{
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
}}
QLabel#MetricLabel {{ color: {MUTED}; font-size: 10px; }}
QLabel#MetricSub {{ color: {DIM}; font-size: 9px; }}
QComboBox, QLineEdit {{
    background-color: #101B2D;
    border: 1px solid #1C2D49;
    border-radius: 10px;
    padding: 7px 10px;
    min-height: 20px;
    color: {TEXT};
    selection-background-color: #2C5A96;
    selection-color: #FFFFFF;
}}
QComboBox:hover, QLineEdit:hover {{ border-color: #2B4266; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox:disabled, QLineEdit:disabled {{
    color: #53647E;
    background-color: #0C1524;
    border-color: #162238;
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #7D8FB0;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: #101B2D;
    border: 1px solid #243754;
    border-radius: 10px;
    padding: 6px;
    outline: 0;
    selection-background-color: #1E3A63;
    selection-color: #FFFFFF;
}}
QPushButton {{
    background-color: #111D30;
    border: 1px solid #1E304C;
    border-radius: 10px;
    padding: 7px 13px;
    color: #C9D6EA;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #162640; border-color: #2D4A73; }}
QPushButton:pressed {{ background-color: #0D1727; }}
QPushButton:disabled {{
    color: #53647E;
    background-color: #0C1524;
    border-color: #162238;
}}
QPushButton#GhostBtn {{
    background-color: transparent;
    border: 1px solid #1B2B44;
    color: #93A6C3;
    font-weight: 600;
}}
QPushButton#GhostBtn:hover {{ background-color: #111F33; border-color: #2D4A73; color: #DCE7F7; }}
QPushButton#ChipBtn {{
    background-color: #0E1929;
    border: 1px solid #1B2C46;
    border-radius: 14px;
    padding: 4px 12px;
    color: #9FB2CE;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}}
QPushButton#ChipBtn:hover {{ border-color: #33517C; color: #DCE7F7; }}
QPlainTextEdit {{
    background-color: #070E19;
    border: 1px solid #132138;
    border-radius: 12px;
    padding: 9px;
    color: #8FA3C0;
    selection-background-color: #23405F;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #22344F;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: #2E4768; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QToolTip {{
    background-color: #0E1A2C;
    color: #DCE7F7;
    border: 1px solid #2A3E5E;
    padding: 5px 8px;
    border-radius: 6px;
}}
"""
