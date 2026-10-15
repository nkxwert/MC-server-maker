"""새 서버 만들기 창."""

import random

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import server as srv
from mc_server_maker.core.providers import PROVIDERS
from mc_server_maker.gui.theme import set_kind
from mc_server_maker.gui.widgets import COLOR_HELP, amp_to_section
from mc_server_maker.gui.workers import run_async


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


def random_seed() -> str:
    return str(random.randint(-(2**63), 2**63 - 1))


class VersionLoader:
    """구동기를 바꾸면 버전 목록을 백그라운드에서 받아와 콤보박스를 채운다."""

    def __init__(self, combo: QComboBox, status: QLabel):
        self.combo = combo
        self.status = status
        self._request = 0

    def load(self, provider, include_unstable: bool, keep=None, filter_fn=None):
        self._request += 1
        req = self._request
        self.combo.clear()
        self.combo.setEnabled(False)
        self.status.setText("버전 목록 불러오는 중...")

        def done(result):
            if req != self._request:
                return
            items = [v for v in result if not filter_fn or filter_fn(v)]
            self.combo.addItems(items)
            self.combo.setEnabled(bool(items))
            if keep and keep in items:
                self.combo.setCurrentText(keep)
            self.status.setText(f"{len(items)}개 버전" if items else "선택할 수 있는 버전이 없습니다.")

        def fail(msg):
            if req == self._request:
                self.status.setText("⚠ 버전 목록을 불러오지 못했습니다: " + msg)

        run_async(lambda task: provider.list_versions(include_unstable), done, fail)


class CreateServerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("새 서버 만들기")
        self.resize(660, 800)
        self.options = None

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 0, 12, 0)
        layout.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # --- 1. 구동기 / 버전
        box = QGroupBox("1. 구동기와 버전")
        form = QFormLayout(box)
        self.name = QLineEdit("내 서버")
        form.addRow("서버 이름", self.name)
        cards = QGridLayout()
        cards.setSpacing(8)
        self.software = QButtonGroup(self)
        for i, p in enumerate(PROVIDERS):
            card = set_kind(QPushButton(f"{p.name}\n{p.short}"), "card")
            card.setCheckable(True)
            card.setMinimumHeight(54)
            card.setToolTip(p.description)
            self.software.addButton(card, i)
            cards.addWidget(card, i // 2, i % 2)
        self.software.button(0).setChecked(True)
        form.addRow("구동기 종류", cards)
        self.software_desc = hint_label("")
        form.addRow("", self.software_desc)
        self.version = QComboBox()
        form.addRow("버전", self.version)
        self.version_status = hint_label("")
        form.addRow("", self.version_status)
        self.unstable = QCheckBox("스냅샷 / 테스트 버전도 표시")
        form.addRow("", self.unstable)
        layout.addWidget(box)

        # --- 2. 실행 환경
        box = QGroupBox("2. 실행 환경")
        form = QFormLayout(box)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64, value=2)
        form.addRow("메모리(RAM)", self.ram)
        self.auto_java = QCheckBox("필요한 Java가 없으면 자동으로 설치 (권장)")
        self.auto_java.setChecked(True)
        form.addRow("Java", self.auto_java)
        hint = hint_label("버전에 맞는 Java(Eclipse Temurin)를 runtime 폴더에 받아서 이 프로그램만 사용합니다.")
        form.addRow("", hint)
        layout.addWidget(box)

        # --- 3. 맵
        box = QGroupBox("3. 맵(월드)")
        v = QVBoxLayout(box)
        self.world_group = QButtonGroup(self)
        self.rb_random = QRadioButton("무작위 맵 생성")
        self.rb_seed = QRadioButton("시드로 생성")
        self.rb_import = QRadioButton("기존 맵 불러오기 (폴더 또는 .zip)")
        self.rb_random.setChecked(True)
        for i, rb in enumerate((self.rb_random, self.rb_seed, self.rb_import)):
            self.world_group.addButton(rb, i)

        v.addWidget(self.rb_random)
        v.addWidget(self.rb_seed)
        seed_row = QHBoxLayout()
        self.seed = QLineEdit(placeholderText="시드 입력 (숫자 또는 글자)")
        self.seed_dice = QPushButton("🎲 무작위 시드")
        self.seed_dice.clicked.connect(lambda: self.seed.setText(random_seed()))
        seed_row.addSpacing(24)
        seed_row.addWidget(self.seed, 1)
        seed_row.addWidget(self.seed_dice)
        v.addLayout(seed_row)

        v.addWidget(self.rb_import)
        imp_row = QHBoxLayout()
        self.import_path = QLineEdit(placeholderText="맵 폴더 또는 zip 파일 경로")
        btn_dir = QPushButton("폴더...")
        btn_dir.clicked.connect(self._pick_world_dir)
        btn_zip = QPushButton("zip...")
        btn_zip.clicked.connect(self._pick_world_zip)
        imp_row.addSpacing(24)
        imp_row.addWidget(self.import_path, 1)
        imp_row.addWidget(btn_dir)
        imp_row.addWidget(btn_zip)
        v.addLayout(imp_row)
        self.import_widgets = (self.import_path, btn_dir, btn_zip)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("맵 종류"))
        self.level_type = QComboBox()
        for key, label in srv.LEVEL_TYPES:
            self.level_type.addItem(label, key)
        type_row.addWidget(self.level_type, 1)
        v.addLayout(type_row)
        layout.addWidget(box)

        # --- 4. 기본 설정
        box = QGroupBox("4. 기본 설정 (나중에 바꿀 수 있어요)")
        form = QFormLayout(box)
        self.motd = QLineEdit("&a마인크래프트 서버에 오신 걸 환영합니다!")
        form.addRow("서버 설명(MOTD)", self.motd)
        color_help = hint_label(COLOR_HELP)
        form.addRow("", color_help)
        self.gamemode = QComboBox()
        for key, label in srv.GAMEMODES:
            self.gamemode.addItem(label, key)
        form.addRow("게임 모드", self.gamemode)
        self.difficulty = QComboBox()
        for key, label in srv.DIFFICULTIES:
            self.difficulty.addItem(label, key)
        self.difficulty.setCurrentIndex(1)
        form.addRow("난이도", self.difficulty)
        self.max_players = QSpinBox(minimum=1, maximum=1000, value=20)
        form.addRow("최대 인원", self.max_players)
        self.port = QSpinBox(minimum=1, maximum=65535, value=25565)
        form.addRow("포트", self.port)
        self.online_mode = QCheckBox("정품 인증 (끄면 비정품 계정도 접속 가능)")
        self.online_mode.setChecked(True)
        form.addRow("", self.online_mode)
        self.pvp = QCheckBox("PvP 허용")
        self.pvp.setChecked(True)
        form.addRow("", self.pvp)
        layout.addWidget(box)

        # --- EULA
        self.eula = QCheckBox()
        eula_label = QLabel(
            '<a href="https://aka.ms/MinecraftEULA">마인크래프트 EULA(최종 사용자 라이선스)</a>에 동의합니다. (필수)'
        )
        eula_label.setOpenExternalLinks(True)
        eula_row = QHBoxLayout()
        eula_row.addWidget(self.eula)
        eula_row.addWidget(eula_label, 1)
        layout.addLayout(eula_row)
        layout.addStretch()

        buttons = QDialogButtonBox()
        self.create_btn = set_kind(buttons.addButton("서버 만들기", QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.loader = VersionLoader(self.version, self.version_status)
        self.software.idToggled.connect(lambda _id, on: on and self._software_changed())
        self.unstable.toggled.connect(self._reload_versions)
        self.world_group.idToggled.connect(self._world_mode_changed)
        self._software_changed()
        self._world_mode_changed()

    # ------------------------------------------------------------------

    def _provider(self):
        return PROVIDERS[self.software.checkedId()]

    def _software_changed(self):
        self.software_desc.setText(self._provider().description)
        self._reload_versions()

    def _reload_versions(self):
        self.loader.load(self._provider(), self.unstable.isChecked(), keep=self.version.currentText())

    def _world_mode_changed(self, *_):
        mode = self.world_group.checkedId()
        self.seed.setEnabled(mode == 1)
        self.seed_dice.setEnabled(mode == 1)
        for w in self.import_widgets:
            w.setEnabled(mode == 2)
        self.level_type.setEnabled(mode != 2)

    def _pick_world_dir(self):
        d = QFileDialog.getExistingDirectory(self, "맵 폴더 선택 (level.dat 이 있는 폴더)")
        if d:
            self.import_path.setText(d)

    def _pick_world_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "맵 zip 파일 선택", "", "Zip 파일 (*.zip)")
        if f:
            self.import_path.setText(f)

    def _accept(self):
        name = self.name.text().strip()
        version = self.version.currentText()
        mode = ("random", "seed", "import")[self.world_group.checkedId()]
        problems = []
        if not name:
            problems.append("서버 이름을 입력해 주세요.")
        if not version:
            problems.append("버전을 선택해 주세요. (목록이 안 나오면 인터넷 연결을 확인해 주세요)")
        if mode == "seed" and not self.seed.text().strip():
            problems.append("시드를 입력하거나 🎲 버튼을 눌러 주세요.")
        if mode == "import":
            try:
                srv.find_world_root(self.import_path.text().strip())
            except srv.ServerError as e:
                problems.append(str(e))
        if not self.eula.isChecked():
            problems.append("EULA에 동의해야 서버를 만들 수 있습니다.")
        if problems:
            QMessageBox.warning(self, "확인해 주세요", "\n".join(problems))
            return

        self.options = srv.CreateOptions(
            name=name,
            software=self._provider().id,
            mc_version=version,
            ram_mb=self.ram.value() * 1024,
            auto_java=self.auto_java.isChecked(),
            world=srv.WorldOptions(
                mode=mode,
                seed=self.seed.text(),
                import_path=self.import_path.text().strip(),
                level_type=self.level_type.currentData(),
            ),
            motd=amp_to_section(self.motd.text()),
            max_players=self.max_players.value(),
            gamemode=self.gamemode.currentData(),
            difficulty=self.difficulty.currentData(),
            online_mode=self.online_mode.isChecked(),
            pvp=self.pvp.isChecked(),
            port=self.port.value(),
            eula_accepted=True,
        )
        self.accept()
