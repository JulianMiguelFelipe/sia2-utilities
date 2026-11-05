"""URL Shortener: validate, shorten with TinyURL, history."""

import re
from urllib.parse import urlparse

import pyshorteners

from database.db import get_connection


def normalize_url(url):
    """Clean up and check a URL."""
    url = url.strip()
    if not url:
        raise ValueError("Please enter a URL.")
    if " " in url:
        raise ValueError("A URL can't contain spaces.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url                 # "google.com" -> "https://google.com"
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError("That doesn't look like a valid URL.")
    return url


def shorten_url(url):
    """Get a TinyURL short link."""
    try:
        return pyshorteners.Shortener(timeout=10).tinyurl.short(url)
    except Exception:
        raise ConnectionError("Couldn't reach TinyURL. Check your internet connection.")


def save_short_url(user_id, original_url, short_url):
    """Save a link to history."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO short_urls (user_id, original_url, short_url) VALUES (?, ?, ?)",
        (user_id, original_url, short_url),
    )
    conn.commit()
    conn.close()


def find_existing(user_id, original_url):
    """Link already shortened?"""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? AND original_url = ? ORDER BY id DESC LIMIT 1",
        (user_id, original_url),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_short_urls(user_id, ids):
    """Delete selected links."""
    conn = get_connection()
    conn.executemany("DELETE FROM short_urls WHERE id = ? AND user_id = ?",
                     [(i, user_id) for i in ids])
    conn.commit()
    conn.close()


def clear_short_urls(user_id):
    """Delete all links."""
    conn = get_connection()
    conn.execute("DELETE FROM short_urls WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_stats(user_id):
    """Link count and characters saved."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS links, "
        "COALESCE(SUM(MAX(LENGTH(original_url) - LENGTH(short_url), 0)), 0) AS saved, "
        "MAX(created_at) AS last FROM short_urls WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def get_history(user_id):
    """This user's links, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
