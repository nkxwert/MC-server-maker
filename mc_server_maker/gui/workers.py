"""백그라운드 작업 실행 (UI가 멈추지 않도록)."""

import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from mc_server_maker.core.tasks import Cancelled, Task

_running = set()  # 실행 중인 스레드가 GC로 사라지지 않게 보관


class Worker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, fn: Callable[[Task], object]):
        super().__init__()
        self.fn = fn
        self.task = Task(log=self.log.emit, progress=self.progress.emit)

    @Slot()
    def run(self):
        try:
            result = self.fn(self.task)
        except Cancelled as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 - 어떤 오류든 사용자에게 보여준다
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.done.emit(result)
        finally:
            self.finished.emit()

    def cancel(self):
        self.task.cancelled = True


class _Bridge(QObject):
    """작업 스레드의 신호를 UI 스레드에서 콜백으로 전달한다."""

    def __init__(self, on_done, on_fail, on_log, on_progress):
        super().__init__()
        self.cb = (on_done, on_fail, on_log, on_progress)

    @Slot(object)
    def done(self, result):
        if self.cb[0]:
            self.cb[0](result)

    @Slot(str)
    def failed(self, msg):
        if self.cb[1]:
            self.cb[1](msg)

    @Slot(str)
    def log(self, msg):
        if self.cb[2]:
            self.cb[2](msg)

    @Slot(int, int)
    def progress(self, done, total):
        if self.cb[3]:
            self.cb[3](done, total)

    @Slot()
    def cleanup(self):
        self.entry[0].wait()
        _running.discard(self.entry)


def run_async(
    fn: Callable[[Task], object],
    on_done: Optional[Callable[[object], None]] = None,
    on_fail: Optional[Callable[[str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Worker:
    """fn(task)을 다른 스레드에서 실행한다. 콜백은 UI 스레드에서 불린다."""
    thread = QThread()
    worker = Worker(fn)
    worker.moveToThread(thread)
    bridge = _Bridge(on_done, on_fail, on_log, on_progress)
    worker.done.connect(bridge.done)
    worker.failed.connect(bridge.failed)
    worker.log.connect(bridge.log)
    worker.progress.connect(bridge.progress)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    entry = (thread, worker, bridge)
    bridge.entry = entry
    _running.add(entry)
    thread.finished.connect(bridge.cleanup)
    thread.start()
    return worker


def wait_all(timeout_ms: int = 3000) -> None:
    for thread, worker, _ in list(_running):
        worker.cancel()
        thread.quit()
        thread.wait(timeout_ms)


class TaskDialog(QDialog):
    """진행 로그 + 진행 막대를 보여주며 작업을 실행하는 창."""

    def __init__(self, parent, title: str, fn: Callable[[Task], object]):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 400)
        self.result_value = None
        self.error: Optional[str] = None

        layout = QVBoxLayout(self)
        self.status = QLabel("작업 중...")
        self.status.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(5000)
        layout.addWidget(self.log_view)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.buttons.rejected.connect(self._cancel_or_close)
        layout.addWidget(self.buttons)

        self._finished = False
        self.worker = run_async(fn, self._done, self._fail, self._log, self._progress)

    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def _progress(self, done: int, total: int):
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
        else:
            self.bar.setRange(0, 0)

    def _finish(self, text: str):
        self._finished = True
        self.status.setText(text)
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.buttons.clear()
        self.buttons.addButton(QDialogButtonBox.Close)

    def _done(self, result):
        self.result_value = result
        self._finish("✅ 완료되었습니다.")
        self._log("완료.")

    def _fail(self, msg: str):
        self.error = msg
        self._finish("❌ 실패했습니다.")
        self._log("\n오류: " + msg)

    def _cancel_or_close(self):
        if self._finished:
            self.accept() if self.error is None else self.reject()
        else:
            self.status.setText("취소하는 중...")
            self.worker.cancel()

    def reject(self):
        if not self._finished:
            self._cancel_or_close()
            return
        super().reject()

    def succeeded(self) -> bool:
        return self._finished and self.error is None
