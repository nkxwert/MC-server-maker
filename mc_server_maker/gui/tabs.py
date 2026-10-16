"""Server tabs: Console / Status / Settings / World (with version updates) / Players / Network."""

import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QEasingCurve, QPointF, Qt, QTimer, QUrl, QVariantAnimation, Signal
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
    with_help,
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


def warn_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Warn")
    return label


def _scroll(widget: QWidget) -> QScrollArea:
    widget.layout().setContentsMargins(16, 8, 16, 16)
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

    def set_server(self, meta: srv.ServerMeta) -> None:
        self.meta = meta
        self.refresh()

    def refresh(self) -> None:
        pass

    def on_state(self) -> None:
        """Called when the server starts or stops."""
        self.refresh()

    def run_task(self, title: str, fn) -> bool:
        dlg = TaskDialog(self, title, fn)
        dlg.exec()
        return dlg.succeeded()


# =================================================================== console

_CONSOLE_RULES = [
    (re.compile(r"^»» "), "accent", True),
    (re.compile(r"^> "), "info", True),
    (re.compile(r"ERROR|SEVERE|Exception|^\s+at "), "danger", False),
    (re.compile(r"WARN"), "warn", False),
    (re.compile(r"joined the game"), "accent", False),
    (re.compile(r"left the game"), "warn", False),
    (re.compile(r": <[^>]+> "), "#ffffff", True),  # chat
    (re.compile(r"Done \("), "accent", True),
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
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.view = QPlainTextEdit(readOnly=True)
        self.view.setObjectName("Console")
        self.view.setMaximumBlockCount(5000)
        left.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = HistoryLineEdit(placeholderText=t("Type a command and press Enter (↑↓ history)"))
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
        side.setSpacing(8)
        box = QGroupBox(t("Online"))
        v = QVBoxLayout(box)
        self.player_count = QLabel("0")
        self.player_count.setObjectName("Big")
        v.addWidget(self.player_count)
        self.more_btn = set_kind(QPushButton(t("More...")), "ghost")
        self.more_btn.clicked.connect(self._show_players)
        v.addWidget(self.more_btn)
        v.addStretch()
        side.addWidget(box, 1)  # the three boxes split the height into exact thirds
        box = QGroupBox(t("Uptime"))
        v = QVBoxLayout(box)
        self.uptime = QLabel("-")
        self.uptime.setObjectName("Big")
        v.addWidget(self.uptime)
        v.addStretch()
        side.addWidget(box, 1)
        box = QGroupBox(t("Total uptime"))
        v = QVBoxLayout(box)
        self.total_uptime = QLabel("-")
        self.total_uptime.setObjectName("Big")
        self.total_uptime.setWordWrap(True)
        self.total_uptime.setToolTip(t("All the time this server has been running, across every start."))
        v.addWidget(self.total_uptime)
        v.addStretch()
        side.addWidget(box, 1)
        side_w = QWidget()
        side_w.setLayout(side)
        side.setContentsMargins(0, 0, 0, 0)
        side_w.setFixedWidth(132)
        outer.addWidget(side_w)

        # Lines are drawn in batches (a few times per second) instead of one by one,
        # and not at all while the console is hidden: keeps the app light.
        self._pending = []
        self._dirty = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush)
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self._tick)
        runner.line.connect(self._on_line)
        runner.players_changed.connect(self._on_players)

    @property
    def controls(self):
        return [self.input, self.save_btn]

    def refresh(self):
        self._pending.clear()
        self._dirty = False
        self.view.clear()
        self.view.setPlaceholderText(t("The server is off. Press Start to see its log here."))
        if self.meta:
            cursor = QTextCursor(self.view.document())
            for ln in self.runner.log_lines(self.key)[-self.view.maximumBlockCount():]:
                self._insert(cursor, ln)
        self.view.moveCursor(QTextCursor.End)
        self.on_state()

    def on_state(self):
        # update buttons only; don't redraw the log
        for w in self.controls:
            w.setEnabled(self.running)
        self._on_players(self.key)
        self._tick()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self.refresh()  # catch up on what arrived while hidden
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
        if not self.isVisible():
            self._dirty = True
            return
        self._pending.append(line)
        if not self._flush_timer.isActive():
            self._flush_timer.start(150)

    def _flush(self):
        if not self._pending:
            return
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        cursor = QTextCursor(self.view.document())
        cursor.beginEditBlock()
        for ln in self._pending:
            self._insert(cursor, ln)
        cursor.endEditBlock()
        self._pending.clear()
        if at_bottom:
            bar.setValue(bar.maximum())

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
        form = form_layout(box)
        self.name = QLineEdit()
        form.addRow(t("Name"), self.name)
        self.motd = QPlainTextEdit()
        self.motd.setFixedHeight(56)
        self.motd.textChanged.connect(self._update_preview)
        form.addRow(t("Description"), self.motd)
        # no (?) here: the colour codes show when hovering over the box
        self.motd.setToolTip(t("Shown under the server name in the multiplayer list (MOTD). Up to 2 lines.")
                             + "\n\n" + color_help())
        icon_row = QHBoxLayout()
        pick = QPushButton(t("Choose image..."))
        pick.clicked.connect(self._pick_icon)
        remove = set_kind(QPushButton(t("Remove")), "ghost")
        remove.clicked.connect(self._remove_icon)
        icon_row.addWidget(pick)
        icon_row.addWidget(remove)
        icon_row.addStretch()
        form.addRow(with_help(t("Icon"), t("Any image; resized to 64×64 automatically.")), icon_row)
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
        form.addRow(with_help(t("Port"), t(
            "Usually 25565. Change it only to run several servers at the same time.")), self.port)
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
        for key, label, help_text in (
            ("online-mode", "Online mode", "Players must sign in with a real Minecraft account. "
             "Turn it off to let non-premium accounts join (anyone can then use any name)."),
            ("pvp", "PvP", ""),
            ("hardcore", "Hardcore", "One life: players become spectators when they die."),
            ("white-list", "Whitelist only", "Only players on the whitelist (Players tab) can join."),
            ("allow-flight", "Allow flight", "Stops the server from kicking players for flying. "
             "Turn it on if mods or plugins let players fly."),
            ("enable-command-block", "Command blocks", ""),
        ):
            cb = QCheckBox(t(label))
            self.checks[key] = cb
            form.addRow("", with_help(cb, t(help_text)) if help_text else cb)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64)
        form.addRow(with_help(t("Memory (RAM)"), t(
            "1–3 players: 1–2 GB is usually enough. Modpacks need 4 GB or more.")), self.ram)
        self.autosave = QComboBox()
        for minutes in AUTOSAVE_CHOICES:
            self.autosave.addItem(t("Off") if not minutes else
                                  t("Every {n} minutes", n=minutes) if minutes < 60 else t("Every hour"), minutes)
        form.addRow(with_help(t("Auto-save"), t(
            "While the server runs, the world is saved at this interval, so less is lost if the PC "
            "shuts down suddenly. Saving takes a moment on big worlds.")), self.autosave)
        all_props = set_kind(QPushButton(t("Edit all server.properties...")), "ghost")
        all_props.clicked.connect(self._edit_all)
        form.addRow("", all_props)
        layout.addWidget(box)

        box = QGroupBox(t("Memory saver"))
        v = QVBoxLayout(box)
        self.memory_saver = QCheckBox(t("Use less memory"))
        self.memory_saver.toggled.connect(self._memory_saver_toggled)
        v.addWidget(with_help(self.memory_saver, t(
            "Usually saves a third to half of the memory. Sets view distance 6 and simulation distance 4, "
            "unloads spawn chunks and returns unused memory sooner. Far-away farms only run while someone is nearby.")))
        layout.addWidget(box)

        self.bedrock_box = QGroupBox(t("Bedrock players (phone / console / Windows)"))
        v = QVBoxLayout(self.bedrock_box)
        self.bedrock_status = QLabel()
        self.bedrock_status.setObjectName("ItemName")
        v.addWidget(with_help(self.bedrock_status, t(
            "Installs Geyser + Floodgate so Bedrock Edition players can join with their Xbox account.")))
        row = QHBoxLayout()
        self.btn_bedrock = set_kind(QPushButton(), "primary")
        self.btn_bedrock.clicked.connect(self._install_bedrock)
        self.btn_bedrock_remove = set_kind(QPushButton(t("Remove")), "danger")
        self.btn_bedrock_remove.clicked.connect(self._remove_bedrock)
        row.addWidget(self.btn_bedrock)
        row.addWidget(self.btn_bedrock_remove)
        row.addStretch()
        v.addLayout(row)
        layout.addWidget(self.bedrock_box)

        save = set_kind(QPushButton(t("Save")), "primary")
        save.setMinimumHeight(38)
        save.clicked.connect(self.save)
        layout.addWidget(save)

        # ---- world (its buttons act right away; "Save" above is only for the settings)
        layout.addSpacing(14)
        title = QLabel("🌍 " + t("World"))
        title.setObjectName("Big")
        layout.addWidget(title)
        self.world = WorldTab(runner, on_changed, embedded=True)
        layout.addWidget(self.world)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

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

    def on_state(self):
        # only update the notice so unsaved edits are kept
        self.notice.setText(t("The server is running. Saved changes apply after a restart.") if self.running else "")
        self.notice.setVisible(self.running)
        self._refresh_bedrock()
        self.world.on_state()

    def _refresh_bedrock(self):
        if not self.meta:
            return
        supported = plugins.supports_bedrock(self.meta)
        self.bedrock_box.setVisible(supported)
        if not supported:
            return
        installed = plugins.bedrock_installed(self.meta)
        self.bedrock_status.setText(
            ("🟢 " + t("Enabled — Bedrock port {port} (UDP)", port=plugins.bedrock_port(self.meta)))
            if installed else ("⚪ " + t("Not enabled"))
        )
        self.btn_bedrock.setText(t("Update Geyser") if installed else t("Enable Bedrock join"))
        self.btn_bedrock.setEnabled(not self.running)
        self.btn_bedrock_remove.setVisible(installed)
        self.btn_bedrock_remove.setEnabled(not self.running)

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

    def _edit_all(self):
        if PropertiesDialog(self, self.meta.properties_path).exec():
            self.refresh()

    def _install_bedrock(self):
        meta = self.meta
        self.run_task(t("Bedrock players"), lambda task: plugins.install_bedrock(meta, task))
        self._refresh_bedrock()

    def _remove_bedrock(self):
        if QMessageBox.question(self, t("Bedrock players"), t("Remove Geyser and Floodgate?")) == QMessageBox.Yes:
            plugins.remove_bedrock(self.meta)
            self._refresh_bedrock()

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
        self.meta.ram_mb = self.ram.value() * 1024
        self.meta.autosave_minutes = int(self.autosave.currentData() or 0)
        self.meta.save()
        srv.write_start_scripts(self.meta)
        self.on_changed()
        QMessageBox.information(self, t("Save"), t("Saved.") + ("\n" + t("Restart the server to apply.") if self.running else ""))


