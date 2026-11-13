# JD UTILS

**Julian & Darwin Utilities** is a Python desktop app for our SIA 2 (ITL313-18) final term mini project, built with PySide6 and SQLite.

- **Login system:** username and password, stored as salted PBKDF2-SHA256 hashes
- **URL Shortener:** TinyURL links that open the page directly, with a searchable history (optional own API token per account)
- **Fake Data Generator:** fake Filipino people with the fields you pick and an AI photo, saved to the database, shown as an ID card and downloadable as Excel, PDF or PNG
- **SMS & Email:** send texts through SMSGate and email through Gmail, plus an SMS chat and an email inbox. Logins are saved to your account with encrypted passwords

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

## Build the Windows app (.exe and installer)

1. Run `build.bat` (double-click it, or type `build.bat` in the project folder). It takes a few minutes and makes `dist\JD UTILS\JD UTILS.exe`. Test that `.exe` first.
2. Install **Inno Setup** from jrsoftware.org (free), open `installer.iss` and press **Compile** (Ctrl+F9). The installer is `installer\JD_UTILS_Setup.exe`, the one file to share.

- The installed app keeps its database in `%APPDATA%\JD UTILS`, separate from `data\` used by `python main.py`, so accounts made while coding don't carry over.
- Windows may say "Windows protected your PC" because the app isn't signed: click **More info → Run anyway**.
- After changing the code, run `build.bat` again (and recompile the installer). To ship an update, raise `AppVersion` in `installer.iss`.

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
| "TinyURL rejected the API token" | Clear the TINYURL TOKEN box and SAVE to use the built-in token, or paste a working one |
