"""Feature 2: draws the fake data as an ID card, the fun way to view a generated person.

Everything is drawn with QPainter on a fixed 856 x 540 grid (the shape of a real
85.6 x 54 mm ID) and then scaled to fit. Because of that, one paint_card()
function draws the card on screen, into the PDF and into the PNG, and all three
always look the same. Fields that are off are simply left out and the rest
move up to fill the space.
"""

import random

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter, QPainterPath,
    QPdfWriter, QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from services.fake_data_service import (
    birthdate_text, card_name, emergency_text, format_id, format_mobile, height_weight_text,
)

# Fixed card colors (not the app theme), so the card looks like a printed card in both modes.
CARD_W, CARD_H = 856, 540
BAND_H = 66
PAPER, INK, MUTED, LINE = QColor("#ffffff"), QColor("#111111"), QColor("#6b6b6b"), QColor("#d4d4d4")
RED, PHOTO_BG = QColor("#e02424"), QColor("#e9e9e9")
TITLE = "JD UTILS · IDENTIFICATION CARD"


def _font(size, bold=True, script=False):
    font = QFont()
    font.setFamilies(["Segoe Script", "Lucida Handwriting", "Brush Script MT"] if script
                     else ["Segoe UI", "Arial", "Helvetica"])
    font.setPixelSize(size)
    font.setBold(bold and not script)
    font.setItalic(script)
    return font


# Shrinks the font until the text fits on one line (long names, the signature, the ID number).
def _fit(text, size, width, script=False):
    while size > 16 and QFontMetricsF(_font(size, script=script)).horizontalAdvance(text) > width:
        size -= 2
    return size


# Draws text in a box; one-line text that's too long ends with "..." instead of overflowing.
def _text(painter, rect, text, font, color, flags=Qt.AlignLeft | Qt.AlignVCenter):
    painter.setFont(font)
    painter.setPen(color)
    if not flags & Qt.TextWordWrap:
        text = QFontMetricsF(font).elidedText(text, Qt.ElideRight, rect.width())
    painter.drawText(rect, int(flags), text)


# Front side fields: (key, label, value, width weight, full row?).
def _front_items(p):
    on = set(p["fields"])
    items = [
        ("name", "NAME", card_name(p), 0, True),
        ("sex", "SEX", p.get("sex"), 1, False),
        ("birthdate", "BIRTHDATE", birthdate_text(p), 1, False),
        ("civil_status", "CIVIL STATUS", p.get("civil_status"), 1, False),
        ("blood_type", "BLOOD TYPE", p.get("blood_type"), 1, False),
        ("nationality", "NATIONALITY", p.get("nationality"), 1, False),
        ("height_weight", "HEIGHT / WEIGHT", height_weight_text(p), 1, False),
        ("occupation", "OCCUPATION", p.get("occupation"), 0, True),
    ]
    return [i for i in items if i[0] in on]


def _back_items(p):
    on = set(p["fields"])
    items = [
        ("address", "ADDRESS", p.get("address"), 0, True),
        ("mobile", "MOBILE", format_mobile(p.get("mobile")), 2, False),
        ("email", "EMAIL", p.get("email"), 3, False),
        ("emergency", "IN CASE OF EMERGENCY", emergency_text(p), 0, True),
        ("validity", "ISSUED", p.get("issued_on"), 1, False),
        ("validity", "VALID UNTIL", p.get("valid_until"), 1, False),
    ]
    return [i for i in items if i[0] in on]


# Packs fields into rows: full-width fields get their own row, the rest go two per row.
def _rows(items):
    rows, pending = [], []
    for item in items:
        if item[4]:
            if pending:
                rows.append(pending)
                pending = []
            rows.append([item])
        else:
            pending.append(item)
            if len(pending) == 2:
                rows.append(pending)
                pending = []
    if pending:
        rows.append(pending)
    return rows


