"""App look: dark and light themes."""

import tempfile
from pathlib import Path

from PySide6 import QtSvg  # noqa: F401 - bundles the SVG plugin used for check marks
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFormLayout

from mc_server_maker.core import paths
from mc_server_maker.i18n import language

# Quiet, neutral greys; the logo blue (accent) only marks the main action, the selected
# tab/server and switched-on things. Green ("ok") means running / reachable, red stops things.
DARK = {
    "bg": "#121315", "surface": "#18191c", "surface2": "#1f2024", "surface3": "#28292e",
    "hover": "#2c2e33", "border": "#2a2c30", "text": "#e6e7e9", "muted": "#8e9198",
    "disabled": "#5d6068", "accent": "#3d7bff", "accent_hover": "#5a90ff", "accent_text": "#ffffff",
    # filled buttons are a shade darker than the logo blue / red so white text stays readable (4.5:1)
    "button": "#2e64d8", "button_hover": "#2858c4", "stop": "#d4373c", "stop_hover": "#bb2d32",
    "placeholder": "#8e9198",
    "accent_soft": "#1b2436", "danger": "#e5484d", "danger_hover": "#ef5f63", "danger_soft": "#3a1f22",
    "warn": "#d9a441", "ok": "#3ecf7a", "info": "#8fb4ff", "scroll": "#33353b",
    "console_bg": "#0d0e10", "console_text": "#b9bcc2",
}
LIGHT = {
    "bg": "#f6f6f7", "surface": "#ffffff", "surface2": "#efeff1", "surface3": "#e5e6e9",
    "hover": "#e1e2e5", "border": "#e2e3e6", "text": "#18191b", "muted": "#6a6e75",
    "disabled": "#a2a5ab", "accent": "#1f5be0", "accent_hover": "#184cc0", "accent_text": "#ffffff",
    "button": "#1f5be0", "button_hover": "#184cc0", "stop": "#d4373c", "stop_hover": "#bb2d32",
    "placeholder": "#6a6e75",
    "accent_soft": "#e6edfc", "danger": "#d4373c", "danger_hover": "#bb2d32", "danger_soft": "#fbe8e8",
    "warn": "#9a6a00", "ok": "#1f9d55", "info": "#1f5be0", "scroll": "#c9cbd0",
    "console_bg": "#0d0e10", "console_text": "#b9bcc2",
}
THEMES = {"dark": DARK, "light": LIGHT}

# Current palette; read by widgets that draw their own colors (console etc.)
C = dict(DARK)

MONO = '"Consolas", "D2Coding", "Menlo", "DejaVu Sans Mono", monospace'

