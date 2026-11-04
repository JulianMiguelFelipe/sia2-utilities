from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QScrollArea, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from services.messaging_service import (
    SMS_MAX_LENGTH, MessagingError, clear_messages, connect_gmail, connect_smsgate,
    delete_messages, detect_type, get_messages, get_sms_status, log_message,
    normalize_phone, send_email, send_sms, update_message_status,
)
from ui.styles import GREEN, RED
from ui.widgets import ImageSlot, field_label, make_box, make_button, set_status
from ui.workers import run_in_background

STATUS_COLORS = {"queued": "#bbbbbb", "sent": GREEN, "delivered": GREEN, "failed": RED}
POLL_EVERY_MS = 3000
POLL_MAX_TRIES = 10

def make_input(placeholder="", password=False):
    field = QLineEdit()
    field.setFixedHeight(30)
    field.setPlaceholderText(placeholder)
    if password:
        field.setEchoMode(QLineEdit.Password)
    return field


def friendly(err):
    """Text to show for an error from a background task."""
    return str(err) if isinstance(err, MessagingError) else "Something went wrong. Try again."


class ConnectionBox(QWidget):
    """A white box with a title, a CONNECTED dot, fields, and a CONNECT button."""

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
        self.form.setSpacing(6)

        layout = QVBoxLayout(self.box)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(QLabel(hint, objectName="hint"))
        layout.addSpacing(4)
        layout.addLayout(self.form)
        layout.addSpacing(4)
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


