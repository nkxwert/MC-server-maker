"""서버 프로세스 실행 / 콘솔 입출력."""

import re
from typing import Dict

from PySide6.QtCore import QObject, QProcess, Signal

from mc_server_maker.core import server as srv

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MAX_LOG_CHARS = 300_000


class ServerRunner(QObject):
    output = Signal(str, str)  # (서버 폴더, 텍스트)
    state_changed = Signal(str, bool)  # (서버 폴더, 실행 중)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.procs: Dict[str, QProcess] = {}
        self.logs: Dict[str, str] = {}

    def is_running(self, key: str) -> bool:
        p = self.procs.get(key)
        return p is not None and p.state() != QProcess.NotRunning

    def any_running(self) -> bool:
        return any(self.is_running(k) for k in self.procs)

    def log_text(self, key: str) -> str:
        return self.logs.get(key, "")

    def _append(self, key: str, text: str):
        log = self.logs.get(key, "") + text
        if len(log) > MAX_LOG_CHARS:
            log = log[-MAX_LOG_CHARS:]
        self.logs[key] = log
        self.output.emit(key, text)

    def start(self, meta: srv.ServerMeta) -> None:
        key = str(meta.folder)
        if self.is_running(key):
            return
        cmd = srv.launch_command(meta)  # Java를 못 찾으면 ServerError
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
        self._append(key, f"\n▶ 서버 시작: {' '.join(cmd)}\n")
        proc.start()
        self.state_changed.emit(key, True)

    def _read(self, key: str, proc: QProcess):
        data = bytes(proc.readAllStandardOutput())
        self._append(key, ANSI_RE.sub("", data.decode("utf-8", errors="replace")).replace("\r\n", "\n"))

    def _finished(self, key: str, code: int):
        self._append(key, f"\n■ 서버가 종료되었습니다. (코드 {code})\n")
        self.state_changed.emit(key, False)

    def _error(self, key: str, proc: QProcess, err):
        if err == QProcess.FailedToStart:
            self._append(key, f"\n❌ 서버를 시작하지 못했습니다: {proc.errorString()}\n")
            self.state_changed.emit(key, False)

    def send(self, key: str, command: str) -> bool:
        if not self.is_running(key):
            return False
        self._append(key, f"> {command}\n")
        self.procs[key].write((command + "\n").encode("utf-8"))
        return True

    def stop(self, key: str) -> None:
        self.send(key, "stop")

    def kill(self, key: str) -> None:
        if self.is_running(key):
            self.procs[key].kill()

    def stop_all(self, timeout_ms: int = 30000) -> None:
        for key, proc in self.procs.items():
            if self.is_running(key):
                self.send(key, "stop")
        for key, proc in self.procs.items():
            if proc.state() != QProcess.NotRunning and not proc.waitForFinished(timeout_ms):
                proc.kill()
