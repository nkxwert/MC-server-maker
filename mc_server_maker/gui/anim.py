"""Small, quick transitions (cross-fades and fade-ins).

Kept short (about 0.2 s) so the app feels smooth, never slow. Turned off in
low-resource mode, where every animation just jumps to its end.
"""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QDialog, QGraphicsOpacityEffect, QLabel, QWidget

FAST = 160
NORMAL = 220
_enabled = {"on": True}


def set_enabled(on: bool) -> None:
    _enabled["on"] = on


def enabled() -> bool:
    return _enabled["on"]


def crossfade(area: QWidget, change=None, ms: int = NORMAL) -> None:
    """Blend from what `area` shows now into what it shows next.

    A picture of the current look is laid over the area and fades out while the new content is
    already in place underneath, so the old screen melts into the new one (no dark flash in
    between, which a plain fade-in from transparent gives). Call it right before the change, or
    pass the change as `change`."""
    if not enabled() or area is None or not area.isVisible() or area.width() <= 0 or area.height() <= 0:
        if change:
            change()
        return
    old = getattr(area, "_xfade_cover", None)
    if old is not None:  # a fade is still running: start the new one from the current look
        try:
            old.hide()
            old.deleteLater()
        except RuntimeError:
            pass
    picture = area.grab()
    # the cover sits next to the area (same parent), so pages raised inside the area stay under it
    host = area.parentWidget() or area
    cover = QLabel(host)
    cover.setAttribute(Qt.WA_TransparentForMouseEvents)
    cover.setPixmap(picture)
    cover.setGeometry(area.geometry() if host is not area else area.rect())
    cover.show()
    cover.raise_()
    area._xfade_cover = cover
    if change:
        change()
        cover.raise_()
    effect = QGraphicsOpacityEffect(cover)
    effect.setOpacity(1.0)
    cover.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", cover)
    fade.setDuration(ms)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.InOutQuad)

    def done():
        if getattr(area, "_xfade_cover", None) is cover:
            area._xfade_cover = None
        cover.hide()
        cover.deleteLater()

    fade.finished.connect(done)
    fade.start(QAbstractAnimation.DeleteWhenStopped)


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
    anim.start(QAbstractAnimation.DeleteWhenStopped)


class FadeInDialog(QDialog):
    """A dialog that fades in when it opens."""

    def showEvent(self, event):
        super().showEvent(event)
        fade_window_in(self)
