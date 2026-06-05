; ============================================================
;  AI Blog Generator — Inno Setup Installer Script
;  Build: iscc /DMyAppVersion=x.y.z installer\installer.iss
; ============================================================

#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif

#define MyAppName "AI Blog Generator"
#define MyAppPublisher "Yoshiteru Yamakawa"
#define MyAppURL "https://github.com/yama203/blog_generator"
#define MyAppExeName "launcher\start_windows.bat"

[Setup]
AppId={{6A3E7B1C-4D2F-4A8B-9C5E-0F1D2E3A4B5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=yes
OutputBaseFilename=AI Blog Generator Setup {#MyAppVersion}
OutputDir=Output
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\AppIcon.ico
SetupIconFile=..\AppIcon.ico
WizardStyle=modern
WizardSizePercent=120

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成(&D)"; GroupDescription: "追加タスク:"

[Files]
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs
Source: "..\launcher\start_windows.bat"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "..\uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\AppIcon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\AppIcon.ico"
Name: "{group}\{#MyAppName} のアンインストール"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\AppIcon.ico"; Tasks: desktopicon

[Run]
Filename: "cmd.exe"; Parameters: "/c ""{app}\{#MyAppExeName}"""; Description: "{#MyAppName} を起動する"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\articles"
Type: filesandordirs; Name: "{app}\__pycache__"