# ===================================================================== world


class WorldTab(ServerTab):
    """World and server version. Shown inside the Settings tab (embedded=True)."""

    def __init__(self, runner, on_changed, embedded: bool = False):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        self.running_notice = warn_label(t("Stop the server to change the world or update it."))
        layout.addWidget(self.running_notice)

        box = QGroupBox(t("Current world"))
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
        dice = QPushButton("🎲 " + t("Random"))
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
        self.btn_new = set_kind(QPushButton(t("Replace with new world")), "primary")
        self.btn_new.clicked.connect(self._new_world)
        v.addWidget(self.btn_new)
        self.mode_group.idToggled.connect(lambda *_: self.seed.setEnabled(self.rb_seed.isChecked()))
        self.seed.setEnabled(False)
        layout.addWidget(box)

        box = QGroupBox(t("Import world"))
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_import_dir = QPushButton(t("From folder..."))
        self.btn_import_dir.clicked.connect(self._import_dir)
        self.btn_import_zip = QPushButton(t("From zip..."))
        self.btn_import_zip.clicked.connect(self._import_zip)
        row.addWidget(self.btn_import_dir)
        row.addWidget(self.btn_import_zip)
        row.addWidget(HelpButton(t(
            "Singleplayer worlds are in .minecraft/saves. Choose the folder with level.dat, or a zip.")))
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

    def refresh(self):
        if not self.meta:
            return
        p = self.meta.properties()
        level = p.get("level-name") or "world"
        seed = p.get("level-seed") or ""
        self.info_seed.setText(seed or t("(random)"))
        lt = srv.parse_level_type(p.get("level-type"))
        self.info_type.setText(t(dict(srv.LEVEL_TYPES)[lt]))
        self.level_type.setCurrentIndex(self.level_type.findData(lt))
        exists = (self.meta.folder / level / "level.dat").exists()
        self.info_exists.setText(t("Generated") if exists else t("Not yet (created on first start)"))
        backups = srv.list_backups(self.meta)
        self.backup_info.setText(
            t("{n} backups", n=len(backups)) + (f" · {t('latest')}: {backups[0].name}" if backups else "")
        )
        running = self.running
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
            QMessageBox.warning(self, t("New world"), t("Enter a seed or press 🎲."))
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
        if not any(d.exists() for d in srv.world_dirs(meta)):
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
        row.setContentsMargins(0, 2, 0, 2)
        col = QVBoxLayout()
        col.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("ItemName")
        col.addWidget(title_label)
        col.addWidget(hint(sub))
        row.addLayout(col, 1)
        self.value = ClickLabel("-")
        self.value.setObjectName("Big")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.value)
        self.copy = QPushButton(t("Copy"))
        self.copy.clicked.connect(self._copy)
        row.addWidget(self.copy)
        if private:  # click the address to show it, click again to blur it
            self.value.setCursor(Qt.PointingHandCursor)
            self.value.clicked.connect(self._toggle_shown)
            self._render()

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text)  # always the real address, even while hidden
        self.copy.setText(t("Copied ✓"))
        QTimer.singleShot(1200, lambda: self.copy.setText(t("Copy")))

    def _toggle_shown(self):
        if not self._real:
            return
        self._shown = not self._shown
        self._render()

    def _render(self):
        hide = self._private and not self._shown and self._real
        self.value.setText(self._text)
        if hide:  # blurred, not replaced: the layout stays the same and it looks tidy
            blur = QGraphicsBlurEffect(self.value)
            blur.setBlurRadius(24)  # strong enough that the digits can't be read, even zoomed in
            blur.setBlurHints(QGraphicsBlurEffect.QualityHint)
            self.value.setGraphicsEffect(blur)
        else:
            self.value.setGraphicsEffect(None)
        # private rows aren't selectable: a click toggles them (Copy is there for copying)
        self.value.setTextInteractionFlags(Qt.NoTextInteraction if self._private else Qt.TextSelectableByMouse)
        if self._private:
            self.value.setToolTip(t("Click to show the address") if hide else
                                  (t("Click to hide the address") if self._real else ""))

    def set(self, text: str, enabled: bool = True):
        self._text, self._real = text, enabled and text not in ("", "-")
        self.copy.setEnabled(enabled)
        self._render()


