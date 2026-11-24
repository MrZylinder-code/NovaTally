; NovaTally – Installer (Inno Setup 6)
; Bauen:  ISCC /DMyAppVersion=1.3.0 installer\NovaTally.iss              -> dist\NovaTally-Setup.exe (enthält die EXE)
;         ISCC /DMyAppVersion=1.3.0 /DWebSetup installer\NovaTally.iss   -> dist\NovaTally-WebSetup.exe
;           (klein; lädt beim Installieren die neueste NovaTally.exe von GitHub und prüft ihre SHA-256-Prüfsumme)
;
; Standard: Installation nur für den aktuellen Benutzer nach %LOCALAPPDATA%\Programs\NovaTally –
; ohne Administratorrechte, und der Update-Button kann die EXE dort selbst ersetzen.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "NovaTally"
#define MyAppExe "NovaTally.exe"
#define MyAppURL "https://github.com/MrZylinder-code/NovaTally"
#define WebView2Guid "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
#define LatestUrl "https://github.com/MrZylinder-code/NovaTally/releases/latest/download/"

[Setup]
AppId={{38FBF82F-2686-499D-BAED-00986B4A6DB2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
#ifdef WebSetup
AppVerName={#MyAppName}
#else
AppVerName={#MyAppName} {#MyAppVersion}
#endif
AppPublisher=MrZylinder-code
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile=..\novatally\web\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
OutputDir=..\dist
#ifdef WebSetup
OutputBaseFilename=NovaTally-WebSetup
#else
OutputBaseFilename=NovaTally-Setup
#endif
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.TaskAutostart=Mit Windows starten (empfohlen – sonst wird nicht erfasst)
en.TaskAutostart=Start with Windows (recommended – otherwise nothing is tracked)
de.TaskDesktop=Verknüpfung auf dem Desktop anlegen
en.TaskDesktop=Create a desktop shortcut
de.TaskGroup=Optionen:
en.TaskGroup=Options:
de.RunNow=NovaTally jetzt starten
en.RunNow=Start NovaTally now
de.CheckTitle=Systemprüfung
en.CheckTitle=System check
de.CheckDesc=NovaTally prüft, ob dein PC alles Nötige mitbringt.
en.CheckDesc=NovaTally checks whether your PC has everything it needs.
de.CheckIntro=Voraussetzungen für NovaTally:
en.CheckIntro=Requirements for NovaTally:
de.Ok=erfüllt
en.Ok=OK
de.Missing=fehlt
en.Missing=missing
de.ReqWindows=Windows 10 oder 11
en.ReqWindows=Windows 10 or 11
de.Req64=64-Bit-System
en.Req64=64-bit system
de.ReqWebView=Microsoft WebView2 (für das NovaTally-Fenster)
en.ReqWebView=Microsoft WebView2 (for the NovaTally window)
de.WebViewHint=wird nach der Installation angeboten – ohne öffnet NovaTally im Browser
en.WebViewHint=will be offered after installation – without it NovaTally opens in your browser
de.ReqInternet=Internetverbindung (lädt die aktuelle NovaTally-Version, ca. 22 MB)
en.ReqInternet=Internet connection (downloads the latest NovaTally version, about 22 MB)
de.DownloadFailed=Die aktuelle NovaTally-Version konnte nicht heruntergeladen werden:%n%n%1%n%nBitte Internetverbindung prüfen und erneut versuchen – oder den vollständigen Installer „NovaTally-Setup.exe“ verwenden.
en.DownloadFailed=The latest NovaTally version could not be downloaded:%n%n%1%n%nPlease check your internet connection and try again – or use the full installer "NovaTally-Setup.exe".
de.ShaInvalid=Die Prüfsummen-Datei auf GitHub ist unlesbar.
en.ShaInvalid=The checksum file on GitHub is unreadable.
de.ReqDisk=Speicherplatz: ca. 60 MB
en.ReqDisk=Disk space: about 60 MB
de.ReqAdmin=Administratorrechte: nicht nötig (Installation nur für dich)
en.ReqAdmin=Administrator rights: not required (installs for you only)
de.ReqData=Deine Spieldaten liegen getrennt unter %APPDATA%\NovaTally und bleiben bei Updates erhalten.
en.ReqData=Your play data is stored separately in %APPDATA%\NovaTally and is kept on updates.
de.WebViewAsk=Für das eigene NovaTally-Fenster wird Microsoft WebView2 benötigt. Es ist auf diesem PC nicht installiert.%n%nJetzt kostenlos von Microsoft herunterladen und installieren?%n%n(Ohne WebView2 öffnet NovaTally seine Oberfläche im Browser.)
en.WebViewAsk=The NovaTally window needs Microsoft WebView2, which is not installed on this PC.%n%nDownload and install it from Microsoft now (free)?%n%n(Without WebView2, NovaTally opens in your browser.)
de.WebViewFailed=WebView2 konnte nicht installiert werden. NovaTally öffnet seine Oberfläche dann im Browser.
en.WebViewFailed=WebView2 could not be installed. NovaTally will open in your browser instead.
de.DeleteData=Sollen auch deine erfassten Spielzeiten gelöscht werden?%n%n(%APPDATA%\NovaTally – alle Sitzungen und Einstellungen)%n%nWähle „Nein“, wenn du NovaTally später wieder installieren möchtest.
en.DeleteData=Do you also want to delete your recorded play time?%n%n(%APPDATA%\NovaTally – all sessions and settings)%n%nChoose "No" if you might reinstall NovaTally later.

[Tasks]
Name: "autostart"; Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:TaskGroup}"
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:TaskGroup}"; Flags: unchecked

[Files]
#ifdef WebSetup
; vorher in NextButtonClick heruntergeladen und per SHA-256 geprüft
Source: "{tmp}\{#MyAppExe}"; DestDir: "{app}"; Flags: external ignoreversion
#else
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Merker für NovaTally: installiert per Setup, Autostart-Wahl des Installers
Root: HKCU; Subkey: "Software\NovaTally"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\NovaTally"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "1"; Tasks: autostart
Root: HKCU; Subkey: "Software\NovaTally"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "0"; Tasks: not autostart
; Autostart – gleiches Format, das NovaTally selbst schreibt
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NovaTally"; ValueData: """{app}\{#MyAppExe}"" --autostart"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:RunNow}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Reste vom Update-Button
Type: files; Name: "{app}\NovaTally.old.exe"
Type: files; Name: "{app}\NovaTally.new.exe"

[Code]
function IsWebView2Installed(): Boolean;
var
  V: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', V) and (V <> '') and (V <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', V) and (V <> '') and (V <> '0.0.0.0'));
end;

#ifdef WebSetup
var
  DownloadPage: TDownloadWizardPage;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

{ SHA-256 aus der .sha256-Datei des Releases lesen (64 Hexzeichen am Anfang) }
function ReadSha(): String;
var
  Raw: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(ExpandConstant('{tmp}\{#MyAppExe}.sha256'), Raw) then
    Result := Lowercase(Copy(Trim(String(Raw)), 1, 64));
  if Length(Result) <> 64 then
    RaiseException(CustomMessage('ShaInvalid'));
end;

{ Neueste NovaTally.exe laden – Inno Setup prüft die SHA-256-Prüfsumme und bricht bei Abweichung ab }
procedure DownloadLatest();
var
  Sha: String;
begin
  if WizardSilent() then
  begin
    DownloadTemporaryFile('{#LatestUrl}{#MyAppExe}.sha256', '{#MyAppExe}.sha256', '', nil);
    Sha := ReadSha();
    DownloadTemporaryFile('{#LatestUrl}{#MyAppExe}', '{#MyAppExe}', Sha, nil);
  end
  else
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#LatestUrl}{#MyAppExe}.sha256', '{#MyAppExe}.sha256', '');
    DownloadPage.Show;
    try
      DownloadPage.Download;
      Sha := ReadSha();
      DownloadPage.Clear;
      DownloadPage.Add('{#LatestUrl}{#MyAppExe}', '{#MyAppExe}', Sha);
      DownloadPage.Download;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    try
      DownloadLatest();
    except
      SuppressibleMsgBox(FmtMessage(CustomMessage('DownloadFailed'), [GetExceptionMessage()]), mbCriticalError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;
#endif

function Mark(Ok: Boolean): String;
begin
  if Ok then Result := '✓  ' else Result := '✗  ';
end;

procedure InitializeWizard();
var
  Page: TOutputMsgMemoWizardPage;
  Text: String;
  WebView: Boolean;
begin
  WebView := IsWebView2Installed();
  Text :=
    CustomMessage('CheckIntro') + #13#10#13#10 +
    Mark(True) + CustomMessage('ReqWindows') + '  (' + GetWindowsVersionString() + ')' + #13#10 +
    Mark(IsWin64()) + CustomMessage('Req64') + #13#10;
  if WebView then
    Text := Text + Mark(True) + CustomMessage('ReqWebView') + #13#10
  else
    Text := Text + Mark(False) + CustomMessage('ReqWebView') + ' – ' + CustomMessage('WebViewHint') + #13#10;
  Text := Text +
#ifdef WebSetup
    Mark(True) + CustomMessage('ReqInternet') + #13#10 +
#endif
    Mark(True) + CustomMessage('ReqDisk') + #13#10 +
    Mark(True) + CustomMessage('ReqAdmin') + #13#10#13#10 +
    CustomMessage('ReqData');
  Page := CreateOutputMsgMemoPage(wpWelcome, CustomMessage('CheckTitle'), CustomMessage('CheckDesc'), '', Text);
#ifdef WebSetup
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
#endif
end;

{ Laufendes NovaTally sauber beenden (speichert die aktuelle Sitzung), notfalls hart }
procedure StopRunningApp();
var
  Rc: Integer;
  Exe: String;
begin
  Exe := ExpandConstant('{app}\{#MyAppExe}');
  if FileExists(Exe) then
    Exec(Exe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExe}', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
#ifdef WebSetup
  { Rückfall, falls der Download noch nicht passiert ist (z. B. bei stiller Installation) }
  if not FileExists(ExpandConstant('{tmp}\{#MyAppExe}')) then
  try
    DownloadLatest();
  except
    Result := FmtMessage(CustomMessage('DownloadFailed'), [GetExceptionMessage()]);
    Exit;
  end;
#endif
  StopRunningApp();
end;

procedure InstallWebView2();
var
  Rc: Integer;
begin
  try
    DownloadTemporaryFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703', 'MicrosoftEdgeWebview2Setup.exe', '', nil);
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_SHOW, ewWaitUntilTerminated, Rc) or (Rc <> 0) then
      MsgBox(CustomMessage('WebViewFailed'), mbInformation, MB_OK);
  except
    MsgBox(CustomMessage('WebViewFailed'), mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Der Installer entscheidet über den Autostart – auch wenn NovaTally ihn früher selbst eingetragen hat }
    if not WizardIsTaskSelected('autostart') then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NovaTally');
    if (not WizardSilent()) and (not IsWebView2Installed()) then
      if MsgBox(CustomMessage('WebViewAsk'), mbConfirmation, MB_YESNO) = IDYES then
        InstallWebView2();
  end;
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NovaTally');
    if SuppressibleMsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{userappdata}\NovaTally'), True, True, True);
  end;
end;
