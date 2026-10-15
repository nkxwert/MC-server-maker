"""New server dialog."""

import random

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
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

from mc_server_maker.core import plugins
from mc_server_maker.core import server as srv
from mc_server_maker.core.providers import PROVIDERS
from mc_server_maker.gui.theme import fit_to_screen, form_layout, set_kind
from mc_server_maker.gui.widgets import amp_to_section, color_help, with_help
from mc_server_maker.gui.workers import run_async
from mc_server_maker.i18n import t
from mc_server_maker.gui.anim import FadeInDialog


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


def random_seed() -> str:
    return str(random.randint(-(2**63), 2**63 - 1))


class VersionLoader:
    """Fetch the version list in the background and fill a combo box."""

    def __init__(self, combo: QComboBox, status: QLabel):
        self.combo = combo
        self.status = status
        self._request = 0
        self.loaded = False  # True once a list arrived (even an empty one)

    def load(self, provider, include_unstable: bool, keep=None, filter_fn=None, make_filter=None):
        """make_filter(): optional, runs in the background (may fetch more) and returns filter_fn."""
        self._request += 1
        req = self._request
        self.loaded = False
        self.combo.clear()
        self.combo.setEnabled(False)
        self.status.setText(t("Loading versions..."))

        def fetch(task):
            return provider.list_versions(include_unstable), (make_filter() if make_filter else filter_fn)

        def done(result):
            if req != self._request:
                return
            result, keep_fn = result
            self.loaded = True
            items = [v for v in result if not keep_fn or keep_fn(v)]
            for i, v in enumerate(items):
                self.combo.addItem(v + (f"  ({t('latest')})" if i == 0 and not keep_fn else ""), v)
            self.combo.setEnabled(bool(items))
            if keep and keep in items:
                self.combo.setCurrentIndex(items.index(keep))
            self.status.setText(t("{n} versions", n=len(items)) if items else t("No versions available."))

        def fail(msg):
            if req == self._request:
                self.status.setText("⚠ " + t("Could not load versions: {msg}", msg=msg))

        run_async(fetch, done, fail)


