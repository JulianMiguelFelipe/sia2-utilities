"""Feature 2: Fake Data Generator page.

Top left: tick which fields to generate and press GENERATE. Top right: the
LAST GENERATED panel shows the person's photo, name and occupation, their data
as text, and OPEN ID / EDIT / COPY TEXT. Bottom: HISTORY, every person this user
has generated (saved in the database), with search, delete and download as
Excel or PDF. Clicking a row loads that person into the panel (shown as SELECTED).
"""

import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QFont, QPageLayout, QPageSize, QPainter, QPainterPath, QPdfWriter, QPixmap, QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QSizePolicy, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from services.fake_data_export import export_table_xlsx
from services.fake_data_service import (
    CARD_KEYS, DEFAULT_FIELDS, FIELDS, clear_people, delete_people, details, format_id,
    format_mobile, full_name, generate_person, get_person, latest_person, list_people,
    plain_text, save_person, shows_id,
)

from services.settings_service import get_setting, set_setting
from ui.edit_person_dialog import EditPersonDialog
from ui.id_window import SAVE_FAILED, IdWindow, save_path
from ui.scaling import current_scale, scale_events
from ui.signals import connect_alive
from ui.theme import colors, theme_events
from ui.widgets import field_label, make_box, make_button, set_status
from ui.workers import run_in_background

# Shown in the panel header next to the photo (and also listed in the text below it).
HEADER_KEYS = {"photo", "name", "occupation"}
GROUPS = ["PERSONAL", "CONTACT", "CARD"]
CHECK_COLUMNS = 3
TABLE_HEADERS = ["ID NO.", "NAME", "SEX", "BIRTHDATE", "CIVIL STATUS", "BLOOD", "OCCUPATION", "MADE"]
# Columns for the HISTORY PDF (fewer than Excel, so they fit on a landscape page).
PDF_COLUMNS = [
    ("ID No.", lambda p: format_id(p["id_number"]) if shows_id(p) else None),
    ("Name", full_name),
    ("Sex", lambda p: p.get("sex")),
    ("Birthdate", lambda p: p.get("birthdate")),
    ("Civil status", lambda p: p.get("civil_status")),
    ("Blood", lambda p: p.get("blood_type")),
    ("Occupation", lambda p: p.get("occupation")),
    ("Mobile", lambda p: format_mobile(p.get("mobile"))),
    ("Email", lambda p: p.get("email")),
    ("Address", lambda p: p.get("address")),
]


# HISTORY as a PDF: build an HTML table and let Qt's QTextDocument print it to a PDF.
# Opening the file first fails straight away if it's locked by another program.
def export_table_pdf(people, path):
    open(path, "ab").close()
    head = "".join(f'<th bgcolor="#e02424" align="left"><font color="#ffffff">{h}</font></th>'
                   for h, _ in PDF_COLUMNS)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(get(p) or '–'))}</td>" for _, get in PDF_COLUMNS)
                   + "</tr>" for p in people)
    doc = QTextDocument()
    font = QFont("Arial")
    font.setPointSizeF(7.5)
    doc.setDefaultFont(font)
    doc.setHtml(
        f'<h2><font color="#e02424">JD UTILS · FAKE DATA</font></h2>'
        f"<p>{len(people)} fake people · exported {datetime.now():%Y-%m-%d %I:%M %p} · "
        "not real people</p>"
        f'<table width="100%" border="1" cellspacing="0" cellpadding="3" '
        f'style="border-color:#bbbbbb;"><tr>{head}</tr>{body}</table>')
    writer = QPdfWriter(path)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape,
                                     QMarginsF(12, 12, 12, 12)))
    writer.setTitle("JD UTILS fake data")
    doc.print_(writer)


