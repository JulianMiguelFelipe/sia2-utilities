"""SMS chat: conversations, replies, names, privacy filter."""

from datetime import datetime, timedelta, timezone

from database.db import get_connection
from services.messaging_service import normalize_phone

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"          # how SQLite stores our local times


def now_local():
    """Current local time."""
    return datetime.now().strftime(TIME_FORMAT)


def parse_phone_time(text):
    """Phone time to local time."""
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:                     # no timezone given: assume UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime(TIME_FORMAT)


# ---------- Who are we allowed to hear from? ----------
def first_sent_times(user_id):
    """First text sent to each number."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT recipient, MIN(sent_at) AS first FROM messages "
        "WHERE user_id = ? AND type = 'sms' AND status != 'failed' GROUP BY recipient",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["recipient"]: r["first"] for r in rows}


def inbox_since_utc(first_sent):
    """Earliest time to ask the phone about."""
    earliest = min(first_sent.values())
    local = datetime.strptime(earliest, TIME_FORMAT).astimezone()   # naive -> local
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_incoming(user_id, texts, first_sent):
    """Save allowed replies (privacy filter)."""
    conn = get_connection()
    new, others = 0, []
    for t in texts:
        phone = normalize_phone(t["sender"])
        received_at = parse_phone_time(t["created_at"])
        if not received_at:
            continue
        key = f"{t['id']}|{phone or t['sender']}|{t['created_at']}"   # same text = same key
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
    conn.commit()
    conn.close()
    return new, others


def everyone_since_utc(first_sent, days=7):
    """Start time when showing everyone."""
    week = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return min(week, inbox_since_utc(first_sent)) if first_sent else week


# ---------- Conversations ----------
def _all_texts(conn, user_id, phone=None):
    """Sent + received texts, oldest first."""
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
    """Saved names and read times."""
    rows = conn.execute("SELECT phone, name, last_read_at FROM contacts WHERE user_id = ?",
                        (user_id,)).fetchall()
    return {r["phone"]: dict(r) for r in rows}


def list_conversations(user_id):
    """Conversations, newest first."""
    conn = get_connection()
    texts = _all_texts(conn, user_id)
    contacts = _contacts(conn, user_id)
    conn.close()

    convos = {}
    for phone, c in contacts.items():                  # chats started but empty
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
    """All texts with one number."""
    conn = get_connection()
    texts = _all_texts(conn, user_id, phone)
    conn.close()
    return texts


def unread_total(user_id):
    """Total unread replies."""
    return sum(c["unread"] for c in list_conversations(user_id))


def ensure_contact(user_id, phone):
    """Add a number to contacts."""
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO contacts (user_id, phone) VALUES (?, ?)",
                 (user_id, phone))
    conn.commit()
    conn.close()


def rename_contact(user_id, phone, name):
    """Give a number a name."""
    ensure_contact(user_id, phone)
    conn = get_connection()
    conn.execute("UPDATE contacts SET name = ? WHERE user_id = ? AND phone = ?",
                 (name.strip() or None, user_id, phone))
    conn.commit()
    conn.close()


def mark_read(user_id, phone):
    """Mark a chat as read."""
    ensure_contact(user_id, phone)
    conn = get_connection()
    conn.execute("UPDATE contacts SET last_read_at = ? WHERE user_id = ? AND phone = ?",
                 (now_local(), user_id, phone))
    conn.commit()
    conn.close()


def delete_conversation(user_id, phone):
    """Delete a chat from JD UTILS."""
    conn = get_connection()
    conn.execute("DELETE FROM sms_inbox WHERE user_id = ? AND phone = ?", (user_id, phone))
    conn.execute("DELETE FROM messages WHERE user_id = ? AND type = 'sms' AND recipient = ?",
                 (user_id, phone))
    conn.execute("DELETE FROM contacts WHERE user_id = ? AND phone = ?", (user_id, phone))
    conn.commit()
    conn.close()
