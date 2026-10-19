"""Server tabs: Console / Status / Settings / World (with version updates) / Players / Network."""

import html
import os
import re
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import addons, joincheck, net, network, plugins, property_catalog, stats, versions
from mc_server_maker.core import server as srv
from mc_server_maker.core.properties import Properties
from mc_server_maker.core.providers import PROVIDERS, get_provider
from mc_server_maker.gui import anim, browse, theme
from mc_server_maker.gui.anim import FadeInDialog
from mc_server_maker.gui.browse import ModrinthBrowser
from mc_server_maker.gui.create_dialog import VersionLoader, random_seed
from mc_server_maker.gui.runner import ServerRunner
from mc_server_maker.gui.theme import fit_to_screen, form_layout, set_kind
from mc_server_maker.gui.widgets import (
    HelpButton,
    MotdPreview,
    amp_to_section,
    color_help,
    convert_icon,
    section_to_amp,
    set_status,
    with_help,
    with_note,
)
from mc_server_maker.gui.workers import TaskDialog, run_async
from mc_server_maker.i18n import t


def open_path(path: Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


AUTOSAVE_CHOICES = (0, 5, 10, 15, 30, 60)


def set_spin(spin: QSpinBox, value) -> None:
    """Put a value into a number box, clamped to its range.

    QSpinBox only holds 32-bit numbers; an out-of-range value from server.properties
    (e.g. max-players=99999999999) used to raise OverflowError and crash the app.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = spin.minimum()
    spin.setValue(max(spin.minimum(), min(spin.maximum(), value)))


def help_section(title: str, help_text: str, first: bool = False):
    """A section (title over a thin line) whose explanation hides behind a (?) next to the title."""
    box = QGroupBox()
    box.setObjectName("Section")
    if first:
        box.setProperty("first", True)
    v = QVBoxLayout(box)
    v.setSpacing(10)
    head = QHBoxLayout()
    head.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    head.addWidget(label)
    head.addWidget(HelpButton(help_text))
    head.addStretch()
    v.addLayout(head)
    return box, v


def left_aligned(widget: QWidget) -> QWidget:
    """Keep a button its natural width inside a form row (rows stretch their fields)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch()
    return box


def warn_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Warn")
    return label


def _scroll(widget: QWidget) -> QScrollArea:
    widget.layout().setContentsMargins(24, 10, 24, 24)
    widget.layout().setSpacing(10)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


class ServerTab(QWidget):
    """Base: holds the selected server and knows whether it is running."""

    def __init__(self, runner: ServerRunner, on_changed: Callable[[], None]):
        super().__init__()
        self.runner = runner
        self.on_changed = on_changed
        self.meta: Optional[srv.ServerMeta] = None

    @property
    def key(self) -> str:
        return str(self.meta.folder) if self.meta else ""

    @property
    def running(self) -> bool:
        return bool(self.meta) and self.runner.is_running(self.key)

    @property
    def locked(self) -> bool:
        """Running, or about to start: its files must not be changed now."""
        return self.running or (bool(self.meta) and self.key in self.runner.pending)

    def set_server(self, meta: srv.ServerMeta) -> None:
        self.meta = meta
        self.refresh()

    def forget_server(self) -> None:
        """The shown server was deleted: a new server in the same folder must start fresh."""
        self.meta = None

    def refresh(self) -> None:
        pass

    def on_state(self) -> None:
        """Called when the server starts or stops."""
        self.refresh()

    def run_task(self, title: str, fn) -> bool:
        key = self.key
        if key and key in self.runner.busy:
            return False
        if key:
            self.runner.busy.add(key)  # Start waits until the files are changed
        try:
            dlg = TaskDialog(self, title, fn)
            dlg.exec()
        finally:
            self.runner.busy.discard(key)
        return dlg.succeeded()


# =================================================================== console

_CONSOLE_RULES = [
    (re.compile(r"^»» "), "info", True),
    (re.compile(r"^> "), "text", True),
    (re.compile(r"ERROR|SEVERE|Exception|^\s+at "), "danger", False),
    (re.compile(r"WARN"), "warn", False),
    (re.compile(r"joined the game"), "ok", False),
    (re.compile(r"left the game"), "warn", False),
    (re.compile(r": <[^>]+> "), "#ffffff", True),  # chat
    (re.compile(r"Done \("), "ok", True),
]


def _line_format(line: str) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(theme.DARK["console_text"]))
    for pattern, color, bold in _CONSOLE_RULES:
        if pattern.search(line):
            # the console background is always dark, so use the dark palette
            fmt.setForeground(QColor(theme.DARK.get(color, color)))
            if bold:
                fmt.setFontWeight(QFont.Bold)
            break
    return fmt


