"""서버 관리 탭들: 설정 / 월드 / 플레이어 / 콘솔 / 업그레이드."""

import os
import re
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import network, players
from mc_server_maker.core import server as srv
from mc_server_maker.core import versions
from mc_server_maker.core.providers import get_provider
from mc_server_maker.gui.create_dialog import VersionLoader, random_seed
from mc_server_maker.gui.runner import ServerRunner
from mc_server_maker.gui.theme import ACCENT, DANGER, INFO, TEXT, WARN, set_kind
from mc_server_maker.gui.widgets import (
    COLOR_HELP,
    MotdPreview,
    amp_to_section,
    convert_icon,
    section_to_amp,
)
from mc_server_maker.gui.workers import TaskDialog, run_async


def open_path(path: Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def gray(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


def warn_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Warn")
    return label


class ServerTab(QWidget):
    """공통: 현재 서버와 실행 상태를 받는다."""

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
        """서버가 켜지거나 꺼졌을 때."""
        self.refresh()

    def run_task(self, title: str, fn) -> bool:
        dlg = TaskDialog(self, title, fn)
        dlg.exec()
        return dlg.succeeded()


def _scroll(widget: QWidget) -> QScrollArea:
    widget.layout().setContentsMargins(16, 8, 16, 16)
    widget.layout().setSpacing(10)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


# ===================================================================== 설정


class SettingsTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        # 이름 / MOTD / 아이콘
        box = QGroupBox("서버 이름 · 설명 · 사진")
        form = QFormLayout(box)
        self.name = QLineEdit()
        form.addRow("서버 이름", self.name)
        form.addRow("", gray("이 프로그램에 표시되는 이름입니다. 마인크래프트 서버 목록에는 아래 설명(MOTD)이 보입니다."))
        self.motd = QPlainTextEdit()
        self.motd.setFixedHeight(56)
        self.motd.textChanged.connect(self._update_preview)
        form.addRow("서버 설명\n(MOTD, 2줄까지)", self.motd)
        form.addRow("", gray(COLOR_HELP))

        icon_row = QHBoxLayout()
        pick = QPushButton("🖼 사진 선택...")
        pick.clicked.connect(self._pick_icon)
        remove = QPushButton("사진 삭제")
        remove.clicked.connect(self._remove_icon)
        icon_row.addWidget(pick)
        icon_row.addWidget(remove)
        icon_row.addStretch()
        form.addRow("서버 사진", icon_row)
        form.addRow("", gray("아무 사진이나 고르면 가운데를 잘라 64×64 server-icon.png 로 자동 변환합니다."))
        self.preview = MotdPreview()
        form.addRow("미리보기", self.preview)
        layout.addWidget(box)

        # 게임 설정
        box = QGroupBox("게임 설정")
        form = QFormLayout(box)
        self.max_players = QSpinBox(minimum=1, maximum=1000)
        form.addRow("최대 인원", self.max_players)
        self.gamemode = QComboBox()
        for k, label in srv.GAMEMODES:
            self.gamemode.addItem(label, k)
        form.addRow("게임 모드", self.gamemode)
        self.difficulty = QComboBox()
        for k, label in srv.DIFFICULTIES:
            self.difficulty.addItem(label, k)
        form.addRow("난이도", self.difficulty)
        self.port = QSpinBox(minimum=1, maximum=65535)
        form.addRow("포트", self.port)
        self.view_distance = QSpinBox(minimum=2, maximum=32)
        form.addRow("시야 거리 (청크)", self.view_distance)
        self.spawn_protection = QSpinBox(minimum=0, maximum=1000)
        form.addRow("스폰 보호 범위", self.spawn_protection)
        self.checks = {}
        for key, label in (
            ("online-mode", "정품 인증 (끄면 비정품 접속 허용)"),
            ("pvp", "PvP 허용"),
            ("hardcore", "하드코어"),
            ("white-list", "화이트리스트 사용 (등록된 사람만 접속)"),
            ("allow-flight", "비행 허용 (모드/플러그인 서버에 권장)"),
            ("enable-command-block", "커맨드 블록 허용"),
        ):
            cb = QCheckBox(label)
            self.checks[key] = cb
            form.addRow("", cb)
        layout.addWidget(box)

        box = QGroupBox("실행")
        form = QFormLayout(box)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64)
        form.addRow("메모리(RAM)", self.ram)
        layout.addWidget(box)

        self.notice = warn_label("")
        layout.addWidget(self.notice)
        save = set_kind(QPushButton("💾 저장"), "primary")
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
        self.spawn_protection.setValue(p.get_int("spawn-protection", 16))
        defaults = {"online-mode": True, "pvp": True}
        for key, cb in self.checks.items():
            cb.setChecked(p.get_bool(key, defaults.get(key, False)))
        self.ram.setValue(max(1, self.meta.ram_mb // 1024))
        self.notice.setText("⚠ 서버가 켜져 있습니다. 저장한 설정은 서버를 다시 켜야 적용됩니다." if self.running else "")
        self._update_preview()

    def on_state(self):
        # 입력 중인 내용을 덮어쓰지 않도록 안내 문구만 바꾼다
        self.notice.setText("⚠ 서버가 켜져 있습니다. 저장한 설정은 서버를 다시 켜야 적용됩니다." if self.running else "")

    def _update_preview(self):
        if not self.meta:
            return
        motd = "\n".join(self.motd.toPlainText().splitlines()[:2])
        self.preview.update_preview("Minecraft Server", amp_to_section(motd), self.icon_path)

    def _pick_icon(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "서버 사진 선택", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not f:
            return
        try:
            convert_icon(f, self.icon_path)
        except ValueError as e:
            QMessageBox.warning(self, "사진", str(e))
            return
        self._update_preview()

    def _remove_icon(self):
        self.icon_path.unlink(missing_ok=True)
        self._update_preview()

    def save(self):
        if not self.meta:
            return
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "저장", "서버 이름을 입력해 주세요.")
            return
        lines = self.motd.toPlainText().splitlines()
        if len(lines) > 2:
            QMessageBox.information(self, "저장", "서버 설명은 2줄까지만 표시되어 앞의 2줄만 저장합니다.")
        v = self.meta.mc_version
        p = self.meta.properties()
        p.set("motd", amp_to_section("\n".join(lines[:2])))
        p.set("max-players", self.max_players.value())
        p.set("gamemode", srv.gamemode_value(self.gamemode.currentData(), v))
        p.set("difficulty", srv.difficulty_value(self.difficulty.currentData(), v))
        p.set("server-port", self.port.value())
        p.set("view-distance", self.view_distance.value())
        p.set("spawn-protection", self.spawn_protection.value())
        for key, cb in self.checks.items():
            p.set(key, cb.isChecked())
        p.set("enforce-whitelist", self.checks["white-list"].isChecked())
        p.save()
        self.meta.name = name
        self.meta.ram_mb = self.ram.value() * 1024
        self.meta.save()
        srv.write_start_scripts(self.meta)
        self.on_changed()
        QMessageBox.information(self, "저장", "저장했습니다." + ("\n서버를 다시 켜면 적용됩니다." if self.running else ""))


# ===================================================================== 월드


class WorldTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box = QGroupBox("현재 맵")
        form = QFormLayout(box)
        self.info_name = QLabel()
        self.info_seed = QLabel()
        self.info_seed.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_type = QLabel()
        self.info_exists = QLabel()
        form.addRow("맵 폴더", self.info_name)
        form.addRow("시드", self.info_seed)
        form.addRow("맵 종류", self.info_type)
        form.addRow("상태", self.info_exists)
        layout.addWidget(box)

        self.running_notice = warn_label("⚠ 서버가 켜져 있는 동안에는 맵을 바꿀 수 없습니다. 먼저 서버를 꺼 주세요.")
        layout.addWidget(self.running_notice)

        # 새 맵
        box = QGroupBox("새 맵 만들기 (지금 맵은 자동 백업 후 교체)")
        v = QVBoxLayout(box)
        self.mode_group = QButtonGroup(self)
        self.rb_random = QRadioButton("무작위 맵")
        self.rb_seed = QRadioButton("시드로 생성")
        self.rb_random.setChecked(True)
        self.mode_group.addButton(self.rb_random, 0)
        self.mode_group.addButton(self.rb_seed, 1)
        v.addWidget(self.rb_random)
        v.addWidget(self.rb_seed)
        row = QHBoxLayout()
        self.seed = QLineEdit(placeholderText="시드 입력")
        dice = QPushButton("🎲 무작위 시드")
        dice.clicked.connect(lambda: (self.rb_seed.setChecked(True), self.seed.setText(random_seed())))
        row.addSpacing(24)
        row.addWidget(self.seed, 1)
        row.addWidget(dice)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("맵 종류"))
        self.level_type = QComboBox()
        for k, label in srv.LEVEL_TYPES:
            self.level_type.addItem(label, k)
        row.addWidget(self.level_type, 1)
        v.addLayout(row)
        self.btn_new = set_kind(QPushButton("🌱 새 맵으로 교체"), "primary")
        self.btn_new.clicked.connect(self._new_world)
        v.addWidget(self.btn_new)
        self.mode_group.idToggled.connect(lambda *_: self.seed.setEnabled(self.rb_seed.isChecked()))
        self.seed.setEnabled(False)
        layout.addWidget(box)

        # 불러오기
        box = QGroupBox("맵 불러오기 (싱글플레이 맵, 다운받은 맵 등)")
        v = QVBoxLayout(box)
        v.addWidget(gray("싱글플레이 맵은 .minecraft/saves 폴더 안에 있습니다. level.dat 이 들어 있는 폴더나 zip을 고르세요."))
        row = QHBoxLayout()
        self.btn_import_dir = QPushButton("📁 폴더에서 불러오기")
        self.btn_import_dir.clicked.connect(self._import_dir)
        self.btn_import_zip = QPushButton("🗜 zip에서 불러오기")
        self.btn_import_zip.clicked.connect(self._import_zip)
        row.addWidget(self.btn_import_dir)
        row.addWidget(self.btn_import_zip)
        v.addLayout(row)
        layout.addWidget(box)

        # 백업
        box = QGroupBox("백업")
        v = QVBoxLayout(box)
        self.backup_info = gray("")
        v.addWidget(self.backup_info)
        row = QHBoxLayout()
        self.btn_backup = QPushButton("💾 지금 맵 백업")
        self.btn_backup.clicked.connect(self._backup)
        open_btn = QPushButton("백업 폴더 열기")
        open_btn.clicked.connect(lambda: open_path(self.meta.folder / srv.BACKUP_DIR))
        row.addWidget(self.btn_backup)
        row.addWidget(open_btn)
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
        self.info_name.setText(level)
        seed = p.get("level-seed") or ""
        level_dat_seed = "(무작위)" if not seed else seed
        self.info_seed.setText(level_dat_seed)
        lt = srv.parse_level_type(p.get("level-type"))
        self.info_type.setText(dict(srv.LEVEL_TYPES)[lt])
        self.level_type.setCurrentIndex(self.level_type.findData(lt))
        exists = (self.meta.folder / level / "level.dat").exists()
        self.info_exists.setText("맵 있음" if exists else "아직 없음 (서버를 처음 켤 때 만들어짐)")
        backups = srv.list_backups(self.meta)
        self.backup_info.setText(f"백업 {len(backups)}개" + (f" · 최근: {backups[0].name}" if backups else ""))
        running = self.running
        self.running_notice.setVisible(running)
        for w in (self.btn_new, self.btn_import_dir, self.btn_import_zip, self.btn_backup):
            w.setEnabled(not running)

    def _confirm(self, text: str) -> bool:
        return (
            QMessageBox.question(self, "맵 교체", text + "\n\n지금 맵은 backups 폴더에 자동으로 백업됩니다.")
            == QMessageBox.Yes
        )

    def _new_world(self):
        seed = self.seed.text().strip() if self.rb_seed.isChecked() else ""
        if self.rb_seed.isChecked() and not seed:
            QMessageBox.warning(self, "새 맵", "시드를 입력하거나 🎲 버튼을 눌러 주세요.")
            return
        if not self._confirm("지금 맵을 지우고 새 맵을 만들까요?"):
            return
        meta, lt = self.meta, self.level_type.currentData()
        self.run_task("새 맵 만들기", lambda task: srv.regenerate_world(meta, seed, lt, task))
        self.refresh()

    def _import(self, path: str):
        try:
            srv.find_world_root(path)
        except srv.ServerError as e:
            QMessageBox.warning(self, "맵 불러오기", str(e))
            return
        if not self._confirm(f"'{Path(path).name}' 맵으로 교체할까요?"):
            return
        meta = self.meta
        self.run_task("맵 불러오기", lambda task: srv.replace_world_with_import(meta, Path(path), task))
        self.refresh()

    def _import_dir(self):
        d = QFileDialog.getExistingDirectory(self, "맵 폴더 선택 (level.dat 이 있는 폴더)")
        if d:
            self._import(d)

    def _import_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "맵 zip 선택", "", "Zip 파일 (*.zip)")
        if f:
            self._import(f)

    def _backup(self):
        meta = self.meta
        if not any(d.exists() for d in srv.world_dirs(meta)):
            QMessageBox.information(self, "백업", "아직 맵이 없습니다.")
            return
        self.run_task("맵 백업", lambda task: srv.backup_server(meta, "world", worlds_only=True, task=task))
        self.refresh()


# ================================================================= 플레이어


class PlayersTab(ServerTab):
    KINDS = (("ops", "OP (관리자)", "op", "deop"), ("whitelist", "화이트리스트", "whitelist add", "whitelist remove"))

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 16)
        self.hint = gray("")
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        self.lists = {}
        for kind, title, add_cmd, remove_cmd in self.KINDS:
            box = QGroupBox(title)
            v = QVBoxLayout(box)
            lst = QListWidget()
            v.addWidget(lst)
            buttons = QHBoxLayout()
            add = QPushButton("추가")
            add.clicked.connect(lambda _=False, k=kind, c=add_cmd: self._add(k, c))
            rem = QPushButton("삭제")
            rem.clicked.connect(lambda _=False, k=kind, c=remove_cmd: self._remove(k, c))
            buttons.addWidget(add)
            buttons.addWidget(rem)
            v.addLayout(buttons)
            self.lists[kind] = lst
            row.addWidget(box)
        layout.addLayout(row)
        refresh = QPushButton("새로고침")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

    def refresh(self):
        if not self.meta:
            return
        for kind, lst in self.lists.items():
            lst.clear()
            lst.addItems(players.list_names(self.meta.folder, kind))
        online = self.meta.properties().get_bool("online-mode", True)
        self.hint.setText(
            ("서버가 켜져 있어서 콘솔 명령어로 바로 적용합니다. " if self.running else "")
            + ("정품 인증이 켜져 있어 정확한 마인크래프트 닉네임이 필요합니다." if online else "비정품(오프라인) 모드입니다.")
        )

    def _add(self, kind: str, command: str):
        name, ok = QInputDialog.getText(self, "플레이어 추가", "마인크래프트 닉네임:")
        name = name.strip()
        if not ok or not name:
            return
        if self.running:
            self.runner.send(self.key, f"{command} {name}")
            self._refresh_later()
            return
        folder = self.meta.folder
        online = self.meta.properties().get_bool("online-mode", True)
        run_async(
            lambda task: players.add(folder, kind, name, online),
            lambda _: self.refresh(),
            lambda msg: QMessageBox.warning(self, "플레이어 추가", msg),
        )

    def _remove(self, kind: str, command: str):
        item = self.lists[kind].currentItem()
        if not item:
            return
        name = item.text()
        if self.running:
            self.runner.send(self.key, f"{command} {name}")
            self._refresh_later()
        else:
            players.remove(self.meta.folder, kind, name)
            self.refresh()

    def _refresh_later(self):
        QTimer.singleShot(1500, self.refresh)


