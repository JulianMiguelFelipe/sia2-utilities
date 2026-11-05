"""EMAIL INBOX sub-tab: read and reply to Gmail."""

import html
import re
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTextBrowser,
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
    """Shorten text with an ellipsis."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


URL_PATTERN = re.compile(r"(https?://[^\s<>\"]+)")
QUOTE_START = re.compile(r"^On .{4,200}wrote:\s*$")


def _paragraphs_html(lines, color, size):
    """Lines to paragraphs with links."""
    out, block = [], []
    for line in lines + [""]:
        if line.strip():
            block.append(URL_PATTERN.sub(r"<a href='\1'>\1</a>", html.escape(line)))
        elif block:
            out.append(f"<p style='color:{color}; font-size:{size}px; margin-bottom:{size}px'>"
                       + "<br>".join(block) + "</p>")
            block = []
    return "".join(out)


def format_email_body(text):
    """Style the email and its quoted part."""
    s, p = current_scale(), colors()
    lines = text.replace("\r\n", "\n").split("\n")
    for i in range(len(lines) - 1):          # Gmail sometimes splits "On ... wrote:" in two
        joined = f"{lines[i].strip()} {lines[i + 1].strip()}"
        if lines[i].startswith("On ") and not QUOTE_START.match(lines[i].strip()) \
                and QUOTE_START.match(joined):
            lines[i:i + 2] = [joined, ""]
            break
    cut = next((i for i, line in enumerate(lines)
                if QUOTE_START.match(line.strip()) or line.startswith(">")), len(lines))
    main, quoted = lines[:cut], lines[cut:]
    body = _paragraphs_html(main, p["fg"], round(14 * s)) or \
        f"<p style='color:{p['muted']}'>(No message text)</p>"
    if quoted:
        header = quoted[0].strip() if QUOTE_START.match(quoted[0].strip()) else ""
        rest = quoted[1:] if header else quoted
        rest = [re.sub(r"^>\s?", "", line) for line in rest]
        while rest and not rest[-1].strip():
            rest.pop()
        small = round(12.5 * s)
        inner = (f"<p style='color:{p['muted']}; font-size:{small}px; font-weight:700'>"
                 f"{html.escape(header)}</p>" if header else "")
        inner += _paragraphs_html(rest, p["muted"], small)
        body += (f"<table width='100%' cellspacing='0' cellpadding='{round(12 * s)}' "
                 f"bgcolor='{p['surface']}' style='margin-top:{round(8 * s)}px'>"
                 f"<tr><td>{inner}</td></tr></table>")
    return body


class EmailInboxTab(QWidget):
    """EMAIL INBOX sub-tab."""
    unread_changed = Signal(int)

    def __init__(self, user, connections):
        """Build the tab."""
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
        connect_alive(theme_events.changed, self, lambda _t: (self.show_list(), self.render_body()))
        connect_alive(scale_events.changed, self, lambda _s: self.render_body())
        self.connection_changed()

    # ---------- Toolbar ----------
    def build_toolbar(self):
        """Search, filter and REFRESH."""
        self.search = make_input("Search sender or subject")
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self.show_list)
        self.only_ours = QAction("Email Inbox: only people I emailed", self)  # in the gear menu
        self.only_ours.setCheckable(True)
        self.only_ours.setChecked(True)
        self.only_ours.toggled.connect(self.restart)
        self.filter_note = QLabel("", objectName="hint")
        self.updated = QLabel("", objectName="hint")
        self.refresh_btn = make_button("REFRESH", "secondary")
        self.refresh_btn.clicked.connect(self.load)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.search)
        row.addWidget(self.filter_note)
        row.addStretch()
        row.addWidget(self.updated)
        row.addWidget(self.refresh_btn)
        return row

    # ---------- Left: the list ----------
    def build_list_box(self):
        """INBOX list box."""
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
        """Gmail connected or not."""
        if self.conn.gmail:
            self.timer.start()
            self.restart()
        else:
            self.timer.stop()
            self.forget()
            self.list_note.setText("EMAIL isn't connected. Connect it in COMPOSE to see your inbox.")

    def restart(self):
        """Reload from the first page."""
        self.limit = PAGE_SIZE
        self.show_list()                    # update the 'Showing:' line
        self.load()

    def load_more(self):
        """LOAD MORE button."""
        self.limit += PAGE_SIZE
        self.load()

    def load(self):
        """Load emails in the background."""
        if not self.conn.gmail or self.loading:
            return
        only = emailed_addresses(self.user["id"]) if self.only_ours.isChecked() else None
        self.loading = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("LOADING...")
        run_in_background(fetch_inbox, self.conn.gmail, self.limit, only,
                          on_done=self.loaded, on_error=self.load_failed)

    def finish_loading(self):
        """Reset the REFRESH button."""
        self.loading = False
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("REFRESH")

    def loaded(self, result):
        """Emails loaded."""
        self.finish_loading()
        if not self.conn.gmail:                        # disconnected while loading
            return
        self.emails, self.has_more = result
        self.updated.setText(f"Updated {friendly_time(datetime.now())}")
        self.show_list()

    def load_failed(self, err):
        """Loading failed."""
        self.finish_loading()
        self.list_note.setText(friendly(err))

    def show_list(self):
        """Draw the email list."""
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

        self.filter_note.setText("Showing: only people you emailed through JD UTILS"
                                 if self.only_ours.isChecked() else "Showing: all emails")
        unread = sum(e["unread"] for e in self.emails)
        self.list_title.setText(f"INBOX · {unread} UNREAD" if unread else "INBOX")
        self.more_btn.setVisible(self.has_more)
        if not self.conn.gmail:
            self.list_note.setText("EMAIL isn't connected. Connect it in COMPOSE to see your inbox.")
        elif not self.emails and self.only_ours.isChecked():
            self.list_note.setText("No emails from people you emailed through JD UTILS yet. "
                                   "Turn off the filter in Settings (gear) to see everything.")
        elif not self.emails:
            self.list_note.setText("Your inbox is empty.")
        elif not shown:
            self.list_note.setText("No emails match your search.")
        else:
            self.list_note.setText("")
        self.unread_changed.emit(unread)

    @staticmethod
    def item_html(e):
        """One email in the list."""
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

    # ---------- Right: reading + replying ----------
    def build_reader_box(self):
        """Email reader and reply box."""
        box = make_box()

        # Header: subject, then [avatar] name <address> ........ date
        self.subject = QLabel("", objectName="emailSubject")
        self.subject.setWordWrap(True)
        self.avatar = QLabel("", objectName="avatar")
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setFixedSize(38, 38)
        self.sender_name = QLabel("", objectName="emailSender")
        self.sender_address = QLabel("", objectName="hint")
        self.to_line = QLabel("", objectName="hint")
        self.date_line = QLabel("", objectName="hint")
        self.attachments = QLabel("", objectName="attachments")
        self.attachments.setWordWrap(True)

        who = QVBoxLayout()
        who.setSpacing(1)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(self.sender_name)
        name_row.addWidget(self.sender_address)
        name_row.addStretch()
        name_row.addWidget(self.date_line, alignment=Qt.AlignTop)
        who.addLayout(name_row)
        who.addWidget(self.to_line)
        sender_row = QHBoxLayout()
        sender_row.setSpacing(12)
        sender_row.addWidget(self.avatar, alignment=Qt.AlignTop)
        sender_row.addLayout(who, stretch=1)

        head = QVBoxLayout()
        head.setContentsMargins(20, 14, 20, 12)
        head.setSpacing(10)
        head.addWidget(self.subject)
        head.addLayout(sender_row)
        head.addWidget(self.attachments)
        head_box = QWidget(objectName="chatHeader")
        head_box.setLayout(head)

        # Body: formatted text, quoted earlier messages in a grey box
        self.body = QTextBrowser(objectName="emailBody")
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))

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
        """Open an email."""
        if not self.conn.gmail:
            return
        self.subject.setText("Opening...")
        run_in_background(open_email, self.conn.gmail, uid,
                          on_done=self.show_email,
                          on_error=lambda err: self.subject.setText(friendly(err)))

    def show_email(self, email):
        """Show an email in the reader."""
        self.opened = email
        if email is None:
            self.subject.setText("EMAIL INBOX")
            self.avatar.hide()
            self.sender_name.setText("Pick an email on the left to read it here.")
            for label in (self.sender_address, self.to_line, self.date_line):
                label.setText("")
            self.attachments.hide()
            self.body.setHtml("")
            self.foot_box.setEnabled(False)
            self.reply_to.setText("")
            return
        self.subject.setText(email["subject"])
        self.avatar.setText((email["name"] or email["address"] or "?")[:1].upper())
        self.avatar.show()
        self.sender_name.setText(email["name"])
        self.sender_address.setText(f"<{email['address']}>" if email["name"] != email["address"] else "")
        self.to_line.setText(f"to {email['to']}")
        self.date_line.setText(email["date"].strftime("%b %d, %Y \u00b7 %I:%M %p")
                               if email["date"] else "")
        if email["attachments"]:
            self.attachments.setText("ATTACHMENTS (listed only, not downloaded)   "
                                     + "   \u00b7   ".join(email["attachments"]))
            self.attachments.show()
        else:
            self.attachments.hide()
        self.render_body()
        self.foot_box.setEnabled(True)
        self.reply_to.setText(f"To {email['address']} · {reply_subject(email['subject'])}")
        self.reply_status.setText("Your reply joins the same Gmail conversation.")
        for e in self.emails:                           # opening marks it read
            if e["uid"] == email["uid"]:
                e["unread"] = False
        self.show_list()

    def render_body(self):
        """Draw the email text."""
        if not self.opened:
            return
        self.body.document().setDefaultStyleSheet(f"a {{ color: {colors()['red']}; }}")
        self.body.setHtml(format_email_body(self.opened["body"]))

    def send_reply(self):
        """SEND REPLY button."""
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
        """Reset the SEND REPLY button."""
        self.sending = False
        self.send_btn.setEnabled(True)
        self.send_btn.setText("SEND REPLY")

    def reply_sent(self, email, subject, text):
        """Reply sent."""
        log_message(self.user["id"], "email", email["address"], subject, text, "sent")
        self.finish_sending()
        self.reply.clear()
        set_status(self.reply_status, f"Reply sent to {email['address']}", success=True)

    def reply_failed(self, email, subject, text, err):
        """Reply failed."""
        log_message(self.user["id"], "email", email["address"], subject, text, "failed",
                    error=friendly(err))
        self.finish_sending()
        set_status(self.reply_status, friendly(err))

    # ---------- Logout ----------
    def forget(self):
        """Clear loaded emails."""
        self.emails = []
        self.has_more = False
        self.reply.clear()
        self.updated.setText("")
        self.show_email(None)
        self.show_list()

    def clear_credentials(self):
        """Stop and clear (logout)."""
        self.timer.stop()
        self.forget()