class HistoryLineEdit(QLineEdit):
    """Up/Down recall previous commands."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []
        self.pos = 0

    def remember(self, text: str):
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.pos = len(self.history)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up and self.history:
            self.pos = max(0, self.pos - 1)
            self.setText(self.history[self.pos])
        elif event.key() == Qt.Key_Down and self.history:
            self.pos = min(len(self.history), self.pos + 1)
            self.setText(self.history[self.pos] if self.pos < len(self.history) else "")
        else:
            super().keyPressEvent(event)


def format_uptime(secs: float) -> str:
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return (f"{d}d " if d else "") + f"{h:02d}:{m:02d}:{s:02d}"


def format_total(secs: float) -> str:
    """Long running times in words: '3d 4h', '5h 12m', '7m 30s', '13s'."""
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return t("{d}d {h}h", d=d, h=h)
    if h:
        return t("{h}h {m}m", h=h, m=m)
    if m:
        return t("{m}m {s}s", m=m, s=s)
    return t("{s}s", s=s)


class OnlinePlayersDialog(FadeInDialog):
    """Online players with Kick / Ban (updates live)."""

    def __init__(self, parent, runner: ServerRunner, key: str):
        super().__init__(parent)
        self.runner, self.key = runner, key
        self.setWindowTitle(t("Online players"))
        fit_to_screen(self, 360, 420)
        layout = QVBoxLayout(self)
        self.count = QLabel()
        self.count.setObjectName("Big")
        layout.addWidget(self.count)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        self.reason = QLineEdit(placeholderText=t("Reason (optional)"))
        layout.addWidget(self.reason)
        row = QHBoxLayout()
        self.btn_kick = QPushButton(t("Kick"))
        self.btn_kick.clicked.connect(lambda: self._act("kick"))
        self.btn_ban = set_kind(QPushButton(t("Ban")), "danger")
        self.btn_ban.clicked.connect(lambda: self._act("ban"))
        row.addWidget(self.btn_kick)
        row.addWidget(self.btn_ban)
        row.addStretch()
        close = set_kind(QPushButton(t("Close")), "ghost")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        runner.players_changed.connect(self._refresh)
        self._refresh(key)

    def _refresh(self, key: str):
        if key != self.key:
            return
        names = self.runner.online_players(key)
        current = self.list.currentItem().text() if self.list.currentItem() else None
        self.list.clear()
        self.list.addItems(names)
        if current in names:
            self.list.setCurrentRow(names.index(current))
        self.count.setText(t("{n} online", n=len(names)))
        has = bool(names) and self.runner.is_running(key)
        self.btn_kick.setEnabled(has)
        self.btn_ban.setEnabled(has)

    def _act(self, cmd: str):
        item = self.list.currentItem()
        if not item:
            QMessageBox.information(self, t("Online players"), t("Select a player first."))
            return
        name = item.text()
        if cmd == "ban" and QMessageBox.question(self, t("Ban"), t("Ban {name} from this server?", name=name)) != QMessageBox.Yes:
            return
        reason = self.reason.text().strip()
        self.runner.send(self.key, f"{cmd} {name}" + (f" {reason}" if reason else ""))


class ConsoleTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(8)
        # after a start: is the server reachable for friends, and what to do next
        self.friend_bar = QFrame()
        self.friend_bar.setObjectName("FriendBar")
        fb = QHBoxLayout(self.friend_bar)
        fb.setContentsMargins(14, 10, 12, 10)
        fb.setSpacing(12)
        self.friend_text = QLabel()
        self.friend_text.setWordWrap(True)
        self.friend_text.setTextFormat(Qt.RichText)
        self.friend_text.setMinimumWidth(240)
        fb.addWidget(self.friend_text, 1)
        self.friend_btn = set_kind(QPushButton(), "primary")
        self.friend_btn.clicked.connect(self._friend_action)
        fb.addWidget(self.friend_btn)
        self.friend_bar.setVisible(False)
        left.addWidget(self.friend_bar)
        self._friend = ("", "lan")  # address and kind, from the Network tab
        self.open_network = None  # set by the main window: shows the Network tab
        self.copy_invite = None  # set by the main window: copies the invitation text
        self.view = QPlainTextEdit(readOnly=True)
        self.view.setObjectName("Console")
        self.view.setMaximumBlockCount(5000)
        left.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = HistoryLineEdit(placeholderText=t("Type a command and press Enter"))
        self.input.setObjectName("ConsoleInput")
        self.input.returnPressed.connect(self._send)
        self.save_btn = QPushButton(t("Save world"))
        self.save_btn.setToolTip("save-all")
        self.save_btn.clicked.connect(lambda: self.runner.send(self.key, "save-all"))
        clear = set_kind(QPushButton(t("Clear")), "ghost")
        clear.clicked.connect(self._clear)
        row.addWidget(self.input, 1)
        row.addWidget(self.save_btn)
        row.addWidget(clear)
        left.addLayout(row)
        outer.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(0)
        box = QGroupBox(t("Online"))
        box.setObjectName("Stat")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        self.player_count = QLabel("0")
        self.player_count.setObjectName("Big")
        v.addWidget(self.player_count)
        self.more_btn = set_kind(QPushButton(t("Show list")), "link")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.clicked.connect(self._show_players)
        v.addWidget(self.more_btn, 0, Qt.AlignLeft)
        side.addWidget(box)
        side.addWidget(self._rule())
        box = QGroupBox(t("Uptime"))
        box.setObjectName("Stat")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 12, 0, 0)
        self.uptime = QLabel("-")
        self.uptime.setObjectName("Big")
        v.addWidget(self.uptime)
        side.addWidget(box)
        side.addWidget(self._rule())
        box = QGroupBox(t("Total uptime"))
        box.setObjectName("Stat")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 12, 0, 0)
        self.total_uptime = QLabel("-")
        self.total_uptime.setObjectName("Big")
        self.total_uptime.setWordWrap(True)
        self.total_uptime.setToolTip(t("All the time this server has been running, across every start."))
        v.addWidget(self.total_uptime)
        side.addWidget(box)
        side.addStretch()  # numbers stay together at the top
        side_w = QWidget()
        side_w.setLayout(side)
        side.setContentsMargins(0, 0, 0, 0)
        side_w.setFixedWidth(150)  # fits "00:00:00" and long totals
        outer.addWidget(side_w)

        # Lines are drawn in batches (a few times per second) instead of one by one,
        # and not at all while the console is hidden: keeps the app light.
        self._pending: deque = deque(maxlen=self.view.maximumBlockCount())
        self._dirty = False  # the whole log must be redrawn (another server, cleared...)
        self._missed = 0  # lines that arrived while hidden: only these are added on return
        self._paused = False  # window minimized
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush)
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self._tick)
        runner.line.connect(self._on_line)
        runner.players_changed.connect(self._on_players)

    @staticmethod
    def _rule() -> QFrame:
        rule = QFrame()
        rule.setObjectName("Rule")
        return rule

    @property
    def controls(self):
        return [self.input, self.save_btn]

    def set_server(self, meta) -> None:
        if self.meta is not None and meta.folder == self.meta.folder and not self._dirty:
            self.meta = meta  # same server reloaded (Save, rename...): the log on screen is still right
            self.on_state()
        else:
            super().set_server(meta)

    def forget_server(self) -> None:
        super().forget_server()
        self._dirty = True
        self._pending.clear()
        self._missed = 0
        self.view.clear()

    def _live(self) -> bool:
        return self.isVisible() and not self._paused

    def refresh(self):
        self._pending.clear()
        self._missed = 0
        self.view.setPlaceholderText(t("The server is off. Press Start to see its log here."))
        if not self._live():
            self._dirty = True  # redraw once it's on screen again; hidden work is wasted work
            self.view.clear()
        else:
            self._dirty = False
            self._redraw(self.runner.log_lines(self.key) if self.meta else [], clear=True)
        self.on_state()

    def _redraw(self, lines, clear: bool):
        """Add many lines in one go (one edit, one repaint) instead of one by one."""
        lines = list(lines)[-self.view.maximumBlockCount():]
        bar = self.view.verticalScrollBar()
        at_bottom = clear or bar.value() >= bar.maximum() - 4
        self.view.setUpdatesEnabled(False)
        try:
            if clear:
                self.view.clear()
            cursor = QTextCursor(self.view.document())
            cursor.beginEditBlock()
            for ln in lines:
                self._insert(cursor, ln)
            cursor.endEditBlock()
        finally:
            self.view.setUpdatesEnabled(True)
        if at_bottom:
            bar.setValue(bar.maximum())

    def _catch_up(self):
        if self._dirty or self._missed >= self.view.maximumBlockCount():
            self.refresh()
        elif self._missed:
            log = self.runner.log_lines(self.key)
            self._redraw(log[-self._missed:], clear=False)
        self._missed = 0

    def set_paused(self, paused: bool):
        self._paused = paused
        if paused:
            self._uptime_timer.stop()
        elif self.isVisible():
            self._catch_up()
            self._uptime_timer.start(1000)
            self._tick()

    def on_state(self):
        # update buttons only; don't redraw the log
        for w in self.controls:
            w.setEnabled(self.running)
        self._on_players(self.key)
        self._tick()
        self._render_friend()

    def set_friend(self, address: str, kind: str) -> None:
        """The address friends should use (from the Network tab): 'tunnel', 'internet' or 'lan'."""
        self._friend = (address, kind)
        self._render_friend()

    def _render_friend(self):
        address, kind = self._friend
        show = self.running and bool(self.meta)
        self.friend_bar.setVisible(show)
        if not show:
            return
        c = theme.C
        if kind in ("tunnel", "internet") and address:
            how = t("playit.gg tunnel") if kind == "tunnel" else t("router port")
            text = (f"<span style='color:{c['ok']}'>●</span>&nbsp; <b>{html.escape(t('Friends can join'))}</b>"
                    f" <span style='color:{c['muted']}'>· {html.escape(how)}</span><br>"
                    + html.escape(t("Address to send: {addr}", addr=address)))
            self.friend_btn.setText(t("Copy invitation"))
            tint = c["ok"]
        else:
            lan = html.escape(address or "-")
            text = (f"<span style='color:{c['warn']}'>●</span>&nbsp; <b>{html.escape(t('The server is on. Friends elsewhere can not join yet.'))}</b><br>"
                    + t("People on the same Wi-Fi can join now: <b>{lan}</b>", lan=lan))
            self.friend_btn.setText(t("Open to the internet"))
            tint = c["accent"]
        col = QColor(tint)
        rgb = f"{col.red()}, {col.green()}, {col.blue()}"
        self.friend_bar.setStyleSheet(  # a faint tint of the state's color (Qt hex alpha is #AARRGGBB)
            f"#FriendBar {{ background: rgba({rgb}, 0.10); border: 1px solid rgba({rgb}, 0.40); border-radius: 8px; }}")
        self.friend_text.setText(text)

    def _friend_action(self):
        address, kind = self._friend
        if kind in ("tunnel", "internet") and address:
            if self.copy_invite:
                self.copy_invite()
                self.friend_btn.setText(t("Copied"))
                QTimer.singleShot(1200, self._render_friend)
        elif self.open_network:
            self.open_network()

    def showEvent(self, event):
        super().showEvent(event)
        if self._paused:
            return
        self._catch_up()  # add what arrived while hidden
        self._uptime_timer.start(1000)
        self._tick()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._uptime_timer.stop()

    def _insert(self, cursor: QTextCursor, line: str):
        cursor.movePosition(QTextCursor.End)
        if not self.view.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(line, _line_format(line))

    def _on_line(self, key: str, line: str):
        if key != self.key:
            return
        if not self._live():
            self._missed += 1
            return
        self._pending.append(line)
        if not self._flush_timer.isActive():
            self._flush_timer.start(150)

    def _flush(self):
        if not self._pending:
            return
        # a flood bigger than the console replaces it (older lines would be trimmed right away)
        self._redraw(self._pending, clear=len(self._pending) >= self._pending.maxlen)
        self._pending.clear()

    def _on_players(self, key: str):
        if key != self.key:
            return
        self.player_count.setText(str(len(self.runner.online_players(key))))

    def _tick(self):
        up = self.runner.uptime(self.key) if self.meta else 0
        self.uptime.setText(format_uptime(up) if up else "-")
        total = self.runner.total_uptime(self.key) if self.meta else 0
        self.total_uptime.setText(format_total(total) if total >= 1 else "-")

    def _show_players(self):
        if self.meta:
            dlg = OnlinePlayersDialog(self, self.runner, self.key)
            dlg.exec()
            dlg.deleteLater()

    def _clear(self):
        self.runner.clear_log(self.key)
        self._pending.clear()
        self._missed = 0
        self.view.clear()

    def _send(self):
        cmd = self.input.text().strip().lstrip("/")
        if cmd and self.runner.send(self.key, cmd):
            self.input.remember(cmd)
            self.input.clear()


# ================================================================== settings


class PropertiesDialog(FadeInDialog):
    """Every server.properties setting: all known keys plus anything already in the file."""

    def __init__(self, parent, path: Path):
        super().__init__(parent)
        self.setWindowTitle(t("All server.properties"))
        fit_to_screen(self, 860, 680)
        self.props = Properties(path)
        layout = QVBoxLayout(self)
        layout.addWidget(hint(t("All settings. Gray values are defaults that aren't in the file yet. Changes apply on next start.")))
        self.filter = QLineEdit(placeholderText=t("Search..."))
        self.filter.textChanged.connect(self._filter)
        layout.addWidget(self.filter)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([t("Key"), t("Value"), t("Description")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 200)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        keys = sorted(set(property_catalog.BY_KEY) | set(self.props.values))
        self._original = {}
        self._bool_keys = set()
        for key in keys:
            self._add_row(key)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton(t("Add setting"))
        add.clicked.connect(self._add_new)
        row.addWidget(add)
        row.addStretch()
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        set_kind(buttons.addButton(t("Save"), QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton(t("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, key: str):
        info = property_catalog.BY_KEY.get(key)
        in_file = key in self.props.values
        value = self.props.values[key] if in_file else (info.default if info else "")
        self._original[key] = (value, in_file)
        r = self.table.rowCount()
        self.table.insertRow(r)
        k = QTableWidgetItem(key)
        k.setFlags(k.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 0, k)
        if info and info.is_bool and value in ("true", "false"):
            self._bool_keys.add(key)
            v = QTableWidgetItem(value)
            v.setFlags((v.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            v.setCheckState(Qt.Checked if value == "true" else Qt.Unchecked)
        else:
            v = QTableWidgetItem(value)
        if not in_file:
            v.setForeground(QColor(theme.C["muted"]))
        self.table.setItem(r, 1, v)
        d = QTableWidgetItem(info.description() if info else "")
        d.setFlags(d.flags() & ~Qt.ItemIsEditable)
        d.setForeground(QColor(theme.C["muted"]))
        d.setToolTip(d.text())
        self.table.setItem(r, 2, d)

    def _value(self, r: int) -> str:
        item = self.table.item(r, 1)
        if self.table.item(r, 0).text() in self._bool_keys:
            return "true" if item.checkState() == Qt.Checked else "false"
        return item.text()

    def _add_new(self):
        key, ok = QInputDialog.getText(self, t("Add setting"), t("Key (e.g. simulation-distance):"))
        key = key.strip()
        if ok and key and key not in self._original:
            self._add_row(key)
            self.table.scrollToBottom()

    def _filter(self, text: str):
        text = text.lower()
        for r in range(self.table.rowCount()):
            hay = self.table.item(r, 0).text().lower() + " " + self.table.item(r, 2).text().lower()
            self.table.setRowHidden(r, text not in hay)

    def _save(self):
        # numbers Minecraft reads as 32-bit ints must fit, or the server (and older app versions) choke
        bad = []
        for r in range(self.table.rowCount()):
            key = self.table.item(r, 0).text()
            info = property_catalog.BY_KEY.get(key)
            value = self._value(r).strip()
            if info and info.default.lstrip("-").isdigit() and value:
                try:
                    ok = -(2**31) <= int(value) <= 2**31 - 1
                except ValueError:
                    ok = False
                if not ok:
                    bad.append(f"{key} = {value}")
        if bad:
            QMessageBox.warning(self, t("All server.properties"),
                                t("These need a whole number between -2147483648 and 2147483647:") + "\n" + "\n".join(bad))
            return
        for r in range(self.table.rowCount()):
            key = self.table.item(r, 0).text()
            value = self._value(r)
            original, _in_file = self._original.get(key, ("", False))
            # only write what changed; untouched defaults stay out of the file
            if value != original:
                self.props.set(key, value)
        self.props.save()
        self.accept()


class SettingsTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        self.notice = warn_label("")
        layout.addWidget(self.notice)

        box = QGroupBox(t("Name · description · icon"))
        box.setProperty("first", True)
        form = form_layout(box)
        self.name = QLineEdit()
        form.addRow(t("Name"), self.name)
        self.motd = QPlainTextEdit()
        self.motd.setFixedHeight(56)
        self.motd.textChanged.connect(self._update_preview)
        form.addRow(t("Description"), with_note(self.motd, t(
            "Shown under the server name in the multiplayer list (MOTD). Up to 2 lines.")))
        self.motd.setToolTip(color_help())  # the colour codes show when hovering over the box
        icon_row = QHBoxLayout()
        pick = QPushButton(t("Choose image..."))
        pick.clicked.connect(self._pick_icon)
        remove = set_kind(QPushButton(t("Remove")), "ghost")
        remove.clicked.connect(self._remove_icon)
        icon_row.addWidget(pick)
        icon_row.addWidget(remove)
        icon_row.addStretch()
        icon_w = QWidget()
        icon_w.setLayout(icon_row)
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_w.setToolTip(t("Any image; resized to 64×64 automatically."))
        form.addRow(t("Icon"), icon_w)
        self.preview = MotdPreview()
        form.addRow(t("Preview"), self.preview)
        layout.addWidget(box)

        box = QGroupBox(t("Game"))
        form = form_layout(box)
        self.max_players = QSpinBox(minimum=1, maximum=1000)
        form.addRow(t("Max players"), self.max_players)
        self.gamemode = QComboBox()
        for k, label in srv.GAMEMODES:
            self.gamemode.addItem(t(label), k)
        form.addRow(t("Game mode"), self.gamemode)
        self.difficulty = QComboBox()
        for k, label in srv.DIFFICULTIES:
            self.difficulty.addItem(t(label), k)
        form.addRow(t("Difficulty"), self.difficulty)
        self.port = QSpinBox(minimum=1, maximum=65535)
        form.addRow(t("Port"), with_note(self.port, t(
            "Usually 25565. Change it only to run several servers at the same time.")))
        self.view_distance = QSpinBox(minimum=2, maximum=32)
        form.addRow(with_help(t("View distance"), t(
            "How far players can see, in chunks. Higher looks better but uses more memory and CPU.")),
            self.view_distance)
        self.sim_distance = QSpinBox(minimum=2, maximum=32)
        form.addRow(with_help(t("Simulation distance"), t(
            "How far from players the world keeps moving (crops, mobs, redstone), in chunks. Lower is lighter.")),
            self.sim_distance)
        self.spawn_protection = QSpinBox(minimum=0, maximum=10000)
        self.spawn_protection.setSpecialValueText(t("Off"))
        form.addRow(with_help(t("Spawn protection"), t(
            "Within this many blocks of the world spawn, only OPs can break or place blocks. "
            "0 = off, everyone can build. It only works once the server has at least one OP.")),
            self.spawn_protection)
        self.checks = {}
        rules = QGridLayout()
        rules.setContentsMargins(0, 0, 0, 0)
        rules.setHorizontalSpacing(28)
        rules.setVerticalSpacing(8)
        for i, (key, label, help_text) in enumerate((
            ("online-mode", "Online mode", "Players must sign in with a real Minecraft account. "
             "Turn it off to let non-premium accounts join (anyone can then use any name)."),
            ("pvp", "PvP", ""),
            ("hardcore", "Hardcore", "One life: players become spectators when they die."),
            ("white-list", "Whitelist only", "Only players on the whitelist can join. Add a friend in the console: whitelist add <name>"),
            ("allow-flight", "Allow flight", "Stops the server from kicking players for flying. "
             "Turn it on if mods or plugins let players fly."),
            ("enable-command-block", "Command blocks", ""),
        )):
            cb = QCheckBox(t(label))
            if help_text:
                cb.setToolTip(t(help_text))
            self.checks[key] = cb
            rules.addWidget(cb, i // 2, i % 2)
        rules.setColumnStretch(2, 1)
        rules_w = QWidget()
        rules_w.setLayout(rules)
        form.addRow(t("Rules"), rules_w)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64)
        form.addRow(t("Memory (RAM)"), with_note(self.ram, t(
            "1–3 players: 1–2 GB is usually enough. Modpacks need 4 GB or more.")))
        self.autosave = QComboBox()
        for minutes in AUTOSAVE_CHOICES:
            self.autosave.addItem(t("Off") if not minutes else
                                  t("Every {n} minutes", n=minutes) if minutes < 60 else t("Every hour"), minutes)
        self.autosave.setToolTip(t(
            "While the server runs, the world is saved at this interval, so less is lost if the PC "
            "shuts down suddenly. Saving takes a moment on big worlds."))
        form.addRow(t("Auto-save"), self.autosave)
        self.memory_saver = QCheckBox(t("Use less memory"))
        self.memory_saver.toggled.connect(self._memory_saver_toggled)
        form.addRow("", with_note(self.memory_saver, t(
            "Usually saves a third to half of the memory. Sets view distance 6 and simulation distance 4, "
            "unloads spawn chunks and returns unused memory sooner. Far-away farms only run while someone is nearby.")))
        all_props = set_kind(QPushButton(t("Edit all server.properties...")), "ghost")
        all_props.clicked.connect(self._edit_all)
        form.addRow("", left_aligned(all_props))
        layout.addWidget(box)

        self.bedrock_box = QGroupBox(t("Bedrock players (phone / console / Windows)"))
        v = QVBoxLayout(self.bedrock_box)
        v.setSpacing(10)
        v.addWidget(hint(t(
            "Installs Geyser + Floodgate so Bedrock Edition players can join with their Xbox account.")))
        self.bedrock_status = QLabel()
        v.addWidget(self.bedrock_status)
        row = QHBoxLayout()
        self.btn_bedrock = QPushButton()
        self.btn_bedrock.clicked.connect(self._install_bedrock)
        self.btn_bedrock_remove = set_kind(QPushButton(t("Remove")), "danger")
        self.btn_bedrock_remove.clicked.connect(self._remove_bedrock)
        row.addWidget(self.btn_bedrock)
        row.addWidget(self.btn_bedrock_remove)
        row.addStretch()
        v.addLayout(row)
        layout.addWidget(self.bedrock_box)

        # ---- world (its buttons act right away; the save bar below is only for the settings)
        layout.addSpacing(28)
        rule = QFrame()
        rule.setObjectName("Rule")
        layout.addWidget(rule)
        layout.addSpacing(16)
        title = QLabel(t("World"))
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.world = WorldTab(runner, on_changed, embedded=True)
        layout.addWidget(self.world)
        layout.addStretch()

        # ---- save bar: always under the form (no jumping), says when something isn't saved yet
        self.save_bar = QFrame()
        self.save_bar.setObjectName("SaveBar")
        bar = QHBoxLayout(self.save_bar)
        bar.setContentsMargins(24, 10, 24, 10)
        bar.setSpacing(10)
        self.save_status = QLabel()
        self.save_status.setWordWrap(True)
        bar.addWidget(self.save_status, 1)
        self.btn_undo = set_kind(QPushButton(t("Undo changes")), "ghost")
        self.btn_undo.clicked.connect(lambda: self.refresh())  # back to what the files say
        bar.addWidget(self.btn_undo)
        self.btn_save = set_kind(QPushButton(t("Save server settings")), "primary")
        self.btn_save.setMinimumHeight(34)
        self.btn_save.clicked.connect(self.save)
        bar.addWidget(self.btn_save)
        for w in (self.name, self.motd):
            w.textChanged.connect(self._update_save_bar)
        for spin in list(self._spins().values()) + [self.ram]:
            spin.valueChanged.connect(self._update_save_bar)
        for cb in list(self.checks.values()) + [self.memory_saver]:
            cb.toggled.connect(self._update_save_bar)
        for combo in (self.gamemode, self.difficulty, self.autosave):
            combo.currentIndexChanged.connect(self._update_save_bar)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_scroll(body), 1)
        outer.addWidget(self.save_bar)
        self._update_save_bar()

    def _update_save_bar(self, *_):
        changed = self.has_unsaved()
        if changed:
            self.save_status.setText(t("You changed settings. They apply when the server restarts.")
                                     if self.running else t("You changed settings."))
        else:
            self.save_status.setText(t("No unsaved changes"))
        self.save_status.setObjectName("" if changed else "Muted")
        self.btn_undo.setVisible(changed)
        self.btn_save.setEnabled(changed)
        if self.save_bar.property("dirty") != changed:
            self.save_bar.setProperty("dirty", changed)
            for w in (self.save_bar, self.save_status):
                w.style().unpolish(w)
                w.style().polish(w)

    @property
    def icon_path(self) -> Path:
        return self.meta.folder / "server-icon.png"

    def refresh(self):
        if not self.meta:
            return
        p = self.meta.properties()
        self.name.setText(self.meta.name)
        self.motd.setPlainText(section_to_amp(p.get("motd", "A Minecraft Server")))
        set_spin(self.max_players, p.get_int("max-players", 20))
        gm = srv.parse_choice(p.get("gamemode"), srv.GAMEMODES, "survival")
        self.gamemode.setCurrentIndex(self.gamemode.findData(gm))
        diff = srv.parse_choice(p.get("difficulty"), srv.DIFFICULTIES, "easy")
        self.difficulty.setCurrentIndex(self.difficulty.findData(diff))
        set_spin(self.port, p.get_int("server-port", 25565))
        set_spin(self.view_distance, p.get_int("view-distance", 10))
        set_spin(self.sim_distance, p.get_int("simulation-distance", 10))
        set_spin(self.spawn_protection, p.get_int("spawn-protection", 16))
        self.memory_saver.blockSignals(True)
        self.memory_saver.setChecked(self.meta.memory_saver)
        self.memory_saver.blockSignals(False)
        self._distances_before = (self.view_distance.value(), self.sim_distance.value())
        defaults = {"online-mode": True, "pvp": True}
        for key, cb in self.checks.items():
            cb.setChecked(p.get_bool(key, defaults.get(key, False)))
        set_spin(self.ram, max(1, self.meta.ram_mb // 1024))
        idx = self.autosave.findData(self.meta.autosave_minutes)
        if idx < 0:  # an interval not in the list (edited by hand): show it anyway
            self.autosave.addItem(t("Every {n} minutes", n=self.meta.autosave_minutes), self.meta.autosave_minutes)
            idx = self.autosave.count() - 1
        self.autosave.setCurrentIndex(idx)
        self._update_preview()
        self._loaded = self._form_state()  # what's on disk; Save writes only what differs
        self.world.set_server(self.meta)
        self.on_state()

    def _spins(self):
        return {"max-players": self.max_players, "server-port": self.port, "view-distance": self.view_distance,
                "simulation-distance": self.sim_distance, "spawn-protection": self.spawn_protection}

    def _form_state(self) -> dict:
        state = {key: spin.value() for key, spin in self._spins().items()}
        state.update({key: cb.isChecked() for key, cb in self.checks.items()})
        state.update(motd=self.motd.toPlainText(), gamemode=self.gamemode.currentData(),
                     difficulty=self.difficulty.currentData(), _name=self.name.text(),
                     _ram=self.ram.value(), _saver=self.memory_saver.isChecked(),
                     _autosave=self.autosave.currentData())
        return state

    def _apply_form_state(self, state: dict):
        for key, spin in self._spins().items():
            spin.setValue(state[key])
        for key, cb in self.checks.items():
            cb.setChecked(state[key])
        self.motd.setPlainText(state["motd"])
        self.gamemode.setCurrentIndex(self.gamemode.findData(state["gamemode"]))
        self.difficulty.setCurrentIndex(self.difficulty.findData(state["difficulty"]))
        self.name.setText(state["_name"])
        self.ram.setValue(state["_ram"])
        self.autosave.setCurrentIndex(max(0, self.autosave.findData(state["_autosave"])))
        self.memory_saver.blockSignals(True)
        self.memory_saver.setChecked(state["_saver"])
        self.memory_saver.blockSignals(False)

    def _icon_changed(self):
        # the window reloads to show the new icon; keep what the user typed but hasn't saved
        state, loaded = self._form_state(), self._loaded
        self.on_changed()
        if self.meta:
            self._apply_form_state(state)
            self._loaded = loaded
            self._update_preview()
            self._update_save_bar()

    def on_state(self):
        # only update the notice so unsaved edits are kept
        self.notice.setText(t("The server is running. Saved changes apply after a restart.") if self.running else "")
        self.notice.setVisible(self.running)
        self._refresh_bedrock()
        self._update_save_bar()
        self.world.on_state()

    def _refresh_bedrock(self):
        if not self.meta:
            return
        supported = plugins.supports_bedrock(self.meta)
        self.bedrock_box.setVisible(supported)
        if not supported:
            return
        installed = plugins.bedrock_installed(self.meta)
        if installed:
            set_status(self.bedrock_status, "ok", t("Enabled — Bedrock port {port} (UDP)", port=plugins.bedrock_port(self.meta)))
        else:
            set_status(self.bedrock_status, "off", t("Not enabled"))
        self.btn_bedrock.setText(t("Update Geyser") if installed else t("Enable Bedrock join"))
        self.btn_bedrock.setEnabled(not self.locked)
        self.btn_bedrock_remove.setVisible(installed)
        self.btn_bedrock_remove.setEnabled(not self.locked)

    def _memory_saver_toggled(self, on: bool):
        if on:
            self._distances_before = (self.view_distance.value(), self.sim_distance.value())
            set_spin(self.view_distance, srv.MEMORY_SAVER_DISTANCES["view-distance"])
            set_spin(self.sim_distance, srv.MEMORY_SAVER_DISTANCES["simulation-distance"])
        else:
            saved = self.meta.saved_distances if self.meta and self.meta.saved_distances else {}
            set_spin(self.view_distance, saved.get("view-distance", self._distances_before[0]))
            set_spin(self.sim_distance, saved.get("simulation-distance", self._distances_before[1]))

    def _update_preview(self):
        if not self.meta:
            return
        motd = "\n".join(self.motd.toPlainText().splitlines()[:2])
        self.preview.update_preview("Minecraft Server", amp_to_section(motd), self.icon_path)

    def _pick_icon(self):
        f, _ = QFileDialog.getOpenFileName(
            self, t("Choose image"), "", t("Images") + " (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not f:
            return
        try:
            convert_icon(f, self.icon_path)
        except ValueError as e:
            QMessageBox.warning(self, t("Icon"), str(e))
            return
        self._update_preview()
        self._icon_changed()

    def _remove_icon(self):
        self.icon_path.unlink(missing_ok=True)
        self._update_preview()
        self._icon_changed()

    def set_server(self, meta) -> None:
        if self.meta is not None and meta.folder == self.meta.folder:
            self.meta = meta  # the same server reloaded (rename elsewhere, app settings...): keep edits
            self._reload_keeping_edits()
        else:
            super().set_server(meta)

    def has_unsaved(self) -> bool:
        loaded = getattr(self, "_loaded", None)
        return self.meta is not None and loaded is not None and self._form_state() != loaded

    def forget_server(self) -> None:
        super().forget_server()
        self._loaded = None  # no unsaved edits carry over to whatever comes next
        self._update_save_bar()
        self.world.forget_server()

    def _reload_keeping_edits(self):
        """Re-read the server from disk but keep what the user changed and hasn't saved yet."""
        loaded = getattr(self, "_loaded", None)
        edits = {k: v for k, v in self._form_state().items() if loaded is not None and v != loaded.get(k)}
        self.refresh()
        if edits:
            state = self._form_state()
            state.update(edits)
            self._apply_form_state(state)
            self._update_preview()
            self._update_save_bar()

    def _edit_all(self):
        if PropertiesDialog(self, self.meta.properties_path).exec():
            self._reload_keeping_edits()

    def _install_bedrock(self):
        meta = self.meta
        self.run_task(t("Bedrock players"), lambda task: plugins.install_bedrock(meta, task))
        self._refresh_bedrock()
        self.on_changed()  # the Network and Status tabs show the Bedrock port too

    def _remove_bedrock(self):
        if QMessageBox.question(self, t("Bedrock players"), t("Remove Geyser and Floodgate?")) == QMessageBox.Yes:
            plugins.remove_bedrock(self.meta)
            self._refresh_bedrock()
            self.on_changed()

    def save(self):
        if not self.meta:
            return
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, t("Save"), t("Enter a server name."))
            return
        v = self.meta.mc_version
        p = self.meta.properties()
        # write only what changed: untouched values (a MOTD with a literal "&", max-players over
        # 1000, enforce-whitelist set in the full editor...) stay exactly as they are in the file
        state = self._form_state()
        changed = {k for k, val in state.items() if val != self._loaded.get(k)}
        if "motd" in changed:
            p.set("motd", amp_to_section("\n".join(state["motd"].splitlines()[:2])))
        if "gamemode" in changed:
            p.set("gamemode", srv.gamemode_value(state["gamemode"], v))
        if "difficulty" in changed:
            p.set("difficulty", srv.difficulty_value(state["difficulty"], v))
        saver = self.memory_saver.isChecked()
        if saver and not self.meta.memory_saver:
            # remember what to go back to when it's turned off
            self.meta.saved_distances = {"view-distance": str(self._distances_before[0]),
                                         "simulation-distance": str(self._distances_before[1])}
        elif not saver:
            self.meta.saved_distances = {}
        self.meta.memory_saver = saver
        for key in list(self._spins()) + list(self.checks):
            if key in changed:
                p.set(key, state[key])
        if "white-list" in changed:
            p.set("enforce-whitelist", state["white-list"])
        p.save()
        self.meta.name = name
        if "_ram" in changed:  # untouched: keep odd values like 1536 MB exactly
            self.meta.ram_mb = self.ram.value() * 1024
        if "_autosave" in changed:
            self.meta.autosave_minutes = int(self.autosave.currentData() or 0)
        self.meta.save()
        srv.write_start_scripts(self.meta)
        if self.running and "white-list" in changed:
            # a running server keeps its own whitelist switch (and writes it back): change it now
            self.runner.send(self.key, "whitelist on" if state["white-list"] else "whitelist off")
        self._loaded = state
        self._update_save_bar()
        self.on_changed()
        QMessageBox.information(self, t("Save"), t("Saved.") + ("\n" + t("Restart the server to apply.") if self.running else ""))


