"""Email inbox: read Gmail over IMAP."""

import html
import imaplib
import re
from email import message_from_bytes, policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from database.db import get_connection
from services.messaging_service import MessagingError

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
PAGE_SIZE = 30


# ---------- Connecting ----------
def _imap_login(gmail):
    """Log in to Gmail IMAP."""
    address, app_password = gmail
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=20)
    except OSError:
        raise MessagingError("Couldn't reach Gmail. Check your internet connection.")
    try:
        imap.login(address, app_password)
    except imaplib.IMAP4.error as err:
        imap.shutdown()
        if "IMAP" in str(err).upper() and "DISABLED" in str(err).upper():
            raise MessagingError("IMAP is off. Turn it on in Gmail: Settings > "
                                 "Forwarding and POP/IMAP > Enable IMAP.")
        raise MessagingError("Gmail rejected this email or App Password.")
    except OSError:
        raise MessagingError("Couldn't reach Gmail. Check your internet connection.")
    return imap


def _close(imap):
    """Log out of IMAP."""
    try:
        imap.logout()
    except (imaplib.IMAP4.error, OSError):
        pass


# ---------- Who did we email? (for the "only JD UTILS" filter) ----------
def emailed_addresses(user_id):
    """Addresses this user emailed."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT lower(recipient) AS r FROM messages "
        "WHERE user_id = ? AND type = 'email' AND status = 'sent'",
        (user_id,),
    ).fetchall()
    conn.close()
    return sorted(r["r"] for r in rows)


# ---------- The inbox list ----------
def _sender(header):
    """Sender name and address."""
    value = header.get("From")
    addresses = getattr(value, "addresses", None)
    if addresses:
        return addresses[0].display_name or addresses[0].addr_spec, addresses[0].addr_spec
    name, address = parseaddr(str(value or ""))
    return name or address, address


def _when(date_header):
    """Email date as local time."""
    try:
        return parsedate_to_datetime(date_header).astimezone()
    except (TypeError, ValueError, IndexError):
        return None


def fetch_inbox(gmail, limit=PAGE_SIZE, only_from=None):
    """Newest emails in the inbox."""
    if only_from is not None and not only_from:
        return [], False                       # filter on, but we emailed nobody yet

    imap = _imap_login(gmail)
    try:
        imap.select("INBOX", readonly=True)
        uids = set()
        if only_from is None:
            _, data = imap.uid("search", None, "ALL")
            uids.update(data[0].split())
        else:
            for address in only_from:
                _, data = imap.uid("search", None, "FROM", f'"{address}"')
                uids.update(data[0].split())
        ordered = sorted(uids, key=int, reverse=True)
        page = ordered[:limit]
        if not page:
            return [], False

        _, data = imap.uid("fetch", b",".join(page),
                           "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        emails = []
        for part in data:
            if not isinstance(part, tuple):
                continue
            meta = part[0].decode(errors="replace")
            uid = re.search(r"UID (\d+)", meta)
            flags = re.search(r"FLAGS \(([^)]*)\)", meta)
            header = message_from_bytes(part[1], policy=policy.default)
            name, address = _sender(header)
            emails.append({
                "uid": uid.group(1) if uid else "",
                "name": name or address,
                "address": address,
                "subject": str(header.get("Subject", "")) or "(no subject)",
                "date": _when(header.get("Date")),
                "unread": "\\Seen" not in (flags.group(1) if flags else ""),
            })
        emails.sort(key=lambda e: int(e["uid"] or 0), reverse=True)
        return emails, len(ordered) > limit
    except imaplib.IMAP4.error:
        raise MessagingError("Gmail couldn't load the inbox. Try REFRESH.")
    except OSError:
        raise MessagingError("Lost the connection to Gmail. Try REFRESH.")
    finally:
        _close(imap)


# ---------- Opening one email ----------
class _HTMLToText(HTMLParser):
    """HTML email to plain text."""

    BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        """Start empty."""
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        """Line breaks; skip scripts/styles."""
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        """End of a skipped tag."""
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        """Keep visible text."""
        if not self.skip:
            self.parts.append(data)

    def text(self):
        """The cleaned-up text."""
        out = html.unescape("".join(self.parts))
        out = re.sub(r"[ \t]+", " ", out)
        return re.sub(r"\n\s*\n+", "\n\n", out).strip()


def _body_text(msg):
    """Readable text of an email."""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return "(This email has no text to show.)"
    try:
        content = part.get_content()
    except (LookupError, ValueError):            # unknown character set
        content = part.get_payload(decode=True).decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        parser = _HTMLToText()
        parser.feed(content)
        return parser.text()
    return content.strip()


def _size(n):
    """File size as KB / MB."""
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def open_email(gmail, uid):
    """Download one email (marks it read)."""
    imap = _imap_login(gmail)
    try:
        imap.select("INBOX")                      # not read-only: lets Gmail mark it read
        _, data = imap.uid("fetch", uid.encode(), "(RFC822)")
        raw = next((p[1] for p in data if isinstance(p, tuple)), None)
        if raw is None:
            raise MessagingError("That email isn't in the inbox anymore. Try REFRESH.")
        msg = message_from_bytes(raw, policy=policy.default)
        name, address = _sender(msg)
        attachments = []
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            attachments.append(f"{part.get_filename() or 'attachment'} · {_size(len(payload))}")
        to = ", ".join(a for _, a in getaddresses([str(msg.get("To", ""))]) if a)
        return {
            "uid": uid,
            "name": name,
            "address": address,
            "to": to,
            "subject": str(msg.get("Subject", "")) or "(no subject)",
            "date": _when(msg.get("Date")),
            "body": _body_text(msg),
            "attachments": attachments,
            "message_id": str(msg.get("Message-ID", "")),
            "references": str(msg.get("References", "")),
        }
    except imaplib.IMAP4.error:
        raise MessagingError("Gmail couldn't open that email. Try again.")
    except OSError:
        raise MessagingError("Lost the connection to Gmail. Try again.")
    finally:
        _close(imap)


def reply_subject(subject):
    """Add 'Re:' to a subject."""
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def quote_original(email):
    """Original email quoted under a reply."""
    when = email["date"].strftime("%b %d, %Y, %I:%M %p") if email["date"] else "earlier"
    lines = email["body"].splitlines()[:40]
    quoted = "\n".join(f"> {line}" for line in lines)
    return f"\n\nOn {when}, {email['name']} <{email['address']}> wrote:\n{quoted}"
