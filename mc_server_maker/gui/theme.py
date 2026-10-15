"""App look: dark and light themes."""

from PySide6 import QtSvg  # noqa: F401 - bundles the SVG plugin used for check marks
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from mc_server_maker.core import paths

DARK = {
    "bg": "#15171c", "surface": "#1d2027", "surface2": "#252932", "surface3": "#2e333d",
    "hover": "#383e4a", "border": "#343a46", "text": "#e8eaed", "muted": "#8e96a3",
    "disabled": "#5d6470", "accent": "#4cc764", "accent_hover": "#5fd877", "accent_text": "#0b1a10",
    "accent_soft": "#1f3b27", "danger": "#f0605a", "danger_soft": "#3a1f1f", "warn": "#e3b341",
    "info": "#58a6ff", "scroll": "#3b414d", "console_bg": "#0d0f12", "console_text": "#b9c0cb",
}
LIGHT = {
    "bg": "#f4f5f7", "surface": "#ffffff", "surface2": "#f0f2f5", "surface3": "#e6e9ee",
    "hover": "#dde1e7", "border": "#d6dae1", "text": "#1d2127", "muted": "#68707d",
    "disabled": "#a3a9b3", "accent": "#2e9e48", "accent_hover": "#27893e", "accent_text": "#ffffff",
    "accent_soft": "#e3f4e7", "danger": "#d1453b", "danger_soft": "#fbe9e7", "warn": "#a86b00",
    "info": "#1f6feb", "scroll": "#c3c8d0", "console_bg": "#0d0f12", "console_text": "#b9c0cb",
}
THEMES = {"dark": DARK, "light": LIGHT}

# Current palette; read by widgets that draw their own colors (console etc.)
C = dict(DARK)

MONO = '"Consolas", "D2Coding", "Menlo", "DejaVu Sans Mono", monospace'

QSS = """
* {{ outline: 0; }}
QWidget {{ color: {text}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {bg}; }}
QToolTip {{ background: {surface3}; color: {text}; border: 1px solid {border}; padding: 4px 6px; }}

#Sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
#AppTitle {{ font-size: 14pt; font-weight: 700; }}
#AppSubtitle {{ color: {muted}; font-size: 9pt; }}
#SectionLabel {{ color: {muted}; font-size: 8.5pt; font-weight: 700; }}
#ServerList {{ background: transparent; border: none; padding: 0; }}
#ServerList::item {{ border-radius: 8px; margin: 2px 0; padding: 0; }}
#ServerList::item:hover {{ background: {surface2}; }}
#ServerList::item:selected {{ background: {surface3}; }}
#ItemName {{ font-weight: 600; }}
#ItemSub {{ color: {muted}; font-size: 9pt; }}

#Header {{ background: {surface}; border-bottom: 1px solid {border}; }}
#ServerName {{ font-size: 16pt; font-weight: 700; }}
#Chip {{ background: {surface3}; border-radius: 10px; padding: 2px 10px; font-size: 9pt; }}
#Muted {{ color: {muted}; }}
#Hint {{ color: {muted}; font-size: 9pt; }}
#Warn {{ color: {warn}; font-weight: 600; }}
#Big {{ font-size: 14pt; font-weight: 700; }}

QGroupBox {{
    background: {surface}; border: 1px solid {border}; border-radius: 10px;
    margin-top: 26px; padding: 12px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 4px; top: 4px; padding: 0; color: {muted}; font-weight: 700;
}}

QPushButton {{
    background: {surface3}; border: 1px solid {border}; border-radius: 7px; padding: 7px 14px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {disabled}; background: {surface2}; border-color: {surface3}; }}
QPushButton[kind="primary"] {{ background: {accent}; border-color: {accent}; color: {accent_text}; font-weight: 700; }}
QPushButton[kind="primary"]:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton[kind="primary"]:disabled {{ background: {accent_soft}; border-color: {accent_soft}; color: {disabled}; }}
QPushButton[kind="danger"] {{ background: transparent; border-color: {danger}; color: {danger}; }}
QPushButton[kind="danger"]:hover {{ background: {danger_soft}; }}
QPushButton[kind="danger"]:disabled {{ color: {disabled}; border-color: {surface3}; }}
QPushButton[kind="ghost"] {{ background: transparent; border-color: transparent; color: {muted}; }}
QPushButton[kind="ghost"]:hover {{ background: {surface2}; color: {text}; }}
QPushButton[kind="card"] {{ text-align: left; padding: 10px 12px; border-radius: 9px; background: {surface2}; }}
QPushButton[kind="card"]:checked {{ border: 2px solid {accent}; background: {accent_soft}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {disabled}; background: {surface}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {surface2}; border: 1px solid {border}; selection-background-color: {surface3};
    selection-color: {text}; padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid {muted}; background: {bg};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QTableView::indicator {{ width: 16px; height: 16px; border: 1px solid {muted}; border-radius: 4px; background: {bg}; }}
QTableView::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({check}); }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({check}); }}
QRadioButton::indicator:checked {{
    border-color: {accent};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {accent_text}, stop:0.35 {accent_text}, stop:0.45 {accent}, stop:1 {accent});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {surface2}; border-color: {surface3}; }}

QTabWidget::pane {{ border: none; background: {bg}; }}
QTabWidget::tab-bar {{ left: 8px; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 9px 16px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}

QListWidget, QTableWidget {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; padding: 4px; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 4px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {surface3}; color: {text}; }}
QTableWidget {{ gridline-color: {border}; }}
QHeaderView::section {{ background: {surface2}; color: {muted}; border: none; padding: 5px 8px; font-weight: 600; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {surface2}; border: none; border-radius: 4px; height: 8px; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

#Console {{
    background: {console_bg}; color: {console_text}; border: 1px solid {border}; border-radius: 8px;
    padding: 6px; font-family: {mono}; font-size: 9.5pt;
}}
#ConsoleInput {{ font-family: {mono}; padding: 8px 10px; }}
"""


def app_icon() -> QIcon:
    return QIcon(str(paths.resource("icon.png")))


def apply(app: QApplication, mode: str = "dark") -> None:
    colors = THEMES.get(mode, DARK)
    C.clear()
    C.update(colors)
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans CJK KR", "sans-serif"])
    font.setPointSize(10)
    app.setFont(font)
    pal = QPalette()
    for role, key in (
        (QPalette.Window, "bg"),
        (QPalette.WindowText, "text"),
        (QPalette.Base, "bg"),
        (QPalette.AlternateBase, "surface"),
        (QPalette.Text, "text"),
        (QPalette.Button, "surface3"),
        (QPalette.ButtonText, "text"),
        (QPalette.Highlight, "accent"),
        (QPalette.HighlightedText, "accent_text"),
        (QPalette.ToolTipBase, "surface3"),
        (QPalette.ToolTipText, "text"),
        (QPalette.PlaceholderText, "disabled"),
        (QPalette.Link, "info"),
    ):
        pal.setColor(role, QColor(colors[key]))
    app.setPalette(pal)
    app.setStyleSheet(QSS.format(**colors, mono=MONO, check=paths.resource("check.svg").as_posix()))
    app.setWindowIcon(app_icon())


def set_kind(button, kind: str):
    """Button style: primary / danger / ghost / card."""
    button.setProperty("kind", kind)
    button.style().unpolish(button)
    button.style().polish(button)
    return button
