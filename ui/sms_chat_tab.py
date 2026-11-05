"""
ui/sms_chat_tab.py
SMS CHAT sub-tab: a messaging app for texts sent through SMSGate.

  Left:  conversations (numbers you've texted), unread dots, search, + NEW CHAT
  Right: chat bubbles (yours on the right in white, theirs on the left in grey),
         RENAME / DELETE CHAT, and a message box (Enter sends).

Every 5 seconds the app asks the phone for new texts (GET /inbox) and keeps
only replies from numbers you texted (the PRIVACY FILTER in sms_chat_service.py).
"""

import html

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from services.messaging_service import (
    SMS_MAX_LENGTH, get_sms_inbox, log_message, normalize_phone, send_sms,
)
from services.sms_chat_service import (
    delete_conversation, ensure_contact, first_sent_times, get_thread, inbox_since_utc,
    list_conversations, mark_read, rename_contact, save_incoming,
)
from ui.messaging_shared import friendly, friendly_time, make_input
from ui.scaling import current_scale, scale_events
from ui.theme import colors, status_color, theme_events
from ui.widgets import make_box, make_button, set_status
from ui.workers import run_in_background
from ui.signals import connect_alive

INBOX_CHECK_MS = 5000


def _short(text, limit=34):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class SmsChatTab(QWidget):
    unread_changed = Signal(int)

    def __init__(self, user, connections, tracker):
        super().__init__()
        self.user = user
        self.conn = connections
        self.tracker = tracker
        self.current = None              # phone number of the open chat
        self.checking_inbox = False
        self.inbox_unsupported = False
        self.sending = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)
        layout.addWidget(self.build_list_box())
        layout.addWidget(self.build_chat_box(), stretch=1)

        self.inbox_timer = QTimer(self)
        self.inbox_timer.setInterval(INBOX_CHECK_MS)
        self.inbox_timer.timeout.connect(self.check_inbox)

        connections.changed.connect(self.connection_changed)
        tracker.updated.connect(self.refresh)
        connect_alive(scale_events.changed, self, lambda _s: self.refresh())
        connect_alive(theme_events.changed, self, lambda _t: self.refresh())
        self.connection_changed()
        self.refresh()

    # ================= LEFT: conversations =================

    def build_list_box(self):
        box = make_box()
        box.setFixedWidth(300)

        self.search = make_input("Search name or number")
        self.search.textChanged.connect(self.refresh_list)

        self.list = QListWidget(objectName="itemList")
        self.list.itemClicked.connect(lambda item: self.open_chat(item.data(Qt.UserRole)))
        self.empty_list = QLabel("No chats yet. Start one below, or send an SMS from COMPOSE.",
                                 objectName="hint")
        self.empty_list.setWordWrap(True)

        self.new_number = make_input("New number, e.g. 09171234567")
        self.new_number.returnPressed.connect(self.start_new_chat)
        new_btn = make_button("+ NEW CHAT", "secondary")
        new_btn.clicked.connect(self.start_new_chat)
        self.list_status = QLabel("", objectName="error")
        self.list_status.setWordWrap(True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel("CONVERSATIONS", objectName="sectionTitle"))
        layout.addWidget(self.search)
        layout.addWidget(self.list, stretch=1)
        layout.addWidget(self.empty_list)
        layout.addWidget(self.new_number)
        layout.addWidget(new_btn)
        layout.addWidget(self.list_status)
        return box

    def refresh_list(self):
        convos = list_conversations(self.user["id"])
        query = self.search.text().strip().lower()
        if query:
            convos = [c for c in convos
                      if query in c["phone"] or query in (c["name"] or "").lower()]
        self.list.clear()
        self.empty_list.setVisible(not convos)
        for c in convos:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c["phone"])
            label = QLabel(self.list_item_html(c))
            label.setTextFormat(Qt.RichText)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)   # clicks go to the list
            pad = round(8 * current_scale())
            label.setContentsMargins(pad + 2, pad, pad + 2, pad)
            self.list.addItem(item)
            self.list.setItemWidget(item, label)
            label.ensurePolished()                        # apply the stylesheet font first
            lines = 3 if c["name"] else 2
            height = lines * QFontMetrics(label.font()).lineSpacing() + 2 * pad
            item.setSizeHint(QSize(0, height + round(12 * current_scale())))
            if c["phone"] == self.current:
                item.setSelected(True)
        total = sum(c["unread"] for c in list_conversations(self.user["id"]))
        self.unread_changed.emit(total)

    @staticmethod
    def list_item_html(c):
        p = colors()
        name = html.escape(c["name"] or c["phone"])
        when = friendly_time(c["last_at"])
        dot = f"<span style='color:{p['red']}'>● </span>" if c["unread"] else ""
        number = f"<br><span style='color:{p['muted']}'>{c['phone']}</span>" if c["name"] else ""
        if not c["last_text"]:
            preview = f"<span style='color:{p['muted2']}'>No messages yet</span>"
        else:
            text = html.escape(_short(c["last_text"]))
            text = f"You: {text}" if c["last_mine"] else text
            color = p["fg"] if c["unread"] else p["muted"]
            weight = "700" if c["unread"] else "400"
            preview = f"<span style='color:{color}; font-weight:{weight}'>{text}</span>"
        return (f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
                f"<td>{dot}<b>{name}</b></td>"
                f"<td align='right'><span style='color:{p['muted']}'>{when}</span></td></tr></table>"
                f"{number}<br>{preview}")

    def start_new_chat(self):
        phone = normalize_phone(self.new_number.text())
        if not phone:
            return set_status(self.list_status, "Enter a valid mobile number (09XXXXXXXXX).")
        self.list_status.clear()
        self.new_number.clear()
        ensure_contact(self.user["id"], phone)
        self.open_chat(phone)
        self.message.setFocus()

    # ================= RIGHT: the chat =================

    def build_chat_box(self):
        box = make_box()

        self.title = QLabel("", objectName="sectionTitle")
        self.subtitle = QLabel("", objectName="hint")
        self.rename_btn = make_button("RENAME", "secondary")
        self.rename_btn.clicked.connect(self.rename)
        self.delete_btn = make_button("DELETE CHAT", "primary")
        self.delete_btn.clicked.connect(self.delete_chat)

        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.title)
        names.addWidget(self.subtitle)
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 10)
        header.addLayout(names, stretch=1)
        header.addWidget(self.rename_btn)
        header.addWidget(self.delete_btn)
        header_box = QWidget(objectName="chatHeader")
        header_box.setLayout(header)

        self.view = QTextBrowser(objectName="chatView")
        self.view.setOpenLinks(False)

        self.message = make_input("Type a message... (Enter to send)")
        self.message.setFixedHeight(34)
        self.message.setMaxLength(SMS_MAX_LENGTH)
        self.message.returnPressed.connect(self.send)
        self.message.textChanged.connect(self.update_counter)
        self.send_btn = make_button("SEND", "primary", width=110)
        self.send_btn.setFixedHeight(34)
        self.send_btn.clicked.connect(self.send)
        send_row = QHBoxLayout()
        send_row.addWidget(self.message, stretch=1)
        send_row.addWidget(self.send_btn)

        self.status = QLabel("", objectName="hint")
        self.status.setWordWrap(True)
        self.counter = QLabel(f"0 / {SMS_MAX_LENGTH}", objectName="hint")
        footer = QHBoxLayout()
        footer.addWidget(self.status, stretch=1)
        footer.addWidget(self.counter, alignment=Qt.AlignTop)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(16, 10, 16, 10)
        bottom.setSpacing(6)
        bottom.addLayout(send_row)
        bottom.addLayout(footer)
        bottom_box = QWidget(objectName="chatFooter")
        bottom_box.setLayout(bottom)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(header_box)
        layout.addWidget(self.view, stretch=1)
        layout.addWidget(bottom_box)
        return box

    def open_chat(self, phone):
        self.current = phone
        mark_read(self.user["id"], phone)
        self.refresh()

    def refresh(self):
        self.refresh_list()
        self.refresh_chat()

    def refresh_chat(self):
        has_chat = self.current is not None
        for w in (self.rename_btn, self.delete_btn, self.message, self.send_btn):
            w.setEnabled(has_chat and not self.sending)
        if not has_chat:
            self.title.setText("SMS CHAT")
            self.subtitle.setText("Pick a conversation, or start a new chat.")
            self.view.setHtml(self.empty_html("Your conversations will show up here."))
            return

        name = next((c["name"] for c in list_conversations(self.user["id"])
                     if c["phone"] == self.current), None)
        self.title.setText(name or self.current)
        self.subtitle.setText(self.current if name else "Tap RENAME to give this number a name")
        texts = get_thread(self.user["id"], self.current)
        self.view.setHtml(self.thread_html(texts) if texts
                          else self.empty_html("No messages yet. Say hi!"))
        QTimer.singleShot(0, lambda: self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum()))

    @staticmethod
    def empty_html(text):
        size = round(13 * current_scale())
        return (f"<div style='color:{colors()['muted2']}; font-size:{size}px' align='center'>"
                f"<br><br>{html.escape(text)}</div>")

    def thread_html(self, texts):
        s, p = current_scale(), colors()
        body, small, pad = round(13 * s), round(10.5 * s), round(8 * s)
        parts, last_day = [], None
        for t in texts:
            day = t["at"][:10]
            if day != last_day:
                label = friendly_time(t["at"][:10] + " 00:00:00")
                label = "TODAY" if ":" in label else label.upper()
                parts.append(f"<p align='center' style='color:{p['muted']}; font-size:{small}px;"
                             f" font-weight:800'>{label}</p>")
                last_day = day
            text = html.escape(t["body"]).replace("\n", "<br>")
            time = friendly_time(t["at"])
            time = time if ":" in time else t["at"][11:16]
            if t["mine"]:
                color = status_color(t["status"])
                meta = f"{t['status'].upper()} · {time}"
                parts.append(
                    f"<table align='right' cellspacing='0' cellpadding='{pad}' "
                    f"style='margin-left:{round(80 * s)}px' bgcolor='{p['alt_bg']}'>"
                    f"<tr><td style='color:{p['alt_fg']}; font-size:{body}px'>{text}</td></tr></table>"
                    f"<p align='right' style='margin-top:{round(3 * s)}px; color:{color};"
                    f" font-size:{small}px; font-weight:800'>{meta}</p>")
            else:
                parts.append(
                    f"<table align='left' cellspacing='0' cellpadding='{pad}' "
                    f"style='margin-right:{round(80 * s)}px' bgcolor='{p['bubble_in']}'>"
                    f"<tr><td style='color:{p['fg']}; font-size:{body}px'>{text}</td></tr></table>"
                    f"<p align='left' style='margin-top:{round(3 * s)}px; color:{p['muted']};"
                    f" font-size:{small}px; font-weight:800'>{time}</p>")
        return "".join(parts)

    def update_counter(self):
        self.counter.setText(f"{len(self.message.text())} / {SMS_MAX_LENGTH}")

    # ================= Sending =================

    def send(self):
        body = self.message.text().strip()
        if not self.current or not body or self.sending:
            return
        if not self.conn.smsgate:
            return set_status(self.status, "Connect SMS in COMPOSE first.")
        self.sending = True
        self.send_btn.setText("SENDING...")
        self.refresh_chat()
        phone = self.current
        run_in_background(send_sms, self.conn.smsgate, phone, body,
                          on_done=lambda result: self.sent(phone, body, result),
                          on_error=lambda err: self.send_failed(phone, body, err))

    def finish_sending(self):
        self.sending = False
        self.send_btn.setText("SEND")

    def sent(self, phone, body, result):
        gateway_id, status, error, config = result
        if self.conn.smsgate:
            self.conn.smsgate = config               # remember the API path that worked
        row_id = log_message(self.user["id"], "sms", phone, "", body, status, gateway_id, error)
        if status == "queued" and gateway_id:
            self.tracker.track(row_id, gateway_id)
        self.finish_sending()
        self.message.clear()
        self.show_listening_status()
        self.refresh()
        self.message.setFocus()

    def send_failed(self, phone, body, err):
        log_message(self.user["id"], "sms", phone, "", body, "failed", error=friendly(err))
        self.finish_sending()
        set_status(self.status, friendly(err))
        self.refresh()

    # ================= Rename / delete =================

    def rename(self):
        if not self.current:
            return
        name, ok = QInputDialog.getText(self, "Rename", f"Name for {self.current}:",
                                        text=self.title.text() if self.title.text() != self.current else "")
        if ok:
            rename_contact(self.user["id"], self.current, name[:40])
            self.refresh()

    def delete_chat(self):
        if not self.current:
            return
        answer = QMessageBox.question(
            self, "JD UTILS",
            f"Delete this chat with {self.title.text()}?\n"
            "It's removed from JD UTILS only; the texts stay on the phone.")
        if answer == QMessageBox.Yes:
            delete_conversation(self.user["id"], self.current)
            self.current = None
            self.refresh()

    # ================= Receiving replies =================

    def connection_changed(self):
        if self.conn.smsgate:
            self.inbox_unsupported = False
            self.inbox_timer.start()
            self.check_inbox()
        else:
            self.inbox_timer.stop()
        self.show_listening_status()

    def show_listening_status(self):
        if not self.conn.smsgate:
            set_status(self.status, "SMS isn't connected. Connect it in COMPOSE to send and receive.")
        elif self.inbox_unsupported:
            set_status(self.status, "This SMSGate version can't share replies. Update the SMSGate app.")
        else:
            self.status.setObjectName("hint")
            self.status.style().polish(self.status)
            self.status.setText("Checking for replies every 5 seconds. "
                                "Only replies from numbers you texted here are shown.")

    def check_inbox(self):
        if not self.conn.smsgate or self.checking_inbox or self.inbox_unsupported:
            return
        first_sent = first_sent_times(self.user["id"])
        if not first_sent:
            return                                     # we haven't texted anyone yet
        self.checking_inbox = True
        run_in_background(get_sms_inbox, self.conn.smsgate, inbox_since_utc(first_sent),
                          on_done=lambda texts: self.inbox_received(texts, first_sent),
                          on_error=self.inbox_failed)

    def inbox_received(self, texts, first_sent):
        self.checking_inbox = False
        new = save_incoming(self.user["id"], texts, first_sent)
        if new:
            if self.current and self.isVisible():
                mark_read(self.user["id"], self.current)
            self.refresh()
        self.show_listening_status()

    def inbox_failed(self, err):
        self.checking_inbox = False
        if "can't share received texts" in friendly(err):
            self.inbox_unsupported = True
        self.show_listening_status()

    def showEvent(self, event):
        super().showEvent(event)
        if self.current:                               # opening the tab reads the open chat
            mark_read(self.user["id"], self.current)
        self.refresh()

    def clear_credentials(self):
        self.inbox_timer.stop()
        self.current = None
        self.message.clear()