# ===================================================================== 콘솔

_CONSOLE_RULES = [
    (re.compile(r"^»» "), ACCENT, True),
    (re.compile(r"^> "), INFO, True),
    (re.compile(r"ERROR|SEVERE|Exception|^\s+at "), DANGER, False),
    (re.compile(r"WARN"), WARN, False),
    (re.compile(r"joined the game"), ACCENT, False),
    (re.compile(r"left the game"), "#e6a35c", False),
    (re.compile(r": <[^>]+> "), TEXT, True),  # 채팅
    (re.compile(r"Done \("), ACCENT, True),
]


def _line_format(line: str) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor("#b9c0cb"))
    for pattern, color, bold in _CONSOLE_RULES:
        if pattern.search(line):
            fmt.setForeground(QColor(color))
            if bold:
                fmt.setFontWeight(QFont.Bold)
            break
    return fmt


class HistoryLineEdit(QLineEdit):
    """↑/↓ 키로 이전 명령어를 다시 불러온다."""

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
    QUICK = [
        ("☀ 낮", "time set day"),
        ("🌙 밤", "time set night"),
        ("🌤 맑음", "weather clear"),
        ("💾 저장", "save-all"),
        ("👥 접속자", "list"),
    ]

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
        self.view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        left.addWidget(self.view, 1)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        self.quick_buttons = []
        for label, cmd in self.QUICK:
            b = QPushButton(label)
            b.setToolTip(cmd)
            b.clicked.connect(lambda _=False, c=cmd: self._run(c))
            quick.addWidget(b)
            self.quick_buttons.append(b)
        quick.addStretch()
        clear = set_kind(QPushButton("🧹 지우기"), "ghost")
        clear.clicked.connect(self._clear)
        quick.addWidget(clear)
        left.addLayout(quick)

        row = QHBoxLayout()
        self.input = HistoryLineEdit(placeholderText="명령어 입력 후 Enter  (예: say 안녕, gamemode creative 닉네임)   ↑↓ 이전 명령어")
        self.input.setObjectName("ConsoleInput")
        self.input.returnPressed.connect(self._send)
        self.send_btn = set_kind(QPushButton("보내기"), "primary")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        left.addLayout(row)
        outer.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        box = QGroupBox("접속 중인 플레이어")
        v = QVBoxLayout(box)
        self.player_count = QLabel("0명")
        self.player_count.setObjectName("Big")
        v.addWidget(self.player_count)
        self.player_list = QListWidget()
        v.addWidget(self.player_list, 1)
        self.btn_op = QPushButton("👑 OP 주기")
        self.btn_op.clicked.connect(lambda: self._player_cmd("op"))
        self.btn_kick = set_kind(QPushButton("추방"), "danger")
        self.btn_kick.clicked.connect(lambda: self._player_cmd("kick"))
        v.addWidget(self.btn_op)
        v.addWidget(self.btn_kick)
        side.addWidget(box, 1)
        box = QGroupBox("가동 시간")
        v = QVBoxLayout(box)
        self.uptime = QLabel("-")
        self.uptime.setObjectName("Big")
        v.addWidget(self.uptime)
        side.addWidget(box)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(210)
        side.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(side_w)

        runner.line.connect(self._on_line)
        runner.players_changed.connect(self._on_players)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def refresh(self):
        self.view.clear()
        if self.meta:
            cursor = QTextCursor(self.view.document())
            for ln in self.runner.log_lines(self.key):
                self._insert(cursor, ln)
            if self.view.document().isEmpty() or not self.runner.log_lines(self.key):
                self.view.setPlaceholderText("서버가 꺼져 있습니다. 위의 ▶ 서버 켜기를 누르면 여기에 서버 로그가 나옵니다.")
        self.view.moveCursor(QTextCursor.End)
        running = self.running
        for w in [self.input, self.send_btn, *self.quick_buttons]:
            w.setEnabled(running)
        self._on_players(self.key)
        self._tick()

    def on_state(self):
        # 로그를 다시 그리지 않고 버튼만 갱신
        running = self.running
        for w in [self.input, self.send_btn, *self.quick_buttons]:
            w.setEnabled(running)
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
        self.player_count.setText(f"{len(names)}명")
        has = bool(names) and self.running
        self.btn_op.setEnabled(has)
        self.btn_kick.setEnabled(has)

    def _tick(self):
        secs = int(self.runner.uptime(self.key)) if self.meta else 0
        if not secs:
            self.uptime.setText("-")
            return
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        self.uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _run(self, cmd: str):
        self.runner.send(self.key, cmd)

    def _player_cmd(self, cmd: str):
        item = self.player_list.currentItem()
        if not item:
            QMessageBox.information(self, "플레이어", "목록에서 플레이어를 먼저 선택해 주세요.")
            return
        self._run(f"{cmd} {item.text()}")

    def _clear(self):
        self.runner.clear_log(self.key)
        self.view.clear()

    def _send(self):
        cmd = self.input.text().strip().lstrip("/")
        if cmd and self.runner.send(self.key, cmd):
            self.input.remember(cmd)
            self.input.clear()