# ===================================================================== world


class WorldTab(ServerTab):
    """World and server version. Shown inside the Settings tab (embedded=True)."""

    def __init__(self, runner, on_changed, embedded: bool = False):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        layout.addWidget(hint(t("The buttons below run right away. The current world is backed up first.")))
        self.running_notice = warn_label(t("Stop the server to change the world or update it."))
        layout.addWidget(self.running_notice)

        box = QGroupBox(t("Current world"))
        box.setProperty("first", True)
        form = form_layout(box)
        self.info_seed = QLabel()
        self.info_seed.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_type = QLabel()
        self.info_exists = QLabel()
        form.addRow(t("Seed"), self.info_seed)
        form.addRow(t("World type"), self.info_type)
        form.addRow(t("Status"), self.info_exists)
        layout.addWidget(box)

        self.upgrade = UpgradeSection(runner, on_changed)
        layout.addWidget(self.upgrade)

        box = QGroupBox(t("New world (current one is backed up)"))
        v = QVBoxLayout(box)
        self.mode_group = QButtonGroup(self)
        self.rb_random = QRadioButton(t("Random world"))
        self.rb_seed = QRadioButton(t("From seed"))
        self.rb_random.setChecked(True)
        self.mode_group.addButton(self.rb_random, 0)
        self.mode_group.addButton(self.rb_seed, 1)
        v.addWidget(self.rb_random)
        v.addWidget(self.rb_seed)
        row = QHBoxLayout()
        self.seed = QLineEdit(placeholderText=t("Seed"))
        dice = QPushButton(t("Random"))
        dice.clicked.connect(lambda: (self.rb_seed.setChecked(True), self.seed.setText(random_seed())))
        row.addSpacing(24)
        row.addWidget(self.seed, 1)
        row.addWidget(dice)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("World type")))
        self.level_type = QComboBox()
        for k, label in srv.LEVEL_TYPES:
            self.level_type.addItem(t(label), k)
        row.addWidget(self.level_type, 1)
        v.addLayout(row)
        self.btn_new = QPushButton(t("Replace with new world"))
        self.btn_new.clicked.connect(self._new_world)
        v.addWidget(self.btn_new, 0, Qt.AlignLeft)
        self.mode_group.idToggled.connect(lambda *_: self.seed.setEnabled(self.rb_seed.isChecked()))
        self.seed.setEnabled(False)
        layout.addWidget(box)

        box = QGroupBox(t("Import world"))
        v = QVBoxLayout(box)
        v.addWidget(hint(t(
            "Singleplayer worlds are in .minecraft/saves. Choose the folder with level.dat, or a zip.")))
        row = QHBoxLayout()
        self.btn_import_dir = QPushButton(t("From folder..."))
        self.btn_import_dir.clicked.connect(self._import_dir)
        self.btn_import_zip = QPushButton(t("From zip..."))
        self.btn_import_zip.clicked.connect(self._import_zip)
        row.addWidget(self.btn_import_dir)
        row.addWidget(self.btn_import_zip)
        row.addStretch()
        v.addLayout(row)
        layout.addWidget(box)

        box = QGroupBox(t("Backups"))
        v = QVBoxLayout(box)
        self.backup_info = hint("")
        v.addWidget(self.backup_info)
        row = QHBoxLayout()
        self.btn_backup = QPushButton(t("Back up now"))
        self.btn_backup.clicked.connect(self._backup)
        open_btn = set_kind(QPushButton(t("Open backups folder")), "ghost")
        open_btn.clicked.connect(lambda: open_path(self.meta.folder / srv.BACKUP_DIR))
        row.addWidget(self.btn_backup)
        row.addWidget(open_btn)
        row.addStretch()
        v.addLayout(row)
        layout.addWidget(box)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if embedded:  # the Settings tab already scrolls
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            outer.addWidget(body)
        else:
            outer.addWidget(_scroll(body))

    def forget_server(self) -> None:
        super().forget_server()
        self._shown_for = None
        self.upgrade.forget_server()

    def refresh(self):
        if not self.meta:
            return
        p = self.meta.properties()
        level = p.get("level-name") or "world"
        seed = p.get("level-seed") or ""
        self.info_seed.setText(seed or t("(random)"))
        lt = srv.parse_level_type(p.get("level-type"))
        self.info_type.setText(t(dict(srv.LEVEL_TYPES)[lt]))
        if getattr(self, "_shown_for", None) != self.meta.folder:  # another server: start its choices fresh
            self._shown_for = self.meta.folder
            self.level_type.setCurrentIndex(self.level_type.findData(lt))
            self.rb_random.setChecked(True)
            self.seed.clear()
        exists = (self.meta.folder / level / "level.dat").exists()
        self.info_exists.setText(t("Generated") if exists else t("Not yet (created on first start)"))
        backups = srv.list_backups(self.meta)
        self.backup_info.setText(
            t("{n} backups", n=len(backups)) + (f" · {t('latest')}: {backups[0].name}" if backups else "")
        )
        running = self.locked
        self.running_notice.setVisible(running)
        for w in (self.btn_new, self.btn_import_dir, self.btn_import_zip, self.btn_backup):
            w.setEnabled(not running)
        self.upgrade.set_server(self.meta)

    def _confirm(self, text: str) -> bool:
        return QMessageBox.question(
            self, t("Replace world"), text + "\n\n" + t("The current world is backed up first.")
        ) == QMessageBox.Yes

    def _new_world(self):
        seed = self.seed.text().strip() if self.rb_seed.isChecked() else ""
        if self.rb_seed.isChecked() and not seed:
            QMessageBox.warning(self, t("New world"), t("Enter a seed or press Random."))
            return
        if not self._confirm(t("Delete the current world and create a new one?")):
            return
        meta, lt = self.meta, self.level_type.currentData()
        self.run_task(t("New world"), lambda task: srv.regenerate_world(meta, seed, lt, task))
        self.refresh()

    def _import(self, path: str):
        try:
            srv.find_world_root(path)
        except srv.ServerError as e:
            QMessageBox.warning(self, t("Import world"), str(e))
            return
        if not self._confirm(t("Replace the world with '{name}'?", name=Path(path).name)):
            return
        meta = self.meta
        self.run_task(t("Import world"), lambda task: srv.replace_world_with_import(meta, Path(path), task))
        self.refresh()

    def _import_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("Choose a world folder (with level.dat)"))
        if d:
            self._import(d)

    def _import_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, t("Choose a world zip"), "", "Zip (*.zip)")
        if f:
            self._import(f)

    def _backup(self):
        meta = self.meta
        try:
            worlds = srv.world_dirs(meta)
        except srv.ServerError as e:
            QMessageBox.warning(self, t("Backups"), str(e))
            return
        if not any(d.exists() for d in worlds):
            QMessageBox.information(self, t("Backups"), t("There is no world yet."))
            return
        self.run_task(t("Backups"), lambda task: srv.backup_server(meta, "world", worlds_only=True, task=task))
        self.refresh()


