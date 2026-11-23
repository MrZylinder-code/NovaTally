# Stellt den Neustart nach einem Update nach (ohne Download) und prueft, dass die neue Instanz
# danach vollstaendig funktioniert - auch nachdem die alte Instanz ihren Temp-Ordner geloescht hat.
# (Fehler bis 1.4.0: neue Instanz teilte den _MEI-Ordner der alten -> "Nicht gefunden".)
# Aufruf:  pwsh tools/restart_test.ps1 [-Exe dist\NovaTally.exe]
param([string]$Exe = "dist\NovaTally.exe")
$ErrorActionPreference = "Stop"

$data = Join-Path ([System.IO.Path]::GetTempPath()) ("novatally-restart-" + [guid]::NewGuid())
$env:NOVATALLY_DATA = $data
$env:NOVATALLY_SELFTEST_RESTART = "1"
$headers = @{ "X-NovaTally" = "1" }
$base = "http://127.0.0.1:47815"
$log = Join-Path $data "demo\novatally.log"
$p = Start-Process -FilePath $Exe -ArgumentList "--demo", "--headless" -PassThru
Remove-Item Env:\NOVATALLY_SELFTEST_RESTART
try {
  # 1) warten, bis der Neustart passiert ist
  $restarted = $false
  for ($i = 0; $i -lt 60 -and -not $restarted; $i++) {
    Start-Sleep -Seconds 1
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern "Neustart nach Update" -Quiet)) { $restarted = $true }
  }
  if (-not $restarted) { throw "Kein Neustart innerhalb von 60 s" }
  Write-Host "OK: Neustart wie nach einem Update ausgeloest"

  # 2) die alte Instanz raeumt ihren Temp-Ordner auf - danach muss die neue noch alles haben
  Start-Sleep -Seconds 15
  $ping = Invoke-RestMethod -Uri "$base/api/ping" -Headers $headers
  $html = Invoke-WebRequest -Uri "$base/" -UseBasicParsing
  if ($html.StatusCode -ne 200 -or $html.Content -notmatch "app.js") { throw "Oberflaeche fehlt nach dem Neustart" }
  $js = Invoke-WebRequest -Uri "$base/app.js" -UseBasicParsing
  if ($js.StatusCode -ne 200) { throw "app.js fehlt nach dem Neustart" }
  Write-Host "OK: Nach dem Neustart laeuft NovaTally $($ping.version) vollstaendig (Oberflaeche + Skripte vorhanden)"

  $restarts = @(Select-String -Path $log -Pattern "Neustart nach Update").Count
  if ($restarts -ne 1) { throw "Erwartet genau einen Neustart, gefunden: $restarts" }
  Write-Host "OK: genau ein Neustart"
} finally {
  if (Test-Path $log) { Write-Host "--- Log:"; Get-Content $log | Select-Object -Last 12 }
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  Get-Process NovaTally -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort 47815 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
  }
  Remove-Item -Recurse -Force $data -ErrorAction SilentlyContinue
}
