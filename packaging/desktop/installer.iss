; Compiled only by package-desktop.py after exact payload verification.
; Inno Setup is a build dependency, never an end-user prerequisite.
#ifndef PayloadRoot
  #error PayloadRoot is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputRoot
  #error OutputRoot is required
#endif
#ifndef ArtifactName
  #error ArtifactName is required
#endif

[Setup]
AppId={{53D29C4E-2932-457E-BA82-53E95B290A93}
AppName=Game Immersion Toolkit
AppVersion={#AppVersion}
AppPublisher=Game Immersion Toolkit contributors
AppPublisherURL=https://github.com/Firebird55/Game-immersion-toolkit
AppSupportURL=https://github.com/Firebird55/Game-immersion-toolkit/issues
DefaultDirName={autopf}\Game Immersion Toolkit
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputRoot}
OutputBaseFilename={#ArtifactName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile={#PayloadRoot}\LICENSE
UninstallDisplayIcon={app}\versions\{#AppVersion}\ProxyTranscriptRuntime.exe
UninstallDisplayName=Game Immersion Toolkit
CloseApplications=no
RestartApplications=no
SetupLogging=yes
UsePreviousTasks=yes

[Tasks]
Name: "startmenu"; Description: "Add a Start menu shortcut"; Flags: checkedonce
Name: "desktop"; Description: "Add a Desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Game Immersion Toolkit"; Filename: "{app}\versions\{#AppVersion}\ProxyTranscriptRuntime.exe"; Tasks: startmenu
Name: "{autodesktop}\Game Immersion Toolkit"; Filename: "{app}\versions\{#AppVersion}\ProxyTranscriptRuntime.exe"; Tasks: desktop

[Registry]
Root: HKLM; Subkey: "Software\Game Immersion Toolkit"; ValueType: string; ValueName: "Executable"; ValueData: "{app}\versions\{#AppVersion}\ProxyTranscriptRuntime.exe"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
; runasoriginaluser prevents an elevated installer from creating admin-owned
; transcript/settings stores or opening the administrator's browser profile.
Filename: "{app}\versions\{#AppVersion}\ProxyTranscriptRuntime.exe"; Description: "Open Game Immersion Toolkit"; Flags: nowait postinstall skipifsilent runasoriginaluser

; No [UninstallDelete] wildcard: uninstall removes installed payloads/shortcuts
; recorded by Setup, and preserves all per-user state and game installations.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreviousExecutable: String;
  ExitCode: Integer;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'Software\Game Immersion Toolkit',
    'Executable', PreviousExecutable) and FileExists(PreviousExecutable) then
  begin
    { The owner drains its children and releases the state lease before exit 0.
      Use the original account so an elevated installer cannot target a
      different account's data directory. Never force-kill active writers. }
    if not ExecAsOriginalUser(PreviousExecutable, '--request-quit', '',
      SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Could not contact Game Immersion Toolkit. Quit it from the tray, then retry Setup.'
    else if ExitCode <> 0 then
      Result := 'Game Immersion Toolkit has not finished stopping. Quit it from the tray and wait for its status window to close, then retry Setup.';
  end;
end;
