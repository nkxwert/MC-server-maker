"""Small, quick transitions (fade-ins).

Kept short (about 0.2 s) so the app feels smooth, never slow. Turned off in
low-resource mode, where every animation just jumps to its end.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QDialog, QGraphicsOpacityEffect, QWidget

FAST = 160
NORMAL = 220
_enabled = {"on": True}


def set_enabled(on: bool) -> None:
    _enabled["on"] = on


def enabled() -> bool:
    return _enabled["on"]


def fade_in(widget: QWidget, ms: int = NORMAL) -> None:
    """Fade a widget in. The effect is removed afterwards so it costs nothing later."""
    if not enabled() or widget is None or not widget.isVisible():
        return
    old = getattr(widget, "_fade_anim", None)
    if old is not None:
        old.stop()
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def done():
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
        widget._fade_anim = None

    anim.finished.connect(done)
    widget._fade_anim = anim
    anim.start()


def fade_window_in(window: QWidget, ms: int = FAST) -> None:
    """Fade a top-level window (dialog) in when it opens."""
    if not enabled():
        return
    anim = QPropertyAnimation(window, b"windowOpacity", window)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    window._window_anim = anim
    anim.start()


class FadeInDialog(QDialog):
    """A dialog that fades in when it opens."""

    def showEvent(self, event):
        super().showEvent(event)
        fade_window_in(self)
