"""Home tab: the one page a beginner needs — is it on, start/stop, and how to join."""

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mc_server_maker.core import network
from mc_server_maker.gui import anim, theme
from mc_server_maker.gui.runner import RUNNING, STARTING, STOPPED, STOPPING
from mc_server_maker.gui.tabs import AddressRow, ServerTab, _scroll, format_total, format_uptime, hint
from mc_server_maker.gui.theme import set_kind
from mc_server_maker.gui.widgets import HelpButton
from mc_server_maker.i18n import t


def _card(title: str = "") -> tuple:
    frame = QFrame()
    frame.setObjectName("Card")
    v = QVBoxLayout(frame)
    v.setContentsMargins(18, 16, 18, 16)
    v.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("CardTitle")
        v.addWidget(label)
    return frame, v


class Tile(QFrame):
    """A small number with a label under it."""

    def __init__(self, label: str):
        super().__init__()
        self.setObjectName("Card")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)
        self.value = QLabel("-")
        self.value.setObjectName("Big")
        self.value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # may cut, never widens the page
        v.addWidget(self.value)
        self.label = hint(label)
        v.addWidget(self.label)


class HomeTab(ServerTab):
    def __init__(self, runner, on_changed, on_start: Callable[[], None], on_stop: Callable[[], None],
                 show_invite: Callable[[], None]):
        super().__init__(runner, on_changed)
        self.on_start, self.on_stop = on_start, on_stop
        self.tunnel = None
        self._last_state = None
        body = QWidget()
        layout = QVBoxLayout(body)

        # ---- status + the big button
        self.status_card, v = _card()
        row = QHBoxLayout()
        row.setSpacing(16)
        self.dot = QLabel("●")
        self.dot.setObjectName("StatusDot")
        row.addWidget(self.dot, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.status_title = QLabel()
        self.status_title.setObjectName("Big")
        col.addWidget(self.status_title)
        self.status_sub = QLabel()
        self.status_sub.setObjectName("Muted")
        self.status_sub.setWordWrap(True)
        col.addWidget(self.status_sub)
        row.addLayout(col, 1)
        self.power = set_kind(QPushButton(), "primary")
        self.power.setMinimumSize(150, 52)
        self.power.setObjectName("PowerButton")
        self.power.clicked.connect(self._power)
        row.addWidget(self.power, 0, Qt.AlignVCenter)
        v.addLayout(row)
        layout.addWidget(self.status_card)

        # ---- numbers
        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.t_players = Tile(t("Playing now"))
        self.t_uptime = Tile(t("Uptime"))
        self.t_version = Tile(t("Version"))
        for i, tile in enumerate((self.t_players, self.t_uptime, self.t_version)):
            tiles.addWidget(tile, 0, i)
        layout.addLayout(tiles)

        # ---- how to join
        card, v = _card(t("How to join"))
        steps = QHBoxLayout()
        steps.addWidget(hint(t("In Minecraft: Multiplayer → Add Server → paste an address below.")), 1)
        steps.addWidget(HelpButton(t(
            "Use the same Minecraft version as the server. 'This PC' works only on this computer, "
            "'Same Wi-Fi' for people in your home, and 'Friends in other homes' over the internet.")))
        v.addLayout(steps)
        self.addr_local = AddressRow(t("This PC"), t("Playing on this computer"))
        self.addr_lan = AddressRow(t("Same Wi-Fi"), t("People in the same home"))
        v.addWidget(self.addr_local)
        v.addWidget(self.addr_lan)
        self.addr_friends = AddressRow(t("Friends in other homes"), t("Over the internet"))
        v.addWidget(self.addr_friends)
        self.invite_row = QWidget()
        r = QHBoxLayout(self.invite_row)
        r.setContentsMargins(0, 2, 0, 2)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel(t("Friends in other homes"))
        name.setObjectName("ItemName")
        col.addWidget(name)
        col.addWidget(hint(t("Needs a one-time setup (about 2 minutes, free).")))
        r.addLayout(col, 1)
        invite = set_kind(QPushButton(t("Set up →")), "primary")
        invite.clicked.connect(show_invite)
        r.addWidget(invite)
        v.addWidget(self.invite_row)
        layout.addWidget(card)

        # ---- first time
        self.first_card, v = _card(t("First time?"))
        steps_text = QLabel(t(
            "1. Press Start and wait until it says the server is on (the first start takes a minute).\n"
            "2. Open Minecraft → Multiplayer → Add Server, and enter the address 'This PC'.\n"
            "3. To play with friends, press 'Set up' above."))
        steps_text.setWordWrap(True)
        v.addWidget(steps_text)
        layout.addWidget(self.first_card)
        layout.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        runner.players_changed.connect(lambda key: key == self.key and self._tick())

    def set_tunnel(self, manager):
        self.tunnel = manager
        manager.changed.connect(self._refresh_addresses)

    # ----------------------------------------------------------- view

    def refresh(self):
        if not self.meta:
            return
        self._last_state = None
        self._refresh_addresses()
        self.on_state()

    def on_state(self):
        if not self.meta:
            return
        state = self.runner.state(self.key)
        players = len(self.runner.online_players(self.key))
        texts = {
            STOPPED: (t("Server is off"), t("Press Start. The first start takes a minute while the world is made."),
                      "▶  " + t("Start server"), "muted"),
            STARTING: (t("Starting..."), t("Getting the world ready. This can take a minute."),
                       t("Starting..."), "warn"),
            RUNNING: (t("Server is on"), t("Friends can join now with an address below."),
                      "■  " + t("Stop server"), "accent"),
            STOPPING: (t("Stopping..."), t("Saving the world. Don't close the app yet."), t("Stopping..."), "warn"),
        }
        title, sub, button, color = texts[state]
        self.status_title.setText(title)
        self.status_sub.setText(sub)
        self.dot.setStyleSheet(f"color: {theme.C[color]}; font-size: 26pt;")
        self.power.setText(button)
        set_kind(self.power, "ghost" if state == RUNNING else "primary")
        self.power.setEnabled(state in (STOPPED, RUNNING))
        self.first_card.setVisible(not self._world_exists() and state == STOPPED)
        self.t_version.value.setText(f"{self.meta.software_name} {self.meta.mc_version}")
        self.t_players.value.setText(str(players) if state == RUNNING else "-")
        if state != self._last_state and self._last_state is not None:
            anim.fade_in(self.status_card, anim.FAST)
        self._last_state = state
        self._tick()

    def _world_exists(self) -> bool:
        level = self.meta.properties().get("level-name") or "world"
        return (self.meta.folder / level / "level.dat").exists()

    def _tick(self):
        if not self.meta:
            return
        up = self.runner.uptime(self.key)
        total = self.runner.total_uptime(self.key)
        # running: this run's time; off: all the time so far
        self.t_uptime.value.setText(format_uptime(up) if up else (format_total(total) if total >= 1 else "-"))
        self.t_uptime.label.setText(t("Uptime") if up else t("Total uptime"))
        self.t_uptime.value.setToolTip(t("Total: {time}", time=format_total(total)) if up and total >= 1 else "")
        if self.runner.is_running(self.key):
            self.t_players.value.setText(str(len(self.runner.online_players(self.key))))

    def _refresh_addresses(self):
        if not self.meta:
            return
        port = self.meta.properties().get_int("server-port", 25565)

        def fmt(host):
            return host if port == 25565 else f"{host}:{port}"

        self.addr_local.set(fmt("localhost"))
        self.addr_lan.set(fmt(network.lan_ip()))
        address = self.tunnel.address if self.tunnel else ""
        self.addr_friends.setVisible(bool(address))
        self.invite_row.setVisible(not address)
        if address:
            self.addr_friends.set(address)

    def _power(self):
        if self.runner.is_running(self.key):
            self.on_stop()
        else:
            self.on_start()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start(1000)
        self._tick()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
