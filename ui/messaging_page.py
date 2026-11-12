"""Feature 3: SMS & EMAIL UI page, which holds three sub-tabs.

COMPOSE connects Gmail and SMSGate and sends messages, SMS CHAT shows text
conversations, and EMAIL INBOX reads Gmail. They share one Connections object
and one SmsStatusTracker, so connecting once in COMPOSE works in every tab. The
bar on top shows unread badges and an EMAIL / SMS status dot.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from services.messaging_service import get_unfinished_sms
from ui.compose_tab import ComposeTab
from ui.email_inbox_tab import EmailInboxTab
from ui.messaging_shared import Connections, SmsStatusTracker
from ui.sms_chat_tab import SmsChatTab


class MessagingPage(QWidget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        # Shared by all three sub-tabs (see ui/messaging_shared.py).
        self.conn = Connections()
        self.tracker = SmsStatusTracker(self.conn)

        self.compose = ComposeTab(user, self.conn, self.tracker)
        self.chat = SmsChatTab(user, self.conn, self.tracker)
        self.inbox = EmailInboxTab(user, self.conn)
        # Sending a text from COMPOSE refreshes SMS CHAT straight away.
        self.compose.sent_something.connect(self.chat.refresh)

        self.stack = QStackedWidget()
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 8, 16, 0)
        bar.setSpacing(4)
        self.tabs = QButtonGroup(self)
        self.badges = {}
        for index, (label, page) in enumerate([("COMPOSE", self.compose),
                                               ("SMS CHAT", self.chat),
                                               ("EMAIL INBOX", self.inbox)]):
            self.stack.addWidget(page)
            tab = QPushButton(label, objectName="subtab")
            tab.setCheckable(True)
            tab.setCursor(Qt.PointingHandCursor)
            tab.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            self.tabs.addButton(tab, index)
            bar.addWidget(tab)
            # SMS CHAT and EMAIL INBOX get a red unread-count badge next to their tab.
            if page is not self.compose:
                badge = QLabel("", objectName="countBadge")
                badge.hide()
                self.badges[page] = badge
                bar.addWidget(badge, alignment=Qt.AlignVCenter)
                bar.addSpacing(8)
        self.tabs.button(0).setChecked(True)

        bar.addStretch()
        self.email_dot = QLabel("", objectName="dotOff")
        self.sms_dot = QLabel("", objectName="dotOff")
        bar.addWidget(self.email_dot)
        bar.addSpacing(10)
        bar.addWidget(self.sms_dot)

        bar_widget = QWidget(objectName="subtabBar")
        bar_widget.setLayout(bar)

        self.chat.unread_changed.connect(lambda n: self.set_badge(self.chat, n))
        self.inbox.unread_changed.connect(lambda n: self.set_badge(self.inbox, n))
        # Whenever a login changes, update the status dots and pick up unfinished texts.
        self.conn.changed.connect(self.update_dots)
        self.conn.changed.connect(self.resume_tracking)
        self.update_dots()
        self.chat.refresh()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar_widget)
        layout.addWidget(self.stack, stretch=1)

    def set_badge(self, page, count):
        badge = self.badges[page]
        badge.setText(str(count) if count < 100 else "99+")
        badge.setVisible(count > 0)

    # After connecting SMSGate (also after logging back in), keep tracking texts from the
    # last 24 hours that were still queued or sent.
    def resume_tracking(self):
        if self.conn.smsgate:
            for row in get_unfinished_sms(self.user["id"]):
                if row["id"] not in self.tracker.pending:
                    self.tracker.track(row["id"], row["gateway_id"])

    def update_dots(self):
        for dot, name, on in ((self.email_dot, "EMAIL", self.conn.gmail),
                              (self.sms_dot, "SMS", self.conn.smsgate)):
            dot.setObjectName("dotOn" if on else "dotOff")
            dot.style().polish(dot)
            dot.setText(f"● {name}")
            dot.setToolTip(f"{name} is connected" if on else f"{name} is not connected")

    # Logout: stop tracking and forget the logins held in memory. Saved logins stay in
    # the database and reconnect at the next login.
    def clear_credentials(self):
        self.tracker.stop()
        self.compose.clear_credentials()
        self.chat.clear_credentials()
        self.inbox.clear_credentials()
        self.conn.clear()
