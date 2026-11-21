"""Pfade und feste Einstellungen."""

import os
import shutil
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
    override = os.environ.get("NOVATALLY_DATA")
    if override:
        base = Path(override)
    elif IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "novatally.db"


# Früherer Name der App – Daten aus dieser Zeit werden beim ersten Start übernommen.
LEGACY_NAME = "Spielzeit"


def legacy_data_dir():
    """Datenordner der früheren Version „Spielzeit“ (None, wenn ein eigener Ordner gesetzt ist)."""
    if os.environ.get("NOVATALLY_DATA"):
        return None
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home())) / LEGACY_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / LEGACY_NAME.lower()


def migrate_legacy_db(old_dir, new_dir) -> bool:
    """Kopiert spielzeit.db (samt WAL-Dateien) als novatally.db, falls es noch keine neue Datenbank gibt.

    Die alten Dateien bleiben als Sicherung liegen.
    """
    if old_dir is None:
        return False
    old_db, new_db = Path(old_dir) / "spielzeit.db", Path(new_dir) / "novatally.db"
    if new_db.exists() or not old_db.is_file():
        return False
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(old_db) + suffix)
        if src.exists():
            shutil.copy2(src, Path(str(new_db) + suffix))
    return True


def resource_dir() -> Path:
    """Ordner mit den Web-Dateien – funktioniert auch in der PyInstaller-EXE."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "novatally"
    return Path(__file__).resolve().parent
