# JD UTILS

**Julian & Darwin Utilities** is a Python desktop app for our SIA 2 (ITL313-18) final term mini project, built with PySide6 and SQLite.

- **Login system:** username and password, stored as salted PBKDF2-SHA256 hashes
- **URL Shortener:** TinyURL links with a searchable history
- **Fake Data Generator:** 10-field records saved to the database
- **SMS & Email:** send texts through SMSGate and email through Gmail, plus an SMS chat and an email inbox

## Setup (first time)

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

## Workflow

`main` is protected. All changes go through a branch and a pull request.

**1. Start**
```
cd sia2-utilities
venv\Scripts\activate
git checkout <your-branch>
git pull origin main
```
First time only: create your branch with `git checkout -b <your-branch>`.

**2. Code and test:** `python main.py`

**3. Save and upload**
```
git add .
git commit -m "what you changed"
git push
```
The first push of a new branch needs `git push -u origin <your-branch>`.

**4. Merge:** on GitHub, click **Compare & pull request → Create pull request**. The pull request is merged into `main` after it's reviewed and approved.

## Rules

- Pull before you code.
- Don't edit the same file at the same time.
- Never upload `venv/`, `data/` or any passwords.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Push rejected | `git pull --no-rebase`, then `git push` |
| `CONFLICT` after a pull | Keep the right lines, delete the `<<<<<<<` `=======` `>>>>>>>` markers, then add, commit and push |
| App errors after a pull | Delete `data\app.db` and run the app again |
| `ModuleNotFoundError` | Activate the venv, then `pip install -r requirements.txt` |
