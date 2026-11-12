"""Feature 2: the EDIT window for a generated person (EDIT button in LAST GENERATED).

The form only shows the fields that were generated for this person. Each field
gets the right input: a dropdown for sex, civil status and blood type, a date
picker for dates, and number-only boxes for height and weight, so most mistakes
can't even be typed. SAVE CHANGES runs validate_edits() and saves to the database.
"""

from PySide6.QtCore import QDate, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from services.fake_data_service import (
    BLOOD_TYPES, CIVIL_STATUSES, SEXES, full_name, get_person, update_person, validate_edits,
)
from ui.scaling import current_scale
from ui.widgets import field_label, make_box, make_button, set_status


class EditPersonDialog(QDialog):
    # Tells the page to refresh its panel and table after saving.
    changed = Signal()

    def __init__(self, parent, user, person_id):
        super().__init__(parent)
        self.user = user
        self.person_id = person_id
        self.person = get_person(user["id"], person_id)
        self.inputs = {}
        self.s = s = current_scale()
        self.setWindowTitle("JD UTILS")
        self.setMinimumSize(round(560 * s), round(380 * s))
        self.resize(round(720 * s), round(560 * s))
        # The person may have been deleted in the meantime; the page checks for this.
        if self.person is None:
            return

        title = QLabel("EDIT DATA", objectName="sectionTitle")
        subtitle = QLabel(full_name(self.person) or "Fake person", objectName="hint")
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        self.build_form(area)
        self.status = QLabel("", objectName="error")
        self.status.setWordWrap(True)

        cancel_btn = make_button("CANCEL", "secondary")
        cancel_btn.clicked.connect(self.reject)
        save_btn = make_button("SAVE CHANGES", "primary")
        save_btn.clicked.connect(self.save)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        # Stop Enter from pressing a button by accident; Enter in a text box saves instead.
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)

        box = make_box()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(round(20 * s), round(14 * s), round(20 * s), round(16 * s))
        inner.setSpacing(round(8 * s))
        inner.addWidget(title)
        inner.addWidget(subtitle)
        inner.addWidget(area, stretch=1)
        inner.addWidget(self.status)
        inner.addLayout(buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        first = next(iter(self.inputs.values()), None)
        if first:
            first.setFocus()

    # Small helpers that create one input, fill it with the current value and remember it
    # in self.inputs under its database column name.
    def _sized(self, widget):
        widget.setFixedHeight(round(30 * self.s))
        return widget

    def _line(self, key, placeholder=""):
        field = self._sized(QLineEdit(str(self.person.get(key) or "")))
        field.setPlaceholderText(placeholder)
        field.returnPressed.connect(self.save)
        self.inputs[key] = field
        return field

    def _combo(self, key, options):
        box = self._sized(QComboBox())
        box.addItems(options)
        if self.person.get(key) and self.person[key] not in options:
            box.addItem(self.person[key])
        box.setCurrentText(self.person.get(key) or options[0])
        self.inputs[key] = box
        return box

    def _date(self, key, latest=None):
        edit = self._sized(QDateEdit())
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        if latest:
            edit.setMaximumDate(latest)
        edit.setDate(QDate.fromString(self.person.get(key) or "", "yyyy-MM-dd"))
        self.inputs[key] = edit
        return edit

    # QIntValidator only lets digits be typed; the real range check is in validate_edits().
    def _number(self, key, low, high, unit):
        field = self._line(key, unit)
        field.setValidator(QIntValidator(low, high, field))
        return field

    @staticmethod
    def _pair(*widgets):
        row = QHBoxLayout()
        for w in widgets:
            row.addWidget(w)
        return row

    # Builds the form from the fields that are on. Each cell is (label, input, full width?);
    # they are then laid out two per row, with full-width cells (name, address) on their own row.
    def build_form(self, area):
        on = set(self.person["fields"])
        self.inputs = {}
        cells = []
        if "name" in on:
            cells.append(("NAME (FIRST · MIDDLE · LAST)", self._pair(
                self._line("first_name", "First"), self._line("middle_name", "Middle (optional)"),
                self._line("last_name", "Last")), True))
        if "sex" in on:
            cells.append(("SEX", self._combo("sex", SEXES), False))
        if "birthdate" in on:
            cells.append(("BIRTHDATE", self._date("birthdate", QDate.currentDate()), False))
        if "civil_status" in on:
            cells.append(("CIVIL STATUS", self._combo("civil_status", CIVIL_STATUSES), False))
        if "blood_type" in on:
            cells.append(("BLOOD TYPE", self._combo("blood_type", BLOOD_TYPES), False))
        if "nationality" in on:
            cells.append(("NATIONALITY", self._line("nationality"), False))
        if "height_weight" in on:
            cells.append(("HEIGHT (CM) / WEIGHT (KG)", self._pair(self._number("height_cm", 1, 999, "cm"),
                                                        self._number("weight_kg", 1, 999, "kg")), False))
        if "occupation" in on:
            cells.append(("OCCUPATION", self._line("occupation"), False))
        if "address" in on:
            cells.append(("ADDRESS", self._line("address"), True))
        if "mobile" in on:
            cells.append(("MOBILE NUMBER", self._line("mobile", "09171234567"), False))
        if "email" in on:
            cells.append(("EMAIL", self._line("email", "name@example.com"), False))
        if "emergency" in on:
            cells.append(("EMERGENCY CONTACT NAME", self._line("emergency_name"), False))
            cells.append(("EMERGENCY CONTACT MOBILE", self._line("emergency_phone", "09171234567"), False))
        if "validity" in on:
            cells.append(("ISSUED", self._date("issued_on"), False))
            cells.append(("VALID UNTIL", self._date("valid_until"), False))

        form = QWidget()
        grid = QGridLayout(form)
        grid.setContentsMargins(0, 0, round(10 * self.s), 0)
        grid.setHorizontalSpacing(round(14 * self.s))
        grid.setVerticalSpacing(round(8 * self.s))
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        row = col = 0
        for label, content, wide in cells:
            if wide and col == 1:
                row, col = row + 1, 0
            cell = QVBoxLayout()
            cell.setSpacing(round(3 * self.s))
            cell.addWidget(field_label(label))
            if isinstance(content, QWidget):
                cell.addWidget(content)
            else:
                cell.addLayout(content)
            grid.addLayout(cell, row, col, 1, 2 if wide else 1)
            if wide or col == 1:
                row, col = row + 1, 0
            else:
                col = 1
        if not cells:
            grid.addWidget(QLabel("Nothing here can be edited (only a photo or ID number was generated).",
                                  objectName="hint"), 0, 0, 1, 2)
        grid.setRowStretch(row + 1, 1)
        area.setWidget(form)

    # Read every input back as text, keyed by database column.
    def form_values(self):
        raw = {}
        for key, widget in self.inputs.items():
            if isinstance(widget, QLineEdit):
                raw[key] = widget.text()
            elif isinstance(widget, QComboBox):
                raw[key] = widget.currentText()
            else:
                raw[key] = widget.date().toString("yyyy-MM-dd")
        return raw

    # Invalid input shows the message and keeps the window open; valid input saves and closes.
    def save(self):
        try:
            clean = validate_edits(self.person["fields"], self.form_values())
        except ValueError as err:
            return set_status(self.status, str(err))
        update_person(self.user["id"], self.person_id, clean)
        self.changed.emit()
        self.accept()
