"""Run work in the background so the UI never freezes."""

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
from mc_server_maker.gui.theme import fit_to_screen
from mc_server_maker.i18n import t

_running = set()  # keep running threads alive (not garbage-collected)


class Worker(QObject):
    log = Signal(str)
    progress = Signal(object, object)  # byte counts can exceed 32-bit int (files > 2 GB)
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
        except Exception as e:  # noqa: BLE001 - show any error to the user
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.done.emit(result)
        finally:
            self.finished.emit()

    def cancel(self):
        self.task.cancelled = True


class _Bridge(QObject):
    """Deliver worker-thread signals as callbacks on the UI thread."""

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

    @Slot(object, object)
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
    """Run fn(task) on another thread. Callbacks run on the UI thread."""
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
    """Dialog that runs a job and shows its log and progress."""

    def __init__(self, parent, title: str, fn: Callable[[Task], object]):
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_to_screen(self, 640, 400)
        self.result_value = None
        self.error: Optional[str] = None

        layout = QVBoxLayout(self)
        self.status = QLabel(t("Working..."))
        self.status.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setObjectName("Console")
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
        self._finish("✅ " + t("Done."))
        self._log(t("Done."))

    def _fail(self, msg: str):
        self.error = msg
        self._finish("❌ " + t("Failed."))
        self._log("\n" + t("Error: {msg}", msg=msg))

    def _cancel_or_close(self):
        if self._finished:
            self.accept() if self.error is None else self.reject()
        else:
            self.status.setText(t("Cancelling..."))
            self.worker.cancel()

    def reject(self):
        if not self._finished:
            self._cancel_or_close()
            return
        super().reject()

    def succeeded(self) -> bool:
        return self._finished and self.error is None
