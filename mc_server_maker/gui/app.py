"""Main window."""

import sys
import time
import traceback
from typing import List, Optional

from PySide6.QtCore import QFile, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMainWindow,
    QMenu,
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
from mc_server_maker.core import addons, network, paths, updater
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
    PlayersTab,
    SettingsTab,
    StatusTab,
    WorldTab,
    jar_paths,
    open_path,
)
from mc_server_maker.gui.tunnel_manager import TunnelManager
from mc_server_maker.gui.theme import fit_to_screen, form_layout, set_kind
from mc_server_maker.gui.widgets import with_help
from mc_server_maker.gui.workers import TaskDialog, run_async, wait_all
from mc_server_maker.i18n import LANGUAGES, set_language, t


def state_text(state: str):
    return {
        STOPPED: (t("Stopped"), theme.C["muted"]),
        STARTING: (t("Starting..."), theme.C["warn"]),
        RUNNING: (t("Running"), theme.C["accent"]),
        STOPPING: (t("Stopping..."), theme.C["warn"]),
    }[state]


def server_icon(meta: srv.ServerMeta, size: int) -> QPixmap:
    path = meta.folder / "server-icon.png"
    return theme.icon_pixmap(path if path.exists() else paths.resource("icon.png"), size)


class ServerItem(QWidget):
    """One server in the sidebar, with a ⋯ menu."""

    def __init__(self, meta: srv.ServerMeta, state: str, on_menu):
        super().__init__()
        self.meta = meta
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(server_icon(meta, 36))
        icon.setFixedSize(36, 36)
        row.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel()
        name.setObjectName("ItemName")
        sub = QLabel()
        sub.setObjectName("ItemSub")
        # long names end with "…" instead of pushing the ⋯ button out of the sidebar
        for label, text in ((name, meta.name), (sub, f"{meta.software_name} {meta.mc_version}")):
            label.setText(label.fontMetrics().elidedText(text, Qt.ElideRight, 100))
            label.setToolTip(text)
        col.addWidget(name)
        col.addWidget(sub)
        row.addLayout(col, 1)
        text, color = state_text(state)
        dot = QLabel("●")
        dot.setToolTip(text)
        dot.setStyleSheet(f"color: {color}; font-size: 11pt;")
        row.addWidget(dot)
        more = QToolButton()
        more.setText("⋯")
        more.setObjectName("MoreButton")
        more.setToolTip(t("Rename, duplicate, delete..."))
        more.setCursor(Qt.PointingHandCursor)
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
    def __init__(self, parent, settings: AppSettings, on_check_updates=None):
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
        form.addRow("", with_help(self.low_resource, t(
            "Runs servers at lower priority with a smaller memory footprint, "
            "and pauses the app's live updates while its window is hidden.")))
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
        self.servers: List[srv.ServerMeta] = []
        self.meta: Optional[srv.ServerMeta] = None

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # ---- sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(212)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(10)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(theme.icon_pixmap(paths.resource("icon.png"), 34))
        brand.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel(f"v{APP_VERSION}")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        brand.addLayout(titles, 1)
        sv.addLayout(brand)
        sv.addSpacing(6)

        new_btn = set_kind(QPushButton("＋  " + t("New server")), "primary")
        new_btn.setMinimumHeight(42)
        new_btn.clicked.connect(self.create_server)
        sv.addWidget(new_btn)
        sv.addSpacing(4)
        label = QLabel(t("SERVERS"))
        label.setObjectName("SectionLabel")
        sv.addWidget(label)
        self.list = QListWidget()
        self.list.setObjectName("ServerList")
        self.list.currentRowChanged.connect(self._select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_context_menu)
        sv.addWidget(self.list, 1)
        row = QHBoxLayout()
        folder_btn = set_kind(QPushButton("📁 " + t("Folder")), "ghost")
        folder_btn.setToolTip(str(paths.SERVERS_DIR))
        folder_btn.clicked.connect(lambda: open_path(paths.SERVERS_DIR))
        prefs_btn = set_kind(QPushButton("⚙ " + t("Settings")), "ghost")
        prefs_btn.clicked.connect(self.open_preferences)
        self.prefs_btn = prefs_btn
        self._show_update_dot()
        row.addWidget(folder_btn)
        row.addWidget(prefs_btn)
        sv.addLayout(row)
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
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(12)
        self.h_icon = QLabel()
        self.h_icon.setFixedSize(52, 52)
        hl.addWidget(self.h_icon)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.h_name = QLabel()
        self.h_name.setObjectName("ServerName")
        info.addWidget(self.h_name)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_state = QLabel()
        self.chip_state.setObjectName("Chip")
        self.chip_soft = QLabel()
        self.chip_soft.setObjectName("Chip")
        self.chip_ram = QLabel()
        self.chip_ram.setObjectName("Chip")
        for c in (self.chip_state, self.chip_soft, self.chip_ram):
            chips.addWidget(c)
        chips.addStretch()
        info.addLayout(chips)
        # the name/chips area may shrink (text is cut) so narrow screens still fit the buttons
        info_w = QWidget()
        info_w.setLayout(info)
        info.setContentsMargins(0, 0, 0, 0)
        info_w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        info_w.setMinimumWidth(140)
        hl.addWidget(info_w, 1)
        self.btn_start = set_kind(QPushButton("▶  " + t("Start")), "primary")
        self.btn_start.setMinimumSize(96, 42)
        self.btn_start.clicked.connect(self.start_server)
        self.btn_stop = QPushButton("■  " + t("Stop"))
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.clicked.connect(lambda: self.runner.stop(self.key))
        self.btn_kill = set_kind(QPushButton(t("Kill")), "danger")
        self.btn_kill.setToolTip(t("Force stop without saving"))
        self.btn_kill.setMinimumHeight(42)
        self.btn_kill.clicked.connect(self._kill)
        self.btn_folder = QPushButton("📂")
        self.btn_folder.setToolTip(t("Open server folder (plugins, mods...)"))
        self.btn_folder.setMinimumSize(44, 42)
        self.btn_folder.clicked.connect(lambda: open_path(self.meta.folder))
        for b in (self.btn_start, self.btn_stop, self.btn_kill, self.btn_folder):
            hl.addWidget(b)
        dv.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setDrawBase(False)
        self.console_tab = ConsoleTab(self.runner, self.reload)
        self.status_tab = StatusTab(self.runner, self.reload)
        self.addons_tab = AddonsTab(self.runner, self.reload)
        self.settings_tab = SettingsTab(self.runner, self.reload)
        self.world_tab = WorldTab(self.runner, self.reload)
        self.players_tab = PlayersTab(self.runner, self.reload)
        self.network_tab = NetworkTab(self.runner, self.reload)
        self.all_tabs = [
            self.console_tab, self.status_tab, self.addons_tab, self.settings_tab, self.world_tab,
            self.players_tab, self.network_tab,
        ]
        titles = ["Console", "Server status", "Plugins", "Settings", "World", "Players", "Network"]
        for tab, name in zip(self.all_tabs, titles):
            self.tabs.addTab(tab, t(name))
        self.tabs.currentChanged.connect(lambda _i: anim.fade_in(self.tabs.currentWidget(), anim.FAST))
        self.network_tab.set_tunnel(self.tunnel)
        self.status_tab.tunnel = self.tunnel
        tab_wrap = QWidget()
        tw = QVBoxLayout(tab_wrap)
        tw.setContentsMargins(8, 6, 8, 0)
        tw.addWidget(self.tabs)
        dv.addWidget(tab_wrap, 1)
        self.stack.addWidget(detail)
        root_layout.addWidget(self.stack, 1)

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
        btn = set_kind(QPushButton("＋  " + t("New server")), "primary")
        btn.setFixedSize(QSize(220, 46))
        btn.clicked.connect(self.create_server)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        v.addSpacing(10)
        v.addLayout(row)
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
        self.list.blockSignals(False)
        if self.servers:
            self.list.setCurrentRow(row)
            self._select(row)
        else:
            self.meta = None
            if self.stack.currentIndex() != 0:
                self.stack.setCurrentIndex(0)
                anim.fade_in(self.stack.currentWidget())

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

    def _select(self, row: int):
        if row < 0 or row >= len(self.servers):
            return
        changed = self.meta is None or self.meta.folder != self.servers[row].folder or self.stack.currentIndex() != 1
        self.meta = self.servers[row]
        self.stack.setCurrentIndex(1)
        if changed:  # switching servers fades the new one in
            anim.fade_in(self.stack.currentWidget(), anim.FAST)
        # Plugins / Mods tab only for software that supports them
        label = addons.kind_label(self.meta)
        idx = self.tabs.indexOf(self.addons_tab)
        if not label and self.tabs.currentIndex() == idx:
            self.tabs.setCurrentIndex(0)
        self.tabs.setTabVisible(idx, bool(label))
        if label:
            self.tabs.setTabText(idx, t(label))
        self._update_header()
        failed = []
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

    def _update_header(self):
        m = self.meta
        if not m:
            return
        state = self.runner.state(self.key)
        text, color = state_text(state)
        self.h_icon.setPixmap(server_icon(m, 52))
        self.h_name.setText(self.h_name.fontMetrics().elidedText(m.name, Qt.ElideRight, 360))
        self.h_name.setToolTip(m.name)
        self.chip_state.setText(f"● {text}")
        self.chip_state.setStyleSheet(f"color: {color};")
        self.chip_soft.setText(f"{m.software_name} {m.mc_version}")
        self.chip_ram.setText(f"RAM {m.ram_mb // 1024} GB")
        running = self.runner.is_running(self.key)
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running and state != STOPPING)
        self.btn_kill.setEnabled(running)

    def _on_state_changed(self, key: str, state: str):
        if state == STOPPED:
            for m in self.servers:
                if str(m.folder) == key and srv.end_offline_session(m):
                    self.runner.system_line(key, t("Online mode is back on."))
                    if key == self.key:
                        self.settings_tab.set_server(self.meta)  # show the restored setting
        for i, m in enumerate(self.servers):
            if str(m.folder) == key:
                self._add_item(m, i)
        if key == self.key:
            self._update_header()
            for tab in self.all_tabs:
                tab.on_state()

    # ------------------------------------------------------------------

    def open_preferences(self):
        dlg = PreferencesDialog(self, self.settings, lambda: self.check_updates(manual=True))
        if not dlg.exec():
            return
        new_theme, new_lang = dlg.theme.currentData(), dlg.language.currentData()
        changed_lang = new_lang != self.settings.language
        self.settings.theme, self.settings.language = new_theme, new_lang
        self.settings.low_resource = dlg.low_resource.isChecked()
        self.settings.save()
        apply_low_resource(self.runner, self.settings.low_resource)
        if changed_lang:
            set_language(new_lang)  # before theme.apply: the font depends on the language
        theme.apply(QApplication.instance(), new_theme)
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
        self.prefs_btn.setText("⚙ " + t("Settings") + ("  ●" if info else ""))
        self.prefs_btn.setToolTip(t("Update available: v{v}", v=info.version) if info else "")

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
        if self.runner.any_running() and QMessageBox.question(
                self, t("Update"), t("Running servers will be stopped safely before updating. Continue?")) != QMessageBox.Yes:
            return
        task_dlg = TaskDialog(self, t("Downloading v{v}...", v=info.version), lambda task: updater.download(info, task))
        task_dlg.exec()
        if not task_dlg.succeeded():
            return
        new_exe = task_dlg.result_value
        if self.runner.any_running():
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.runner.stop_all()
            QApplication.restoreOverrideCursor()
        try:
            updater.install_and_restart(new_exe)
        except OSError as e:
            QMessageBox.warning(self, t("Update"), t("Couldn't install the update: {err}", err=e))
            return
        quit_app(self)

    def show_whats_new_if_updated(self):
        """After an update, show the notes for this version once."""
        previous = self.settings.last_run_version
        self.settings.last_run_version = APP_VERSION
        self.settings.save()
        if previous and previous != APP_VERSION:
            notes = updater.bundled_notes(APP_VERSION, self.settings.language)
            if notes:
                UpdateDialog(self, t("What's new"), t("Updated to v{v}", v=APP_VERSION), notes).exec()

    def create_server(self):
        dlg = CreateServerDialog(self)
        if not dlg.exec() or not dlg.options:
            return
        opts = dlg.options
        task_dlg = TaskDialog(self, t("Creating server..."), lambda task: srv.create_server(opts, task))
        task_dlg.exec()
        if task_dlg.succeeded():
            meta = task_dlg.result_value
            self.reload(select_folder=meta.folder)
            QMessageBox.information(
                self,
                t("Done"),
                t("'{name}' is ready!\n\nPress Start — the world is generated on first start.\n"
                  "To play with friends in other homes, see the Network tab.", name=meta.name),
            )

    def start_server(self):
        if not self.meta or self.runner.is_running(self.key):
            return
        meta = self.meta
        srv.end_offline_session(meta)  # left over if the app closed while an offline run was going
        if not meta.properties().get_bool("online-mode", True):
            self._launch(meta)
            return
        # Online mode needs Mojang's sign-in servers. Without internet nobody could join
        # ("Authentication servers are down"), so offer an offline run first.
        self.btn_start.setEnabled(False)

        def checked(has_net):
            if self.meta is meta:
                self.btn_start.setEnabled(not self.runner.is_running(self.key))
            if not has_net:
                choice = self._ask_offline(meta)
                if choice is None:
                    return
                if choice:
                    srv.begin_offline_session(meta)
            self._launch(meta)

        run_async(lambda task: network.has_internet(), checked, lambda m: checked(True))

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
        if clicked is cancel:
            return None
        return clicked is offline

    def _launch(self, meta: srv.ServerMeta):
        key = str(meta.folder)
        try:
            self.runner.start(meta)
        except srv.ServerError as e:
            srv.end_offline_session(meta)
            QMessageBox.warning(self, t("Start"), str(e))
            return
        if self.meta is meta:
            self.tabs.setCurrentWidget(self.console_tab)
        if meta.offline_session:
            self.runner.system_line(key, t(
                "Offline mode for this run: players join without signing in. Online mode turns back on when the server stops."))
        if meta.tunnel and not self.tunnel.is_active():
            self.runner.system_line(key, t("Starting the playit.gg tunnel..."))
            self.tunnel.start()
        if meta.upnp:
            port = meta.properties().get_int("server-port", 25565)
            udp = udp_ports(meta)
            self.runner.system_line(key, t("Opening router port {port} (UPnP)...", port=port))

            def done(res):
                msg = t("Port {port} open — friends in other homes can join.", port=res.port)
                if res.cgnat:
                    msg += " " + t("(Warning: the router's internet IP is private; joining may not work.)")
                self.runner.system_line(key, msg)

            run_async(
                lambda task: network.open_port(port, f"Minecraft {meta.name}"[:60], udp_ports=udp),
                done,
                lambda m: self.runner.system_line(key, t("Could not open the port: {err}", err=m.replace("\n", " "))),
            )

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
        name, ok = QInputDialog.getText(self, t("Duplicate"), t("Name of the copy:"), text=t("{name} (copy)", name=meta.name))
        name = name.strip()
        if not ok or not name:
            return
        dlg = TaskDialog(self, t("Duplicate"), lambda task: srv.duplicate_server(meta, name, task))
        dlg.exec()
        if dlg.succeeded():
            self.reload(select_folder=dlg.result_value.folder)

    def delete_server(self, meta: srv.ServerMeta):
        if self.runner.is_running(str(meta.folder)):
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

    def _kill(self):
        if QMessageBox.question(
            self, t("Kill"), t("Force stop without saving? The world may be damaged.")
        ) == QMessageBox.Yes:
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
        quit_app(self)
        event.accept()

    def _detach(self):
        self.runner.state_changed.disconnect(self._on_state_changed)
        self.setAttribute(Qt.WA_DeleteOnClose)
        if self in _windows:
            _windows.remove(self)


