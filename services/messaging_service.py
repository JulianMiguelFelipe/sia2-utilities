"""SMS & Email sending: Gmail SMTP, SMSGate HTTP, message log."""

import re
import smtplib
from dataclasses import dataclass, replace
from email.message import EmailMessage

import requests

from database.db import get_connection

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465                       # SSL
SMS_MAX_LENGTH = 1600

# SMSGate has used two paths over its versions. We try the documented local
# path first, then the newer one, and remember whichever the phone answers.
SMSGATE_PATHS = ["/message", "/3rdparty/v1/messages"]
SMSGATE_TIMEOUT = (5, 15)              # (seconds to connect, seconds to wait for reply)

# SMSGate message states -> our history statuses
SMSGATE_STATES = {
    "pending": "queued", "processed": "queued", "cancelling": "queued",
    "sent": "sent", "delivered": "delivered",
    "failed": "failed", "cancelled": "failed",
}


class MessagingError(Exception):
    """Error with a message safe to show."""


# ---------- Recipient detection ----------
def normalize_phone(text):
    """PH number to +639... format."""
    number = re.sub(r"[\s\-()]", "", text)
    if re.fullmatch(r"09\d{9}", number):
        return "+63" + number[1:]
    if re.fullmatch(r"639\d{9}", number):
        return "+" + number
    if re.fullmatch(r"\+\d{8,15}", number):
        return number
    return None


def detect_type(recipient):
    """Email, SMS, or not valid."""
    recipient = recipient.strip()
    if not recipient:
        return None
    if "@" in recipient:
        return "email" if EMAIL_PATTERN.match(recipient) else None
    return "sms" if normalize_phone(recipient) else None


# ---------- Gmail ----------
def _gmail_login(address, app_password):
    """Log in to Gmail SMTP."""
    try:
        server = smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT, timeout=15)
    except OSError:
        raise MessagingError("Couldn't reach Gmail. Check your internet connection.")
    try:
        server.login(address, app_password)
    except smtplib.SMTPAuthenticationError:
        server.close()
        raise MessagingError("Gmail rejected this email or App Password.")
    except (smtplib.SMTPException, OSError):
        server.close()
        raise MessagingError("Gmail login failed. Try again.")
    return server


def connect_gmail(address, app_password):
    """Check Gmail + App Password."""
    address = address.strip()
    app_password = re.sub(r"\s", "", app_password)   # "abcd efgh ..." -> "abcdefgh..."
    if not EMAIL_PATTERN.match(address):
        raise MessagingError("Enter a valid Gmail address.")
    if len(app_password) != 16 or not app_password.isalpha():
        raise MessagingError("The App Password should be 16 letters.")
    _gmail_login(address, app_password).quit()
    return address, app_password


def send_email(gmail, to, subject, body, in_reply_to=None, references=None):
    """Send an email (or a reply)."""
    address, app_password = gmail
    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = to
    msg["Subject"] = subject.strip() or "(no subject)"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
    msg.set_content(body)

    server = _gmail_login(address, app_password)
    try:
        server.send_message(msg)
    except smtplib.SMTPRecipientsRefused:
        raise MessagingError("Gmail refused that recipient address.")
    except (smtplib.SMTPException, OSError):
        raise MessagingError("Gmail couldn't send the email. Try again.")
    finally:
        try:
            server.quit()
        except (smtplib.SMTPException, OSError):
            pass


# ---------- SMSGate (SMS) ----------
@dataclass(frozen=True)
class SmsGateConfig:
    """SMSGate connection details."""
    base_url: str          # e.g. http://192.168.43.1:8080
    username: str
    password: str
    path: str = SMSGATE_PATHS[0]


def build_base_url(ip_text, port_text):
    """Phone IP + port to a URL."""
    host = re.sub(r"^https?://", "", ip_text.strip(), flags=re.IGNORECASE).rstrip("/")
    port = port_text.strip()
    if ":" in host:                                  # port pasted together with the IP
        host, port = host.split(":", 1)
    if not host or not re.fullmatch(r"[A-Za-z0-9.\-]+", host):
        raise MessagingError("Enter the phone's IP address, like 192.168.43.1.")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise MessagingError("The port should be a number, usually 8080.")
    return f"http://{host}:{port}"


def _smsgate_request(method, url, config, **kwargs):
    """One HTTP request to the phone."""
    try:
        return requests.request(method, url, auth=(config.username, config.password),
                                timeout=SMSGATE_TIMEOUT, **kwargs)
    except requests.exceptions.Timeout:
        raise MessagingError("The phone took too long to respond. "
                             "Check that SMSGate's Local Server is running.")
    except requests.exceptions.ConnectionError:
        raise MessagingError("Phone not reachable. Check the IP and port, and that "
                             "both devices are on the same Wi-Fi or hotspot.")
    except requests.exceptions.RequestException:
        raise MessagingError("Couldn't talk to the phone. Try again.")