QSS = """
* {{ outline: 0; }}
QWidget {{ color: {text}; font-size: 10.5pt; }}
QMainWindow, QDialog {{ background: {bg}; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 4px 6px; }}
QMenu {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {surface2}; }}
QMenu::item:disabled {{ color: {disabled}; }}

#Sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
#AppTitle {{ font-size: 12.5pt; font-weight: 600; }}
#AppSubtitle {{ color: {muted}; font-size: 9pt; }}
#SectionLabel {{ color: {muted}; font-size: 9pt; }}
#SideFoot {{ border-top: 1px solid {border}; }}
#ServerList {{ background: transparent; border: none; padding: 0; }}
#ServerList::item {{ border-radius: 6px; margin: 1px 0; padding: 0; border-left: 2px solid transparent; }}
#ServerList::item:hover {{ background: {surface2}; }}
#ServerList::item:selected {{ background: {surface2}; border-left: 2px solid {accent}; }}
#ItemName {{ font-weight: 500; }}
#ItemSub {{ color: {muted}; font-size: 9pt; }}

#MoreButton {{ background: transparent; border: none; color: {muted}; font-size: 13pt; padding: 0 4px; border-radius: 4px; }}
#MoreButton:hover {{ background: {hover}; color: {text}; }}
#Card {{ background: transparent; border: none; border-bottom: 1px solid {border}; border-radius: 0; }}
#Header {{ background: {bg}; }}
#ServerName {{ font-size: 14.5pt; font-weight: 600; }}
#Meta {{ color: {muted}; font-size: 9.5pt; }}
#Muted {{ color: {muted}; }}
#Hint {{ color: {muted}; font-size: 9.5pt; }}
#Help {{
    background: transparent; color: {muted}; border: 1px solid {border}; border-radius: 10px;
    min-width: 19px; max-width: 19px; min-height: 19px; max-height: 19px; padding: 0;
    font-size: 8pt; font-weight: 600;
}}
#Help:hover, #Help:checked {{ color: {text}; border-color: {muted}; }}
#HelpPopup {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; }}
#HelpPopup QLabel {{ background: transparent; }}
#Warn {{ color: {warn}; }}
#Big {{ font-size: 14pt; font-weight: 600; }}
#PageTitle {{ font-size: 13pt; font-weight: 600; }}
#Rule {{ background: {border}; border: none; min-height: 1px; max-height: 1px; }}
#Address {{ font-family: {mono}; font-size: 12pt; }}
#AddonList {{ background: transparent; border: none; border-top: 1px solid {border}; border-radius: 0; padding: 0; }}
#AddonList::item {{ padding: 0; border: none; }}
#Tiles {{ background: {border}; border: 1px solid {border}; border-radius: 6px; }}
#Tile {{ background: {bg}; }}

QGroupBox {{
    background: transparent; border: none; border-top: 1px solid {border}; border-radius: 0;
    margin-top: 10px; padding: 42px 0 4px 0;
}}
QGroupBox[first="true"] {{ border-top: none; margin-top: 0; padding-top: 30px; }}
QGroupBox::title {{
    subcontrol-origin: padding; subcontrol-position: top left;
    left: 0; top: 16px; padding: 0; font-weight: bold; font-size: 10.5pt;
}}
QGroupBox[first="true"]::title {{ top: 4px; }}
QGroupBox#Section {{ padding-top: 18px; }}
QGroupBox#Section[first="true"] {{ padding-top: 4px; }}
#SectionTitle {{ font-weight: bold; font-size: 10.5pt; }}
QGroupBox#Stat {{ border-top: none; margin-top: 0; padding: 22px 0 0 0; }}
QGroupBox#Stat::title {{ top: 0; color: {muted}; font-weight: 400; font-size: 9.5pt; }}

QPushButton {{
    background: {surface2}; border: 1px solid {border}; border-radius: 6px; padding: 6px 12px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {disabled}; background: {surface2}; border-color: {surface2}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton[kind="primary"]:focus, QPushButton[kind="stop"]:focus {{ border-color: {text}; }}
QPushButton[kind="ghost"]:focus, QPushButton[kind="link"]:focus {{ color: {text}; }}
QPushButton[kind="primary"] {{ background: {button}; border-color: {button}; color: {accent_text}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {button_hover}; border-color: {button_hover}; }}
QPushButton[kind="primary"]:disabled {{ background: {surface3}; border-color: {surface3}; color: {disabled}; }}
QPushButton[kind="danger"] {{ background: transparent; border-color: {border}; color: {danger}; }}
QPushButton[kind="danger"]:hover {{ background: {danger_soft}; }}
QPushButton[kind="danger"]:disabled {{ color: {disabled}; }}
QPushButton[kind="stop"] {{ background: {stop}; border-color: {stop}; color: #ffffff; font-weight: 600; }}
QPushButton[kind="stop"]:hover {{ background: {stop_hover}; border-color: {stop_hover}; }}
QPushButton[kind="stop"]:disabled {{ background: {surface3}; border-color: {surface3}; color: {disabled}; }}
QPushButton[kind="ghost"] {{ background: transparent; border-color: transparent; color: {muted}; }}
QPushButton[kind="ghost"]:hover {{ background: {surface2}; color: {text}; }}
QPushButton[kind="ghost"]:disabled {{ background: transparent; border-color: transparent; color: {disabled}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; padding: 0; color: {muted}; text-align: left; text-decoration: underline; }}
QPushButton[kind="link"]:hover {{ color: {text}; }}
QPushButton[kind="card"] {{ text-align: left; padding: 8px 10px; border-radius: 6px; background: transparent; }}
QPushButton[kind="card"]:hover {{ background: {surface2}; }}
QPushButton[kind="card"]:checked {{ border: 2px solid {accent}; padding: 7px 9px; }}
QPushButton[kind="segment"] {{
    background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0;
    padding: 6px 2px; margin-right: 14px; color: {muted};
}}
QPushButton[kind="segment"]:hover {{ color: {text}; background: transparent; }}
QPushButton[kind="segment"]:checked {{ color: {text}; border-bottom-color: {text}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 5px 9px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {disabled}; background: {bg}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 22px; right: -4px;
}}
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url("{arrow_down_off}"); }}
QComboBox::down-arrow:on {{ image: url("{arrow_up}"); }}
QComboBox QAbstractItemView {{
    background: {surface}; border: 1px solid {border}; selection-background-color: {surface3};
    selection-color: {text}; padding: 4px;
}}
QSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; border-left: 1px solid {border}; background: {surface2};
}}
QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 6px; margin: 1px 1px 0 0; }}
QSpinBox::down-button {{
    subcontrol-position: bottom right; border-bottom-right-radius: 6px; margin: 0 1px 1px 0;
    border-top: 1px solid {border};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {hover}; }}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {{ background: transparent; }}
QSpinBox::up-arrow {{ image: url("{arrow_up}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{arrow_down}"); width: 10px; height: 10px; }}
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off {{ image: url("{arrow_up_off}"); }}
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off {{ image: url("{arrow_down_off}"); }}
QLineEdit[error="true"], QComboBox[error="true"] {{ border-color: {danger}; }}
#FieldError {{ color: {danger}; font-size: 9.5pt; }}
#EulaStrip {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; }}
#EulaStrip[error="true"] {{ border-color: {danger}; }}
#SaveBar {{ background: {surface}; border: none; border-top: 1px solid {border}; }}
#SaveBar[dirty="true"] {{ background: {accent_soft}; }}
#SaveBar QLabel {{ background: transparent; }}
#EmptyTitle {{ font-size: 13pt; font-weight: 600; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px; border: 1px solid {muted}; background: {surface};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QTableView::indicator {{ width: 15px; height: 15px; border: 1px solid {muted}; border-radius: 4px; background: {surface}; }}
QTableView::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url("{check}"); }}
QRadioButton::indicator:checked {{
    border-color: {accent};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {accent_text}, stop:0.35 {accent_text}, stop:0.45 {accent}, stop:1 {accent});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {surface2}; border-color: {surface3}; }}

QTabWidget::pane {{ border: none; border-top: 1px solid {border}; background: {bg}; top: -1px; }}
QTabWidget::tab-bar {{ left: 16px; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 8px 0 9px 0; margin-right: 20px;
    border: none; border-bottom: 2px solid transparent; font-weight: 500;
}}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:selected:hover {{ color: {text}; }}

QListWidget, QTableWidget {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; padding: 4px; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 4px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {surface3}; color: {text}; }}
QTableWidget {{ gridline-color: {border}; }}
QHeaderView::section {{ background: {surface}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 5px 8px; font-weight: 500; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {scroll}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {surface2}; border: none; border-radius: 3px; height: 6px; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}

#Console {{
    background: {console_bg}; color: {console_text}; border: 1px solid {border}; border-radius: 6px;
    padding: 8px 10px; font-family: {mono}; font-size: 10pt;
}}
#ConsoleInput {{ font-family: {mono}; padding: 7px 10px; }}
"""


