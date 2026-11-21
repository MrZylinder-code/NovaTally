# Startet die gebaute EXE MIT Fenster (Demo-Modus) und prueft:
#  - NovaTally hat ein eigenes Fenster mit dem Titel "NovaTally" (kein Edge-Fenster)
#  - ein zweiter Start oeffnet kein weiteres Fenster, sondern zeigt das vorhandene
# Aufruf:  pwsh tools/window_test.ps1 [-Exe dist\NovaTally.exe]
param([string]$Exe = "dist\NovaTally.exe")
$ErrorActionPreference = "Stop"

$env:NOVATALLY_DATA = Join-Path ([System.IO.Path]::GetTempPath()) ("novatally-fenster-" + [guid]::NewGuid())
$headers = @{ "X-NovaTally" = "1" }
$base = "http://127.0.0.1:47815"
$edgeBefore = @(Get-Process msedge -ErrorAction SilentlyContinue).Count
$p = Start-Process -FilePath $Exe -ArgumentList "--demo" -PassThru
try {
  $title = $null
  for ($i = 0; $i -lt 40 -and -not $title; $i++) {
    Start-Sleep -Seconds 1
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if (-not $proc) { throw "NovaTally hat sich beendet - siehe Log in $env:NOVATALLY_DATA\demo\novatally.log" }
    $proc.Refresh()
    if ($proc.MainWindowTitle) { $title = $proc.MainWindowTitle }
  }
  if ($title -ne "NovaTally") { throw "Kein eigenes Fenster gefunden (Fenstertitel: '$title')" }
  Write-Host "OK: eigenes Fenster '$title' gehoert zu NovaTally.exe (PID $($p.Id))"

  $r = Invoke-RestMethod -Method Post -Uri "$base/api/window/show" -Headers $headers -Body "{}" -ContentType "application/json"
  if (-not $r.ok) { throw "Fenster zeigen per API fehlgeschlagen" }

  # zweiter Start: darf kein zweites Fenster/keinen zweiten Prozess hinterlassen
  $second = Start-Process -FilePath $Exe -ArgumentList "--demo" -PassThru
  if (-not $second.WaitForExit(20000)) { throw "Zweiter Start hat sich nicht beendet" }
  Start-Sleep -Seconds 2
  $count = @(Get-Process NovaTally -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "NovaTally" }).Count
  $edgeAfter = @(Get-Process msedge -ErrorAction SilentlyContinue).Count
  Write-Host "OK: zweiter Start beendet; NovaTally-Fenster: $count; Edge-Prozesse vorher/nachher: $edgeBefore/$edgeAfter"
  if ($count -ne 1) { throw "Erwartet genau ein NovaTally-Fenster, gefunden: $count" }
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  $log = Join-Path $env:NOVATALLY_DATA "demo\novatally.log"
  if (Test-Path $log) { Write-Host "--- Log:"; Get-Content $log | Select-Object -Last 15 }
  Remove-Item -Recurse -Force $env:NOVATALLY_DATA -ErrorAction SilentlyContinue
}
