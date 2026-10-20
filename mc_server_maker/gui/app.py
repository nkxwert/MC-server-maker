"""Main window."""

import html
import os
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QEvent, QFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMainWindow,
    QMenu,
    QProgressBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker import APP_NAME, APP_VERSION
from mc_server_maker.core import addons, autostart, network, paths, preflight, updater
from mc_server_maker.core import server as srv
from mc_server_maker.core.plugins import udp_ports
from mc_server_maker.core.settings import AppSettings
from mc_server_maker.gui import anim, theme
from mc_server_maker.gui.anim import FadeInDialog
from mc_server_maker.gui.create_dialog import CreateServerDialog
from mc_server_maker.gui.runner import RUNNING, STARTING, STOPPED, STOPPING, ServerRunner
from mc_server_maker.gui.tabs import (
    AddonsTab,
    ConsoleTab,
    NetworkTab,
    SettingsTab,
    StatusTab,
    jar_paths,
    open_path,
)
from mc_server_maker.gui.tunnel_manager import TunnelManager
from mc_server_maker.gui.theme import fit_to_screen, form_layout, set_kind
from mc_server_maker.gui.widgets import ask, with_note
from mc_server_maker.gui.workers import TaskDialog, any_running, run_async, wait_all
from mc_server_maker.i18n import LANGUAGES, set_language, t


_after_start: dict = {}  # server folder -> meta: tunnel/UPnP to do once its Java process runs


def state_text(state: str):
    return {
        STOPPED: (t("Stopped"), theme.C["muted"]),
        STARTING: (t("Starting..."), theme.C["warn"]),
        RUNNING: (t("Running"), theme.C["ok"]),  # green = on, separate from the blue accent
        STOPPING: (t("Stopping..."), theme.C["warn"]),
    }[state]


def server_icon(meta: srv.ServerMeta, size: int) -> QPixmap:
    path = meta.folder / "server-icon.png"
    return theme.icon_pixmap(path if path.exists() else paths.resource("icon.png"), size)


class ServerItem(QWidget):
    """One server in the sidebar, with a ⋯ menu."""

    class _Elided(QLabel):
        """Long names end with "…" where the room ends, instead of pushing the ⋯ button out of
        the sidebar. The full text shows when hovering."""

        def __init__(self, text: str):
            super().__init__()
            self.full = text
            self.setToolTip(text)
            self.setMinimumWidth(1)
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.setText(self.fontMetrics().elidedText(self.full, Qt.ElideRight, self.width()))

        def changeEvent(self, event):
            super().changeEvent(event)
            if event.type() in (QEvent.FontChange, QEvent.StyleChange):  # bold names are wider
                self.setText(self.fontMetrics().elidedText(self.full, Qt.ElideRight, self.width()))

    def __init__(self, meta: srv.ServerMeta, state: str, on_menu):
        super().__init__()
        self.meta = meta
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 6, 7)
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(server_icon(meta, 32))
        icon.setFixedSize(32, 32)
        row.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = self._Elided(meta.name)
        name.setObjectName("ItemName")
        sub = self._Elided(f"{meta.software_name} {meta.mc_version}")
        sub.setObjectName("ItemSub")
        col.addWidget(name)
        col.addWidget(sub)
        row.addLayout(col, 1)
        text, color = state_text(state)
        dot = QLabel("●")
        dot.setToolTip(text)
        dot.setStyleSheet(f"color: {color}; font-size: 8pt;")
        row.addWidget(dot)
        row.addSpacing(-4)  # the dot and ⋯ belong together
        more = QToolButton()
        more.setText("⋯")
        more.setObjectName("MoreButton")
        more.setToolTip(t("Rename, duplicate, delete..."))
        more.setCursor(Qt.PointingHandCursor)
        more.setFixedWidth(26)  # narrow: the room goes to the name
        more.clicked.connect(lambda: on_menu(meta, more.mapToGlobal(more.rect().bottomLeft())))
        row.addWidget(more)


