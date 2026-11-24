# Testet dist\NovaTally-WebSetup.exe: still installieren (laedt die neueste NovaTally.exe von GitHub),
# pruefen, dass genau die veroeffentlichte Datei installiert wurde, starten, deinstallieren.
# Aufruf:  pwsh tools/websetup_test.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$setup = "dist\NovaTally-WebSetup.exe"
$dir = Join-Path ([System.IO.Path]::GetTempPath()) ("NovaTally-WebTest-" + [guid]::NewGuid())
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{38FBF82F-2686-499D-BAED-00986B4A6DB2}_is1"
function Check([bool]$cond, [string]$msg) {
  if (-not $cond) { throw "FEHLER: $msg" }
  Write-Host "OK: $msg"
}

$size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Check ($size -lt 8) "Web-Installer ist klein ($size MB)"

$p = Start-Process -FilePath $setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
  "/DIR=`"$dir`"", "/MERGETASKS=`"!autostart,!desktopicon`"", "/LOG=`"$dir-setup.log`"") -PassThru -Wait
if ($p.ExitCode -ne 0) {
  if (Test-Path "$dir-setup.log") { Get-Content "$dir-setup.log" | Select-Object -Last 25 }
  throw "Web-Installer endete mit Code $($p.ExitCode)"
}
Check (Test-Path "$dir\NovaTally.exe") "NovaTally.exe heruntergeladen und installiert"

# Ist es genau die veroeffentlichte Datei?
$published = (Invoke-RestMethod -Uri "https://github.com/MrZylinder-code/NovaTally/releases/latest/download/NovaTally.exe.sha256").ToString().Trim().Substring(0, 64).ToLower()
$installed = (Get-FileHash "$dir\NovaTally.exe" -Algorithm SHA256).Hash.ToLower()
Check ($installed -eq $published) "Pruefsumme stimmt mit dem neuesten Release ueberein ($($installed.Substring(0, 12))...)"
Check (Test-Path $uninstKey) "Eintrag unter 'Apps & Features' vorhanden"

& (Join-Path $PSScriptRoot "smoke_test.ps1") -Exe "$dir\NovaTally.exe"

$p = Start-Process -FilePath "$dir\unins000.exe" -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru -Wait
for ($i = 0; $i -lt 30 -and (Test-Path "$dir\NovaTally.exe"); $i++) { Start-Sleep -Milliseconds 500 }
Check (-not (Test-Path "$dir\NovaTally.exe")) "wieder deinstalliert"
Check (-not (Test-Path $uninstKey)) "Eintrag unter 'Apps & Features' entfernt"
Write-Host "Web-Installer-Test bestanden."