class FakeDataPage(QWidget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.people = []
        self.visible = []
        self.last = None
        self.id_window = None

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self.build_options_box(), stretch=1)
        top.addWidget(self.build_last_box())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self.build_table_box(), stretch=1)

        # The panel's HTML has colors and font sizes written in, so redraw it when either changes.
        connect_alive(theme_events.changed, self, lambda _t: self.show_last())
        connect_alive(scale_events.changed, self, lambda _s: self.show_last())
        self.load_choices()
        self.refresh()

    # Each account remembers its own field choices in app_settings.
    @property
    def setting_key(self):
        return f"fake_fields:{self.user['id']}"

    def build_options_box(self):
        box = make_box()
        self.count = QLabel("", objectName="hint")
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("FAKE DATA GENERATOR", objectName="boxTitle"))
        title_row.addStretch()
        title_row.addWidget(self.count, alignment=Qt.AlignBottom)

        # One grid for all three groups so the checkbox columns line up. Each group gets a
        # label row, then its checkboxes three per row.
        self.checks = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        row = 0
        for group in GROUPS:
            grid.addWidget(field_label(group), row, 0, 1, CHECK_COLUMNS)
            row += 1
            keys = [(key, label) for key, label, g, _ in FIELDS if g == group]
            for i, (key, label) in enumerate(keys):
                check = QCheckBox(label)
                check.setCursor(Qt.PointingHandCursor)
                check.toggled.connect(self.update_count)
                self.checks[key] = check
                grid.addWidget(check, row + i // CHECK_COLUMNS, i % CHECK_COLUMNS)
            row += (len(keys) - 1) // CHECK_COLUMNS + 1
            grid.setRowMinimumHeight(row, 6)
            row += 1
        for c in range(CHECK_COLUMNS):
            grid.setColumnStretch(c, 1)

        self.generate_btn = make_button("GENERATE", "primary", width=130)
        self.generate_btn.clicked.connect(self.handle_generate)
        all_btn = make_button("SELECT ALL", "secondary")
        all_btn.clicked.connect(lambda: self.set_all(True))
        none_btn = make_button("SELECT NONE", "secondary")
        none_btn.clicked.connect(lambda: self.set_all(False))
        self.message = QLabel("", objectName="error")
        self.message.setWordWrap(True)

        # GENERATE on the left; SELECT ALL / NONE on the right because they act on the checkboxes.
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.generate_btn)
        buttons.addSpacing(4)
        buttons.addWidget(self.message, stretch=1)
        buttons.addWidget(all_btn)
        buttons.addWidget(none_btn)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(4)
        layout.addLayout(title_row)
        layout.addWidget(QLabel("Pick which fields to generate for a fake person.", objectName="hint"))
        layout.addSpacing(6)
        layout.addLayout(grid)
        layout.addStretch()
        layout.addLayout(buttons)
        return box

    def set_all(self, on):
        for check in self.checks.values():
            check.setChecked(on)

    def selected_fields(self):
        return [key for key, check in self.checks.items() if check.isChecked()]

    def update_count(self):
        self.count.setText(f"{len(self.selected_fields())} of {len(FIELDS)} fields")

    # Tick the fields this user picked last time (or the defaults on first use).
    def load_choices(self):
        saved = get_setting(self.setting_key)
        fields = saved.split(",") if saved else DEFAULT_FIELDS
        for key, check in self.checks.items():
            check.setChecked(key in fields)
        self.update_count()

    def build_last_box(self):
        box = make_box()
        box.setFixedWidth(330)

        self.thumb = QLabel("", objectName="thumb")
        self.thumb.setFixedSize(90, 90)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setScaledContents(True)
        self.last_name = QLabel("", objectName="lastName")
        self.last_name.setWordWrap(True)
        self.last_job = QLabel("", objectName="lastJob")
        self.last_job.setWordWrap(True)
        self.last_meta = QLabel("", objectName="hint")
        self.last_meta.setWordWrap(True)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addStretch()
        for label in (self.last_name, self.last_job, self.last_meta):
            names.addWidget(label)
        names.addStretch()
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(self.thumb)
        header_layout.addLayout(names, stretch=1)

        # Ignored vertical size: the text panel takes whatever height is left instead of
        # making the top row taller and squeezing the HISTORY table.
        self.last_view = QTextBrowser(objectName="lastData")
        self.last_view.setOpenLinks(False)
        self.last_view.setMinimumHeight(60)
        self.last_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.open_btn = make_button("OPEN ID", "primary")
        self.open_btn.clicked.connect(lambda: self.open_person(self.last["id"] if self.last else None))
        self.edit_btn = make_button("EDIT", "secondary")
        self.edit_btn.clicked.connect(self.edit_last)
        self.copy_btn = make_button("COPY TEXT", "secondary")
        self.copy_btn.clicked.connect(self.copy_last)
        self.last_message = QLabel("", objectName="success")

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for btn in (self.open_btn, self.edit_btn, self.copy_btn):
            buttons.addWidget(btn, stretch=1)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        self.last_title = QLabel("LAST GENERATED", objectName="sectionTitle")
        title_row.addWidget(self.last_title)
        title_row.addStretch()
        title_row.addWidget(self.last_message)
        layout.addLayout(title_row)
        layout.addWidget(self.header)
        layout.addWidget(self.last_view, stretch=1)
        layout.addLayout(buttons)
        return box

    @staticmethod
    # Crops the photo to a square with rounded corners for the panel header.
    def rounded(photo):
        source = QPixmap()
        if not source.loadFromData(photo):
            return None
        size = min(source.width(), source.height())
        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.09, size * 0.09)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipPath(clip)
        left, top = (source.width() - size) // 2, (source.height() - size) // 2
        painter.drawPixmap(0, 0, source, left, top, size, size)
        painter.end()
        return result

    # Header above the text: photo, name and occupation. A failed photo download shows
    # initials and a hint instead.
    def show_header(self):
        p = self.last
        on = set(p["fields"]) if p else set()
        self.header.setVisible(bool(on & HEADER_KEYS))
        if not p:
            return
        self.thumb.setVisible("photo" in on)
        self.thumb.clear()
        pixmap = self.rounded(p["photo"]) if p.get("photo") else None
        if pixmap:
            self.thumb.setPixmap(pixmap)
        else:
            initials = "".join(n[0] for n in (p.get("first_name"), p.get("last_name")) if n)
            self.thumb.setText(initials or "?")
        self.last_name.setText(full_name(p))
        self.last_name.setVisible("name" in on)
        self.last_job.setText(p.get("occupation") or "")
        self.last_job.setVisible("occupation" in on)
        missing = "photo" in on and not p.get("photo")
        self.last_meta.setText("No photo. Open the ID and click NEW PHOTO." if missing else "")
        self.last_meta.setVisible(missing)

    # The person's data as label/value pairs. CARD fields (ID number, issued/valid,
    # signature, emergency contact) are left out; they belong to the ID view.
    def last_html(self):
        c, s = colors(), current_scale()
        px = lambda n: round(n * s)
        if not self.last:
            return (f'<p style="color:{c["muted"]}; font-size:{px(12)}px;">'
                    "Click GENERATE to make a fake person. Their details show up here, "
                    "and every person is saved to HISTORY below.</p>")
        rows = []
        for key, label, value in details(self.last):
            if key in CARD_KEYS:
                continue
            rows.append(
                f'<p style="margin:0; color:{c["muted"]}; font-size:{px(10)}px; font-weight:800;">'
                f"{html.escape(label.upper())}</p>"
                f'<p style="margin:0 0 {px(8)}px 0; font-size:{px(13)}px;">{html.escape(str(value))}</p>')
        if not rows:
            rows.append(f'<p style="color:{c["muted"]}; font-size:{px(12)}px;">'
                        "No other fields were generated.</p>")
        return "".join(rows)

    # Which person to show: the one asked for, otherwise keep the current one (reloaded to pick
    # up edits), or fall back to the newest if it was deleted. The title says LAST GENERATED
    # for the newest person and SELECTED for an older one picked in HISTORY.
    def show_last(self, person_id=None):
        latest = latest_person(self.user["id"])
        if person_id is not None:
            self.last = get_person(self.user["id"], person_id)
        elif self.last is None or get_person(self.user["id"], self.last["id"]) is None:
            self.last = latest
        else:
            self.last = get_person(self.user["id"], self.last["id"])
        newest = self.last is None or (latest is not None and self.last["id"] == latest["id"])
        self.last_title.setText("LAST GENERATED" if newest else "SELECTED")
        self.show_header()
        self.last_view.setHtml(self.last_html())
        for btn in (self.open_btn, self.edit_btn, self.copy_btn):
            btn.setEnabled(self.last is not None)

    # Clicking a HISTORY row shows that person in the panel.
    def show_selected(self):
        person_id = self.selected_id()
        if person_id is not None and (self.last is None or person_id != self.last["id"]):
            self.last_message.clear()
            self.show_last(person_id)

    # exec() keeps the EDIT window on top until it's closed; saving refreshes the page.
    def edit_last(self):
        if not self.last:
            return
        dialog = EditPersonDialog(self, self.user, self.last["id"])
        if dialog.person is None:
            return self.refresh()
        dialog.changed.connect(self.refresh)
        dialog.exec()

    def copy_last(self):
        if self.last:
            QApplication.clipboard().setText(plain_text(self.last))
            self.last_message.setText("Copied")

    # GENERATE: remember the choices, then build the person in the background
    # (the photo download can take a few seconds).
    def handle_generate(self):
        fields = self.selected_fields()
        if not fields:
            return set_status(self.message, "Pick at least one field.")
        set_setting(self.setting_key, ",".join(fields))
        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("WORKING...")
        set_status(self.message, "Getting a photo..." if "photo" in fields else "Making a person...",
                   success=True)
        run_in_background(generate_person, self.user["id"], fields,
                          on_done=self.generated, on_error=self.generate_failed)

    def finish_generating(self):
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("GENERATE")

    # Back on the main thread: save to the database, then show the new person in the panel
    # and select it in HISTORY.
    def generated(self, person):
        self.finish_generating()
        person_id = save_person(self.user["id"], person)
        self.last_message.clear()
        if person["photo_error"]:
            set_status(self.message, f"{person['photo_error']} Saved without a photo.")
        else:
            set_status(self.message, "Saved to history.", success=True)
        self.refresh(select=person_id, last=person_id)

    def generate_failed(self, _err):
        self.finish_generating()
        set_status(self.message, "Couldn't generate. Try again.")

    # Only one ID window at a time; opening another closes the previous one.
    def open_person(self, person_id):
        if person_id is None:
            return set_status(self.table_message, "Select a row in the history first.")
        if self.id_window is not None:
            self.id_window.close()
        self.id_window = IdWindow(self, self.user, person_id)
        if self.id_window.person is None:
            self.id_window = None
            return self.refresh()
        self.id_window.changed.connect(self.refresh)
        self.id_window.open()

    def close_id_window(self):
        if self.id_window is not None:
            self.id_window.close()
            self.id_window = None

    def build_table_box(self):
        box = make_box()

        self.search = QLineEdit()
        self.search.setFixedHeight(32)
        self.search.setFixedWidth(200)
        self.search.setPlaceholderText("Search history")
        self.search.textChanged.connect(self.show_table)

        open_btn = make_button("OPEN ID", "secondary")
        open_btn.clicked.connect(lambda: self.open_person(self.selected_id()))
        download_btn = make_button("DOWNLOAD ▾", "secondary")
        menu = QMenu(self)
        menu.addAction("Excel (.xlsx)", lambda: self.download_table("xlsx"))
        menu.addAction("PDF (.pdf)", lambda: self.download_table("pdf"))
        download_btn.clicked.connect(
            lambda: menu.exec(download_btn.mapToGlobal(download_btn.rect().bottomLeft())))
        delete_btn = make_button("DELETE SELECTED", "secondary")
        delete_btn.clicked.connect(self.handle_delete)
        clear_btn = make_button("CLEAR ALL", "primary")
        clear_btn.clicked.connect(self.handle_clear_all)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(QLabel("HISTORY", objectName="sectionTitle"))
        title_row.addSpacing(8)
        title_row.addWidget(self.search)
        title_row.addStretch()
        title_row.addWidget(open_btn)
        title_row.addWidget(download_btn)
        title_row.addSpacing(14)
        title_row.addWidget(delete_btn)
        title_row.addWidget(clear_btn)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(70)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.open_person(self.row_id(r)))
        # Single click shows the person above; double click opens the ID.
        self.table.itemSelectionChanged.connect(self.show_selected)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.empty_label = QLabel("Nothing yet. Everything you generate is saved here. Click a row to "
                                  "see it above, double-click to open its ID.", objectName="hint")
        self.table_message = QLabel("", objectName="error")
        bottom = QHBoxLayout()
        bottom.addWidget(self.empty_label)
        bottom.addStretch()
        bottom.addWidget(self.table_message)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.addLayout(title_row)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(bottom)
        return box

    def refresh(self, select=None, last=None):
        self.people = list_people(self.user["id"])
        self.show_table()
        self.show_last(last)
        if select is not None:
            self.select_row(select)

    @staticmethod
    # Search matches any visible value; the ID number is searchable with or without dashes.
    def search_text(p):
        values = [full_name(p), p.get("sex"), p.get("birthdate"), p.get("civil_status"),
                  p.get("blood_type"), p.get("occupation"), p.get("address"), p.get("mobile"), p.get("email")]
        if shows_id(p):
            values += [p["id_number"], format_id(p["id_number"])]
        return " ".join(v for v in values if v).lower()

    def show_table(self):
        query = self.search.text().strip().lower()
        self.visible = [p for p in self.people if not query or query in self.search_text(p)]
        self.table.setRowCount(len(self.visible))
        self.empty_label.setVisible(not self.people)
        for r, p in enumerate(self.visible):
            values = [format_id(p["id_number"]) if shows_id(p) else None, full_name(p), p.get("sex"),
                      p.get("birthdate"), p.get("civil_status"), p.get("blood_type"),
                      p.get("occupation"), p["created_at"]]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value or "–")
                # Each cell remembers the person's database id.
                item.setData(Qt.UserRole, p["id"])
                self.table.setItem(r, c, item)

    def row_id(self, row):
        return self.table.item(row, 0).data(Qt.UserRole)

    def selected_rows(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def selected_id(self):
        rows = self.selected_rows()
        return self.row_id(rows[0]) if rows else None

    def select_row(self, person_id):
        self.search.clear()
        for r in range(self.table.rowCount()):
            if self.row_id(r) == person_id:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                return

    def handle_delete(self):
        rows = self.selected_rows()
        if not rows:
            return set_status(self.table_message, "Select a row in the history first.")
        # Close the ID window first in case it shows someone being deleted.
        self.close_id_window()
        delete_people(self.user["id"], [self.row_id(r) for r in rows])
        self.table_message.clear()
        self.refresh()

    def handle_clear_all(self):
        if not self.people:
            return
        answer = QMessageBox.question(self, "JD UTILS", "Delete your whole fake data history?")
        if answer == QMessageBox.Yes:
            self.close_id_window()
            clear_people(self.user["id"])
            self.table_message.clear()
            self.refresh()

    # Downloads exactly what the table shows, so searching first exports a filtered list.
    def download_table(self, kind):
        if not self.visible:
            return set_status(self.table_message, "There's nothing to download yet.")
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        if kind == "xlsx":
            path = save_path(self, "Save history as Excel", f"JD_FakeData_{stamp}.xlsx",
                             "Excel files (*.xlsx)")
            writer = export_table_xlsx
        else:
            path = save_path(self, "Save history as PDF", f"JD_FakeData_{stamp}.pdf", "PDF files (*.pdf)")
            writer = export_table_pdf
        if not path:
            return
        try:
            writer(self.visible, path)
        except OSError:
            return set_status(self.table_message, SAVE_FAILED)
        set_status(self.table_message, f"Saved {Path(path).name} ({len(self.visible)} people)", success=True)
