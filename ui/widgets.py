"""
ui/widgets.py
Small reusable pieces shared by every screen.
"""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QTransform
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton

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
    label.style().polish(label)
    label.setText(text)


# ---------- Flat gear icon (drawn in code, no image file needed) ----------

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


class GearButton(QToolButton):
    """Plain white gear that turns red on hover."""

    def __init__(self, size=24):
        super().__init__(objectName="gear")
        self.normal_icon = gear_icon("#ffffff", size)
        self.hover_icon = gear_icon("#ff3333", size)
        self.setIcon(self.normal_icon)
        self.setIconSize(QSize(size, size))
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self.normal_icon)
        super().leaveEvent(event)


class ImageSlot(QLabel):
    """
    Shows assets/images/<filename> if it exists, scaled to fit.
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

        path = IMAGES_DIR / filename
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        self.pixmap_data = None if pixmap.isNull() else pixmap

        if self.pixmap_data is None:
            self.setObjectName("placeholder")
            self.setText(f"PNG PLACEHOLDER\n{filename}")

    def paintEvent(self, event):
        if self.pixmap_data is None:
            return super().paintEvent(event)
        scaled = self.pixmap_data.scaled(self.size(), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
        painter = QPainter(self)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           (self.height() - scaled.height()) // 2, scaled)
