"""Start the app: python main.py"""

import sys

from PySide6.QtWidgets import QApplication

from database.db import init_db
from ui.dashboard import Dashboard
from ui.login_window import LoginWindow
from services.settings_service import get_setting
from ui.theme import set_theme


class App:
    """Switches between the login window and the dashboard."""

    def __init__(self):
        """Create the login window."""
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self.open_dashboard)
        self.dashboard = None

    def start(self):
        """Show the login window."""
        self.login_window.show()

    def open_dashboard(self, user):
        """Open the dashboard after login."""
        self.dashboard = Dashboard(user)
        self.dashboard.logout_requested.connect(self.logout)
        if self.login_window.isMaximized():      # keep the same window size
            self.dashboard.showMaximized()
        else:
            self.dashboard.show()
        self.login_window.hide()

    def logout(self):
        """Close the dashboard and go back to login."""
        was_maximized = self.dashboard.isMaximized()
        self.dashboard.clear_session()      # wipe Email/SMS credentials from memory
        self.dashboard.close()
        self.dashboard.deleteLater()
        self.dashboard = None
        self.login_window.show_login()
        if was_maximized:
            self.login_window.showMaximized()
        else:
            self.login_window.show()


def main():
    """Start the database, theme and windows."""
    init_db()                       # make sure the database and tables exist
    qt_app = QApplication(sys.argv)
    set_theme(get_setting("theme", "dark"), save=False)   # open in the last mode used
    app = App()
    app.start()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
