"""
services/url_service.py
URL Shortener logic: validate, shorten with TinyURL, save history.
No GUI code here.
"""

import re
from urllib.parse import urlparse

import pyshorteners

from database.db import get_connection


def normalize_url(url):
    """Clean up and validate a URL. Raises ValueError if it's not valid."""
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
    """Return a TinyURL short link. Needs an internet connection."""
    try:
        return pyshorteners.Shortener(timeout=10).tinyurl.short(url)
    except Exception:
        raise ConnectionError("Couldn't reach TinyURL. Check your internet connection.")


def save_short_url(user_id, original_url, short_url):
    conn = get_connection()
    conn.execute(
        "INSERT INTO short_urls (user_id, original_url, short_url) VALUES (?, ?, ?)",
        (user_id, original_url, short_url),
    )
    conn.commit()
    conn.close()


def find_existing(user_id, original_url):
    """If this user already shortened this exact link, return that row (else None)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? AND original_url = ? ORDER BY id DESC LIMIT 1",
        (user_id, original_url),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_short_urls(user_id, ids):
    conn = get_connection()
    conn.executemany("DELETE FROM short_urls WHERE id = ? AND user_id = ?",
                     [(i, user_id) for i in ids])
    conn.commit()
    conn.close()


def clear_short_urls(user_id):
    conn = get_connection()
    conn.execute("DELETE FROM short_urls WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_stats(user_id):
    """How many links, and how many characters the short links saved in total."""
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
    """All links this user has shortened, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
