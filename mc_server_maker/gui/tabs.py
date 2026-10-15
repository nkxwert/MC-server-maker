"""서버 관리 탭들: 설정 / 월드 / 플레이어 / 콘솔 / 업그레이드."""

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor
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

from mc_server_maker.core import players
from mc_server_maker.core import server as srv
from mc_server_maker.core import versions
from mc_server_maker.core.providers import get_provider
from mc_server_maker.gui.create_dialog import VersionLoader, random_seed
from mc_server_maker.gui.runner import ServerRunner
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
    label.setStyleSheet("color: gray;")
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

    def run_task(self, title: str, fn) -> bool:
        dlg = TaskDialog(self, title, fn)
        dlg.exec()
        return dlg.succeeded()


def _scroll(widget: QWidget) -> QScrollArea:
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
        help_label = gray(COLOR_HELP)
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", help_label)

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

        self.notice = gray("")
        layout.addWidget(self.notice)
        save = QPushButton("💾 저장")
        save.setMinimumHeight(36)
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

        self.running_notice = QLabel("⚠ 서버가 켜져 있는 동안에는 맵을 바꿀 수 없습니다. 먼저 서버를 꺼 주세요.")
        self.running_notice.setStyleSheet("color: #d08000; font-weight: bold;")
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
        self.btn_new = QPushButton("🌱 새 맵으로 교체")
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


class ConsoleTab(ServerTab):
    def __init__(self, runner, on_changed):
        super().__init__(runner, on_changed)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit(readOnly=True)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.view.setFont(font)
        self.view.setStyleSheet("background: #111; color: #ddd;")
        layout.addWidget(self.view)
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="명령어 입력 (예: say 안녕, time set day, op 닉네임)  — 앞에 / 없이")
        self.input.returnPressed.connect(self._send)
        send = QPushButton("보내기")
        send.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(send)
        layout.addLayout(row)
        runner.output.connect(self._on_output)

    def refresh(self):
        self.view.setPlainText(self.runner.log_text(self.key) if self.meta else "")
        self.view.moveCursor(QTextCursor.End)
        self.input.setEnabled(self.running)

    def _on_output(self, key: str, text: str):
        if key != self.key:
            return
        bar = self.view.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        cursor = QTextCursor(self.view.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        if at_bottom:
            bar.setValue(bar.maximum())

    def _send(self):
        cmd = self.input.text().strip().lstrip("/")
        if cmd and self.runner.send(self.key, cmd):
            self.input.clear()


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

        self.running_notice = QLabel("⚠ 서버를 끈 다음 업그레이드할 수 있습니다.")
        self.running_notice.setStyleSheet("color: #d08000; font-weight: bold;")
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
        self.btn_upgrade = QPushButton("⬆ 업그레이드")
        self.btn_upgrade.setMinimumHeight(36)
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
