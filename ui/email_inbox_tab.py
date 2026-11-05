"""
ui/email_inbox_tab.py
EMAIL INBOX sub-tab: read your Gmail inbox and reply, using the same Gmail +
App Password as COMPOSE.

  Top:   search, "Only people I emailed through JD UTILS" filter, REFRESH
  Left:  the newest emails (unread in bold with a red dot), LOAD MORE
  Right: the open email (attachments listed by name only) and a reply box

Nothing is saved: emails are loaded from Gmail while you're connected and
forgotten on logout. Only replies you send are added to the history log.
"""

import html
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from services.email_inbox_service import (
    PAGE_SIZE, emailed_addresses, fetch_inbox, open_email, quote_original, reply_subject,
)
from services.messaging_service import log_message, send_email
from ui.messaging_shared import friendly, friendly_time, make_input
from ui.scaling import current_scale, scale_events
from ui.theme import colors, theme_events
from ui.widgets import make_box, make_button, set_status
from ui.workers import run_in_background
from ui.signals import connect_alive

AUTO_REFRESH_MS = 60_000          # check for new mail every minute


def _short(text, limit=40):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class EmailInboxTab(QWidget):
    unread_changed = Signal(int)

    def __init__(self, user, connections):
        super().__init__()
        self.user = user
        self.conn = connections
        self.emails = []           # the loaded list (memory only)
        self.limit = PAGE_SIZE
        self.has_more = False
        self.loading = False
        self.opened = None         # the email shown on the right
        self.sending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        layout.addLayout(self.build_toolbar())
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self.build_list_box())
        body.addWidget(self.build_reader_box(), stretch=1)
        layout.addLayout(body, stretch=1)

        self.timer = QTimer(self)
        self.timer.setInterval(AUTO_REFRESH_MS)
        self.timer.timeout.connect(self.load)

        connections.changed.connect(self.connection_changed)
        connect_alive(scale_events.changed, self, lambda _s: self.show_list())
        connect_alive(theme_events.changed, self, lambda _t: self.show_list())
        self.connection_changed()

    # ================= Toolbar =================

    def build_toolbar(self):
        self.search = make_input("Search sender or subject")
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self.show_list)
        self.only_ours = QCheckBox("Only people I emailed through JD UTILS")
        self.only_ours.setChecked(True)
        self.only_ours.toggled.connect(self.restart)
        self.updated = QLabel("", objectName="hint")
        self.refresh_btn = make_button("REFRESH", "secondary")
        self.refresh_btn.clicked.connect(self.load)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.search)
        row.addWidget(self.only_ours)
        row.addStretch()
        row.addWidget(self.updated)
        row.addWidget(self.refresh_btn)
        return row

    # ================= Left: the list =================

    def build_list_box(self):
        box = make_box()
        box.setFixedWidth(340)
        self.list_title = QLabel("INBOX", objectName="sectionTitle")
        self.list = QListWidget(objectName="itemList")
        self.list.itemClicked.connect(lambda item: self.open(item.data(Qt.UserRole)))
        self.list_note = QLabel("", objectName="hint")
        self.list_note.setWordWrap(True)
        self.more_btn = make_button("LOAD MORE", "secondary")
        self.more_btn.clicked.connect(self.load_more)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self.list_title)
        layout.addWidget(self.list, stretch=1)
        layout.addWidget(self.list_note)
        layout.addWidget(self.more_btn)
        return box

    def connection_changed(self):
        if self.conn.gmail:
            self.timer.start()
            self.restart()
        else:
            self.timer.stop()
            self.forget()
            self.list_note.setText("EMAIL isn't connected. Connect it in COMPOSE to see your inbox.")

    def restart(self):
        self.limit = PAGE_SIZE
        self.load()

    def load_more(self):
        self.limit += PAGE_SIZE
        self.load()

    def load(self):
        if not self.conn.gmail or self.loading:
            return
        only = emailed_addresses(self.user["id"]) if self.only_ours.isChecked() else None
        self.loading = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("LOADING...")
        run_in_background(fetch_inbox, self.conn.gmail, self.limit, only,
                          on_done=self.loaded, on_error=self.load_failed)

    def finish_loading(self):
        self.loading = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("REFRESH")

    def loaded(self, result):
        self.finish_loading()
        if not self.conn.gmail:                        # disconnected while loading
            return
        self.emails, self.has_more = result
        self.updated.setText(f"Updated {friendly_time(datetime.now())}")
        self.show_list()

    def load_failed(self, err):
        self.finish_loading()
        self.list_note.setText(friendly(err))

    def show_list(self):
        query = self.search.text().strip().lower()
        shown = [e for e in self.emails
                 if not query or query in e["name"].lower() or query in e["address"].lower()
                 or query in e["subject"].lower()]
        self.list.clear()
        for e in shown:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, e["uid"])
            label = QLabel(self.item_html(e))
            label.setTextFormat(Qt.RichText)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            pad = round(8 * current_scale())
            label.setContentsMargins(pad + 2, pad, pad + 2, pad)
            self.list.addItem(item)
            self.list.setItemWidget(item, label)
            label.ensurePolished()                        # apply the stylesheet font first
            lines = 2
            height = lines * QFontMetrics(label.font()).lineSpacing() + 2 * pad
            item.setSizeHint(QSize(0, height + round(12 * current_scale())))
            if self.opened and e["uid"] == self.opened["uid"]:
                item.setSelected(True)

        unread = sum(e["unread"] for e in self.emails)
        self.list_title.setText(f"INBOX · {unread} UNREAD" if unread else "INBOX")
        self.more_btn.setVisible(self.has_more)
        if not self.conn.gmail:
            self.list_note.setText("EMAIL isn't connected. Connect it in COMPOSE to see your inbox.")
        elif not self.emails and self.only_ours.isChecked():
            self.list_note.setText("No emails from people you emailed through JD UTILS yet. "
                                   "Untick the filter to see everything.")
        elif not self.emails:
            self.list_note.setText("Your inbox is empty.")
        elif not shown:
            self.list_note.setText("No emails match your search.")
        else:
            self.list_note.setText("")
        self.unread_changed.emit(unread)

    @staticmethod
    def item_html(e):
        p = colors()
        dot = f"<span style='color:{p['red']}'>● </span>" if e["unread"] else ""
        name = html.escape(_short(e["name"], 26))
        subject = html.escape(_short(e["subject"]))
        when = friendly_time(e["date"]) if e["date"] else ""
        subject_style = f"color:{p['fg']}; font-weight:700" if e["unread"] else f"color:{p['muted']}"
        return (f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
                f"<td>{dot}<b>{name}</b></td>"
                f"<td align='right'><span style='color:{p['muted']}'>{when}</span></td></tr></table>"
                f"<span style='{subject_style}'>{subject}</span>")

    # ================= Right: reading + replying =================

    def build_reader_box(self):
        box = make_box()
        self.subject = QLabel("", objectName="sectionTitle")
        self.subject.setWordWrap(True)
        self.from_line = QLabel("", objectName="infoText")
        self.to_line = QLabel("", objectName="hint")
        self.attachments = QLabel("", objectName="hint")
        self.attachments.setWordWrap(True)

        head = QVBoxLayout()
        head.setContentsMargins(18, 12, 18, 10)
        head.setSpacing(3)
        head.addWidget(self.subject)
        head.addWidget(self.from_line)
        head.addWidget(self.to_line)
        head.addWidget(self.attachments)
        head_box = QWidget(objectName="chatHeader")
        head_box.setLayout(head)

        self.body = QTextBrowser(objectName="chatView")
        self.body.setOpenLinks(False)

        self.reply_to = QLabel("", objectName="hint")
        self.reply = QTextEdit()
        self.reply.setPlaceholderText("Type your reply...")
        self.reply.setFixedHeight(64)
        self.send_btn = make_button("SEND REPLY", "primary", width=130)
        self.send_btn.clicked.connect(self.send_reply)
        clear_btn = make_button("CLEAR", "secondary", width=100)
        clear_btn.clicked.connect(self.reply.clear)
        self.reply_status = QLabel("", objectName="hint")
        self.reply_status.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.send_btn)
        buttons.addWidget(clear_btn)
        buttons.addSpacing(6)
        buttons.addWidget(self.reply_status, stretch=1)

        title = QHBoxLayout()
        title.addWidget(QLabel("REPLY", objectName="fieldLabel"))
        title.addStretch()
        title.addWidget(self.reply_to)
        foot = QVBoxLayout()
        foot.setContentsMargins(18, 10, 18, 12)
        foot.setSpacing(6)
        foot.addLayout(title)
        foot.addWidget(self.reply)
        foot.addLayout(buttons)
        self.foot_box = QWidget(objectName="chatFooter")
        self.foot_box.setLayout(foot)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(head_box)
        layout.addWidget(self.body, stretch=1)
        layout.addWidget(self.foot_box)
        self.show_email(None)
        return box

    def open(self, uid):
        if not self.conn.gmail:
            return
        self.subject.setText("Opening...")
        run_in_background(open_email, self.conn.gmail, uid,
                          on_done=self.show_email,
                          on_error=lambda err: self.subject.setText(friendly(err)))

    def show_email(self, email):
        self.opened = email
        if email is None:
            self.subject.setText("EMAIL INBOX")
            self.from_line.setText("Pick an email on the left to read it here.")
            self.to_line.setText("")
            self.attachments.hide()
            self.body.setPlainText("")
            self.foot_box.setEnabled(False)
            self.reply_to.setText("")
            return
        when = email["date"].strftime("%b %d, %Y, %I:%M %p") if email["date"] else ""
        self.subject.setText(email["subject"])
        self.from_line.setText(f"From  {email['name']} <{email['address']}>")
        self.to_line.setText(f"To  {email['to']} · {when}")
        if email["attachments"]:
            self.attachments.setText("Attachments (listed only, not downloaded):  "
                                     + ",  ".join(email["attachments"]))
            self.attachments.show()
        else:
            self.attachments.hide()
        self.body.setPlainText(email["body"])          # plain text only: no images, no scripts
        self.foot_box.setEnabled(True)
        self.reply_to.setText(f"To {email['address']} · {reply_subject(email['subject'])}")
        self.reply_status.setText("Your reply joins the same Gmail conversation.")
        for e in self.emails:                           # opening marks it read
            if e["uid"] == email["uid"]:
                e["unread"] = False
        self.show_list()

    def send_reply(self):
        email, text = self.opened, self.reply.toPlainText().strip()
        if not email or self.sending:
            return
        if not text:
            return set_status(self.reply_status, "Type a reply first.")
        if not self.conn.gmail:
            return set_status(self.reply_status, "Connect EMAIL in COMPOSE first.")
        self.sending = True
        self.send_btn.setEnabled(False)
        self.send_btn.setText("SENDING...")
        subject = reply_subject(email["subject"])
        full_body = text + quote_original(email)
        run_in_background(send_email, self.conn.gmail, email["address"], subject, full_body,
                          email["message_id"] or None, email["references"] or None,
                          on_done=lambda _: self.reply_sent(email, subject, text),
                          on_error=lambda err: self.reply_failed(email, subject, text, err))

    def finish_sending(self):
        self.sending = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText("SEND REPLY")

    def reply_sent(self, email, subject, text):
        log_message(self.user["id"], "email", email["address"], subject, text, "sent")
        self.finish_sending()
        self.reply.clear()
        set_status(self.reply_status, f"Reply sent to {email['address']}", success=True)

    def reply_failed(self, email, subject, text, err):
        log_message(self.user["id"], "email", email["address"], subject, text, "failed",
                    error=friendly(err))
        self.finish_sending()
        set_status(self.reply_status, friendly(err))

    # ================= Logout =================

    def forget(self):
        self.emails = []
        self.has_more = False
        self.reply.clear()
        self.updated.setText("")
        self.show_email(None)
        self.show_list()

    def clear_credentials(self):
        self.timer.stop()
        self.forget()