# =================================================================== network


def mask_address(text: str) -> str:
    """'203.0.113.5:25570' -> '•••.•.•••.•:25570' (the port isn't private)."""
    m = re.fullmatch(r"([^:]*?)(\s*:\s*\d{1,5})?", text)  # no match for IPv6: mask it all
    host, port = (m.group(1), m.group(2) or "") if m else (text, "")
    return re.sub(r"[^.]", "•", host) + port


class ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AddressRow(QWidget):
    def __init__(self, title: str, sub: str, private: bool = False):
        super().__init__()
        self._text = "-"
        self._real = False  # a real address (not "-" or "Checking...")
        self._private = private
        self._shown = not private  # private addresses start hidden (screen sharing, streaming)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("ItemName")
        title_label.setToolTip(sub)  # who the address is for: in the section's (?) and on hover
        col.addWidget(title_label)
        self.badge = QLabel()  # "Send this to friends": the one address that works for them now
        self.badge.setVisible(False)
        col.addWidget(self.badge)
        row.addLayout(col, 1)
        self._blur_anim = None
        self.value = ClickLabel("-")
        self.value.setObjectName("Address")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.value)
        self.show_btn = None
        if private:  # click the address (or Show) to show it, again to blur it
            self.value.setCursor(Qt.PointingHandCursor)
            self.value.clicked.connect(self._toggle_shown)
            self.show_btn = set_kind(QPushButton(t("Show")), "ghost")  # reachable with the keyboard too
            self.show_btn.setAccessibleName(f"{t('Show')} — {title}")
            self.show_btn.clicked.connect(self._toggle_shown)
            row.addWidget(self.show_btn)
        self.copy = QPushButton(t("Copy"))
        self.copy.setAccessibleName(f"{t('Copy')} — {title}")  # several Copy buttons: say which address
        self.copy.clicked.connect(self._copy)
        row.addWidget(self.copy)
        if private:
            self._render()

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text)  # always the real address, even while hidden
        self.copy.setText(t("Copied"))
        QTimer.singleShot(1200, lambda: self.copy.setText(t("Copy")))

    BLUR = 24  # strong enough that the digits can't be read, even zoomed in

    def _toggle_shown(self):
        if not self._real:
            return
        self._shown = not self._shown
        self._render(animate=True)

    def _blur(self) -> QGraphicsBlurEffect:
        blur = self.value.graphicsEffect()
        if not isinstance(blur, QGraphicsBlurEffect):
            blur = QGraphicsBlurEffect(self.value)
            blur.setBlurHints(QGraphicsBlurEffect.QualityHint)
            blur.setBlurRadius(0)
            self.value.setGraphicsEffect(blur)
        return blur

    def _render(self, animate: bool = False):
        hide = self._private and not self._shown and self._real
        self.value.setText(self._text)
        if self.show_btn is not None:
            self.show_btn.setText(t("Show") if hide else t("Hide"))
            self.show_btn.setVisible(self._real)
        if self._blur_anim is not None:
            self._blur_anim.stop()
            self._blur_anim = None
        # blurred, not replaced: the layout stays the same and it looks tidy
        if animate and anim.enabled():  # the blur melts away / fogs over instead of jumping
            blur = self._blur()
            fade = QVariantAnimation(self)
            fade.setDuration(220)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            fade.setStartValue(float(blur.blurRadius()))
            fade.setEndValue(float(self.BLUR if hide else 0))
            fade.valueChanged.connect(lambda r, b=blur: b.setBlurRadius(r))
            def done(fade=fade, hide=hide):
                if self._blur_anim is fade:
                    self._blur_anim = None
                    if not hide:  # fully sharp at the end: drop the effect so the text renders crisply
                        self.value.setGraphicsEffect(None)

            fade.finished.connect(done)
            self._blur_anim = fade
            fade.start()
        elif hide:
            self._blur().setBlurRadius(self.BLUR)
        else:
            self.value.setGraphicsEffect(None)
        # private rows aren't selectable: a click toggles them (Copy is there for copying)
        self.value.setTextInteractionFlags(Qt.NoTextInteraction if self._private else Qt.TextSelectableByMouse)
        if self._private:
            self.value.setToolTip(t("Click to show the address") if hide else
                                  (t("Click to hide the address") if self._real else ""))

    def set_badge(self, on: bool):
        if on:
            self.badge.setText(f"<span style='color:{theme.C['ok']}'>● {html.escape(t('Send this to friends'))}</span>")
            self.badge.setStyleSheet("font-size: 9pt;")
        self.badge.setVisible(on)

    @property
    def text(self) -> str:
        return self._text if self._real else ""

    def set(self, text: str, enabled: bool = True):
        self._text, self._real = text, enabled and text not in ("", "-")
        self.copy.setEnabled(enabled)
        self._render()


