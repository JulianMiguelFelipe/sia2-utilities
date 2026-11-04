"""
ui/dashboard.py
Main window after login: top navigation bar with tabs + settings gear.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMenu, QPushButton, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from ui.messaging_page import MessagingPage
from ui.url_page import UrlShortenerPage
from ui.widgets import GearButton, ImageSlot, make_box


class ComingSoonPage(QWidget):
    """Temporary page until the real feature is built."""

    def __init__(self, title, description, art_file):
        super().__init__()
        box = make_box()
        box.setFixedWidth(676)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(22, 14, 22, 22)
        box_layout.addWidget(QLabel(title, objectName="boxTitle"))
        box_layout.addWidget(QLabel(description, objectName="fieldLabel"))
        box_layout.addSpacing(12)
        box_layout.addWidget(QLabel("COMING SOON", objectName="error"))

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(box)
        row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 44, 26, 0)
        layout.setSpacing(22)
        layout.addLayout(row)
        layout.addWidget(ImageSlot(art_file, min_height=120), stretch=1)


class Dashboard(QWidget):
    logout_requested = Signal()

    def __init__(self, user):
        super().__init__()
        self.user = user
        self.setWindowTitle("JD UTILS")
        self.resize(1000, 660)
        self.setMinimumSize(860, 540)

        # ----- Pages -----
        self.stack = QStackedWidget()
        pages = [
            ("URL SHORTENER", UrlShortenerPage(user)),
            ("FAKE DATA GENERATOR", ComingSoonPage(
                "FAKE DATA GENERATOR", "Generate and store records with 10 fields each.",
                "fakedata_art.png")),
            ("SMS && EMAIL UI", MessagingPage(user)),
        ]
        self.pages = [page for _, page in pages]

        # ----- Top navigation bar -----
        nav = make_box()
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(10, 4, 10, 4)
        nav_layout.setSpacing(14)
        nav_layout.addWidget(QLabel("JD UTILS", objectName="brand"))
        nav_layout.addSpacing(6)

        self.tabs = QButtonGroup(self)
        self.tabs.setExclusive(True)
        for index, (label, page) in enumerate(pages):
            self.stack.addWidget(page)
            tab = QPushButton(label, objectName="tab")
            tab.setCheckable(True)
            tab.setCursor(Qt.PointingHandCursor)
            tab.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            self.tabs.addButton(tab, index)
            nav_layout.addWidget(tab)
        self.tabs.button(0).setChecked(True)

        nav_layout.addStretch()
        nav_layout.addWidget(self.make_gear_button())

        # ----- Put it together -----
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(nav)
        layout.addWidget(self.stack, stretch=1)

    def clear_session(self):
        """Called on logout: every page forgets its passwords and keys."""
        for page in self.pages:
            if hasattr(page, "clear_credentials"):
                page.clear_credentials()

    def make_gear_button(self):
        gear = GearButton()
        gear.setPopupMode(QToolButton.InstantPopup)

        menu = QMenu(gear)
        who = menu.addAction(f"Signed in as {self.user['username']}")
        who.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Log out", self.logout_requested.emit)
        gear.setMenu(menu)
        return gear
