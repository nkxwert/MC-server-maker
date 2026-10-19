; Bartizan installer (Inno Setup 6). Built by the CI workflow:
;   iscc /DAppVersion=1.23.0 /DSourceDir=..\dist\Bartizan [/DHaveKorean] installer\Bartizan.iss
;
; Per-user install (no administrator prompt) into %LOCALAPPDATA%\Programs\Bartizan.
; Servers and worlds live in Documents\Bartizan and are never touched by install, update or uninstall.
;
; The app updates itself by downloading this setup and running it with
;   /VERYSILENT /SUPPRESSMSGBOXES /NORESTART [/OLDEXE="<old portable Bartizan.exe>"]
; Setup then starts the app again; /OLDEXE removes the portable single-file EXE it replaces.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Bartizan"
#endif

[Setup]
AppId={{06911409-FC75-4B94-BF00-3155830D4AD7}
AppName=Bartizan
AppVersion={#AppVersion}
AppVerName=Bartizan {#AppVersion}
AppPublisher=Bartizan
AppPublisherURL=https://github.com/nkxwert/MC-server-maker
AppSupportURL=https://github.com/nkxwert/MC-server-maker/issues
AppUpdatesURL=https://github.com/nkxwert/MC-server-maker/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Bartizan Setup
VersionInfoProductName=Bartizan
DefaultDirName={localappdata}\Programs\Bartizan
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Bartizan-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Bartizan.exe
UninstallDisplayName=Bartizan
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; an update replaces the files of the running app: close it (it saves and stops its servers itself)
CloseApplications=force
RestartApplications=no

[Languages]
#ifdef HaveKorean
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; files of the previous version that the new one no longer has
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Bartizan"; Filename: "{app}\Bartizan.exe"
Name: "{autodesktop}\Bartizan"; Filename: "{app}\Bartizan.exe"; Tasks: desktopicon

[Run]
; interactive install: offer to start it; silent update: always start it again
Filename: "{app}\Bartizan.exe"; Description: "{cm:LaunchProgram,Bartizan}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Bartizan.exe"; Flags: nowait; Check: WizardSilent

[Code]
// After moving from the portable single EXE to the installed app: remove the old EXE
// (and its .old leftover). It may still be closing, so retry for a while.
procedure DeleteOldExe();
var
  OldExe: String;
  I: Integer;
begin
  OldExe := ExpandConstant('{param:OLDEXE|}');
  if (OldExe = '') or (CompareText(ExtractFileExt(OldExe), '.exe') <> 0) then
    exit;
  if CompareText(OldExe, ExpandConstant('{app}\Bartizan.exe')) = 0 then
    exit;
  for I := 1 to 40 do
  begin
    if (not FileExists(OldExe)) or DeleteFile(OldExe) then
      break;
    Sleep(500);
  end;
  DeleteFile(OldExe + '.old');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    DeleteOldExe();
end;

// "Start Bartizan when Windows starts" (set in the app) goes away with the app
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Bartizan');
end;