class NetworkTab(ServerTab):
    friend_changed = Signal(str, str)  # the address for friends and its kind: tunnel / internet / lan
    _public_ip = None  # looked up once per app run
    _ip_lookup = False  # a lookup is running
    tunnel = None  # TunnelManager, set by the main window

    def set_tunnel(self, manager):
        self.tunnel = manager
        manager.changed.connect(self._refresh_tunnel)
        self._refresh_tunnel()

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box, v = help_section(t("Addresses"), t(
            "Give friends the address that fits where they are:\n"
            "• This PC: playing on this computer\n"
            "• Same Wi-Fi: people in the same home\n"
            "• Internet: friends in other homes (the port must be open, or use the tunnel)\n"
            "• Bedrock: phone / console players, address + port\n\n"
            "Blurred addresses are private: click one to show it, click again to hide it. "
            "Copy always copies the real address."), first=True)
        self.addr_local = AddressRow(t("This PC"), t("Playing on this computer"))
        self.addr_lan = AddressRow(t("Same Wi-Fi"), t("People in the same home"), private=True)
        self.addr_public = AddressRow(t("Internet"), t("Friends in other homes"), private=True)
        self.addr_bedrock = AddressRow(t("Bedrock (Internet)"), t("Phone / console players: address + port"),
                                       private=True)
        for w in (self.addr_local, self.addr_lan, self.addr_public, self.addr_bedrock):
            v.addWidget(w)
        # one button for the whole invitation (game version, address, "only while the PC is on")
        self.btn_invite = QPushButton(t("Copy invitation"))
        self.btn_invite.setToolTip(t("Copies how to join (game version and the address marked for friends), "
                                     "ready to paste into a chat."))
        self.btn_invite.clicked.connect(self.copy_invite)
        v.itemAt(0).layout().addWidget(self.btn_invite)
        layout.addWidget(box)

        # friends elsewhere: either the playit.gg tunnel or a router port, one at a time on screen
        box, sec = help_section(t("Open to the internet"), t(
            "Friends who aren't on your Wi-Fi reach the server over the internet. One of the two ways is enough.\n\n"
            "playit.gg tunnel (recommended): free, no router settings, works in dorms, offices and on hotspots. "
            "It adds a little latency.\n"
            "1. Press Start tunnel. The playit.gg agent is downloaded and started automatically.\n"
            "2. First time only: a browser page opens. Sign in to playit.gg (or continue as a guest) "
            "and approve this PC.\n"
            "3. On the playit.gg dashboard add a tunnel: type Minecraft Java, local port = this server's "
            "port (usually 25565). Bedrock players: also a Minecraft Bedrock tunnel (local port 19132).\n"
            "4. After a few seconds the tunnel address appears. If it doesn't, copy it from the dashboard "
            "and use Enter address.\n\n"
            "Router port: the lowest latency. Most routers open the port automatically (UPnP); otherwise "
            "set up port forwarding on the router. Allow in Windows Firewall lets other devices through "
            "this PC's firewall; the rules only matter while the server runs."))
        sec.addWidget(hint(t("Lets friends who aren't on your Wi-Fi join. One of the two is enough.")))
        seg = QHBoxLayout()
        seg.setSpacing(18)
        self.way_group = QButtonGroup(self)
        self.way_tunnel = set_kind(QPushButton(t("playit.gg tunnel (recommended)")), "segment")
        self.way_router = set_kind(QPushButton(t("Open a router port")), "segment")
        for i, b in enumerate((self.way_tunnel, self.way_router)):
            b.setCheckable(True)
            self.way_group.addButton(b, i)
            seg.addWidget(b)
        seg.addStretch()
        sec.addLayout(seg)
        self.way_group.idClicked.connect(self._show_way)
        self.way_stack = QStackedWidget()
        sec.addWidget(self.way_stack)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(10)
        self.way_stack.addWidget(page)
        self.tunnel_status = QLabel()
        self.tunnel_status.setWordWrap(True)
        self.tunnel_status.setTextFormat(Qt.RichText)
        self.tunnel_status.setOpenExternalLinks(True)
        v.addWidget(self.tunnel_status)
        self.addr_tunnel = AddressRow(t("Tunnel address"), t("Give this to friends (Java Edition)"), private=True)
        v.addWidget(self.addr_tunnel)
        row = QHBoxLayout()
        self.btn_tunnel = set_kind(QPushButton(), "primary")
        self.btn_tunnel.clicked.connect(self._toggle_tunnel)
        dash = set_kind(QPushButton(t("Open playit.gg dashboard")), "ghost")
        dash.clicked.connect(lambda: self.tunnel and self.tunnel.open_dashboard())
        edit = set_kind(QPushButton(t("Enter address...")), "ghost")
        edit.setToolTip(t("If the address isn't detected, copy it from the playit.gg dashboard."))
        edit.clicked.connect(self._edit_tunnel_address)
        log_btn = set_kind(QPushButton(t("Agent log")), "ghost")
        log_btn.clicked.connect(self._show_tunnel_log)
        for w in (self.btn_tunnel, dash, edit, log_btn):
            row.addWidget(w)
        row.addStretch()
        v.addLayout(row)
        self.auto_tunnel = QCheckBox(t("Start the tunnel together with this server"))
        self.auto_tunnel.toggled.connect(self._toggle_auto_tunnel)
        v.addWidget(self.auto_tunnel)
        v.addStretch()

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(10)
        self.way_stack.addWidget(page)
        # no router at all (a public address on this PC) or the provider's shared address:
        # say so first, the router steps below don't apply
        self.direct_note = QLabel()
        self.direct_note.setWordWrap(True)
        self.direct_note.setTextFormat(Qt.RichText)
        self.direct_note.setVisible(False)
        sec.insertWidget(sec.indexOf(self.way_stack) - 1, self.direct_note)
        self.port_status = QLabel()
        self.port_status.setWordWrap(True)
        v.addWidget(self.port_status)
        row = QHBoxLayout()
        self.btn_open = QPushButton(t("Open port automatically (UPnP)"))
        self.btn_open.clicked.connect(self._open_port)
        self.btn_close = set_kind(QPushButton(t("Close port")), "ghost")
        self.btn_close.clicked.connect(self._close_port)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_close)
        if os.name == "nt":
            fw = QPushButton(t("Allow in Windows Firewall"))
            fw.setToolTip(t("Shows an administrator prompt."))
            fw.clicked.connect(self._firewall)
            row.addWidget(fw)
        row.addStretch()
        v.addLayout(row)
        self.fw_status = QLabel()
        self.fw_status.setWordWrap(True)
        self.fw_status.setVisible(os.name == "nt")
        v.addWidget(self.fw_status)
        self._fw_busy = False
        self._fw_for = None
        self.auto_upnp = QCheckBox(t("Open the port every time the server starts"))
        self.auto_upnp.toggled.connect(self._toggle_auto)
        v.addWidget(self.auto_upnp)
        # one button that gathers everything someone helping needs, ready to paste in a chat
        diag_row = QHBoxLayout()
        self.btn_diag = QPushButton(t("Copy diagnostic info"))
        self.btn_diag.setToolTip(t("Checks the router, firewall, tunnel and ports, then copies a summary to paste "
                                   "into a chat. Internet addresses are partly hidden."))
        self.btn_diag.clicked.connect(self._copy_diagnostics)
        diag_row.addWidget(self.btn_diag)
        self.diag_status = QLabel()
        self.diag_status.setWordWrap(True)
        diag_row.addWidget(self.diag_status, 1)
        sec.addLayout(diag_row)
        # the manual steps are long: folded away until asked for
        self.btn_manual = set_kind(QPushButton(), "ghost")
        self.btn_manual.setCheckable(True)
        self.btn_manual.setStyleSheet("QPushButton { padding-left: 0; text-align: left; }")
        self.btn_manual.toggled.connect(self._show_manual)
        v.addWidget(self.btn_manual, 0, Qt.AlignLeft)
        self.manual_box = QWidget()
        mv = QVBoxLayout(self.manual_box)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(10)
        # 1) find the router: its address, brand, and where its web page really answers
        self.router_status = QLabel()
        self.router_status.setWordWrap(True)
        self.router_status.setTextFormat(Qt.RichText)
        mv.addWidget(self.router_status)
        row = QHBoxLayout()
        self.btn_admin = set_kind(QPushButton(t("Open the router page")), "primary")
        self.btn_admin.clicked.connect(self._open_admin)
        self.btn_router = QPushButton(t("Find the router again"))
        self.btn_router.clicked.connect(self._check_router)
        row.addWidget(self.btn_admin)
        row.addWidget(self.btn_router)
        row.addStretch()
        mv.addLayout(row)
        # 2) the steps, with this router's menu when known
        self.manual = QLabel()
        self.manual.setWordWrap(True)
        self.manual.setTextFormat(Qt.RichText)
        self.manual.setOpenExternalLinks(True)
        self.manual.setTextInteractionFlags(Qt.TextBrowserInteraction)
        mv.addWidget(self.manual)
        # 3) check from outside that it worked
        row = QHBoxLayout()
        self.btn_check_port = QPushButton(t("Check the port from outside"))
        self.btn_check_port.clicked.connect(self._check_port)
        row.addWidget(self.btn_check_port)
        self.port_check_status = QLabel()
        self.port_check_status.setWordWrap(True)
        row.addWidget(self.port_check_status, 1)
        mv.addLayout(row)
        v.addWidget(self.manual_box)
        self._router = None  # network.RouterCheck
        self._router_busy = False
        self._show_manual(False)
        layout.addWidget(box)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

    def forget_server(self) -> None:
        super().forget_server()
        self._status_key = None
        self._fw_for = None
        self._way_for = None

    # ------------------------------------------------------- open to the internet

    _internet_ok: dict = {}  # server folder -> the router port was opened / reached from outside

    def _show_way(self, index: int):
        self.way_group.button(index).setChecked(True)

        def switch():
            self.way_stack.setCurrentIndex(index)
            for i in range(self.way_stack.count()):  # the stack is as tall as the page shown, not the tallest
                self.way_stack.widget(i).setSizePolicy(
                    QSizePolicy.Preferred, QSizePolicy.Preferred if i == index else QSizePolicy.Ignored)
            self.way_stack.adjustSize()
        if anim.enabled() and self.isVisible() and self.way_stack.currentIndex() != index:
            anim.crossfade(self.way_stack.parentWidget(), switch, ms=anim.FAST)
        else:
            switch()

    def _friend(self):
        """(row, address, kind) of the address friends should use right now."""
        tm = self.tunnel
        if tm and tm.is_active() and tm.address:
            return self.addr_tunnel, tm.address, "tunnel"
        kind = self._router.kind if self._router else network.connection_kind(network.lan_ip())
        if self.addr_public.text and (NetworkTab._internet_ok.get(self.key) or kind == "direct"):
            return self.addr_public, self.addr_public.text, "internet"
        return self.addr_lan, self.addr_lan.text, "lan"

    def _update_friend(self):
        if not self.meta:
            return
        row, address, kind = self._friend()
        for r in (self.addr_lan, self.addr_public, self.addr_tunnel):
            r.set_badge(r is row and bool(address))
        if (address, kind) != getattr(self, "_friend_sent", None):
            self._friend_sent = (address, kind)
            self.friend_changed.emit(address, kind)

    def invitation(self) -> str:
        _row, address, kind = self._friend()
        if not address:
            return ""
        text = t("How to join: Minecraft Java {v} → Multiplayer → Add Server\nAddress: {addr}",
                 v=self.meta.mc_version, addr=address)
        if kind == "lan":
            text += "\n" + t("(Works on the same Wi-Fi only.)")
        return text + "\n" + t("You can join only while the server PC is on.")

    def copy_invite(self):
        text = self.invitation()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.btn_invite.setText(t("Copied"))
        QTimer.singleShot(1200, lambda: self.btn_invite.setText(t("Copy invitation")))

    def _show_manual(self, on: bool):
        self.btn_manual.setText(t("If automatic doesn't work") + ("  ▴" if on else "  ▾"))
        if on and anim.enabled():
            anim.crossfade(self.manual_box.parentWidget(), lambda: self.manual_box.setVisible(True), ms=anim.FAST)
        else:
            self.manual_box.setVisible(on)
        if on and self._router is None:
            self._check_router()  # the first time it's opened: find the router right away

    # ------------------------------------------------------- manual forwarding

    def _check_router(self):
        if self._router_busy:
            return
        self._router_busy = True
        self.btn_router.setEnabled(False)
        self.btn_admin.setEnabled(False)
        set_status(self.router_status, "wait", t("Looking for the router..."))

        def done(res):
            self._router_busy = False
            self._router = res
            self.btn_router.setEnabled(True)
            self._render_router()
            self._render_manual()

        def fail(msg):
            self._router_busy = False
            self.btn_router.setEnabled(True)
            set_status(self.router_status, "fail", msg)

        run_async(lambda task: network.check_router(), done, fail)

    def _render_router(self):
        r = self._router
        if r is None:
            return
        esc = html.escape
        if not r.gateway:
            set_status(self.router_status, "fail", t(
                "No router found. Is this PC connected by Wi-Fi or cable to a home router?"))
            self.btn_admin.setEnabled(False)
            return
        self._render_kind(r.kind)
        if r.kind == "direct":
            set_status(self.router_status, "ok", t(
                "No router: this PC has a public internet address. There's nothing to forward."), rich=True)
            self.btn_admin.setEnabled(False)
            return
        name = esc(r.brand) if r.brand else esc(t("Router"))
        lines = [t("{name} at <b>{ip}</b>", name=name, ip=esc(r.gateway))]
        admin = r.upnp_admin or (r.admin_urls[0] if r.admin_urls else "")
        if r.admin_urls:
            lines.append(t("Its settings page answers at {urls}.", urls=", ".join(
                f"<a href='{esc(u)}'>{esc(u)}</a>" for u in r.admin_urls)))
        elif not r.upnp_admin:
            lines.append(t(
                "It has no web settings page on the usual ports. Some routers (mesh Wi-Fi, some internet "
                "provider models) are set up only with their phone app: look for Port forwarding there."))
        state = "ok"
        if r.double_nat:
            state = "warn"
            lines.append(t(
                "<b>There's another router in front of this one</b> (its internet address is {wan}). "
                "Forward the port on that device too, first to this router's address, or use the tunnel. "
                "If it's your internet provider's network (carrier NAT), forwarding can't work: use the tunnel.",
                wan=esc(network.mask_ip(r.wan_ip))))
        set_status(self.router_status, state, "<br>".join(lines), rich=True)
        self.btn_admin.setEnabled(bool(admin))
        self.btn_admin.setToolTip(admin)

    def _open_admin(self):
        r = self._router
        url = r and (r.upnp_admin or (r.admin_urls[0] if r.admin_urls else ""))
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _render_manual(self):
        if not self.meta:
            return
        udp = plugins.udp_ports(self.meta)
        ports = f"TCP {self.port}" + "".join(f", UDP {u}" for u in udp)
        r = self._router
        if r is not None and r.kind == "direct":
            self.manual.setText(NetworkTab._direct_text())
            return
        guides = {
            "iptime": t("ipTIME: Admin tools → Advanced setup → NAT/Router management → Port forward setup"),
            "kt": t("KT: Device settings → Traffic management → Port forwarding"),
            "skb": t("SK broadband: Advanced setup → NAT → Port forwarding"),
            "lgu": t("LG U+: Network settings → NAT settings → Port forwarding"),
            "asus": t("ASUS: WAN → Virtual Server / Port Forwarding"),
            "tplink": t("TP-Link: Advanced → NAT Forwarding → Virtual Servers"),
            "netgear": t("NETGEAR: Advanced → Advanced Setup → Port Forwarding / Port Triggering"),
            "mesh_app": t("This kind of router is set up in its phone app: look for Port forwarding (Advanced networking)."),
        }
        where = guides.get(r.guide_key if r else "", "") or t("Port Forwarding (also called NAT, Virtual Server or Port mapping)")
        self.manual.setText(t(
            "<ol style='margin-left:-20px'>"
            "<li>Press <b>Open the router page</b> and sign in. The password is often on a sticker under the router.</li>"
            "<li>Go to: <b>{where}</b>.</li>"
            "<li>Add a rule: internal IP = this PC (<b>{lan}</b>), ports <b>{ports}</b> (the same number outside and inside).</li>"
            "<li>Save, start the server, then press <b>Check the port from outside</b>.</li></ol>"
            "<p>Can't forward ports (carrier NAT, dorm or office Wi-Fi, hotspot)? Use the tunnel above.</p>",
            where=html.escape(where), ports=ports,
            lan=html.escape(r.lan_ip) if r and r.lan_ip else t("the 'Same Wi-Fi' address above"),
        ))

    def _copy_diagnostics(self):
        if not self.meta:
            return
        meta, port, running = self.meta, self.port, self.running
        udp = plugins.udp_ports(meta)
        java = java_exe(meta)
        tm = self.tunnel
        tunnel_state = tm.state if tm else "off"
        tunnel_addr = bool(tm and tm.address)
        self.btn_diag.setEnabled(False)
        set_status(self.diag_status, "wait", t("Checking... (about 10 seconds)"))

        def work(task):
            r = network.check_router()
            res = {"router": r}
            res["firewall"] = network.firewall_status(port, java) if os.name == "nt" else "-"
            res["local"] = joincheck.server_list_ping("127.0.0.1", port) if running else None
            if running and r.public_ip:
                res["internet"] = joincheck.external_check(f"{r.public_ip}:{port}")
            return res

        def done(res):
            self.btn_diag.setEnabled(True)
            text = self._diagnostics_text(meta, port, udp, running, tunnel_state, tunnel_addr, res)
            QGuiApplication.clipboard().setText(text)
            self._router = res["router"]  # the manual section can use it too
            self._render_router()
            self._render_manual()
            set_status(self.diag_status, "ok", t("Copied! Paste it into the chat (Ctrl+V)."))

        def fail(msg):
            self.btn_diag.setEnabled(True)
            set_status(self.diag_status, "fail", msg)

        run_async(work, done, fail)

    @staticmethod
    def _diagnostics_text(meta, port, udp, running, tunnel_state, tunnel_addr, res) -> str:
        import platform

        from mc_server_maker import APP_VERSION

        r = res["router"]
        yes, no, unknown = t("yes"), t("no"), t("unknown")

        def check(c):
            if c is None:
                return t("not checked (server is off)")
            return t("OK") if c.ok else t("failed") + (f" ({c.error})" if c.error else "")

        lines = [
            f"[Bartizan {APP_VERSION} - " + t("network diagnostics") + "]",
            f"OS: {platform.system()} {platform.release()} ({platform.version()})",
            t("Server") + f": {meta.software_name} {meta.mc_version} · " + t("port") + f" TCP {port}"
            + "".join(f", UDP {u}" for u in udp) + " · " + (t("running") if running else t("stopped")),
            t("Connection") + ": " + {"direct": t("direct, no router (public address on this PC)"),
                                      "carrier": t("internet provider's shared address (carrier NAT)"),
                                      }.get(r.kind, t("through a router")),
            # a public address here would identify the person: hide it like the others
            t("This PC (LAN IP)") + f": {network.hide_public(r.lan_ip) if r.lan_ip else unknown}",
            t("Default gateway") + f": {network.hide_public(r.gateway) if r.gateway else unknown}",
            t("Router model") + f": {r.brand or unknown}",
            t("Router settings page") + ": " + (", ".join(r.admin_urls) or r.upnp_admin or t("no answer on usual ports"))
            .replace(r.gateway or "\0", network.hide_public(r.gateway or "")),
            t("UPnP router found") + f": {yes if r.wan_ip else no}",
            t("Router internet IP") + f": {network.mask_ip(r.wan_ip) if r.wan_ip else unknown}"
            + (f" ({t('private')})" if r.wan_ip and not network.is_public(r.wan_ip) else ""),
            t("Public IP") + f": {network.mask_ip(r.public_ip) if r.public_ip else unknown}",
            t("Another router/modem in front (double NAT)") + f": {yes if r.double_nat else (no if r.wan_ip else unknown)}",
            t("Windows Firewall") + f": {res.get('firewall', '-')}",
            t("Tunnel (playit.gg)") + f": {tunnel_state}" + (", " + t("address known") if tunnel_addr else ""),
            t("Join from this PC") + f": {check(res.get('local'))}",
            t("Join from the internet") + f": {check(res.get('internet')) if running and r.public_ip else t('not checked')}",
        ]
        return "\n".join(lines)

    def _check_port(self):
        if not self.meta:
            return
        if not self.running:
            set_status(self.port_check_status, "off", t("Start the server first: only a running server can answer."))
            return
        port, key = self.port, self.key
        set_status(self.port_check_status, "wait", t("Checking from outside..."))
        self.btn_check_port.setEnabled(False)

        def work(task):
            ip = network.public_ip()
            return joincheck.external_check(f"{ip}:{port}")

        def done(res):
            self.btn_check_port.setEnabled(True)
            if key != self.key:
                return
            if res.ok:
                set_status(self.port_check_status, "ok", t("Open! Friends can join with the Internet address."))
                NetworkTab._internet_ok[key] = True
                self._update_friend()
            elif res.error != "offline":
                set_status(self.port_check_status, "off", t("Couldn't check (no internet?)"))
            else:
                set_status(self.port_check_status, "fail", t(
                    "Not reachable yet. Check the rule (IP and port), Windows Firewall, and that no other router is "
                    "in front. The check service can lag a few minutes."))

        def fail(msg):
            self.btn_check_port.setEnabled(True)
            set_status(self.port_check_status, "fail", msg)

        run_async(work, done, fail)

    @property
    def port(self) -> int:
        return self.runner.port(self.key, self.meta) if self.meta else 25565

    def showEvent(self, event):
        super().showEvent(event)
        if self.meta and self._fw_for != self.key:  # once per server while the tab is open
            self._fw_for = self.key
            self._check_firewall()

    def _fmt(self, host: str) -> str:
        return host if self.port == 25565 else f"{host}:{self.port}"

    def refresh(self):
        if not self.meta:
            return
        lan = network.lan_ip()
        self.addr_local.set(self._fmt("localhost"))
        self.addr_lan.set(self._fmt(lan))
        udp = plugins.udp_ports(self.meta)
        self.addr_bedrock.setVisible(bool(udp))
        if NetworkTab._public_ip:
            self._show_public(NetworkTab._public_ip)
        else:
            self.addr_public.set(t("Checking..."), False)
            self.addr_bedrock.set(t("Checking..."), False)
            if not NetworkTab._ip_lookup:  # one lookup at a time, however often we refresh
                NetworkTab._ip_lookup = True
                run_async(lambda task: network.public_ip(), self._got_public_ip, self._no_public_ip)
        self.auto_upnp.blockSignals(True)
        self.auto_upnp.setChecked(self.meta.upnp)
        self.auto_upnp.blockSignals(False)
        self.auto_tunnel.blockSignals(True)
        self.auto_tunnel.setChecked(self.meta.tunnel)
        self.auto_tunnel.blockSignals(False)
        if self.tunnel:
            self.tunnel.set_server_port(self.port)  # several tunnels: show the one for this server
        self._refresh_tunnel()
        if self.key != getattr(self, "_status_key", None):  # another server: its own port status
            self._status_key = self.key
            self.port_status.clear()
        if not self.port_status.text():
            set_status(self.port_status, "off", t("Port not opened yet."))
        self.port_check_status.clear()
        self._render_kind(self._router.kind if self._router else network.connection_kind(network.lan_ip()))
        self._render_manual()
        if self.key != getattr(self, "_way_for", None):  # another server: the way it uses
            self._way_for = self.key
            use_router = self.meta.upnp and not self.meta.tunnel and not (self.tunnel and self.tunnel.is_active())
            self._show_way(1 if use_router else 0)
        self._update_friend()

    def _render_kind(self, kind: str):
        if kind == "direct":
            set_status(self.direct_note, "ok", NetworkTab._direct_text(), rich=True)
        elif kind == "carrier":
            set_status(self.direct_note, "warn", t(
                "<b>This connection uses an address shared by your internet provider</b> (carrier NAT, common "
                "with phone hotspots). Friends from other homes can't reach it directly and port forwarding "
                "can't work: use the <b>tunnel</b> above."), rich=True)
        self.direct_note.setVisible(kind in ("direct", "carrier"))

    @staticmethod
    def _direct_text() -> str:
        return t(
            "<b>This PC is connected to the internet directly, without a router.</b> No port forwarding is "
            "needed: friends join with the <b>Internet</b> address above. If they can't, check the firewall "
            "of your antivirus (e.g. V3) and that Windows Firewall doesn't \"block all incoming connections\". "
            "If it still doesn't work, the building or provider blocks incoming connections: use the tunnel.")

    def _show_public(self, ip: str):
        self.addr_public.set(self._fmt(ip))
        udp = plugins.udp_ports(self.meta) if self.meta else []
        if udp:
            self.addr_bedrock.set(f"{ip} : {udp[0]}")

    def _no_public_ip(self, _msg: str):
        NetworkTab._ip_lookup = False
        for row in (self.addr_public, self.addr_bedrock):
            row.set(t("Unavailable (offline?)"), False)

    def _got_public_ip(self, ip: str):
        NetworkTab._ip_lookup = False
        NetworkTab._public_ip = ip
        if self.meta:
            self._show_public(ip)

    def _open_port(self):
        port, name, udp = self.port, self.meta.name, plugins.udp_ports(self.meta)
        key = self.key
        set_status(self.port_status, "wait", t("Looking for the router..."))
        self.btn_open.setEnabled(False)

        def done(res):
            self.btn_open.setEnabled(True)
            if key != self.key:
                return  # the user switched servers meanwhile
            if res.cgnat:
                set_status(self.port_status, "warn", t(
                    "Port opened, but the router's internet IP ({ip}) is private. You are probably behind "
                    "carrier NAT, so friends may not get in. See playit.gg below.", ip=mask_address(res.router_ip)))
            else:
                set_status(self.port_status, "ok", t("Port {port} is open! Friends can join with the Internet address.", port=res.port))
                NetworkTab._internet_ok[key] = True
            self.refresh()

        def fail(msg):
            self.btn_open.setEnabled(True)
            if key == self.key:
                set_status(self.port_status, "fail", msg)

        run_async(lambda task: network.open_port(port, f"Minecraft {name}"[:60], udp_ports=udp), done, fail)

    def _close_port(self):
        port, udp, key = self.port, plugins.udp_ports(self.meta), self.key
        set_status(self.port_status, "wait", t("Closing port..."))
        run_async(lambda task: network.close_port(port, udp_ports=udp),
                  lambda _: (NetworkTab._internet_ok.pop(key, None), key == self.key and set_status(
                      self.port_status, "off", t("Port closed.")), self._update_friend()),
                  lambda msg: key == self.key and set_status(self.port_status, "fail", msg))

    # ------------------------------------------------------------ tunnel

    def _refresh_tunnel(self):
        tm = self.tunnel
        if not tm:
            return
        from mc_server_maker.gui import tunnel_manager as tmod

        port = self.port
        esc = html.escape
        texts = {
            tmod.OFF: ("off", esc(t("Tunnel is off."))),
            tmod.INSTALLING: ("wait", esc(t("Downloading the playit.gg agent..."))),
            tmod.STARTING: ("wait", esc(t("Starting the tunnel..."))),
            tmod.WAITING_CLAIM: ("warn", t(
                "First time only: in the browser page that opened, sign in to playit.gg and approve this PC. "
                "Then add a tunnel: <b>Minecraft Java</b>, local port <b>{port}</b>. "
                "(Bedrock players: also add a <b>Minecraft Bedrock</b> tunnel, port <b>19132</b>.)", port=port)
                + (f" <a href='{esc(tm.claim_url)}'>{t('Open the link again')}</a>" if tm.claim_url else "")),
            tmod.RUNNING: ("ok", esc(t("Tunnel is running. Friends can join with the tunnel address."))),
            tmod.ERROR: ("fail", esc(tm.error or t("Tunnel error."))),
        }
        state, text = texts.get(tm.state, ("off", ""))
        java_tunnels = [x for x in (tm.tunnels or []) if x.address and not x.disabled
                        and "bedrock" not in x.kind and x.port_type != "udp"]
        for_port = [x for x in java_tunnels if x.local_port in (None, port)]
        if tm.state == tmod.RUNNING and tm.tunnels is not None and java_tunnels and not for_port:
            state, text = "warn", t(
                "No tunnel points to this server's port <b>{port}</b> yet (the existing ones lead to another "
                "server). On the playit.gg dashboard add a tunnel: <b>Minecraft Java</b>, local port <b>{port}</b>.",
                port=port)
        elif tm.state == tmod.RUNNING and tm.tunnels is not None and not java_tunnels:
            # the agent runs, but the playit account has no (working) Minecraft Java tunnel yet
            state, text = "warn", t(
                "The agent is running, but there is no Minecraft Java tunnel yet. On the playit.gg dashboard "
                "add a tunnel: <b>Minecraft Java</b>, local port <b>{port}</b>.", port=port)
        elif port != 25565 and tm.state == tmod.RUNNING:
            text += " " + esc(t("(Make sure the playit tunnel points to local port {port}.)", port=port))
        set_status(self.tunnel_status, state, text, rich=True)
        self.btn_tunnel.setText(t("Stop tunnel") if tm.is_active() else t("Start tunnel"))
        set_kind(self.btn_tunnel, "" if tm.is_active() else "primary")
        self.addr_tunnel.set(tm.address or "-", bool(tm.address))
        self._update_friend()

    def _toggle_tunnel(self):
        if not self.tunnel:
            return
        if self.tunnel.is_active():
            self.tunnel.stop()
        else:
            self.tunnel.start()

    def _edit_tunnel_address(self):
        if not self.tunnel:
            return
        text, ok = QInputDialog.getText(self, t("Tunnel address"), t("Address from the playit.gg dashboard:"),
                                        text=self.tunnel.address)
        if ok:
            self.tunnel.set_address(text, manual=True)

    def _show_tunnel_log(self):
        if not self.tunnel:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Agent log"))
        fit_to_screen(dlg, 640, 400)
        v = QVBoxLayout(dlg)
        view = QPlainTextEdit(readOnly=True)
        view.setObjectName("Console")
        view.setPlainText("\n".join(self.tunnel.log) or t("(empty)"))
        v.addWidget(view)
        dlg.exec()
        dlg.deleteLater()

    def _toggle_auto_tunnel(self, on: bool):
        if self.meta:
            self.meta.tunnel = on
            self.meta.save()

    def _toggle_auto(self, on: bool):
        if self.meta:
            self.meta.upnp = on
            self.meta.save()

    def _firewall(self):
        if not network.allow_firewall(self.port, plugins.udp_ports(self.meta), java_exe(self.meta)):
            QMessageBox.warning(self, t("Firewall"), t("Could not add the firewall rule."))
            return
        set_status(self.fw_status, "wait", t("Waiting for the administrator prompt..."))
        QTimer.singleShot(6000, self._check_firewall)  # the prompt runs on its own: look again shortly
        QTimer.singleShot(20000, self._check_firewall)

    def _check_firewall(self):
        if os.name != "nt" or not self.meta or self._fw_busy:
            return
        self._fw_busy = True
        key, port, java = self.key, self.port, java_exe(self.meta)

        def done(state):
            self._fw_busy = False
            if key != self.key:
                return
            if state == network.BLOCKED:
                set_status(self.fw_status, "fail", t("Windows Firewall blocks Java: other devices can't join. Press 'Allow in Windows Firewall'."))
            elif state == network.ALLOWED:
                set_status(self.fw_status, "ok", t("Windows Firewall lets players in."))
            else:
                set_status(self.fw_status, "off", t("Not allowed in Windows Firewall yet."))

        def fail(_msg):
            self._fw_busy = False

        run_async(lambda task: network.firewall_status(port, java), done, fail)


