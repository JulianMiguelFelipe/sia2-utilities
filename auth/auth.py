"""Login system: register, login, password hashing, account changes."""

import hashlib
import hmac
import os
import re
import sqlite3

from database.db import get_connection

ITERATIONS = 200_000          # more rounds = slower to brute-force
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MIN_PASSWORD_LENGTH = 8


# ---------- Password hashing ----------
def hash_password(password, salt=None):
    """Hash a password with a salt."""
    if salt is None:
        salt = os.urandom(16)                  # new random salt for new users
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return pw_hash.hex(), salt.hex()


def verify_password(password, stored_hash, stored_salt):
    """Check a password against its stored hash."""
    new_hash, _ = hash_password(password, bytes.fromhex(stored_salt))
    return hmac.compare_digest(new_hash, stored_hash)   # safe comparison


# ---------- Validation ----------
def validate_registration(username, password, confirm_password):
    """Check the sign-up fields."""
    if not username or not password or not confirm_password:
        return "Please fill in all fields."
    if not USERNAME_PATTERN.match(username):
        return "Username must be 3-20 characters: letters, numbers, or underscore."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "Password must contain at least one letter and one number."
    if password != confirm_password:
        return "Passwords do not match."
    return None


# ---------- Register / Login ----------
def register_user(username, password, confirm_password):
    """Create a new account."""
    username = username.strip()
    error = validate_registration(username, password, confirm_password)
    if error:
        return False, error

    pw_hash, salt = hash_password(password)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, pw_hash, salt),
        )
        conn.commit()
        return True, "Account created! You can now log in."
    except sqlite3.IntegrityError:            # UNIQUE constraint on username
        return False, "That username is already taken."
    finally:
        conn.close()


def login_user(username, password):
    """Check username and password."""
    username = username.strip()
    if not username or not password:
        return None, "Please enter your username and password."

    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    # Same message for "no such user" and "wrong password" so attackers
    # can't tell which usernames exist.
    if row is None or not verify_password(password, row["password_hash"], row["salt"]):
        return None, "Invalid username or password."

    return {"id": row["id"], "username": row["username"]}, "Login successful."


# ---------- Account settings (from the gear menu) ----------
def _check_current_password(conn, user_id, password):
    """Check the signed-in user's password."""
    row = conn.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None and verify_password(password, row["password_hash"], row["salt"])


def change_username(user_id, new_username, current_password):
    """Change the username."""
    new_username = new_username.strip()
    if not USERNAME_PATTERN.match(new_username):
        return False, "Username must be 3-20 characters: letters, numbers, or underscore."
    conn = get_connection()
    try:
        if not _check_current_password(conn, user_id, current_password):
            return False, "Your current password is wrong."
        conn.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, user_id))
        conn.commit()
        return True, f"Username changed to {new_username}."
    except sqlite3.IntegrityError:
        return False, "That username is already taken."
    finally:
        conn.close()


def change_password(user_id, current_password, new_password, confirm_password):
    """Change the password (new salt + hash)."""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return False, f"New password must be at least {MIN_PASSWORD_LENGTH} characters."
    if not (re.search(r"[A-Za-z]", new_password) and re.search(r"\d", new_password)):
        return False, "New password must contain at least one letter and one number."
    if new_password != confirm_password:
        return False, "New passwords do not match."
    if new_password == current_password:
        return False, "Choose a password different from your current one."
    conn = get_connection()
    try:
        if not _check_current_password(conn, user_id, current_password):
            return False, "Your current password is wrong."
        pw_hash, salt = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                     (pw_hash, salt, user_id))
        conn.commit()
        return True, "Password changed."
    finally:
        conn.close()
