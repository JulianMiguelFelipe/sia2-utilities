"""Feature 3: COMPOSE sub-tab. Connect Gmail and SMSGate, send a message, see the history.

One SEND TO box handles both kinds of message: an email address sends an email,
a mobile number sends an SMS (detect_type decides). Logins are saved to the
user's account after a successful CONNECT and reconnect automatically at the
next login (services/saved_logins_service.py). Every send is logged in the
messages table, and queued texts are handed to the status tracker.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from services.saved_logins_service import (
    forget_gmail, forget_smsgate, load_logins, save_gmail, save_smsgate,
)
from services.messaging_service import (
    clear_messages, connect_gmail, connect_smsgate, delete_messages,
    detect_type, failure_reason, get_messages, log_message, normalize_phone, send_email,
    send_sms, sms_counter_text,
)
from ui.theme import colors, status_color, theme_events
from ui.messaging_shared import ConnectionBox, friendly, make_input
from ui.widgets import field_label, make_box, make_button, set_status
from ui.workers import run_in_background
from ui.signals import connect_alive


class ComposeTab(QWidget):
    sent_something = Signal()

    def __init__(self, user, connections, tracker):
        super().__init__()
        self.user = user
        self.conn = connections
        self.tracker = tracker
        # When the tracker gets a new SMS status, refresh the history so the color updates.
        tracker.updated.connect(self.refresh_history)
        connect_alive(theme_events.changed, self,
                      lambda _t: (self.refresh_history(), self.update_recipient_type()))

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self.build_gmail_box())
        left.addWidget(self.build_smsgate_box())
        left.addStretch()
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(360)

        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(left_widget)
        top.addWidget(self.build_send_box(), stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 8)
        layout.setSpacing(10)
        layout.addLayout(top, stretch=0)
        layout.addWidget(self.build_history_box(), stretch=1)

        self.refresh_history()
        self.update_recipient_type()
        self.restore_saved_logins()

    # The logins live in the shared Connections object, so all three sub-tabs see them.
    # These properties make self.gmail / self.smsgate read and write that shared object.
    @property
    def gmail(self):
        return self.conn.gmail

    @gmail.setter
    def gmail(self, value):
        self.conn.set_gmail(value)

    @property
    def smsgate(self):
        return self.conn.smsgate

    @smsgate.setter
    def smsgate(self, value):
        self.conn.set_smsgate(value)

    def build_gmail_box(self):
        self.gmail_box = ConnectionBox("EMAIL", "Your Gmail address and its 16-letter App Password")
        self.gmail_address = make_input("yourname@gmail.com")
        self.gmail_password = make_input("16-letter App Password", password=True)
        self.gmail_box.add_field(self.gmail_address, self.gmail_address)
        self.gmail_box.add_field(self.gmail_password, self.gmail_password)
        self.gmail_box.button.clicked.connect(self.toggle_gmail)
        self.gmail_password.returnPressed.connect(self.toggle_gmail)
        return self.gmail_box

    # One button for both: DISCONNECT when connected, CONNECT otherwise.
    # DISCONNECT also deletes the saved login from the database.
    def toggle_gmail(self):
        if self.gmail:
            self.gmail = None
            forget_gmail(self.user["id"])
            self.gmail_password.clear()
            self.gmail_box.set_connected(False)
            return
        # Connecting means a real login to Gmail, which takes a moment, so it runs in the background.
        self.gmail_box.set_busy(True)
        run_in_background(connect_gmail, self.gmail_address.text(), self.gmail_password.text(),
                          on_done=self.gmail_connected, on_error=self.gmail_failed)

    # Login worked: share it with the other tabs and save it (encrypted) to the account.
    def gmail_connected(self, gmail):
        self.gmail = gmail
        save_gmail(self.user["id"], self.user["key"], *gmail)
        self.gmail_box.set_busy(False)
        self.gmail_box.set_connected(True)

    def gmail_failed(self, err):
        self.gmail_box.set_busy(False)
        self.gmail_box.set_connected(False)
        self.gmail_box.show_error(friendly(err))

    def build_smsgate_box(self):
        self.sms_box = ConnectionBox("SMS", "Phone IP and port, or api.sms-gate.app and 443 for cloud")
        self.sms_ip = make_input("Phone IP or api.sms-gate.app")
        self.sms_port = make_input("Port")
        self.sms_port.setText("8080")
        self.sms_port.setFixedWidth(72)
        address_row = QHBoxLayout()
        address_row.setSpacing(8)
        address_row.addWidget(self.sms_ip, stretch=1)
        address_row.addWidget(QLabel(":", objectName="fieldLabel"))
        address_row.addWidget(self.sms_port)

        # Username and password share one row, like IP : port, so the SMS box is the same
        # height as the EMAIL box and nothing gets squeezed.
        self.sms_user = make_input("Username")
        self.sms_password = make_input("Password", password=True)
        login_row = QHBoxLayout()
        login_row.setSpacing(8)
        login_row.addWidget(self.sms_user, stretch=1)
        login_row.addWidget(self.sms_password, stretch=1)
        self.sms_box.add_field(address_row, self.sms_ip, self.sms_port)
        self.sms_box.add_field(login_row, self.sms_user, self.sms_password)
        self.sms_box.button.clicked.connect(self.toggle_smsgate)
        self.sms_password.returnPressed.connect(self.toggle_smsgate)
        return self.sms_box

    def toggle_smsgate(self):
        if self.smsgate:
            self.smsgate = None
            forget_smsgate(self.user["id"])
            self.sms_password.clear()
            self.sms_box.set_connected(False)
            return
        self.sms_box.set_busy(True)
        run_in_background(connect_smsgate, self.sms_ip.text(), self.sms_port.text(),
                          self.sms_user.text(), self.sms_password.text(),
                          on_done=self.smsgate_connected, on_error=self.smsgate_failed)

    def smsgate_connected(self, config):
        self.smsgate = config
        # Save what the user typed for IP and port, so the boxes look the same next time.
        save_smsgate(self.user["id"], self.user["key"], self.sms_ip.text().strip(),
                     self.sms_port.text().strip(), config.username, config.password)
        self.sms_box.set_busy(False)
        self.sms_box.set_connected(True)

    def smsgate_failed(self, err):
        self.sms_box.set_busy(False)
        self.sms_box.set_connected(False)
        self.sms_box.show_error(friendly(err))

    # Runs when the tab is built (right after login): fill in the saved logins and
    # connect them. If the phone's IP changed, the box shows the error and the user
    # can fix it.
    def restore_saved_logins(self):
        saved = load_logins(self.user["id"], self.user["key"])
        if saved.get("gmail_password"):
            self.gmail_address.setText(saved["gmail_address"])
            self.gmail_password.setText(saved["gmail_password"])
            self.toggle_gmail()
        if saved.get("sms_password"):
            self.sms_ip.setText(saved["sms_ip"])
            self.sms_port.setText(saved["sms_port"])
            self.sms_user.setText(saved["sms_username"])
            self.sms_password.setText(saved["sms_password"])
            self.toggle_smsgate()

    # Logout: clear the boxes. The saved logins stay in the database.
    def clear_credentials(self):
        for field in (self.gmail_address, self.gmail_password, self.sms_ip,
                      self.sms_user, self.sms_password):
            field.clear()
        self.gmail_box.set_connected(False)
        self.sms_box.set_connected(False)

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
        self.body.setFixedHeight(70)
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
        return box

    # Live badge next to SEND TO: EMAIL, SMS, or ? while the recipient isn't valid yet.
    # The subject box is disabled for SMS because texts have no subject.
    def update_recipient_type(self):
        kind = detect_type(self.recipient.text())
        if kind:
            self.type_badge.setText(kind.upper())
            green = colors()["green"]
            self.type_badge.setStyleSheet(f"border-color: {green}; color: {green};")
        else:
            self.type_badge.setText("?")
            self.type_badge.setStyleSheet("")
        self.subject.setEnabled(kind != "sms")
        self.update_char_count()

    def update_char_count(self):
        count = len(self.body.toPlainText())
        if detect_type(self.recipient.text()) == "sms":
            self.char_count.setText(sms_counter_text(self.body.toPlainText()))
        else:
            self.char_count.setText(f"{count} characters")

    def handle_send(self):
        to = self.recipient.text().strip()
        kind = detect_type(to)
        subject = self.subject.text().strip()
        body = self.body.toPlainText().strip()

        # Check everything before sending, with a clear message for each problem.
        if not kind:
            return set_status(self.send_status,
                              "Enter a valid email or mobile number (09XXXXXXXXX).")
        if not body:
            return set_status(self.send_status, "Type a message first.")
        if kind == "email" and not self.gmail:
            return set_status(self.send_status, "Connect EMAIL first.")
        if kind == "sms" and not self.smsgate:
            return set_status(self.send_status, "Connect SMS first.")

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

    # SMSGate replied. The config may come back with a different API path; keep it. A
    # queued text goes to the status tracker, which follows it until delivered or failed.
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
                self.tracker.track(row_id, gateway_id)
        self.refresh_history()
        self.sent_something.emit()

    # Failed sends are logged too, with the reason shown as a tooltip in the history.
    def send_failed(self, kind, job, err):
        to, subject, body = job
        log_message(self.user["id"], kind, to, subject, body, "failed", error=friendly(err))
        self.finish_sending()
        set_status(self.send_status, friendly(err))
        self.refresh_history()
        self.sent_something.emit()

    def clear_form(self):
        self.recipient.clear()
        self.subject.clear()
        self.body.clear()
        self.send_status.clear()

    def build_history_box(self):
        box = make_box()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["DATE", "TYPE", "TO", "MESSAGE", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        # Room for the header and at least 4 messages at the default window size.
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
        layout.setContentsMargins(18, 8, 18, 10)
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
            status = msg["status"].upper()
            if msg["status"] == "failed" and msg["error"]:
                status += f" · {failure_reason(msg['error'])}"
            values = [msg["sent_at"], msg["type"].upper(), msg["recipient"], preview, status]
            for c, value in enumerate(values):
                # Each cell remembers its database id; the STATUS cell is colored by status.
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, msg["id"])
                if c == 4:
                    item.setForeground(QColor(status_color(msg["status"])))
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
        # Stop tracking deleted texts so the tracker doesn't write to rows that are gone.
        self.tracker.forget(ids)
        delete_messages(self.user["id"], ids)
        self.refresh_history()
        self.sent_something.emit()

    def handle_clear_all(self):
        if self.table.rowCount() == 0:
            return
        answer = QMessageBox.question(self, "JD UTILS", "Delete your whole message history?")
        if answer == QMessageBox.Yes:
            self.tracker.forget()
            clear_messages(self.user["id"])
            self.refresh_history()
            self.sent_something.emit()