# Draws label + value pairs row by row and stops before running past the bottom.
# Within a row, fields share the width by their weight (e.g. EMAIL gets more than MOBILE).
def _draw_grid(painter, x, y, width, items, bottom, wrap=()):
    gap = 22
    for row in _rows(items):
        lines = 2 if row[0][0] in wrap else 1
        height = 22 + 32 * lines
        if y + height > bottom:
            break
        weights = [max(i[3], 1) for i in row]
        free = width - gap * (len(row) - 1)
        cx = x
        for item, weight in zip(row, weights):
            w = free * weight / sum(weights)
            _text(painter, QRectF(cx, y, w, 20), item[1], _font(16), MUTED)
            if lines == 2:
                flags = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
            else:
                flags = Qt.AlignLeft | Qt.AlignVCenter
            size = 22 if lines == 2 else (28 if item[0] == "name" else 24)
            _text(painter, QRectF(cx, y + 22, w, 32 * lines), item[2] or "–", _font(size), INK, flags)
            cx += w + gap
        y += height + 10
    return y


# The photo is cropped to fill the frame with rounded corners. Without a photo it shows
# initials and NO PHOTO.
def _draw_photo(painter, rect, p):
    clip = QPainterPath()
    clip.addRoundedRect(rect, 10, 10)
    painter.save()
    painter.setClipPath(clip)
    image = QImage.fromData(p["photo"]) if p.get("photo") else QImage()
    if not image.isNull():
        scaled = image.scaled(rect.size().toSize(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        sx, sy = (scaled.width() - rect.width()) / 2, (scaled.height() - rect.height()) / 2
        painter.drawImage(rect, scaled, QRectF(sx, sy, rect.width(), rect.height()))
    else:
        painter.fillRect(rect, PHOTO_BG)
        initials = "".join(n[0] for n in (p.get("first_name"), p.get("last_name")) if n) or "?"
        _text(painter, rect, initials, _font(64), MUTED, Qt.AlignCenter)
        _text(painter, QRectF(rect.x(), rect.bottom() - 40, rect.width(), 30), "NO PHOTO",
              _font(15), MUTED, Qt.AlignCenter)
    painter.restore()


def _draw_front(painter, p):
    on = set(p["fields"])
    left, top = 32, 92
    id_y = top
    if "photo" in on:
        _draw_photo(painter, QRectF(left, top, 220, 264), p)
        id_y = top + 280
    if "id_number" in on:
        number = format_id(p["id_number"])
        _text(painter, QRectF(left, id_y, 220, 20), "ID NO.", _font(16), MUTED)
        _text(painter, QRectF(left, id_y + 20, 220, 50), number, _font(_fit(number, 40, 220)), RED)
    # No photo and no ID number means no left column, so the fields use the full width.
    grid_x = 280 if on & {"photo", "id_number"} else left

    bottom = CARD_H - 24
    # The signature is the person's name in a handwriting-style font above a line.
    signed = "signature" in on and p.get("first_name")
    if signed:
        bottom -= 96
        line_y = CARD_H - 52
        painter.setPen(QPen(INK, 2))
        painter.drawLine(QRectF(560, line_y, 266, 0).topLeft(), QRectF(560, line_y, 266, 0).topRight())
        name = f"{p['first_name'].split()[0]} {p['last_name']}"
        _text(painter, QRectF(560, line_y - 58, 266, 56), name,
              _font(_fit(name, 34, 262, script=True), script=True), INK, Qt.AlignCenter)
        _text(painter, QRectF(560, line_y + 4, 266, 20), "SIGNATURE", _font(14), MUTED, Qt.AlignCenter)
    _draw_grid(painter, grid_x, top, CARD_W - grid_x - 30, _front_items(p), bottom)


# Decoration only: random bars seeded with the ID number, so the same ID always gets
# the same barcode. It isn't a scannable code.
def _draw_barcode(painter, rect, seed):
    rng = random.Random(seed)
    painter.setPen(Qt.NoPen)
    x = rect.x()
    while x < rect.right() - 8:
        width = rng.choice([3, 3, 4, 6, 8])
        painter.fillRect(QRectF(x, rect.y(), width, rect.height()), INK)
        x += width + rng.choice([3, 4, 6])


def _draw_back(painter, p):
    items = _back_items(p)
    if items:
        _draw_grid(painter, 32, 92, CARD_W - 64, items, CARD_H - 110, wrap=("address",))
    else:
        _text(painter, QRectF(0, BAND_H, CARD_W, CARD_H - BAND_H - 100), "NO CONTACT DETAILS ON THIS ID",
              _font(20), MUTED, Qt.AlignCenter)
    painter.setPen(QPen(LINE, 2))
    painter.drawLine(32, CARD_H - 100, CARD_W - 32, CARD_H - 100)
    if "id_number" in p["fields"]:
        _draw_barcode(painter, QRectF(32, CARD_H - 84, 260, 44), p["id_number"])
        _text(painter, QRectF(32, CARD_H - 38, 260, 20), format_id(p["id_number"]),
              _font(15, bold=False), INK, Qt.AlignCenter)
    # Always printed, so an exported card can never pass for a real ID.
    _text(painter, QRectF(320, CARD_H - 84, CARD_W - 352, 26), "SAMPLE ONLY · NOT A REAL ID",
          _font(20), RED, Qt.AlignRight | Qt.AlignVCenter)
    _text(painter, QRectF(320, CARD_H - 56, CARD_W - 352, 22),
          "Made with JD UTILS for a school project. All details are fake.",
          _font(15, bold=False), MUTED, Qt.AlignRight | Qt.AlignVCenter)


# Draws one side into any target rectangle. translate + scale map the 856 x 540 grid
# onto the target, so every number in this file is in card units, not pixels.
def paint_card(painter, target, person, side):
    painter.save()
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
    painter.translate(target.topLeft())
    painter.scale(target.width() / CARD_W, target.height() / CARD_H)

    shape = QPainterPath()
    shape.addRoundedRect(QRectF(0, 0, CARD_W, CARD_H), 28, 28)
    painter.fillPath(shape, PAPER)
    painter.setClipPath(shape)
    painter.fillRect(QRectF(0, 0, CARD_W, BAND_H), RED)
    _text(painter, QRectF(32, 0, CARD_W - 64, BAND_H), TITLE, _font(26), PAPER)
    if side == "front":
        _draw_front(painter, person)
    else:
        _draw_back(painter, person)
    painter.setClipping(False)
    painter.setPen(QPen(LINE, 3))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(shape)
    painter.restore()


# On-screen card. paintEvent runs whenever Qt needs to redraw; the card keeps its shape
# whatever size the widget is.
class IdCardView(QWidget):
    def __init__(self, side):
        super().__init__()
        self.side = side
        self.person = None
        self.setMinimumSize(300, 190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_person(self, person):
        self.person = person
        self.update()

    def paintEvent(self, event):
        if not self.person:
            return
        width = min(self.width(), self.height() * CARD_W / CARD_H)
        height = width * CARD_H / CARD_W
        target = QRectF((self.width() - width) / 2, 0, width, height)
        painter = QPainter(self)
        paint_card(painter, target, self.person, self.side)
        painter.end()


# PDF: two pages at the real ID size (85.6 x 54 mm), front then back, at 300 dpi.
# ExactMatch stops Qt from rounding the page to a standard paper size.
def export_card_pdf(person, path):
    writer = QPdfWriter(path)
    size = QPageSize(QSizeF(54, 85.6), QPageSize.Millimeter, "ID card", QPageSize.ExactMatch)
    writer.setPageLayout(QPageLayout(size, QPageLayout.Landscape, QMarginsF(0, 0, 0, 0)))
    writer.setResolution(300)
    writer.setTitle("JD UTILS fake ID")
    painter = QPainter()
    if not painter.begin(writer):
        raise OSError("Couldn't write the PDF. Close it if it's open in another app.")
    target = QRectF(0, 0, writer.width(), writer.height())
    paint_card(painter, target, person, "front")
    writer.newPage()
    paint_card(painter, target, person, "back")
    painter.end()


# PNG: front above back at twice the grid size, on a transparent background.
def export_card_png(person, path):
    width, height, gap = CARD_W * 2, CARD_H * 2, 40
    image = QImage(width, height * 2 + gap, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    paint_card(painter, QRectF(0, 0, width, height), person, "front")
    paint_card(painter, QRectF(0, height + gap, width, height), person, "back")
    painter.end()
    if not image.save(path, "PNG"):
        raise OSError("Couldn't write the PNG.")
