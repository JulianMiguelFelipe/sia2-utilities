"""Feature 2: download the fake data HISTORY as an Excel (.xlsx) file using openpyxl.

One row per person and one column per field. Fields that were turned off are
left blank. The header row is red, frozen and has filter buttons.
"""

from openpyxl import Workbook
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from services.fake_data_service import age_from, format_id, format_mobile, full_name, shows_id

FONT = "Arial"
RED = "E02424"
NOTE = "Fake data made with JD UTILS · not real people"

# (column header, how to get the value from a person). Changing this list changes the file.
TABLE_COLUMNS = [
    ("ID No.", lambda p: format_id(p["id_number"]) if shows_id(p) else None),
    ("Name", full_name),
    ("Sex", lambda p: p.get("sex")),
    ("Birthdate", lambda p: p.get("birthdate")),
    ("Age", lambda p: age_from(p["birthdate"]) if p.get("birthdate") else None),
    ("Civil status", lambda p: p.get("civil_status")),
    ("Blood type", lambda p: p.get("blood_type")),
    ("Nationality", lambda p: p.get("nationality")),
    ("Height (cm)", lambda p: p.get("height_cm")),
    ("Weight (kg)", lambda p: p.get("weight_kg")),
    ("Occupation", lambda p: p.get("occupation")),
    ("Address", lambda p: p.get("address")),
    ("Mobile", lambda p: format_mobile(p.get("mobile")) or None),
    ("Email", lambda p: p.get("email")),
    ("Emergency contact", lambda p: p.get("emergency_name")),
    ("Emergency mobile", lambda p: format_mobile(p.get("emergency_phone")) or None),
    ("Issued", lambda p: p.get("issued_on")),
    ("Valid until", lambda p: p.get("valid_until")),
    ("Photo", lambda p: "Yes" if p.get("has_photo") else "No"),
    ("Created", lambda p: p.get("created_at")),
]


def export_table_xlsx(people, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Fake data"
    line = Side(style="thin", color="000000")
    for c, (header, _) in enumerate(TABLE_COLUMNS, start=1):
        cell = ws.cell(1, c, header)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=RED)
        cell.border = Border(bottom=line)

    # Track the longest value in each column to size the columns afterwards (max 45).
    widths = [len(h) for h, _ in TABLE_COLUMNS]
    for r, person in enumerate(people, start=2):
        for c, (_, get) in enumerate(TABLE_COLUMNS, start=1):
            value = get(person)
            cell = ws.cell(r, c, value)
            cell.font = Font(name=FONT)
            widths[c - 1] = max(widths[c - 1], len(str(value or "")))

    for c, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = min(width + 2, 45)
    # Keep the header visible while scrolling, and add Excel's filter dropdowns.
    ws.freeze_panes = "A2"
    if people:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(TABLE_COLUMNS))}{len(people) + 1}"
    ws.cell(len(people) + 3, 1, NOTE).font = Font(name=FONT, italic=True, color="888888")
    wb.save(path)
