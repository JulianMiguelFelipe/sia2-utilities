"""Feature 3: SMS CHAT sub-tab, a messenger-style view of text conversations.

Left: the conversation list with unread dots and search. Right: the chat bubbles
and a reply box. While SMS is connected, the phone's inbox is checked every 5
seconds for replies (services/sms_chat_service.py decides what gets saved).
Bubbles are built as HTML in a QTextBrowser, so their colors and sizes follow
the theme and window scale.
"""

import html
import re
from urllib.parse import quote

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QSystemTrayIcon, QTextBrowser, QToolTip, QVBoxLayout, QWidget,
)

from app_paths import ICON_PATH
from services.messaging_service import (
    SMS_MAX_LENGTH, delete_messages, failure_reason, get_sms_inbox, log_message,
    normalize_phone, send_sms, sms_counter_text,
)
from services.sms_chat_service import (
    delete_conversation, delete_received, ensure_contact, everyone_since_utc,
    first_sent_times, get_thread, inbox_since_utc, list_conversations, mark_read,
    rename_contact, save_incoming,
)
from ui.messaging_shared import friendly, friendly_time, make_input
from ui.scaling import current_scale, scale_events
from ui.theme import colors, status_color, theme_events
from ui.widgets import make_box, make_button, set_status
from ui.workers import run_in_background
from ui.signals import connect_alive

INBOX_CHECK_MS = 5000
# Every 12th check (about once a minute) also asks SMSGate to re-read the phone's SMS.
REFRESH_EVERY = 12


