"""
main.py
Start the app:  python main.py
"""

import sys

from PySide6.QtWidgets import QApplication

from database.db import init_db
from ui.dashboard import Dashboard
from ui.login_window import LoginWindow
from ui.styles import APP_STYLE


class App:
    """Switches between the login window and the dashboard."""

    def __init__(self):
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self.open_dashboard)
        self.dashboard = None

    def start(self):
        self.login_window.show()

    def open_dashboard(self, user):
        self.dashboard = Dashboard(user)
        self.dashboard.logout_requested.connect(self.logout)
        self.dashboard.show()
        self.login_window.hide()

    def logout(self):
        self.dashboard.clear_session()
        self.dashboard.close()
        self.dashboard.deleteLater()
        self.dashboard = None
        self.login_window.show_login()
        self.login_window.show()


def main():
    init_db()
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(APP_STYLE)
    app = App()
    app.start()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
