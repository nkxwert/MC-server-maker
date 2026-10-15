"""오래 걸리는 작업(다운로드, 설치)에 진행 상황을 전달하기 위한 객체."""

from typing import Callable, Optional


class Cancelled(Exception):
    pass


class Task:
    def __init__(
        self,
        log: Optional[Callable[[str], None]] = None,
        progress: Optional[Callable[[int, int], None]] = None,
    ):
        self._log = log or print
        self._progress = progress or (lambda done, total: None)
        self.cancelled = False

    def log(self, msg: str) -> None:
        self._log(msg)

    def progress(self, done: int, total: int) -> None:
        self._progress(done, total)

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled("작업이 취소되었습니다.")