class UpdateDialog(FadeInDialog):
    """New version: what's new + Update now / Later. Also used for "What's new" after updating."""

    def __init__(self, parent, title: str, heading: str, notes_md: str, can_update: bool = False,
                 update_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_to_screen(self, 560, 520)
        layout = QVBoxLayout(self)
        h = QLabel(heading)
        h.setObjectName("Big")
        h.setWordWrap(True)
        layout.addWidget(h)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(notes_md or t("(no notes)"))
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox()
        if can_update:
            set_kind(buttons.addButton(update_label or t("Update now"), QDialogButtonBox.AcceptRole), "primary")
            buttons.addButton(t("Later"), QDialogButtonBox.RejectRole)
        else:
            set_kind(buttons.addButton(t("OK"), QDialogButtonBox.AcceptRole), "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PreferencesDialog(FadeInDialog):
    def __init__(self, parent, settings: AppSettings, on_check_updates=None, servers=None):
        super().__init__(parent)
        self.setWindowTitle(t("App settings"))
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        form = form_layout()
        self.theme = QComboBox()
        self.theme.addItem(t("Dark"), "dark")
        self.theme.addItem(t("Light"), "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.theme)))
        form.addRow(t("Theme"), self.theme)
        self.language = QComboBox()
        for code, label in LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        form.addRow(t("Language"), self.language)
        self.low_resource = QCheckBox(t("Low-resource mode"))
        self.low_resource.setChecked(settings.low_resource)
        form.addRow("", with_note(self.low_resource, t(
            "Runs servers at lower priority with a smaller memory footprint, turns off screen "
            "transition effects, and pauses the app's live updates while its window is hidden.")))
        self.autostart = QCheckBox(t("Start Bartizan when Windows starts"))
        self.autostart_min = QCheckBox(t("Start in the tray (no window)"))
        self.autostart_server = QComboBox()
        self.autostart_server.addItem(t("No server"), "")
        for meta in servers or []:
            self.autostart_server.addItem(meta.name, str(meta.folder))
        if autostart.supported():
            self.autostart.setChecked(autostart.enabled())
            self.autostart_min.setChecked(autostart.minimized())
            self.autostart_server.setCurrentIndex(max(0, self.autostart_server.findData(settings.autostart_server)))
            form.addRow(t("Startup"), self.autostart)
            form.addRow("", self.autostart_min)
            form.addRow(t("Then start"), with_note(self.autostart_server, t(
                "Starts this server too, so friends can join as soon as the PC is on.")))
            self.autostart.toggled.connect(self._autostart_toggled)
            self._autostart_toggled(self.autostart.isChecked())
        folder = QLabel(str(paths.BASE_DIR))
        folder.setWordWrap(True)
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(t("Data folder"), folder)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("Version {v}", v=APP_VERSION)))
        check = QPushButton(t("Check for updates"))
        if on_check_updates:
            check.clicked.connect(on_check_updates)
        row.addWidget(check)
        row.addStretch()
        form.addRow(t("App"), row)
        layout.addLayout(form)
        buttons = QDialogButtonBox()
        set_kind(buttons.addButton(t("Save"), QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton(t("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _autostart_toggled(self, on: bool):
        self.autostart_min.setEnabled(on)
        self.autostart_server.setEnabled(on)


class PreflightDialog(FadeInDialog):
    """Problems found before a start, each with its one-click fix; Start anyway or Cancel."""

    def __init__(self, parent, meta, issues, apply_fix):
        super().__init__(parent)
        self.setWindowTitle(t("Before starting"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        head = QLabel(t("Check these before starting '{name}':", name=meta.name))
        head.setWordWrap(True)
        layout.addWidget(head)
        for issue in issues:
            row = QHBoxLayout()
            text = QLabel()
            text.setWordWrap(True)
            text.setTextFormat(Qt.RichText)
            color = theme.C["danger"] if issue.error else theme.C["warn"]
            text.setText(f"<span style='color:{color}'>●</span>&nbsp; <b>{html.escape(issue.title)}</b><br>"
                         f"<span style='color:{theme.C['muted']}'>{html.escape(issue.detail)}</span>")
            row.addWidget(text, 1)
            if issue.fix:
                btn = QPushButton(issue.fix_label)
                if issue.error:
                    set_kind(btn, "primary")

                def fix(_c=False, i=issue, b=btn, label=text):
                    apply_fix(meta, i.fix, i.value)
                    b.setEnabled(False)
                    b.setText(t("Done"))
                    label.setText(f"<span style='color:{theme.C['ok']}'>●</span>&nbsp; <b>{html.escape(i.fix_label)}</b>")
                    if i.error:
                        self._errors -= 1
                        self._update_buttons()
                btn.clicked.connect(fix)
                row.addWidget(btn, 0, Qt.AlignTop)
            layout.addLayout(row)
        self._errors = sum(1 for i in issues if i.error)
        buttons = QDialogButtonBox()
        self.start_btn = buttons.addButton(t("Start anyway"), QDialogButtonBox.AcceptRole)
        buttons.addButton(t("Cancel"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_buttons()

    def _update_buttons(self):
        fixed = self._errors <= 0
        self.start_btn.setText(t("Start") if fixed else t("Start anyway"))
        set_kind(self.start_btn, "primary" if fixed else "")


class OldCopiesDialog(FadeInDialog):
    """Old downloaded Bartizan files, each with a checkbox; checked ones go to the Recycle Bin."""

    def __init__(self, parent, files):
        super().__init__(parent)
        self.setWindowTitle(t("Old Bartizan files"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        text = QLabel(t("These are older downloaded copies of Bartizan. You now use the installed app "
                        "(Start menu), so they're no longer needed and make it hard to tell which one is "
                        "current.\n\nMove the checked files to the Recycle Bin? Your servers and worlds "
                        "are not affected."))
        text.setWordWrap(True)
        layout.addWidget(text)
        self.boxes = []
        for path in files:
            try:
                st = path.stat()
                info = f"{st.st_size / 1e6:.0f} MB · {time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))}"
            except OSError:
                info = ""
            box = QCheckBox(f"{path.name}   ({info})" if info else path.name)
            box.setToolTip(str(path))
            box.setChecked(True)
            layout.addWidget(box)
            self.boxes.append((box, path))
        buttons = QDialogButtonBox()
        set_kind(buttons.addButton(t("Move to Recycle Bin"), QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton(t("Keep them"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._remove)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _remove(self):
        failed = []
        for box, path in self.boxes:
            if not box.isChecked():
                continue
            result = QFile.moveToTrash(str(path))
            ok = result[0] if isinstance(result, tuple) else bool(result)
            if not ok or path.exists():
                failed.append(path.name)  # e.g. still running
        if failed:
            QMessageBox.warning(self, t("Old Bartizan files"), t(
                "These couldn't be moved (close them if they're running):\n{files}", files="\n".join(failed)))
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, runner: ServerRunner, settings: AppSettings, tunnel: TunnelManager, select_folder=None):
        super().__init__()
        self.tunnel = tunnel
        self.setAcceptDrops(True)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        fit_to_screen(self, 1180, 760, center=True)
        paths.ensure_dirs()
        self.runner = runner
        self.settings = settings
        self._replaced = False
        self.runner.state_changed.connect(self._on_state_changed)
        self.runner.process_started.connect(self._process_started)
        self.runner.stop_slow.connect(self._stop_slow)
        self.servers: List[srv.ServerMeta] = []
        self.meta: Optional[srv.ServerMeta] = None

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # ---- sidebar
        side = QFrame()
        self.side = side
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 16, 12, 10)
        sv.setSpacing(10)
        brand = QHBoxLayout()
        brand.setContentsMargins(4, 0, 0, 0)
        brand.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(theme.icon_pixmap(paths.resource("icon.png"), 28))
        brand.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel(APP_VERSION)
        subtitle.setObjectName("AppSubtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle, 1, Qt.AlignBottom)
        sv.addLayout(brand)
        sv.addSpacing(4)

        new_btn = set_kind(QPushButton(t("New server")), "primary")
        new_btn.setMinimumHeight(36)
        new_btn.clicked.connect(self.create_server)
        sv.addWidget(new_btn)
        sv.addSpacing(4)
        label = QLabel("  " + t("SERVERS"))
        label.setObjectName("SectionLabel")
        sv.addWidget(label)
        self.list = QListWidget()
        self.list.setObjectName("ServerList")
        self.list.currentRowChanged.connect(self._select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_context_menu)
        sv.addWidget(self.list, 1)
        foot = QFrame()
        foot.setObjectName("SideFoot")
        row = QHBoxLayout(foot)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(4)
        folder_btn = set_kind(QPushButton(t("Folder")), "ghost")
        folder_btn.setToolTip(str(paths.SERVERS_DIR))
        folder_btn.clicked.connect(lambda: open_path(paths.SERVERS_DIR))
        prefs_btn = set_kind(QPushButton(t("Settings")), "ghost")
        prefs_btn.clicked.connect(self.open_preferences)
        self.prefs_btn = prefs_btn
        self._show_update_dot()
        row.addWidget(folder_btn)
        row.addWidget(prefs_btn)
        row.addStretch()
        sv.addWidget(foot)
        root_layout.addWidget(side)

        # ---- main area
        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_page())

        detail = QWidget()
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(0)
        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 12)
        hl.setSpacing(12)
        self.h_icon = QLabel()
        self.h_icon.setFixedSize(44, 44)
        hl.addWidget(self.h_icon)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.h_name = QLabel()
        self.h_name.setObjectName("ServerName")
        info.addWidget(self.h_name)
        # one quiet line: "● Running · Paper 1.21.4 · Memory 2 GB"
        self.h_meta = QLabel()
        self.h_meta.setObjectName("Meta")
        self.h_meta.setTextFormat(Qt.RichText)
        info.addWidget(self.h_meta)
        # the name/meta area may shrink (text is cut) so narrow screens still fit the buttons
        info_w = QWidget()
        info_w.setLayout(info)
        info.setContentsMargins(0, 0, 0, 0)
        info_w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_w.setMinimumWidth(140)
        hl.addWidget(info_w, 1)
        self.btn_start = set_kind(QPushButton(t("Start")), "primary")
        self.btn_start.setMinimumSize(88, 36)
        self.btn_start.clicked.connect(self.start_server)
        self.btn_stop = set_kind(QPushButton(t("Stop")), "stop")
        self.btn_stop.setMinimumSize(80, 36)
        self.btn_stop.setStyleSheet("QPushButton { border-top-right-radius: 0; border-bottom-right-radius: 0; }")
        self.btn_stop.clicked.connect(lambda: self.runner.stop(self.key))
        # ▾ next to Stop: rarely needed "force stop" lives in its menu
        self.btn_stop_more = set_kind(QPushButton("▾"), "stop")
        self.btn_stop_more.setToolTip(t("More stop options"))
        self.btn_stop_more.setFixedSize(28, 36)
        self.btn_stop_more.setStyleSheet(  # our own ▾ only, not Qt's extra menu arrow
            "QPushButton { padding: 0; border-top-left-radius: 0; border-bottom-left-radius: 0; }"
            " QPushButton::menu-indicator { image: none; width: 0px; }")
        stop_menu = QMenu(self.btn_stop_more)
        self.act_restart = stop_menu.addAction(t("Save and restart"), self._restart)
        stop_menu.addSeparator()
        self.act_kill = stop_menu.addAction(t("Force stop (without saving)"), self._kill)
        self.btn_stop_more.setMenu(stop_menu)
        stop_group = QHBoxLayout()
        stop_group.setSpacing(1)
        stop_group.addWidget(self.btn_stop)
        stop_group.addWidget(self.btn_stop_more)
        hl.addWidget(self.btn_start)
        hl.addLayout(stop_group)
        dv.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setDrawBase(False)
        self.console_tab = ConsoleTab(self.runner, self.reload)
        self.status_tab = StatusTab(self.runner, self.reload)
        self.addons_tab = AddonsTab(self.runner, self.reload)
        self.settings_tab = SettingsTab(self.runner, self.reload)
        self.network_tab = NetworkTab(self.runner, self.reload)
        self.all_tabs = [
            self.console_tab, self.status_tab, self.addons_tab, self.network_tab, self.settings_tab,
        ]
        titles = ["Console", "Server status", "Plugins", "Network", "Settings"]  # settings last
        for tab, name in zip(self.all_tabs, titles):
            self.tabs.addTab(tab, t(name))
        # clicking a tab blends the old page into the new one (the click comes before the switch)
        self.tabs.tabBar().tabBarClicked.connect(self._tab_clicked)
        self.network_tab.set_tunnel(self.tunnel)
        self.status_tab.tunnel = self.tunnel
        # the console says whether friends can join, using what the Network tab knows
        self.network_tab.friend_changed.connect(self.console_tab.set_friend)
        self.console_tab.open_network = lambda: self._go_tab(self.network_tab)
        self.console_tab.copy_invite = self.network_tab.copy_invite
        self.console_tab.on_fix = self._fix_crash
        tab_wrap = QWidget()
        tw = QVBoxLayout(tab_wrap)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.addWidget(self.tabs)
        dv.addWidget(tab_wrap, 1)
        self.stack.addWidget(detail)
        root_layout.addWidget(self.stack, 1)

        theme.flatten_groups(self)
        self.reload(select_folder)

    def _empty_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        icon = QLabel()
        icon.setPixmap(theme.icon_pixmap(paths.resource("icon.png"), 88))
        icon.setAlignment(Qt.AlignCenter)
        v.addWidget(icon)
        title = QLabel(t("Create your first Minecraft server"))
        title.setObjectName("Big")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)
        sub = QLabel(t("Pick the software and version — downloading and setup are automatic."))
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignCenter)
        v.addWidget(sub)
        btn = set_kind(QPushButton(t("New server")), "primary")
        btn.setFixedSize(QSize(200, 40))
        btn.clicked.connect(self.create_server)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        v.addSpacing(10)
        v.addLayout(row)
        # the sidebar is hidden until the first server exists, so app settings live here too
        self.empty_prefs = set_kind(QPushButton(t("Settings")), "ghost")
        self.empty_prefs.clicked.connect(self.open_preferences)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.empty_prefs)
        row.addStretch()
        v.addSpacing(4)
        v.addLayout(row)
        self._show_update_dot()
        v.addStretch()
        return page

    # ------------------------------------------------------------------

    @property
    def key(self) -> str:
        return str(self.meta.folder) if self.meta else ""

    def reload(self, select_folder=None):
        """Re-read servers from disk, keeping the current selection."""
        keep = str(select_folder) if select_folder else self.key
        self.servers = srv.list_servers()
        folders = {m.folder for m in self.servers}
        for tab in self.all_tabs:  # a server that's gone (deleted here or by hand): forget it
            if tab.meta is not None and tab.meta.folder not in folders:
                tab.forget_server()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self._drop_widget(self.list.item(i))
        self.list.clear()
        row = 0
        for i, m in enumerate(self.servers):
            if not self.runner.is_running(str(m.folder)):
                srv.end_offline_session(m)  # the app closed during an offline run
            self._add_item(m)
            if str(m.folder) == keep:
                row = i
        if self.servers:
            self.list.setCurrentRow(row)  # while signals are blocked: _select runs once, below
        self.list.blockSignals(False)
        # no servers yet: just the welcome page in the middle, no sidebar
        if self.side.isHidden() == bool(self.servers):  # isHidden: works before the window is shown
            # the first server appears (or the last one is gone): blend the whole window over
            anim.crossfade(self.centralWidget(), lambda: self.side.setVisible(bool(self.servers)))
        if self.servers:
            self._select(row)
        else:
            self.meta = None
            if self.stack.currentIndex() != 0:
                anim.crossfade(self.stack, lambda: self.stack.setCurrentIndex(0))

    def _add_item(self, m: srv.ServerMeta, row: Optional[int] = None):
        widget = ServerItem(m, self.runner.state(str(m.folder)), self.server_menu)
        if row is None:
            item = QListWidgetItem()
            self.list.addItem(item)
        else:
            item = self.list.item(row)
            self._drop_widget(item)
        item.setSizeHint(QSize(0, 56))
        self.list.setItemWidget(item, widget)

    def _drop_widget(self, item: QListWidgetItem):
        old = self.list.itemWidget(item)
        if old:
            self.list.removeItemWidget(item)
            old.hide()
            old.deleteLater()

    def _select_folder(self, folder):
        for i, m in enumerate(self.servers):
            if m.folder == folder:
                self.list.setCurrentRow(i)
                return

    def _ask_unsaved(self):
        """'save', 'discard' or None (cancel)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(t("Unsaved changes"))
        box.setText(t("'{name}' has settings you changed but haven't saved.", name=self.meta.name))
        save = box.addButton(t("Save"), QMessageBox.AcceptRole)
        discard = box.addButton(t("Don't save"), QMessageBox.DestructiveRole)
        box.addButton(t("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard else None

    def _select(self, row: int):
        if row < 0 or row >= len(self.servers):
            return
        target = self.servers[row].folder
        if self.meta is not None and self.meta.folder != target and self.settings_tab.has_unsaved():
            choice = self._ask_unsaved()
            if choice != "discard":
                prev = next((i for i, m in enumerate(self.servers) if m.folder == self.meta.folder), -1)
                self.list.blockSignals(True)  # stay on the edited server
                self.list.setCurrentRow(prev)
                self.list.blockSignals(False)
                if choice == "save":
                    self.settings_tab.save()
                    if not self.settings_tab.has_unsaved():
                        QTimer.singleShot(0, lambda: self._select_folder(target))
                return
        changed = self.meta is None or self.meta.folder != self.servers[row].folder or self.stack.currentIndex() != 1
        if changed:  # switching servers blends the old one into the new one
            anim.crossfade(self.stack)
        self.meta = self.servers[row]
        self.stack.setCurrentIndex(1)
        # Plugins / Mods tab only for software that supports them
        label = addons.kind_label(self.meta)
        idx = self.tabs.indexOf(self.addons_tab)
        if not label and self.tabs.currentIndex() == idx:
            self.tabs.setCurrentIndex(0)
        self.tabs.setTabVisible(idx, bool(label))
        if label:
            self.tabs.setTabText(idx, t(label))
        failed = []
        try:
            self._update_header()
        except Exception:  # noqa: BLE001 - a broken field in one server must not leave the tabs on another
            traceback.print_exc()
        for tab in self.all_tabs:
            try:
                tab.set_server(self.meta)
            except Exception:  # noqa: BLE001 - keep the other tabs usable
                traceback.print_exc()
                failed.append(self.tabs.tabText(self.tabs.indexOf(tab)))
        if failed:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, APP_NAME, t(
                "Some settings of '{name}' couldn't be loaded ({tabs}). Check its server.properties.",
                name=self.meta.name if self.meta else "", tabs=", ".join(failed))))

    def _tab_clicked(self, index: int):
        if index != self.tabs.currentIndex():
            anim.crossfade(self.tabs, ms=anim.TAB)

    def _go_tab(self, tab):
        if self.tabs.currentWidget() is not tab:
            anim.crossfade(self.tabs, ms=anim.FAST)
            self.tabs.setCurrentWidget(tab)

    def _update_header(self):
        m = self.meta
        if not m:
            return
        state = self.runner.state(self.key)
        text, color = state_text(state)
        self.h_icon.setPixmap(server_icon(m, 44))
        self.h_name.setText(self.h_name.fontMetrics().elidedText(m.name, Qt.ElideRight, 360))
        self.h_name.setToolTip(m.name)
        sep = f'<span style="color:{theme.C["disabled"]}">&nbsp;·&nbsp;</span>'
        self.h_meta.setText(
            f'<span style="color:{color}">●</span>&nbsp;{html.escape(text)}{sep}'
            f'{html.escape(m.software_name)} {html.escape(m.mc_version)}{sep}'
            + html.escape(t("Memory {n} GB", n=m.ram_mb // 1024)))
        running = self.runner.is_running(self.key)
        self.btn_start.setEnabled(not running and self.key not in self.runner.pending)
        self.btn_stop.setEnabled(running)  # while stopping too: pressing again re-sends "stop"
        self.btn_stop.setText(t("Stopping...") if state == STOPPING else t("Stop"))
        self.btn_stop_more.setEnabled(running)
        self.act_kill.setEnabled(running)
        self.act_restart.setEnabled(running and state != STOPPING)

    def _on_state_changed(self, key: str, state: str):
        if state == STOPPED:
            _after_start.pop(key, None)
            for m in self.servers:
                if str(m.folder) == key and srv.end_offline_session(m):
                    self.runner.system_line(key, t("Online mode is back on."))
                    if key == self.key:
                        self.settings_tab.set_server(self.meta)  # show the restored setting
            for m in self.servers:
                if str(m.folder) == key and m.upnp:
                    self._close_auto_port(m)
            from mc_server_maker.gui import manage

            manage.auto_backup_after_stop(self.runner, key)  # only if it's switched on for this server
        for i, m in enumerate(self.servers):
            if str(m.folder) == key:
                self._add_item(m, i)
        if key == self.key:
            self._update_header()
            for tab in self.all_tabs:
                tab.on_state()

    def _refresh_tabs(self):
        self._update_header()
        for tab in self.all_tabs:
            tab.on_state()

    # ------------------------------------------------------------------

    def open_preferences(self):
        dlg = PreferencesDialog(self, self.settings, lambda: self.check_updates(manual=True), self.servers)
        if not dlg.exec():
            return
        if autostart.supported():
            on = dlg.autostart.isChecked()
            self.settings.autostart_server = dlg.autostart_server.currentData() if on else ""
            try:
                autostart.set_enabled(on, dlg.autostart_min.isChecked())
            except OSError as e:
                QMessageBox.warning(self, t("Startup"), t("Couldn't change the Windows startup setting: {err}", err=e))
        new_theme, new_lang = dlg.theme.currentData(), dlg.language.currentData()
        changed_lang = new_lang != self.settings.language
        self.settings.theme, self.settings.language = new_theme, new_lang
        self.settings.low_resource = dlg.low_resource.isChecked()
        self.settings.save()
        apply_low_resource(self.runner, self.settings.low_resource)
        if changed_lang:
            set_language(new_lang)  # before theme.apply: the font depends on the language
            install_qt_translation(QApplication.instance(), new_lang)
        theme.apply(QApplication.instance(), new_theme)
        self.console_tab.refresh()  # log lines carry their colors: draw them again in the new theme
        if changed_lang:
            # rebuild the window in the new language; running servers keep running
            retranslate_tray()
            win = MainWindow(self.runner, self.settings, self.tunnel, self.key)
            win.setGeometry(self.geometry())
            win.show()
            _windows.append(win)
            self._replaced = True
            self.close()
        else:
            self.reload()

    # ------------------------------------------------------------- app updates

    def _show_update_dot(self):
        info = _update.get("info")
        for btn in (self.prefs_btn, getattr(self, "empty_prefs", None)):
            if btn:
                btn.setText(t("Settings") + ("  ●" if info else ""))
                btn.setToolTip(t("Update available: v{v}", v=info.version) if info else "")

    def check_updates(self, manual: bool = False):
        def done(info):
            self.settings.last_update_check = time.strftime("%Y-%m-%d")
            self.settings.save()
            _update["info"] = info
            for w in list(_windows):
                w._show_update_dot()
            if not info:
                if manual:
                    QMessageBox.information(self, t("Updates"), t("You're on the latest version ({v}).", v=APP_VERSION))
                return
            if manual or self.settings.notified_version != info.version:
                self.settings.notified_version = info.version
                self.settings.save()
                self.offer_update(info)

        def fail(msg):
            if manual:
                QMessageBox.warning(self, t("Updates"), t("Couldn't check for updates: {err}", err=msg))

        run_async(lambda task: updater.check(), done, fail)

    def offer_update(self, info):
        can = updater.can_self_update() and bool(info.exe_url)
        dlg = UpdateDialog(
            self, t("Update available"),
            t("v{new} is available (you have v{cur}). What's new:", new=info.version, cur=APP_VERSION),
            info.notes_text(self.settings.language), can_update=True,
            update_label=t("Update now") if can else t("Open download page"))
        if not dlg.exec():
            return
        if not can:
            QDesktopServices.openUrl(QUrl(info.page_url))
            return
        self._install_update(info)

    def _install_update(self, info):
        """Download `info` (the installer when the release has one) and hand over to it."""
        if self.runner.any_running() and QMessageBox.question(
                self, t("Update"), t("Running servers will be stopped safely before updating. Continue?")) != QMessageBox.Yes:
            return
        task_dlg = TaskDialog(self, t("Downloading v{v}...", v=info.version), lambda task: updater.download(info, task))
        task_dlg.exec()
        if not task_dlg.succeeded():
            return
        new_exe = task_dlg.result_value
        if not wait_for_stop(self):
            return
        try:
            updater.install_and_restart(new_exe)
        except OSError as e:
            QMessageBox.warning(self, t("Update"), t("Couldn't install the update: {err}", err=e))
            return
        quit_app(self)

    def offer_install(self):
        """The portable single EXE asks once to move to the installed app (shortcuts, uninstall in
        Windows settings, fewer antivirus false alarms). Servers and worlds stay where they are."""
        if not updater.can_self_update() or updater.is_installed() or self.settings.install_offered:
            return
        self.settings.install_offered = True
        self.settings.save()
        if QMessageBox.question(self, t("Install Bartizan"), t(
                "Bartizan can now be installed like a normal Windows program: Start menu and desktop "
                "shortcuts, removal in Windows Settings, and fewer false alarms from antivirus programs "
                "such as V3.\n\nInstall it now? Your servers and worlds stay as they are, and this "
                "single Bartizan.exe is removed afterwards.")) != QMessageBox.Yes:
            return

        def got(info):
            if not info or not info.setup_url:
                QMessageBox.information(self, t("Install Bartizan"), t(
                    "The installer isn't available right now. Try again with the next update."))
                return
            self._install_update(info)

        run_async(lambda task: updater.check(current="0"), got,
                  lambda msg: QMessageBox.warning(self, t("Install Bartizan"), msg))

    def offer_cleanup(self):
        """The installed app looks once for old downloaded copies (Bartizan (1).exe, ...) that make
        it hard to tell which one is current, and offers to move them to the Recycle Bin."""
        if not updater.is_installed() or self.settings.old_exes_checked:
            return

        def found(files):
            self.settings.old_exes_checked = True
            self.settings.save()
            if files:
                OldCopiesDialog(self, files).exec()

        run_async(lambda task: updater.old_copies(), found, lambda _m: None)

    def show_whats_new_if_updated(self):
        """After an update, show the notes for this version once. Never again for it, and never
        for an older copy started later (old downloaded EXEs would show theirs every time)."""
        previous = self.settings.last_run_version
        seen = self.settings.notes_seen_version or previous
        newer = updater.parse_version(APP_VERSION) > updater.parse_version(seen) if seen else False
        self.settings.last_run_version = APP_VERSION
        if newer or not seen:
            self.settings.notes_seen_version = APP_VERSION
        self.settings.save()
        if newer:
            notes = updater.bundled_notes(APP_VERSION, self.settings.language)
            if notes:
                UpdateDialog(self, t("What's new"), t("Updated to v{v}", v=APP_VERSION), notes).exec()

    def create_server(self):
        dlg = CreateServerDialog(self)
        while True:  # a failed attempt goes back to the filled-in form, nothing has to be typed again
            if not dlg.exec() or not dlg.options:
                return
            opts = dlg.options
            task_dlg = TaskDialog(self, t("Creating server..."), lambda task, o=opts: srv.create_server(o, task))
            task_dlg.exec()
            if task_dlg.succeeded():
                break
        if task_dlg.succeeded():
            meta = task_dlg.result_value
            self.reload(select_folder=meta.folder)
            QMessageBox.information(
                self,
                t("Done"),
                t("'{name}' is ready!\n\nPress Start — the world is generated on first start.\n"
                  "To play with friends in other homes, see the Network tab.", name=meta.name),
            )

    def start_server(self, meta=None):
        meta = meta or self.meta  # (the button passes False)
        if not meta:
            return
        key = str(meta.folder)
        if self.runner.is_running(key) or key in self.runner.pending:
            return
        if key in self.runner.busy:  # a world import, backup or upgrade is changing its files
            QMessageBox.information(self, t("Start"), t("Wait until the current task on this server is finished."))
            return
        if not self._preflight(meta):
            return
        srv.end_offline_session(meta)  # left over if the app closed while an offline run was going
        if not meta.properties().get_bool("online-mode", True):
            self._launch(meta)
            return
        # Online mode needs Mojang's sign-in servers. Without internet nobody could join
        # ("Authentication servers are down"), so offer an offline run first.
        self.runner.pending.add(key)  # no second Start, Delete or world change while we check
        self.btn_start.setEnabled(False)
        self._refresh_tabs()

        def checked(has_net):
            self.runner.pending.discard(key)
            win = current_window() or self  # the window may have been rebuilt (language change)
            win._refresh_tabs()
            if not meta.folder.exists():
                return  # deleted meanwhile
            if win.key == key:
                win._update_header()  # re-enable Start (the selected meta may be a newer object)
            if not has_net:
                choice = win._ask_offline(meta)
                if choice is None:
                    return
                if choice:
                    srv.begin_offline_session(meta)
            win._launch(meta)

        run_async(lambda task: network.has_internet(), checked, lambda m: checked(True))

    def _preflight(self, meta: srv.ServerMeta) -> bool:
        """Port taken, too little memory or disk: say so before starting. False = don't start."""
        key = str(meta.folder)
        try:
            port = meta.properties().get_int("server-port", 25565)
        except OSError:
            return True
        running = {m.name: self.runner.port(str(m.folder), m) for m in self.servers
                   if str(m.folder) != key and self.runner.is_running(str(m.folder))}
        others = []
        for m in self.servers:
            if str(m.folder) != key:
                try:
                    others.append(m.properties().get_int("server-port", 25565))
                except OSError:
                    pass
        issues = preflight.check(port, meta.ram_mb, meta.folder, running, others)
        if not issues:
            return True
        return PreflightDialog(self, meta, issues, self._apply_fix).exec() == QDialog.Accepted

    def _apply_fix(self, meta: srv.ServerMeta, fix: str, value: int) -> None:
        """A one-click fix from the start check or the crash helper."""
        if fix == "port":
            props = meta.properties()
            props.set("server-port", value)
            props.save()
            srv.write_start_scripts(meta)
        elif fix == "memory":
            meta.ram_mb = value * 1024
            meta.save()
            srv.write_start_scripts(meta)
        self.reload()

    def _fix_crash(self, diag) -> None:
        """The crash helper's button."""
        meta = self.meta
        if not meta:
            return
        if diag.action == "port":
            port = meta.properties().get_int("server-port", 25565)
            taken = [m.properties().get_int("server-port", 25565) for m in self.servers if m.folder != meta.folder]
            new = preflight.next_free_port(port, taken)
            if new and ask(self, t("Use another port"), t(
                    "Change this server's port from {old} to {new}? Friends then need the new address "
                    "(the Network tab shows it).", old=port, new=new), t("Use port {port}", port=new), t("Cancel")):
                self._apply_fix(meta, "port", new)
        elif diag.action == "java":
            self._go_tab(self.settings_tab)
            self.settings_tab.world.upgrade._fix_java()
        elif diag.action == "memory":
            self._go_tab(self.settings_tab)
            self.settings_tab.ram.setFocus()
        elif diag.action == "mod":
            self._go_tab(self.addons_tab)
            self.addons_tab.pages.button(1).click()
            self.addons_tab.browser.query.setText(diag.mod)
        elif diag.action == "eula":
            if ask(self, t("Agree to the EULA"), t(
                    "Do you agree to the Minecraft EULA (https://aka.ms/MinecraftEULA)? "
                    "The server can't run without it."), t("I agree"), t("Cancel")):
                (meta.folder / "eula.txt").write_text(
                    "# https://aka.ms/MinecraftEULA (accepted in Bartizan)\neula=true\n", encoding="utf-8")
                self.runner.system_line(self.key, t("EULA accepted. Press Start again."))
                self.runner.exits.pop(self.key, None)
                self.console_tab.on_state()
        elif diag.action == "backups":
            self._go_tab(self.settings_tab)
            opener = getattr(self.settings_tab.world, "_manage_backups", None)
            if opener:
                opener()

    def _restart(self):
        meta = self.meta
        if meta and self.runner.is_running(self.key):
            key, runner = self.key, self.runner

            def again(m=meta):
                if key in runner.busy:  # e.g. the automatic backup after the stop: start right after it
                    QTimer.singleShot(500, again)
                    return
                (current_window() or self).start_server(m)

            runner.restart(key, again)

    def _ask_offline(self, meta: srv.ServerMeta):
        """No internet: True = start in offline mode, False = start as is, None = cancel."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(t("No internet"))
        box.setText(t("There's no internet connection, so Minecraft can't check accounts. "
                      "Players would see \"Authentication servers are down\" and couldn't join '{name}'.",
                      name=meta.name))
        box.setInformativeText(t(
            "Start in offline mode to play on this PC or the same Wi-Fi without internet. "
            "Online mode turns back on when the server stops.\n\n"
            "In offline mode players get separate inventories and OP rights from online play."))
        offline = box.addButton(t("Start in offline mode"), QMessageBox.AcceptRole)
        box.addButton(t("Start anyway"), QMessageBox.DestructiveRole)
        cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(offline)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked is cancel:  # closed by quitting the app: don't start anything
            return None
        return clicked is offline

    def _launch(self, meta: srv.ServerMeta):
        key = str(meta.folder)
        try:
            self.runner.start(meta)
        except (srv.ServerError, OSError) as e:
            srv.end_offline_session(meta)
            QMessageBox.warning(self, t("Start"), str(e))
            return
        if self.runner.state(key) == STOPPED:  # Java couldn't be started: no tunnel/port for it
            srv.end_offline_session(meta)
            return
        if self.key == key:
            self.tabs.setCurrentWidget(self.console_tab)
        if meta.offline_session:
            self.runner.system_line(key, t(
                "Offline mode for this run: players join without signing in. Online mode turns back on when the server stops."))
        # tunnel and router port only once Java really runs (on Linux/macOS a failed start is
        # reported a moment after start() returns)
        _after_start[key] = meta
        if self.runner.has_started(key):  # Windows may report "started" inside start() already
            self._process_started(key)

    def _process_started(self, key: str):
        meta = _after_start.pop(key, None)
        if meta is None or not self.runner.is_running(key):
            return
        if meta.tunnel and not self.tunnel.is_active():
            self.runner.system_line(key, t("Starting the playit.gg tunnel..."))
            self.tunnel.start()
        if meta.upnp:
            port = self.runner.port(key, meta)
            udp = udp_ports(meta)
            _opened_ports[key] = (port, udp)
            self.runner.system_line(key, t("Opening router port {port} (UPnP)...", port=port))

            def done(res):
                if not self.runner.is_running(key):  # stopped while the router was being asked
                    self._close_auto_port(meta)
                    return
                msg = t("Port {port} open — friends in other homes can join.", port=res.port)
                if res.cgnat:
                    msg += " " + t("(Warning: the router's internet IP is private; joining may not work.)")
                self.runner.system_line(key, msg)

            run_async(
                lambda task: network.open_port(port, f"Minecraft {meta.name}"[:60], udp_ports=udp),
                done,
                lambda m: self.runner.system_line(key, t("Could not open the port: {err}", err=m.replace("\n", " "))),
            )

    def _close_auto_port(self, meta: srv.ServerMeta):
        """The router mapping opened at start is removed again when the server stops, so the
        router doesn't keep forwarding to whatever device gets this PC's address later."""
        opened = _opened_ports.pop(str(meta.folder), None)
        if opened is None:  # opened by an earlier run of the app: settings are the best guess
            try:
                opened = (meta.properties().get_int("server-port", 25565), udp_ports(meta))
            except OSError:
                return
        port, udp = opened
        run_async(lambda task: network.close_port(port, udp_ports=udp), lambda _r: None, lambda _m: None)

    # ------------------------------------------------------- server list menu

    def _list_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item:
            widget = self.list.itemWidget(item)
            self.server_menu(widget.meta, self.list.viewport().mapToGlobal(pos))

    def server_menu(self, meta: srv.ServerMeta, global_pos):
        running = self.runner.is_running(str(meta.folder))
        menu = QMenu(self)
        menu.addAction(t("Rename..."), lambda: self.rename_server(meta))
        dup = menu.addAction(t("Duplicate"), lambda: self.duplicate_server(meta))
        menu.addAction(t("Open folder"), lambda: open_path(meta.folder))
        menu.addSeparator()
        delete = menu.addAction(t("Move to Recycle Bin..."), lambda: self.delete_server(meta))
        if running:
            dup.setEnabled(False)
            delete.setEnabled(False)
            delete.setText(t("Stop the server to delete it"))
        menu.exec(global_pos)

    def rename_server(self, meta: srv.ServerMeta):
        name, ok = QInputDialog.getText(self, t("Rename"), t("Server name:"), text=meta.name)
        name = name.strip()
        if ok and name and name != meta.name:
            meta.name = name
            meta.save()
            self.reload()

    def duplicate_server(self, meta: srv.ServerMeta):
        if str(meta.folder) in self.runner.busy:
            QMessageBox.information(self, t("Duplicate"), t("Wait until the current task on this server is finished."))
            return
        name, ok = QInputDialog.getText(self, t("Duplicate"), t("Name of the copy:"), text=t("{name} (copy)", name=meta.name))
        name = name.strip()
        if not ok or not name:
            return
        dlg = TaskDialog(self, t("Duplicate"), lambda task: srv.duplicate_server(meta, name, task))
        dlg.exec()
        if dlg.succeeded():
            self.reload(select_folder=dlg.result_value.folder)

    def delete_server(self, meta: srv.ServerMeta):
        if self.runner.is_running(str(meta.folder)) or str(meta.folder) in self.runner.pending:
            return
        if str(meta.folder) in self.runner.busy:  # e.g. its automatic backup is being written
            QMessageBox.information(self, t("Delete server"), t("Wait until the current task on this server is finished."))
            return
        answer = QMessageBox.question(
            self, t("Delete server"),
            t("Move '{name}' to the Recycle Bin?\n\nIts world, settings and backups go with it. "
              "You can restore it from the Recycle Bin.", name=meta.name))
        if answer != QMessageBox.Yes:
            return
        result = QFile.moveToTrash(str(meta.folder))
        ok = result[0] if isinstance(result, tuple) else bool(result)  # bool in PySide6, tuple in some builds
        if not ok or meta.folder.exists():
            QMessageBox.warning(self, t("Delete server"), t(
                "Couldn't move it to the Recycle Bin. Close any program using its files and try again.\n{path}",
                path=meta.folder))
            return
        self.runner.forget(str(meta.folder))  # a new server with the same name starts with a clean log
        for tab in self.all_tabs:  # ...and with fresh tabs (no old graphs, edits or port status)
            if tab.meta is not None and tab.meta.folder == meta.folder:
                tab.forget_server()
        if self.meta and self.meta.folder == meta.folder:
            self.meta = None
        self.reload()

    # drag .jar files anywhere on the window -> Plugins / Mods tab
    def dragEnterEvent(self, event):
        if self.meta and addons.kind_label(self.meta) and jar_paths(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = jar_paths(event.mimeData())
        if files and self.meta and addons.kind_label(self.meta):
            event.acceptProposedAction()
            self.tabs.setCurrentWidget(self.addons_tab)
            self.addons_tab.add_files(files)

    def _stop_slow(self, key: str):
        if key != self.key or not self.isVisible() or _quitting["now"]:
            return
        if ask(self, t("Stop"), t(
                "The server is still running a minute after Stop. A big world can take a while to save.\n\n"
                "Force stop now? Changes since the last save can be lost."),
                t("Force stop"), t("Keep waiting"), danger=True):
            if self.runner.is_running(key):
                self.runner.kill(key)

    def _kill(self):
        if ask(self, t("Kill"), t("Force stop without saving? The world may be damaged."),
               t("Force stop"), t("Keep running"), danger=True):
            self.runner.kill(self.key)

    def closeEvent(self, event):
        if self._replaced or _quitting["now"]:
            if self._replaced:
                self._detach()
            event.accept()
            return
        if self.runner.any_running():
            box = QMessageBox(self)
            box.setWindowTitle(t("Quit"))
            box.setText(t("A server is running."))
            keep = box.addButton(t("Keep running in background"), QMessageBox.AcceptRole)
            stop = box.addButton(t("Stop server and quit"), QMessageBox.DestructiveRole)
            box.addButton(t("Cancel"), QMessageBox.RejectRole)
            if not QSystemTrayIcon.isSystemTrayAvailable():
                keep.setVisible(False)
            box.exec()
            if box.clickedButton() is keep:
                event.ignore()
                self.hide()
                tray_message(t("{app} is still running. Open it from the tray icon.", app=APP_NAME))
                return
            if box.clickedButton() is not stop:
                event.ignore()
                return
        if quit_app(self):
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            # minimized: the window stays "visible" to Qt, so pause the live updates by hand
            for tab in (self.console_tab, self.status_tab):
                tab.set_paused(self.isMinimized())

    def _detach(self):
        self.runner.state_changed.disconnect(self._on_state_changed)
        self.runner.process_started.disconnect(self._process_started)
        self.runner.stop_slow.disconnect(self._stop_slow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        if self in _windows:
            _windows.remove(self)


_windows: List[MainWindow] = []  # keep windows alive
_tray: dict = {}
_update: dict = {"info": None}  # newest release found by the update check
_quitting = {"now": False}
_opened_ports: dict = {}  # server folder -> (TCP port, UDP ports) opened on the router at start


def current_window() -> Optional[MainWindow]:
    return _windows[-1] if _windows else None


def apply_low_resource(runner: ServerRunner, enabled: bool) -> None:
    srv.set_low_resource(enabled)
    runner.low_priority = enabled
    anim.set_enabled(not enabled)  # no animations in low-resource mode


def tray_message(text: str) -> None:
    tray = _tray.get("icon")
    if tray:
        tray.showMessage(APP_NAME, text, theme.app_icon(), 4000)


def show_window():
    win = current_window()
    if win:
        if win.isMinimized():
            win.showNormal()
        else:
            win.show()  # keeps a maximized window maximized
        win.raise_()
        win.activateWindow()


def wait_for_stop(win: MainWindow) -> bool:
    """Ask every server to save and stop, and wait as long as saving takes: a big world can need
    minutes. A force stop is offered after a while but never done without asking. Automatic
    backups (started when a server stops) are waited for too, and never cut off.
    False = the user cancelled (the servers still stop, the backups still finish)."""
    from mc_server_maker.gui import manage

    runner = win.runner
    runner.request_stop_all()
    if not runner.any_running() and not manage.auto_backups_running():
        return True
    dlg = QDialog(win)
    dlg.setWindowTitle(t("Stopping servers"))
    lay = QVBoxLayout(dlg)
    label = QLabel(t("Saving the world and stopping the servers..."))
    label.setWordWrap(True)
    lay.addWidget(label)
    bar = QProgressBar()
    bar.setRange(0, 0)
    bar.setTextVisible(False)
    lay.addWidget(bar)
    row = QHBoxLayout()
    row.addStretch(1)
    force = QPushButton(t("Force stop"))
    force.setProperty("kind", "stop")
    force.setVisible(False)
    cancel = QPushButton(t("Cancel"))
    row.addWidget(force)
    row.addWidget(cancel)
    lay.addLayout(row)
    dlg.setMinimumWidth(420)

    def slow():
        label.setText(t("Still saving. A big world can take a few minutes.\n\n"
                        "Force stop only if it seems stuck: changes since the last save can be lost."))
        force.setVisible(True)

    def kill_all():
        for key in list(runner.procs):
            runner.kill(key)

    def busy() -> bool:
        if runner.any_running():
            return True
        if manage.auto_backups_running():  # the servers are down; only the backup is left
            label.setText(t("Saving the automatic backup..."))
            force.setVisible(False)
            patience.stop()
            return True
        return False

    poll = QTimer(dlg)
    poll.timeout.connect(lambda: busy() or dlg.accept())
    poll.start(200)
    patience = QTimer(dlg)
    patience.setSingleShot(True)
    patience.timeout.connect(slow)
    patience.start(runner.STOP_PATIENCE_MS)
    force.clicked.connect(kill_all)
    cancel.clicked.connect(dlg.reject)
    return dlg.exec() == QDialog.Accepted or not (runner.any_running() or manage.auto_backups_running())


def quit_app(win: Optional[MainWindow] = None) -> bool:
    """Stop servers safely and exit. False = the user cancelled while servers were saving."""
    win = win or current_window()
    from mc_server_maker.gui import manage

    runner = win.runner if win else None
    if runner and (runner.any_running() or manage.auto_backups_running()):
        if win is None or not wait_for_stop(win):
            return False
    if win and win.tunnel:
        win.tunnel.stop()
    wait_all()
    _quitting["now"] = True
    if _tray.get("icon"):
        _tray["icon"].hide()
    QApplication.instance().quit()


def _single_instance(app: QApplication) -> bool:
    """Only one copy may run: two copies would start the same server twice on one world.

    A second launch (e.g. from the desktop while the first sits in the tray) asks the
    first copy to show its window, then exits.
    """
    import hashlib

    from PySide6.QtCore import QLockFile

    try:  # only for "show the window of the copy that's already running"
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
    except ImportError:  # a build without QtNetwork must still start
        QLocalServer = QLocalSocket = None

    import tempfile

    paths.BASE_DIR.mkdir(parents=True, exist_ok=True)
    name = "bartizan-" + hashlib.sha1(str(paths.BASE_DIR).encode("utf-8")).hexdigest()[:12]
    # the lock lives in this PC's temp folder, not in Documents: Documents is often synced by
    # OneDrive, and a lock copied from another PC can never be checked, so Bartizan wouldn't start
    lock = QLockFile(str(Path(tempfile.gettempdir()) / f"{name}.lock"))
    lock.setStaleLockTime(0)  # a dead owner is still detected
    # right after a self-update the old copy is still closing: give it time
    wait_ms = 20000 if os.environ.pop("BARTIZAN_RESTART", "") else 300
    if not lock.tryLock(wait_ms):
        if QLocalSocket is not None:
            sock = QLocalSocket()
            sock.connectToServer(name)
            if sock.waitForConnected(1500):  # the running copy shows its window
                sock.write(b"show")
                sock.waitForBytesWritten(1000)
                sock.disconnectFromServer()
                return False
        if lock.error() == QLockFile.LockFailedError:
            # another copy holds the lock but doesn't answer (still starting, or stuck): say so
            QMessageBox.information(None, APP_NAME, t(
                "Bartizan is already running. Look for its icon in the taskbar tray (next to the clock)."))
            return False
        # the lock file can't be written at all (e.g. a security setting): run anyway, unguarded
        app._instance = (lock,)
        return True
    if QLocalServer is None:
        app._instance = (lock,)
        return True
    QLocalServer.removeServer(name)
    server = QLocalServer(app)

    def wake():
        conn = server.nextPendingConnection()
        if conn:
            conn.deleteLater()
        show_window()

    server.newConnection.connect(wake)
    server.listen(name)
    app._instance = (lock, server)  # keep both alive for the app's lifetime
    return True


def _make_tray(app: QApplication):
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    tray = QSystemTrayIcon(theme.app_icon(), app)
    tray.setToolTip(APP_NAME)
    menu = QMenu()
    tray.setContextMenu(menu)
    _tray["menu"] = menu
    retranslate_tray()
    tray.activated.connect(lambda reason: show_window() if reason in (
        QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
    tray.show()
    _tray["icon"] = tray


def retranslate_tray():
    menu = _tray.get("menu")
    if not menu:
        return
    menu.clear()
    menu.addAction(t("Open"), show_window)
    menu.addSeparator()
    menu.addAction(t("Stop servers and quit"), lambda: quit_app())


def _excepthook(exc_type, exc, tb):
    """Show unexpected errors instead of crashing the whole app."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.__stderr__ and sys.__stderr__.write(text)
    if QApplication.instance() is None:
        return
    box = QMessageBox(current_window())
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(APP_NAME)
    box.setText(t("Something went wrong, but {app} keeps running.", app=APP_NAME))
    box.setDetailedText(text)
    box.exec()


def _hard_exit(code: int) -> None:
    """Leave right away while a worker thread is still blocked (e.g. in a network call).

    On Windows os._exit still runs DLL shutdown code, which can crash (0xC0000005) while Qt
    threads are alive; TerminateProcess ends the process without running any of it."""
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # 64-bit handle: without these types ctypes cuts the pseudo-handle (-1) to 32 bits
            # and the call silently fails
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
            kernel32.TerminateProcess(kernel32.GetCurrentProcess(), code & 0xFFFFFFFF)
        except (AttributeError, OSError):
            pass
    os._exit(code)


def _selftest_log():
    """BARTIZAN_SELFTEST=1 (the build check): write progress and any hard crash to a log."""
    if not os.environ.get("BARTIZAN_SELFTEST"):
        return lambda _msg: None
    import faulthandler

    paths.BASE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(paths.BASE_DIR / "selftest.log", "w", encoding="utf-8", buffering=1)
    faulthandler.enable(log, all_threads=True)

    def write(msg: str):
        log.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    write("starting")
    return write


_qt_translator: dict = {}


def install_qt_translation(app: QApplication, lang: str) -> None:
    """Qt's own words (Yes / No / Cancel / Close in standard dialogs) in the app's language."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    old = _qt_translator.pop("t", None)
    if old is not None:
        app.removeTranslator(old)
    if lang == "en":
        return
    tr = QTranslator(app)
    if tr.load(f"qtbase_{lang}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
        _qt_translator["t"] = tr


def _autostart_server(folder: str):
    """Windows started the app: start the server chosen in the app settings."""
    win = current_window()
    if not win:
        return
    for meta in win.servers:
        if str(meta.folder) == folder:
            win._select_folder(meta.folder)
            win.start_server()
            return


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == "win32":
        # show the app icon (not Python's) in the taskbar
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Bartizan")
        except (AttributeError, OSError):
            pass
    try:
        moved = paths.migrate_legacy_data()
    except OSError as e:
        moved = []
        print("data migration failed:", e)
    sys.excepthook = _excepthook
    selftest = _selftest_log()
    settings = AppSettings.load()
    set_language(settings.language)
    app = QApplication(sys.argv)
    if not _single_instance(app):
        return 0  # already running: that copy was asked to show its window
    app.setApplicationName(APP_NAME)
    install_qt_translation(app, settings.language)
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive
    theme.apply(app, settings.theme)
    runner = ServerRunner(app)
    apply_low_resource(runner, settings.low_resource)
    _make_tray(app)
    tunnel = TunnelManager(settings, app)
    win = MainWindow(runner, settings, tunnel)
    _windows.append(win)
    startup = autostart.STARTUP_FLAG in sys.argv  # started by Windows at sign-in
    autostart.refresh_path()
    # Windows logoff/shutdown or any other way out of the event loop: still stop servers with a save
    app.aboutToQuit.connect(lambda: runner.any_running() and runner.stop_all(20000))
    app.commitDataRequest.connect(lambda _m: runner.any_running() and runner.stop_all(20000))
    if startup and autostart.MINIMIZED_FLAG in sys.argv and QSystemTrayIcon.isSystemTrayAvailable():
        tray_message(t("{app} is running. Open it from the tray icon.", app=APP_NAME))
    else:
        win.show()
    selftest("window shown")
    if startup and settings.autostart_server:
        QTimer.singleShot(3000, lambda: _autostart_server(settings.autostart_server))
    if os.environ.pop("BARTIZAN_UPDATE_FAILED", ""):
        QTimer.singleShot(500, lambda: QMessageBox.warning(win, t("Update"), t(
            "The update couldn't replace Bartizan.exe (the file was locked, e.g. by antivirus). "
            "This is still the previous version; please try updating again.")))
    updater.cleanup_old()
    QTimer.singleShot(400, win.show_whats_new_if_updated)
    if not os.environ.get("BARTIZAN_SELFTEST"):
        QTimer.singleShot(1500, lambda: current_window() and current_window().offer_install())
        QTimer.singleShot(2500, lambda: current_window() and current_window().offer_cleanup())
    if not os.environ.get("BARTIZAN_SELFTEST") and settings.last_update_check != time.strftime("%Y-%m-%d"):
        QTimer.singleShot(4000, lambda: current_window() and current_window().check_updates(manual=False))
    if moved:
        QMessageBox.information(win, APP_NAME, t("Your servers were moved to:\n{path}", path=paths.BASE_DIR))
    if os.environ.get("BARTIZAN_SELFTEST"):
        # the build check: the app really started and runs, then quits normally with code 0
        def finish():
            selftest(f"visible={win.isVisible()} tabs={win.tabs.count()} servers={len(win.servers)}")
            for i in range(win.tabs.count()):  # every tab draws once
                win.tabs.setCurrentIndex(i)
                QApplication.processEvents()
            selftest("tabs ok")
            # quitting while a worker is still busy (like a slow network call) must exit cleanly too
            run_async(lambda task: time.sleep(30), lambda _r: None, lambda _m: None)
            app.exit(0 if win.isVisible() else 3)

        QTimer.singleShot(6000, finish)
    code = app.exec()
    selftest(f"event loop ended: {code}")
    if any_running():
        # a network lookup is still blocked in a thread; destroying it would abort the process
        if sys.stdout:  # None in the windowed EXE
            sys.stdout.flush()
        _hard_exit(code)
    sys.exit(code)
