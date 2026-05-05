#define MyAppName "TokenMind"
#define MyAppPublisher "TokenMind"
#ifndef MyAppVersion
#define MyAppVersion "0.1.10"
#endif

#define ProjectRoot AddBackslash(SourcePath) + "..\.."
#define AppDist ProjectRoot + "\dist-windows\TokenMind"
#define AppIcon ProjectRoot + "\packaging\windows\tokenmind.ico"

[Setup]
AppId={{B5E10D8C-3B7B-4B22-90F4-8628F75C0E48}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\TokenMind.exe
DefaultDirName={localappdata}\Programs\TokenMind
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#ProjectRoot}\dist-installer
OutputBaseFilename=TokenMindSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "{#AppDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppIcon}"; DestDir: "{app}"; DestName: "tokenmind.ico"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TokenMind"; Filename: "{app}\TokenMind.exe"; IconFilename: "{app}\tokenmind.ico"
Name: "{autodesktop}\TokenMind"; Filename: "{app}\TokenMind.exe"; IconFilename: "{app}\tokenmind.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\TokenMind.exe"; Description: "Launch TokenMind"; Flags: nowait postinstall skipifsilent
