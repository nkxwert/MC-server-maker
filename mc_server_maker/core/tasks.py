"""Progress reporting for long jobs (downloads, installs)."""

from typing import Callable, Optional

from mc_server_maker.i18n import t


def _safe_print(msg: str) -> None:
    """print() that never crashes on consoles that can't show the text (e.g. cp1252)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        import sys

        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


class Cancelled(Exception):
    pass


class Task:
    def __init__(
        self,
        log: Optional[Callable[[str], None]] = None,
        progress: Optional[Callable[[int, int], None]] = None,
    ):
        self._log = log or _safe_print
        self._progress = progress or (lambda done, total: None)
        self.cancelled = False

    def log(self, msg: str) -> None:
        self._log(msg)

    def progress(self, done: int, total: int) -> None:
        self._progress(done, total)

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled(t("Cancelled."))
