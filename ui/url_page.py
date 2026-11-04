"""
ui/url_page.py
URL Shortener page: paste a long link, press START, copy the short link.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from services.url_service import normalize_url, save_short_url, shorten_url
from ui.widgets import ImageSlot, field_label, make_box, make_button, set_status
from ui.workers import run_in_background


class UrlShortenerPage(QWidget):
    def __init__(self, user):
        super().__init__()
        self.user = user

        # ----- The main box -----
        box = make_box()
        box.setFixedWidth(676)

        self.long_url = QLineEdit()
        self.long_url.setFixedHeight(30)
        self.long_url.setPlaceholderText("https://example.com/a/very/long/link")
        self.long_url.returnPressed.connect(self.handle_shorten)

        self.short_url = QLineEdit()
        self.short_url.setFixedHeight(30)
        self.short_url.setReadOnly(True)

        self.start_btn = make_button("START", "primary", width=150)
        self.start_btn.clicked.connect(self.handle_shorten)

        copy_btn = make_button("COPY LINK TO CLIPBOARD", "secondary", width=192)
        copy_btn.clicked.connect(self.handle_copy)

        self.message = QLabel("", objectName="error")

        form = QVBoxLayout()
        form.setContentsMargins(22, 0, 38, 0)
        form.setSpacing(2)
        form.addWidget(field_label("LONG URL"))
        form.addWidget(self.long_url)
        form.addSpacing(10)
        form.addWidget(self.start_btn, alignment=Qt.AlignCenter)
        form.addSpacing(14)
        form.addWidget(field_label("SHORT URL"))
        form.addWidget(self.short_url)
        form.addSpacing(10)
        form.addWidget(copy_btn, alignment=Qt.AlignCenter)
        form.addSpacing(4)
        form.addWidget(self.message, alignment=Qt.AlignCenter)

        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(22, 14, 22, 14)
        box_layout.addWidget(QLabel("URL SHORTENER", objectName="boxTitle"))
        box_layout.addSpacing(6)
        box_layout.addLayout(form)

        box_row = QHBoxLayout()
        box_row.addStretch()
        box_row.addWidget(box)
        box_row.addStretch()

        # ----- Art row under the box -----
        small_art = ImageSlot("url_art_small.png", min_width=118, min_height=120)
        small_art.setFixedWidth(118)
        big_art = ImageSlot("url_art_large.png", min_width=300, min_height=120)

        art_row = QHBoxLayout()
        art_row.setSpacing(0)
        art_row.addWidget(small_art)
        art_row.addSpacing(132)
        art_row.addWidget(big_art, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 44, 26, 0)
        layout.setSpacing(22)
        layout.addLayout(box_row)
        layout.addLayout(art_row, stretch=1)

    def show_message(self, text, success=False):
        set_status(self.message, text, success)

    def handle_shorten(self):
        self.short_url.clear()
        try:
            url = normalize_url(self.long_url.text())
        except ValueError as err:
            self.show_message(str(err))
            return

        self.long_url.setText(url)
        self.start_btn.setEnabled(False)
        self.start_btn.setText("WORKING...")
        self.show_message("Shortening...", success=True)
        run_in_background(shorten_url, url,
                          on_done=lambda short: self.shorten_done(url, short),
                          on_error=self.shorten_failed)

    def finish(self):
        self.start_btn.setEnabled(True)
        self.start_btn.setText("START")

    def shorten_done(self, url, short):
        self.finish()
        self.short_url.setText(short)
        save_short_url(self.user["id"], url, short)
        self.show_message("Done! Saved to your history.", success=True)

    def shorten_failed(self, err):
        self.finish()
        self.show_message(str(err) if isinstance(err, ConnectionError)
                          else "Something went wrong. Try again.")

    def handle_copy(self):
        if not self.short_url.text():
            self.show_message("Shorten a link first.")
            return
        QApplication.clipboard().setText(self.short_url.text())
        self.show_message("Copied to clipboard!", success=True)