class NetworkTab(ServerTab):
    _public_ip = None  # looked up once per app run
    tunnel = None  # TunnelManager, set by the main window

    def set_tunnel(self, manager):
        self.tunnel = manager
        manager.changed.connect(self._refresh_tunnel)
        self._refresh_tunnel()

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box = QGroupBox(t("Addresses"))
        v = QVBoxLayout(box)
        self.addr_local = AddressRow(t("This PC"), t("Playing on this computer"))
        self.addr_lan = AddressRow(t("Same Wi-Fi"), t("People in the same home"), private=True)
        self.addr_public = AddressRow(t("Internet"), t("Friends in other homes"), private=True)
        self.addr_bedrock = AddressRow(t("Bedrock (Internet)"), t("Phone / console players: address + port"),
                                       private=True)
        for w in (self.addr_local, self.addr_lan, self.addr_public, self.addr_bedrock):
            v.addWidget(w)
        layout.addWidget(box)

        box = QGroupBox(t("Tunnel (no port forwarding) — playit.gg"))
        v = QVBoxLayout(box)
        self.tunnel_status = QLabel()
        self.tunnel_status.setWordWrap(True)
        self.tunnel_status.setObjectName("ItemName")
        self.tunnel_status.setTextFormat(Qt.RichText)
        self.tunnel_status.setOpenExternalLinks(True)
        v.addWidget(with_help(self.tunnel_status, t(
            "Free and the easiest option: friends join without opening any ports. "
            "Adds a little latency (distance to the nearest playit server)."), expand=True))
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
        layout.addWidget(box)

        box = QGroupBox(t("Let friends from other homes join"))
        v = QVBoxLayout(box)
        self.port_status = QLabel()
        self.port_status.setWordWrap(True)
        self.port_status.setObjectName("ItemName")
        v.addWidget(with_help(self.port_status, t(
            "Your router must forward the server port. Most routers can do it automatically (UPnP)."), expand=True))
        row = QHBoxLayout()
        self.btn_open = set_kind(QPushButton(t("Open port automatically (UPnP)")), "primary")
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
        self.auto_upnp = QCheckBox(t("Open the port every time the server starts"))
        self.auto_upnp.toggled.connect(self._toggle_auto)
        v.addWidget(self.auto_upnp)
        layout.addWidget(box)

        box = QGroupBox(t("If automatic doesn't work"))
        v = QVBoxLayout(box)
        self.manual = QLabel()
        self.manual.setWordWrap(True)
        self.manual.setTextFormat(Qt.RichText)
        self.manual.setOpenExternalLinks(True)
        self.manual.setTextInteractionFlags(Qt.TextBrowserInteraction)
        v.addWidget(self.manual)
        layout.addWidget(box)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))
        self._router_host = ""

    @property
    def port(self) -> int:
        return self.meta.properties().get_int("server-port", 25565) if self.meta else 25565

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
            run_async(lambda task: network.public_ip(), self._got_public_ip,
                      lambda msg: self.addr_public.set(t("Unavailable (offline?)"), False))
        self.auto_upnp.blockSignals(True)
        self.auto_upnp.setChecked(self.meta.upnp)
        self.auto_upnp.blockSignals(False)
        self.auto_tunnel.blockSignals(True)
        self.auto_tunnel.setChecked(self.meta.tunnel)
        self.auto_tunnel.blockSignals(False)
        self._refresh_tunnel()
        if self.key != getattr(self, "_status_key", None):  # another server: its own port status
            self._status_key = self.key
            self._router_host = None
            self.port_status.setText("")
        if not self.port_status.text():
            self.port_status.setText("⚪ " + t("Port not opened yet."))
        ports = f"TCP {self.port}" + "".join(f", UDP {u}" for u in udp)
        router = self._router_host or "192.168.0.1 / 192.168.1.1"
        self.manual.setText(t(
            "<ol style='margin-left:-20px'>"
            "<li>Open your router page (usually <b>http://{router}</b>) in a browser.</li>"
            "<li>Find <b>Port Forwarding</b> (or NAT / Virtual Server).</li>"
            "<li>Forward <b>{ports}</b> to this PC: <b>{lan}</b>.</li>"
            "<li>Give friends the <b>Internet</b> address above.</li></ol>"
            "<p>Can't forward ports (carrier NAT, dorm or office Wi-Fi, hotspot)? A free tunnel such as "
            "<a href='https://playit.gg'>playit.gg</a> works without it.</p>",
            router=router, ports=ports, lan=t("the 'Same Wi-Fi' address above"),  # not the IP itself (privacy)
        ))

    def _show_public(self, ip: str):
        self.addr_public.set(self._fmt(ip))
        udp = plugins.udp_ports(self.meta) if self.meta else []
        if udp:
            self.addr_bedrock.set(f"{ip} : {udp[0]}")

    def _got_public_ip(self, ip: str):
        NetworkTab._public_ip = ip
        if self.meta:
            self._show_public(ip)

    def _open_port(self):
        port, name, udp = self.port, self.meta.name, plugins.udp_ports(self.meta)
        key = self.key
        self.port_status.setText("⏳ " + t("Looking for the router..."))
        self.btn_open.setEnabled(False)

        def done(res):
            self.btn_open.setEnabled(True)
            if key != self.key:
                return  # the user switched servers meanwhile
            self._router_host = res.router_host
            if res.cgnat:
                self.port_status.setText("🟡 " + t(
                    "Port opened, but the router's internet IP ({ip}) is private. You are probably behind "
                    "carrier NAT, so friends may not get in. See playit.gg below.", ip=mask_address(res.router_ip)))
            else:
                self.port_status.setText("🟢 " + t("Port {port} is open! Friends can join with the Internet address.", port=res.port))
            self.refresh()

        def fail(msg):
            self.btn_open.setEnabled(True)
            if key == self.key:
                self.port_status.setText("🔴 " + msg)

        run_async(lambda task: network.open_port(port, f"Minecraft {name}"[:60], udp_ports=udp), done, fail)

    def _close_port(self):
        port, udp, key = self.port, plugins.udp_ports(self.meta), self.key
        self.port_status.setText("⏳ " + t("Closing port..."))
        run_async(lambda task: network.close_port(port, udp_ports=udp),
                  lambda _: key == self.key and self.port_status.setText("⚪ " + t("Port closed.")),
                  lambda msg: key == self.key and self.port_status.setText("🔴 " + msg))

    # ------------------------------------------------------------ tunnel

    def _refresh_tunnel(self):
        tm = self.tunnel
        if not tm:
            return
        from mc_server_maker.gui import tunnel_manager as tmod

        port = self.port
        texts = {
            tmod.OFF: "⚪ " + t("Tunnel is off."),
            tmod.INSTALLING: "⏳ " + t("Downloading the playit.gg agent..."),
            tmod.STARTING: "⏳ " + t("Starting the tunnel..."),
            tmod.WAITING_CLAIM: "🟡 " + t(
                "First time only: in the browser page that opened, sign in to playit.gg and approve this PC. "
                "Then add a tunnel: <b>Minecraft Java</b>, local port <b>{port}</b>. "
                "(Bedrock players: also add a <b>Minecraft Bedrock</b> tunnel, port <b>19132</b>.)", port=port)
                + (f" <a href='{tm.claim_url}'>{t('Open the link again')}</a>" if tm.claim_url else ""),
            tmod.RUNNING: "🟢 " + t("Tunnel is running. Friends can join with the tunnel address."),
            tmod.ERROR: "🔴 " + (tm.error or t("Tunnel error.")),
        }
        self.tunnel_status.setText(texts.get(tm.state, ""))
        self.btn_tunnel.setText(t("Stop tunnel") if tm.is_active() else t("Start tunnel"))
        set_kind(self.btn_tunnel, "ghost" if tm.is_active() else "primary")
        self.addr_tunnel.set(tm.address or "-", bool(tm.address))
        if port != 25565 and tm.state == tmod.RUNNING:
            self.tunnel_status.setText(self.tunnel_status.text() + " " + t(
                "(Make sure the playit tunnel points to local port {port}.)", port=port))

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
            self.tunnel.set_address(text)

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
        if not network.allow_firewall(self.port, plugins.udp_ports(self.meta)):
            QMessageBox.warning(self, t("Firewall"), t("Could not add the firewall rule."))


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
        p.setBrush(QColor("#ffffff"))
        x = 3 + (self.width() - 22) * k
        p.drawEllipse(QPointF(x + 8, 11), 8, 8)