# ================================================================ 외부 접속


class AddressRow(QWidget):
    def __init__(self, title: str, hint: str):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("ItemName")
        col.addWidget(t)
        col.addWidget(gray(hint))
        row.addLayout(col, 1)
        self.value = QLabel("-")
        self.value.setObjectName("Big")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.value)
        self.copy = QPushButton("복사")
        self.copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(self.value.text()),
                                           self.copy.setText("복사됨 ✓"),
                                           QTimer.singleShot(1200, lambda: self.copy.setText("복사"))))
        row.addWidget(self.copy)

    def set(self, text: str, enabled: bool = True):
        self.value.setText(text)
        self.copy.setEnabled(enabled)


class NetworkTab(ServerTab):
    _public_ip = None  # 프로그램 실행 중 한 번만 확인

    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box = QGroupBox("접속 주소")
        v = QVBoxLayout(box)
        self.addr_local = AddressRow("같은 PC", "이 컴퓨터에서 접속할 때")
        self.addr_lan = AddressRow("같은 와이파이 / 공유기", "같은 집에 있는 사람")
        self.addr_public = AddressRow("🌍 다른 집 (인터넷)", "멀리 있는 친구에게 이 주소를 알려주세요")
        for w in (self.addr_local, self.addr_lan, self.addr_public):
            v.addWidget(w)
        layout.addWidget(box)

        box = QGroupBox("다른 집에서 들어오게 하기")
        v = QVBoxLayout(box)
        v.addWidget(gray("다른 집 사람이 들어오려면 공유기의 포트를 열어야 합니다(포트포워딩). "
                         "대부분의 공유기는 아래 버튼으로 자동으로 열 수 있어요."))
        self.port_status = QLabel()
        self.port_status.setWordWrap(True)
        self.port_status.setObjectName("ItemName")
        v.addWidget(self.port_status)
        row = QHBoxLayout()
        self.btn_open = set_kind(QPushButton("🔓 자동으로 포트 열기 (UPnP)"), "primary")
        self.btn_open.clicked.connect(self._open_port)
        self.btn_close = QPushButton("포트 닫기")
        self.btn_close.clicked.connect(self._close_port)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_close)
        row.addStretch()
        v.addLayout(row)
        self.auto_upnp = QCheckBox("서버를 켤 때마다 자동으로 포트 열기")
        self.auto_upnp.toggled.connect(self._toggle_auto)
        v.addWidget(self.auto_upnp)
        if os.name == "nt":
            row = QHBoxLayout()
            fw = QPushButton("🛡 Windows 방화벽 허용")
            fw.clicked.connect(self._firewall)
            row.addWidget(fw)
            row.addWidget(gray("관리자 권한 창이 뜨면 '예'를 눌러 주세요. (Java 첫 실행 때 뜨는 방화벽 창에서 '허용'을 눌러도 됩니다)"), 1)
            v.addLayout(row)
        layout.addWidget(box)

        box = QGroupBox("자동으로 안 될 때 (직접 포트포워딩)")
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
        if NetworkTab._public_ip:
            self.addr_public.set(self._fmt(NetworkTab._public_ip))
        else:
            self.addr_public.set("확인 중...", False)
            run_async(lambda task: network.public_ip(), self._got_public_ip,
                      lambda msg: self.addr_public.set("확인 실패 (인터넷 연결 확인)", False))
        self.auto_upnp.blockSignals(True)
        self.auto_upnp.setChecked(self.meta.upnp)
        self.auto_upnp.blockSignals(False)
        if not self.port_status.text():
            self._status("⚪ 아직 포트를 열지 않았어요.")
        router = self._router_host or "192.168.0.1 또는 192.168.1.1"
        self.manual.setText(
            "<ol style='margin-left:-20px'>"
            f"<li>인터넷 주소창에 공유기 관리 페이지 <b>http://{router}</b> 를 입력해 들어갑니다. "
            "(ipTIME 192.168.0.1 · KT 172.30.1.254 · SK 192.168.45.1 · LG U+ 192.168.219.1 등)</li>"
            "<li><b>포트포워딩</b> (또는 'NAT', '가상 서버') 메뉴로 갑니다.</li>"
            f"<li>내부 IP <b>{lan}</b>, 외부/내부 포트 <b>{self.port}</b>, 프로토콜 <b>TCP</b> 로 규칙을 추가합니다.</li>"
            f"<li>친구에게 위의 <b>다른 집 주소</b>를 알려줍니다.</li></ol>"
            "<p>포트를 열 수 없는 환경(통신사 공유기 뒤, 기숙사·회사 와이파이, 모바일 핫스팟)이라면 "
            "<a href='https://playit.gg'>playit.gg</a> 같은 무료 터널 서비스를 쓰면 포트포워딩 없이 "
            "접속 주소를 받을 수 있어요.</p>"
            "<p>정품 계정이 없는 친구가 있다면 설정 탭에서 '정품 인증'을 끄세요.</p>"
        )

    def _got_public_ip(self, ip: str):
        NetworkTab._public_ip = ip
        if self.meta:
            self.addr_public.set(self._fmt(ip))

    def _status(self, text: str):
        self.port_status.setText(text)

    def _open_port(self):
        port, name = self.port, self.meta.name
        self._status("⏳ 공유기를 찾는 중... (몇 초 걸려요)")
        self.btn_open.setEnabled(False)

        def done(res):
            self.btn_open.setEnabled(True)
            self._router_host = res.router_host
            if res.cgnat:
                self._status(
                    f"🟡 포트는 열었지만, 공유기의 외부 IP({res.router_ip})가 사설 IP입니다. "
                    "통신사 공유기가 한 번 더 있거나 통신사 NAT 뒤라서 다른 집에서 접속이 안 될 수 있어요. "
                    "아래 안내(playit.gg)를 참고하세요."
                )
            else:
                self._status(f"🟢 포트 {res.port} 열림! 다른 집 친구가 위의 주소로 들어올 수 있어요. (내 PC: {res.lan_ip})")
            self.refresh()

        def fail(msg):
            self.btn_open.setEnabled(True)
            self._status("🔴 " + msg)

        run_async(lambda task: network.open_port(port, f"Minecraft {name}"[:60]), done, fail)

    def _close_port(self):
        port = self.port
        self._status("⏳ 포트 닫는 중...")
        run_async(lambda task: network.close_port(port),
                  lambda _: self._status("⚪ 포트를 닫았습니다."),
                  lambda msg: self._status("🔴 " + msg))

    def _toggle_auto(self, on: bool):
        if self.meta:
            self.meta.upnp = on
            self.meta.save()

    def _firewall(self):
        if not network.allow_firewall(self.port):
            QMessageBox.warning(self, "방화벽", "방화벽 규칙을 추가하지 못했습니다.")


