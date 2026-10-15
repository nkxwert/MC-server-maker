"""공용 위젯: MOTD 미리보기, 서버 아이콘 변환."""

import html
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

COLORS = {
    "0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA",
    "4": "#AA0000", "5": "#AA00AA", "6": "#FFAA00", "7": "#AAAAAA",
    "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
    "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF",
}
COLOR_HELP = (
    "색 코드: &0검정 &1진파랑 &2초록 &3청록 &4빨강 &5보라 &6금색 &7회색 "
    "&8진회색 &9파랑 &a연두 &b하늘 &c연빨강 &d분홍 &e노랑 &f흰색 · "
    "&l굵게 &o기울임 &n밑줄 &m취소선 &r초기화"
)
_CODE_RE = re.compile(r"&([0-9a-fk-or])", re.IGNORECASE)


def amp_to_section(text: str) -> str:
    return _CODE_RE.sub(lambda m: "§" + m.group(1).lower(), text)


def section_to_amp(text: str) -> str:
    return text.replace("§", "&")


def motd_to_html(motd: str) -> str:
    """'§a안녕 §l서버' 같은 MOTD를 HTML로 바꾼다."""
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
    """마인크래프트 서버 목록처럼 보이는 미리보기."""

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
            self.icon.setPixmap(QPixmap(str(icon_path)))
            self.icon.setText("")
        else:
            self.icon.setPixmap(QPixmap())
            self.icon.setText("<span style='color:#888'>아이콘<br>없음</span>")


def convert_icon(src: str, dest: Path) -> None:
    """아무 이미지나 가운데를 정사각형으로 잘라 64x64 PNG로 저장한다."""
    img = QImage(src)
    if img.isNull():
        raise ValueError("이미지를 열 수 없습니다. PNG/JPG/BMP/GIF 파일을 골라 주세요.")
    side = min(img.width(), img.height())
    x = (img.width() - side) // 2
    y = (img.height() - side) // 2
    img = img.copy(x, y, side, side).scaled(64, 64, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_ARGB32)
    if not img.save(str(dest), "PNG"):
        raise ValueError("아이콘 저장에 실패했습니다.")
