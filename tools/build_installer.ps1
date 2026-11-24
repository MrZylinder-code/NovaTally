# Baut dist\NovaTally-Setup.exe mit Inno Setup (erwartet dist\NovaTally.exe).
# Fehlt Inno Setup, wird es per winget oder Chocolatey installiert (falls vorhanden).
# Aufruf:  pwsh tools/build_installer.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Iscc {
  $candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
  )
  foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
  Write-Host "Inno Setup nicht gefunden - wird installiert ..."
  if (Get-Command choco -ErrorAction SilentlyContinue) {
    choco install innosetup -y --no-progress | Out-Null
  } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
  }
  $iscc = Find-Iscc
}
if (-not $iscc) { throw "Inno Setup (ISCC.exe) nicht gefunden. Bitte von https://jrsoftware.org/isdl.php installieren." }
if (-not (Test-Path "dist\NovaTally.exe")) { throw "dist\NovaTally.exe fehlt - zuerst tools\build_exe.py ausfuehren." }

$version = (python -c "import novatally; print(novatally.__version__)").Trim()
Write-Host "Baue Installer fuer Version $version mit $iscc"
& $iscc "/Qp" "/DMyAppVersion=$version" "installer\NovaTally.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup ist mit Fehler $LASTEXITCODE abgebrochen." }
& $iscc "/Qp" "/DMyAppVersion=$version" "/DWebSetup" "installer\NovaTally.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup (Web-Installer) ist mit Fehler $LASTEXITCODE abgebrochen." }
foreach ($f in @("NovaTally-Setup.exe", "NovaTally-WebSetup.exe")) {
  if (-not (Test-Path "dist\$f")) { throw "dist\$f wurde nicht erzeugt." }
  Write-Host "Fertig: $root\dist\$f ($([math]::Round((Get-Item dist\$f).Length / 1MB, 1)) MB)"
}
