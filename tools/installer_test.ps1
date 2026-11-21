# Testet dist\NovaTally-Setup.exe: still installieren, starten, mit Autostart erneut installieren
# (Update-Fall), deinstallieren - und pruefen, dass die Spieldaten dabei erhalten bleiben.
# Aufruf:  pwsh tools/installer_test.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$setup = "dist\NovaTally-Setup.exe"
$dir = Join-Path ([System.IO.Path]::GetTempPath()) ("NovaTally-Test-" + [guid]::NewGuid())
$appId = "{38FBF82F-2686-499D-BAED-00986B4A6DB2}_is1"
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$dataMarker = Join-Path $env:APPDATA "NovaTally\installer-test.txt"

function Run-Setup([string[]]$extra) {
  $setupArgs = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/DIR=`"$dir`"") + $extra
  $p = Start-Process -FilePath $setup -ArgumentList $setupArgs -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw "Setup endete mit Code $($p.ExitCode)" }
}
function Check([bool]$cond, [string]$msg) {
  if (-not $cond) { throw "FEHLER: $msg" }
  Write-Host "OK: $msg"
}

# 1) Installation ohne Autostart/Desktop
Run-Setup @("/MERGETASKS=`"!autostart,!desktopicon`"")
Check (Test-Path "$dir\NovaTally.exe") "NovaTally.exe installiert nach $dir"
Check (Test-Path $uninstKey) "Eintrag unter 'Apps & Features' vorhanden"
$entry = Get-ItemProperty $uninstKey
Check ($entry.DisplayName -eq "NovaTally") "Anzeigename '$($entry.DisplayName)', Version $($entry.DisplayVersion)"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\NovaTally.lnk"
Check (Test-Path $startMenu) "Startmenue-Verknuepfung vorhanden"
Check (-not (Get-ItemProperty $runKey -Name NovaTally -ErrorAction SilentlyContinue)) "kein Autostart, weil abgewaehlt"
Check ((Get-ItemProperty "HKCU:\Software\NovaTally").InstallerAutostart -eq 0) "Autostart-Wahl fuer NovaTally gespeichert (aus)"

# 2) Installierte EXE starten und pruefen
& (Join-Path $PSScriptRoot "smoke_test.ps1") -Exe "$dir\NovaTally.exe"

# 3) Erneut installieren (wie ein Update), diesmal mit Autostart
Run-Setup @("/MERGETASKS=`"autostart`"")
$run = (Get-ItemProperty $runKey -Name NovaTally).NovaTally
Check ($run -eq "`"$dir\NovaTally.exe`" --autostart") "Autostart eingetragen: $run"

# 4) Deinstallieren - Spieldaten muessen bleiben (Standard-Antwort 'Nein')
New-Item -ItemType Directory -Force -Path (Split-Path $dataMarker) | Out-Null
Set-Content -Path $dataMarker -Value "darf nicht geloescht werden"
$p = Start-Process -FilePath "$dir\unins000.exe" -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru -Wait
for ($i = 0; $i -lt 30 -and (Test-Path "$dir\NovaTally.exe"); $i++) { Start-Sleep -Milliseconds 500 }
Check (-not (Test-Path "$dir\NovaTally.exe")) "NovaTally.exe deinstalliert"
Check (-not (Test-Path $uninstKey)) "Eintrag unter 'Apps & Features' entfernt"
Check (-not (Get-ItemProperty $runKey -Name NovaTally -ErrorAction SilentlyContinue)) "Autostart entfernt"
Check (-not (Test-Path $startMenu)) "Startmenue-Verknuepfung entfernt"
Check (Test-Path $dataMarker) "Spieldaten in %APPDATA%\NovaTally sind erhalten geblieben"
Remove-Item -Force $dataMarker -ErrorAction SilentlyContinue
Write-Host "Installer-Test bestanden."
