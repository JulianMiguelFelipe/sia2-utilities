"""Feature 2 logic: generate a fake Filipino person, save them, and show their data.

The user picks which fields to generate. generate_person() makes up every value
(Faker plus our own lists of common Filipino names), then keeps only the chosen
fields. The photo is an AI-generated face from thispersondoesnotexist.com.
People are saved in the fake_people table; turned-off fields are stored as NULL
and the "fields" column remembers which ones were on.
"""

import io
import random
import re
import sqlite3
import unicodedata
from datetime import date, timedelta

import requests
from faker import Faker
from PIL import Image

from database.db import get_connection
from services.messaging_service import EMAIL_PATTERN, normalize_phone

# Every request to this address returns a new, random AI face (a 1024 px JPEG).
PHOTO_URL = "https://thispersondoesnotexist.com/random-person.jpeg"
# Photos are shrunk to 360 px before saving, so each one is only about 25 KB.
PHOTO_SIZE = 360

# Every toggle on the page: (key, checkbox label, group, on by default). The groups
# become the PERSONAL / CONTACT / CARD sections. CARD fields only matter for the ID view.
FIELDS = [
    ("photo", "PHOTO", "PERSONAL", True),
    ("name", "FULL NAME", "PERSONAL", True),
    ("sex", "SEX", "PERSONAL", True),
    ("birthdate", "BIRTHDATE / AGE", "PERSONAL", True),
    ("civil_status", "CIVIL STATUS", "PERSONAL", True),
    ("blood_type", "BLOOD TYPE", "PERSONAL", True),
    ("nationality", "NATIONALITY", "PERSONAL", False),
    ("height_weight", "HEIGHT / WEIGHT", "PERSONAL", False),
    ("occupation", "OCCUPATION", "PERSONAL", True),
    ("address", "ADDRESS", "CONTACT", True),
    ("mobile", "MOBILE NUMBER", "CONTACT", True),
    ("email", "EMAIL", "CONTACT", True),
    ("id_number", "ID NUMBER", "CARD", True),
    ("validity", "ISSUED / VALID UNTIL", "CARD", True),
    ("signature", "SIGNATURE", "CARD", False),
    ("emergency", "EMERGENCY CONTACT", "CARD", False),
]
FIELD_KEYS = [key for key, *_ in FIELDS]
DEFAULT_FIELDS = [key for key, _, _, on in FIELDS if on]
CARD_KEYS = {key for key, _, group, _ in FIELDS if group == "CARD"}

# Which database columns belong to each toggle. ID number has no column here because
# it is always stored (it keeps rows unique) and only shown when its toggle is on.
FIELD_COLUMNS = {
    "photo": ["photo"],
    "name": ["first_name", "middle_name", "last_name"],
    "sex": ["sex"],
    "birthdate": ["birthdate"],
    "civil_status": ["civil_status"],
    "blood_type": ["blood_type"],
    "nationality": ["nationality"],
    "height_weight": ["height_cm", "weight_kg"],
    "occupation": ["occupation"],
    "address": ["address"],
    "mobile": ["mobile"],
    "email": ["email"],
    "emergency": ["emergency_name", "emergency_phone"],
    "validity": ["issued_on", "valid_until"],
    "signature": [],
    "id_number": [],
}
DATA_COLUMNS = [c for key in FIELD_KEYS for c in FIELD_COLUMNS[key]]

SEXES = ["Male", "Female"]
CIVIL_STATUSES = ["Single", "Married", "Widowed", "Separated"]
BLOOD_TYPES = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
# Weights make common blood types (O+, B+, A+) appear far more often than rare ones.
BLOOD_WEIGHTS = [44, 22, 26, 6, 0.6, 0.5, 0.5, 0.1]
NATIONALITIES = ["Filipino", "Chinese", "American", "Japanese", "Korean", "Indian"]
NATIONALITY_WEIGHTS = [90, 3, 2, 2, 2, 1]

