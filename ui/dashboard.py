"""
ui/dashboard.py
Main window after login: top navigation bar with tabs + settings gear.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from ui.messaging_page import MessagingPage
from ui.url_page import UrlShortenerPage
from ui.scaling import ScalingWindow
from ui.account_dialog import ChangePasswordDialog, ChangeUsernameDialog
from ui.theme import current_theme, toggle_theme
from ui.widgets import ClockLabel, GearButton, make_box


class ComingSoonPage(QWidget):
    """Temporary page until the real feature is built."""

    def __init__(self, title, description):
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
        layout.addStretch()


class Dashboard(ScalingWindow):
    logout_requested = Signal()
    BASE_SIZE = (1000, 660)         # everything grows when the window is bigger

    def __init__(self, user):
        super().__init__()
        self.user = user                       # {"id": ..., "username": ...}
        self.setWindowTitle("JD UTILS")
        self.resize(1000, 660)
        self.setMinimumSize(860, 540)

        # ----- Pages -----
        self.stack = QStackedWidget()
        pages = [
            ("URL SHORTENER", UrlShortenerPage(user)),
            ("FAKE DATA GENERATOR", ComingSoonPage(
                "FAKE DATA GENERATOR", "Generate and store records with 10 fields each.")),
            ("SMS && EMAIL UI", MessagingPage(user)),      # && shows a single &
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
        nav_layout.addWidget(ClockLabel())                       # live date and time
        divider = QFrame(objectName="headerDivider")
        divider.setFixedSize(1, 22)
        nav_layout.addWidget(divider)
        self.user_label = QLabel(user["username"], objectName="headerUser")
        nav_layout.addWidget(self.user_label)
        nav_layout.addWidget(self.make_gear_button())

        # ----- Put it together -----
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(nav)
        layout.addWidget(self.stack, stretch=1)
        self.finish_scaling()

    def clear_session(self):
        """Called on logout: every page forgets its passwords and keys."""
        for page in self.pages:
            if hasattr(page, "clear_credentials"):
                page.clear_credentials()

    # ================= Settings (gear) menu =================

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
