"""Find plugins/mods on Modrinth and install them with one click (Plugins/Mods tab)."""

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import modrinth, net
from mc_server_maker.gui import theme
from mc_server_maker.gui.theme import fit_to_screen, set_kind
from mc_server_maker.gui.widgets import HelpButton
from mc_server_maker.gui.workers import TaskDialog, run_async
from mc_server_maker.i18n import t

ICON = 48


def _alive(fn):
    """Skip a background result when its widget was already closed (e.g. language change)."""
    def call(*args):
        try:
            fn(*args)
        except RuntimeError:  # "Internal C++ object already deleted"
            pass
    return call


def short_number(n: int) -> str:
    for size, unit in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + unit
    return str(n)


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    return label


class ResultCard(QFrame):
    """One search result: icon, name, description, Install button."""

    def __init__(self, hit: modrinth.Hit, mods: bool, on_install: Callable[["ResultCard"], None]):
        super().__init__()
        self.setObjectName("Card")
        self.hit = hit
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedSize(ICON, ICON)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"background: {theme.C['surface3']}; border-radius: 8px;")
        row.addWidget(self.icon, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(hit.title)
        title.setObjectName("ItemName")
        col.addWidget(title)
        text = " ".join(hit.description.split())
        desc = QLabel(text if len(text) <= 120 else text[:117].rstrip() + "…")  # about two lines
        desc.setWordWrap(True)
        desc.setMinimumWidth(80)
        desc.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        if len(text) > 120:
            desc.setToolTip(text)
        col.addWidget(desc)
        bits = [f"⬇ {short_number(hit.downloads)}"]
        if hit.author:
            bits.append(t("by {author}", author=hit.author))
        if mods and hit.client_side == "required":
            bits.append("👥 " + t("Players need it too"))
        info = _muted(" · ".join(bits))
        if mods and hit.client_side == "required":
            info.setToolTip(t("Everyone who joins must install this mod in their own Minecraft as well."))
        col.addWidget(info)
        row.addLayout(col, 1)

        buttons = QVBoxLayout()
        self.btn = set_kind(QPushButton(t("Install")), "primary")
        self.btn.setMinimumWidth(96)
        self.btn.clicked.connect(lambda: on_install(self))
        buttons.addWidget(self.btn)
        page = set_kind(QPushButton(t("Details ↗")), "ghost")
        page.setMinimumWidth(96)
        page.setToolTip(hit.page_url)
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(hit.page_url)))
        buttons.addWidget(page)
        buttons.addStretch()
        row.addLayout(buttons)

    def set_installed(self, installed: bool):
        self.btn.setText("✓ " + t("Installed") if installed else t("Install"))
        set_kind(self.btn, "ghost" if installed else "primary")
        self.btn.setEnabled(not installed)

    def set_icon(self, pix: QPixmap):
        self.icon.setPixmap(pix)


