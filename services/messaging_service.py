"""Feature 3 logic: send email through Gmail and SMS through the SMSGate app.

Email: Gmail's SMTP server over SSL (port 465), signed in with the user's Gmail
address and a 16-letter App Password (a normal Gmail password doesn't work here).
SMS: the SMSGate Android app turns the phone into a small web server on the local
Wi-Fi. We send it HTTP requests with the phone's IP, port, username and password,
and the phone sends the text with its own SIM. Every message is logged in the
messages table with a status: queued, sent, delivered or failed.
"""

import re
import smtplib
from dataclasses import dataclass, replace
from email.message import EmailMessage

import requests

from database.db import get_connection

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465
SMS_MAX_LENGTH = 1600

# SMSGate has used two API paths over its versions. We try the older local path
# first, then the newer one, and remember whichever the phone answers.
SMSGATE_PATHS = ["/message", "/3rdparty/v1/messages"]
# SMSGate's public cloud server. It only speaks HTTPS and uses the /3rdparty/v1 paths.
CLOUD_HOST = "api.sms-gate.app"
# (seconds to connect, seconds to wait for the reply)
SMSGATE_TIMEOUT = (5, 15)

# SMSGate's own message states mapped onto our four history statuses.
SMSGATE_STATES = {
    "pending": "queued", "processed": "queued", "cancelling": "queued",
    "sent": "sent", "delivered": "delivered",
    "failed": "failed", "cancelled": "failed",
}


# An error whose message is written for the user and safe to show on screen.
class MessagingError(Exception):
    pass


# Philippine numbers: 09XXXXXXXXX or 639XXXXXXXXX become +639XXXXXXXXX.
# Other countries are accepted in +<country code> form.
def normalize_phone(text):
    number = re.sub(r"[\s\-()]", "", text)
    if re.fullmatch(r"09\d{9}", number):
        return "+63" + number[1:]
    if re.fullmatch(r"639\d{9}", number):
        return "+" + number
    if re.fullmatch(r"\+\d{8,15}", number):
        return number
    return None


# The recipient box takes either an email or a phone number; this decides which.
def detect_type(recipient):
    recipient = recipient.strip()
    if not recipient:
        return None
    if "@" in recipient:
        return "email" if EMAIL_PATTERN.match(recipient) else None
    return "sms" if normalize_phone(recipient) else None


# Opens an SSL connection to Gmail and signs in. Each failure gets its own message.
def _gmail_login(address, app_password):
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


# CONNECT for EMAIL: check the inputs, then try a real login. Spaces are removed because
# Google shows App Passwords in groups of four.
def connect_gmail(address, app_password):
    address = address.strip()
    app_password = re.sub(r"\s", "", app_password)
    if not EMAIL_PATTERN.match(address):
        raise MessagingError("Enter a valid Gmail address.")
    if len(app_password) != 16 or not app_password.isalpha():
        raise MessagingError("The App Password should be 16 letters.")
    _gmail_login(address, app_password).quit()
    return address, app_password


# In-Reply-To and References keep a reply in the same conversation thread in Gmail.
def send_email(gmail, to, subject, body, in_reply_to=None, references=None):
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


# Everything needed to reach the phone. frozen=True makes it read-only, so a changed
# path is made with replace() instead of editing a shared object.
@dataclass(frozen=True)
class SmsGateConfig:
    base_url: str
    username: str
    password: str
    path: str = SMSGATE_PATHS[0]
    cloud: bool = False


# Builds http(s)://HOST:PORT. Also accepts "192.168.1.5:8080" typed in the IP box.
# HTTPS is used when typed, on port 443, or for the cloud server; sending plain HTTP
# to an HTTPS port makes the server answer every request with a 400 error.
def build_base_url(ip_text, port_text):
    text = ip_text.strip()
    secure = text.lower().startswith("https://")
    host = re.sub(r"^https?://", "", text, flags=re.IGNORECASE).split("/")[0]
    port = port_text.strip()
    if ":" in host:
        host, port = host.split(":", 1)
    if not host or not re.fullmatch(r"[A-Za-z0-9.\-]+", host):
        raise MessagingError("Enter the phone's IP address, like 192.168.43.1.")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise MessagingError("The port should be a number, usually 8080.")
    if secure or port == "443" or host.lower() == CLOUD_HOST:
        return f"https://{host}:{port}"
    return f"http://{host}:{port}"


