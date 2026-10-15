"""메인 창."""

import sys
from typing import List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker import APP_NAME, APP_VERSION
from mc_server_maker.core import network, paths
from mc_server_maker.core import server as srv
from mc_server_maker.gui import theme
from mc_server_maker.gui.create_dialog import CreateServerDialog
from mc_server_maker.gui.runner import RUNNING, STARTING, STOPPED, STOPPING, ServerRunner
from mc_server_maker.gui.tabs import (
    ConsoleTab,
    NetworkTab,
    PlayersTab,
    SettingsTab,
    UpgradeTab,
    WorldTab,
    open_path,
)
from mc_server_maker.gui.theme import set_kind
from mc_server_maker.gui.workers import TaskDialog, run_async, wait_all

STATE_TEXT = {
    STOPPED: ("꺼짐", theme.MUTED),
    STARTING: ("켜는 중...", theme.WARN),
    RUNNING: ("실행 중", theme.ACCENT),
    STOPPING: ("끄는 중...", theme.WARN),
}


def server_icon(meta: srv.ServerMeta, size: int) -> QPixmap:
    path = meta.folder / "server-icon.png"
    pix = QPixmap(str(path)) if path.exists() else QPixmap(str(paths.resource("default-server.png")))
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)


class ServerItem(QWidget):
    """사이드바의 서버 한 줄."""

    def __init__(self, meta: srv.ServerMeta, state: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(server_icon(meta, 36))
        icon.setFixedSize(36, 36)
        row.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(meta.name)
        name.setObjectName("ItemName")
        sub = QLabel(f"{meta.software_name.split(' (')[0]} {meta.mc_version}")
        sub.setObjectName("ItemSub")
        col.addWidget(name)
        col.addWidget(sub)
        row.addLayout(col, 1)
        text, color = STATE_TEXT[state]
        dot = QLabel("●")
        dot.setToolTip(text)
        dot.setStyleSheet(f"color: {color}; font-size: 11pt;")
        row.addWidget(dot)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        paths.ensure_dirs()
        self.runner = ServerRunner(self)
        self.runner.state_changed.connect(self._on_state_changed)
        self.servers: List[srv.ServerMeta] = []
        self.meta: Optional[srv.ServerMeta] = None

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # ---- 왼쪽: 사이드바
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(270)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(10)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(paths.resource("icon.png"))).scaled(34, 34, Qt.KeepAspectRatio, Qt.FastTransformation))
        brand.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("MC Server Maker")
        t.setObjectName("AppTitle")
        st = QLabel(f"마인크래프트 서버 관리 · v{APP_VERSION}")
        st.setObjectName("AppSubtitle")
        titles.addWidget(t)
        titles.addWidget(st)
        brand.addLayout(titles, 1)
        sv.addLayout(brand)
        sv.addSpacing(6)

        new_btn = set_kind(QPushButton("＋  새 서버 만들기"), "primary")
        new_btn.setMinimumHeight(42)
        new_btn.clicked.connect(self.create_server)
        sv.addWidget(new_btn)
        sv.addSpacing(4)
        label = QLabel("내 서버")
        label.setObjectName("SectionLabel")
        sv.addWidget(label)
        self.list = QListWidget()
        self.list.setObjectName("ServerList")
        self.list.currentRowChanged.connect(self._select)
        sv.addWidget(self.list, 1)
        row = QHBoxLayout()
        folder_btn = set_kind(QPushButton("📁 서버 폴더"), "ghost")
        folder_btn.clicked.connect(lambda: open_path(paths.SERVERS_DIR))
        refresh_btn = set_kind(QPushButton("↻ 새로고침"), "ghost")
        refresh_btn.clicked.connect(lambda: self.reload())
        row.addWidget(folder_btn)
        row.addWidget(refresh_btn)
        sv.addLayout(row)
        root_layout.addWidget(side)

        # ---- 오른쪽
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
        hl.setSpacing(14)
        self.h_icon = QLabel()
        self.h_icon.setFixedSize(56, 56)
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
        hl.addLayout(info, 1)
        self.btn_start = set_kind(QPushButton("▶  서버 켜기"), "primary")
        self.btn_start.setMinimumSize(130, 42)
        self.btn_start.clicked.connect(self.start_server)
        self.btn_stop = QPushButton("■  끄기")
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.clicked.connect(lambda: self.runner.stop(self.key))
        self.btn_kill = set_kind(QPushButton("강제 종료"), "danger")
        self.btn_kill.setMinimumHeight(42)
        self.btn_kill.clicked.connect(self._kill)
        self.btn_folder = QPushButton("📂")
        self.btn_folder.setToolTip("서버 폴더 열기 (plugins, mods 폴더에 파일을 넣을 때)")
        self.btn_folder.setMinimumSize(44, 42)
        self.btn_folder.clicked.connect(lambda: open_path(self.meta.folder))
        for b in (self.btn_start, self.btn_stop, self.btn_kill, self.btn_folder):
            hl.addWidget(b)
        dv.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setDrawBase(False)
        self.console_tab = ConsoleTab(self.runner, self.reload)
        self.settings_tab = SettingsTab(self.runner, self.reload)
        self.world_tab = WorldTab(self.runner, self.reload)
        self.players_tab = PlayersTab(self.runner, self.reload)
        self.network_tab = NetworkTab(self.runner, self.reload)
        self.upgrade_tab = UpgradeTab(self.runner, self.reload)
        self.all_tabs = [
            self.console_tab, self.settings_tab, self.world_tab,
            self.players_tab, self.network_tab, self.upgrade_tab,
        ]
        for tab, title in zip(self.all_tabs, ["🖥 콘솔", "⚙ 설정", "🌍 맵", "👤 플레이어", "🌐 외부 접속", "⬆ 업그레이드"]):
            self.tabs.addTab(tab, title)
        tab_wrap = QWidget()
        tw = QVBoxLayout(tab_wrap)
        tw.setContentsMargins(8, 6, 8, 0)
        tw.addWidget(self.tabs)
        dv.addWidget(tab_wrap, 1)
        self.stack.addWidget(detail)
        root_layout.addWidget(self.stack, 1)

        self.reload()

    def _empty_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        icon = QLabel()
        icon.setPixmap(QPixmap(str(paths.resource("icon.png"))).scaled(96, 96, Qt.KeepAspectRatio, Qt.FastTransformation))
        icon.setAlignment(Qt.AlignCenter)
        v.addWidget(icon)
        title = QLabel("첫 마인크래프트 서버를 만들어 보세요")
        title.setObjectName("Big")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)
        sub = QLabel("구동기와 버전만 고르면 다운로드부터 설정까지 자동으로 해 드려요.")
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignCenter)
        v.addWidget(sub)
        btn = set_kind(QPushButton("＋  새 서버 만들기"), "primary")
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
        """디스크에서 서버 목록을 다시 읽고, 선택했던 서버를 유지한다."""
        keep = str(select_folder) if select_folder else self.key
        self.servers = srv.list_servers()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self._drop_widget(self.list.item(i))
        self.list.clear()
        row = 0
        for i, m in enumerate(self.servers):
            self._add_item(m)
            if str(m.folder) == keep:
                row = i
        self.list.blockSignals(False)
        if self.servers:
            self.list.setCurrentRow(row)
            self._select(row)
        else:
            self.meta = None
            self.stack.setCurrentIndex(0)

    def _add_item(self, m: srv.ServerMeta, row: Optional[int] = None):
        widget = ServerItem(m, self.runner.state(str(m.folder)))
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
        self.meta = self.servers[row]
        self.stack.setCurrentIndex(1)
        self._update_header()
        for tab in self.all_tabs:
            tab.set_server(self.meta)

    def _update_header(self):
        m = self.meta
        if not m:
            return
        state = self.runner.state(self.key)
        text, color = STATE_TEXT[state]
        self.h_icon.setPixmap(server_icon(m, 56))
        self.h_name.setText(m.name)
        self.chip_state.setText(f"● {text}")
        self.chip_state.setStyleSheet(f"color: {color};")
        self.chip_soft.setText(f"{m.software_name.split(' (')[0]} {m.mc_version}")
        self.chip_ram.setText(f"RAM {m.ram_mb // 1024}GB")
        running = self.runner.is_running(self.key)
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running and state != STOPPING)
        self.btn_kill.setEnabled(running)

    def _on_state_changed(self, key: str, state: str):
        for i, m in enumerate(self.servers):
            if str(m.folder) == key:
                self._add_item(m, i)
        if key == self.key:
            self._update_header()
            for tab in self.all_tabs:
                tab.on_state()

    # ------------------------------------------------------------------

    def create_server(self):
        dlg = CreateServerDialog(self)
        if not dlg.exec() or not dlg.options:
            return
        opts = dlg.options
        task_dlg = TaskDialog(self, "서버 만드는 중...", lambda task: srv.create_server(opts, task))
        task_dlg.exec()
        if task_dlg.succeeded():
            meta = task_dlg.result_value
            self.reload(select_folder=meta.folder)
            QMessageBox.information(
                self,
                "완료",
                f"'{meta.name}' 서버를 만들었습니다!\n\n"
                "▶ 서버 켜기를 누르면 처음 실행할 때 맵이 만들어집니다.\n"
                "다른 집 친구와 같이 하려면 '🌐 외부 접속' 탭을 확인하세요.",
            )

    def start_server(self):
        if not self.meta:
            return
        meta = self.meta
        key = self.key
        try:
            self.runner.start(meta)
        except srv.ServerError as e:
            QMessageBox.warning(self, "서버 켜기", str(e))
            return
        self.tabs.setCurrentWidget(self.console_tab)
        if meta.upnp:
            port = meta.properties().get_int("server-port", 25565)
            self.runner.system_line(key, f"공유기 포트 {port} 자동으로 여는 중 (UPnP)...")

            def done(res):
                msg = f"포트 {res.port} 열림 - 다른 집에서 접속할 수 있습니다."
                if res.cgnat:
                    msg += " (주의: 공유기 외부 IP가 사설 IP라 접속이 안 될 수 있어요)"
                self.runner.system_line(key, msg)

            run_async(
                lambda task: network.open_port(port, f"Minecraft {meta.name}"[:60]),
                done,
                lambda m: self.runner.system_line(key, "포트 자동 열기 실패: " + m.replace("\n", " ")),
            )

    def _kill(self):
        if QMessageBox.question(
            self, "강제 종료", "저장하지 않고 강제로 끕니다. 맵 데이터가 손상될 수 있어요. 계속할까요?"
        ) == QMessageBox.Yes:
            self.runner.kill(self.key)

    def closeEvent(self, event):
        if self.runner.any_running():
            answer = QMessageBox.question(
                self, "종료", "켜져 있는 서버가 있습니다. 서버를 안전하게 끄고 프로그램을 종료할까요?"
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.runner.stop_all()
            QApplication.restoreOverrideCursor()
        wait_all()
        event.accept()


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == "win32":
        # 작업 표시줄에 파이썬 아이콘 대신 앱 아이콘이 보이게
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MCServerMaker")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    theme.apply(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
