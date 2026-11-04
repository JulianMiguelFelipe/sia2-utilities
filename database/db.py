"""
database/db.py
Handles the SQLite connection and creates all tables for the app.

Run this file directly to create the database:
    python -m database.db
"""

import sqlite3
from pathlib import Path

# app.db lives in the data/ folder at the project root
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


def get_connection():
    """Open a connection to the SQLite database."""
    DATA_DIR.mkdir(exist_ok=True)              # create data/ if missing
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row             # access columns by name: row["username"]
    conn.execute("PRAGMA foreign_keys = ON")   # make FOREIGN KEY rules actually work
    return conn


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Users (login system) -- passwords are NEVER stored as plain text
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 2. URL Shortener history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS short_urls (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            original_url TEXT    NOT NULL,
            short_url    TEXT    NOT NULL,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 3. SMS & Email log
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

    # 4. Fake Data Generator -- exactly 10 data fields
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fake_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            full_name     TEXT    NOT NULL,   -- 1
            gender        TEXT    NOT NULL,   -- 2
            birthdate     TEXT    NOT NULL,   -- 3 (YYYY-MM-DD)
            address       TEXT    NOT NULL,   -- 4
            city          TEXT    NOT NULL,   -- 5
            zip_code      TEXT    NOT NULL,   -- 6
            mobile_number TEXT    NOT NULL,   -- 7
            email         TEXT    NOT NULL,   -- 8
            job           TEXT    NOT NULL,   -- 9
            company       TEXT    NOT NULL,   -- 10
            created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at: {DB_PATH}")

    # Show the tables that were created
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    conn.close()
    print("Tables:", ", ".join(t["name"] for t in tables))
