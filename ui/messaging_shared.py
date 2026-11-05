"""Shared by the SMS & Email sub-tabs: logins, SMS status, connection box."""

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from services.messaging_service import MessagingError, get_sms_status, update_message_status
from ui.widgets import make_box, make_button
from ui.workers import run_in_background

POLL_EVERY_MS = 5000          # check SMS status every 5 seconds...
POLL_MAX_TRIES = 24           # ...for up to 2 minutes


def make_input(placeholder="", password=False):
    """Text field (password optional)."""
    field = QLineEdit()
    field.setFixedHeight(28)
    field.setPlaceholderText(placeholder)
    if password:
        field.setEchoMode(QLineEdit.Password)
    return field


def friendly(err):
    """Error text to show."""
    return str(err) if isinstance(err, MessagingError) else "Something went wrong. Try again."


def friendly_time(value):
    """Short date or time."""
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
    """Shared Gmail and SMSGate logins."""

    changed = Signal()

    def __init__(self):
        """Start disconnected."""
        super().__init__()
        self.gmail = None        # (address, app_password)
        self.smsgate = None      # SmsGateConfig

    def set_gmail(self, gmail):
        """Set the Gmail login."""
        self.gmail = gmail
        self.changed.emit()

    def set_smsgate(self, config):
        """Set the SMSGate login."""
        self.smsgate = config
        self.changed.emit()

    def clear(self):
        """Forget both logins."""
        self.gmail = None
        self.smsgate = None
        self.changed.emit()


class SmsStatusTracker(QObject):
    """Follows QUEUED texts until final."""

    updated = Signal()           # a status changed in the database

    def __init__(self, connections):
        """Start the tracker."""
        super().__init__()
        self.conn = connections
        self.pending = {}        # message row id -> {"gateway_id", "tries", "checking", "last"}
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_EVERY_MS)
        self.timer.timeout.connect(self.poll)

    def track(self, row_id, gateway_id):
        """Start following a text."""
        self.pending[row_id] = {"gateway_id": gateway_id, "tries": 0, "checking": False}
        self.timer.start()

    def forget(self, row_ids=None):
        """Stop following texts."""
        if row_ids is None:
            self.pending.clear()
        for row_id in row_ids or []:
            self.pending.pop(row_id, None)

    def stop(self):
        """Stop everything."""
        self.timer.stop()
        self.pending.clear()

    def poll(self):
        """Ask the phone about each text."""
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
        """Status received."""
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
        """Status check failed."""
        if row_id in self.pending:
            self.pending[row_id]["checking"] = False     # try again next tick


class ConnectionBox(QWidget):
    """Connection box with CONNECT button."""

    def __init__(self, title, hint):
        """Build the box."""
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
        """Add a field."""
        if isinstance(widget_or_layout, QWidget):
            self.form.addWidget(widget_or_layout)
        else:
            self.form.addLayout(widget_or_layout)
        self.fields.extend(fields)

    def set_connected(self, connected):
        """Show connected or not."""
        self.dot.setObjectName("dotOn" if connected else "dotOff")
        self.dot.style().polish(self.dot)
        self.dot.setText("● CONNECTED" if connected else "● NOT CONNECTED")
        self.button.setText("DISCONNECT" if connected else "CONNECT")
        for field in self.fields:
            field.setEnabled(not connected)
        if connected:
            self.show_error("")

    def show_error(self, text):
        """Show or hide the error."""
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def set_busy(self, busy):
        """Show CONNECTING..."""
        self.button.setEnabled(not busy)
        if busy:
            self.button.setText("CONNECTING...")
            self.show_error("")
