"""
auth/auth.py
User registration and login (username + password).

Passwords are NEVER stored as plain text. Each password is:
  1. combined with a random "salt" (16 random bytes, unique per user)
  2. hashed with PBKDF2-HMAC-SHA256 (200,000 rounds) from Python's built-in hashlib
Only the hash and the salt are saved in the database.
"""

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
    """Hash a password with a salt. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = os.urandom(16)                  # new random salt for new users
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return pw_hash.hex(), salt.hex()


def verify_password(password, stored_hash, stored_salt):
    """Re-hash the entered password with the stored salt and compare."""
    new_hash, _ = hash_password(password, bytes.fromhex(stored_salt))
    return hmac.compare_digest(new_hash, stored_hash)   # safe comparison


# ---------- Validation ----------

def validate_registration(username, password, confirm_password):
    """Return an error message, or None if everything is valid."""
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
    """Create a new account. Returns (success, message)."""
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
    """Check credentials. Returns (user_dict, message). user_dict is None on failure."""
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