MALE_NAMES = [
    "Juan", "Jose", "Mark", "John Paul", "Christian", "Carlo", "Miguel", "Paolo", "Rafael",
    "Joshua", "Angelo", "Kenneth", "Jerome", "Ramon", "Antonio", "Emmanuel", "Gabriel",
    "Adrian", "Jericho", "Francis", "Renz", "Joel", "Ronaldo", "Eduardo", "Vincent",
    "Darwin", "Julian", "Nathaniel", "Marvin", "Arnel",
]
FEMALE_NAMES = [
    "Maria", "Ana", "Kristine", "Angelica", "Patricia", "Camille", "Jasmine", "Nicole",
    "Mary Grace", "Princess", "Bea", "Andrea", "Erika", "Joanna", "Rose Ann", "Shiela",
    "Michelle", "Lorna", "Carmela", "Bianca", "Trisha", "Danica", "Jennifer", "Precious",
    "Rowena", "Liza", "Kathleen", "Aira", "Hazel", "Janine",
]
SURNAMES = [
    "Dela Cruz", "Santos", "Reyes", "Garcia", "Mendoza", "Bautista", "Villanueva", "Ramos",
    "Aquino", "Castillo", "Rivera", "Flores", "Gonzales", "Torres", "Navarro", "Domingo",
    "Salazar", "Mercado", "Aguilar", "Pascual", "Fernandez", "Lopez", "Cruz", "Del Rosario",
    "Soriano", "Tolentino", "Manalo", "Valdez", "Dizon", "Gutierrez", "Sison", "Ocampo",
    "Panganiban", "Mallari", "Lacson", "Bernardo", "Javier", "Robles", "Marquez", "Estrada",
]

# Faker's Philippine locale: addresses, provinces and mobile numbers look local.
# Its names are mostly American, so names come from the lists above instead.
_fake = Faker("en_PH")


class PhotoError(Exception):
    pass


# Faker's job list has a few cut-off entries; skip them.
BROKEN_JOBS = {"Copy", "Land", "Make", "Sub"}


# Faker writes jobs like "Engineer, broadcasting (operations)". This reorders them to
# "Broadcasting Engineer", drops the brackets, and fixes the capitalization.
def _occupation():
    job = _fake.job()
    while job in BROKEN_JOBS:
        job = _fake.job()
    job = re.sub(r"\s*\(.*?\)", "", job)
    if ", " in job:
        role, kind = job.split(", ", 1)
        job = f"{kind} {role}"
    job = re.sub(r"(^|[\s/-])(\w)", lambda m: m.group(1) + m.group(2).upper(), job)
    return re.sub(r"(?<=\s)(And|Of|The|For|In|To)(?=\s)", lambda m: m.group(1).lower(), job)


def _mobile():
    return normalize_phone(_fake.mobile_number()) or "+639" + "".join(random.choices("0123456789", k=9))


# Built from the name, e.g. juan.delacruz27@gmail.com. Accents such as ñ become n.
def _email(first, last):
    text = unicodedata.normalize("NFKD", f"{first}.{last}").encode("ascii", "ignore").decode()
    local = re.sub(r"[^a-z0-9.]", "", text.lower().replace(" ", ""))
    if random.random() < 0.5:
        local += str(random.randint(1, 99))
    return f"{local}@gmail.com"


# Realistic by age: an 18-year-old is almost always single and never widowed.
def _civil_status(age):
    if age < 25:
        weights = [85, 15, 0, 0]
    elif age < 40:
        weights = [40, 52, 2, 6]
    elif age < 60:
        weights = [15, 65, 10, 10]
    else:
        weights = [8, 55, 30, 7]
    return random.choices(CIVIL_STATUSES, weights)[0]


# Valid-until date. A Feb 29 issue date moves to Feb 28 in a year without one.
def _plus_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


# Subtracts 1 when this year's birthday hasn't happened yet.
def age_from(birthdate, today=None):
    born = date.fromisoformat(birthdate)
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


