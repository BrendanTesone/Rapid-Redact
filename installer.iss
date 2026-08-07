; Inno Setup Script for Rapid Redact
; Packages the PyInstaller output into a professional Windows installer

#define MyAppName "Rapid Redact"
#define MyAppVersion "0.1.0"
#ifndef VersionInfoVersion
  #define VersionInfoVersion MyAppVersion
#endif
#define MyAppPublisher "Rapid Redact"
#define MyAppExeName "Rapid-Redact.exe"
#define MyAppSourceDir "dist\Rapid-Redact"

[Setup]
; Basic app information
AppId={{5D0E89B4-BD1E-4810-9664-302C128113BD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (C) 2026 {#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Update/Upgrade behavior
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#VersionInfoVersion}
; Close running app before installing
CloseApplications=yes
CloseApplicationsFilter=*.exe

; Output settings
OutputDir=installer_output
OutputBaseFilename=Rapid-Redact-Setup-{#MyAppVersion}

; Compression - fast build for CI (75% faster, ~20MB larger installer)
Compression=lzma2/fast
SolidCompression=no
InternalCompressLevel=fast

; Windows version requirements
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64compatible

; Visual settings
WizardStyle=modern

; Silent install - skip all wizard pages
DisableWelcomePage=yes
DisableReadyPage=yes
DisableDirPage=yes
DisableReadyMemo=yes
DisableFinishedPage=yes

; Privileges - always install for current user only, no admin prompt
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Include entire PyInstaller output directory
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional, user-selected)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon


[Run]
; Option to launch app after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any runtime-generated files
Type: filesandordirs; Name: "{app}\storage"
Type: filesandordirs; Name: "{app}\temp"
Type: files; Name: "{app}\*.log"