_ARROW = ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
          '<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
          'stroke-linejoin="round"/></svg>')
_ARROW_PATHS = {"down": "M3.5 6l4.5 4.5 4.5-4.5", "up": "M3.5 10.5l4.5-4.5 4.5 4.5"}


def _arrows(colors: dict) -> dict:
    """Combo box / number box arrows drawn in the theme's colours (like check.svg, but the colour
    changes with the theme, so they're written to a cache folder when the theme is applied)."""
    folder = Path(tempfile.gettempdir()) / "bartizan-ui"
    out = {}
    for name, d in _ARROW_PATHS.items():
        for suffix, key in (("", "muted"), ("_off", "disabled")):
            color = colors[key]
            path = folder / f"arrow-{name}-{color.lstrip('#')}.svg"
            try:
                if not path.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    path.write_text(_ARROW.format(d=d, color=color), encoding="utf-8")
            except OSError:
                pass  # no arrows is better than no app: Qt just draws none
            out[f"arrow_{name}{suffix}"] = path.as_posix()
    return out


def app_icon() -> QIcon:
    """Window / taskbar / tray icon, pre-shrunk smoothly so small sizes don't look jagged."""
    src = QPixmap(str(paths.resource("icon.png")))
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return icon


def icon_pixmap(path, size: int, smooth: bool = True) -> QPixmap:
    """An image scaled to `size` (logical px), sharp on 125-200% display scaling.

    smooth=False keeps hard pixel edges, like Minecraft draws server icons."""
    app = QGuiApplication.instance()
    ratio = max(1.0, app.devicePixelRatio() if app else 1.0)
    pix = QPixmap(str(path))
    if pix.isNull():
        return pix
    px = round(size * ratio)
    pix = pix.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation if smooth else Qt.FastTransformation)
    pix.setDevicePixelRatio(ratio)
    return pix


