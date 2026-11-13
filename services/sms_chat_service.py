"""Feature 3 logic for SMS CHAT: turns sent texts and received texts into conversations.

Sent texts come from the messages table and received ones from sms_inbox. Both
are merged per phone number and sorted by time. Privacy rule: a received text is
only saved if it comes from a number the user already texted through JD UTILS,
and only if it arrived after that first text. Everything else from the phone's
inbox is never stored.
"""

from datetime import datetime, timedelta, timezone

from database.db import get_connection
from services.messaging_service import normalize_phone

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_local():
    return datetime.now().strftime(TIME_FORMAT)


# SMSGate reports times in UTC (e.g. 2026-03-05T08:41:00Z); convert to local time
# so they sort correctly next to our own local timestamps.
def parse_phone_time(text):
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime(TIME_FORMAT)


# For each number: when did this user first text it? Used for the privacy rule.
def first_sent_times(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT recipient, MIN(sent_at) AS first FROM messages "
        "WHERE user_id = ? AND type = 'sms' AND status != 'failed' GROUP BY recipient",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["recipient"]: r["first"] for r in rows}


# Ask SMSGate for texts since the earliest first text; nothing older can be a reply.
def inbox_since_utc(first_sent):
    earliest = min(first_sent.values())
    local = datetime.strptime(earliest, TIME_FORMAT).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Save replies from numbers we texted. Everything else goes into "others", which is
# only shown in memory when the user turns off the "only people I texted" filter.
def save_incoming(user_id, texts, first_sent):
    conn = get_connection()
    new, others, fresh = 0, [], []
    for t in texts:
        phone = normalize_phone(t["sender"])
        received_at = parse_phone_time(t["created_at"])
        if not received_at:
            continue
        # A time more than 5 minutes in the future is a carrier time-zone mistake. We check
        # every 5 seconds, so "now" (when JD UTILS first saw it) is the real arrival time.
        if received_at > (datetime.now() + timedelta(minutes=5)).strftime(TIME_FORMAT):
            received_at = now_local()
        # A text's own id + sender + time. The UNIQUE key in sms_inbox ignores repeats, so
        # asking the phone every 5 seconds never saves the same text twice.
        key = f"{t['id']}|{phone or t['sender']}|{t['created_at']}"
        if not phone or phone not in first_sent or received_at < first_sent[phone]:
            others.append({"phone": phone or t["sender"], "body": t["text"], "at": received_at,
                           "mine": 0, "status": "received", "error": None, "id": 0,
                           "key": key, "outside": True})
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO sms_inbox (user_id, phone, body, received_at, external_key) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, phone, t["text"], received_at, key),
        )
        new += cur.rowcount
        if cur.rowcount:
            fresh.append({"phone": phone, "body": t["text"]})
    conn.commit()
    conn.close()
    # fresh = replies saved just now, used for the desktop notification.
    return new, others, fresh


# For "show everyone": the last 7 days (or since the first text, if that's earlier).
def everyone_since_utc(first_sent, days=7):
    week = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return min(week, inbox_since_utc(first_sent)) if first_sent else week


# One query for both directions: sent texts (mine = 1) UNION received texts (mine = 0),
# in time order. Optionally only for one phone number.
def _all_texts(conn, user_id, phone=None):
    sql = (
        "SELECT recipient AS phone, body, sent_at AS at, 1 AS mine, status, error, id "
        "FROM messages WHERE user_id = ? AND type = 'sms' {f1} "
        "UNION ALL "
        "SELECT phone, body, received_at, 0, 'received', NULL, id "
        "FROM sms_inbox WHERE user_id = ? {f2} "
        "ORDER BY at, mine DESC, id"
    )
    if phone:
        sql = sql.format(f1="AND recipient = ?", f2="AND phone = ?")
        args = (user_id, phone, user_id, phone)
    else:
        sql = sql.format(f1="", f2="")
        args = (user_id, user_id)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _contacts(conn, user_id):
    rows = conn.execute("SELECT phone, name, last_read_at FROM contacts WHERE user_id = ?",
                        (user_id,)).fetchall()
    return {r["phone"]: dict(r) for r in rows}


# One entry per number: name, last message, time and unread count. Unread = received
# texts newer than the time the conversation was last opened (contacts.last_read_at).
def list_conversations(user_id):
    conn = get_connection()
    texts = _all_texts(conn, user_id)
    contacts = _contacts(conn, user_id)
    conn.close()

    convos = {}
    for phone, c in contacts.items():
        convos[phone] = {"phone": phone, "name": c["name"], "last_text": "",
                         "last_at": "", "last_mine": True, "unread": 0}
    for t in texts:
        c = convos.setdefault(t["phone"], {"phone": t["phone"], "name": None, "unread": 0})
        c.update(last_text=t["body"], last_at=t["at"], last_mine=bool(t["mine"]))
        last_read = (contacts.get(t["phone"]) or {}).get("last_read_at")
        if not t["mine"] and (last_read is None or t["at"] > last_read):
            c["unread"] += 1
        if c.get("name") is None and t["phone"] in contacts:
            c["name"] = contacts[t["phone"]]["name"]
    return sorted(convos.values(), key=lambda c: c["last_at"] or "9999", reverse=True)


def get_thread(user_id, phone):
    conn = get_connection()
    texts = _all_texts(conn, user_id, phone)
    conn.close()
    return texts


def unread_total(user_id):
    return sum(c["unread"] for c in list_conversations(user_id))


def ensure_contact(user_id, phone):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO contacts (user_id, phone) VALUES (?, ?)",
                 (user_id, phone))
    conn.commit()
    conn.close()


def rename_contact(user_id, phone, name):
    ensure_contact(user_id, phone)
    conn = get_connection()
    conn.execute("UPDATE contacts SET name = ? WHERE user_id = ? AND phone = ?",
                 (name.strip() or None, user_id, phone))
    conn.commit()
    conn.close()


def mark_read(user_id, phone):
    ensure_contact(user_id, phone)
    conn = get_connection()
    conn.execute("UPDATE contacts SET last_read_at = ? WHERE user_id = ? AND phone = ?",
                 (now_local(), user_id, phone))
    conn.commit()
    conn.close()


# Removes the conversation from JD UTILS only; the texts stay on the phone.
def delete_received(user_id, inbox_id):
    conn = get_connection()
    conn.execute("DELETE FROM sms_inbox WHERE id = ? AND user_id = ?", (inbox_id, user_id))
    conn.commit()
    conn.close()


def delete_conversation(user_id, phone):
    conn = get_connection()
    conn.execute("DELETE FROM sms_inbox WHERE user_id = ? AND phone = ?", (user_id, phone))
    conn.execute("DELETE FROM messages WHERE user_id = ? AND type = 'sms' AND recipient = ?",
                 (user_id, phone))
    conn.execute("DELETE FROM contacts WHERE user_id = ? AND phone = ?", (user_id, phone))
    conn.commit()
    conn.close()