class AddonCard(QFrame):
    def __init__(self, addon, warning: str, on_toggle, on_remove):
        super().__init__()
        self.setObjectName("Card")
        self.addon = addon
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(addon.name + (f"  <span style='color:{theme.C['muted']}'>{addon.version}</span>" if addon.version else ""))
        name.setObjectName("ItemName")
        name.setTextFormat(Qt.RichText)
        col.addWidget(name)
        bits = [addon.file_name, stats.human_bytes(addon.size)]
        if addon.authors:
            bits.insert(0, ", ".join(addon.authors[:3]))
        col.addWidget(hint(" · ".join(bits)))
        if warning:
            col.addWidget(warn_label("⚠ " + warning))
        row.addLayout(col, 1)
        self.switch = ToggleSwitch(addon.enabled)
        self.switch.setToolTip(t("On / off"))
        self.switch.toggled.connect(lambda on: on_toggle(self, on))
        row.addWidget(self.switch)
        remove = set_kind(QPushButton("✕"), "ghost")
        remove.setToolTip(t("Remove"))
        remove.setFixedWidth(34)
        remove.clicked.connect(lambda: on_remove(self))
        row.addWidget(remove)
        self.setOpacity(addon.enabled)

    def setOpacity(self, enabled: bool):
        self.setStyleSheet("" if enabled else "QLabel { color: %s; }" % theme.C["disabled"])


