@echo off
REM Builds the Windows app: dist\JD UTILS\JD UTILS.exe
REM Double-click this file, or run "build.bat" from the project folder.

cd /d "%~dp0"
if not exist venv\Scripts\activate.bat (
    echo No venv found. First run:  python -m venv venv
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

echo Installing the app's packages and PyInstaller...
pip install -r requirements.txt
pip install "pyinstaller>=6.16"

REM --windowed       no black console window behind the app
REM --onedir         a folder with the .exe (starts faster, fewer antivirus false alarms)
REM --add-data       ships the images and icon inside the app
REM --collect-submodules faker   Faker loads its Philippine data by name, so include all of it
pyinstaller --noconfirm --clean --windowed --onedir --name "JD UTILS" --icon assets\icon.ico ^
    --add-data "assets;assets" --collect-submodules faker main.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED. Scroll up for the first red error.
    pause
    exit /b 1
)

echo.
echo Done: dist\JD UTILS\JD UTILS.exe
echo To make an installer, open installer.iss in Inno Setup and press Compile.
pause
