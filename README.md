# JD UTILS

**Julian & Darwin Utilities** is a Python desktop app for our SIA 2 (ITL313-18) final term mini project, built with PySide6 and SQLite.

- **Login system:** username and password, stored as salted PBKDF2-SHA256 hashes
- **URL Shortener:** TinyURL links that open the page directly, with a searchable history (optional own API token per account)
- **Fake Data Generator:** fake Filipino people with the fields you pick and an AI photo, saved to the database, shown as an ID card and downloadable as Excel, PDF or PNG
- **SMS & Email:** send texts through SMSGate and email through Gmail, plus an SMS chat and an email inbox. Logins are saved to your account with encrypted passwords

## Setup

1. Install **Python 3.10+** (tick **"Add python.exe to PATH"**) and **Git**.
2. Run:
```
git clone https://github.com/JulianMiguelFelipe/sia2-utilities.git
cd sia2-utilities
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
3. Register an account in the app. Each computer has its own database.

If PowerShell says "running scripts is disabled," run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