class DropZone(QFrame):
    def __init__(self, on_files, on_browse):
        super().__init__()
        self.setObjectName("DropZone")
        self.on_files = on_files
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        self.title = QLabel()
        self.title.setObjectName("ItemName")
        self.title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.title)
        row = QHBoxLayout()
        row.addStretch()
        browse = QPushButton(t("Choose files..."))
        browse.clicked.connect(on_browse)
        row.addWidget(browse)
        row.addStretch()
        v.addLayout(row)
        self._set_hover(False)

    def _set_hover(self, hover: bool):
        border = theme.C["accent"] if hover else theme.C["border"]
        bg = theme.C["accent_soft"] if hover else "transparent"
        self.setStyleSheet(f"#DropZone {{ border: 2px dashed {border}; border-radius: 10px; background: {bg}; }}")

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
        outer.setContentsMargins(16, 10, 16, 16)
        outer.setSpacing(10)
        self.notice = warn_label(t("The server is running. Changes apply after a restart."))
        outer.addWidget(self.notice)
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.btn_installed = set_kind(QPushButton(t("Installed")), "segment")
        self.btn_browse = set_kind(QPushButton("🔍 " + t("Find more")), "segment")
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
        row = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("ItemName")
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
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("ServerList")
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setSpacing(3)
        layout.addWidget(self.list, 1)
        self.empty = hint("")
        self.empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty)

    def label(self) -> str:
        return addons.kind_label(self.meta) if self.meta else ""

    def set_server(self, meta) -> None:
        super().set_server(meta)
        if self.label():
            self.browser.set_server(meta)

    def refresh_installed(self):
        self.refresh()

    def _check_updates(self):
        if self.meta:
            browse.check_updates(self, self.meta, self.refresh, self.running, self.btn_updates)

    def refresh(self):
        if not self.meta or not self.label():
            return
        self.drop.title.setText(t("Drag plugin .jar files here") if self.label() == "Plugins" else t("Drag mod .jar files here"))
        self.list.clear()
        items = addons.list_addons(self.meta)
        for a in items:
            self._add_card(a, addons.compatibility_warning(self.meta, a))
        on = sum(1 for a in items if a.enabled)
        self.summary.setText(t("{n} installed · {on} on", n=len(items), on=on))
        self.empty.setText("" if items else t("Nothing installed yet."))
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
        items = addons.list_addons(self.meta)
        self.summary.setText(t("{n} installed · {on} on", n=len(items), on=sum(1 for a in items if a.enabled)))

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
        fill.setAlpha(40)
        p.fillPath(area, fill)
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(theme.C["accent"]), 2)
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


