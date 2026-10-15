"""앱 전체 디자인 (다크 테마)."""

from PySide6 import QtSvg  # noqa: F401 - 체크 표시(SVG)를 그리는 플러그인이 EXE에 포함되도록
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from mc_server_maker.core import paths

BG = "#15171c"
SURFACE = "#1d2027"
SURFACE_2 = "#252932"
SURFACE_3 = "#2e333d"
BORDER = "#343a46"
TEXT = "#e8eaed"
MUTED = "#8e96a3"
ACCENT = "#4cc764"
ACCENT_HOVER = "#5fd877"
ACCENT_DARK = "#1f3b27"
DANGER = "#f0605a"
WARN = "#e3b341"
INFO = "#58a6ff"

QSS = f"""
* {{ outline: 0; }}
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}

/* 사이드바 */
#Sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#AppTitle {{ font-size: 15pt; font-weight: 700; }}
#AppSubtitle {{ color: {MUTED}; font-size: 9pt; }}
#SectionLabel {{ color: {MUTED}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; }}
#ServerList {{ background: transparent; border: none; }}
#ServerList::item {{ border-radius: 8px; margin: 2px 0; }}
#ServerList::item:hover {{ background: {SURFACE_2}; }}
#ServerList::item:selected {{ background: {SURFACE_3}; }}
#ItemName {{ font-weight: 600; }}
#ItemSub {{ color: {MUTED}; font-size: 9pt; }}

/* 헤더 */
#Header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
#ServerName {{ font-size: 17pt; font-weight: 700; }}
#Chip {{ background: {SURFACE_3}; color: {TEXT}; border-radius: 10px; padding: 2px 10px; font-size: 9pt; }}
#Muted {{ color: {MUTED}; }}
#Hint {{ color: {MUTED}; font-size: 9pt; }}
#Warn {{ color: {WARN}; font-weight: 600; }}
#Big {{ font-size: 15pt; font-weight: 700; }}
#Mono {{ font-family: "Consolas", "D2Coding", "Menlo", "DejaVu Sans Mono", monospace; }}

/* 카드 (QGroupBox) */
QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    margin-top: 26px; padding: 12px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 4px; top: 4px; padding: 0; color: {MUTED}; font-weight: 700;
}}

/* 버튼 */
QPushButton {{
    background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: 7px;
    padding: 7px 14px; color: {TEXT};
}}
QPushButton:hover {{ background: #383e4a; }}
QPushButton:pressed {{ background: #2a2f38; }}
QPushButton:disabled {{ color: #5d6470; background: {SURFACE_2}; border-color: {SURFACE_3}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; color: #0b1a10; font-weight: 700; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[kind="primary"]:disabled {{ background: #2c4a33; border-color: #2c4a33; color: #6f8a75; }}
QPushButton[kind="danger"] {{ background: transparent; border-color: #5a2d2d; color: {DANGER}; }}
QPushButton[kind="danger"]:hover {{ background: #3a1f1f; }}
QPushButton[kind="danger"]:disabled {{ color: #5d4646; border-color: {SURFACE_3}; }}
QPushButton[kind="ghost"] {{ background: transparent; border-color: transparent; color: {MUTED}; }}
QPushButton[kind="ghost"]:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton[kind="card"] {{
    text-align: left; padding: 10px 12px; border-radius: 9px; background: {SURFACE_2};
}}
QPushButton[kind="card"]:checked {{ border: 2px solid {ACCENT}; background: {ACCENT_DARK}; }}

/* 입력 */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: #0b1a10;
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: #5d6470; background: {SURFACE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_3};
    selection-color: {TEXT}; padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid #4a5160; background: {BG};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ image: url(CHECK_SVG); }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 #0b1a10, stop:0.35 #0b1a10, stop:0.45 {ACCENT}, stop:1 {ACCENT}); }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {SURFACE_2}; border-color: {SURFACE_3}; }}

/* 탭 */
QTabWidget::pane {{ border: none; background: {BG}; }}
QTabWidget::tab-bar {{ left: 8px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 9px 16px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* 목록 */
QListWidget {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}

/* 스크롤 */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3b414d; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4b5260; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3b414d; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {SURFACE_2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QSplitter::handle {{ background: {BORDER}; }}
QMessageBox {{ background: {SURFACE}; }}

/* 콘솔 */
#Console {{
    background: #0d0f12; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px;
    font-family: "Consolas", "D2Coding", "Menlo", "DejaVu Sans Mono", monospace; font-size: 9.5pt;
}}
#ConsoleInput {{ font-family: "Consolas", "D2Coding", "Menlo", "DejaVu Sans Mono", monospace; padding: 8px 10px; }}
"""


def app_icon() -> QIcon:
    return QIcon(str(paths.resource("icon.png")))


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans CJK KR", "sans-serif"])
    font.setPointSize(10)
    app.setFont(font)
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG),
        (QPalette.WindowText, TEXT),
        (QPalette.Base, BG),
        (QPalette.AlternateBase, SURFACE),
        (QPalette.Text, TEXT),
        (QPalette.Button, SURFACE_3),
        (QPalette.ButtonText, TEXT),
        (QPalette.Highlight, ACCENT),
        (QPalette.HighlightedText, "#0b1a10"),
        (QPalette.ToolTipBase, SURFACE_3),
        (QPalette.ToolTipText, TEXT),
        (QPalette.PlaceholderText, "#6b7280"),
        (QPalette.Link, INFO),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS.replace("CHECK_SVG", paths.resource("check.svg").as_posix()))
    app.setWindowIcon(app_icon())


def set_kind(button, kind: str):
    """버튼 스타일 지정: primary / danger / ghost / card."""
    button.setProperty("kind", kind)
    button.style().unpolish(button)
    button.style().polish(button)
    return button
