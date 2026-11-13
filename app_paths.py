"""Where the app's files live, both when run with python main.py and as the packaged .exe.

Running from source: images come from assets/ and the database goes in data/,
both inside the project folder (same as before).

Packaged with PyInstaller: images are unpacked inside the bundle (sys._MEIPASS),
and the database goes in %APPDATA%\\JD UTILS. The program folder can be read-only
(Program Files) or replaced by an update, so user data must live outside it.
"""

import os
import sys
from pathlib import Path

PACKAGED = getattr(sys, "frozen", False)
PROJECT_DIR = Path(__file__).resolve().parent

# Read-only files shipped with the app (images, icon).
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
ASSETS_DIR = BUNDLE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
ICON_PATH = ASSETS_DIR / "icon.ico"

# Writable user data (the SQLite database).
if PACKAGED:
    DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "JD UTILS"
else:
    DATA_DIR = PROJECT_DIR / "data"
