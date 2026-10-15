"""Shared widgets: (?) help buttons, MOTD preview, server icon conversion."""

import html
import re
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget
from mc_server_maker.core import paths
from mc_server_maker.gui import theme
from mc_server_maker.i18n import t

COLORS = {
    "0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA",
    "4": "#AA0000", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
    "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF",
}
class HelpButton(QToolButton):
    """A small (?) next to a setting. Click it to read the longer explanation."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.help_text = text
        self.setText("?")
        self.setObjectName("Help")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName(t("Help"))
        self.setAccessibleDescription(text)
        self.clicked.connect(self.show_help)
        self._popup = None

    def show_help(self):
        popup = QFrame(self, Qt.Popup)
        popup.setObjectName("HelpPopup")
        v = QVBoxLayout(popup)
        v.setContentsMargins(12, 10, 12, 10)
        label = QLabel(self.help_text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        label.setMaximumWidth(340)
        label.setMinimumWidth(min(340, max(160, label.fontMetrics().horizontalAdvance(self.help_text) + 4)))
        v.addWidget(label)
        popup.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        x = min(pos.x(), screen.right() - popup.width() - 4)
        y = pos.y() if pos.y() + popup.height() < screen.bottom() else self.mapToGlobal(QPoint(0, 0)).y() - popup.height() - 4
        popup.move(max(screen.left() + 4, x), y)
        popup.show()
        self._popup = popup


def with_help(widget, text: str, expand: bool = False) -> QWidget:
    """`widget` (or a label for a string) followed by a (?) button.

    expand=True lets the widget take the row's width (for wrapping status text)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(QLabel(widget) if isinstance(widget, str) else widget, 1 if expand else 0)
    row.addWidget(HelpButton(text), 0, Qt.AlignTop if expand else Qt.AlignVCenter)
    if not expand:
        row.addStretch()
    return box


def color_help() -> str:
    return t("Colors: &0 black &1 dark blue &2 green &3 teal &4 red &5 purple &6 gold &7 gray "
             "&8 dark gray &9 blue &a lime &b aqua &c light red &d pink &e yellow &f white · "
             "&l bold &o italic &n underline &m strike &r reset")
_CODE_RE = re.compile(r"&([0-9a-fk-or])", re.IGNORECASE)


def amp_to_section(text: str) -> str:
    return _CODE_RE.sub(lambda m: "§" + m.group(1).lower(), text)


def section_to_amp(text: str) -> str:
    return text.replace("§", "&")


def motd_to_html(motd: str) -> str:
    """Convert a MOTD like '§aHello §lworld' to HTML."""
    out = []
    color = COLORS["7"]
    styles = set()
    i = 0
    buf = ""

    def flush():
        nonlocal buf
        if not buf:
            return
        css = [f"color:{color}"]
        if "l" in styles:
            css.append("font-weight:bold")
        if "o" in styles:
            css.append("font-style:italic")
        deco = [d for s, d in (("n", "underline"), ("m", "line-through")) if s in styles]
        if deco:
            css.append("text-decoration:" + " ".join(deco))
        text = html.escape(buf).replace("\n", "<br>").replace(" ", "&nbsp;")
        out.append(f'<span style="{";".join(css)}">{text}</span>')
        buf = ""

    while i < len(motd):
        c = motd[i]
        if c == "§" and i + 1 < len(motd):
            code = motd[i + 1].lower()
            flush()
            if code in COLORS:
                color = COLORS[code]
                styles.clear()
            elif code == "r":
                color = COLORS["7"]
                styles.clear()
            elif code in "lomn":
                styles.add(code)
            i += 2
            continue
        buf += c
        i += 1
    flush()
    return "".join(out)


class MotdPreview(QFrame):
    """Preview that looks like the Minecraft server list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("MotdPreview { background: #1e1e1e; border: 1px solid #555; border-radius: 4px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.icon = QLabel()
        self.icon.setFixedSize(64, 64)
        self.icon.setStyleSheet("background: #333;")
        self.icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon)
        col = QVBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("color: white; font-weight: bold;")
        self.motd = QLabel()
        self.motd.setTextFormat(Qt.RichText)
        self.motd.setStyleSheet("font-family: monospace;")
        col.addWidget(self.title)
        col.addWidget(self.motd)
        col.addStretch()
        layout.addLayout(col, 1)

    def update_preview(self, title: str, motd_section: str, icon_path: Path = None):
        self.title.setText(html.escape(title))
        self.motd.setText(motd_to_html(motd_section) or "&nbsp;")
        # without an icon, Minecraft shows its default one, so the preview does too
        has_icon = bool(icon_path) and Path(icon_path).exists()
        source = icon_path if has_icon else paths.resource("unknown-server.png")
        self.icon.setPixmap(theme.icon_pixmap(source, 64, smooth=False))


def convert_icon(src: str, dest: Path) -> None:
    """Center-crop any image to a square and save it as a 64x64 PNG."""
    img = QImage(src)
    if img.isNull():
        raise ValueError(t("Can't open that image. Choose a PNG/JPG/BMP/GIF file."))
    side = min(img.width(), img.height())
    x = (img.width() - side) // 2
    y = (img.height() - side) // 2
    img = img.copy(x, y, side, side).scaled(64, 64, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_ARGB32)
    if not img.save(str(dest), "PNG"):
        raise ValueError(t("Could not save the icon."))
