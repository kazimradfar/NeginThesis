; Inno Setup script: setup wizard for PyTPS (built by .github/workflows/pytps.yml after PyInstaller has
; produced dist\PyTPS). Installs per user, no administrator rights needed.
#ifndef AppVersion
  #define AppVersion "0.2.1"
#endif
#define AppName "PyTPS"

[Setup]
AppId={{3F7A2C91-58B4-4E0D-A6C2-9D1E7B40C5A8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Kazim Radfar
AppCopyright=Copyright (C) 2026 Kazim Radfar
AppComments=Educational radiotherapy treatment planning system (not for clinical use)
DefaultDirName={localappdata}\Programs\PyTPS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\pytps\resources\pytps.ico
UninstallDisplayIcon={app}\PyTPS.exe
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\installer_out
OutputBaseFilename=PyTPS_Setup_v{#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\PyTPS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\PyTPS.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PyTPS.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PyTPS.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
