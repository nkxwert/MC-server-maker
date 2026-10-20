"""Backup manager (with automatic backups when a server stops) and the player manager."""

import html
import re
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mc_server_maker.core import players as pl
from mc_server_maker.core import server as srv
from mc_server_maker.core import stats
from mc_server_maker.core.properties import Properties
from mc_server_maker.gui import theme
from mc_server_maker.gui.anim import FadeInDialog
from mc_server_maker.gui.runner import ServerRunner
from mc_server_maker.gui.theme import fit_to_screen, set_kind
from mc_server_maker.gui.widgets import ask
from mc_server_maker.gui.workers import TaskDialog, run_async
from mc_server_maker.i18n import t


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


def _open_folder(path: Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _row_list() -> QListWidget:
    """A list of rows with a thin line between them (like the plugin list)."""
    lst = QListWidget()
    lst.setObjectName("AddonList")
    lst.setSelectionMode(QAbstractItemView.NoSelection)
    lst.setFocusPolicy(Qt.NoFocus)
    return lst


def _add_row(lst: QListWidget, row: QFrame) -> None:
    item = QListWidgetItem()
    item.setSizeHint(row.sizeHint())
    lst.addItem(item)
    lst.setItemWidget(item, row)


def _run_task(parent, runner: ServerRunner, key: str, title: str, fn) -> bool:
    """TaskDialog that marks the server busy (Start waits), like ServerTab.run_task."""
    if key in runner.busy:
        QMessageBox.information(parent, title, t("Wait until the current task on this server is finished."))
        return False
    runner.busy.add(key)
    try:
        dlg = TaskDialog(parent, title, fn)
        dlg.exec()
    finally:
        runner.busy.discard(key)
    return dlg.succeeded()


# ============================================================ automatic backups


class _Notifier(QObject):
    changed = Signal(str)  # (server folder) a backup was made, restored or deleted


backups_changed = _Notifier()
_auto: Dict[str, object] = {}  # server folder -> worker of its running automatic backup


def auto_backups_running() -> bool:
    return bool(_auto)


def auto_backup_running(key: str) -> bool:
    return key in _auto


def auto_backup_after_stop(runner: ServerRunner, key: str) -> bool:
    """Back up the world in the background if the server has automatic backups on.

    The server is marked busy meanwhile, so Start waits; quitting waits for it too (wait_for_stop)."""
    if key in _auto or key in runner.busy or runner.is_running(key):
        return False
    try:  # from disk: the switch may have changed while it ran
        meta = srv.ServerMeta.load(Path(key))
        if not meta.auto_backup or not srv.world_dirs(meta)[0].is_dir():
            return False
    except (OSError, ValueError, TypeError, srv.ServerError):
        return False
    keep = meta.auto_backup_keep if meta.auto_backup_keep > 0 else 5

    def work(task):
        path = srv.backup_server(meta, srv.AUTO_LABEL, worlds_only=True, task=task)
        srv.prune_auto_backups(meta, keep)  # only once the new one is safely written
        return path

    def finish(line: str):
        _auto.pop(key, None)
        runner.busy.discard(key)
        runner.system_line(key, line)
        backups_changed.changed.emit(key)

    runner.busy.add(key)
    _auto[key] = run_async(work, lambda _p: finish(t("Automatic backup saved.")),
                           lambda err: finish(t("Automatic backup failed: {err}", err=err)))
    return True


# ============================================================== backup manager


def kind_text(info: srv.BackupInfo) -> str:
    """'Automatic (on stop)', 'Before update · → 1.21.4'..."""
    if info.kind == "auto":
        return t("Automatic (on stop)")
    if info.kind == "manual":
        return t("Made by you")
    if info.kind == "update":
        return t("Before update") + " · → " + info.label
    if info.kind == "restore":
        return t("Before restore")
    if info.label == "world-before-import":
        return t("Before importing a world")
    if info.label == "world-before-reset":
        return t("Before a new world")
    return t("Other") + (" · " + info.label if info.label else "")


class BackupRow(QFrame):
    def __init__(self, info: srv.BackupInfo, on_restore: Callable[[srv.BackupInfo], None]):
        super().__init__()
        self.setObjectName("Card")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 9, 0, 9)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        when = QLabel(time.strftime("%Y-%m-%d %H:%M", time.localtime(info.when)))
        when.setObjectName("ItemName")
        col.addWidget(when)
        kind = _hint(kind_text(info))
        kind.setWordWrap(False)
        kind.setToolTip(info.path.name)
        col.addWidget(kind)
        row.addLayout(col, 1)
        size = _hint(stats.human_bytes(info.size))
        size.setWordWrap(False)
        row.addWidget(size)
        restore = QPushButton(t("Restore"))
        restore.clicked.connect(lambda: on_restore(info))
        row.addWidget(restore)


