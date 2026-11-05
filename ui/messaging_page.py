"""SMS & EMAIL UI page: the three sub-tabs."""

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
    """SMS & EMAIL UI page."""
    def __init__(self, user):
        """Build the sub-tabs and status bar."""
        super().__init__()
        self.user = user
        self.conn = Connections()                       # shared logins (memory only)
        self.tracker = SmsStatusTracker(self.conn)

        self.compose = ComposeTab(user, self.conn, self.tracker)
        self.chat = SmsChatTab(user, self.conn, self.tracker)
        self.inbox = EmailInboxTab(user, self.conn)
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
        self.conn.changed.connect(self.update_dots)
        self.conn.changed.connect(self.resume_tracking)
        self.update_dots()
        self.chat.refresh()                             # show the starting unread count

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar_widget)
        layout.addWidget(self.stack, stretch=1)

    def set_badge(self, page, count):
        """Unread number on a sub-tab."""
        badge = self.badges[page]
        badge.setText(str(count) if count < 100 else "99+")
        badge.setVisible(count > 0)

    def resume_tracking(self):
        """On SMS connect, check texts still QUEUED/SENT from earlier."""
        if self.conn.smsgate:
            for row in get_unfinished_sms(self.user["id"]):
                if row["id"] not in self.tracker.pending:
                    self.tracker.track(row["id"], row["gateway_id"])

    def update_dots(self):
        """EMAIL / SMS status dots."""
        for dot, name, on in ((self.email_dot, "EMAIL", self.conn.gmail),
                              (self.sms_dot, "SMS", self.conn.smsgate)):
            dot.setObjectName("dotOn" if on else "dotOff")
            dot.style().polish(dot)
            dot.setText(f"● {name}")
            dot.setToolTip(f"{name} is connected" if on else f"{name} is not connected")

    def clear_credentials(self):
        """Forget logins (logout)."""
        self.tracker.stop()
        self.compose.clear_credentials()
        self.chat.clear_credentials()
        self.inbox.clear_credentials()
        self.conn.clear()
