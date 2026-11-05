"""Change username / change password pop-ups."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from auth.auth import change_password, change_username
from ui.scaling import current_scale
from ui.widgets import field_label, make_box, make_button, set_status


class AccountDialog(QDialog):
    """Pop-up with fields, SAVE and CANCEL."""

    def __init__(self, parent, title, subtitle, fields):
        """Build the pop-up."""
        super().__init__(parent)
        self.setWindowTitle("JD UTILS")
        self.setModal(True)
        s = current_scale()
        self.setMinimumWidth(round(380 * s))

        box = make_box()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(round(22 * s), round(16 * s), round(22 * s), round(18 * s))
        inner.setSpacing(round(6 * s))
        inner.addWidget(QLabel(title, objectName="sectionTitle"))
        note = QLabel(subtitle, objectName="hint")
        note.setWordWrap(True)
        inner.addWidget(note)
        inner.addSpacing(round(6 * s))

        self.inputs = {}
        for key, label, password in fields:
            field = QLineEdit()
            field.setMinimumHeight(round(32 * s))
            if password:
                field.setEchoMode(QLineEdit.Password)
            field.returnPressed.connect(self.save)
            inner.addWidget(field_label(label))
            inner.addWidget(field)
            inner.addSpacing(round(4 * s))
            self.inputs[key] = field

        self.message = QLabel("", objectName="error")
        self.message.setWordWrap(True)
        inner.addWidget(self.message)

        save_btn = make_button("SAVE", "primary")
        save_btn.clicked.connect(self.save)
        cancel_btn = make_button("CANCEL", "secondary")
        cancel_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        inner.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        first = next(iter(self.inputs.values()))
        first.setFocus(Qt.OtherFocusReason)

    def value(self, key):
        """Text of one field."""
        return self.inputs[key].text()

    def show_error(self, text):
        """Show a red error."""
        set_status(self.message, text)

    def save(self):
        """Save (each dialog does its own)."""
        raise NotImplementedError


class ChangeUsernameDialog(AccountDialog):
    """Change username pop-up."""
    def __init__(self, parent, user):
        """Build the fields."""
        super().__init__(parent, "CHANGE USERNAME",
                         f"You're signed in as {user['username']}. "
                         "3-20 letters, numbers or underscores.",
                         [("username", "NEW USERNAME", False),
                          ("password", "CURRENT PASSWORD", True)])
        self.user = user
        self.inputs["username"].setText(user["username"])
        self.inputs["username"].selectAll()

    def save(self):
        """Save the new username."""
        ok, msg = change_username(self.user["id"], self.value("username"), self.value("password"))
        if not ok:
            self.inputs["password"].clear()
            return self.show_error(msg)
        self.user["username"] = self.value("username").strip()   # every page shares this dict
        self.accept()


class ChangePasswordDialog(AccountDialog):
    """Change password pop-up."""
    def __init__(self, parent, user):
        """Build the fields."""
        super().__init__(parent, "CHANGE PASSWORD",
                         "At least 8 characters, with a letter and a number. "
                         "It's saved as a new salted hash.",
                         [("current", "CURRENT PASSWORD", True),
                          ("new", "NEW PASSWORD", True),
                          ("confirm", "CONFIRM NEW PASSWORD", True)])
        self.user = user

    def save(self):
        """Save the new password."""
        ok, msg = change_password(self.user["id"], self.value("current"),
                                  self.value("new"), self.value("confirm"))
        if not ok:
            return self.show_error(msg)
        self.accept()