class StatTile(QGroupBox):
    def __init__(self, title: str, spark: Optional[Sparkline] = None):
        super().__init__(title)
        v = QVBoxLayout(self)
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


def _rate(v: float) -> str:
    return stats.human_bytes(v) + "/s"


class CheckRow(QWidget):
    """One line of the join check: ● title — detail."""

    def __init__(self, title: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        self.icon = QLabel("○")
        self.icon.setFixedWidth(18)
        row.addWidget(self.icon)
        self.title = QLabel(title)
        self.title.setObjectName("ItemName")
        self.title.setMinimumWidth(90)
        self.title.setMaximumWidth(150)
        row.addWidget(self.title)
        self.detail = QLabel("-")
        self.detail.setWordWrap(True)
        row.addWidget(self.detail, 1)

    def set(self, state: str, detail: str):
        """state: ok / fail / wait / off"""
        icon, color = {"ok": ("●", theme.C["accent"]), "fail": ("●", theme.C["danger"]),
                       "wait": ("◌", theme.C["warn"]), "off": ("○", theme.C["muted"])}[state]
        self.icon.setText(icon)
        self.icon.setStyleSheet(f"color: {color}; font-size: 12pt;")
        self.detail.setText(detail)
        self.detail.setStyleSheet(f"color: {theme.C['text'] if state in ('ok', 'fail') else theme.C['muted']};")


def _ok_detail(r) -> str:
    bits = [r.version, t("{players} players", players=r.players) if r.players else ""]
    if r.latency_ms is not None:
        bits.append(f"{r.latency_ms:.0f} ms")
    return " · ".join(b for b in bits if b) or t("Reachable")


class JoinCheckBox(QGroupBox):
    INTERVAL_MS = 60_000

    def __init__(self, tab: "StatusTab"):
        super().__init__(t("Can players join?"))
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
        self.when = hint("")
        row.addWidget(self.when, 1)
        self.btn = QPushButton(t("Check now"))
        self.btn.clicked.connect(self.run)
        row.addWidget(self.btn)
        row.addWidget(HelpButton(t(
            "Internet checks are done from outside by mcsrvstat.us and can lag a few minutes behind.")))
        v.addLayout(row)
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
        if self.tab.isVisible() and self.tab.running:
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
        udp = plugins.udp_ports(meta)
        tunnel_addr = self.tab.tunnel.address if self.tab.tunnel else ""

        def work(task):
            res = {"local": joincheck.server_list_ping("127.0.0.1", port)}
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
            self.when.setText("⚠ " + msg)

        run_async(work, done, fail)

    def _show(self, res):
        local, lan, inet = res.get("local"), res.get("lan"), res.get("internet")
        if local and local.ok:
            self.rows["local"].set("ok", _ok_detail(local))
        else:
            self.rows["local"].set("fail", t("The server isn't answering."))
        if lan is None:
            self.rows["lan"].set("off", t("Not connected to a network"))
        elif lan.ok:
            self.rows["lan"].set("ok", _ok_detail(lan))
        else:
            self.rows["lan"].set("fail", t("Blocked on the network. Allow it in Windows Firewall (Network tab)."))
        if inet is None:
            self.rows["internet"].set("off", t("Couldn't check (no internet?)"))
        elif inet.ok:
            self.rows["internet"].set("ok", _ok_detail(inet))
        else:
            self.rows["internet"].set("fail", t("Not reachable from the internet. Open the port or start the tunnel (Network tab)."))
        if "tunnel" in res:
            tr = res["tunnel"]
            if tr.ok:
                self.rows["tunnel"].set("ok", _ok_detail(tr))
            else:
                self.rows["tunnel"].set("fail", t("The tunnel isn't reaching the server. Check the playit tunnel's local port."))
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
        self.notice = hint("")
        layout.addWidget(self.notice)
        self.join = JoinCheckBox(self)
        layout.addWidget(self.join)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cpu = StatTile(t("CPU"), Sparkline(lambda v: f"{v:.0f}%", fixed_max=100))
        self.mem = StatTile(t("Memory"), Sparkline(stats.human_bytes))
        self.down = StatTile(t("Download"), Sparkline(_rate))
        self.up = StatTile(t("Upload"), Sparkline(_rate))
        self.ping = StatTile(t("Average ping"), Sparkline(lambda v: f"{v:.0f} ms"))
        self.disk = StatTile(t("Disk"))
        for i, tile in enumerate((self.cpu, self.mem, self.down, self.up, self.ping, self.disk)):
            grid.addWidget(tile, i // 3, i % 3)
        layout.addLayout(grid)
        about = with_help(t("About these numbers"), t(
            "Download/upload are for the whole PC. Ping is measured from this PC to each player (some networks block it)."))
        about.layout().itemAt(0).widget().setObjectName("Hint")
        layout.addWidget(about)
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

    def refresh(self):
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
        self._disk()

    # sample only while this tab is on screen and the server runs (low-resource)
    def showEvent(self, event):
        super().showEvent(event)
        self._update_timer()
        self._sample()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()
        self.join.timer.stop()

    def _update_timer(self):
        self.join.update_timer()
        if self.isVisible() and self.running:
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
        meta = self.meta

        def work(task):
            return stats.folder_size(meta.folder), sum(stats.folder_size(d) for d in srv.world_dirs(meta) if d.exists())

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
        form.addRow(with_help(t("Software"), t(
            "Pick another software to switch this server to it (for example Paper → Fabric). "
            "The world and settings stay; a full backup is made first.")), self.software)
        self.version = QComboBox()
        form.addRow(t("Update to"), self.version)
        self.version_label = form.labelForField(self.version)
        self.version_status = hint("")
        form.addRow("", self.version_status)
        self.unstable = QCheckBox(t("Show snapshots"))
        self.unstable.toggled.connect(self._reload)
        form.addRow("", with_help(self.unstable, t("Test versions of upcoming updates. They can be unstable.")))
        self.allow_downgrade = QCheckBox(t("Show older versions"))
        self.allow_downgrade.toggled.connect(self._reload)
        form.addRow("", with_help(self.allow_downgrade, t(
            "Going back to an older version can break the world. Keep the backup option on.")))
        self.backup = QCheckBox(t("Back up the whole server first (recommended)"))
        self.backup.setChecked(True)
        form.addRow("", self.backup)
        self.auto_java = QCheckBox(t("Install the right Java automatically"))
        self.auto_java.setChecked(True)
        form.addRow("", self.auto_java)
        row = QHBoxLayout()
        self.btn_upgrade = set_kind(QPushButton(t("Update")), "primary")
        self.btn_upgrade.setMinimumHeight(36)
        self.btn_upgrade.clicked.connect(self._upgrade)
        row.addWidget(self.btn_upgrade)
        row.addWidget(HelpButton(t("Check that your plugins/mods support the new version.")))
        row.addStretch()
        form.addRow("", row)
        layout.addWidget(box)

        self.loader = VersionLoader(self.version, self.version_status)
        self._loaded_for = None

    def refresh(self):
        if not self.meta:
            return
        m = self.meta
        self.cur_version.setText(f"{m.software_name} {m.mc_version}" + (f"  (build {m.build})" if m.build else ""))
        self.cur_java.setText(f"Java {m.java_major} — {m.java_path}")
        running = self.running
        self.btn_upgrade.setEnabled(not running)
        self.btn_java.setEnabled(not running)
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
