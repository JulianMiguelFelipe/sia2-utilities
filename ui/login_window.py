"""The first window: log in or create an account.

Left side: an about card, the feature list and artwork. Right side: a
QStackedWidget that switches between LoginForm and RegisterForm. The checks
(password rules, hashing, duplicate usernames) live in auth/auth.py; this file
only shows the forms and the messages they return.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QStackedWidget,
    QVBoxLayout, QWidget,
)

from auth.auth import login_user, register_user
from ui.scaling import ScalingWindow
from ui.widgets import ClockLabel, ImageSlot, field_label, make_box, make_button, set_status

FEATURES = [
    ("URL SHORTENER", "Turns a long link into a shorter link"),
    ("FAKE DATA GENERATOR", "Generate fake data"),
    ("SMS & EMAIL UI", "Send SMS and email messages using our UI"),
]


def make_input(password=False):
    field = QLineEdit()
    field.setFixedHeight(30)
    if password:
        field.setEchoMode(QLineEdit.Password)
    return field


def set_message(label, text, success=False):
    set_status(label, text, success)


def make_top_bar():
    bar = make_box()
    layout = QGridLayout(bar)
    layout.setContentsMargins(12, 4, 12, 4)
    layout.addWidget(QLabel("JD UTILS", objectName="brand"), 0, 0, alignment=Qt.AlignCenter)
    layout.addWidget(ClockLabel(), 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    return bar


def make_features_box():
    box = make_box()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(10, 8, 14, 12)
    layout.setSpacing(2)
    layout.addWidget(QLabel("AVAILABLE FEATURES:", objectName="boxTitleBordered"),
                     alignment=Qt.AlignLeft)
    layout.addSpacing(6)
    for name, desc in FEATURES:
        layout.addWidget(QLabel(name, objectName="featureName"))
        layout.addWidget(QLabel(desc, objectName="featureDesc"))
        layout.addSpacing(4)
    return box


# Login form. A successful login emits login_success(user), which main.py uses to
# open the dashboard.
class LoginForm(QWidget):
    login_success = Signal(dict)
    go_to_register = Signal()

    def __init__(self):
        super().__init__()
        box = make_box()

        self.username = make_input()
        self.password = make_input(password=True)
        self.message = QLabel("", objectName="error")
        self.message.setWordWrap(True)

        enter_btn = make_button("ENTER NOW", "primary", width=150)
        enter_btn.clicked.connect(self.handle_login)
        # Enter in USERNAME jumps to PASSWORD; Enter in PASSWORD logs in.
        self.username.returnPressed.connect(self.password.setFocus)
        self.password.returnPressed.connect(self.handle_login)

        create_btn = make_button("CREATE AN ACCOUNT", "secondary")
        create_btn.clicked.connect(self.go_to_register.emit)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(4)
        layout.addWidget(field_label("USERNAME"))
        layout.addWidget(self.username)
        layout.addSpacing(18)
        layout.addWidget(field_label("PASSWORD"))
        layout.addWidget(self.password)
        layout.addSpacing(6)
        layout.addWidget(self.message)
        layout.addSpacing(6)
        layout.addWidget(enter_btn, alignment=Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(field_label("NO ACCOUNT?"))
        layout.addWidget(create_btn, alignment=Qt.AlignLeft)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

    def handle_login(self):
        user, msg = login_user(self.username.text(), self.password.text())
        if user:
            self.clear()
            self.login_success.emit(user)
        else:
            set_message(self.message, msg)
            # Clear only the password so the user doesn't have to retype the username.
            self.password.clear()

    def clear(self):
        self.username.clear()
        self.password.clear()
        self.message.clear()


# Sign-up form. On success it goes back to the login form with a green message.
class RegisterForm(QWidget):
    go_to_login = Signal(str)

    def __init__(self):
        super().__init__()
        box = make_box()

        self.username = make_input()
        self.password = make_input(password=True)
        self.confirm = make_input(password=True)
        self.message = QLabel("", objectName="error")
        self.message.setWordWrap(True)

        hint = QLabel("8+ characters, with a letter and a number", objectName="hint")

        signup_btn = make_button("SIGN UP", "primary", width=150)
        signup_btn.clicked.connect(self.handle_register)
        self.confirm.returnPressed.connect(self.handle_register)

        back_btn = make_button("BACK TO LOGIN", "secondary")
        back_btn.clicked.connect(lambda: self.go_to_login.emit(""))

        layout = QVBoxLayout(box)
        layout.setContentsMargins(24, 16, 24, 18)
        layout.setSpacing(4)
        layout.addWidget(QLabel("CREATE AN ACCOUNT", objectName="boxTitle"))
        layout.addSpacing(8)
        layout.addWidget(field_label("USERNAME"))
        layout.addWidget(self.username)
        layout.addSpacing(10)
        layout.addWidget(field_label("PASSWORD"))
        layout.addWidget(self.password)
        layout.addWidget(hint)
        layout.addSpacing(6)
        layout.addWidget(field_label("CONFIRM PASSWORD"))
        layout.addWidget(self.confirm)
        layout.addSpacing(4)
        layout.addWidget(self.message)
        layout.addSpacing(6)
        layout.addWidget(signup_btn, alignment=Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(field_label("ALREADY HAVE AN ACCOUNT?"))
        layout.addWidget(back_btn, alignment=Qt.AlignLeft)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

    def handle_register(self):
        ok, msg = register_user(self.username.text(), self.password.text(),
                                self.confirm.text())
        if ok:
            self.clear()
            self.go_to_login.emit(msg)
        else:
            set_message(self.message, msg)

    def clear(self):
        for field in (self.username, self.password, self.confirm):
            field.clear()
        self.message.clear()


def make_info_card():
    box = make_box()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(10, 8, 14, 12)
    layout.setSpacing(4)
    layout.addWidget(QLabel("JULIAN & DARWIN UTILITIES", objectName="boxTitleBordered"),
                     alignment=Qt.AlignLeft)
    layout.addSpacing(4)
    about = QLabel("A python program made for our SIA 2 final term project. "
                   "Built with Python, PySide6 and SQLite.",
                   objectName="infoText")
    about.setWordWrap(True)
    layout.addWidget(about)
    layout.addWidget(QLabel("ITL313-18 \u00b7 SIA 2 LAB \u00b7 FINAL TERM PROJECT", objectName="hint"))
    return box


# BASE_SIZE is this window's design size for scaling (see ui/scaling.py).
class LoginWindow(ScalingWindow):
    login_success = Signal(dict)
    BASE_SIZE = (900, 560)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JD UTILS")
        self.resize(900, 560)
        self.setMinimumSize(820, 520)

        art = ImageSlot("login_art.png", min_width=200, min_height=110)
        art.setFixedWidth(245)
        art_row = QHBoxLayout()
        art_row.addStretch(1)
        art_row.addWidget(art)
        art_row.addStretch(1)

        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(make_info_card())
        left.addWidget(make_features_box())
        left.addLayout(art_row, stretch=1)

        self.login_form = LoginForm()
        self.register_form = RegisterForm()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.login_form)
        self.stack.addWidget(self.register_form)
        self.stack.setFixedWidth(318)
        self.stack.setMinimumHeight(410)

        right = QVBoxLayout()
        right.setContentsMargins(0, 6, 0, 40)
        right.addWidget(self.stack)
        right.addStretch()

        body = QHBoxLayout()
        body.setContentsMargins(12, 16, 48, 0)
        body.setSpacing(60)
        body.addLayout(left, stretch=1)
        body.addLayout(right)

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(make_top_bar())
        layout.addLayout(body, stretch=1)

        self.login_form.go_to_register.connect(self.show_register)
        self.register_form.go_to_login.connect(self.show_login)
        self.login_form.login_success.connect(self.login_success.emit)
        self.finish_scaling()

    def show_register(self):
        self.login_form.clear()
        self.stack.setCurrentWidget(self.register_form)
        self.register_form.username.setFocus()

    def show_login(self, success_message=""):
        self.register_form.clear()
        self.login_form.clear()
        if success_message:
            set_message(self.login_form.message, success_message, success=True)
        self.stack.setCurrentWidget(self.login_form)
        self.login_form.username.setFocus()