class ModrinthBrowser(QWidget):
    """Search box + results. Only asks Modrinth once the page is opened."""

    def __init__(self, on_installed: Callable[[], None], is_running: Callable[[], bool]):
        super().__init__()
        self.on_installed = on_installed
        self.is_running = is_running
        self.meta = None
        self._req = 0  # newer searches win over late answers
        self._offset = 0
        self._total = 0
        self._loaded_for = None
        self._installed: Dict[str, object] = {}
        self._just_installed = set()  # installed here; kept even if Modrinth's lookup lags behind
        self._icons: Dict[str, QPixmap] = {}
        self.cards: List[ResultCard] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        row = QHBoxLayout()
        self.query = QLineEdit(placeholderText=t("Search Modrinth..."))
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(lambda: self._debounce.start())
        self.query.returnPressed.connect(self.reload)
        row.addWidget(self.query, 1)
        self.sort = QComboBox()
        for key, label in modrinth.SORTS:
            self.sort.addItem(t(label), key)
        self.sort.currentIndexChanged.connect(self.reload)
        row.addWidget(self.sort)
        v.addLayout(row)
        row = QHBoxLayout()
        self.filter_label = _muted("")
        row.addWidget(self.filter_label, 1)
        row.addWidget(HelpButton(t(
            "Results come from Modrinth and only show versions made for this server's software and "
            "Minecraft version. Required add-ons (like Fabric API) are installed automatically.")))
        v.addLayout(row)

        # a scroll area (not a list widget) so cards always fit the width and wrap their text
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.results = QVBoxLayout(body)
        self.results.setContentsMargins(0, 0, 6, 0)
        self.results.setSpacing(6)
        self.status = _muted("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.results.addWidget(self.status)
        self.more = QPushButton(t("Show more"))
        self.more.clicked.connect(lambda: self._load(reset=False))
        self.more.hide()
        self.results.addWidget(self.more, 0, Qt.AlignHCenter)
        self.results.addStretch()
        self.area.setWidget(body)
        v.addWidget(self.area, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self.reload)

    # ----------------------------------------------------------- loading

    def set_server(self, meta):
        self.meta = meta
        if meta and modrinth.supported(meta):
            what = t("plugins") if not modrinth.is_mods(meta) else t("mods")
            self.filter_label.setText(t("Showing {what} for {software} {v}", what=what,
                                        software=meta.software_name, v=meta.mc_version))
        if self.isVisible():
            self._ensure_loaded()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_loaded()

    def _ensure_loaded(self):
        if not self.meta or not modrinth.supported(self.meta):
            return
        key = (str(self.meta.folder), self.meta.software, self.meta.mc_version)
        if key != self._loaded_for:
            self._loaded_for = key
            self.reload()

    def reload(self):
        self._debounce.stop()
        self._load(reset=True)

    def _load(self, reset: bool):
        if not self.meta:
            return
        meta, query, sort = self.meta, self.query.text(), self.sort.currentData()
        if reset:
            self._offset = 0
            for card in self.cards:
                card.deleteLater()
            self.cards = []
            self.area.verticalScrollBar().setValue(0)
            self._just_installed.clear()
            self._refresh_installed()
        self._req += 1
        req = self._req
        offset = self._offset
        self.status.setText(t("Searching..."))
        self.status.show()
        self.more.hide()

        @_alive
        def done(result):
            if req != self._req:
                return
            hits, total = result
            self._total = total
            self._offset = offset + modrinth.PAGE_SIZE
            for hit in hits:
                self._add_card(hit)
            self.status.setText("" if self.cards else t("Nothing found. Try other words."))
            self.status.setVisible(not self.cards)
            self.more.setVisible(self._offset < self._total)
            self._load_icons([c.hit.icon_url for c in self.cards if c.hit.icon_url not in self._icons])

        @_alive
        def fail(msg):
            if req == self._req:
                self.status.setText(t("Couldn't load results. Check your internet connection.") + "\n" + msg)
                self.status.show()

        run_async(lambda task: modrinth.search(meta, query, sort, offset), done, fail)

    def _refresh_installed(self):
        meta = self.meta

        @_alive
        def done(found):
            if meta is self.meta:
                self._installed = dict(found)
                self._installed.update(dict.fromkeys(self._just_installed, True))
                for card in self.cards:
                    card.set_installed(card.hit.id in self._installed)

        run_async(lambda task: modrinth.installed(meta), done, lambda _m: None)

    def _add_card(self, hit: modrinth.Hit):
        card = ResultCard(hit, modrinth.is_mods(self.meta), self._install)
        card.set_installed(hit.id in self._installed)
        if hit.icon_url in self._icons:
            card.set_icon(self._icons[hit.icon_url])
        self.results.insertWidget(len(self.cards), card)  # above the status / "Show more"
        self.cards.append(card)

    def _load_icons(self, urls: List[str]):
        urls = [u for u in dict.fromkeys(urls) if u]
        if not urls:
            return

        def fetch(task):
            for url in urls:
                if task.cancelled:
                    return
                try:  # progress() carries (url, image bytes) back to the UI thread
                    task.progress(url, net.get_bytes(url))
                except Exception:  # noqa: BLE001 - an icon is not worth an error
                    continue

        @_alive
        def got(url, data):
            pix = QPixmap()
            if not pix.loadFromData(data):
                return
            ratio = max(1.0, self.devicePixelRatioF())
            px = round(ICON * ratio)
            pix = pix.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix.setDevicePixelRatio(ratio)
            self._icons[url] = pix
            for card in self.cards:
                if card.hit.icon_url == url:
                    card.set_icon(pix)

        run_async(fetch, on_progress=got)

    # ----------------------------------------------------------- install

    def _install(self, card: ResultCard):
        meta, hit = self.meta, card.hit
        dlg = TaskDialog(self, t("Install {name}", name=hit.title), lambda task: modrinth.install(meta, hit.id, task))
        dlg.exec()
        if not dlg.succeeded():
            return
        card.set_installed(True)
        self._installed[hit.id] = True
        self._just_installed.add(hit.id)
        self.on_installed()
        files = dlg.result_value or []
        if len(files) > 1 or self.is_running():
            text = t("Installed: {files}", files=", ".join(files))
            if self.is_running():
                text += "\n\n" + t("Restart the server to use it.")
            QMessageBox.information(self, t("Install {name}", name=hit.title), text)
        self._refresh_installed()  # dependencies may now be installed too


class UpdatesDialog(QDialog):
    """Lists available updates; 'Update all' installs them."""

    def __init__(self, parent, meta, updates: List[modrinth.Update], unknown: int):
        super().__init__(parent)
        self.meta, self.updates = meta, updates
        self.setWindowTitle(t("Updates"))
        fit_to_screen(self, 520, 380)
        v = QVBoxLayout(self)
        title = QLabel(t("{n} updates available", n=len(updates)))
        title.setObjectName("ItemName")
        v.addWidget(title)
        lst = QListWidget()
        for u in updates:
            lst.addItem(f"{u.title}   {u.old_version} → {u.new.get('version_number', '?')}")
        v.addWidget(lst, 1)
        if unknown:
            v.addWidget(_muted(t("{n} files aren't from Modrinth, so they weren't checked.", n=unknown)))
        buttons = QDialogButtonBox()
        set_kind(buttons.addButton(t("Update all"), QDialogButtonBox.AcceptRole), "primary")
        buttons.addButton(t("Close"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)


def check_updates(parent: QWidget, meta, on_done: Callable[[], None], running: bool,
                  button: Optional[QPushButton] = None):
    """Look for updates of installed plugins/mods, then offer to install them."""
    if button:
        button.setEnabled(False)
        button.setText(t("Checking..."))

    def restore():
        if button:
            button.setEnabled(True)
            button.setText(t("Check for updates"))

    def done(result):
        restore()
        updates, unknown = result
        if not updates:
            text = t("Everything is up to date.")
            if unknown:
                text += "\n" + t("{n} files aren't from Modrinth, so they weren't checked.", n=unknown)
            QMessageBox.information(parent, t("Updates"), text)
            return
        if not UpdatesDialog(parent, meta, updates, unknown).exec():
            return
        dlg = TaskDialog(parent, t("Updates"),
                         lambda task: [modrinth.apply_update(meta, u, task).name for u in updates])
        dlg.exec()
        on_done()
        if dlg.succeeded() and running:
            QMessageBox.information(parent, t("Updates"), t("Restart the server to use the new versions."))

    def fail(msg):
        restore()
        QMessageBox.warning(parent, t("Updates"), t("Couldn't check for updates: {err}", err=msg))

    run_async(lambda task: modrinth.check_updates(meta), done, fail)
