"""Feature 1 logic: check a URL, shorten it with TinyURL, keep the history.

Shortening uses TinyURL's current API (api.tinyurl.com/create), so links open the
page directly (the old api-create.php endpoint shows a preview page first). The
API needs a token: the user's own if they saved one on the URL Shortener page,
otherwise the built-in team token below."""

import re
from urllib.parse import urlparse

import requests

from database.db import get_connection

# Built-in team token, used when the user hasn't saved their own on the URL Shortener page.
DEFAULT_TOKEN = "2hu2grtdU81HZl3fLgPbb9CM0zU9htcDEF68mYgfeBk2oRskPYZLFONo6HTo"
TINYURL_API = "https://api.tinyurl.com/create"
# TinyURL HTTP error codes turned into messages the user can act on.
TINYURL_ERRORS = {
    401: "TinyURL rejected the API token. Check the token box or clear it to use the built-in one.",
    422: "TinyURL says that URL isn't valid.",
    429: "TinyURL's request limit was reached. Try again later.",
}


# Accepts "google.com" too: a missing http:// or https:// is added, then the domain is checked.
def normalize_url(url):
    url = url.strip()
    if not url:
        raise ValueError("Please enter a URL.")
    if " " in url:
        raise ValueError("A URL can't contain spaces.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        raise ValueError("That doesn't look like a valid URL.")
    return url


def shorten_url(url, token=None):
    token = (token or "").strip() or DEFAULT_TOKEN
    try:
        # POST the long link with the token in the Authorization header. timeout=(5, 15):
        # up to 5 s to connect and 15 s to wait for the reply.
        response = requests.post(TINYURL_API, timeout=(5, 15),
                                 headers={"Authorization": f"Bearer {token}"},
                                 json={"url": url, "domain": "tinyurl.com"})
    except requests.exceptions.RequestException:
        raise ConnectionError("Couldn't reach TinyURL. Check your internet connection.")
    if response.status_code in TINYURL_ERRORS:
        raise ConnectionError(TINYURL_ERRORS[response.status_code])
    try:
        # Successful reply: {"data": {"tiny_url": "https://tinyurl.com/...", ...}, "code": 0}
        return response.json()["data"]["tiny_url"]
    except (ValueError, KeyError, TypeError):
        raise ConnectionError("TinyURL sent an unexpected reply. Try again.")


def save_short_url(user_id, original_url, short_url):
    conn = get_connection()
    conn.execute(
        "INSERT INTO short_urls (user_id, original_url, short_url, direct) VALUES (?, ?, ?, 1)",
        (user_id, original_url, short_url),
    )
    conn.commit()
    conn.close()


# Only links made with the current API (direct = 1) are reused, so an old link that
# shows a preview page gets replaced by a new one.
def find_existing(user_id, original_url):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? AND original_url = ? AND direct = 1 ORDER BY id DESC LIMIT 1",
        (user_id, original_url),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_short_urls(user_id, ids):
    conn = get_connection()
    # "AND user_id = ?" makes sure users can only delete their own links.
    conn.executemany("DELETE FROM short_urls WHERE id = ? AND user_id = ?",
                     [(i, user_id) for i in ids])
    conn.commit()
    conn.close()


def clear_short_urls(user_id):
    conn = get_connection()
    conn.execute("DELETE FROM short_urls WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# Totals for this user: number of links and characters saved.
def get_stats(user_id):
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
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_url, short_url, created_at FROM short_urls "
        "WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
