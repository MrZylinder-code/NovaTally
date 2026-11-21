@echo off
rem Startet NovaTally ohne Bauen direkt mit Python (beim ersten Mal werden die Pakete installiert).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Erster Start: Pakete werden eingerichtet ...
  set "PY="
  py -3 --version >nul 2>nul && set "PY=py -3"
  if not defined PY set "PY=python"
  call %%PY%% -m venv .venv || goto :fehler
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fehler
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0NovaTally.pyw" %*
exit /b 0

:fehler
echo Start fehlgeschlagen. Ist Python 3.11+ installiert ("Add python.exe to PATH")?
pause
exit /b 1