# ============================================================ plugins / mods


class ToggleSwitch(QAbstractButton):
    """iOS-style on/off switch; the knob slides and the colour blends when it changes."""

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)
        self._pos = 1.0 if checked else 0.0  # 0 = off, 1 = on
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self.animate_to)

    def _set_pos(self, value):
        self._pos = float(value)
        self.update()

    def animate_to(self, on: bool):
        self._anim.stop()
        if not anim.enabled():  # low-resource mode: jump
            self._set_pos(1.0 if on else 0.0)
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(theme.C["surface3"]), QColor(theme.C["accent"])
        k = self._pos
        track = QColor(round(off.red() + (on.red() - off.red()) * k),
                       round(off.green() + (on.green() - off.green()) * k),
                       round(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 11, 11)
        if self.hasFocus():  # keyboard users see where they are
            p.setPen(QPen(QColor(theme.C["text"]), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5), 10.25, 10.25)
            p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        x = 3 + (self.width() - 22) * k
        p.drawEllipse(QPointF(x + 8, 11), 8, 8)


class AddonCard(QFrame):
    def __init__(self, addon, warning: str, on_toggle, on_remove):
        super().__init__()
        self.setObjectName("Card")
        self.addon = addon
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(html.escape(addon.name) + (f"&nbsp;&nbsp;<span style='color:{theme.C['muted']}; font-weight:400'>"
                                                 f"{html.escape(addon.version)}</span>" if addon.version else ""))
        name.setObjectName("ItemName")
        name.setTextFormat(Qt.RichText)
        col.addWidget(name)
        bits = [addon.file_name, stats.human_bytes(addon.size)]
        if addon.authors:
            bits.insert(0, ", ".join(addon.authors[:3]))
        info = hint(" · ".join(bits))
        info.setWordWrap(False)  # one line, so every row has the same height
        col.addWidget(info)
        if warning:
            col.addWidget(warn_label(warning))
        row.addLayout(col, 1)
        self.off_label = hint(t("Off"))  # said in words, not only by fading the row
        self.off_label.setVisible(not addon.enabled)
        row.addWidget(self.off_label)
        self.switch = ToggleSwitch(addon.enabled)
        self.switch.setToolTip(t("On / off"))
        self.switch.setAccessibleName(f"{addon.name} — {t('On / off')}")
        self.switch.toggled.connect(lambda on: on_toggle(self, on))
        row.addWidget(self.switch)
        remove = set_kind(QPushButton(t("Remove")), "ghost")
        remove.clicked.connect(lambda: on_remove(self))
        row.addWidget(remove)
        self.setOpacity(addon.enabled)

    def setOpacity(self, enabled: bool):
        # muted, not "disabled" grey: the row can still be switched back on, so it must stay readable
        self.setStyleSheet("" if enabled else "QLabel { color: %s; }" % theme.C["muted"])
        if hasattr(self, "off_label"):
            self.off_label.setVisible(not enabled)


class DropZone(QFrame):
    def __init__(self, on_files, on_browse, compact: bool = False):
        """compact=True: the text and the button on one line (under the empty-list message)."""
        super().__init__()
        self.setObjectName("DropZone")
        self.on_files = on_files
        self.setAcceptDrops(True)
        v = QHBoxLayout(self) if compact else QVBoxLayout(self)
        if compact:
            v.setContentsMargins(14, 8, 10, 8)
        else:
            v.setContentsMargins(16, 14, 16, 14)
        self.title = QLabel()
        self.title.setObjectName("Muted")
        self.title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft if compact else Qt.AlignCenter)
        v.addWidget(self.title, 1 if compact else 0)
        row = QHBoxLayout()
        row.addStretch()
        browse = QPushButton(t("Choose files..."))
        browse.clicked.connect(on_browse)
        row.addWidget(browse)
        if not compact:
            row.addStretch()
        v.addLayout(row)
        self._set_hover(False)

    def _set_hover(self, hover: bool):
        border = theme.C["accent"] if hover else theme.C["border"]
        bg = theme.C["accent_soft"] if hover else "transparent"
        self.setStyleSheet(f"#DropZone {{ border: 1px dashed {border}; border-radius: 6px; background: {bg}; }}")

    def dragEnterEvent(self, event):
        if jar_paths(event.mimeData()):
            event.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, event):
        self._set_hover(False)

    def dropEvent(self, event):
        self._set_hover(False)
        files = jar_paths(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.on_files(files)


def jar_paths(mime) -> List[Path]:
    if not mime.hasUrls():
        return []
    return [Path(u.toLocalFile()) for u in mime.urls()
            if u.isLocalFile() and u.toLocalFile().lower().endswith(".jar")]


class AddonsTab(ServerTab):
    """Plugins (Paper/Purpur) or mods (Fabric/NeoForge/Forge). Hidden for Vanilla."""

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 14, 24, 16)
        outer.setSpacing(14)
        self.notice = warn_label(t("The server is running. Changes apply after a restart."))
        outer.addWidget(self.notice)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.btn_installed = set_kind(QPushButton(), "segment")  # named in refresh(): plugins or mods
        self.btn_browse = set_kind(QPushButton(), "segment")
        self.pages = QButtonGroup(self)
        for i, b in enumerate((self.btn_installed, self.btn_browse)):
            b.setCheckable(True)
            self.pages.addButton(b, i)
            seg.addWidget(b)
        seg.addStretch()
        outer.addLayout(seg)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.stack.addWidget(page)
        self.browser = ModrinthBrowser(self.refresh_installed, lambda: self.running)
        self.stack.addWidget(self.browser)
        self.pages.idClicked.connect(self.stack.setCurrentIndex)
        self.btn_installed.setChecked(True)
        self.drop = DropZone(self.add_files, self._browse)
        layout.addWidget(self.drop)
        self.toolbar = QWidget()
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setObjectName("Hint")
        row.addWidget(self.summary)
        row.addStretch()
        self.search = QLineEdit(placeholderText=t("Search..."))
        self.search.setMaximumWidth(200)
        self.search.setMinimumWidth(100)
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search)
        self.btn_updates = QPushButton(t("Check for updates"))
        self.btn_updates.clicked.connect(self._check_updates)
        row.addWidget(self.btn_updates)
        open_btn = set_kind(QPushButton(t("Open folder")), "ghost")
        open_btn.clicked.connect(lambda: open_path(addons.addon_dir(self.meta)))
        row.addWidget(open_btn)
        layout.addWidget(self.toolbar)
        self.list = QListWidget()
        self.list.setObjectName("AddonList")
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setSpacing(0)
        layout.addWidget(self.list, 1)

        # nothing installed: say it's fine (they're optional) and point to the search
        self.empty = QWidget()
        ev = QVBoxLayout(self.empty)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(10)
        ev.addStretch(2)
        self.empty_title = QLabel()
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        ev.addWidget(self.empty_title)
        self.empty_text = hint("")
        self.empty_text.setAlignment(Qt.AlignCenter)
        ev.addWidget(self.empty_text)
        ev.addSpacing(6)
        self.btn_find = set_kind(QPushButton(), "primary")
        self.btn_find.setMinimumHeight(34)
        self.btn_find.clicked.connect(self._show_browser)
        ev.addWidget(self.btn_find, 0, Qt.AlignHCenter)
        ev.addSpacing(18)
        self.empty_drop = DropZone(self.add_files, self._browse, compact=True)
        self.empty_drop.setMaximumWidth(460)
        ev.addWidget(self.empty_drop, 0, Qt.AlignHCenter)
        ev.addStretch(3)
        layout.addWidget(self.empty, 1)

    def label(self) -> str:
        return addons.kind_label(self.meta) if self.meta else ""

    def set_server(self, meta) -> None:
        super().set_server(meta)
        if self.label():
            self.browser.set_server(meta)

    def refresh_installed(self):
        self.refresh()

    def _show_browser(self):
        self.btn_browse.setChecked(True)
        self.stack.setCurrentIndex(1)

    def _check_updates(self):
        if self.meta:
            browse.check_updates(self, self.meta, self.refresh, self.running, self.btn_updates)

    def refresh(self):
        if not self.meta or not self.label():
            return
        plugin = self.label() == "Plugins"
        self.btn_installed.setText(t("Installed plugins") if plugin else t("Installed mods"))
        self.btn_browse.setText(t("Find plugins") if plugin else t("Find mods"))
        self.btn_find.setText(self.btn_browse.text())
        self.empty_title.setText(t("No plugins yet") if plugin else t("No mods yet"))
        self.empty_text.setText(t("Plugins are optional. You can play with friends without any.") if plugin
                                else t("Mods are optional. You can play with friends without any."))
        for zone in (self.drop, self.empty_drop):
            zone.title.setText(t("Drag plugin .jar files here") if plugin else t("Drag mod .jar files here"))
        self.list.clear()
        self.browser.invalidate_installed()
        items = addons.list_addons(self.meta)
        for a in items:
            self._add_card(a, addons.compatibility_warning(self.meta, a))
        on = sum(1 for a in items if a.enabled)
        self.summary.setText(t("{n} installed · {on} on", n=len(items), on=on))
        for w in (self.drop, self.toolbar, self.list):
            w.setVisible(bool(items))
        self.empty.setVisible(not items)
        self.on_state()
        self._filter(self.search.text())

    def on_state(self):
        self.notice.setVisible(self.running)

    def _add_card(self, addon, warning: str):
        item = QListWidgetItem()
        card = AddonCard(addon, warning, self._toggle, self._remove)
        item.setSizeHint(card.sizeHint())
        item.setData(Qt.UserRole, (addon.name + " " + addon.file_name).lower())
        self.list.addItem(item)
        self.list.setItemWidget(item, card)

    def _filter(self, text: str):
        text = text.lower().strip()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(text) and text not in it.data(Qt.UserRole))

    def _browse(self):
        files, _ = QFileDialog.getOpenFileNames(self, t("Choose files..."), "", "Java (*.jar)")
        if files:
            self.add_files([Path(f) for f in files])

    def add_files(self, files: List[Path]):
        if not self.meta or not files:
            return
        # warn before copying jars made for another loader
        mismatched = [(f, addons.compatibility_warning(self.meta, addons.read_info(f))) for f in files]
        mismatched = [(f, w) for f, w in mismatched if w]
        if mismatched:
            text = "\n".join(f"• {f.name}: {w}" for f, w in mismatched)
            if QMessageBox.question(self, t("Check these files"), text + "\n\n" + t("Add them anyway?")) != QMessageBox.Yes:
                files = [f for f in files if f not in {m for m, _ in mismatched}]
        try:
            addons.add_files(self.meta, files)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, t(self.label()), str(e))
        self.refresh()

    def _toggle(self, card, on: bool):
        try:
            addons.set_enabled(card.addon, on)
        except OSError as e:
            # e.g. Windows keeps the jar locked while the server runs: put the switch back
            card.switch.blockSignals(True)
            card.switch.setChecked(not on)
            card.switch.blockSignals(False)
            card.switch.animate_to(not on)  # slide back
            QMessageBox.warning(self, t(self.label()), t("Couldn't change {file}. Stop the server, then try again.",
                                                         file=card.addon.file_name) + f"\n{e}")
            return
        card.setOpacity(on)
        # count from the cards on screen: re-reading every jar made each switch slow
        cards = [self.list.itemWidget(self.list.item(i)) for i in range(self.list.count())]
        cards = [c for c in cards if c is not None]
        self.summary.setText(t("{n} installed · {on} on", n=len(cards), on=sum(1 for c in cards if c.switch.isChecked())))

    def _remove(self, card):
        if QMessageBox.question(self, t("Remove"), t("Delete {name}?", name=card.addon.file_name)) == QMessageBox.Yes:
            try:
                addons.remove(card.addon)
            except OSError as e:
                QMessageBox.warning(self, t("Remove"), t("Couldn't change {file}. Stop the server, then try again.",
                                                         file=card.addon.file_name) + f"\n{e}")
            self.refresh()


