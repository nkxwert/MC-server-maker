"""Server tabs: Console / Settings / World / Players / Network / Update."""

import os
import re
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import network, players, plugins, versions
from mc_server_maker.core import server as srv
from mc_server_maker.core.properties import Properties
from mc_server_maker.core.providers import get_provider
from mc_server_maker.gui import theme
from mc_server_maker.gui.create_dialog import VersionLoader, random_seed
from mc_server_maker.gui.runner import ServerRunner
from mc_server_maker.gui.theme import set_kind
from mc_server_maker.gui.widgets import MotdPreview, amp_to_section, color_help, convert_icon, section_to_amp
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
        self.send_btn = set_kind(QPushButton(t("Send")), "primary")
        self.send_btn.clicked.connect(self._send)
        self.save_btn = QPushButton(t("Save world"))
        self.save_btn.setToolTip("save-all")
        self.save_btn.clicked.connect(lambda: self.runner.send(self.key, "save-all"))
        clear = set_kind(QPushButton(t("Clear")), "ghost")
        clear.clicked.connect(self._clear)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        row.addWidget(self.save_btn)
        row.addWidget(clear)
        left.addLayout(row)
        outer.addLayout(left, 1)

        box = QGroupBox(t("Online"))
        box.setFixedWidth(190)
        v = QVBoxLayout(box)
        self.player_count = QLabel("0")
        self.player_count.setObjectName("Big")
        v.addWidget(self.player_count)
        self.player_list = QListWidget()
        v.addWidget(self.player_list, 1)
        self.btn_kick = set_kind(QPushButton(t("Kick")), "danger")
        self.btn_kick.clicked.connect(self._kick)
        v.addWidget(self.btn_kick)
        outer.addWidget(box)

        runner.line.connect(self._on_line)
        runner.players_changed.connect(self._on_players)

    @property
    def controls(self):
        return [self.input, self.send_btn, self.save_btn]

    def refresh(self):
        self.view.clear()
        self.view.setPlaceholderText(t("The server is off. Press Start to see its log here."))
        if self.meta:
            cursor = QTextCursor(self.view.document())
            for ln in self.runner.log_lines(self.key):
                self._insert(cursor, ln)
        self.view.moveCursor(QTextCursor.End)
        self.on_state()

    def on_state(self):
        # update buttons only; don't redraw the log
        for w in self.controls:
            w.setEnabled(self.running)
        self._on_players(self.key)

    def _insert(self, cursor: QTextCursor, line: str):
        cursor.movePosition(QTextCursor.End)
        if not self.view.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(line, _line_format(line))

    def _on_line(self, key: str, line: str):
        if key != self.key:
            return
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self._insert(QTextCursor(self.view.document()), line)
        if at_bottom:
            bar.setValue(bar.maximum())

    def _on_players(self, key: str):
        if key != self.key:
            return
        names = self.runner.online_players(key)
        self.player_list.clear()
        self.player_list.addItems(names)
        self.player_count.setText(str(len(names)))
        self.btn_kick.setEnabled(bool(names) and self.running)

    def _kick(self):
        item = self.player_list.currentItem()
        if not item:
            QMessageBox.information(self, t("Kick"), t("Select a player first."))
            return
        self.runner.send(self.key, f"kick {item.text()}")

    def _clear(self):
        self.runner.clear_log(self.key)
        self.view.clear()

    def _send(self):
        cmd = self.input.text().strip().lstrip("/")
        if cmd and self.runner.send(self.key, cmd):
            self.input.remember(cmd)
            self.input.clear()


# ================================================================== settings