# A random 9-digit number that this user doesn't already have (shown as 000-000-000).
def new_id_number(user_id):
    conn = get_connection()
    taken = {r["id_number"] for r in conn.execute(
        "SELECT id_number FROM fake_people WHERE user_id = ?", (user_id,))}
    conn.close()
    while True:
        number = f"{random.randint(0, 999_999_999):09d}"
        if number not in taken:
            return number


# Download a face and shrink it. The check for b"\\xff\\xd8" (the start of every JPEG)
# catches the site sending an error page instead of a picture.
def fetch_photo():
    try:
        response = requests.get(PHOTO_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 20))
    except requests.exceptions.RequestException:
        raise PhotoError("Couldn't reach the photo site. Check your internet connection.")
    if not response.ok or not response.content.startswith(b"\xff\xd8"):
        raise PhotoError("The photo site didn't send a picture.")
    try:
        with Image.open(io.BytesIO(response.content)) as img:
            img = img.convert("RGB")
            img.thumbnail((PHOTO_SIZE, PHOTO_SIZE))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return out.getvalue()
    except OSError:
        raise PhotoError("The photo couldn't be read.")


# Runs in the background (the photo download can take a few seconds).
def generate_person(user_id, fields):
    fields = [key for key in FIELD_KEYS if key in fields]
    sex = random.choice(SEXES)
    male = sex == "Male"
    middle, last = random.sample(SURNAMES, 2)
    first = random.choice(MALE_NAMES if male else FEMALE_NAMES)
    born = _fake.date_of_birth(minimum_age=18, maximum_age=75)
    age = age_from(born.isoformat())
    # Height follows a bell curve around the Filipino average for each sex, and weight
    # comes from a healthy-range BMI, so the numbers look believable together.
    height = round(random.gauss(165 if male else 153, 6 if male else 5))
    bmi = min(max(random.gauss(23, 3), 17.5), 35)
    issued = date.today() - timedelta(days=random.randint(0, 3 * 365))

    everything = {
        "first_name": first, "middle_name": middle, "last_name": last,
        "sex": sex,
        "birthdate": born.isoformat(),
        "civil_status": _civil_status(age),
        "blood_type": random.choices(BLOOD_TYPES, BLOOD_WEIGHTS)[0],
        "nationality": random.choices(NATIONALITIES, NATIONALITY_WEIGHTS)[0],
        "height_cm": height,
        "weight_kg": round(bmi * (height / 100) ** 2),
        "occupation": _occupation(),
        "address": _fake.address().replace("\n", ", "),
        "mobile": _mobile(),
        "email": _email(first, last),
        "emergency_name": f"{random.choice(MALE_NAMES + FEMALE_NAMES)} {last}",
        "emergency_phone": _mobile(),
        "issued_on": issued.isoformat(),
        "valid_until": _plus_years(issued, 5).isoformat(),
    }
    # Keep only the fields the user turned on; everything else stays None (NULL).
    person = {col: None for col in DATA_COLUMNS}
    for key in fields:
        for col in FIELD_COLUMNS[key]:
            person[col] = everything.get(col)
    person["fields"] = fields
    person["id_number"] = new_id_number(user_id)
    person["photo_error"] = None
    if "photo" in fields:
        # A failed photo doesn't stop anything: the person is saved without one, and the
        # user can press NEW PHOTO later.
        try:
            person["photo"] = fetch_photo()
        except PhotoError as err:
            person["photo_error"] = str(err)
    return person


def _person(row):
    person = dict(row)
    person["fields"] = [f for f in (person.get("fields") or "").split(",") if f]
    # IDs made in an earlier version, when the ID number was always shown, keep it visible.
    if len(person["id_number"]) == 6 and "id_number" not in person["fields"]:
        person["fields"].append("id_number")
    return person


