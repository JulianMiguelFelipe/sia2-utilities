"""URL Shortener page."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from services.url_service import (
    clear_short_urls, delete_short_urls, find_existing, get_history,
    normalize_url, save_short_url, shorten_url,
)
from ui.messaging_shared import friendly_time
from ui.widgets import field_label, make_box, make_button, set_status
from ui.workers import run_in_background


def make_field(placeholder="", read_only=False):
    """Text field."""
    field = QLineEdit()
    field.setFixedHeight(32)
    field.setPlaceholderText(placeholder)
    field.setReadOnly(read_only)
    return field


def savings_text(long_url, short_url):
    """'49 -> 28 characters' line."""
    saved = len(long_url) - len(short_url)
    if saved <= 0:
        return f"{len(long_url)} → {len(short_url)} characters (this link was already short)"
    percent = round(saved / len(long_url) * 100)
    return f"{len(long_url)} → {len(short_url)} characters · saved {saved} ({percent}% shorter)"


class UrlShortenerPage(QWidget):
    """URL Shortener page."""
    def __init__(self, user):
        """Build the page."""
        super().__init__()
        self.user = user
        self.history = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self.build_form_box())
        layout.addWidget(self.build_history_box(), stretch=1)
        self.refresh()

    # ---------- Shortening ----------
    def build_form_box(self):
        """Shortening box."""
        box = make_box()

        self.long_url = make_field("Paste a long link, e.g. https://example.com/a/very/long/link")
        self.long_url.textChanged.connect(self.update_counter)
        self.long_url.returnPressed.connect(self.handle_shorten)
        self.counter = QLabel("0 characters", objectName="hint")
        paste_btn = make_button("PASTE", "secondary", width=90)
        paste_btn.clicked.connect(self.paste)
        self.start_btn = make_button("START", "primary", width=130)
        self.start_btn.clicked.connect(self.handle_shorten)

        long_label = QHBoxLayout()
        long_label.addWidget(field_label("LONG URL"))
        long_label.addStretch()
        long_label.addWidget(self.counter)
        long_row = QHBoxLayout()
        long_row.setSpacing(8)
        long_row.addWidget(self.long_url, stretch=1)
        long_row.addWidget(paste_btn)
        long_row.addWidget(self.start_btn)

        self.short_url = make_field("Your short link appears here", read_only=True)
        copy_btn = make_button("COPY", "secondary", width=90)
        copy_btn.clicked.connect(lambda: self.copy(self.short_url.text()))
        open_btn = make_button("OPEN", "secondary", width=90)
        open_btn.clicked.connect(lambda: self.open_link(self.short_url.text()))
        short_row = QHBoxLayout()
        short_row.setSpacing(8)
        short_row.addWidget(self.short_url, stretch=1)
        short_row.addWidget(copy_btn)
        short_row.addWidget(open_btn)

        self.savings = QLabel("", objectName="hint")
        self.message = QLabel("", objectName="error")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(4)
        layout.addWidget(QLabel("URL SHORTENER", objectName="boxTitle"))
        layout.addWidget(QLabel("Turn a long link into a short TinyURL you can share anywhere.",
                                objectName="hint"))
        layout.addSpacing(8)
        layout.addLayout(long_label)
        layout.addLayout(long_row)
        layout.addSpacing(8)
        layout.addWidget(field_label("SHORT URL"))
        layout.addLayout(short_row)
        status_row = QHBoxLayout()
        status_row.addWidget(self.message)
        status_row.addStretch()
        status_row.addWidget(self.savings)
        layout.addLayout(status_row)
        return box

    def update_counter(self):
        """Character counter."""
        n = len(self.long_url.text().strip())
        self.counter.setText(f"{n} character{'s' if n != 1 else ''}")

    def paste(self):
        """PASTE button."""
        self.long_url.setText(QApplication.clipboard().text().strip())
        self.long_url.setFocus()

    def show_message(self, text, success=False):
        """Status message."""
        set_status(self.message, text, success)

    def handle_shorten(self):
        """START button."""
        self.short_url.clear()
        self.savings.clear()
        try:
            url = normalize_url(self.long_url.text())
        except ValueError as err:
            self.show_message(str(err))
            return
        self.long_url.setText(url)

        existing = find_existing(self.user["id"], url)      # shortened before? reuse it
        if existing:
            self.short_url.setText(existing["short_url"])
            self.savings.setText(savings_text(url, existing["short_url"]))
            self.show_message(f"Already shortened {friendly_time(existing['created_at'])}. "
                              "Using your saved link.", success=True)
            self.select_in_history(existing["id"])
            return

        self.start_btn.setEnabled(False)
        self.start_btn.setText("WORKING...")
        self.show_message("Shortening...", success=True)
        run_in_background(shorten_url, url,
                          on_done=lambda short: self.shorten_done(url, short),
                          on_error=self.shorten_failed)

    def finish(self):
        """Reset the START button."""
        self.start_btn.setEnabled(True)
        self.start_btn.setText("START")

    def shorten_done(self, url, short):
        """Short link received."""
        self.finish()
        self.short_url.setText(short)
        save_short_url(self.user["id"], url, short)
        self.savings.setText(savings_text(url, short))
        self.show_message("Done! Saved to your history.", success=True)
        self.refresh()

    def shorten_failed(self, err):
        """Shortening failed."""
        self.finish()
        self.show_message(str(err) if isinstance(err, ConnectionError)
                          else "Something went wrong. Try again.")

    def copy(self, link):
        """COPY button."""
        if not link:
            return self.show_message("Shorten a link first.")
        QApplication.clipboard().setText(link)
        self.show_message(f"Copied {link}", success=True)

    def open_link(self, link):
        """OPEN button."""
        if not link:
            return self.show_message("Shorten a link first.")
        QDesktopServices.openUrl(QUrl(link))              # opens in your browser

    # ---------- History ----------
    def build_history_box(self):
        """HISTORY box."""
        box = make_box()

        self.search = make_field("Search links")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.show_history)
        copy_btn = make_button("COPY", "secondary")
        copy_btn.clicked.connect(lambda: self.copy(self.selected_short()))
        open_btn = make_button("OPEN", "secondary")
        open_btn.clicked.connect(lambda: self.open_link(self.selected_short()))
        delete_btn = make_button("DELETE SELECTED", "secondary")
        delete_btn.clicked.connect(self.handle_delete)
        clear_btn = make_button("CLEAR ALL", "primary")
        clear_btn.clicked.connect(self.handle_clear_all)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(QLabel("HISTORY", objectName="sectionTitle"))
        title_row.addSpacing(8)
        title_row.addWidget(self.search)
        title_row.addStretch()
        for btn in (copy_btn, open_btn, delete_btn, clear_btn):
            title_row.addWidget(btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["DATE", "SHORT URL", "ORIGINAL URL", "SAVED"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(70)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.copy(self.table.item(r, 1).text()))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)    # ORIGINAL URL fills the rest
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.empty_label = QLabel("No links yet. Shortened links will show up here. "
                                  "Double-click a row to copy its short link.", objectName="hint")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.addLayout(title_row)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.empty_label)
        return box

    def refresh(self):
        """Reload the history."""
        self.history = get_history(self.user["id"])
        self.show_history()

    def show_history(self):
        """Draw the history table."""
        query = self.search.text().strip().lower()
        rows = [h for h in self.history
                if not query or query in h["original_url"].lower() or query in h["short_url"].lower()]
        self.table.setRowCount(len(rows))
        self.empty_label.setVisible(not self.history)
        for r, h in enumerate(rows):
            saved = max(len(h["original_url"]) - len(h["short_url"]), 0)
            values = [h["created_at"], h["short_url"], h["original_url"], f"{saved} chars"]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, h["id"])
                if c == 2:
                    item.setToolTip(value)                   # full link on hover
                self.table.setItem(r, c, item)

    def selected_short(self):
        """Selected short link."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return self.table.item(rows[0], 1).text() if rows else ""

    def select_in_history(self, row_id):
        """Highlight a history row."""
        self.search.clear()
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole) == row_id:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                return

    def handle_delete(self):
        """DELETE SELECTED button."""
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return self.show_message("Select a link in the history first.")
        delete_short_urls(self.user["id"], [self.table.item(r, 0).data(Qt.UserRole) for r in rows])
        self.refresh()

    def handle_clear_all(self):
        """CLEAR ALL button."""
        if not self.history:
            return
        answer = QMessageBox.question(self, "JD UTILS", "Delete your whole link history?")
        if answer == QMessageBox.Yes:
            clear_short_urls(self.user["id"])
            self.refresh()
