; Inno Setup script: packs dist\JD UTILS into one installer, installer\JD_UTILS_Setup.exe.
; Run build.bat first, then open this file in Inno Setup and press Compile (Ctrl+F9).

#define AppName "JD UTILS"
#define AppVersion "1.0"
#define AppExe "JD UTILS.exe"

[Setup]
; Fixed ID so a newer installer updates the existing install instead of adding a second copy.
AppId={{C41B9C9F-F9BF-42BA-ACAD-A3D634EC2A79}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Julian & Darwin
; "lowest" installs for the current user without asking for admin rights
; ({autopf} then means %LOCALAPPDATA%\Programs).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=JD_UTILS_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Everything PyInstaller made. User data lives in %APPDATA%\JD UTILS, not here,
; so uninstalling or updating never deletes accounts or history.
Source: "dist\JD UTILS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
