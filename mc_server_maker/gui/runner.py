"""Run server processes, console I/O and online-player tracking."""

import codecs
import re
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional, Set

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from mc_server_maker.core import server as srv
from mc_server_maker.i18n import t

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Anchored to the log prefix ("[12:00:00 INFO]: Steve joined the game", Forge: "[..] [..] [..]: ...")
# so a chat line like "<Steve> Notch joined the game" can't fake a join or a leave.
_PREFIX = r"^(?:\[[^\]]*\]\s*)+:\s(?:\[[^\]]*\]\s)?"
JOIN_RE = re.compile(_PREFIX + r"([A-Za-z0-9_.]{1,16}) joined the game\s*$")
LEFT_RE = re.compile(_PREFIX + r"([A-Za-z0-9_.]{1,16}) left the game\s*$")
DONE_RE = re.compile(r'Done \([\d.,]+s\)! For help, type')
# "Steve[/203.0.113.5:51234] logged in with entity id ..." (IPv6: "[/[::1]:51234]")
LOGIN_RE = re.compile(_PREFIX + r"([A-Za-z0-9_.]{1,16})\[/\[?([0-9a-fA-F.:]+?)\]?:\d+\] logged in")
MAX_LINES = 5000

STOPPED, STARTING, RUNNING, STOPPING = "stopped", "starting", "running", "stopping"