def save_person(user_id, person):
    cols = ["id_number", "fields"] + DATA_COLUMNS
    conn = get_connection()
    try:
        # If the ID number got taken in the meantime (UNIQUE rule), pick another and retry.
        for _ in range(5):
            values = [person["id_number"], ",".join(person["fields"])] + [person.get(c) for c in DATA_COLUMNS]
            try:
                cur = conn.execute(
                    f"INSERT INTO fake_people (user_id, {', '.join(cols)}) "
                    f"VALUES (?, {', '.join('?' for _ in cols)})", [user_id] + values)
                conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                person["id_number"] = new_id_number(user_id)
        raise RuntimeError("Couldn't pick a free ID number.")
    finally:
        conn.close()


def get_person(user_id, person_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM fake_people WHERE id = ? AND user_id = ?",
                       (person_id, user_id)).fetchone()
    conn.close()
    return _person(row) if row else None


def latest_person(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM fake_people WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                       (user_id,)).fetchone()
    conn.close()
    return _person(row) if row else None


# For the HISTORY table: everything except the photo (big), plus a has_photo flag.
def list_people(user_id):
    cols = ", ".join(["id", "id_number", "fields", "created_at"] + [c for c in DATA_COLUMNS if c != "photo"])
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {cols}, photo IS NOT NULL AS has_photo FROM fake_people "
        "WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [_person(r) for r in rows]


def update_person(user_id, person_id, values):
    # Only real data columns can be updated; the column names never come from user input.
    values = {k: v for k, v in values.items() if k in DATA_COLUMNS and k != "photo"}
    if not values:
        return
    conn = get_connection()
    conn.execute(f"UPDATE fake_people SET {', '.join(f'{k} = ?' for k in values)} "
                 "WHERE id = ? AND user_id = ?", list(values.values()) + [person_id, user_id])
    conn.commit()
    conn.close()


def set_photo(user_id, person_id, photo):
    conn = get_connection()
    conn.execute("UPDATE fake_people SET photo = ? WHERE id = ? AND user_id = ?",
                 (photo, person_id, user_id))
    conn.commit()
    conn.close()


def replace_photo(user_id, person_id):
    set_photo(user_id, person_id, fetch_photo())


def delete_people(user_id, ids):
    conn = get_connection()
    conn.executemany("DELETE FROM fake_people WHERE id = ? AND user_id = ?",
                     [(i, user_id) for i in ids])
    conn.commit()
    conn.close()