class BackupsDialog(FadeInDialog):
    """The server's backups, newest first, with Restore; automatic-backup options."""

    def __init__(self, parent, runner: ServerRunner, meta: srv.ServerMeta):
        super().__init__(parent)
        self.runner, self.meta, self.key = runner, meta, str(meta.folder)
        self.setWindowTitle(t("Backups"))
        fit_to_screen(self, 620, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self.summary = _hint("")
        layout.addWidget(self.summary)
        self.list = _row_list()
        layout.addWidget(self.list, 1)
        self.empty = _hint(t("No backups yet."))
        self.empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty, 1)

        self.auto = QCheckBox(t("Back up automatically when the server stops"))
        self.auto.setChecked(meta.auto_backup)
        self.auto.toggled.connect(self._options_changed)
        layout.addWidget(self.auto)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        self.keep = QComboBox()
        for n in srv.AUTO_BACKUP_KEEP_CHOICES:
            self.keep.addItem(t("Keep the last {n} automatic backups", n=n), n)
        index = self.keep.findData(meta.auto_backup_keep)
        self.keep.setCurrentIndex(index if index >= 0 else self.keep.findData(5))
        self.keep.currentIndexChanged.connect(self._options_changed)
        row.addWidget(self.keep)
        row.addStretch()
        layout.addLayout(row)
        note = _hint(t("Backups you make, and the ones from before an update or a restore, are never deleted automatically."))
        note.setContentsMargins(24, 0, 0, 0)
        layout.addWidget(note)

        row = QHBoxLayout()
        self.btn_backup = set_kind(QPushButton(t("Back up now")), "primary")
        self.btn_backup.clicked.connect(self._backup)
        row.addWidget(self.btn_backup)
        open_btn = set_kind(QPushButton(t("Open backups folder")), "ghost")
        open_btn.clicked.connect(lambda: _open_folder(self.meta.folder / srv.BACKUP_DIR))
        row.addWidget(open_btn)
        row.addStretch()
        close = QPushButton(t("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        runner.state_changed.connect(self._on_state)
        backups_changed.changed.connect(self._on_changed)
        self.refresh()

    @property
    def locked(self) -> bool:
        return self.runner.is_running(self.key) or self.key in self.runner.pending

    def _on_state(self, key: str, _state: str):
        if key == self.key:
            self.refresh()

    def _on_changed(self, key: str):
        if key == self.key:
            self.refresh()

    def refresh(self):
        infos = srv.backup_infos(self.meta)
        self.list.clear()
        for info in infos:
            _add_row(self.list, BackupRow(info, self._restore))
        self.list.setVisible(bool(infos))
        self.empty.setVisible(not infos)
        bits = [t("{n} backups", n=len(infos)), t("{size} in total", size=stats.human_bytes(sum(b.size for b in infos)))]
        try:
            bits.append(t("{size} free on the disk", size=stats.human_bytes(shutil.disk_usage(self.meta.folder).free)))
        except OSError:
            pass
        if auto_backup_running(self.key):
            bits.append(t("Saving an automatic backup..."))
        self.summary.setText(" · ".join(bits))
        self.btn_backup.setEnabled(not self.locked)
        self.btn_backup.setToolTip(t("Stop the server to back up the world.") if self.locked else "")

    def _options_changed(self, *_):
        self.meta.auto_backup = self.auto.isChecked()
        self.meta.auto_backup_keep = int(self.keep.currentData() or 5)
        self.keep.setEnabled(self.meta.auto_backup)
        try:
            self.meta.save()
        except OSError as e:
            QMessageBox.warning(self, t("Backups"), str(e))

    def showEvent(self, event):
        super().showEvent(event)
        self.keep.setEnabled(self.auto.isChecked())

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
        _run_task(self, self.runner, self.key, t("Backups"),
                  lambda task: srv.backup_server(meta, srv.MANUAL_LABEL, worlds_only=True, task=task))
        backups_changed.changed.emit(self.key)

    def _restore(self, info: srv.BackupInfo):
        title = t("Restore")
        if self.locked:
            QMessageBox.information(self, title, t("Stop the server first, then restore the backup."))
            return
        if self.key in self.runner.busy:
            QMessageBox.information(self, title, t("Wait until the current task on this server is finished."))
            return
        try:
            srv.find_world_root(info.path)  # a zip without a world (or a broken one) is refused here
            srv.level_name(self.meta)
        except (srv.ServerError, OSError) as e:
            QMessageBox.warning(self, title, str(e))
            return
        text = t("Restore this backup? The current world is backed up first ('Before restore').")
        if srv.backup_has_server_files(info.path):
            text += "\n\n" + t("Only the world is restored from this backup.")
        if not ask(self, title, text, t("Restore"), t("Cancel")):
            return
        meta, path = self.meta, info.path
        ok = _run_task(self, self.runner, self.key, title, lambda task: srv.restore_backup(meta, path, task))
        backups_changed.changed.emit(self.key)
        if ok:
            QMessageBox.information(self, title, t("Restored. The server opens this world next time it starts."))


# ============================================================== player manager

NAME_RE = re.compile(r"[A-Za-z0-9_.]{1,16}")  # Java names; "." starts a Bedrock (Floodgate) name
FILTERS = ("all", "online", "op", "banned")


def _badge(text: str, color: str) -> str:
    return (f"&nbsp;&nbsp;<span style='color:{color}; font-size:9pt; font-weight:600'>"
            f"{html.escape(text)}</span>")


class PlayerRow(QFrame):
    def __init__(self, p: pl.Player, running: bool, act: Callable[[str, pl.Player], None]):
        super().__init__()
        self.setObjectName("Card")
        C = theme.C
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 8)
        row.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(1)
        dot = f"<span style='color:{C['ok'] if p.online else C['disabled']}'>●</span>&nbsp; "
        badges = ""
        if p.op:
            badges += _badge("OP", C["info"])
        if p.whitelisted:
            badges += _badge(t("Whitelist"), C["ok"])
        if p.banned:
            badges += _badge(t("Banned"), C["danger"])
        name = QLabel(dot + html.escape(p.name) + badges)
        name.setObjectName("ItemName")
        name.setTextFormat(Qt.RichText)
        name.setToolTip(t("Online") if p.online else t("Offline"))
        col.addWidget(name)
        if p.banned and p.ban_reason:
            reason = _hint(t("Reason: {reason}", reason=p.ban_reason))
            reason.setWordWrap(False)
            col.addWidget(reason)
        row.addLayout(col, 1)

        def button(text: str, action: str, shown: bool = True, kind: str = "ghost", width_of=()) -> None:
            # every row has the same slots (a missing action keeps its space), so the columns line up
            b = set_kind(QPushButton(text), kind)
            b.clicked.connect(lambda: act(action, p))
            if width_of:
                pad = b.sizeHint().width() - b.fontMetrics().horizontalAdvance(text)
                b.setMinimumWidth(pad + max(b.fontMetrics().horizontalAdvance(s) for s in width_of))
            policy = b.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            b.setSizePolicy(policy)
            b.setVisible(shown)
            row.addWidget(b)

        button(t("Remove OP") if p.op else t("Give OP"), "deop" if p.op else "op",
               width_of=(t("Remove OP"), t("Give OP")))
        button(t("Kick"), "kick", p.online and running)
        button(t("Remove from whitelist"), "unwhitelist", p.whitelisted)
        button(t("Unban") if p.banned else t("Ban"), "pardon" if p.banned else "ban",
               kind="ghost" if p.banned else "danger", width_of=(t("Unban"), t("Ban")))


class PlayersDialog(FadeInDialog):
    """Everyone this server knows: online players, the whitelist, OPs, bans and recent visitors.

    While the server runs, changes go through its console (it owns the files then and writes them
    back); while it's stopped, the JSON files are edited directly."""

    def __init__(self, parent, runner: ServerRunner, key: str):
        super().__init__(parent)
        self.runner, self.key, self.folder = runner, key, Path(key)
        self.filter = "all"
        self.setWindowTitle(t("Players"))
        fit_to_screen(self, 720, 600)
        self.setMinimumSize(self.size().boundedTo(QSize(720, 520)))  # opens at its full size right away
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        self.name = QLineEdit(placeholderText=t("Nickname"))
        self.name.setMaxLength(16)
        self.name.returnPressed.connect(self._add)
        row.addWidget(self.name, 1)
        self.btn_add = set_kind(QPushButton(t("Add to whitelist")), "primary")
        self.btn_add.clicked.connect(self._add)
        row.addWidget(self.btn_add)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setObjectName("FieldError")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        layout.addWidget(self.error)
        self.whitelist = QCheckBox(t("Whitelist on — only players on the list can join"))
        self.whitelist.toggled.connect(self._toggle_whitelist)
        layout.addWidget(self.whitelist)
        self.mode = _hint("")
        layout.addWidget(self.mode)

        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.segments = QButtonGroup(self)
        self.seg_buttons = {}
        for i, f in enumerate(FILTERS):
            b = set_kind(QPushButton(), "segment")
            b.setCheckable(True)
            self.segments.addButton(b, i)
            self.seg_buttons[f] = b
            seg.addWidget(b)
        seg.addStretch()
        self.seg_buttons["all"].setChecked(True)
        self.segments.idClicked.connect(self._set_filter)
        layout.addLayout(seg)
        self.list = _row_list()
        layout.addWidget(self.list, 1)
        self.empty = _hint("")
        self.empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty, 1)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(t("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        self._later = QTimer(self)  # the server writes its JSON files a moment after a command
        self._later.setSingleShot(True)
        self._later.setInterval(1500)
        self._later.timeout.connect(self.refresh)
        runner.players_changed.connect(self._on_key)
        runner.state_changed.connect(self._on_state)
        self.refresh()

    # ------------------------------------------------------------------ state

    @property
    def running(self) -> bool:
        return self.runner.is_running(self.key)

    def _props(self) -> Properties:
        return Properties(self.folder / "server.properties")

    def _online_mode(self) -> bool:
        return self._props().get_bool("online-mode", True)

    def _on_key(self, key: str):
        if key == self.key:
            self.refresh()

    def _on_state(self, key: str, _state: str):
        self._on_key(key)

    def _set_filter(self, index: int):
        self.filter = FILTERS[index]
        self.refresh()

    def refresh(self):
        try:
            whitelist_on = self._props().get_bool("white-list", False)
        except OSError:
            whitelist_on = False
        self.whitelist.blockSignals(True)
        self.whitelist.setChecked(whitelist_on)
        self.whitelist.blockSignals(False)
        self.mode.setText(t("Changes are sent to the running server.") if self.running
                          else t("The server is stopped. Changes are saved to its files."))
        people = pl.roster(self.folder, self.runner.online_players(self.key) if self.running else ())
        shown = {
            "all": people,
            "online": [p for p in people if p.online],
            "op": [p for p in people if p.op],
            "banned": [p for p in people if p.banned],
        }
        names = {"all": t("All"), "online": t("Online"), "op": "OP", "banned": t("Banned")}
        for f, b in self.seg_buttons.items():
            b.setText(f"{names[f]}  {len(shown[f])}")
        scroll = self.list.verticalScrollBar().value()
        self.list.clear()
        for p in shown[self.filter]:
            _add_row(self.list, PlayerRow(p, self.running, self._act))
        self.list.verticalScrollBar().setValue(scroll)
        self.list.setVisible(bool(shown[self.filter]))
        self.empty.setVisible(not shown[self.filter])
        self.empty.setText(t("No players yet. Players show up here once they join or are added.")
                           if self.filter == "all" else t("No one here."))

    # ---------------------------------------------------------------- changes

    def _can_change(self) -> bool:
        if not self.running and self.key in self.runner.pending:
            QMessageBox.information(self, t("Players"), t("Wait until the server has started, then try again."))
            return False
        return True

    def _command(self, command: str) -> None:
        self.runner.send(self.key, command)
        self._later.start()

    def _edit_files(self, fn, on_fail: Optional[Callable[[str], None]] = None, on_done=None) -> None:
        """Change the JSON files in the background (a Mojang lookup can take a moment)."""
        def done(result):
            self.refresh()
            if on_done:
                on_done(result)

        def fail(msg: str):
            self.refresh()
            if on_fail:
                on_fail(msg)
            else:
                QMessageBox.warning(self, t("Players"), msg)

        run_async(lambda task: fn(), done, fail)

    def _add(self):
        name = self.name.text().strip()
        self.error.setVisible(False)
        if not NAME_RE.fullmatch(name):
            self._show_error(t("Enter a Minecraft nickname: letters, numbers and _ (up to 16)."))
            return
        if not self._can_change():
            return
        if self.running:
            self._command(f"whitelist add {name}")
            self.name.clear()
            return
        folder, online = self.folder, self._online_mode()
        self.btn_add.setEnabled(False)

        def done(_real):
            self.btn_add.setEnabled(True)
            self.name.clear()

        def fail(msg):  # the typed name stays in the field, to fix or retry
            self.btn_add.setEnabled(True)
            self._show_error(msg)

        self._edit_files(lambda: pl.add(folder, "whitelist", name, online), fail, done)

    def _show_error(self, msg: str):
        self.error.setText(msg)
        self.error.setVisible(True)

    def _toggle_whitelist(self, on: bool):
        if not self._can_change():
            self.refresh()
            return
        if on and not any(p.whitelisted for p in pl.roster(self.folder)) and not ask(
                self, t("Whitelist"), t("The whitelist is empty, so nobody can join until you add players. Turn it on anyway?"),
                t("Turn on"), t("Cancel")):
            self.refresh()
            return
        try:
            p = self._props()
            p.set("white-list", on)
            p.set("enforce-whitelist", on)  # also removes online players who aren't on it
            p.save()
        except OSError as e:
            QMessageBox.warning(self, t("Players"), str(e))
            self.refresh()
            return
        if self.running:  # a running server keeps its own switch (and writes it back): change it now
            self._command("whitelist on" if on else "whitelist off")

    def _act(self, action: str, p: pl.Player):
        if not self._can_change():
            return
        name, folder = p.name, self.folder
        if not NAME_RE.fullmatch(name):  # a hand-edited file: never put it in a command
            QMessageBox.warning(self, t("Players"), t("'{name}' isn't a valid nickname.", name=name))
            return
        reason = ""
        if action == "op" and not ask(
                self, t("Give OP"),
                t("OP players can use every command, including changing the world and banning others. "
                  "Only give it to people you trust."), t("Give OP"), t("Cancel")):
            return
        if action == "ban":
            reason, ok = QInputDialog.getText(self, t("Ban"), t("Ban {name}? Reason (optional):", name=name))
            if not ok:
                return
            reason = " ".join(reason.split())  # one line: it goes into a console command
        if self.running:
            self._command({
                "op": f"op {name}", "deop": f"deop {name}", "kick": f"kick {name}",
                "unwhitelist": f"whitelist remove {name}", "pardon": f"pardon {name}",
                "ban": f"ban {name}" + (f" {reason}" if reason else ""),
            }[action])
            return
        online = self._online_mode()
        work = {
            "op": lambda: pl.add(folder, "ops", name, online),
            "deop": lambda: pl.remove(folder, "ops", name),
            "unwhitelist": lambda: pl.remove(folder, "whitelist", name),
            "pardon": lambda: pl.pardon(folder, name),
            "ban": lambda: pl.ban(folder, name, online, reason),
        }.get(action)
        if work:  # (kick needs a running server; its button only shows then)
            self._edit_files(work)
