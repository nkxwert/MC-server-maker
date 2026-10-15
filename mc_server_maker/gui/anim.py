"""Small, quick transitions (fade-ins, expanding sections).

Kept short (about 0.2 s) so the app feels smooth, never slow. Turned off in
low-resource mode, where every animation just jumps to its end.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QVariantAnimation
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


def set_expanded(widget: QWidget, expanded: bool, ms: int = NORMAL) -> None:
    """Show or hide a section by sliding its height open or closed."""
    old = getattr(widget, "_expand_anim", None)
    if old is not None:
        old.stop()
    if not enabled():
        widget.setMaximumHeight(16777215)
        widget.setVisible(expanded)
        return
    full = widget.sizeHint().height()
    if expanded:
        widget.setMaximumHeight(0)
        widget.setVisible(True)
        full = widget.sizeHint().height()
    start, end = (0, full) if expanded else (widget.height(), 0)
    anim = QVariantAnimation(widget)
    anim.setDuration(ms)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.OutCubic if expanded else QEasingCurve.InCubic)
    anim.valueChanged.connect(lambda v: widget.setMaximumHeight(int(v)))

    def done():
        widget.setMaximumHeight(16777215)  # let it grow again with its content
        if not expanded:
            widget.setVisible(False)
        widget._expand_anim = None

    anim.finished.connect(done)
    widget._expand_anim = anim
    anim.start()


class FadeInDialog(QDialog):
    """A dialog that fades in when it opens."""

    def showEvent(self, event):
        super().showEvent(event)
        fade_window_in(self)