# ==================================================================== status


class Sparkline(QWidget):
    """Tiny single-series line chart (newest on the right). Hover shows the value."""

    def __init__(self, fmt: Callable[[float], str], fixed_max: Optional[float] = None, points: int = 90):
        super().__init__()
        self.values: deque = deque(maxlen=points)
        self.fmt = fmt
        self.fixed_max = fixed_max
        self.points = points
        self.setMinimumHeight(46)
        self.setMouseTracking(True)

    def add(self, v: float):
        self.values.append(v)
        self.update()

    def clear(self):
        self.values.clear()
        self.update()

    def _scale_max(self) -> float:
        if self.fixed_max:
            return self.fixed_max
        return max(max(self.values, default=0) * 1.15, 1e-9)

    def _xy(self, i: int, v: float, w: float, h: float):
        step = w / max(self.points - 1, 1)
        x = w - (len(self.values) - 1 - i) * step
        y = h - 2 - (min(v, self._scale_max()) / self._scale_max()) * (h - 6)
        return x, y

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # recessive baseline
        p.setPen(QPen(QColor(theme.C["border"]), 1))
        p.drawLine(0, h - 1, w, h - 1)
        if len(self.values) < 2:
            return
        pts = [QPointF(*self._xy(i, v, w, h)) for i, v in enumerate(self.values)]
        area = QPainterPath(QPointF(pts[0].x(), h - 1))
        for pt in pts:
            area.lineTo(pt)
        area.lineTo(QPointF(pts[-1].x(), h - 1))
        fill = QColor(theme.C["accent"])
        fill.setAlpha(18)
        p.fillPath(area, fill)
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(theme.C["accent"]), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(line)

    def mouseMoveEvent(self, event):
        if not self.values:
            return
        step = self.width() / max(self.points - 1, 1)
        back = round((self.width() - event.position().x()) / step)
        i = len(self.values) - 1 - back
        if 0 <= i < len(self.values):
            secs = back * StatusTab.INTERVAL_MS // 1000
            when = t("now") if back == 0 else t("{s}s ago", s=secs)
            QToolTip.showText(event.globalPosition().toPoint(), f"{self.fmt(self.values[i])} · {when}", self)


class StatTile(QFrame):
    """One cell of the numbers table: small gray title, the value, a note and a tiny chart."""

    def __init__(self, title: str, spark: Optional[Sparkline] = None):
        super().__init__()
        self.setObjectName("Tile")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(2)
        head = QLabel(title)
        head.setObjectName("Hint")
        v.addWidget(head)
        self.value = QLabel("-")
        self.value.setObjectName("Big")
        self.sub = hint("")
        v.addWidget(self.value)
        v.addWidget(self.sub)
        self.spark = spark
        if spark:
            v.addWidget(spark)
        else:
            v.addStretch()

    def set(self, value: str, sub: str = ""):
        self.value.setText(value)
        self.sub.setText(sub)


def java_exe(meta) -> str:
    """Full path of the java.exe this server runs with ("" if unknown)."""
    path = (meta.java_path or "") if meta else ""
    if path and not os.path.isabs(path):
        path = shutil.which(path) or ""
    return path


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _rate(v: float) -> str:
    return stats.human_bytes(v) + "/s"


class CheckRow(QWidget):
    """One line of the join check: ● title — detail."""

    def __init__(self, title: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        self.icon = QLabel("●")
        self.icon.setFixedWidth(12)
        row.addWidget(self.icon)
        self.title = QLabel(title)
        self.title.setMinimumWidth(90)
        self.title.setMaximumWidth(150)
        row.addWidget(self.title)
        self.detail = QLabel("-")
        self.detail.setWordWrap(True)
        row.addWidget(self.detail, 1)

    def set(self, state: str, detail: str):
        """state: ok / warn / fail / wait / off"""
        color = {"ok": theme.C["ok"], "fail": theme.C["danger"], "wait": theme.C["warn"], "warn": theme.C["warn"],
                 "off": theme.C["disabled"]}[state]
        self.icon.setStyleSheet(f"color: {color}; font-size: 8pt;")
        self.detail.setText(detail)
        self.detail.setStyleSheet(f"color: {theme.C['text'] if state in ('ok', 'fail', 'warn') else theme.C['muted']};")


def _ok_detail(r) -> str:
    bits = [r.version, t("{players} players", players=r.players) if r.players else ""]
    if r.latency_ms is not None:
        bits.append(f"{r.latency_ms:.0f} ms")
    return " · ".join(b for b in bits if b) or t("Reachable")


class JoinCheckBox(QGroupBox):
    INTERVAL_MS = 60_000

    def __init__(self, tab: "StatusTab"):
        super().__init__(t("Can players join?"))
        self.setProperty("first", True)
        self.tab = tab
        v = QVBoxLayout(self)
        self.rows = {
            "local": CheckRow(t("This PC")),
            "lan": CheckRow(t("Same Wi-Fi")),
            "internet": CheckRow(t("Internet")),
            "tunnel": CheckRow(t("Tunnel")),
            "bedrock": CheckRow(t("Bedrock")),
        }
        for r in self.rows.values():
            v.addWidget(r)
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 0)
        self.btn = QPushButton(t("Check now"))
        self.btn.clicked.connect(self.run)
        row.addWidget(self.btn)
        self.when = hint("")
        row.addWidget(self.when, 1)
        v.addLayout(row)
        v.addWidget(hint(t(
            "Internet checks are done from outside by mcsrvstat.us and can lag a few minutes behind.")))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.run)
        self._busy = False

    def reset(self):
        meta = self.tab.meta
        tunnel_addr = self.tab.tunnel.address if self.tab.tunnel else ""
        self.rows["tunnel"].setVisible(bool(tunnel_addr))
        self.rows["bedrock"].setVisible(bool(meta and plugins.udp_ports(meta)))
        for r in self.rows.values():
            r.set("off", t("Server is off") if not self.tab.running else "-")
        self.when.setText("")
        self.btn.setEnabled(self.tab.running)

    def update_timer(self):
        if self.tab.isVisible() and self.tab.running and not self.tab._paused:
            if not self.timer.isActive():
                self.timer.start(self.INTERVAL_MS)
                self.run()
        else:
            self.timer.stop()

    def run(self):
        meta = self.tab.meta
        if self._busy or not meta or not self.tab.running:
            return
        if self.tab.runner.state(self.tab.key) != "running":
            for r in self.rows.values():
                r.set("wait", t("Server is still starting..."))
            return
        self._busy = True
        self.btn.setEnabled(False)
        for r in self.rows.values():
            r.set("wait", t("Checking..."))
        port = meta.properties().get_int("server-port", 25565)
        self._port = port
        udp = plugins.udp_ports(meta)
        tunnel_addr = self.tab.tunnel.address if self.tab.tunnel else ""
        java = java_exe(meta)

        def work(task):
            res = {"local": joincheck.server_list_ping("127.0.0.1", port)}
            # pinging our own LAN address goes through loopback, which Windows Firewall never
            # filters: ask the firewall itself whether other devices are let in
            res["firewall"] = network.firewall_status(port, java, max_age=300) if os.name == "nt" else network.UNKNOWN
            lan = network.lan_ip()
            res["lan"] = joincheck.server_list_ping(lan, port) if lan != "127.0.0.1" else None
            try:
                public = network.public_ip()
            except net.NetError:
                public = ""
            res["internet"] = joincheck.external_check(f"{public}:{port}") if public else None
            if tunnel_addr:
                res["tunnel"] = joincheck.external_check(tunnel_addr)
            if udp and public:
                res["bedrock"] = joincheck.external_check(f"{public}:{udp[0]}", bedrock=True)
            return res

        def done(res):
            self._busy = False
            self.btn.setEnabled(self.tab.running)
            if str(meta.folder) != self.tab.key:
                self.run()  # we switched servers meanwhile: check the one on screen instead
                return
            self._show(res)
            self.when.setText(t("Last checked {time}", time=time.strftime("%H:%M:%S")))

        def fail(msg):
            self._busy = False
            self.btn.setEnabled(self.tab.running)
            self.when.setText(msg)

        run_async(work, done, fail)

    def _show(self, res):
        local, lan, inet = res.get("local"), res.get("lan"), res.get("internet")
        tm = self.tab.tunnel
        tunnel_on = bool(tm and tm.state == "running" and tm.address)
        if local and local.ok:
            self.rows["local"].set("ok", _ok_detail(local))
        else:
            self.rows["local"].set("fail", t("The server isn't answering."))
        fw = res.get("firewall", network.UNKNOWN)
        if lan is None:
            self.rows["lan"].set("off", t("Not connected to a network"))
        elif not lan.ok:
            self.rows["lan"].set("fail", t("Blocked on the network. Allow it in Windows Firewall (Network tab)."))
        elif fw == network.BLOCKED:
            self.rows["lan"].set("fail", t(
                "Windows Firewall blocks Java, so other devices can't join. Press 'Allow in Windows Firewall' in the Network tab."))
        elif fw == network.UNKNOWN and os.name == "nt":
            self.rows["lan"].set("warn", t(
                "Works from this PC. Other devices may still be blocked by Windows Firewall: "
                "press 'Allow in Windows Firewall' in the Network tab to be sure."))
        else:
            self.rows["lan"].set("ok", _ok_detail(lan))
        if inet is None:
            self.rows["internet"].set("off", t("Couldn't check (no internet?)"))
        elif inet.ok:
            self.rows["internet"].set("ok", _ok_detail(inet))
        elif res.get("tunnel") is not None and res["tunnel"].ok:
            # the port isn't open, but that's fine: friends come in through the tunnel
            self.rows["internet"].set("ok", t("Through the tunnel (the port itself isn't open, which is fine)."))
        elif tunnel_on:
            self.rows["internet"].set("warn", t(
                "The port isn't open. Friends in other homes can still join with the tunnel address."))
        elif fw == network.BLOCKED:
            self.rows["internet"].set("fail", t(
                "Windows Firewall blocks Java. Press 'Allow in Windows Firewall' in the Network tab, then open the port."))
        else:
            self.rows["internet"].set("fail", t("Not reachable from the internet. Open the port or start the tunnel (Network tab)."))
        if "tunnel" in res:
            tr = res["tunnel"]
            if tr.ok:
                self.rows["tunnel"].set("ok", _ok_detail(tr))
            elif tr.error != "offline":
                self.rows["tunnel"].set("off", t("Couldn't check (no internet?)"))
            else:
                # the outside check service caches answers for a few minutes and can miss a fresh tunnel
                self.rows["tunnel"].set("warn", t(
                    "Not confirmed from outside yet (the check service updates every few minutes). If it stays like "
                    "this, check that the playit tunnel points to local port {port}.", port=self._port))
        if "bedrock" in res:
            br = res["bedrock"]
            if br.ok:
                self.rows["bedrock"].set("ok", _ok_detail(br))
            else:
                udp = plugins.udp_ports(self.tab.meta) if self.tab.meta else []
                self.rows["bedrock"].set("fail", t("Bedrock port not reachable. Open UDP {port} or add a Bedrock tunnel.",
                                                   port=udp[0] if udp else plugins.DEFAULT_BEDROCK_PORT))