# =============================================================== 업그레이드


class UpgradeTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        body = QWidget()
        layout = QVBoxLayout(body)

        box = QGroupBox("현재 버전")
        form = QFormLayout(box)
        self.cur_software = QLabel()
        self.cur_version = QLabel()
        self.cur_java = QLabel()
        self.cur_java.setWordWrap(True)
        form.addRow("구동기", self.cur_software)
        form.addRow("버전", self.cur_version)
        form.addRow("Java", self.cur_java)
        layout.addWidget(box)

        self.running_notice = warn_label("⚠ 서버를 끈 다음 업그레이드할 수 있습니다.")
        layout.addWidget(self.running_notice)

        box = QGroupBox("버전 업그레이드")
        form = QFormLayout(box)
        self.version = QComboBox()
        form.addRow("새 버전", self.version)
        self.version_status = gray("")
        form.addRow("", self.version_status)
        self.unstable = QCheckBox("스냅샷 / 테스트 버전도 표시")
        self.unstable.toggled.connect(self._reload)
        form.addRow("", self.unstable)
        self.allow_downgrade = QCheckBox("낮은 버전도 표시 (권장하지 않음: 맵이 깨질 수 있음)")
        self.allow_downgrade.toggled.connect(self._reload)
        form.addRow("", self.allow_downgrade)
        self.backup = QCheckBox("업그레이드 전에 서버 전체 백업 (강력 권장)")
        self.backup.setChecked(True)
        form.addRow("", self.backup)
        self.auto_java = QCheckBox("필요한 Java가 없으면 자동으로 설치")
        self.auto_java.setChecked(True)
        form.addRow("", self.auto_java)
        form.addRow(
            "",
            gray("플러그인/모드는 새 버전을 지원하는지 따로 확인해 주세요. "
                 "업그레이드 후 처음 켤 때 맵이 새 버전 형식으로 변환되어 시간이 걸릴 수 있습니다."),
        )
        self.btn_upgrade = set_kind(QPushButton("⬆ 업그레이드"), "primary")
        self.btn_upgrade.setMinimumHeight(38)
        self.btn_upgrade.clicked.connect(self._upgrade)
        form.addRow(self.btn_upgrade)
        layout.addWidget(box)

        box = QGroupBox("Java")
        v = QVBoxLayout(box)
        v.addWidget(gray("서버가 Java 오류로 켜지지 않으면 눌러 보세요. 버전에 맞는 Java를 다시 찾고, 없으면 설치합니다."))
        self.btn_java = QPushButton("☕ Java 다시 찾기 / 설치")
        self.btn_java.clicked.connect(self._fix_java)
        v.addWidget(self.btn_java)
        layout.addWidget(box)
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
        self.cur_software.setText(m.software_name)
        self.cur_version.setText(m.mc_version + (f"  (빌드 {m.build})" if m.build else ""))
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
            # 바닐라/Fabric 스냅샷(예: 25w14a)은 번호로 비교할 수 없어서 목록 순서(최신이 앞)를 쓴다
            if m.software in ("vanilla", "fabric"):
                order = provider.list_versions(unstable)  # 이미 받아 둔 목록 (캐시)
                if current in order:
                    return order.index(v) < order.index(current)
            return versions.version_key(v) > versions.version_key(current)

        self.loader.load(provider, unstable, filter_fn=newer)

    def _upgrade(self):
        new = self.version.currentText()
        if not new:
            return
        m = self.meta
        warn = ""
        if versions.version_key(new) < versions.version_key(m.mc_version):
            warn = "\n\n⚠ 낮은 버전으로 바꾸면 맵이 깨질 수 있습니다!"
        if QMessageBox.question(
            self, "업그레이드", f"{m.software_name} {m.mc_version} → {new} 로 바꿀까요?{warn}"
        ) != QMessageBox.Yes:
            return
        backup, auto_java = self.backup.isChecked(), self.auto_java.isChecked()
        self.run_task(
            "서버 업그레이드",
            lambda task: srv.upgrade_server(m, new, auto_java=auto_java, backup_first=backup, task=task),
        )
        self.on_changed()

    def _fix_java(self):
        m = self.meta
        auto = self.auto_java.isChecked()
        self.run_task("Java 확인", lambda task: srv.change_java(m, auto, task))
        self.on_changed()