def apply(app: QApplication, mode: str = "dark") -> None:
    colors = THEMES.get(mode, DARK)
    C.clear()
    C.update(colors)
    app.setStyle("Fusion")
    font = QFont()
    korean = ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans CJK KR"]
    # Korean UI: a Korean font first so Hangul and Latin share one consistent look
    families = korean + ["Segoe UI"] if language() == "ko" else ["Segoe UI"] + korean
    font.setFamilies(families + ["sans-serif"])
    font.setPointSizeF(10.5)
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
        (QPalette.PlaceholderText, "placeholder"),
        (QPalette.Link, "info"),
    ):
        pal.setColor(role, QColor(colors[key]))
    app.setPalette(pal)
    app.setStyleSheet(QSS.format(**colors, mono=MONO, check=paths.resource("check.svg").as_posix(),
                                 **_arrows(colors)))
    app.setWindowIcon(app_icon())


def set_kind(button, kind: str):
    """Button style: primary / danger / stop / ghost / link / card / segment."""
    button.setProperty("kind", kind)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def flatten_groups(root) -> None:
    """Sections are a title over a thin line now, not boxes: their content lines up with the title."""
    from PySide6.QtWidgets import QGroupBox
    for box in root.findChildren(QGroupBox):
        if box.layout() is not None:
            m = box.layout().contentsMargins()
            box.layout().setContentsMargins(0, m.top() if box.objectName() == "Stat" else 0, 0, 0)


def form_layout(parent=None) -> QFormLayout:
    """Form with comfortable spacing and labels aligned for easy scanning."""
    form = QFormLayout(parent)
    form.setVerticalSpacing(10)
    form.setHorizontalSpacing(18)
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return form


def fit_to_screen(widget, width: int, height: int, center: bool = False) -> None:
    """Resize to the preferred size, but never larger than the screen's usable area.

    Windows laptops with 125-150% display scaling often have only ~900x600 usable
    logical pixels; fixed sizes larger than that push buttons off-screen.
    """
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        width = min(width, int(avail.width() * 0.95))
        height = min(height, int(avail.height() * 0.92))
    widget.resize(width, height)
    if center and screen is not None:
        frame = widget.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        widget.move(frame.topLeft())
