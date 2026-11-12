"""Feature 2: the ID window, which shows a generated person as the front and back of an ID card.

Opened with OPEN ID (or by double-clicking a HISTORY row). It only views: NEW PHOTO
downloads another face, DOWNLOAD saves the card as a PDF or a PNG, and editing
happens in the EDIT window (ui/edit_person_dialog.py) from the main page.
"""

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout,
)

from services.fake_data_service import (
    PhotoError, card_name, format_id, get_person, replace_photo, shows_id,
)
from ui.id_card import IdCardView, export_card_pdf, export_card_png
from ui.messaging_shared import friendly_time
from ui.scaling import current_scale
from ui.widgets import make_box, make_button, set_status
from ui.workers import run_in_background

SAVE_FAILED = "Couldn't save the file. Close it if it's open in another app, then try again."


# Save dialog that starts in the user's Downloads folder.
def save_path(parent, title, filename, file_filter):
    folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home())
    path, _ = QFileDialog.getSaveFileName(parent, title, str(Path(folder) / filename), file_filter)
    return path


class IdWindow(QDialog):
    # Tells the page to refresh after a new photo, so the panel shows it too.
    changed = Signal()

    def __init__(self, parent, user, person_id, notice=""):
        super().__init__(parent)
        self.user = user
        self.person_id = person_id
        self.person = None
        # Dialogs aren't part of the window scaling capture, so they size themselves from the scale.
        s = current_scale()
        self.setWindowTitle("JD UTILS")
        self.setMinimumSize(round(760 * s), round(430 * s))
        self.resize(round(920 * s), round(440 * s))

        self.title = QLabel("", objectName="sectionTitle")
        self.subtitle = QLabel("", objectName="hint")

        self.front, self.back = IdCardView("front"), IdCardView("back")
        cards = QGridLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setHorizontalSpacing(round(16 * s))
        for col, (card, caption) in enumerate(((self.front, "FRONT"), (self.back, "BACK"))):
            card.setMinimumSize(round(330 * s), round(208 * s))
            cards.addWidget(QLabel(caption, objectName="cardCaption"), 0, col, alignment=Qt.AlignCenter)
            cards.addWidget(card, 1, col)

        self.status = QLabel("", objectName="error")
        self.status.setWordWrap(True)

        self.photo_btn = make_button("NEW PHOTO", "secondary")
        self.photo_btn.clicked.connect(self.new_photo)
        download_btn = make_button("DOWNLOAD ▾", "secondary")
        menu = QMenu(self)
        menu.addAction("PDF (.pdf)", lambda: self.download("pdf"))
        menu.addAction("PNG (.png)", lambda: self.download("png"))
        # The menu opens right under the button.
        download_btn.clicked.connect(
            lambda: menu.exec(download_btn.mapToGlobal(download_btn.rect().bottomLeft())))
        close_btn = make_button("CLOSE", "primary")
        close_btn.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.photo_btn)
        buttons.addStretch()
        buttons.addWidget(download_btn)
        buttons.addWidget(close_btn)
        # Stop Enter from pressing a button by accident.
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)

        box = make_box()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(round(20 * s), round(14 * s), round(20 * s), round(16 * s))
        inner.setSpacing(round(8 * s))
        inner.addWidget(self.title)
        inner.addWidget(self.subtitle)
        inner.addLayout(cards, stretch=1)
        inner.addWidget(self.status)
        inner.addLayout(buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

        self.load()
        if notice:
            set_status(self.status, notice)

    def load(self):
        self.person = get_person(self.user["id"], self.person_id)
        if self.person is None:
            # The person was deleted while the window was opening.
            self.reject()
            return
        p = self.person
        self.title.setText(card_name(p) or "FAKE PERSON")
        made = f"Made {friendly_time(p['created_at'])}"
        self.subtitle.setText(f"ID {format_id(p['id_number'])} · {made}" if shows_id(p) else made)
        self.photo_btn.setVisible("photo" in p["fields"])
        self.front.set_person(p)
        self.back.set_person(p)

    def file_name(self, ext):
        last = re.sub(r"[^A-Za-z0-9]", "", self.person.get("last_name") or "")
        return f"JD_ID_{last or 'Person'}_{self.person['id']}.{ext}"

    def download(self, kind):
        if kind == "pdf":
            path = save_path(self, "Save ID as PDF", self.file_name("pdf"), "PDF files (*.pdf)")
            writer = export_card_pdf
        else:
            path = save_path(self, "Save ID as image", self.file_name("png"), "PNG images (*.png)")
            writer = export_card_png
        if not path:
            return
        # Writing fails if the file is open in another program (e.g. a PDF viewer).
        try:
            writer(self.person, path)
        except OSError:
            return set_status(self.status, SAVE_FAILED)
        set_status(self.status, f"Saved {Path(path).name}", success=True)

    def new_photo(self):
        self.photo_btn.setEnabled(False)
        self.photo_btn.setText("LOADING...")
        set_status(self.status, "Getting a new photo...", success=True)
        # Downloading and saving the photo runs in the background; the window stays usable.
        run_in_background(replace_photo, self.user["id"], self.person_id,
                          on_done=lambda _: self.photo_done(), on_error=self.photo_failed)

    def photo_done(self):
        self.photo_btn.setEnabled(True)
        self.photo_btn.setText("NEW PHOTO")
        self.load()
        set_status(self.status, "New photo saved.", success=True)
        self.changed.emit()

    def photo_failed(self, err):
        self.photo_btn.setEnabled(True)
        self.photo_btn.setText("NEW PHOTO")
        set_status(self.status, str(err) if isinstance(err, PhotoError)
                   else "Couldn't get a new photo. Try again.")
