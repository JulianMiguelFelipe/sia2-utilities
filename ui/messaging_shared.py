"""
ui/messaging_shared.py
Pieces shared by the three SMS & EMAIL UI sub-tabs (COMPOSE, SMS CHAT, EMAIL INBOX).

  Connections      - the Gmail and SMSGate logins, kept in memory only.
                     All three sub-tabs read the same object, so you connect once.
  SmsStatusTracker - asks the phone every few seconds what happened to each
                     QUEUED text and updates the database (SENT / DELIVERED / FAILED).
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from services.messaging_service import MessagingError, get_sms_status, update_message_status
from ui.widgets import make_box, make_button
from ui.workers import run_in_background

POLL_EVERY_MS = 3000          # check SMS status every 3 seconds...
POLL_MAX_TRIES = 10           # ...for up to 30 seconds


def make_input(placeholder="", password=False):
    field = QLineEdit()
    field.setFixedHeight(28)
    field.setPlaceholderText(placeholder)
    if password:
        field.setEchoMode(QLineEdit.Password)
    return field


def friendly(err):
    """Text to show for an error from a background task."""
    return str(err) if isinstance(err, MessagingError) else "Something went wrong. Try again."


def friendly_time(value):
    """'7:32 AM' today, 'Yesterday', 'Nov 3' this year, else '2025-11-03'.
    Accepts our 'YYYY-MM-DD HH:MM:SS' text or a datetime."""
    if not value:
        return ""
    when = value if isinstance(value, datetime) else datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    when = when.replace(tzinfo=None)
    today = datetime.now().date()
    if when.date() == today:
        return when.strftime("%I:%M %p").lstrip("0")
    if when.date() == today - timedelta(days=1):
        return "Yesterday"
    if when.year == today.year:
        return f"{when.strftime('%b')} {when.day}"
    return when.strftime("%Y-%m-%d")


class Connections(QObject):
    """The logins. `changed` fires whenever one connects or disconnects."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.gmail = None        # (address, app_password)
        self.smsgate = None      # SmsGateConfig

    def set_gmail(self, gmail):
        self.gmail = gmail
        self.changed.emit()

    def set_smsgate(self, config):
        self.smsgate = config
        self.changed.emit()

    def clear(self):
        self.gmail = None
        self.smsgate = None
        self.changed.emit()


class SmsStatusTracker(QObject):
    """Follows each QUEUED text until the phone says SENT, DELIVERED or FAILED."""

    updated = Signal()           # a status changed in the database

    def __init__(self, connections):
        super().__init__()
        self.conn = connections
        self.pending = {}        # message row id -> {"gateway_id", "tries", "checking", "last"}
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_EVERY_MS)
        self.timer.timeout.connect(self.poll)

    def track(self, row_id, gateway_id):
        self.pending[row_id] = {"gateway_id": gateway_id, "tries": 0, "checking": False}
        self.timer.start()

    def forget(self, row_ids=None):
        if row_ids is None:
            self.pending.clear()
        for row_id in row_ids or []:
            self.pending.pop(row_id, None)

    def stop(self):
        self.timer.stop()
        self.pending.clear()

    def poll(self):
        if not self.pending or not self.conn.smsgate:
            self.timer.stop()
            return
        for row_id, info in list(self.pending.items()):
            if info["checking"]:
                continue
            if info["tries"] >= POLL_MAX_TRIES:           # give up; stays as it is
                del self.pending[row_id]
                continue
            info["tries"] += 1
            info["checking"] = True
            run_in_background(get_sms_status, self.conn.smsgate, info["gateway_id"],
                              on_done=lambda result, r=row_id: self.checked(r, result),
                              on_error=lambda _err, r=row_id: self.check_failed(r))

    def checked(self, row_id, result):
        status, error = result
        info = self.pending.get(row_id)
        if info is None:
            return
        info["checking"] = False
        if status == "queued":
            return
        # SENT: keep checking in case a delivery report arrives.
        # DELIVERED / FAILED: final, stop checking.
        if status != info.get("last"):
            update_message_status(row_id, status, error)
            info["last"] = status
            self.updated.emit()
        if status in ("delivered", "failed"):
            del self.pending[row_id]

    def check_failed(self, row_id):
        if row_id in self.pending:
            self.pending[row_id]["checking"] = False     # try again next tick


class ConnectionBox(QWidget):
    """A white box with a title, a CONNECTED dot, fields, and a CONNECT button."""

    def __init__(self, title, hint):
        super().__init__()
        self.box = make_box()
        self.dot = QLabel("", objectName="dotOff")
        self.button = make_button("CONNECT", "primary", width=130)
        self.error = QLabel("", objectName="error")
        self.error.setWordWrap(True)
        self.error.hide()                 # only shown when there's an error
        self.fields = []

        header = QHBoxLayout()
        header.addWidget(QLabel(title, objectName="sectionTitle"))
        header.addStretch()
        header.addWidget(self.dot)

        self.form = QVBoxLayout()
        self.form.setSpacing(8)

        layout = QVBoxLayout(self.box)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(3)
        layout.addLayout(header)
        layout.addWidget(QLabel(hint, objectName="hint"))
        layout.addSpacing(2)
        layout.addLayout(self.form)
        layout.addSpacing(10)                   # gap above the CONNECT button
        layout.addWidget(self.button, alignment=Qt.AlignLeft)
        layout.addWidget(self.error)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.box)
        self.set_connected(False)

    def add_field(self, widget_or_layout, *fields):
        if isinstance(widget_or_layout, QWidget):
            self.form.addWidget(widget_or_layout)
        else:
            self.form.addLayout(widget_or_layout)
        self.fields.extend(fields)

    def set_connected(self, connected):
        self.dot.setObjectName("dotOn" if connected else "dotOff")
        self.dot.style().polish(self.dot)
        self.dot.setText("● CONNECTED" if connected else "● NOT CONNECTED")
        self.button.setText("DISCONNECT" if connected else "CONNECT")
        for field in self.fields:
            field.setEnabled(not connected)
        if connected:
            self.show_error("")

    def show_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def set_busy(self, busy):
        self.button.setEnabled(not busy)
        if busy:
            self.button.setText("CONNECTING...")
            self.show_error("")