class ServerRunner(QObject):
    line = Signal(str, str)  # (server folder, one line)
    state_changed = Signal(str, str)  # (server folder, state)
    players_changed = Signal(str)  # (server folder)
    process_started = Signal(str)  # (server folder) Java really runs (not just "asked to start")
    stop_slow = Signal(str)  # (server folder) still running a while after Stop

    def __init__(self, parent=None):
        super().__init__(parent)
        self.procs: Dict[str, QProcess] = {}
        self.logs: Dict[str, Deque[str]] = {}
        self.players: Dict[str, Set[str]] = {}
        self.status: Dict[str, str] = {}
        self.player_ips: Dict[str, Dict[str, str]] = {}
        self.started_at: Dict[str, float] = {}
        self._counted_until: Dict[str, float] = {}  # running time up to here is already in the total
        self._totals: Dict[str, float] = {}  # cached total uptime per server
        self._uptime_saver = QTimer(self)  # save the total now and then, so a crash loses little
        self._uptime_saver.timeout.connect(self._save_uptimes)
        self._uptime_saver.start(60_000)
        self._last_autosave: Dict[str, float] = {}
        self._autosave_timer = QTimer(self)  # checks every 30 s whether a server is due for a save
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(30_000)
        self.metas: Dict[str, srv.ServerMeta] = {}
        self.low_priority = True  # run servers below normal priority (low-resource mode)
        self._partial: Dict[str, str] = {}
        self._decoders: Dict[str, codecs.IncrementalDecoder] = {}  # keeps characters split across reads
        self.pending: Set[str] = set()  # servers whose Start waits for the internet check
        self.busy: Set[str] = set()  # servers whose files are being changed (world import, upgrade...)
        self._killed: Set[str] = set()
        self.ports: Dict[str, int] = {}  # the port each server was started with (settings may change meanwhile)

    # ------------------------------------------------------------------ state

    def state(self, key: str) -> str:
        return self.status.get(key, STOPPED)

    def is_running(self, key: str) -> bool:
        p = self.procs.get(key)
        return p is not None and p.state() != QProcess.NotRunning

    def has_started(self, key: str) -> bool:
        """The Java process is up (QProcess "Running", past "Starting")."""
        p = self.procs.get(key)
        return p is not None and p.state() == QProcess.Running

    def any_running(self) -> bool:
        return any(self.is_running(k) for k in self.procs)

    def log_lines(self, key: str):
        return list(self.logs.get(key, ()))

    def online_players(self, key: str):
        return sorted(self.players.get(key, set()), key=str.lower)

    def ips(self, key: str) -> Dict[str, str]:
        """Online player -> IP address (from the login log line)."""
        online = self.players.get(key, set())
        return {n: ip for n, ip in self.player_ips.get(key, {}).items() if n in online}

    def uptime(self, key: str) -> float:
        if not self.is_running(key) or key not in self.started_at:
            return 0.0
        return time.time() - self.started_at[key]

    def total_uptime(self, key: str) -> float:
        """All-time running seconds, including the current run."""
        if key not in self._totals:
            self._totals[key] = srv.total_uptime(Path(key))
        extra = time.time() - self._counted_until[key] if self.is_running(key) and key in self._counted_until else 0
        return self._totals[key] + extra

    def _count_uptime(self, key: str) -> None:
        since = self._counted_until.get(key)
        if since is None:
            return
        now = time.time()
        self._totals[key] = srv.add_uptime(Path(key), now - since)
        self._counted_until[key] = now

    def _save_uptimes(self) -> None:
        for key in list(self._counted_until):
            if self.is_running(key):
                self._count_uptime(key)

    def _autosave(self) -> None:
        now = time.time()
        for key in list(self.procs):
            if self.state(key) != RUNNING:
                continue
            try:  # read from disk: the setting may have changed since the server started
                minutes = srv.ServerMeta.load(Path(key)).autosave_minutes
            except (OSError, ValueError, TypeError):
                continue
            if minutes > 0 and now - self._last_autosave.get(key, now) >= minutes * 60 - 5:
                self._last_autosave[key] = now
                self.system_line(key, t("Auto-save"))
                self.procs[key].write(b"save-all\n")
            self._last_autosave.setdefault(key, now)

    def pid(self, key: str) -> Optional[int]:
        return int(self.procs[key].processId()) if self.is_running(key) else None

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
            self._last_autosave[key] = time.time()  # count the interval from when it's ready
            meta = self.metas.get(key)
            cmd = srv.spawn_chunk_command(meta) if meta and meta.memory_saver else None
            if cmd:
                self.system_line(key, t("Memory saver: unloading spawn chunks"))
                self.send(key, cmd)
        m = LOGIN_RE.search(text)
        if m:
            self.player_ips.setdefault(key, {})[m.group(1)] = m.group(2)
        m = JOIN_RE.search(text)
        if m:
            self.players.setdefault(key, set()).add(m.group(1))
            self.players_changed.emit(key)
        m = LEFT_RE.search(text)
        if m:
            self.players.setdefault(key, set()).discard(m.group(1))
            self.player_ips.get(key, {}).pop(m.group(1), None)
            self.players_changed.emit(key)

    def system_line(self, key: str, text: str):
        """A message from this app shown in the console."""
        self._emit_line(key, "»» " + text)

    def _read(self, key: str, proc: QProcess):
        decoder = self._decoders.setdefault(key, codecs.getincrementaldecoder("utf-8")(errors="replace"))
        data = decoder.decode(bytes(proc.readAllStandardOutput()))
        text = self._partial.get(key, "") + data.replace("\r\n", "\n")
        *lines, rest = text.split("\n")
        # a lone "\r" redraws the line (progress output): keep only the last version of it
        self._partial[key] = rest.rstrip("\r").rsplit("\r", 1)[-1][-8192:] + ("\r" if rest.endswith("\r") else "")
        for ln in lines:
            ln = ln.rstrip("\r").rsplit("\r", 1)[-1]
            self._emit_line(key, ANSI_RE.sub("", ln))  # on whole lines: escape codes can be split too

    # ---------------------------------------------------------------- control

    def start(self, meta: srv.ServerMeta) -> None:
        key = str(meta.folder)
        if self.is_running(key):
            return
        cmd = srv.launch_command(meta)  # ServerError if Java is missing
        srv.write_start_scripts(meta)
        old = self.procs.get(key)
        if old is not None:  # the finished process of the previous run
            old.deleteLater()
        proc = QProcess(self)
        proc.setProgram(cmd[0])
        proc.setArguments(cmd[1:])
        proc.setWorkingDirectory(key)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._read(key, proc))
        proc.finished.connect(lambda code, _status: self._finished(key, code))
        proc.errorOccurred.connect(lambda err: self._error(key, proc, err))
        proc.started.connect(lambda: self._started(key, proc))
        self.procs[key] = proc
        self.metas[key] = meta
        self.players[key] = set()
        self.player_ips[key] = {}
        self._partial[key] = ""
        self._decoders.pop(key, None)
        try:
            self.ports[key] = meta.properties().get_int("server-port", 25565)
        except OSError:
            self.ports.pop(key, None)
        self.started_at[key] = time.time()
        self._counted_until[key] = self.started_at[key]
        self.system_line(key, t("Starting: {cmd}", cmd=" ".join(cmd)))
        proc.start()
        # announce "starting" only once the process exists, so every tab sees it as running
        if proc.state() != QProcess.NotRunning:
            self._set_state(key, STARTING)

    def _started(self, key: str, proc: QProcess):
        self.process_started.emit(key)
        if not self.low_priority:
            return
        try:
            from mc_server_maker.core.stats import ProcessMonitor

            ProcessMonitor(int(proc.processId())).lower_priority()
        except Exception:  # noqa: BLE001 - priority is a nice-to-have
            pass

    def _finished(self, key: str, code: int):
        rest = self._partial.pop(key, "")
        if rest:
            self._emit_line(key, ANSI_RE.sub("", rest.rstrip("\r")))
        self._count_uptime(key)
        self._counted_until.pop(key, None)
        self._last_autosave.pop(key, None)
        if key in self._killed:
            self.system_line(key, t("Server force stopped."))
        elif code == 0 or self.state(key) == STOPPING:
            self.system_line(key, t("Server stopped (exit code {code}).", code=code))
        else:  # nobody asked it to stop: a crash or a failed start
            self.system_line(key, t(
                "The server stopped unexpectedly (exit code {code}). The red lines above usually say why; "
                "to ask for help, copy the log.", code=code))
        self._killed.discard(key)
        self.players[key] = set()
        self.players_changed.emit(key)
        self._set_state(key, STOPPED)

    def _error(self, key: str, proc: QProcess, err):
        if err == QProcess.FailedToStart:
            self._counted_until.pop(key, None)
            self.system_line(key, t("Could not start the server: {err}", err=proc.errorString()))
            # always tell the window, even when the state was already "stopped" (Windows fails
            # inside start()), so offline mode is switched back and the buttons are right
            self.status[key] = STOPPED
            self.state_changed.emit(key, STOPPED)

    def send(self, key: str, command: str) -> bool:
        if not self.is_running(key):
            return False
        self._emit_line(key, "> " + command)
        self.procs[key].write((command + "\n").encode("utf-8"))
        return True

    STOP_PATIENCE_MS = 60_000  # big worlds take a while to save; after this, offer a force stop

    def stop(self, key: str) -> None:
        """Ask the server to save and stop. Pressing it again re-sends "stop" (it is never ignored)."""
        if not self.is_running(key):
            return
        state = self.state(key)
        if state == STARTING:
            # Minecraft reads the console only once it's up: the command waits, it isn't lost
            self.system_line(key, t("The server is still starting. It stops as soon as it's ready."))
        elif state == STOPPING:
            self.system_line(key, t("Asking the server to stop again..."))
        else:
            self.system_line(key, t("Stopping: saving the world..."))
        self.send(key, "stop")
        self._set_state(key, STOPPING)
        proc = self.procs.get(key)
        QTimer.singleShot(self.STOP_PATIENCE_MS, lambda: self._check_stopped(key, proc))

    def _check_stopped(self, key: str, proc) -> None:
        if self.procs.get(key) is proc and self.is_running(key) and self.state(key) == STOPPING:
            self.stop_slow.emit(key)

    def kill(self, key: str) -> None:
        if self.is_running(key):
            self._killed.add(key)
            self.procs[key].kill()

    def clear_log(self, key: str) -> None:
        self.logs.pop(key, None)

    def forget(self, key: str) -> None:
        """Drop everything kept for a deleted server, so a new one in the same folder starts clean."""
        if self.is_running(key):
            return
        if self.procs.get(key) is not None:
            self.procs[key].deleteLater()
        for store in (self.logs, self.players, self.player_ips, self.started_at, self._counted_until,
                      self._totals, self.metas, self.ports, self._partial, self._decoders, self.status, self.procs):
            store.pop(key, None)

    def request_stop_all(self) -> None:
        """Ask every running server to save and stop, without waiting."""
        for key in list(self.procs):
            if self.is_running(key) and self.state(key) != STOPPING:
                self.system_line(key, t("Stopping: saving the world..."))
                self.send(key, "stop")
                self._set_state(key, STOPPING)

    def port(self, key: str, meta: srv.ServerMeta) -> int:
        """The port the server listens on: the one it started with while it runs."""
        if self.is_running(key) and key in self.ports:
            return self.ports[key]
        return meta.properties().get_int("server-port", 25565)

    def stop_all(self, timeout_ms: int = 30000) -> None:
        for key in list(self.procs):
            if self.is_running(key):
                self.send(key, "stop")
        # one shared deadline: several hung servers don't add up to minutes of waiting
        deadline = time.monotonic() + timeout_ms / 1000
        for proc in list(self.procs.values()):
            if proc.state() == QProcess.NotRunning:
                continue
            left = max(0, int((deadline - time.monotonic()) * 1000))
            if not proc.waitForFinished(left):
                proc.kill()
                proc.waitForFinished(3000)
