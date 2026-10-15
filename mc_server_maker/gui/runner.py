"""Run server processes, console I/O and online-player tracking."""

import re
from collections import deque
from typing import Deque, Dict, Set

from PySide6.QtCore import QObject, QProcess, Signal

from mc_server_maker.core import server as srv
from mc_server_maker.i18n import t

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
JOIN_RE = re.compile(r":\s(?:\[[^\]]*\]\s)?([A-Za-z0-9_.]{1,16}) joined the game")
LEFT_RE = re.compile(r":\s(?:\[[^\]]*\]\s)?([A-Za-z0-9_.]{1,16}) left the game")
DONE_RE = re.compile(r'Done \([\d.,]+s\)! For help, type')
MAX_LINES = 5000

STOPPED, STARTING, RUNNING, STOPPING = "stopped", "starting", "running", "stopping"


class ServerRunner(QObject):
    line = Signal(str, str)  # (server folder, one line)
    state_changed = Signal(str, str)  # (server folder, state)
    players_changed = Signal(str)  # (server folder)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.procs: Dict[str, QProcess] = {}
        self.logs: Dict[str, Deque[str]] = {}
        self.players: Dict[str, Set[str]] = {}
        self.status: Dict[str, str] = {}
        self._partial: Dict[str, str] = {}

    # ------------------------------------------------------------------ state

    def state(self, key: str) -> str:
        return self.status.get(key, STOPPED)

    def is_running(self, key: str) -> bool:
        p = self.procs.get(key)
        return p is not None and p.state() != QProcess.NotRunning

    def any_running(self) -> bool:
        return any(self.is_running(k) for k in self.procs)

    def log_lines(self, key: str):
        return list(self.logs.get(key, ()))

    def online_players(self, key: str):
        return sorted(self.players.get(key, set()), key=str.lower)

    def _set_state(self, key: str, state: str):
        if self.status.get(key) != state:
            self.status[key] = state
            self.state_changed.emit(key, state)

    # ----------------------------------------------------------------- output

    def _emit_line(self, key: str, text: str):
        self.logs.setdefault(key, deque(maxlen=MAX_LINES)).append(text)
        self.line.emit(key, text)
        if self.state(key) == STARTING and DONE_RE.search(text):
            self._set_state(key, RUNNING)
        m = JOIN_RE.search(text)
        if m:
            self.players.setdefault(key, set()).add(m.group(1))
            self.players_changed.emit(key)
        m = LEFT_RE.search(text)
        if m:
            self.players.setdefault(key, set()).discard(m.group(1))
            self.players_changed.emit(key)

    def system_line(self, key: str, text: str):
        """A message from this app shown in the console."""
        self._emit_line(key, "»» " + text)

    def _read(self, key: str, proc: QProcess):
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        text = self._partial.get(key, "") + ANSI_RE.sub("", data).replace("\r\n", "\n").replace("\r", "")
        *lines, self._partial[key] = text.split("\n")
        for ln in lines:
            self._emit_line(key, ln)

    # ---------------------------------------------------------------- control

    def start(self, meta: srv.ServerMeta) -> None:
        key = str(meta.folder)
        if self.is_running(key):
            return
        cmd = srv.launch_command(meta)  # ServerError if Java is missing
        srv.write_start_scripts(meta)
        proc = QProcess(self)
        proc.setProgram(cmd[0])
        proc.setArguments(cmd[1:])
        proc.setWorkingDirectory(key)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._read(key, proc))
        proc.finished.connect(lambda code, _status: self._finished(key, code))
        proc.errorOccurred.connect(lambda err: self._error(key, proc, err))
        self.procs[key] = proc
        self.players[key] = set()
        self._partial[key] = ""
        self.system_line(key, t("Starting: {cmd}", cmd=" ".join(cmd)))
        self._set_state(key, STARTING)
        proc.start()

    def _finished(self, key: str, code: int):
        rest = self._partial.pop(key, "")
        if rest:
            self._emit_line(key, rest)
        self.system_line(key, t("Server stopped (exit code {code}).", code=code))
        self.players[key] = set()
        self.players_changed.emit(key)
        self._set_state(key, STOPPED)

    def _error(self, key: str, proc: QProcess, err):
        if err == QProcess.FailedToStart:
            self.system_line(key, t("Could not start the server: {err}", err=proc.errorString()))
            self._set_state(key, STOPPED)

    def send(self, key: str, command: str) -> bool:
        if not self.is_running(key):
            return False
        self._emit_line(key, "> " + command)
        self.procs[key].write((command + "\n").encode("utf-8"))
        return True

    def stop(self, key: str) -> None:
        if self.send(key, "stop"):
            self._set_state(key, STOPPING)

    def kill(self, key: str) -> None:
        if self.is_running(key):
            self.procs[key].kill()

    def clear_log(self, key: str) -> None:
        self.logs.pop(key, None)

    def stop_all(self, timeout_ms: int = 30000) -> None:
        for key in list(self.procs):
            if self.is_running(key):
                self.send(key, "stop")
        for proc in self.procs.values():
            if proc.state() != QProcess.NotRunning and not proc.waitForFinished(timeout_ms):
                proc.kill()
