"""Saved logins per user account: Gmail and SMSGate (feature 3) and a TinyURL token (feature 1).

After a successful CONNECT the login is saved, so it reconnects the next time the
user logs in. The Gmail App Password and SMSGate password are encrypted with
Fernet (AES-128 + HMAC) before going into the database. The encryption key is
derived from the user's JD UTILS password at login, so someone who copies
app.db still can't read them without that password.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from database.db import get_connection

# Same idea as password hashing: many rounds make guessing the password slow.
KEY_ITERATIONS = 200_000


# Turns the login password into a 32-byte Fernet key. The "saved-logins:" prefix makes
# this salt different from the one used for the password hash, so the stored hash can
# never be used as the key.
def login_key(password, user_salt):
    return base64.urlsafe_b64encode(hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), f"saved-logins:{user_salt}".encode(), KEY_ITERATIONS))


# Encrypt a secret into a text token that is safe to store in the database.
def _lock(key, secret):
    return Fernet(key).encrypt(secret.encode()).decode()


# Decrypt a token. With the wrong key Fernet raises InvalidToken; we return None and
# the user just types the login again.
def _unlock(key, token):
    if not token:
        return None
    try:
        return Fernet(key).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# Make sure the user has a row (INSERT OR IGNORE), then update only the given columns.
def _save(user_id, values):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO saved_logins (user_id) VALUES (?)", (user_id,))
    conn.execute(f"UPDATE saved_logins SET {', '.join(f'{k} = ?' for k in values)} WHERE user_id = ?",
                 list(values.values()) + [user_id])
    conn.commit()
    conn.close()


def save_gmail(user_id, key, address, app_password):
    # Only passwords are encrypted. The Gmail address, IP, port and username aren't secret.
    _save(user_id, {"gmail_address": address, "gmail_password": _lock(key, app_password)})


def save_smsgate(user_id, key, ip, port, username, password):
    _save(user_id, {"sms_ip": ip, "sms_port": port, "sms_username": username,
                    "sms_password": _lock(key, password)})


# DISCONNECT forgets the saved login.
def save_tinyurl_token(user_id, key, token):
    _save(user_id, {"tinyurl_token": _lock(key, token) if token else None})


def forget_gmail(user_id):
    _save(user_id, {"gmail_address": None, "gmail_password": None})


def forget_smsgate(user_id):
    _save(user_id, {"sms_ip": None, "sms_port": None, "sms_username": None, "sms_password": None})


def load_logins(user_id, key):
    conn = get_connection()
    row = conn.execute("SELECT * FROM saved_logins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return {}
    saved = dict(row)
    saved["gmail_password"] = _unlock(key, saved["gmail_password"])
    saved["sms_password"] = _unlock(key, saved["sms_password"])
    saved["tinyurl_token"] = _unlock(key, saved["tinyurl_token"])
    return saved


# After a password change: unlock with the old key and lock again with the new one.
def rekey_logins(user_id, old_key, new_key):
    saved = load_logins(user_id, old_key)
    for column in ("gmail_password", "sms_password", "tinyurl_token"):
        if saved.get(column):
            _save(user_id, {column: _lock(new_key, saved[column])})
