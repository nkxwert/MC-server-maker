"""메인 창."""

import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker import APP_NAME, APP_VERSION
from mc_server_maker.core import paths
from mc_server_maker.core import server as srv
from mc_server_maker.gui.create_dialog import CreateServerDialog
from mc_server_maker.gui.runner import ServerRunner
from mc_server_maker.gui.tabs import (
    ConsoleTab,
    PlayersTab,
    SettingsTab,
    UpgradeTab,
    WorldTab,
    open_path,
)
from mc_server_maker.gui.workers import TaskDialog, wait_all


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1080, 720)
        paths.ensure_dirs()
        self.runner = ServerRunner(self)
        self.runner.state_changed.connect(self._on_state_changed)
        self.servers: List[srv.ServerMeta] = []
        self.meta: Optional[srv.ServerMeta] = None

        splitter = QSplitter()
        self.setCentralWidget(splitter)

        # ---- 왼쪽: 서버 목록
        left = QWidget()
        lv = QVBoxLayout(left)
        title = QLabel("내 서버")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        lv.addWidget(title)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        lv.addWidget(self.list, 1)
        new_btn = QPushButton("＋ 새 서버 만들기")
        new_btn.setMinimumHeight(40)
        new_btn.setStyleSheet("font-weight: bold;")
        new_btn.clicked.connect(self.create_server)
        lv.addWidget(new_btn)
        row = QHBoxLayout()
        folder_btn = QPushButton("서버 폴더")
        folder_btn.clicked.connect(lambda: open_path(paths.SERVERS_DIR))
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.reload)
        row.addWidget(folder_btn)
        row.addWidget(refresh_btn)
        lv.addLayout(row)
        splitter.addWidget(left)

        # ---- 오른쪽: 서버 정보 + 탭
        self.stack = QStackedWidget()
        empty = QLabel("왼쪽 아래 '＋ 새 서버 만들기'를 눌러 첫 서버를 만들어 보세요!")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet("font-size: 15px; color: gray;")
        self.stack.addWidget(empty)

        detail = QWidget()
        dv = QVBoxLayout(detail)
        header = QHBoxLayout()
        info = QVBoxLayout()
        self.h_name = QLabel()
        self.h_name.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.h_sub = QLabel()
        self.h_sub.setStyleSheet("color: gray;")
        self.h_addr = QLabel()
        self.h_addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.addWidget(self.h_name)
        info.addWidget(self.h_sub)
        info.addWidget(self.h_addr)
        header.addLayout(info, 1)
        self.btn_start = QPushButton("▶ 서버 켜기")
        self.btn_start.setMinimumSize(120, 40)
        self.btn_start.setStyleSheet("font-weight: bold;")
        self.btn_start.clicked.connect(self.start_server)
        self.btn_stop = QPushButton("■ 끄기")
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.clicked.connect(lambda: self.runner.stop(self.key))
        self.btn_kill = QPushButton("강제 종료")
        self.btn_kill.setMinimumHeight(40)
        self.btn_kill.clicked.connect(self._kill)
        self.btn_folder = QPushButton("📂 폴더")
        self.btn_folder.setMinimumHeight(40)
        self.btn_folder.clicked.connect(lambda: open_path(self.meta.folder))
        for b in (self.btn_start, self.btn_stop, self.btn_kill, self.btn_folder):
            header.addWidget(b)
        dv.addLayout(header)

        self.tabs = QTabWidget()
        self.settings_tab = SettingsTab(self.runner, self.reload)
        self.world_tab = WorldTab(self.runner, self.reload)
        self.players_tab = PlayersTab(self.runner, self.reload)
        self.console_tab = ConsoleTab(self.runner, self.reload)
        self.upgrade_tab = UpgradeTab(self.runner, self.reload)
        self.all_tabs = [self.settings_tab, self.world_tab, self.players_tab, self.console_tab, self.upgrade_tab]
        self.tabs.addTab(self.settings_tab, "⚙ 설정")
        self.tabs.addTab(self.world_tab, "🌍 맵")
        self.tabs.addTab(self.players_tab, "👤 플레이어")
        self.tabs.addTab(self.console_tab, "🖥 콘솔")
        self.tabs.addTab(self.upgrade_tab, "⬆ 업그레이드")
        dv.addWidget(self.tabs, 1)
        self.stack.addWidget(detail)
        splitter.addWidget(self.stack)
        splitter.setSizes([260, 820])

        self.reload()

    # ------------------------------------------------------------------

    @property
    def key(self) -> str:
        return str(self.meta.folder) if self.meta else ""

    def reload(self, select_folder=None):
        """디스크에서 서버 목록을 다시 읽고, 선택했던 서버를 유지한다."""
        keep = str(select_folder) if select_folder else self.key
        self.servers = srv.list_servers()
        self.list.blockSignals(True)
        self.list.clear()
        row = 0
        for i, m in enumerate(self.servers):
            item = QListWidgetItem(self._list_label(m))
            self.list.addItem(item)
            if str(m.folder) == keep:
                row = i
        self.list.blockSignals(False)
        if self.servers:
            self.list.setCurrentRow(row)
            self._select(row)
        else:
            self.meta = None
            self.stack.setCurrentIndex(0)

    def _list_label(self, m: srv.ServerMeta) -> str:
        dot = "🟢" if self.runner.is_running(str(m.folder)) else "⚪"
        return f"{dot} {m.name}\n     {m.software_name.split(' (')[0]} {m.mc_version}"

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
        running = self.runner.is_running(self.key)
        self.h_name.setText(m.name)
        self.h_sub.setText(
            f"{m.software_name} · {m.mc_version}{f' (빌드 {m.build})' if m.build else ''} · "
            f"RAM {m.ram_mb // 1024}GB · Java {m.java_major}"
        )
        port = m.properties().get_int("server-port", 25565)
        port_text = "" if port == 25565 else f":{port}"
        self.h_addr.setText(
            f"{'🟢 실행 중' if running else '⚪ 꺼짐'}   ·   "
            f"같은 PC: localhost{port_text}   ·   같은 와이파이: {srv.lan_ip()}{port_text}"
        )
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_kill.setEnabled(running)

    def _on_state_changed(self, key: str, running: bool):
        for i, m in enumerate(self.servers):
            if str(m.folder) == key:
                self.list.item(i).setText(self._list_label(m))
        if key == self.key:
            self._update_header()
            for tab in self.all_tabs:
                tab.refresh()

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
                "설정 탭에서 서버 설명과 사진을 바꿀 수 있어요.",
            )

    def start_server(self):
        if not self.meta:
            return
        try:
            self.runner.start(self.meta)
        except srv.ServerError as e:
            QMessageBox.warning(self, "서버 켜기", str(e))
            return
        self.tabs.setCurrentWidget(self.console_tab)

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
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