class CreateServerDialog(FadeInDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("New server"))
        fit_to_screen(self, 680, 780)
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

        # --- 1. software / version
        box = QGroupBox(t("1. Software and version"))
        form = form_layout(box)
        self.name = QLineEdit(t("My Server"))
        form.addRow(t("Name"), self.name)
        cards = QGridLayout()
        cards.setSpacing(8)
        self.software = QButtonGroup(self)
        for i, p in enumerate(PROVIDERS):
            card = set_kind(QPushButton(f"{p.name}\n{t(p.short)}"), "card")
            card.setCheckable(True)
            card.setMinimumHeight(54)
            card.setToolTip(t(p.description))
            self.software.addButton(card, i)
            cards.addWidget(card, i // 3, i % 3)
        self.software.button(0).setChecked(True)
        form.addRow(with_help(t("Software"), "\n\n".join(f"{p.name}: {t(p.description)}" for p in PROVIDERS)), cards)
        self.version = QComboBox()
        form.addRow(t("Version"), self.version)
        row = QHBoxLayout()
        self.version_status = hint_label("")
        self.unstable = QCheckBox(t("Show snapshots"))
        row.addWidget(self.version_status, 1)
        row.addWidget(self.unstable)
        form.addRow("", row)
        layout.addWidget(box)

        # --- 2. runtime
        box = QGroupBox(t("2. Runtime"))
        form = form_layout(box)
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64, value=2)
        form.addRow(with_help(t("Memory (RAM)"), t(
            "1–3 players: 1–2 GB is usually enough. Modpacks need 4 GB or more.")), self.ram)
        self.auto_java = QCheckBox(t("Install the right Java automatically"))
        self.auto_java.setChecked(True)
        form.addRow("Java", self.auto_java)
        self.bedrock = QCheckBox(t("Let Bedrock players join"))
        form.addRow(t("Bedrock"), with_help(self.bedrock, t(
            "Installs Geyser + Floodgate so Bedrock Edition players can join with their Xbox account.")))
        layout.addWidget(box)

        # --- 3. world
        box = QGroupBox(t("3. World"))
        v = QVBoxLayout(box)
        self.world_group = QButtonGroup(self)
        self.rb_random = QRadioButton(t("Random world"))
        self.rb_seed = QRadioButton(t("From seed"))
        self.rb_import = QRadioButton(t("Import existing world (folder or .zip)"))
        self.rb_random.setChecked(True)
        for i, rb in enumerate((self.rb_random, self.rb_seed, self.rb_import)):
            self.world_group.addButton(rb, i)

        v.addWidget(self.rb_random)
        v.addWidget(with_help(self.rb_seed, t(
            "The same seed always makes the same world. Use one from a friend or a seed website.")))
        seed_row = QHBoxLayout()
        self.seed = QLineEdit(placeholderText=t("Seed (numbers or text)"))
        self.seed_dice = QPushButton("🎲 " + t("Random"))
        self.seed_dice.clicked.connect(lambda: self.seed.setText(random_seed()))
        seed_row.addSpacing(24)
        seed_row.addWidget(self.seed, 1)
        seed_row.addWidget(self.seed_dice)
        v.addLayout(seed_row)

        v.addWidget(self.rb_import)
        imp_row = QHBoxLayout()
        self.import_path = QLineEdit(placeholderText=t("World folder or zip file"))
        btn_dir = QPushButton(t("Folder..."))
        btn_dir.clicked.connect(self._pick_world_dir)
        btn_zip = QPushButton(t("Zip..."))
        btn_zip.clicked.connect(self._pick_world_zip)
        imp_row.addSpacing(24)
        imp_row.addWidget(self.import_path, 1)
        imp_row.addWidget(btn_dir)
        imp_row.addWidget(btn_zip)
        v.addLayout(imp_row)
        self.import_widgets = (self.import_path, btn_dir, btn_zip)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(t("World type")))
        self.level_type = QComboBox()
        for key, label in srv.LEVEL_TYPES:
            self.level_type.addItem(t(label), key)
        type_row.addWidget(self.level_type, 1)
        v.addLayout(type_row)
        layout.addWidget(box)

        # --- 4. basics
        box = QGroupBox(t("4. Basics (can be changed later)"))
        form = form_layout(box)
        self.motd = QLineEdit(t("&aWelcome to my Minecraft server!"))
        form.addRow(with_help(t("Description"), t(
            "Shown under the server name in the multiplayer list (MOTD). Up to 2 lines.") + "\n\n" + color_help()),
            self.motd)
        self.gamemode = QComboBox()
        for key, label in srv.GAMEMODES:
            self.gamemode.addItem(t(label), key)
        form.addRow(t("Game mode"), self.gamemode)
        self.difficulty = QComboBox()
        for key, label in srv.DIFFICULTIES:
            self.difficulty.addItem(t(label), key)
        self.difficulty.setCurrentIndex(1)
        form.addRow(t("Difficulty"), self.difficulty)
        self.max_players = QSpinBox(minimum=1, maximum=1000, value=20)
        form.addRow(t("Max players"), self.max_players)
        self.port = QSpinBox(minimum=1, maximum=65535, value=25565)
        form.addRow(t("Port"), self.port)
        self.online_mode = QCheckBox(t("Online mode"))
        self.online_mode.setChecked(True)
        form.addRow("", with_help(self.online_mode, t(
            "Players must sign in with a real Minecraft account. "
            "Turn it off to let non-premium accounts join (anyone can then use any name).")))
        self.pvp = QCheckBox("PvP")
        self.pvp.setChecked(True)
        form.addRow("", self.pvp)
        layout.addWidget(box)

        # --- EULA
        self.eula = QCheckBox()
        eula_label = QLabel(
            t('I accept the <a href="https://aka.ms/MinecraftEULA">Minecraft EULA</a> (required).')
        )
        eula_label.setOpenExternalLinks(True)
        eula_row = QHBoxLayout()
        eula_row.addWidget(self.eula)
        eula_row.addWidget(eula_label, 1)
        layout.addLayout(eula_row)
        layout.addStretch()

        buttons = QDialogButtonBox()
        self.create_btn = set_kind(buttons.addButton(t("Create server"), QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton(t("Cancel"), QDialogButtonBox.RejectRole)
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
        ok = self._provider().id in plugins.PLUGIN_SOFTWARE
        self.bedrock.setEnabled(ok)
        if not ok:
            self.bedrock.setChecked(False)
        self._reload_versions()

    def _reload_versions(self):
        self.loader.load(self._provider(), self.unstable.isChecked(), keep=self.version.currentData())

    def _world_mode_changed(self, *_):
        mode = self.world_group.checkedId()
        self.seed.setEnabled(mode == 1)
        self.seed_dice.setEnabled(mode == 1)
        for w in self.import_widgets:
            w.setEnabled(mode == 2)
        self.level_type.setEnabled(mode != 2)

    def _pick_world_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("Choose a world folder (with level.dat)"))
        if d:
            self.import_path.setText(d)

    def _pick_world_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, t("Choose a world zip"), "", "Zip (*.zip)")
        if f:
            self.import_path.setText(f)

    def _accept(self):
        name = self.name.text().strip()
        version = self.version.currentData()
        mode = ("random", "seed", "import")[self.world_group.checkedId()]
        problems = []
        if not name:
            problems.append(t("Enter a server name."))
        if not version:
            problems.append(t("Choose a version. (If the list is empty, check your internet connection.)"))
        if mode == "seed" and not self.seed.text().strip():
            problems.append(t("Enter a seed or press 🎲."))
        if mode == "import":
            try:
                srv.find_world_root(self.import_path.text().strip())
            except srv.ServerError as e:
                problems.append(str(e))
        if not self.eula.isChecked():
            problems.append(t("You must accept the Minecraft EULA to create a server."))
        if problems:
            QMessageBox.warning(self, t("Check these"), "\n".join(problems))
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
            bedrock=self.bedrock.isChecked(),
        )
        self.accept()
