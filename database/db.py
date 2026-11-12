"""SQLite database: a single file at data/app.db.

get_connection() opens it with named columns and foreign keys switched on.
init_db() creates any missing tables, so the app works on a fresh clone.
Every table that belongs to a user has user_id with ON DELETE CASCADE, so
deleting a user deletes all of their data with it.
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


def get_connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Lets code read columns by name, e.g. row["username"].
    conn.row_factory = sqlite3.Row
    # SQLite ignores foreign keys unless they are switched on for each connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Accounts. Passwords are never stored, only a salted PBKDF2 hash (see auth/auth.py).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Feature 1: URL Shortener history. direct = 1 means the link was made with TinyURL's
    # current API (opens the page directly); 0 marks links from the old API (preview page).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS short_urls (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            original_url TEXT    NOT NULL,
            short_url    TEXT    NOT NULL,
            direct       INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Feature 3: every email and SMS sent from COMPOSE, with its delivery status.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            type       TEXT    NOT NULL CHECK (type IN ('email', 'sms')),
            recipient  TEXT    NOT NULL,
            subject    TEXT,                              -- emails only
            body       TEXT    NOT NULL,
            status     TEXT    NOT NULL
                       CHECK (status IN ('queued', 'sent', 'delivered', 'failed')),
            gateway_id TEXT,                              -- SMSGate message ID (SMS only)
            error      TEXT,                              -- reason, if it failed
            sent_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Texts received through SMSGate. external_key stops the same text from being saved twice.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sms_inbox (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            phone        TEXT    NOT NULL,                -- sender, +639...
            body         TEXT    NOT NULL,
            received_at  TEXT    NOT NULL,                -- local time, YYYY-MM-DD HH:MM:SS
            external_key TEXT    NOT NULL,
            UNIQUE (user_id, external_key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # SMS CHAT contact names, and when each conversation was last read (for unread badges).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            phone        TEXT    NOT NULL,
            name         TEXT,
            last_read_at TEXT,
            UNIQUE (user_id, phone),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # App-wide settings such as the theme.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Feature 2: Fake Data Generator. Every field is optional, so the columns allow NULL and
    # "fields" lists the ones the user turned on. fake_records was the old placeholder table.
    cur.execute("DROP TABLE IF EXISTS fake_records")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fake_people (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            id_number       TEXT    NOT NULL,
            fields          TEXT    NOT NULL,
            photo           BLOB,
            first_name      TEXT,
            middle_name     TEXT,
            last_name       TEXT,
            sex             TEXT,
            birthdate       TEXT,
            civil_status    TEXT,
            blood_type      TEXT,
            nationality     TEXT,
            height_cm       INTEGER,
            weight_kg       INTEGER,
            occupation      TEXT,
            address         TEXT,
            mobile          TEXT,
            email           TEXT,
            emergency_name  TEXT,
            emergency_phone TEXT,
            issued_on       TEXT,
            valid_until     TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE (user_id, id_number),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Saved logins, one row per user: Gmail and SMSGate (feature 3) and the user's own TinyURL
    # token (feature 1). The password and token columns are encrypted (see services/saved_logins_service.py).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_logins (
            user_id         INTEGER PRIMARY KEY,
            gmail_address   TEXT,
            gmail_password  TEXT,
            sms_ip          TEXT,
            sms_port        TEXT,
            sms_username    TEXT,
            sms_password    TEXT,
            tinyurl_token   TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Upgrade older databases by adding the "direct" column. Their links get 0 because
    # they came from TinyURL's old API, so the shortener won't reuse them.
    if "tinyurl_token" not in [r["name"] for r in cur.execute("PRAGMA table_info(saved_logins)")]:
        cur.execute("ALTER TABLE saved_logins ADD COLUMN tinyurl_token TEXT")
    columns = [r["name"] for r in cur.execute("PRAGMA table_info(short_urls)")]
    if "direct" not in columns:
        cur.execute("ALTER TABLE short_urls ADD COLUMN direct INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    conn.close()


# Run python database/db.py to create the database and list its tables.
if __name__ == "__main__":
    init_db()
    print(f"Database ready at: {DB_PATH}")

    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    conn.close()
    print("Tables:", ", ".join(t["name"] for t in tables))
