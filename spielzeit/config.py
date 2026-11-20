"""Pfade und feste Einstellungen."""

import os
import sys
from pathlib import Path

from . import APP_NAME

IS_WINDOWS = sys.platform == "win32"

# Wie oft die laufenden Prozesse geprüft werden (Sekunden)
POLL_SECONDS = 5
# Wie oft laufende Sitzungen zwischengespeichert werden (Sekunden)
HEARTBEAT_SECONDS = 30
# Kürzere Sitzungen werden verworfen (Sekunden)
MIN_SESSION_SECONDS = 60
# Wie oft die installierten Spiele neu eingelesen werden (Sekunden)
LIBRARY_RESCAN_SECONDS = 600
# Lokaler Port für die Oberfläche
PORT = 47815


def data_dir() -> Path:
    override = os.environ.get("SPIELZEIT_DATA")
    if override:
        base = Path(override)
    elif IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "spielzeit.db"


def resource_dir() -> Path:
    """Ordner mit den Web-Dateien – funktioniert auch in der PyInstaller-EXE."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "spielzeit"
    return Path(__file__).resolve().parent
