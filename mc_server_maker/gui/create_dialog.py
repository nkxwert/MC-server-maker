"""New server dialog."""

import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from mc_server_maker.gui import theme
from mc_server_maker.gui.theme import fit_to_screen, form_layout, set_kind
from mc_server_maker.gui.widgets import amp_to_section, color_help, with_help, with_note
from mc_server_maker.gui.workers import run_async
from mc_server_maker.i18n import t
from mc_server_maker.gui.anim import FadeInDialog


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Hint")
    return label


def error_label() -> QLabel:
    """A red hint under a field, hidden until Create finds a problem there."""
    label = QLabel()
    label.setWordWrap(True)
    label.setObjectName("FieldError")
    label.hide()
    return label


def stacked(*items) -> QWidget:
    """Widgets (or layouts) on top of each other, as one form field."""
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    for item in items:
        if isinstance(item, QWidget):
            col.addWidget(item)
        else:
            col.addLayout(item)
    return box


def indented(widget: QWidget) -> QWidget:
    """Line up with the fields under a radio button."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(24, 0, 0, 0)
    row.addWidget(widget)
    return box


def set_error(widget: QWidget, on: bool) -> None:
    """Red border on a field (or the EULA strip) while it has a problem."""
    widget.setProperty("error", on)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


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
                self.status.setText(t("Could not load versions: {msg}", msg=msg))

        run_async(fetch, done, fail)


class CreateServerDialog(FadeInDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("New server"))
        fit_to_screen(self, 680, 680)
        self.options = None

        outer = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # always there: unfolding never shifts the content sideways (which made the fade double up)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 0, 12, 0)
        layout.setSpacing(10)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll)
        self._errors = []  # hint labels shown after a failed Create

        # --- what everyone needs: name, server type, version, memory
        box = QGroupBox(t("Server"))
        box.setProperty("first", True)
        form = form_layout(box)
        self.name = QLineEdit(t("My Server"))
        self.name_error = error_label()
        form.addRow(t("Name"), stacked(self.name, self.name_error))
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
        self.version_error = error_label()
        self.version_status = hint_label("")
        self.unstable = QCheckBox(t("Show versions still in development (advanced)"))
        form.addRow(t("Version"), stacked(
            self.version, self.version_error,
            hint_label(t("Match your friends' Minecraft version. Different versions can't join.")),
            self.version_status, self.unstable))
        self.ram = QSpinBox(suffix=" GB", minimum=1, maximum=64, value=2)
        form.addRow(t("Memory (RAM)"), with_note(self.ram, t(
            "1–3 players: 1–2 GB is usually enough. Modpacks need 4 GB or more.")))
        layout.addWidget(box)

        # everything else has good defaults: folded away until asked for
        self.btn_more = set_kind(QPushButton(), "ghost")
        self.btn_more.setCheckable(True)
        self.btn_more.setStyleSheet("QPushButton { padding-left: 0; text-align: left; }")
        self.btn_more.toggled.connect(self._show_more)
        layout.addWidget(self.btn_more, 0, Qt.AlignLeft)
        self.more_box = QWidget()
        more = QVBoxLayout(self.more_box)
        more.setContentsMargins(0, 0, 0, 0)
        more.setSpacing(10)
        layout.addWidget(self.more_box)

        # --- world
        box = QGroupBox(t("World"))
        box.setProperty("first", True)
        v = QVBoxLayout(box)
        self.world_group = QButtonGroup(self)
        self.rb_random = QRadioButton(t("Random world"))
        self.rb_seed = QRadioButton(t("From seed"))
        self.rb_import = QRadioButton(t("Import existing world (folder or .zip)"))
        self.rb_random.setChecked(True)
        for i, rb in enumerate((self.rb_random, self.rb_seed, self.rb_import)):
            self.world_group.addButton(rb, i)

        v.addWidget(self.rb_random)
        self.rb_seed.setToolTip(t(
            "The same seed always makes the same world. Use one from a friend or a seed website."))
        v.addWidget(self.rb_seed)
        seed_row = QHBoxLayout()
        self.seed = QLineEdit(placeholderText=t("Seed (numbers or text)"))
        self.seed_dice = QPushButton(t("Random"))
        self.seed_dice.clicked.connect(lambda: self.seed.setText(random_seed()))
        seed_row.addSpacing(24)
        seed_row.addWidget(self.seed, 1)
        seed_row.addWidget(self.seed_dice)
        v.addLayout(seed_row)
        self.seed_error = error_label()
        v.addWidget(indented(self.seed_error))

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
        self.import_error = error_label()
        v.addWidget(indented(self.import_error))
        self.import_widgets = (self.import_path, btn_dir, btn_zip)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(t("World type")))
        self.level_type = QComboBox()
        for key, label in srv.LEVEL_TYPES:
            self.level_type.addItem(t(label), key)
        type_row.addWidget(self.level_type, 1)
        v.addLayout(type_row)
        more.addWidget(box)

        # --- game rules and joining (all of it can be changed later in Settings)
        box = QGroupBox(t("Game (can be changed later)"))
        form = form_layout(box)
        self.motd = QLineEdit(t("&aWelcome to my Minecraft server!"))
        form.addRow(t("Description"), self.motd)
        # no (?) here: the colour codes show when hovering over the box
        self.motd.setToolTip(t("Shown under the server name in the multiplayer list (MOTD). Up to 2 lines.")
                             + "\n\n" + color_help())
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
        self.online_mode.setToolTip(t(
            "Players must sign in with a real Minecraft account. "
            "Turn it off to let non-premium accounts join (anyone can then use any name)."))
        form.addRow("", self.online_mode)
        self.bedrock = QCheckBox(t("Let Bedrock players join"))
        self.bedrock.setToolTip(t(
            "Installs Geyser + Floodgate so Bedrock Edition players can join with their Xbox account."))
        form.addRow(t("Bedrock"), self.bedrock)
        self.auto_java = QCheckBox(t("Install the right Java automatically"))
        self.auto_java.setChecked(True)
        form.addRow("Java", self.auto_java)
        more.addWidget(box)
        layout.addStretch()

        # --- EULA: outside the scroll area, so it's always in sight right above Create
        self.eula_strip = QFrame()
        self.eula_strip.setObjectName("EulaStrip")
        strip = QVBoxLayout(self.eula_strip)
        strip.setContentsMargins(12, 8, 12, 8)
        strip.setSpacing(4)
        self.eula = QCheckBox()
        eula_label = QLabel(
            t('I accept the <a href="https://aka.ms/MinecraftEULA">Minecraft EULA</a> (required).')
        )
        eula_label.setOpenExternalLinks(True)
        eula_row = QHBoxLayout()
        eula_row.addWidget(self.eula)
        eula_row.addWidget(eula_label, 1)
        strip.addLayout(eula_row)
        self.eula_error = error_label()
        strip.addWidget(self.eula_error)
        outer.addWidget(self.eula_strip)

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
        # a hint goes away as soon as its field is changed
        self.name.textChanged.connect(lambda: self._clear_error(self.name_error))
        self.version.currentIndexChanged.connect(lambda: self._clear_error(self.version_error))
        self.seed.textChanged.connect(lambda: self._clear_error(self.seed_error))
        self.import_path.textChanged.connect(lambda: self._clear_error(self.import_error))
        self.world_group.idToggled.connect(lambda *_: (self._clear_error(self.seed_error),
                                                       self._clear_error(self.import_error)))
        self.eula.toggled.connect(lambda: self._clear_error(self.eula_error))
        self._software_changed()
        self._world_mode_changed()
        self._show_more(False)
        theme.flatten_groups(self)

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

    def _show_more(self, on: bool, animate: bool = True):
        self.btn_more.setText(t("More world and game settings") + ("  ▴" if on else "  ▾"))
        self.more_box.setVisible(on)  # at once: a fade over content that moves down looked smeared

    def _field_of(self, label: QLabel) -> QWidget:
        return {self.name_error: self.name, self.version_error: self.version, self.seed_error: self.seed,
                self.import_error: self.import_path, self.eula_error: self.eula_strip}[label]

    def _clear_error(self, label: QLabel):
        if label in self._errors:
            self._errors.remove(label)
            label.hide()
            set_error(self._field_of(label), False)

    def _show_errors(self, problems):
        """Put each problem right under its field, then bring the first one into view."""
        for label in list(self._errors):
            self._clear_error(label)
        for label, text in problems:
            label.setText(text)
            label.show()
            set_error(self._field_of(label), True)
            self._errors.append(label)
        # a problem in the folded part: unfold it, so its hint isn't hidden
        if not self.btn_more.isChecked() and any(self.more_box.isAncestorOf(label) for label, _ in problems):
            self.btn_more.blockSignals(True)
            self.btn_more.setChecked(True)
            self.btn_more.blockSignals(False)
            self._show_more(True, animate=False)  # no fade: the view scrolls right away
        label = problems[0][0]
        if label is self.eula_error:  # always in sight below the scroll area
            self.eula.setFocus()
            return
        field = self._field_of(label)

        def reveal():  # once the layout has made room for the unfolded part and the hint
            self.scroll.ensureWidgetVisible(label, 0, 60)
            self.scroll.ensureWidgetVisible(field, 0, 40)
            field.setFocus()
        QTimer.singleShot(0, reveal)

    def _accept(self):
        name = self.name.text().strip()
        version = self.version.currentData()
        mode = ("random", "seed", "import")[self.world_group.checkedId()]
        problems = []  # (hint label under the field, what's wrong)
        if not name:
            problems.append((self.name_error, t("Enter a server name.")))
        if not version:
            problems.append((self.version_error,
                             t("Choose a version. (If the list is empty, check your internet connection.)")))
        if mode == "seed" and not self.seed.text().strip():
            problems.append((self.seed_error, t("Enter a seed or press Random.")))
        if mode == "import":
            try:
                srv.find_world_root(self.import_path.text().strip())
            except srv.ServerError as e:
                problems.append((self.import_error, str(e)))
        if not self.eula.isChecked():
            problems.append((self.eula_error, t("Agree to the EULA to create a server.")))
        if problems:
            self._show_errors(problems)
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
            pvp=True,  # changed later in Settings → Edit all server.properties
            port=self.port.value(),
            eula_accepted=True,
            bedrock=self.bedrock.isChecked(),
        )
        self.accept()
