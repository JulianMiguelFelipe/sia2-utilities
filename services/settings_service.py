"""Small key/value settings stored in the app_settings table, like the theme
("dark"/"light") and each user's chosen fake data fields.
"""

from database.db import get_connection


def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    # Insert the key, or update it if it already exists (SQLite upsert).
    conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()
    conn.close()