class PropertiesDialog(QDialog):
    """Edit every key in server.properties."""

    def __init__(self, parent, path: Path):
        super().__init__(parent)
        self.setWindowTitle(t("All server.properties"))
        self.resize(620, 640)
        self.props = Properties(path)
        layout = QVBoxLayout(self)
        layout.addWidget(hint(t("Every setting in server.properties. Changes apply on next start.")))
        self.filter = QLineEdit(placeholderText=t("Search..."))
        self.filter.textChanged.connect(self._filter)
        layout.addWidget(self.filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([t("Key"), t("Value")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for key in sorted(self.props.values):
            self._add_row(key, self.props.values[key])
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

    def _add_row(self, key: str, value: str):
        r = self.table.rowCount()
        self.table.insertRow(r)
        k = QTableWidgetItem(key)
        k.setFlags(k.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 0, k)
        self.table.setItem(r, 1, QTableWidgetItem(value))

    def _add_new(self):
        key, ok = QInputDialog.getText(self, t("Add setting"), t("Key (e.g. simulation-distance):"))
        key = key.strip()
        if ok and key and key not in self.props.values:
            self._add_row(key, "")
            self.table.scrollToBottom()

    def _filter(self, text: str):
        text = text.lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, text not in self.table.item(r, 0).text().lower())

    def _save(self):
        for r in range(self.table.rowCount()):
            key = self.table.item(r, 0).text()
            value = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            if self.props.values.get(key) != value:
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
        form = QFormLayout(box)
        self.name = QLineEdit()
        form.addRow(t("Name"), self.name)
        self.motd = QPlainTextEdit()
        self.motd.setFixedHeight(56)
        self.motd.textChanged.connect(self._update_preview)
        form.addRow(t("Description\n(MOTD, 2 lines)"), self.motd)
        form.addRow("", hint(color_help()))
        icon_row = QHBoxLayout()
        pick = QPushButton(t("Choose image..."))
        pick.clicked.connect(self._pick_icon)
        remove = set_kind(QPushButton(t("Remove")), "ghost")
        remove.clicked.connect(self._remove_icon)
        icon_row.addWidget(pick)
        icon_row.addWidget(remove)
        icon_row.addWidget(hint(t("Any image; resized to 64×64 automatically.")), 1)
        form.addRow(t("Icon"), icon_row)
        self.preview = MotdPreview()
        form.addRow(t("Preview"), self.preview)
        layout.addWidget(box)

        box = QGroupBox(t("Game"))
        form = QFormLayout(box)
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
        form.addRow(t("Port"), self.port)
        self.view_distance = QSpinBox(minimum=2, maximum=32)
        form.addRow(t("View distance"), self.view_distance)
        self.checks = {}
        for key, label in (
            ("online-mode", "Online mode (off = allow non-premium accounts)"),
            ("pvp", "PvP"),
            ("hardcore", "Hardcore"),
            ("white-list", "Whitelist only"),
            ("allow-flight", "Allow flight (recommended with mods/plugins)"),
            ("enable-command-block", "Command blocks"),
        ):
            cb = QCheckBox(t(label))
            self.checks[key] = cb
            form.addRow("", cb)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64)
        form.addRow(t("Memory (RAM)"), self.ram)
        all_props = set_kind(QPushButton(t("Edit all server.properties...")), "ghost")
        all_props.clicked.connect(self._edit_all)
        form.addRow("", all_props)
        layout.addWidget(box)

        self.bedrock_box = QGroupBox(t("Bedrock players (phone / console / Windows)"))
        v = QVBoxLayout(self.bedrock_box)
        v.addWidget(hint(t("Installs Geyser + Floodgate so Bedrock Edition players can join with their Xbox account.")))
        self.bedrock_status = QLabel()
        self.bedrock_status.setObjectName("ItemName")
        v.addWidget(self.bedrock_status)
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
        self.max_players.setValue(p.get_int("max-players", 20))
        gm = srv.parse_choice(p.get("gamemode"), srv.GAMEMODES, "survival")
        self.gamemode.setCurrentIndex(self.gamemode.findData(gm))
        diff = srv.parse_choice(p.get("difficulty"), srv.DIFFICULTIES, "easy")
        self.difficulty.setCurrentIndex(self.difficulty.findData(diff))
        self.port.setValue(p.get_int("server-port", 25565))
        self.view_distance.setValue(p.get_int("view-distance", 10))
        defaults = {"online-mode": True, "pvp": True}
        for key, cb in self.checks.items():
            cb.setChecked(p.get_bool(key, defaults.get(key, False)))
        self.ram.setValue(max(1, self.meta.ram_mb // 1024))
        self._update_preview()
        self.on_state()

    def on_state(self):
        # only update the notice so unsaved edits are kept
        self.notice.setText(t("The server is running. Saved changes apply after a restart.") if self.running else "")
        self.notice.setVisible(self.running)
        self._refresh_bedrock()

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
        self.on_changed()

    def _remove_icon(self):
        self.icon_path.unlink(missing_ok=True)
        self._update_preview()
        self.on_changed()

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
        lines = self.motd.toPlainText().splitlines()
        v = self.meta.mc_version
        p = self.meta.properties()
        p.set("motd", amp_to_section("\n".join(lines[:2])))
        p.set("max-players", self.max_players.value())
        p.set("gamemode", srv.gamemode_value(self.gamemode.currentData(), v))
        p.set("difficulty", srv.difficulty_value(self.difficulty.currentData(), v))
        p.set("server-port", self.port.value())
        p.set("view-distance", self.view_distance.value())
        for key, cb in self.checks.items():
            p.set(key, cb.isChecked())
        p.set("enforce-whitelist", self.checks["white-list"].isChecked())
        p.save()
        self.meta.name = name
        self.meta.ram_mb = self.ram.value() * 1024
        self.meta.save()
        srv.write_start_scripts(self.meta)
        self.on_changed()
        QMessageBox.information(self, t("Save"), t("Saved.") + ("\n" + t("Restart the server to apply.") if self.running else ""))


# ===================================================================== world


class WorldTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        self.running_notice = warn_label(t("Stop the server to change the world."))
        layout.addWidget(self.running_notice)

        box = QGroupBox(t("Current world"))
        form = QFormLayout(box)
        self.info_seed = QLabel()
        self.info_seed.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_type = QLabel()
        self.info_exists = QLabel()
        form.addRow(t("Seed"), self.info_seed)
        form.addRow(t("World type"), self.info_type)
        form.addRow(t("Status"), self.info_exists)
        layout.addWidget(box)

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
        v.addWidget(hint(t("Singleplayer worlds are in .minecraft/saves. Choose the folder with level.dat, or a zip.")))
        row = QHBoxLayout()
        self.btn_import_dir = QPushButton(t("From folder..."))
        self.btn_import_dir.clicked.connect(self._import_dir)
        self.btn_import_zip = QPushButton(t("From zip..."))
        self.btn_import_zip.clicked.connect(self._import_zip)
        row.addWidget(self.btn_import_dir)
        row.addWidget(self.btn_import_zip)
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


# =================================================================== players


class PlayersTab(ServerTab):
    KINDS = (("ops", "Operators (OP)", "op", "deop"), ("whitelist", "Whitelist", "whitelist add", "whitelist remove"))

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 16)
        self.hint = hint("")
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        self.lists = {}
        for kind, title, add_cmd, remove_cmd in self.KINDS:
            box = QGroupBox(t(title))
            v = QVBoxLayout(box)
            lst = QListWidget()
            v.addWidget(lst)
            buttons = QHBoxLayout()
            add = QPushButton(t("Add"))
            add.clicked.connect(lambda _=False, k=kind, c=add_cmd: self._add(k, c))
            rem = set_kind(QPushButton(t("Remove")), "ghost")
            rem.clicked.connect(lambda _=False, k=kind, c=remove_cmd: self._remove(k, c))
            buttons.addWidget(add)
            buttons.addWidget(rem)
            v.addLayout(buttons)
            self.lists[kind] = lst
            row.addWidget(box)
        layout.addLayout(row)

    def refresh(self):
        if not self.meta:
            return
        for kind, lst in self.lists.items():
            lst.clear()
            lst.addItems(players.list_names(self.meta.folder, kind))
        online = self.meta.properties().get_bool("online-mode", True)
        self.hint.setText(
            (t("Server is running: changes are sent as console commands.") + " " if self.running else "")
            + (t("Online mode is on: use exact Minecraft names.") if online else t("Offline mode."))
        )

    def _add(self, kind: str, command: str):
        name, ok = QInputDialog.getText(self, t("Add player"), t("Minecraft name:"))
        name = name.strip()
        if not ok or not name:
            return
        if self.running:
            self.runner.send(self.key, f"{command} {name}")
            QTimer.singleShot(1500, self.refresh)
            return
        folder = self.meta.folder
        online = self.meta.properties().get_bool("online-mode", True)
        run_async(
            lambda task: players.add(folder, kind, name, online),
            lambda _: self.refresh(),
            lambda msg: QMessageBox.warning(self, t("Add player"), msg),
        )

    def _remove(self, kind: str, command: str):
        item = self.lists[kind].currentItem()
        if not item:
            return
        name = item.text()
        if self.running:
            self.runner.send(self.key, f"{command} {name}")
            QTimer.singleShot(1500, self.refresh)
        else:
            players.remove(self.meta.folder, kind, name)
            self.refresh()


# =================================================================== network


class AddressRow(QWidget):
    def __init__(self, title: str, sub: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        col = QVBoxLayout()
        col.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("ItemName")
        col.addWidget(title_label)
        col.addWidget(hint(sub))
        row.addLayout(col, 1)
        self.value = QLabel("-")
        self.value.setObjectName("Big")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.value)
        self.copy = QPushButton(t("Copy"))
        self.copy.clicked.connect(self._copy)
        row.addWidget(self.copy)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.value.text())
        self.copy.setText(t("Copied ✓"))
        QTimer.singleShot(1200, lambda: self.copy.setText(t("Copy")))

    def set(self, text: str, enabled: bool = True):
        self.value.setText(text)
        self.copy.setEnabled(enabled)


class NetworkTab(ServerTab):
    _public_ip = None  # looked up once per app run

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box = QGroupBox(t("Addresses"))
        v = QVBoxLayout(box)
        self.addr_local = AddressRow(t("This PC"), t("Playing on this computer"))
        self.addr_lan = AddressRow(t("Same Wi-Fi"), t("People in the same home"))
        self.addr_public = AddressRow(t("Internet"), t("Friends in other homes"))
        self.addr_bedrock = AddressRow(t("Bedrock (Internet)"), t("Phone / console players: address + port"))
        for w in (self.addr_local, self.addr_lan, self.addr_public, self.addr_bedrock):
            v.addWidget(w)
        layout.addWidget(box)

        box = QGroupBox(t("Let friends from other homes join"))
        v = QVBoxLayout(box)
        v.addWidget(hint(t("Your router must forward the server port. Most routers can do it automatically (UPnP).")))
        self.port_status = QLabel()
        self.port_status.setWordWrap(True)
        self.port_status.setObjectName("ItemName")
        v.addWidget(self.port_status)
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
            router=router, ports=ports, lan=lan,
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
        self.port_status.setText("⏳ " + t("Looking for the router..."))
        self.btn_open.setEnabled(False)

        def done(res):
            self.btn_open.setEnabled(True)
            self._router_host = res.router_host
            if res.cgnat:
                self.port_status.setText("🟡 " + t(
                    "Port opened, but the router's internet IP ({ip}) is private. You are probably behind "
                    "carrier NAT, so friends may not get in. See playit.gg below.", ip=res.router_ip))
            else:
                self.port_status.setText("🟢 " + t("Port {port} is open! Friends can join with the Internet address.", port=res.port))
            self.refresh()

        def fail(msg):
            self.btn_open.setEnabled(True)
            self.port_status.setText("🔴 " + msg)

        run_async(lambda task: network.open_port(port, f"Minecraft {name}"[:60], udp_ports=udp), done, fail)

    def _close_port(self):
        port, udp = self.port, plugins.udp_ports(self.meta)
        self.port_status.setText("⏳ " + t("Closing port..."))
        run_async(lambda task: network.close_port(port, udp_ports=udp),
                  lambda _: self.port_status.setText("⚪ " + t("Port closed.")),
                  lambda msg: self.port_status.setText("🔴 " + msg))

    def _toggle_auto(self, on: bool):
        if self.meta:
            self.meta.upnp = on
            self.meta.save()

    def _firewall(self):
        if not network.allow_firewall(self.port, plugins.udp_ports(self.meta)):
            QMessageBox.warning(self, t("Firewall"), t("Could not add the firewall rule."))


# ==================================================================== update


class UpgradeTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        self.running_notice = warn_label(t("Stop the server to update it."))
        layout.addWidget(self.running_notice)

        box = QGroupBox(t("Current"))
        form = QFormLayout(box)
        self.cur_version = QLabel()
        self.cur_java = QLabel()
        self.cur_java.setWordWrap(True)
        form.addRow(t("Version"), self.cur_version)
        form.addRow("Java", self.cur_java)
        layout.addWidget(box)

        box = QGroupBox(t("Update version"))
        form = QFormLayout(box)
        self.version = QComboBox()
        form.addRow(t("New version"), self.version)
        self.version_status = hint("")
        form.addRow("", self.version_status)
        self.unstable = QCheckBox(t("Show snapshots"))
        self.unstable.toggled.connect(self._reload)
        form.addRow("", self.unstable)
        self.allow_downgrade = QCheckBox(t("Show older versions (may break the world)"))
        self.allow_downgrade.toggled.connect(self._reload)
        form.addRow("", self.allow_downgrade)
        self.backup = QCheckBox(t("Back up the whole server first (recommended)"))
        self.backup.setChecked(True)
        form.addRow("", self.backup)
        self.auto_java = QCheckBox(t("Install the right Java automatically"))
        self.auto_java.setChecked(True)
        form.addRow("", self.auto_java)
        form.addRow("", hint(t("Check that your plugins/mods support the new version.")))
        self.btn_upgrade = set_kind(QPushButton(t("Update")), "primary")
        self.btn_upgrade.setMinimumHeight(38)
        self.btn_upgrade.clicked.connect(self._upgrade)
        form.addRow(self.btn_upgrade)
        layout.addWidget(box)

        row = QHBoxLayout()
        self.btn_java = set_kind(QPushButton(t("Re-detect / reinstall Java")), "ghost")
        self.btn_java.clicked.connect(self._fix_java)
        row.addWidget(self.btn_java)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))
        self.loader = VersionLoader(self.version, self.version_status)
        self._loaded_for = None

    def refresh(self):
        if not self.meta:
            return
        m = self.meta
        self.cur_version.setText(f"{m.software_name} {m.mc_version}" + (f"  (build {m.build})" if m.build else ""))
        self.cur_java.setText(f"Java {m.java_major} — {m.java_path}")
        running = self.running
        self.running_notice.setVisible(running)
        self.btn_upgrade.setEnabled(not running)
        self.btn_java.setEnabled(not running)
        if self._loaded_for != (m.folder, m.software, m.mc_version):
            self._reload()

    def _reload(self):
        if not self.meta:
            return
        m = self.meta
        self._loaded_for = (m.folder, m.software, m.mc_version)
        provider = get_provider(m.software)
        current = m.mc_version
        downgrade = self.allow_downgrade.isChecked()
        unstable = self.unstable.isChecked()

        def newer(v: str) -> bool:
            if v == current:
                return False
            if downgrade:
                return True
            # Vanilla/Fabric snapshots (e.g. 25w14a) can't be compared by number; use list order (newest first)
            if m.software in ("vanilla", "fabric"):
                order = provider.list_versions(unstable)  # already cached
                if current in order:
                    return order.index(v) < order.index(current)
            return versions.version_key(v) > versions.version_key(current)

        self.loader.load(provider, unstable, filter_fn=newer)

    def _upgrade(self):
        new = self.version.currentData()
        if not new:
            QMessageBox.information(self, t("Update"), t("You're on the latest version."))
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

    def _fix_java(self):
        m = self.meta
        auto = self.auto_java.isChecked()
        self.run_task("Java", lambda task: srv.change_java(m, auto, task))
        self.on_changed()
