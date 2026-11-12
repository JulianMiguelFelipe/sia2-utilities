"""Window scaling: everything grows when the window gets bigger.

Pages are designed at BASE_SIZE (1000 x 660). In a bigger window the scale is the
smaller of width/1000 and height/660, kept between 1.0 and 2.0 in steps of 0.1.
Fonts grow by rebuilding the stylesheet with build_style(scale). Fixed sizes,
margins and spacing grow through ScaleManager, from the values captured at 1.0.
"""

import math

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QLayout, QScrollArea, QVBoxLayout, QWidget,
)

from ui.styles import build_style
from ui.theme import theme_events
from ui.signals import connect_alive

# Qt's "no maximum" value. Widgets with no maximum size are left that way.
MAX_SIZE = 16777215


class _ScaleEvents(QObject):
    changed = Signal(float)


# Pages that work out their own sizes (like the fake data panel) listen to this.
scale_events = _ScaleEvents()
_current = {"scale": 1.0}


def current_scale():
    return _current["scale"]


# Scale limits. Whole steps of 0.1 stop the layout from jittering while you resize.
MIN_SCALE, MAX_SCALE, STEP = 1.0, 2.0, 0.1


def scale_for(width, height, base_width, base_height):
    raw = min(width / base_width, height / base_height)
    raw = max(MIN_SCALE, min(MAX_SCALE, raw))
    return round(math.floor(raw / STEP + 1e-9) * STEP, 2)


# Remembers every widget size, margin and spacing at scale 1.0, then re-applies them
# multiplied by the current scale. Always starting from the originals avoids rounding drift.
class ScaleManager:
    def __init__(self):
        self.widgets = []
        self.icons = []
        self.layouts = []
        self.spacers = []

    def capture(self, root):
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
            # The widget may have been deleted since it was captured; skip it.
            except RuntimeError:
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


# Base class for the login window and dashboard. The page sits in a scroll area, so on a
# screen smaller than the minimum size you can scroll instead of losing part of the page.
class ScalingWindow(QWidget):
    BASE_SIZE = (1000, 660)

    def __init__(self):
        super().__init__()
        self.scale = None
        self.scaler = ScaleManager()

        self.content = QWidget()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

        # Resizing fires many events; rescale once, 60 ms after the last one.
        self.rescale_timer = QTimer(self)
        self.rescale_timer.setSingleShot(True)
        self.rescale_timer.setInterval(60)
        self.rescale_timer.timeout.connect(self.update_scale)
        connect_alive(theme_events.changed, self,
                      lambda _t: self.setStyleSheet(build_style(self.scale or 1.0)))

    # Pages call this after building all their widgets, so every size is captured at 1.0.
    def finish_scaling(self):
        self.scaler.capture(self.content)
        self.update_scale(force=True)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_content()
        if self.scale is not None and self.scale != _current["scale"]:
            _current["scale"] = self.scale
            scale_events.changed.emit(self.scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()
        self.rescale_timer.start()

    # Make the page fill the window, but never shrink below its minimum size (the scroll bars
    # appear instead). Done twice because showing a scroll bar changes the free space.
    def fit_content(self):
        minimum = self.content.minimumSizeHint()
        for _ in range(2):
            room = self.scroll.viewport().size()
            self.content.resize(max(room.width(), minimum.width()),
                                max(room.height(), minimum.height()))

    def update_scale(self, force=False):
        new_scale = scale_for(self.width(), self.height(), *self.BASE_SIZE)
        if new_scale == self.scale and not force:
            return
        self.scale = new_scale
        self.setStyleSheet(build_style(new_scale))
        self.scaler.apply(new_scale)
        self.content.layout().activate()
        self.fit_content()
        _current["scale"] = new_scale
        scale_events.changed.emit(new_scale)
