"""Main window after login: top navigation bar, the three feature pages and the
settings (gear) menu.

The three features are separate page classes inside a QStackedWidget; clicking a
tab shows that page. All pages share the same user dict, so a username change
shows up everywhere at once.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout,
)

from ui.fake_data_page import FakeDataPage
from ui.messaging_page import MessagingPage
from ui.url_page import UrlShortenerPage
from ui.scaling import ScalingWindow
from ui.account_dialog import ChangePasswordDialog, ChangeUsernameDialog
from ui.theme import current_theme, toggle_theme
from ui.widgets import ClockLabel, GearButton, make_box


class Dashboard(ScalingWindow):
    logout_requested = Signal()
    BASE_SIZE = (1000, 660)

    def __init__(self, user):
        super().__init__()
        self.user = user
        self.setWindowTitle("JD UTILS")
        self.resize(1000, 660)
        self.setMinimumSize(860, 540)

        # The three features. A QStackedWidget shows one page at a time.
        self.stack = QStackedWidget()
        pages = [
            ("URL SHORTENER", UrlShortenerPage(user)),
            ("FAKE DATA GENERATOR", FakeDataPage(user)),
            ("SMS && EMAIL UI", MessagingPage(user)),
        ]
        self.pages = [page for _, page in pages]

        nav = make_box()
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(10, 4, 10, 4)
        nav_layout.setSpacing(14)
        nav_layout.addWidget(QLabel("JD UTILS", objectName="brand"))
        nav_layout.addSpacing(6)

        # A QButtonGroup keeps exactly one tab highlighted.
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
        self.pages[2].show_requested.connect(self.show_messaging)

        nav_layout.addStretch()
        nav_layout.addWidget(ClockLabel())
        divider = QFrame(objectName="headerDivider")
        divider.setFixedSize(1, 22)
        nav_layout.addWidget(divider)
        self.user_label = QLabel(user["username"], objectName="headerUser")
        nav_layout.addWidget(self.user_label)
        nav_layout.addWidget(self.make_gear_button())

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(nav)
        layout.addWidget(self.stack, stretch=1)
        # Every widget exists now, so capture their sizes for window scaling (ui/scaling.py).
        self.finish_scaling()

    # Called on logout: each page forgets anything it holds in memory.
    # A notification was clicked: show SMS & EMAIL and bring the window to the front.
    def show_messaging(self):
        self.stack.setCurrentIndex(2)
        self.tabs.button(2).setChecked(True)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def clear_session(self):
        for page in self.pages:
            if hasattr(page, "clear_credentials"):
                page.clear_credentials()

    # Settings menu: who is signed in, light/dark mode, SMS & email filters, account
    # changes and log out.
    def make_gear_button(self):
        gear = GearButton()
        gear.setToolTip("Settings")
        gear.setPopupMode(QToolButton.InstantPopup)

        menu = QMenu(gear)
        self.who = menu.addAction("")
        self.who.setEnabled(False)
        menu.addSeparator()
        self.theme_action = menu.addAction("", toggle_theme)
        menu.addSeparator()
        messaging = self.pages[2]
        menu.addAction(messaging.chat.only_ours)
        menu.addAction(messaging.inbox.only_ours)
        menu.addSeparator()
        menu.addAction("Change username", self.change_username)
        menu.addAction("Change password", self.change_password)
        menu.addSeparator()
        menu.addAction("Log out", self.logout_requested.emit)
        menu.aboutToShow.connect(self.update_menu)
        gear.setMenu(menu)
        self.update_menu()
        return gear

    def update_menu(self):
        self.who.setText(f"Signed in as {self.user['username']}")
        self.theme_action.setText("Switch to light mode" if current_theme() == "dark"
                                  else "Switch to dark mode")

    def change_username(self):
        if ChangeUsernameDialog(self, self.user).exec():
            self.user_label.setText(self.user["username"])
            QMessageBox.information(self, "JD UTILS",
                                    f"Your username is now {self.user['username']}.")

    def change_password(self):
        if ChangePasswordDialog(self, self.user).exec():
            QMessageBox.information(self, "JD UTILS",
                                    "Password changed. Use the new one next time you log in.")
