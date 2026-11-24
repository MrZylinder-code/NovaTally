"""Autostart über HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (nur Windows)."""

import logging
import os
import sys
from pathlib import Path

from . import APP_NAME
from .config import IS_WINDOWS

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported():
    return IS_WINDOWS


def installed_exe():
    """Pfad der per Setup installierten NovaTally.exe – oder None (nicht installiert bzw. Datei fehlt)."""
    if not IS_WINDOWS:
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETUP_KEY) as k:
            folder = winreg.QueryValueEx(k, "InstallDir")[0]
    except OSError:
        return None
    exe = Path(folder) / "NovaTally.exe"
    return str(exe) if exe.is_file() else None


def stray_copy(current_exe, installed):
    """Läuft eine andere NovaTally.exe als die installierte? Dann den Pfad der installierten, sonst None."""
    if not installed or not current_exe:
        return None
    same = os.path.normcase(os.path.abspath(current_exe)) == os.path.normcase(os.path.abspath(installed))
    return None if same else installed


def autostart_target(frozen, current_exe, installed):
    """Welche EXE soll mit Windows starten? Gibt es eine Installation, immer die installierte –
    damit eine zufällig gestartete Kopie (z. B. aus „Downloads“) den Autostart nicht übernimmt."""
    if frozen:
        return installed or current_exe
    return None  # aus dem Quellcode gestartet: siehe command()


def command():
    """Befehl, der beim Windows-Start ausgeführt wird."""
    if getattr(sys, "frozen", False):
        return f'"{autostart_target(True, sys.executable, installed_exe())}" --autostart'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parent.parent / "NovaTally.pyw"
    return f'"{exe}" "{script}" --autostart'


def current():
    """Eingetragener Befehl oder None."""
    if not IS_WINDOWS:
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, APP_NAME)[0]
    except OSError:
        return None


def is_enabled():
    return current() is not None


def set_enabled(enabled):
    if not IS_WINDOWS:
        return False
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass
    log.info("Autostart %s", "eingeschaltet" if enabled else "ausgeschaltet")
    return True


SETUP_KEY = r"Software\NovaTally"  # vom Installer angelegt


def installer_choice():
    """Autostart-Wahl im Installer: True/False – oder None, wenn nicht per Setup installiert."""
    if not IS_WINDOWS:
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETUP_KEY) as k:
            return bool(winreg.QueryValueEx(k, "InstallerAutostart")[0])
    except OSError:
        return None


LEGACY_VALUE = "Spielzeit"  # Eintrag der früheren Version


def remove_legacy():
    """Entfernt den Autostart-Eintrag der früheren Version „Spielzeit“. True, wenn es ihn gab."""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            winreg.QueryValueEx(k, LEGACY_VALUE)
            winreg.DeleteValue(k, LEGACY_VALUE)
    except OSError:
        return False
    log.info("Alten Autostart-Eintrag „%s“ entfernt", LEGACY_VALUE)
    return True


def repair():
    """Ist Autostart an, aber zeigt auf einen anderen Pfad, wird er korrigiert –
    auf die installierte Version, falls es eine gibt, sonst auf diesen Start."""
    cur = current()
    if cur and os.path.normcase(cur) != os.path.normcase(command()):
        set_enabled(True)
