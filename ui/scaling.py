"""
ui/scaling.py
Makes a whole window grow with its size, so a maximized window on a big
screen isn't tiny.

How it works:
  1. After a window builds its screen, ScaleManager.capture() remembers every
     fixed size, margin and spacing at their normal (1x) values.
  2. When the window is resized, its scale = how much bigger it is than its
     design size (e.g. 1.6x), between 1.0 and 2.0.
  3. Every remembered size is multiplied by the scale, and the stylesheet is
     rebuilt with bigger fonts, paddings and borders.

The content sits inside a scroll area, so the window can always be made
smaller again (the scale then shrinks back).
"""

import math

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QLayout, QScrollArea, QVBoxLayout, QWidget,
)

from ui.styles import build_style
from ui.theme import theme_events
from ui.signals import connect_alive

MAX_SIZE = 16777215          # Qt's "no limit" value


class _ScaleEvents(QObject):
    """Lets widgets that draw their own content (chat bubbles, lists) redraw at the new size."""
    changed = Signal(float)


scale_events = _ScaleEvents()
_current = {"scale": 1.0}


def current_scale():
    return _current["scale"]
MIN_SCALE, MAX_SCALE, STEP = 1.0, 2.0, 0.1


def scale_for(width, height, base_width, base_height):
    """How much bigger than its design size the window is, rounded DOWN to 0.1
    (rounding down means the content always fits)."""
    raw = min(width / base_width, height / base_height)
    raw = max(MIN_SCALE, min(MAX_SCALE, raw))
    return round(math.floor(raw / STEP + 1e-9) * STEP, 2)


class ScaleManager:
    """Remembers base sizes inside one widget tree and re-applies them scaled."""

    def __init__(self):
        self.widgets = []     # (widget, minW, minH, maxW, maxH)
        self.icons = []       # (button, iconW, iconH)
        self.layouts = []     # (layout, (l, t, r, b), spacing)
        self.spacers = []     # (layout, spacer, w, h, hPolicy, vPolicy)

    def capture(self, root):
        """Record the 1x sizes of root and everything inside it."""
        for w in [root] + root.findChildren(QWidget):
            self.widgets.append((w, w.minimumWidth(), w.minimumHeight(),
                                 w.maximumWidth(), w.maximumHeight()))
            if isinstance(w, QAbstractButton) and not w.icon().isNull():
                size = w.iconSize()
                self.icons.append((w, size.width(), size.height()))
        for layout in root.findChildren(QLayout):
            m = layout.contentsMargins()
            self.layouts.append((layout, (m.left(), m.top(), m.right(), m.bottom()),
                                 layout.spacing()))
            for i in range(layout.count()):
                spacer = layout.itemAt(i).spacerItem()
                if spacer is not None:
                    hint = spacer.sizeHint()
                    policy = spacer.sizePolicy()
                    self.spacers.append((layout, spacer, hint.width(), hint.height(),
                                         policy.horizontalPolicy(), policy.verticalPolicy()))

    def apply(self, scale):
        def s(n):
            return round(n * scale)

        for w, min_w, min_h, max_w, max_h in self.widgets:
            try:
                w.setMinimumSize(s(min_w), s(min_h))
                w.setMaximumSize(max_w if max_w >= MAX_SIZE else s(max_w),
                                 max_h if max_h >= MAX_SIZE else s(max_h))
            except RuntimeError:          # widget was deleted
                pass
        for button, icon_w, icon_h in self.icons:
            try:
                button.setIconSize(QSize(s(icon_w), s(icon_h)))
            except RuntimeError:
                pass
        for layout, (l, t, r, b), spacing in self.layouts:
            try:
                layout.setContentsMargins(s(l), s(t), s(r), s(b))
                if spacing >= 0:
                    layout.setSpacing(s(spacing))
            except RuntimeError:
                pass
        for layout, spacer, w, h, h_policy, v_policy in self.spacers:
            try:
                spacer.changeSize(s(w), s(h), h_policy, v_policy)
                layout.invalidate()
            except RuntimeError:
                pass


class ScalingWindow(QWidget):
    """
    A window whose content grows with the window.
    Subclasses build their screen into `self.content`, then call
    `self.finish_scaling()` at the end of __init__.
    """

    BASE_SIZE = (1000, 660)          # the size the screen was designed at

    def __init__(self):
        super().__init__()
        self.scale = None
        self.scaler = ScaleManager()

        self.content = QWidget()
        # We size the content ourselves (fit_content) instead of letting the scroll
        # area do it: word-wrapped labels make Qt over-estimate the height needed.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

        self.rescale_timer = QTimer(self)        # wait until resizing pauses
        self.rescale_timer.setSingleShot(True)
        self.rescale_timer.setInterval(60)
        self.rescale_timer.timeout.connect(self.update_scale)
        connect_alive(theme_events.changed, self, lambda _t: self.setStyleSheet(build_style(self.scale or 1.0)))

    def finish_scaling(self):
        self.scaler.capture(self.content)
        self.update_scale(force=True)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_content()
        if self.scale is not None and self.scale != _current["scale"]:
            _current["scale"] = self.scale          # this window's size is the one in use
            scale_events.changed.emit(self.scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()
        self.rescale_timer.start()

    def fit_content(self):
        """Content = the window's size, or its minimum if the window is smaller
        (then the scroll bars appear)."""
        minimum = self.content.minimumSizeHint()
        for _ in range(2):            # twice: showing/hiding a scroll bar changes the room
            room = self.scroll.viewport().size()
            self.content.resize(max(room.width(), minimum.width()),
                                max(room.height(), minimum.height()))

    def update_scale(self, force=False):
        new_scale = scale_for(self.width(), self.height(), *self.BASE_SIZE)
        if new_scale == self.scale and not force:
            return
        self.scale = new_scale
        self.setStyleSheet(build_style(new_scale))    # fonts, paddings, borders
        self.scaler.apply(new_scale)                   # fixed sizes and spacing
        self.content.layout().activate()
        self.fit_content()
        _current["scale"] = new_scale
        scale_events.changed.emit(new_scale)