# One place for every request to the phone, with Basic Auth and friendly errors.
def _smsgate_request(method, url, config, **kwargs):
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


# Reads the message state from SMSGate's reply. If any recipient failed, the message failed.
def _read_state(data):
    state = str(data.get("state", "")).lower()
    status = SMSGATE_STATES.get(state, "queued")
    error = None
    for recipient in data.get("recipients") or []:
        if str(recipient.get("state", "")).lower() == "failed":
            status = "failed"
        error = error or recipient.get("error") or recipient.get("reason")
    return status, error


def _is_json(response):
    return "json" in response.headers.get("Content-Type", "")


# CONNECT for SMS: first check the server answers at all (/health), then ask for a
# message that doesn't exist. 401 means a wrong login, a non-JSON 400 means the
# address is wrong (usually http vs https), and any other answer tells us which API
# path this SMSGate version uses. The cloud server is tried with its own path first.
def connect_smsgate(ip_text, port_text, username, password):
    base_url = build_base_url(ip_text, port_text)
    cloud = CLOUD_HOST in base_url.lower()
    paths = list(reversed(SMSGATE_PATHS)) if cloud else SMSGATE_PATHS
    config = SmsGateConfig(base_url, username.strip(), password.strip(), paths[0], cloud)
    if not config.username or not config.password:
        raise MessagingError("Enter the SMSGate username and password.")

    _smsgate_request("GET", config.base_url + "/health", config)

    for path in paths:
        response = _smsgate_request("GET", f"{config.base_url}{path}/jdutils-test", config)
        if response.status_code == 401:
            raise MessagingError("Wrong SMSGate username or password.")
        if response.status_code == 400 and not _is_json(response):
            raise MessagingError("The server didn't understand the request. Check the address: "
                                 "the cloud server is https://api.sms-gate.app with port 443.")
        if response.status_code != 404 or _is_json(response):
            return replace(config, path=path)
    return config


def send_sms(config, to, body):
    if len(body) > SMS_MAX_LENGTH:
        raise MessagingError(f"SMS can't be longer than {SMS_MAX_LENGTH} characters.")

    # withDeliveryReport asks the phone to report when the text is delivered.
    payload = {"textMessage": {"text": body}, "phoneNumbers": [to],
               "withDeliveryReport": True}
    paths = [config.path] + [p for p in SMSGATE_PATHS if p != config.path]
    for path in paths:
        response = _smsgate_request("POST", config.base_url + path, config, json=payload)
        # 404/405 means this version uses the other path; try it.
        if response.status_code in (404, 405):
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
    response = _smsgate_request("GET", f"{config.base_url}{config.path}/{gateway_id}", config)
    _check_response(response)
    return _read_state(response.json())


SMSGATE_INBOX_PATHS = ["/inbox", "/3rdparty/v1/inbox"]


# Received texts since the given time, in one simple format, whichever SMSGate
# version answered (the field names differ between versions).
def get_sms_inbox(config, since_utc_iso):
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
        if isinstance(data, dict):
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


def log_message(user_id, msg_type, recipient, subject, body, status,
                gateway_id=None, error=None):
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
    conn = get_connection()
    conn.execute("UPDATE messages SET status = ?, error = COALESCE(?, error) WHERE id = ?",
                 (status, error, row_id))
    conn.commit()
    conn.close()


# Texts from the last 24 hours that may still change (queued or sent). The status tracker
# keeps checking these, even after logging out and back in.
def get_unfinished_sms(user_id, hours=24):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, gateway_id FROM messages WHERE user_id = ? AND type = 'sms' "
        "AND status IN ('queued', 'sent') AND gateway_id IS NOT NULL "
        "AND sent_at >= datetime('now', 'localtime', ?)",
        (user_id, f"-{hours} hours"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_messages(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, type, recipient, subject, body, status, gateway_id, error, sent_at "
        "FROM messages WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_messages(user_id, message_ids):
    conn = get_connection()
    conn.executemany("DELETE FROM messages WHERE id = ? AND user_id = ?",
                     [(mid, user_id) for mid in message_ids])
    conn.commit()
    conn.close()


def clear_messages(user_id):
    conn = get_connection()
    conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
