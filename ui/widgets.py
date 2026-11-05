"""
ui/widgets.py
Small reusable pieces shared by every screen.
"""

from pathlib import Path

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QTransform
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton

from ui.theme import colors, current_theme, theme_events
from ui.signals import connect_alive

# Put your PNG art in: assets/images/
IMAGES_DIR = Path(__file__).resolve().parent.parent / "assets" / "images"


def make_box():
    """A frame with a white border (styled as QFrame#box)."""
    return QFrame(objectName="box")


def make_button(text, kind="primary", width=None):
    """kind = 'primary' (red) or 'secondary' (white)."""
    btn = QPushButton(text, objectName=kind)
    btn.setCursor(Qt.PointingHandCursor)
    if width:
        btn.setFixedWidth(width)
    return btn


def field_label(text):
    return QLabel(text, objectName="fieldLabel")


def set_status(label, text, success=False):
    """Show a red error or green success message in a label."""
    label.setObjectName("success" if success else "error")
    label.style().polish(label)              # re-apply the color
    label.setText(text)


# ---------- Flat gear icon (drawn in code, no image file needed) ----------

def gear_icon(color, size=24, teeth=8):
    scale = 3                                 # draw big so it stays sharp
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)

    outer_r, body_r, hole_r = size * 0.48, size * 0.34, size * 0.14
    tooth_w = size * 0.18

    gear = QPainterPath()
    gear.addEllipse(QPointF(0, 0), body_r, body_r)
    for i in range(teeth):
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-tooth_w / 2, -outer_r, tooth_w, outer_r - body_r + 1),
                             1.2, 1.2)
        gear = gear.united(QTransform().rotate(360 / teeth * i).map(tooth))
    hole = QPainterPath()
    hole.addEllipse(QPointF(0, 0), hole_r, hole_r)
    gear = gear.subtracted(hole)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale, scale)
    painter.translate(size / 2, size / 2)
    painter.fillPath(gear, QColor(color))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


class GearButton(QToolButton):
    """Plain gear (white in dark mode, black in light mode) that turns red on hover."""

    def __init__(self, size=24):
        super().__init__(objectName="gear")
        self.icon_size = size
        self.make_icons()
        self.setIconSize(QSize(size, size))
        self.setCursor(Qt.PointingHandCursor)
        connect_alive(theme_events.changed, self, lambda _t: self.make_icons())

    def make_icons(self):
        self.normal_icon = gear_icon(colors()["fg"], self.icon_size)
        self.hover_icon = gear_icon(colors()["red"], self.icon_size)
        self.setIcon(self.normal_icon)

    def enterEvent(self, event):
        self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self.normal_icon)
        super().leaveEvent(event)


class ImageSlot(QLabel):
    """
    Shows assets/images/<filename> if it exists, scaled to fit.
    In light mode it uses <name>_light.png instead, if you made one
    (for example, a black version of white art).
    If the file is missing, shows an orange 'PNG PLACEHOLDER' box with the
    file name, so you know exactly what to name your art.
    """

    def __init__(self, filename, min_width=100, min_height=100):
        super().__init__()
        self.filename = filename
        self.setMinimumSize(min_width, min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.load()
        connect_alive(theme_events.changed, self, lambda _t: self.load())

    def load(self):
        path = IMAGES_DIR / self.filename
        if current_theme() == "light":
            light = path.with_name(f"{path.stem}_light{path.suffix}")
            if light.exists():
                path = light
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        self.pixmap_data = None if pixmap.isNull() else pixmap

        if self.pixmap_data is None:
            self.setObjectName("placeholder")
            self.setText(f"PNG PLACEHOLDER\n{self.filename}")
        else:
            self.setObjectName("")
            self.setText("")
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        if self.pixmap_data is None:
            return super().paintEvent(event)
        # Draw the image centered, keeping its proportions
        scaled = self.pixmap_data.scaled(self.size(), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
        painter = QPainter(self)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           (self.height() - scaled.height()) // 2, scaled)


class ClockLabel(QLabel):
    """The current date and time, updated every second: 'Thu, Nov 5, 2026  8:31:05 AM'."""

    def __init__(self):
        super().__init__(objectName="headerInfo")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def tick(self):
        now = datetime.now()
        date = f"{now.strftime('%a, %b')} {now.day}, {now.year}"
        time = now.strftime("%I:%M:%S %p").lstrip("0")
        self.setText(f"{date}   {time}")