def _check_response(response):
    """Turn HTTP errors into messages."""
    if response.status_code == 401:
        raise MessagingError("Wrong SMSGate username or password.")
    if response.status_code == 400:
        try:
            reason = response.json().get("message", "")
        except ValueError:
            reason = ""
        raise MessagingError(f"SMSGate rejected the message. {reason}".strip())
    if response.status_code >= 500:
        raise MessagingError(f"SMSGate had a problem on the phone (error {response.status_code}).")
    if not response.ok:
        raise MessagingError(f"SMSGate returned an error ({response.status_code}).")


def _read_state(data):
    """Message status from SMSGate's reply."""
    state = str(data.get("state", "")).lower()
    status = SMSGATE_STATES.get(state, "queued")
    error = None
    for recipient in data.get("recipients") or []:
        if str(recipient.get("state", "")).lower() == "failed":
            status = "failed"
        error = error or recipient.get("error") or recipient.get("reason")
    return status, error


def _is_json(response):
    """Is the reply JSON?"""
    return "json" in response.headers.get("Content-Type", "")


def connect_smsgate(ip_text, port_text, username, password):
    """Check the phone and login."""
    config = SmsGateConfig(build_base_url(ip_text, port_text),
                           username.strip(), password.strip())
    if not config.username or not config.password:
        raise MessagingError("Enter the SMSGate username and password.")

    # 1. Is the phone there? (any reply at all means yes)
    _smsgate_request("GET", config.base_url + "/health", config)

    # 2. Does the login work, and which API path does this version use?
    #    Asking for a message that doesn't exist: 401 = bad login,
    #    a JSON reply = right path + good login.
    for path in SMSGATE_PATHS:
        response = _smsgate_request("GET", f"{config.base_url}{path}/jdutils-test", config)
        if response.status_code == 401:
            raise MessagingError("Wrong SMSGate username or password.")
        if response.status_code != 404 or _is_json(response):
            return replace(config, path=path)
    return config            # couldn't tell; the first send will confirm


def send_sms(config, to, body):
    """Send an SMS through the phone."""
    if len(body) > SMS_MAX_LENGTH:
        raise MessagingError(f"SMS can't be longer than {SMS_MAX_LENGTH} characters.")

    payload = {"textMessage": {"text": body}, "phoneNumbers": [to]}
    paths = [config.path] + [p for p in SMSGATE_PATHS if p != config.path]
    for path in paths:
        response = _smsgate_request("POST", config.base_url + path, config, json=payload)
        if response.status_code in (404, 405):       # this version uses the other path
            continue
        _check_response(response)
        try:
            data = response.json()
        except ValueError:
            data = {}
        status, error = _read_state(data)
        return data.get("id"), status, error, replace(config, path=path)

    raise MessagingError("SMSGate didn't accept the request. Try updating the SMSGate app.")


def get_sms_status(config, gateway_id):
    """Status of a sent SMS."""
    response = _smsgate_request("GET", f"{config.base_url}{config.path}/{gateway_id}", config)
    _check_response(response)
    return _read_state(response.json())


# SMSGate's Local Server lists received texts at GET /inbox
# (some versions use the /3rdparty/v1 prefix, so we try both).
SMSGATE_INBOX_PATHS = ["/inbox", "/3rdparty/v1/inbox"]


def get_sms_inbox(config, since_utc_iso):
    """Texts received on the phone."""
    params = {"type": "SMS", "from": since_utc_iso, "limit": 200}
    for path in SMSGATE_INBOX_PATHS:
        response = _smsgate_request("GET", config.base_url + path, config, params=params)
        if response.status_code in (404, 405):
            continue
        _check_response(response)
        try:
            data = response.json()
        except ValueError:
            raise MessagingError("SMSGate sent an unexpected reply for the inbox.")
        if isinstance(data, dict):                     # some versions wrap the list
            data = data.get("items") or data.get("messages") or []
        texts = []
        for item in data:
            texts.append({
                "id": str(item.get("id", "")),
                "sender": str(item.get("sender") or item.get("phoneNumber") or ""),
                "text": str(item.get("contentPreview") or item.get("message")
                            or item.get("text") or ""),
                "created_at": str(item.get("createdAt") or item.get("receivedAt") or ""),
            })
        return texts
    raise MessagingError("This SMSGate version can't share received texts. "
                         "Update the SMSGate app to see replies.")


# ---------- Message log (database) ----------
def log_message(user_id, msg_type, recipient, subject, body, status,
                gateway_id=None, error=None):
    """Save a message to history."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO messages (user_id, type, recipient, subject, body, status, "
        "gateway_id, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, msg_type, recipient, subject or None, body, status, gateway_id, error),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_message_status(row_id, status, error=None):
    """Update a message's status."""
    conn = get_connection()
    conn.execute("UPDATE messages SET status = ?, error = COALESCE(?, error) WHERE id = ?",
                 (status, error, row_id))
    conn.commit()
    conn.close()


def get_messages(user_id):
    """This user's message history."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, type, recipient, subject, body, status, gateway_id, error, sent_at "
        "FROM messages WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_messages(user_id, message_ids):
    """Delete selected messages."""
    conn = get_connection()
    conn.executemany("DELETE FROM messages WHERE id = ? AND user_id = ?",
                     [(mid, user_id) for mid in message_ids])
    conn.commit()
    conn.close()


def clear_messages(user_id):
    """Delete all messages."""
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
