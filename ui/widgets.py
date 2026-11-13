"""Small building blocks shared by every page, so the whole app looks the same:
white-bordered boxes, red/white buttons, field labels, status messages, the
settings gear icon, image slots and the live clock.
"""


from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QTransform
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton

from app_paths import IMAGES_DIR
from ui.theme import colors, current_theme, theme_events
from ui.signals import connect_alive



# A white-bordered box; its look comes from QFrame#box in styles.py.
def make_box():
    return QFrame(objectName="box")


# kind is "primary" (red) or "secondary" (white); styles.py colors them by objectName.
def make_button(text, kind="primary", width=None):
    btn = QPushButton(text, objectName=kind)
    btn.setCursor(Qt.PointingHandCursor)
    if width:
        btn.setFixedWidth(width)
    return btn


def field_label(text):
    return QLabel(text, objectName="fieldLabel")


# Turns a label into a red error or a green success message. polish() makes Qt
# re-read the stylesheet after the objectName changes.
def set_status(label, text, success=False):
    label.setObjectName("success" if success else "error")
    label.style().polish(label)
    label.setText(text)


# Draws the settings gear with QPainterPath (a body circle plus teeth, minus a hole)
# instead of using an image file. Drawn at 3x size so it stays sharp on high-DPI screens.
def gear_icon(color, size=24, teeth=8):
    scale = 3
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


# Gear button that turns red on hover and redraws itself when the theme changes.
class GearButton(QToolButton):
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


# Shows a PNG from assets/images, scaled to fit. In light mode it uses name_light.png
# if that file exists. A missing file shows an orange placeholder instead of crashing.
class ImageSlot(QLabel):
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
        scaled = self.pixmap_data.scaled(self.size(), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
        painter = QPainter(self)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           (self.height() - scaled.height()) // 2, scaled)


# Live date and time in the header, updated every second by a QTimer.
class ClockLabel(QLabel):
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
