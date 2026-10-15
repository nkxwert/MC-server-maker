"""Shared widgets: MOTD preview, server icon conversion."""

import html
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
from mc_server_maker.gui import theme
from mc_server_maker.i18n import t

COLORS = {
    "0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA",
    "4": "#AA0000", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
    "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF",
}
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
        if icon_path and Path(icon_path).exists():
            self.icon.setPixmap(theme.icon_pixmap(icon_path, 64))
            self.icon.setText("")
        else:
            self.icon.setPixmap(QPixmap())
            self.icon.setText("<span style='color:#888'>" + t("No icon") + "</span>")


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