def _short(text, limit=34):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class SmsChatTab(QWidget):
    unread_changed = Signal(int)
    # Asks the dashboard to bring this tab to the front (clicking a notification).
    show_requested = Signal()

    def __init__(self, user, connections, tracker):
        super().__init__()
        self.user = user
        self.conn = connections
        self.tracker = tracker
        self.current = None
        self.checking_inbox = False
        self.inbox_checks = 0
        self.inbox_error = ""
        self.inbox_unsupported = False
        self.sending = False
        # Texts from numbers outside JD UTILS. Kept in memory only, never saved.
        self.outside = {}
        self.seen_outside = set()
        self.hidden = set()
        self.hidden_keys = set()
        # href of every bubble in the open chat -> its message, for right-click and RESEND.
        self.bubbles = {}
        self.tray = None
        self.notified_phone = None

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
        # Rebuild the list and bubbles when the window rescales or the theme changes,
        # since their sizes and colors are written into the HTML.
        connect_alive(scale_events.changed, self, lambda _s: self.refresh())
        connect_alive(theme_events.changed, self, lambda _t: self.refresh())
        self.connection_changed()
        self.refresh()

    def build_list_box(self):
        box = make_box()
        box.setFixedWidth(300)

        # This option lives in the gear menu (dashboard.py) but is owned here.
        self.only_ours = QAction("SMS Chat: only people I texted", self)
        self.only_ours.setCheckable(True)
        self.only_ours.setChecked(True)
        self.only_ours.toggled.connect(self.filter_changed)
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

    # Saved conversations plus the in-memory texts from outside numbers.
    def conversations(self):
        convos = {c["phone"]: c for c in list_conversations(self.user["id"])}
        for t in sorted(self.outside.values(), key=lambda t: t["at"]):
            c = convos.setdefault(t["phone"], {"phone": t["phone"], "name": None, "unread": 0,
                                               "last_at": "", "outside": True})
            if t["at"] >= (c.get("last_at") or ""):
                c.update(last_text=t["body"], last_at=t["at"], last_mine=False)
            if t["key"] not in self.seen_outside:
                c["unread"] += 1
        return sorted(convos.values(), key=lambda c: c["last_at"] or "9999", reverse=True)

    def refresh_list(self):
        convos = self.conversations()
        query = self.search.text().strip().lower()
        if query:
            # Search works with names, "+639..." or "09..." (a leading 0 is turned into 63).
            digits = re.sub(r"\D", "", query)
            if digits.startswith("0"):
                digits = "63" + digits[1:]
            convos = [c for c in convos
                      if query in (c["name"] or "").lower() or query in c["phone"].lower()
                      or (digits and digits in re.sub(r"\D", "", c["phone"]))]
        self.list.clear()
        self.empty_list.setVisible(not convos)
        for c in convos:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, c["phone"])
            # Each list row is a QLabel with rich text so it can mix bold names, gray numbers
            # and a red unread dot.
            label = QLabel(self.list_item_html(c))
            label.setTextFormat(Qt.RichText)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            pad = round(8 * current_scale())
            label.setContentsMargins(pad + 2, pad, pad + 2, pad)
            self.list.addItem(item)
            self.list.setItemWidget(item, label)
            label.ensurePolished()
            lines = 3 if c["name"] or c.get("outside") else 2
            height = lines * QFontMetrics(label.font()).lineSpacing() + 2 * pad
            item.setSizeHint(QSize(0, height + round(12 * current_scale())))
            if c["phone"] == self.current:
                item.setSelected(True)
        self.unread_changed.emit(sum(c["unread"] for c in self.conversations()))

    @staticmethod
    # HTML for one conversation row: name, time, number and a preview of the last text.
    def list_item_html(c):
        p = colors()
        name = html.escape(c["name"] or c["phone"])
        when = friendly_time(c["last_at"])
        dot = f"<span style='color:{p['red']}'>● </span>" if c["unread"] else ""
        number = f"<br><span style='color:{p['muted']}'>{c['phone']}</span>" if c["name"] else ""
        if c.get("outside") and not c["name"]:
            number = f"<br><span style='color:{p['muted']}'>Not saved \u00b7 outside JD UTILS</span>"
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

        # Every bubble is a link (msg:...) so a right-click can tell which message it is.
        # setOpenLinks(False): clicks come to link_clicked instead of opening anything.
        self.view = QTextBrowser(objectName="chatView")
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self.link_clicked)
        self.view.highlighted.connect(self.link_hovered)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.message_menu)

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
        self.counter = QLabel(sms_counter_text(""), objectName="hint")
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

    # Opening a chat marks it as read, which clears its unread dot and badge.
    def open_chat(self, phone):
        self.current = phone
        if normalize_phone(phone):
            mark_read(self.user["id"], phone)
        self.seen_outside.update(k for k, t in self.outside.items() if t["phone"] == phone)
        self.refresh()

    def refresh(self):
        self.refresh_list()
        self.refresh_chat()

    def refresh_chat(self):
        has_chat = self.current is not None
        can_reply = has_chat and normalize_phone(self.current) is not None
        for w in (self.rename_btn, self.message, self.send_btn):
            w.setEnabled(can_reply and not self.sending)
        self.delete_btn.setEnabled(has_chat and not self.sending)
        if not has_chat:
            self.title.setText("SMS CHAT")
            self.subtitle.setText("Pick a conversation, or start a new chat.")
            self.view.setHtml(self.empty_html("Your conversations will show up here."))
            return

        name = next((c["name"] for c in self.conversations() if c["phone"] == self.current), None)
        self.title.setText(name or self.current)
        if not can_reply:
            self.subtitle.setText("This sender can't receive replies")
        else:
            self.subtitle.setText(self.current if name else "Tap RENAME to give this number a name")
        texts = get_thread(self.user["id"], self.current)
        texts += [t for t in self.outside.values() if t["phone"] == self.current]
        texts.sort(key=lambda t: (t["at"], -t["mine"]))
        self.view.setHtml(self.thread_html(texts) if texts
                          else self.empty_html("No messages yet. Say hi!"))
        # Scroll to the newest message after Qt finishes laying out the HTML.
        QTimer.singleShot(0, lambda: self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum()))

    @staticmethod
    def empty_html(text):
        size = round(13 * current_scale())
        return (f"<div style='color:{colors()['muted2']}; font-size:{size}px' align='center'>"
                f"<br><br>{html.escape(text)}</div>")

    # Chat bubbles: mine on the right (with the status color and time), theirs on the left,
    # with a date label whenever the day changes.
    def thread_html(self, texts):
        s, p = current_scale(), colors()
        body, small, pad = round(13 * s), round(10.5 * s), round(8 * s)
        parts, last_day = [], None
        self.bubbles = {}
        for t in texts:
            day = t["at"][:10]
            if day != last_day:
                label = friendly_time(t["at"][:10] + " 00:00:00")
                label = "TODAY" if ":" in label else label.upper()
                parts.append(f"<p align='center' style='color:{p['muted']}; font-size:{small}px;"
                             f" font-weight:800'>{label}</p>")
                last_day = day
            time = friendly_time(t["at"])
            time = time if ":" in time else t["at"][11:16]
            if t["mine"]:
                href = f"msg:sent:{t['id']}"
            elif t.get("outside"):
                href = f"msg:out:{quote(t['key'], safe='')}"
            else:
                href = f"msg:recv:{t['id']}"
            self.bubbles[href] = t
            fg = p["alt_fg"] if t["mine"] else p["fg"]
            text = (f"<a href='{href}' style='color:{fg}; text-decoration:none'>"
                    f"{html.escape(t['body']).replace(chr(10), '<br>')}</a>")
            if t["mine"]:
                color = status_color(t["status"])
                meta = f"{t['status'].upper()} · {time}"
                # Failed texts say why, and get a RESEND link that sends the same text again.
                if t["status"] == "failed":
                    reason = failure_reason(t.get("error"))
                    meta = f"FAILED · {reason} · {time}" if reason else meta
                    meta += (f" &nbsp;<a href='resend:{t['id']}' style='color:{p['fg']};"
                             f" text-decoration:underline'>RESEND</a>")
                parts.append(
                    f"<table align='right' cellspacing='0' cellpadding='{pad}' "
                    f"style='margin-left:{round(80 * s)}px' bgcolor='{p['alt_bg']}'>"
                    f"<tr><td style='color:{p['alt_fg']}; font-size:{body}px'>{text}</td></tr></table>"
                    f"<p align='right' style='margin-top:{round(3 * s)}px; color:{color};"
                    f" font-size:{small}px; font-weight:800'>{meta}</p>")
            else:
                not_saved = " \u00b7 NOT SAVED" if t.get("outside") else ""
                parts.append(
                    f"<table align='left' cellspacing='0' cellpadding='{pad}' "
                    f"style='margin-right:{round(80 * s)}px' bgcolor='{p['bubble_in']}'>"
                    f"<tr><td style='color:{p['fg']}; font-size:{body}px'>{text}</td></tr></table>"
                    f"<p align='left' style='margin-top:{round(3 * s)}px; color:{p['muted']};"
                    f" font-size:{small}px; font-weight:800'>{time}{not_saved}</p>")
        return "".join(parts)

    def update_counter(self):
        self.counter.setText(sms_counter_text(self.message.text()))

    # Replying from the chat uses the same send_sms and status tracker as COMPOSE.
    def send(self):
        body = self.message.text().strip()
        if body:
            self.start_send(self.current, body, from_input=True)

    # self.sending blocks a second send until the first one answers, so pressing SEND
    # (or Enter, or RESEND) twice never sends a duplicate.
    def start_send(self, phone, body, from_input=False):
        if not phone or self.sending:
            return
        if not self.conn.smsgate:
            return set_status(self.status, "Connect SMS in COMPOSE first.")
        self.sending = True
        self.send_btn.setText("SENDING...")
        self.refresh_chat()
        run_in_background(send_sms, self.conn.smsgate, phone, body,
                          on_done=lambda result: self.sent(phone, body, result, from_input),
                          on_error=lambda err: self.send_failed(phone, body, err))

    # RESEND: the failed copy is removed and the same text is sent again as a new message,
    # so the chat doesn't show it twice.
    def resend(self, message_id):
        t = self.bubbles.get(f"msg:sent:{message_id}")
        if not t or self.sending:
            return
        if not self.conn.smsgate:
            return set_status(self.status, "Connect SMS in COMPOSE first.")
        delete_messages(self.user["id"], [t["id"]])
        self.start_send(t["phone"], t["body"])

    def link_clicked(self, url):
        if url.scheme() == "resend":
            self.resend(int(url.path()))

    # Hovering a failed text shows the full error from the phone or SMSGate.
    def link_hovered(self, url):
        t = self.bubbles.get(url.toString() if hasattr(url, "toString") else url)
        if t and t.get("status") == "failed" and t.get("error"):
            QToolTip.showText(QCursor.pos(), t["error"], self.view)

    # Right-click a bubble: COPY TEXT or DELETE just that message.
    def message_menu(self, pos):
        t = self.bubbles.get(self.view.anchorAt(pos))
        if not t:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("COPY TEXT")
        delete_action = menu.addAction("DELETE MESSAGE")
        chosen = menu.exec(self.view.viewport().mapToGlobal(pos))
        if chosen == copy_action:
            QApplication.clipboard().setText(t["body"])
            set_status(self.status, "Copied the message.", success=True)
        elif chosen == delete_action:
            self.delete_message(t)

    def delete_message(self, t):
        if t["mine"]:
            self.tracker.forget([t["id"]])
            delete_messages(self.user["id"], [t["id"]])
        elif t.get("outside"):
            self.hidden_keys.add(t["key"])
            self.outside.pop(t["key"], None)
        else:
            delete_received(self.user["id"], t["id"])
        self.refresh()

    def finish_sending(self):
        self.sending = False
        self.send_btn.setText("SEND")

    def sent(self, phone, body, result, from_input=False):
        gateway_id, status, error, config = result
        if self.conn.smsgate:
            self.conn.smsgate = config
        row_id = log_message(self.user["id"], "sms", phone, "", body, status, gateway_id, error)
        if status == "queued" and gateway_id:
            self.tracker.track(row_id, gateway_id)
        self.finish_sending()
        if from_input:
            self.message.clear()
        self.show_listening_status()
        self.refresh()
        self.message.setFocus()

    def send_failed(self, phone, body, err):
        log_message(self.user["id"], "sms", phone, "", body, "failed", error=friendly(err))
        self.finish_sending()
        set_status(self.status, friendly(err))
        self.refresh()

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
            self.hidden.add(self.current)
            self.outside = {k: t for k, t in self.outside.items() if t["phone"] != self.current}
            self.current = None
            self.refresh()

    # Start or stop checking the phone's inbox when SMS connects or disconnects.
    def connection_changed(self):
        if self.conn.smsgate:
            self.inbox_checks = 0
            self.inbox_error = ""
            # The cloud server has no inbox endpoint (only webhooks to a public server),
            # so replies can't be shown; sending and status tracking still work.
            self.inbox_unsupported = self.conn.smsgate.cloud
            self.inbox_timer.start()
            self.check_inbox()
        else:
            self.inbox_timer.stop()
        self.show_listening_status()

    def show_listening_status(self):
        if not self.conn.smsgate:
            set_status(self.status, "SMS isn't connected. Connect it in COMPOSE to send and receive.")
        elif self.inbox_unsupported and self.conn.smsgate.cloud:
            set_status(self.status, "Cloud server: texts send and show their status, but replies "
                                    "only appear with SMSGate's Local Server.")
        elif self.inbox_unsupported:
            set_status(self.status, "This SMSGate version can't share replies. Update the SMSGate app.")
        elif self.inbox_error:
            set_status(self.status, f"Couldn't check for replies: {self.inbox_error}")
        else:
            self.status.setObjectName("hint")
            self.status.style().polish(self.status)
            if self.only_ours.isChecked():
                self.status.setText("Checking every 5 seconds. Only replies from numbers you "
                                    "texted through JD UTILS are shown.")
            else:
                self.status.setText("Showing texts from everyone (last 7 days, not saved). "
                                    "Change this in Settings (gear).")

    # Asks the phone for new texts. checking_inbox stops a second request from starting
    # before the first one has answered.
    def check_inbox(self):
        if not self.conn.smsgate or self.checking_inbox or self.inbox_unsupported:
            return
        first_sent = first_sent_times(self.user["id"])
        show_all = not self.only_ours.isChecked()
        if not first_sent and not show_all:
            return
        since = everyone_since_utc(first_sent) if show_all else inbox_since_utc(first_sent)
        self.checking_inbox = True
        refresh = self.inbox_checks % REFRESH_EVERY == 0
        self.inbox_checks += 1
        run_in_background(get_sms_inbox, self.conn.smsgate, since, refresh,
                          on_done=lambda texts: self.inbox_received(texts, first_sent),
                          on_error=self.inbox_failed)

    def inbox_received(self, texts, first_sent):
        self.checking_inbox = False
        self.inbox_error = ""
        new, others, fresh = save_incoming(self.user["id"], texts, first_sent)
        if not self.only_ours.isChecked():
            for t in others:
                if (t["phone"] not in self.hidden and t["key"] not in self.outside
                        and t["key"] not in self.hidden_keys):
                    self.outside[t["key"]] = t
                    new += 1
                    if t["phone"] == self.current and self.isVisible():
                        self.seen_outside.add(t["key"])
        if new:
            if self.current and self.isVisible():
                mark_read(self.user["id"], self.current)
            self.refresh()
        if fresh:
            self.notify(fresh)
        self.show_listening_status()

    # Desktop notification for new replies, only when you aren't already looking at SMS
    # CHAT. Clicking it brings the app to the front with that conversation open.
    def notify(self, fresh):
        if (self.isVisible() and self.window().isActiveWindow()) or \
                not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), self)
            self.tray.setToolTip("JD UTILS")
            self.tray.messageClicked.connect(self.open_notified)
            self.tray.show()
        latest = fresh[-1]
        name = next((c["name"] for c in self.conversations() if c["phone"] == latest["phone"]), None)
        more = f" (+{len(fresh) - 1} more)" if len(fresh) > 1 else ""
        self.notified_phone = latest["phone"]
        self.tray.showMessage(f"New text from {name or latest['phone']}{more}",
                              latest["body"][:120], QIcon(str(ICON_PATH)), 6000)

    def open_notified(self):
        if self.notified_phone:
            self.current = self.notified_phone
        self.show_requested.emit()
        self.refresh()

    def filter_changed(self, only_ours):
        self.outside.clear()
        self.seen_outside.clear()
        self.hidden.clear()
        self.hidden_keys.clear()
        if only_ours and self.current and not normalize_phone(self.current):
            self.current = None
        self.show_listening_status()
        self.refresh()
        if not only_ours:
            self.check_inbox()

    def inbox_failed(self, err):
        self.checking_inbox = False
        if "can't share received texts" in friendly(err):
            self.inbox_unsupported = True
        else:
            self.inbox_error = friendly(err)
        self.show_listening_status()

    # Coming back to this tab counts as reading the open chat.
    def showEvent(self, event):
        super().showEvent(event)
        if self.current:
            mark_read(self.user["id"], self.current)
        self.refresh()

    # Logout: stop checking and drop everything held in memory.
    def clear_credentials(self):
        self.inbox_timer.stop()
        if self.tray is not None:
            self.tray.hide()
        self.outside.clear()
        self.only_ours.setChecked(True)
        self.current = None
        self.message.clear()
