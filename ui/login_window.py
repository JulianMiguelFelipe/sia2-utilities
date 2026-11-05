"""
ui/login_window.py
Login screen: top bar, "Available Features" box, PNG art slot, and a login box.
The login box swaps with the register box using QStackedWidget.
When login succeeds, the window emits `login_success` with the user's info.
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
        field.setEchoMode(QLineEdit.Password)      # show dots instead of text
    return field


def set_message(label, text, success=False):
    """Show a red error or green success message under the form."""
    set_status(label, text, success)


# ---------- Top bar ----------

def make_top_bar():
    """JD UTILS in the middle, the date and time on the right."""
    bar = make_box()
    layout = QGridLayout(bar)
    layout.setContentsMargins(12, 4, 12, 4)
    layout.addWidget(QLabel("JD UTILS", objectName="brand"), 0, 0, alignment=Qt.AlignCenter)
    layout.addWidget(ClockLabel(), 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
    return bar


# ---------- Available Features box ----------

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


# ---------- Login box ----------

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
        self.username.returnPressed.connect(self.password.setFocus)
        self.password.returnPressed.connect(self.handle_login)   # Enter key logs in

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
            self.password.clear()

    def clear(self):
        self.username.clear()
        self.password.clear()
        self.message.clear()


# ---------- Register box ----------

class RegisterForm(QWidget):
    go_to_login = Signal(str)     # carries a success message (or empty)

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


# ---------- Whole window ----------

def make_info_card():
    """Who made the app and what it is."""
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


class LoginWindow(ScalingWindow):
    login_success = Signal(dict)
    BASE_SIZE = (900, 560)          # everything grows when the window is bigger

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JD UTILS")
        self.resize(900, 560)
        self.setMinimumSize(820, 520)

        # Left column: info card + features box + art
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

        # Right column: login / register (swappable)
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