class StatusTab(ServerTab):
    tunnel = None  # TunnelManager, set by the main window

    INTERVAL_MS = 2000
    PING_EVERY = 5  # samples (10 s)
    DISK_EVERY = 30  # samples (60 s)

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.join = JoinCheckBox(self)
        layout.addWidget(self.join)
        usage = QGroupBox(t("Usage"))
        uv = QVBoxLayout(usage)
        uv.setSpacing(10)
        self.notice = hint("")
        uv.addWidget(self.notice)
        tiles = QFrame()
        tiles.setObjectName("Tiles")
        grid = QGridLayout(tiles)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)  # 1 px gaps show the frame colour: thin lines between the cells
        self.cpu = StatTile(t("CPU"), Sparkline(lambda v: f"{v:.0f}%", fixed_max=100))
        self.mem = StatTile(t("Memory"), Sparkline(stats.human_bytes))
        self.down = StatTile(t("Download"), Sparkline(_rate))
        self.up = StatTile(t("Upload"), Sparkline(_rate))
        self.ping = StatTile(t("Average ping"), Sparkline(lambda v: f"{v:.0f} ms"))
        self.disk = StatTile(t("Disk"))
        for i, tile in enumerate((self.cpu, self.mem, self.down, self.up, self.ping, self.disk)):
            grid.addWidget(tile, i // 3, i % 3)
        uv.addWidget(tiles)
        uv.addWidget(hint(t(
            "Download/upload are for the whole PC. Ping is measured from this PC to each player (some networks block it).")))
        layout.addWidget(usage)
        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sample)
        self.monitor = None
        self._monitor_pid = None
        self._n = 0
        self._ping_busy = self._disk_busy = False
        self._shown_for = None  # the server whose numbers the graphs hold
        self._disk_for = None
        self._paused = False

    def set_server(self, meta) -> None:
        same = self._shown_for == meta.folder
        self.meta = meta
        if same:  # a reload of the same server (Save, rename...): keep the graphs
            self.on_state()
        else:
            self.refresh()

    def set_paused(self, paused: bool):
        self._paused = paused
        self._update_timer()

    def forget_server(self) -> None:
        super().forget_server()
        self._shown_for = None
        self._disk_for = None
        self.timer.stop()
        self.join.timer.stop()

    def refresh(self):
        self._shown_for = self.meta.folder if self.meta else None
        self._disk_for = None
        for tile in (self.cpu, self.mem, self.down, self.up, self.ping):
            tile.spark.clear()
            tile.set("-")
        self.disk.set("-")
        self.monitor = None
        self._monitor_pid = None  # or _sample would never make a new monitor after a reload
        self._n = 0
        self.on_state()

    def on_state(self):
        if not self.meta:
            return
        self.notice.setText("" if self.running else t("The server is off. Live numbers appear while it runs."))
        self.notice.setVisible(not self.running)
        self.mem.spark.fixed_max = self.meta.ram_mb * 1024 * 1024
        self.join.reset()
        self._update_timer()
        if self.isVisible() and self.runner.state(self.key) == "running":
            self.join.run()  # just finished starting: check now, not a minute later
        if self.isVisible():
            self._disk()
        else:
            self._disk_for = None  # measure when the tab is opened

    # sample only while this tab is on screen and the server runs (low-resource)
    def showEvent(self, event):
        super().showEvent(event)
        self._update_timer()
        self._sample()
        if self._disk_for != self.key:
            self._disk()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()
        self.join.timer.stop()

    def _update_timer(self):
        self.join.update_timer()
        if self.isVisible() and self.running and not self._paused:
            if not self.timer.isActive():
                self.timer.start(self.INTERVAL_MS)
        else:
            self.timer.stop()

    def _sample(self):
        if not self.meta or not self.running:
            return
        pid = self.runner.pid(self.key)
        if pid and pid != self._monitor_pid:
            try:
                self.monitor = stats.ProcessMonitor(pid)
                self._monitor_pid = pid
            except Exception:  # noqa: BLE001 - process just exited
                self.monitor = None
        if not self.monitor:
            return
        smp = self.monitor.sample()
        if not smp:
            return
        self.cpu.spark.add(smp.cpu_percent)
        self.cpu.set(f"{smp.cpu_percent:.0f}%", t("of this PC"))
        self.mem.spark.add(smp.memory_bytes)
        self.mem.set(stats.human_bytes(smp.memory_bytes), t("of {max} allowed", max=stats.human_bytes(self.meta.ram_mb * 1024 * 1024)))
        self.down.spark.add(smp.net_recv_per_s)
        self.down.set(_rate(smp.net_recv_per_s))
        self.up.spark.add(smp.net_sent_per_s)
        self.up.set(_rate(smp.net_sent_per_s))
        self._n += 1
        if self._n % self.PING_EVERY == 1:
            self._ping()
        if self._n % self.DISK_EVERY == 0:
            self._disk()

    def _ping(self):
        all_ips = self.runner.ips(self.key)
        if not all_ips:
            self.ping.set("-", t("No players online"))
            return
        # players coming through the playit tunnel show up as 127.0.0.1: pinging that says nothing
        ips = {n: ip for n, ip in all_ips.items() if not ip.startswith("127.") and ip != "::1"}
        if not ips:
            self.ping.set("-", t("Can't measure through the tunnel"))
            return
        if self._ping_busy:
            return
        self._ping_busy = True
        key = self.key

        def done(result):
            self._ping_busy = False
            if key != self.key:
                return
            vals = [v for v in result.values() if v is not None]
            if vals:
                avg = sum(vals) / len(vals)
                self.ping.spark.add(avg)
                self.ping.set(f"{avg:.0f} ms", t("average of {n} players", n=len(vals)))
            else:
                self.ping.set("?", t("Players' networks don't answer ping"))

        def fail(_msg):
            self._ping_busy = False

        run_async(lambda task: stats.average_ping(set(ips.values())), done, fail)

    def _disk(self):
        if not self.meta or self._disk_busy:
            return
        self._disk_busy = True
        self._disk_for = self.key
        meta = self.meta

        def work(task):
            # one walk of the folder: the worlds are counted on the way
            worlds = [d for d in srv.world_dirs(meta) if d.exists()]
            world_total = 0
            total = 0
            for top in meta.folder.iterdir() if meta.folder.exists() else []:
                size = stats.folder_size(top) if top.is_dir() else _file_size(top)
                total += size
                if any(top == w for w in worlds):
                    world_total += size
            world_total += sum(stats.folder_size(w) for w in worlds if w.parent != meta.folder)
            return total, world_total

        def done(res):
            self._disk_busy = False
            if str(meta.folder) != self.key:
                self._disk()  # switched servers meanwhile: measure the one on screen
                return
            total, world = res
            self.disk.set(stats.human_bytes(total), t("World {size}", size=stats.human_bytes(world)))

        def fail(_msg):
            self._disk_busy = False

        run_async(work, done, fail)


# ============================================================ server version


class UpgradeSection(ServerTab):
    """Server version and updates. Lives inside the World tab, which shows the 'stop first' notice."""

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(t("Server version"))
        form = form_layout(box)
        self.cur_version = QLabel()
        self.cur_version.setObjectName("ItemName")
        form.addRow(t("Current"), self.cur_version)
        java_row = QHBoxLayout()
        self.cur_java = QLabel()
        self.cur_java.setWordWrap(True)
        java_row.addWidget(self.cur_java, 1)
        self.btn_java = set_kind(QPushButton(t("Reinstall Java")), "ghost")
        self.btn_java.clicked.connect(self._fix_java)
        java_row.addWidget(self.btn_java)
        form.addRow("Java", java_row)
        # another software (Paper -> Fabric...) switches the server; the same one updates it
        self.software = QComboBox()
        for p in PROVIDERS:
            self.software.addItem(p.name, p.id)
        self.software.currentIndexChanged.connect(self._reload)
        form.addRow(t("Software"), with_note(self.software, t(
            "Pick another software to switch this server to it (for example Paper → Fabric). "
            "The world and settings stay; a full backup is made first.")))
        self.version = QComboBox()
        form.addRow(t("Update to"), self.version)
        self.version_label = form.labelForField(self.version)
        self.version_status = hint("")
        form.addRow("", self.version_status)
        self.unstable = QCheckBox(t("Show snapshots"))
        self.unstable.toggled.connect(self._reload)
        self.unstable.setToolTip(t("Test versions of upcoming updates. They can be unstable."))
        form.addRow("", self.unstable)
        self.allow_downgrade = QCheckBox(t("Show older versions"))
        self.allow_downgrade.toggled.connect(self._reload)
        self.allow_downgrade.setToolTip(t(
            "Going back to an older version can break the world. Keep the backup option on."))
        form.addRow("", self.allow_downgrade)
        self.backup = QCheckBox(t("Back up the whole server first (recommended)"))
        self.backup.setChecked(True)
        form.addRow("", self.backup)
        self.auto_java = QCheckBox(t("Install the right Java automatically"))
        self.auto_java.setChecked(True)
        form.addRow("", self.auto_java)
        row = QHBoxLayout()
        self.btn_upgrade = QPushButton(t("Update"))
        self.btn_upgrade.clicked.connect(self._upgrade)
        row.addWidget(self.btn_upgrade)
        row.addSpacing(6)
        row.addWidget(hint(t("Check that your plugins/mods support the new version.")), 1)
        form.addRow("", row)
        layout.addWidget(box)

        self.loader = VersionLoader(self.version, self.version_status)
        self._loaded_for = None

    def forget_server(self) -> None:
        super().forget_server()
        self._loaded_for = None

    def refresh(self):
        if not self.meta:
            return
        m = self.meta
        self.cur_version.setText(f"{m.software_name} {m.mc_version}" + ("  " + t("(build {b})", b=m.build) if m.build else ""))
        self.cur_java.setText(f"Java {m.java_major} — {m.java_path}")
        running = self.locked
        self.btn_upgrade.setEnabled(not running)
        self.btn_java.setEnabled(not running)
        if self._loaded_for is None or self._loaded_for[0] != m.folder:
            for box, on in ((self.backup, True), (self.auto_java, True), (self.allow_downgrade, False)):
                box.blockSignals(True)  # another server: the safe defaults again (backup on!)
                box.setChecked(on)
                box.blockSignals(False)
        if self._loaded_for is None or self._loaded_for[:3] != (m.folder, m.software, m.mc_version):
            self.software.blockSignals(True)  # a new server (or after a switch): start from its own software
            self.software.setCurrentIndex(max(0, self.software.findData(m.software)))
            self.software.blockSignals(False)
            self._reload()

    def _target(self) -> str:
        return self.software.currentData() or (self.meta.software if self.meta else "")

    def _reload(self):
        if not self.meta:
            return
        m = self.meta
        target = self._target()
        switching = target != m.software
        self._loaded_for = (m.folder, m.software, m.mc_version, target)
        self.version_label.setText(t("Version") if switching else t("Update to"))
        self.btn_upgrade.setText(t("Switch software") if switching else t("Update"))
        provider = get_provider(target)
        current = m.mc_version
        downgrade = self.allow_downgrade.isChecked()
        unstable = self.unstable.isChecked()
        if switching:
            # same Minecraft version or newer (older only when asked); the current one is preselected
            def not_older(v: str) -> bool:
                return downgrade or versions.version_key(v) >= versions.version_key(current)

            self.loader.load(provider, unstable, keep=current, filter_fn=not_older)
            return

        def make_filter():  # runs in the background: may fetch the full list
            order = None
            if m.software in ("vanilla", "fabric"):
                # Snapshots (e.g. 25w14a) can't be compared by number: use list order (newest first).
                # A snapshot server isn't in the releases-only list, so look it up in the full one.
                order = provider.list_versions(unstable)
                if current not in order:
                    try:
                        order = provider.list_versions(True)
                    except Exception:  # noqa: BLE001 - fall back to comparing numbers
                        order = []
                if current not in order:
                    order = None

            def newer(v: str) -> bool:
                if v == current:
                    return False
                if downgrade:
                    return True
                if order is not None and v in order:
                    return order.index(v) < order.index(current)
                return versions.version_key(v) > versions.version_key(current)

            return newer

        self.loader.load(provider, unstable, make_filter=make_filter)

    def _upgrade(self):
        if self._target() != self.meta.software:
            self._switch()
            return
        new = self.version.currentData()
        if not new:
            if self.loader.loaded:
                QMessageBox.information(self, t("Update"), t("You're on the latest version."))
            else:  # still loading, or the list couldn't be fetched (offline)
                QMessageBox.information(self, t("Update"), t("The version list isn't loaded. Check your internet connection."))
            return
        m = self.meta
        warn = ""
        if versions.version_key(new) < versions.version_key(m.mc_version):
            warn = "\n\n⚠ " + t("Going to an older version can break the world!")
        if QMessageBox.question(
            self, t("Update"), t("Update {name} {old} → {new}?", name=m.software_name, old=m.mc_version, new=new) + warn
        ) != QMessageBox.Yes:
            return
        backup, auto_java = self.backup.isChecked(), self.auto_java.isChecked()
        self.run_task(
            t("Update"),
            lambda task: srv.upgrade_server(m, new, auto_java=auto_java, backup_first=backup, task=task),
        )
        self.on_changed()

    def _switch(self):
        m, target, new = self.meta, self._target(), self.version.currentData()
        if not new:
            QMessageBox.information(self, t("Switch software"), t("The version list isn't loaded. Check your internet connection.")
                                    if not self.loader.loaded else t("No versions available."))
            return
        mods = ("fabric", "forge", "neoforge")
        split = srv.SPLIT_DIMENSIONS
        notes = []
        if m.software in mods:
            notes.append(t("Blocks, items and creatures added by mods will disappear from the world."))
        if m.software in split and target not in split:
            notes.append(t("Plugins won't work anymore. The plugins folder is kept."))
            notes.append(t("The Nether and End are moved into the world folder (that's where {name} keeps them).",
                           name=get_provider(target).name))
            if plugins.bedrock_installed(m):
                notes.append(t("Bedrock players can't join anymore: Geyser needs Paper or Purpur."))
        if target in mods and m.software != target:
            notes.append(t("Put mods made for {name} into the Mods tab afterwards.", name=get_provider(target).name))
        if versions.version_key(new) < versions.version_key(m.mc_version):
            notes.append(t("Going to an older version can break the world!"))
        text = t("Switch {old} {oldv} → {new} {newv}?", old=m.software_name, oldv=m.mc_version,
                 new=get_provider(target).name, newv=new)
        text += "\n\n" + t("The world and settings stay.") + ("\n\n" + "\n".join("⚠ " + n for n in notes) if notes else "")
        if QMessageBox.question(self, t("Switch software"), text) != QMessageBox.Yes:
            return
        backup, auto_java = self.backup.isChecked(), self.auto_java.isChecked()
        self.run_task(
            t("Switch software"),
            lambda task: srv.upgrade_server(m, new, auto_java=auto_java, backup_first=backup, task=task,
                                            new_software=target),
        )
        self.on_changed()

    def _fix_java(self):
        m = self.meta
        auto = self.auto_java.isChecked()
        self.run_task("Java", lambda task: srv.change_java(m, auto, task))
        self.on_changed()