def clear_people(user_id):
    conn = get_connection()
    conn.execute("DELETE FROM fake_people WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# Filipino style: the middle name is shown as an initial, e.g. Juan D. Santos.
def _middle_initial(p):
    middle = (p.get("middle_name") or "").strip()
    return f" {middle[0].upper()}." if middle else ""


def full_name(p):
    if not p.get("first_name"):
        return ""
    return f"{p['first_name']}{_middle_initial(p)} {p['last_name']}"


def card_name(p):
    if not p.get("first_name"):
        return ""
    return f"{p['last_name']}, {p['first_name']}{_middle_initial(p)}".upper()


def format_id(number):
    if number and len(number) == 9 and number.isdigit():
        return f"{number[:3]}-{number[3:6]}-{number[6:]}"
    return number or ""


def shows_id(p):
    return "id_number" in p["fields"]


def format_mobile(number):
    if number and re.fullmatch(r"\+639\d{9}", number):
        return f"{number[:3]} {number[3:6]} {number[6:9]} {number[9:]}"
    return number or ""


def birthdate_text(p):
    return f"{p['birthdate']} ({age_from(p['birthdate'])})" if p.get("birthdate") else ""


def height_weight_text(p):
    if p.get("height_cm") is None:
        return ""
    return f"{p['height_cm']} cm · {p['weight_kg']} kg"


def emergency_text(p):
    if not p.get("emergency_name"):
        return ""
    return f"{p['emergency_name']} · {format_mobile(p['emergency_phone'])}"


# The display list used by the panel, the copy text and the Excel export:
# (toggle key, label, value) for every field that is on, in card order.
def details(p):
    on = set(p["fields"])
    table = [
        ("id_number", "ID No.", format_id(p["id_number"])),
        ("name", "Name", full_name(p)),
        ("sex", "Sex", p.get("sex")),
        ("birthdate", "Birthdate", birthdate_text(p)),
        ("civil_status", "Civil status", p.get("civil_status")),
        ("blood_type", "Blood type", p.get("blood_type")),
        ("nationality", "Nationality", p.get("nationality")),
        ("height_weight", "Height / weight", height_weight_text(p)),
        ("occupation", "Occupation", p.get("occupation")),
        ("address", "Address", p.get("address")),
        ("mobile", "Mobile", format_mobile(p.get("mobile"))),
        ("email", "Email", p.get("email")),
        ("emergency", "Emergency contact", emergency_text(p)),
        ("validity", "Issued", p.get("issued_on")),
        ("validity", "Valid until", p.get("valid_until")),
    ]
    return [(k, label, value or "–") for k, label, value in table if k in on]


# COPY TEXT: the person's data only. CARD fields and the photo are left out on purpose.
def plain_text(p):
    lines = ["JD UTILS · FAKE PERSON"]
    lines += [f"{label + ':':<20}{value}" for key, label, value in details(p) if key not in CARD_KEYS]
    lines.append("Fake data made with JD UTILS · not a real person")
    return "\n".join(lines)


def _required(raw, key, label, limit=120):
    value = (raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label} can't be empty.")
    if len(value) > limit:
        raise ValueError(f"{label} can be up to {limit} characters.")
    return value


def _phone(raw, key, label):
    number = normalize_phone((raw.get(key) or "").strip())
    if not number:
        raise ValueError(f"Enter a valid {label} (09XXXXXXXXX).")
    return number


def _number(raw, key, label, low, high, unit):
    text = str(raw.get(key) or "").strip()
    if not text.isdigit() or not low <= int(text) <= high:
        raise ValueError(f"{label} must be {low}-{high} {unit}.")
    return int(text)


# Checks the EDIT window. Returns only the cleaned values for fields that are on,
# or raises ValueError with a message to show the user.
def validate_edits(fields, raw):
    clean = {}
    if "name" in fields:
        clean["first_name"] = _required(raw, "first_name", "First name", 40)
        clean["last_name"] = _required(raw, "last_name", "Last name", 40)
        middle = (raw.get("middle_name") or "").strip()
        if len(middle) > 40:
            raise ValueError("Middle name can be up to 40 characters.")
        clean["middle_name"] = middle or None
    for key in ("sex", "civil_status", "blood_type"):
        if key in fields:
            clean[key] = raw[key]
    if "birthdate" in fields:
        if date.fromisoformat(raw["birthdate"]) > date.today():
            raise ValueError("Birthdate can't be in the future.")
        clean["birthdate"] = raw["birthdate"]
    if "nationality" in fields:
        clean["nationality"] = _required(raw, "nationality", "Nationality", 40)
    if "height_weight" in fields:
        clean["height_cm"] = _number(raw, "height_cm", "Height", 50, 250, "cm")
        clean["weight_kg"] = _number(raw, "weight_kg", "Weight", 20, 300, "kg")
    if "occupation" in fields:
        clean["occupation"] = _required(raw, "occupation", "Occupation", 60)
    if "address" in fields:
        clean["address"] = _required(raw, "address", "Address", 120)
    if "mobile" in fields:
        clean["mobile"] = _phone(raw, "mobile", "mobile number")
    if "email" in fields:
        email = (raw.get("email") or "").strip()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("Enter a valid email address.")
        clean["email"] = email
    if "emergency" in fields:
        clean["emergency_name"] = _required(raw, "emergency_name", "Emergency contact name", 60)
        clean["emergency_phone"] = _phone(raw, "emergency_phone", "emergency contact number")
    if "validity" in fields:
        if raw["valid_until"] <= raw["issued_on"]:
            raise ValueError("Valid until must be after the issue date.")
        clean["issued_on"], clean["valid_until"] = raw["issued_on"], raw["valid_until"]
    return clean