class MessagingPage(QWidget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.gmail = None
        self.smsgate = None
        self.pending = {}

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(POLL_EVERY_MS)
        self.poll_timer.timeout.connect(self.poll_sms_status)

        # ----- Layout -----
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self.build_gmail_box())
        left.addWidget(self.build_smsgate_box())
        left.addWidget(QLabel("Logins are kept in memory only and cleared when you log out.",
                              objectName="hint"))
        left.addStretch()
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(360)

        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(left_widget)
        top.addWidget(self.build_send_box(), stretch=1)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)
        bottom.addWidget(self.build_history_box(), stretch=1)
        art = ImageSlot("sms_art.png", min_width=150, min_height=150)
        art.setFixedWidth(150)
        bottom.addWidget(art)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(18)
        layout.addLayout(top)
        layout.addLayout(bottom, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.refresh_history()
        self.update_recipient_type()

    # ================= GMAIL =================

    def build_gmail_box(self):
        self.gmail_box = ConnectionBox("GMAIL", "For email. Google Account > Security > App passwords")
        self.gmail_address = make_input("yourname@gmail.com")
        self.gmail_password = make_input("16-letter App Password", password=True)
        self.gmail_box.add_field(self.gmail_address, self.gmail_address)
        self.gmail_box.add_field(self.gmail_password, self.gmail_password)
        self.gmail_box.button.clicked.connect(self.toggle_gmail)
        self.gmail_password.returnPressed.connect(self.toggle_gmail)
        return self.gmail_box

    def toggle_gmail(self):
        if self.gmail:
            self.gmail = None
            self.gmail_password.clear()
            self.gmail_box.set_connected(False)
            return
        self.gmail_box.set_busy(True)
        run_in_background(connect_gmail, self.gmail_address.text(), self.gmail_password.text(),
                          on_done=self.gmail_connected, on_error=self.gmail_failed)

    def gmail_connected(self, gmail):
        self.gmail = gmail
        self.gmail_box.set_busy(False)
        self.gmail_box.set_connected(True)

    def gmail_failed(self, err):
        self.gmail_box.set_busy(False)
        self.gmail_box.set_connected(False)
        self.gmail_box.show_error(friendly(err))

    # ================= SMSGATE =================

    def build_smsgate_box(self):
        self.sms_box = ConnectionBox("SMSGATE", "For SMS. Details are on the SMSGate home screen")
        self.sms_ip = make_input("Phone IP, e.g. 192.168.43.1")
        self.sms_port = make_input("Port")
        self.sms_port.setText("8080")
        self.sms_port.setFixedWidth(72)
        address_row = QHBoxLayout()
        address_row.setSpacing(6)
        address_row.addWidget(self.sms_ip, stretch=1)
        address_row.addWidget(QLabel(":", objectName="fieldLabel"))
        address_row.addWidget(self.sms_port)

        self.sms_user = make_input("Username")
        self.sms_password = make_input("Password", password=True)
        self.sms_box.add_field(address_row, self.sms_ip, self.sms_port)
        self.sms_box.add_field(self.sms_user, self.sms_user)
        self.sms_box.add_field(self.sms_password, self.sms_password)
        self.sms_box.button.clicked.connect(self.toggle_smsgate)
        self.sms_password.returnPressed.connect(self.toggle_smsgate)
        return self.sms_box

    def toggle_smsgate(self):
        if self.smsgate:
            self.smsgate = None
            self.sms_password.clear()
            self.sms_box.set_connected(False)
            return
        self.sms_box.set_busy(True)
        run_in_background(connect_smsgate, self.sms_ip.text(), self.sms_port.text(),
                          self.sms_user.text(), self.sms_password.text(),
                          on_done=self.smsgate_connected, on_error=self.smsgate_failed)

    def smsgate_connected(self, config):
        self.smsgate = config
        self.sms_box.set_busy(False)
        self.sms_box.set_connected(True)

    def smsgate_failed(self, err):
        self.sms_box.set_busy(False)
        self.sms_box.set_connected(False)
        self.sms_box.show_error(friendly(err))

    def clear_credentials(self):
        """Called on logout: forget every password and key."""
        self.gmail = None
        self.smsgate = None
        self.poll_timer.stop()
        self.pending.clear()
        for field in (self.gmail_address, self.gmail_password, self.sms_ip,
                      self.sms_user, self.sms_password):
            field.clear()
        self.gmail_box.set_connected(False)
        self.sms_box.set_connected(False)

    # ================= SEND MESSAGE =================

    def build_send_box(self):
        box = make_box()

        self.recipient = make_input("email@example.com or 09171234567")
        self.recipient.textChanged.connect(self.update_recipient_type)
        self.type_badge = QLabel("", objectName="badge")
        self.type_badge.setAlignment(Qt.AlignCenter)
        self.type_badge.setFixedWidth(64)
        to_row = QHBoxLayout()
        to_row.addWidget(self.recipient, stretch=1)
        to_row.addWidget(self.type_badge)

        self.subject = make_input("Email only")

        self.body = QTextEdit()
        self.body.setPlaceholderText("Type your message...")
        self.body.setFixedHeight(100)
        self.body.textChanged.connect(self.update_char_count)
        self.char_count = QLabel("", objectName="hint")

        self.send_btn = make_button("SEND", "primary", width=130)
        self.send_btn.clicked.connect(self.handle_send)
        clear_btn = make_button("CLEAR", "secondary", width=100)
        clear_btn.clicked.connect(self.clear_form)
        self.send_status = QLabel("", objectName="error")
        self.send_status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.send_btn)
        buttons.addWidget(clear_btn)
        buttons.addSpacing(6)
        buttons.addWidget(self.send_status, stretch=1)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 10, 18, 14)
        layout.setSpacing(4)
        layout.addWidget(QLabel("SEND MESSAGE", objectName="sectionTitle"))
        layout.addWidget(QLabel("Type an email to send an email, or a mobile number to send an SMS.",
                                objectName="hint"))
        layout.addSpacing(6)
        layout.addWidget(field_label("SEND TO"))
        layout.addLayout(to_row)
        layout.addSpacing(4)
        layout.addWidget(field_label("SUBJECT"))
        layout.addWidget(self.subject)
        layout.addSpacing(4)
        layout.addWidget(field_label("MESSAGE"))
        layout.addWidget(self.body)
        layout.addWidget(self.char_count, alignment=Qt.AlignRight)
        layout.addLayout(buttons)
        layout.addStretch()
        return box

    def update_recipient_type(self):
        kind = detect_type(self.recipient.text())
        if kind:
            self.type_badge.setText(kind.upper())
            self.type_badge.setStyleSheet(f"border-color: {GREEN}; color: {GREEN};")
        else:
            self.type_badge.setText("?")
            self.type_badge.setStyleSheet("")
        self.subject.setEnabled(kind != "sms")
        self.update_char_count()

    def update_char_count(self):
        count = len(self.body.toPlainText())
        if detect_type(self.recipient.text()) == "sms":
            self.char_count.setText(f"{count} / {SMS_MAX_LENGTH}")
        else:
            self.char_count.setText(f"{count} characters")

    def handle_send(self):
        to = self.recipient.text().strip()
        kind = detect_type(to)
        subject = self.subject.text().strip()
        body = self.body.toPlainText().strip()

        if not kind:
            return set_status(self.send_status,
                              "Enter a valid email or mobile number (09XXXXXXXXX).")
        if not body:
            return set_status(self.send_status, "Type a message first.")
        if kind == "email" and not self.gmail:
            return set_status(self.send_status, "Connect your Gmail first.")
        if kind == "sms" and not self.smsgate:
            return set_status(self.send_status, "Connect SMSGate first.")

        self.send_btn.setEnabled(False)
        self.send_btn.setText("SENDING...")
        self.send_status.clear()

        if kind == "email":
            job = (to, subject, body)
            run_in_background(send_email, self.gmail, to, subject, body,
                              on_done=lambda _: self.email_done(job),
                              on_error=lambda err: self.send_failed("email", job, err))
        else:
            to = normalize_phone(to)
            job = (to, "", body)
            run_in_background(send_sms, self.smsgate, to, body,
                              on_done=lambda result: self.sms_done(job, result),
                              on_error=lambda err: self.send_failed("sms", job, err))

    def finish_sending(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("SEND")

    def email_done(self, job):
        to, subject, body = job
        log_message(self.user["id"], "email", to, subject, body, "sent")
        self.finish_sending()
        set_status(self.send_status, f"Email sent to {to}", success=True)
        self.subject.clear()
        self.body.clear()
        self.refresh_history()

    def sms_done(self, job, result):
        to, _, body = job
        gateway_id, status, error, config = result
        if self.smsgate:
            self.smsgate = config
        row_id = log_message(self.user["id"], "sms", to, "", body, status, gateway_id, error)
        self.finish_sending()
        if status == "failed":
            set_status(self.send_status, f"The phone couldn't send it. {error or ''}".strip())
        else:
            set_status(self.send_status, f"SMS queued on the phone for {to}", success=True)
            self.body.clear()
            if status == "queued" and gateway_id:
                self.pending[row_id] = {"gateway_id": gateway_id, "tries": 0, "checking": False}
                self.poll_timer.start()
        self.refresh_history()

    def send_failed(self, kind, job, err):
        to, subject, body = job
        log_message(self.user["id"], kind, to, subject, body, "failed", error=friendly(err))
        self.finish_sending()
        set_status(self.send_status, friendly(err))
        self.refresh_history()

    def clear_form(self):
        self.recipient.clear()
        self.subject.clear()
        self.body.clear()
        self.send_status.clear()

    # ================= SMS STATUS TRACKING =================

    def poll_sms_status(self):
        """Every few seconds, ask the phone about each QUEUED message."""
        if not self.pending or not self.smsgate:
            self.poll_timer.stop()
            return
        for row_id, info in list(self.pending.items()):
            if info["checking"]:
                continue
            if info["tries"] >= POLL_MAX_TRIES:
                del self.pending[row_id]
                continue
            info["tries"] += 1
            info["checking"] = True
            run_in_background(get_sms_status, self.smsgate, info["gateway_id"],
                              on_done=lambda result, r=row_id: self.status_checked(r, result),
                              on_error=lambda _err, r=row_id: self.status_check_failed(r))

    def status_checked(self, row_id, result):
        status, error = result
        info = self.pending.get(row_id)
        if info is None:
            return
        info["checking"] = False
        if status == "queued":
            return

        if status != info.get("last"):
            update_message_status(row_id, status, error)
            info["last"] = status
            self.refresh_history()
        if status in ("delivered", "failed"):
            del self.pending[row_id]

    def status_check_failed(self, row_id):
        if row_id in self.pending:
            self.pending[row_id]["checking"] = False

    # ================= HISTORY =================

    def build_history_box(self):
        box = make_box()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["DATE", "TYPE", "TO", "MESSAGE", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(150)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.empty_label = QLabel("No messages yet. Sent emails and texts will show up here.",
                                  objectName="hint")

        delete_btn = make_button("DELETE SELECTED", "secondary")
        delete_btn.clicked.connect(self.handle_delete)
        clear_btn = make_button("CLEAR ALL", "primary")
        clear_btn.clicked.connect(self.handle_clear_all)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("HISTORY", objectName="sectionTitle"))
        title_row.addStretch()
        title_row.addWidget(delete_btn)
        title_row.addWidget(clear_btn)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 10, 18, 14)
        layout.addLayout(title_row)
        layout.addWidget(self.table)
        layout.addWidget(self.empty_label)
        return box

    def refresh_history(self):
        rows = get_messages(self.user["id"])
        self.table.setRowCount(len(rows))
        self.empty_label.setVisible(not rows)
        for r, msg in enumerate(rows):
            preview = msg["body"].replace("\n", " ")
            if msg["subject"]:
                preview = f"[{msg['subject']}] {preview}"
            values = [msg["sent_at"], msg["type"].upper(), msg["recipient"],
                      preview, msg["status"].upper()]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, msg["id"])
                if c == 4:
                    item.setForeground(QColor(STATUS_COLORS.get(msg["status"], "#ffffff")))
                    if msg["error"]:
                        item.setToolTip(msg["error"])
                    elif msg["status"] == "queued":
                        item.setToolTip("Waiting for the phone to send it")
                self.table.setItem(r, c, item)

    def handle_delete(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return
        ids = [self.table.item(r, 0).data(Qt.UserRole) for r in rows]
        for row_id in ids:
            self.pending.pop(row_id, None)
        delete_messages(self.user["id"], ids)
        self.refresh_history()

    def handle_clear_all(self):
        if self.table.rowCount() == 0:
            return
        answer = QMessageBox.question(self, "JD UTILS", "Delete your whole message history?")
        if answer == QMessageBox.Yes:
            self.pending.clear()
            clear_messages(self.user["id"])
            self.refresh_history()
