# Startet die gebaute EXE im Demo-Modus ohne Fenster und prueft, ob Server und Oberflaeche antworten.
# Aufruf:  pwsh tools/smoke_test.ps1 [-Exe dist\NovaTally.exe]
param([string]$Exe = "dist\NovaTally.exe")
$ErrorActionPreference = "Stop"

$env:NOVATALLY_DATA = Join-Path ([System.IO.Path]::GetTempPath()) ("novatally-smoke-" + [guid]::NewGuid())
$headers = @{ "X-NovaTally" = "1" }
$base = "http://127.0.0.1:47815"
$p = Start-Process -FilePath $Exe -ArgumentList "--demo", "--headless" -PassThru
try {
  $ping = $null
  for ($i = 0; $i -lt 30 -and -not $ping; $i++) {
    Start-Sleep -Seconds 1
    try { $ping = Invoke-RestMethod -Uri "$base/api/ping" -Headers $headers } catch { }
  }
  if (-not $ping -or $ping.app -ne "NovaTally") { throw "EXE antwortet nicht" }
  $html = Invoke-WebRequest -Uri "$base/" -UseBasicParsing
  if ($html.Content -notmatch "app.js") { throw "Oberflaeche fehlt in der EXE" }
  $o = Invoke-RestMethod -Uri "$base/api/overview?range=30" -Headers $headers
  Write-Host "OK: NovaTally $($ping.version) laeuft - $($o.games) Spiele, $($o.sessions) Sitzungen in der Demo"
  # Update-Suche aus der gebauten EXE (prueft u. a. die SSL-Zertifikate im PyInstaller-Paket)
  try {
    $u = Invoke-RestMethod -Uri "$base/api/update/check" -Headers $headers -TimeoutSec 60
    Write-Host "OK: Update-Suche aus der EXE - neueste Version $($u.latest), neuer: $($u.newer)"
  } catch {
    throw "Update-Suche aus der EXE fehlgeschlagen: $($_.ErrorDetails.Message)"
  }
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  # Eine PyInstaller-EXE laeuft als zwei Prozesse (Starter + Programm) - beide beenden
  Get-Process NovaTally -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort 47815 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
  }
  Remove-Item -Recurse -Force $env:NOVATALLY_DATA -ErrorAction SilentlyContinue
}
