"""JD UTILS entry point. Run with: python main.py

Creates the database, applies the saved light/dark theme, then shows the login
window. After a successful login, App swaps the login window for the dashboard,
and swaps back on logout.
"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app_paths import ICON_PATH

from database.db import init_db
from ui.dashboard import Dashboard
from ui.login_window import LoginWindow
from services.settings_service import get_setting
from ui.theme import set_theme


# Decides which window is on screen: the login window or the dashboard.
class App:
    def __init__(self):
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self.open_dashboard)
        self.dashboard = None

    def start(self):
        self.login_window.show()

    def open_dashboard(self, user):
        self.dashboard = Dashboard(user)
        self.dashboard.logout_requested.connect(self.logout)
        if self.login_window.isMaximized():
            self.dashboard.showMaximized()
        else:
            self.dashboard.show()
        self.login_window.hide()

    # Logout clears the logins held in memory (saved logins stay in the database),
    # closes the dashboard and goes back to the login screen, keeping the same window size.
    def logout(self):
        was_maximized = self.dashboard.isMaximized()
        self.dashboard.clear_session()
        self.dashboard.close()
        self.dashboard.deleteLater()
        self.dashboard = None
        self.login_window.show_login()
        if was_maximized:
            self.login_window.showMaximized()
        else:
            self.login_window.show()


def main():
    # Create the database and any missing tables before anything reads from it.
    init_db()
    qt_app = QApplication(sys.argv)
    qt_app.setWindowIcon(QIcon(str(ICON_PATH)))
    set_theme(get_setting("theme", "dark"), save=False)
    app = App()
    app.start()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