_windows: List[MainWindow] = []  # keep windows alive
_tray: dict = {}
_update: dict = {"info": None}  # newest release found by the update check
_quitting = {"now": False}


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
        win.showNormal()
        win.raise_()
        win.activateWindow()


def quit_app(win: Optional[MainWindow] = None):
    """Stop servers safely and exit."""
    win = win or current_window()
    runner = win.runner if win else None
    if runner and runner.any_running():
        if win:
            win.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        runner.stop_all()
        QApplication.restoreOverrideCursor()
    if win and win.tunnel:
        win.tunnel.stop()
    wait_all()
    _quitting["now"] = True
    if _tray.get("icon"):
        _tray["icon"].hide()
    QApplication.instance().quit()


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
    settings = AppSettings.load()
    set_language(settings.language)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive
    theme.apply(app, settings.theme)
    runner = ServerRunner(app)
    apply_low_resource(runner, settings.low_resource)
    _make_tray(app)
    tunnel = TunnelManager(settings, app)
    win = MainWindow(runner, settings, tunnel)
    _windows.append(win)
    win.show()
    updater.cleanup_old()
    QTimer.singleShot(400, win.show_whats_new_if_updated)
    if settings.last_update_check != time.strftime("%Y-%m-%d"):
        QTimer.singleShot(4000, lambda: current_window() and current_window().check_updates(manual=False))
    if moved:
        QMessageBox.information(win, APP_NAME, t("Your servers were moved to:\n{path}", path=paths.BASE_DIR))
    sys.exit(app.exec())
