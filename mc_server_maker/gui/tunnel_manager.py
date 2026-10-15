"""Runs the playit.gg agent in the background (one per app, shared by all servers)."""

from collections import deque
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from mc_server_maker.core import tunnel
from mc_server_maker.core.settings import AppSettings
from mc_server_maker.gui.runner import ANSI_RE
from mc_server_maker.gui.workers import run_async
from mc_server_maker.i18n import t

OFF, INSTALLING, STARTING, WAITING_CLAIM, RUNNING, ERROR = "off", "installing", "starting", "claim", "running", "error"


class TunnelManager(QObject):
    changed = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.state = OFF
        self.error = ""
        self.claim_url: Optional[str] = None
        self.address = settings.tunnel_address
        self.log = deque(maxlen=300)
        self.proc: Optional[QProcess] = None
        self._variant = 0
        self._opened_claim = False
        self._buf = ""
        self._line = ""

    # ----------------------------------------------------------------- control

    def is_active(self) -> bool:
        return self.state in (INSTALLING, STARTING, WAITING_CLAIM, RUNNING)

    def start(self):
        if self.is_active():
            return
        self.error = ""
        self._variant = 0
        if not tunnel.is_installed():
            self._set(INSTALLING)
            run_async(lambda task: tunnel.install_agent(task), lambda _: self._launch(),
                      lambda msg: self._fail(msg), on_log=self._append)
        else:
            self._launch()

    def stop(self):
        proc, self.proc = self.proc, None  # detach first so _finished() ignores it
        if proc and proc.state() != QProcess.NotRunning:
            proc.kill()
            proc.waitForFinished(3000)
        self._set(OFF)

    def open_dashboard(self):
        QDesktopServices.openUrl(QUrl(tunnel.DASHBOARD))

    def set_address(self, address: str):
        self.address = address.strip()
        self.settings.tunnel_address = self.address
        self.settings.save()
        self.changed.emit()

    # ---------------------------------------------------------------- internals

    def _set(self, state: str):
        self.state = state
        self.changed.emit()

    def _fail(self, msg: str):
        self.error = msg
        self._set(ERROR)

    def _append(self, line: str):
        self.log.append(line)

    def _launch(self):
        variants = tunnel.command_variants()
        if self._variant >= len(variants):
            self._fail(t("The playit.gg agent didn't start. See its log below."))
            return
        cmd = variants[self._variant]
        tunnel.agent_dir().mkdir(parents=True, exist_ok=True)
        proc = QProcess(self)
        proc.setProgram(cmd[0])
        proc.setArguments(cmd[1:])
        proc.setWorkingDirectory(str(tunnel.agent_dir()))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._read(proc))
        proc.finished.connect(lambda code, _s: self._finished(proc, code))
        proc.errorOccurred.connect(lambda err: self._error(proc, err))
        self.proc = proc
        self._buf = ""
        self._line = ""
        self._set(STARTING)
        proc.start()
        # still alive after a few seconds -> this command line works
        QTimer.singleShot(4000, lambda: self._settled(proc))

    def _settled(self, proc: QProcess):
        if proc is self.proc and proc.state() != QProcess.NotRunning and self.state == STARTING:
            self._set(RUNNING if not self.claim_url or tunnel.is_claimed() else WAITING_CLAIM)

    def _error(self, proc: QProcess, err):
        # FailedToStart never emits finished(), so without this the tunnel would say "Starting..." forever
        if proc is self.proc and err == QProcess.FailedToStart:
            self.proc = None
            try:  # a broken (e.g. cut-off) agent download: fetch it again next time
                tunnel.agent_path().unlink(missing_ok=True)
            except OSError:
                pass
            self._fail(t("The playit.gg agent couldn't start: {err}", err=proc.errorString()))

    def _read(self, proc: QProcess):
        text = ANSI_RE.sub("", bytes(proc.readAllStandardOutput()).decode("utf-8", "replace"))
        self._buf = (self._buf + text)[-4000:]
        # only look at whole lines, so an address split across two reads isn't saved half
        lines = (self._line + text).replace("\r", "\n").split("\n")
        self._line = lines.pop()[-1000:]
        text = "\n".join(lines)
        for line in lines:
            if line.strip():
                self._append(line.rstrip())
        url = tunnel.find_claim_url(text)
        if url and url != self.claim_url:
            self.claim_url = url
            if not self._opened_claim:
                self._opened_claim = True
                QDesktopServices.openUrl(QUrl(url))
            self._set(WAITING_CLAIM)
        addr = tunnel.find_address(text)
        if addr and addr != self.address:
            self.set_address(addr)
            self._set(RUNNING)
        elif self.state == WAITING_CLAIM and tunnel.is_claimed():
            self._set(RUNNING)

    def _finished(self, proc: QProcess, code: int):
        if proc is not self.proc:
            return
        out = self._buf.lower()
        bad_args = any(k in out for k in ("unexpected argument", "unrecognized", "unknown argument", "usage:"))
        if bad_args and self._variant + 1 < len(tunnel.command_variants()):
            self._variant += 1  # older/newer CLI: try the next syntax
            self._launch()
            return
        self.proc = None
        if self.state != OFF:
            self._fail(t("The playit.gg agent stopped (code {code}).", code=code))
