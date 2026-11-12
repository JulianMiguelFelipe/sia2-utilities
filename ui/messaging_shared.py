"""Pieces shared by the three SMS & EMAIL sub-tabs (COMPOSE, SMS CHAT, EMAIL INBOX).

Connections holds the live Gmail and SMSGate logins in memory so all three tabs
use the same ones. SmsStatusTracker keeps asking the phone about texts that are
still queued until they become delivered or failed. ConnectionBox is the
EMAIL / SMS login box with its status dot and CONNECT button.
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from services.messaging_service import MessagingError, get_sms_status, update_message_status
from ui.widgets import make_box, make_button
from ui.workers import run_in_background

# Check queued texts every 5 seconds, up to 24 times (2 minutes) each.
POLL_EVERY_MS = 5000
POLL_MAX_TRIES = 24


def make_input(placeholder="", password=False):
    field = QLineEdit()
    field.setFixedHeight(28)
    field.setPlaceholderText(placeholder)
    if password:
        field.setEchoMode(QLineEdit.Password)
    return field


# MessagingError messages are written for the user; anything else gets a general message.
def friendly(err):
    return str(err) if isinstance(err, MessagingError) else "Something went wrong. Try again."


# Database time -> short label: "3:41 PM" today, "Yesterday", "Mar 5", or a full date.
def friendly_time(value):
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


# The active logins, shared by every sub-tab. "changed" tells the tabs and the status
# dots to update whenever a login connects or disconnects.
class Connections(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.gmail = None
        self.smsgate = None

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


# SMS status tracking. When SMSGate accepts a text it is only "queued"; the phone sends
# it a moment later. Every 5 seconds this asks the phone for the new status, updates
# the history, and stops once the text is delivered or failed.
class SmsStatusTracker(QObject):
    updated = Signal()

    def __init__(self, connections):
        super().__init__()
        self.conn = connections
        self.pending = {}
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
        # "checking" skips a text whose last check hasn't answered yet, so slow replies
        # don't pile up.
        for row_id, info in list(self.pending.items()):
            if info["checking"]:
                continue
            if info["tries"] >= POLL_MAX_TRIES:
                del self.pending[row_id]
                continue
            info["tries"] += 1
            info["checking"] = True
            # Each check runs in the background; r=row_id freezes the current row id inside the lambda.
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
        # Only write to the database and refresh the screen when the status actually changed.
        if status != info.get("last"):
            update_message_status(row_id, status, error)
            info["last"] = status
            self.updated.emit()
        if status in ("delivered", "failed"):
            del self.pending[row_id]

    def check_failed(self, row_id):
        if row_id in self.pending:
            self.pending[row_id]["checking"] = False


# A login box: title, CONNECTED / NOT CONNECTED dot, input fields, CONNECT button and
# an error line. Fields are locked while connected so the login can't change mid-session.
class ConnectionBox(QWidget):
    def __init__(self, title, hint):
        super().__init__()
        self.box = make_box()
        self.dot = QLabel("", objectName="dotOff")
        self.button = make_button("CONNECT", "primary", width=130)
        self.error = QLabel("", objectName="error")
        self.error.setWordWrap(True)
        self.error.hide()
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
        layout.addSpacing(10)
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
