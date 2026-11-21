@echo off
setlocal
cd /d "%~dp0"
title NovaTally bauen
echo.
echo  =============================================
echo   NovaTally - baut die Datei dist\NovaTally.exe
echo  =============================================
echo.

rem --- Python suchen (erst den Python-Launcher "py", dann "python") ---
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
  echo FEHLER: Python wurde nicht gefunden.
  echo Bitte Python 3.11 oder neuer von https://www.python.org/downloads/ installieren
  echo und beim Installieren "Add python.exe to PATH" anhaken.
  goto :fehler
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo FEHLER: Python ist zu alt. Benoetigt wird Python 3.11 oder neuer.
  goto :fehler
)

rem --- Laeuft NovaTally noch? Dann kann die EXE nicht ueberschrieben werden ---
tasklist /FI "IMAGENAME eq NovaTally.exe" 2>nul | find /I "NovaTally.exe" >nul
if not errorlevel 1 (
  echo NovaTally laeuft gerade. Bitte erst ueber das Tray-Symbol beenden.
  goto :fehler
)

echo [1/4] Virtuelle Umgebung .venv anlegen ...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fehler
)
set "VPY=.venv\Scripts\python.exe"

echo [2/4] Pakete installieren (psutil, pystray, Pillow, PyInstaller) ...
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip || goto :fehler
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller || goto :fehler

echo [3/4] Symbol pruefen ...
if not exist "novatally\web\icon.ico" "%VPY%" tools\make_icon.py || goto :fehler

echo [4/4] NovaTally.exe bauen (dauert ca. 1 Minute) ...
"%VPY%" tools\build_exe.py || goto :fehler

echo.
echo  Fertig!  Die App liegt hier:  %CD%\dist\NovaTally.exe
echo  Doppelklick darauf startet NovaTally.
echo.
start "" explorer "%CD%\dist"
pause
exit /b 0

:fehler
echo.
echo  Der Bau ist fehlgeschlagen. Die Meldungen oben zeigen den Grund.
pause
exit /b 1
