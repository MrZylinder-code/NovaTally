"""Installierte Spiele erkennen (Steam, Epic, GOG, Ubisoft, Xbox, typische Ordner).

Jede Quelle ist in try/except gekapselt; fehlt eine Quelle, wird sie still übersprungen.
Ergebnis: Liste von LibraryEntry(folder, key, name, source, appid).
"""

import glob
import json
import logging
import os
import re
import string
from collections import namedtuple

from .config import IS_WINDOWS
from .db import norm_path

log = logging.getLogger(__name__)

LibraryEntry = namedtuple("LibraryEntry", "folder key name source appid")

# Steam-Programme, die keine Spiele sind. Viele davon laufen dauerhaft oder parallel zu Spielen
# (Wallpaper Engine, Lossless Scaling, OBS …) und würden sonst als Spielzeit zählen.
STEAM_NON_GAMES = {
    "228980": "Steamworks Common Redistributables",
    "431960": "Wallpaper Engine",
    "250820": "SteamVR",
    "993090": "Lossless Scaling",
    "1905180": "OBS Studio",
    "629520": "Soundpad",
    "365670": "Blender",
    "1325860": "VTube Studio",
    "323910": "FaceRig",
    "1261970": "Desktop Mate",
    "480": "Spacewar",
}
STEAM_EXCLUDED_APPIDS = set(STEAM_NON_GAMES)
STEAM_EXCLUDED_WORDS = ("redistributable", "proton", "steam linux runtime", "sdk", "dedicated server")

# Unterordner in Spieleordnern, die keine Spiele sind (Launcher, Hilfsprogramme)
NON_GAME_FOLDERS = {
    "riot client", "launcher", "directxredist", "epic online services", "steam", "gog galaxy",
    "ubisoft game launcher", "ea desktop", "ea app", "origin", "battle.net", "_commonredist",
    "commonredist", "redist", "vcredist", "installer", "$recycle.bin",
}

# Quellennamen für die Anzeige
SOURCE_LABELS = {
    "steam": "Steam",
    "epic": "Epic Games",
    "gog": "GOG",
    "ubisoft": "Ubisoft Connect",
    "xbox": "Xbox / Game Pass",
    "ea": "EA",
    "riot": "Riot Games",
    "battlenet": "Battle.net",
    "ggg": "Grinding Gear Games",
    "installed": "Installierte Spiele",
    "folder": "Spieleordner",
    "custom": "Eigene Ordner",
    "manual": "Manuell",
}


# ----------------------------------------------------------------- Hilfsfunktionen
def _reg_open(root_name, path):
    import winreg  # nur unter Windows vorhanden

    root = getattr(winreg, root_name)
    for view in (winreg.KEY_READ, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)):
        try:
            return winreg.OpenKey(root, path, 0, view)
        except OSError:
            continue
    return None


def _reg_value(key, name):
    import winreg

    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _reg_subkeys(key):
    import winreg

    i = 0
    while True:
        try:
            yield winreg.EnumKey(key, i)
        except OSError:
            return
        i += 1


DRIVE_FIXED = 3


def fixed_drives(mask, drive_type):
    """Feste lokale Laufwerke ab C: aus der Laufwerks-Bitmaske (GetLogicalDrives).

    Netzlaufwerke, DVD-Laufwerke und Kartenleser werden ausgelassen: Getrennte Netzlaufwerke können
    sonst lange hängen, leere Wechsellaufwerke Fehlermeldungen auslösen.
    """
    out = []
    for i, letter in enumerate(string.ascii_uppercase):
        if i < 2 or not (mask >> i) & 1:
            continue
        root = f"{letter}:\\"
        if drive_type(root) == DRIVE_FIXED:
            out.append(root)
    return out


def _drives():
    if not IS_WINDOWS:
        return []
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        return fixed_drives(k32.GetLogicalDrives(), lambda root: k32.GetDriveTypeW(ctypes.c_wchar_p(root)))
    except Exception:  # noqa: BLE001
        return []


def folder_key(folder):
    return "folder:" + norm_path(folder)


# ---------------------------------------------------------------------- Steam
def parse_libraryfolders(text):
    """Pfade aus steamapps/libraryfolders.vdf lesen."""
    return [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"(.+?)"', text)]


def parse_acf(text):
    """appid, name und installdir aus einem appmanifest_*.acf lesen."""
    out = {}
    for field in ("appid", "name", "installdir"):
        m = re.search(r'"%s"\s+"(.*?)"' % field, text, re.IGNORECASE)
        if m:
            out[field] = m.group(1).replace("\\\\", "\\")
    return out


def steam_games(steam_path=None):
    if steam_path is None:
        if not IS_WINDOWS:
            return []
        key = _reg_open("HKEY_CURRENT_USER", r"Software\Valve\Steam")
        steam_path = _reg_value(key, "SteamPath") if key else None
        if not steam_path:
            return []
    steam_path = os.path.normpath(steam_path)
    libraries = [steam_path]
    try:
        with open(os.path.join(steam_path, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            libraries += parse_libraryfolders(f.read())
    except OSError:
        pass
    seen, out = set(), []
    for lib in libraries:
        lib = os.path.normpath(lib)
        if norm_path(lib) in seen:
            continue
        seen.add(norm_path(lib))
        for manifest in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                with open(manifest, encoding="utf-8", errors="replace") as f:
                    info = parse_acf(f.read())
            except OSError:
                continue
            appid, name, installdir = info.get("appid"), info.get("name"), info.get("installdir")
            if not (appid and name and installdir):
                continue
            if appid in STEAM_EXCLUDED_APPIDS or any(w in name.lower() for w in STEAM_EXCLUDED_WORDS):
                continue
            folder = os.path.join(lib, "steamapps", "common", installdir)
            out.append(LibraryEntry(folder, f"steam:{appid}", name, "steam", appid))
    return out


# ----------------------------------------------------------------------- Epic
def epic_games(manifest_dir=None):
    if manifest_dir is None:
        if not IS_WINDOWS:
            return []
        manifest_dir = os.path.join(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Epic", "EpicGamesLauncher", "Data", "Manifests"
        )
    out = []
    for item in glob.glob(os.path.join(manifest_dir, "*.item")):
        try:
            with open(item, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        name, loc = data.get("DisplayName"), data.get("InstallLocation")
        if not (name and loc):
            continue
        if "UE_" in (data.get("AppName") or "") or not data.get("bIsExecutable", True):
            continue  # Unreal-Engine-Installationen o. ä.
        folder = os.path.normpath(loc)
        out.append(LibraryEntry(folder, "epic:" + os.path.basename(folder).lower(), name, "epic", None))
    return out


# ------------------------------------------------------------------------ GOG
def gog_games():
    if not IS_WINDOWS:
        return []
    out = []
    root = _reg_open("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\GOG.com\Games")
    if not root:
        return out
    import winreg

    for sub in _reg_subkeys(root):
        try:
            k = winreg.OpenKey(root, sub)
        except OSError:
            continue
        name, path = _reg_value(k, "gameName"), _reg_value(k, "path")
        if name and path:
            out.append(LibraryEntry(os.path.normpath(path), f"gog:{sub}", name, "gog", None))
    return out


# -------------------------------------------------------------------- Ubisoft
def ubisoft_games():
    if not IS_WINDOWS:
        return []
    out = []
    root = _reg_open("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs")
    if not root:
        return out
    import winreg

    for sub in _reg_subkeys(root):
        try:
            k = winreg.OpenKey(root, sub)
        except OSError:
            continue
        path = _reg_value(k, "InstallDir")
        if path:
            folder = os.path.normpath(path)
            out.append(LibraryEntry(folder, folder_key(folder), os.path.basename(folder), "ubisoft", None))
    return out


# ------------------------------------------- Installierte Programme (Uninstall-Liste)
# Spielefirmen, deren Programme in der Windows-Liste „Installierte Apps“ als Spiel gelten.
# (Teilstring des Herstellers in Kleinbuchstaben, Quelle)
GAME_PUBLISHERS = (
    ("grinding gear", "ggg"),
    ("blizzard", "battlenet"),
    ("activision", "battlenet"),
    ("riot games", "riot"),
    ("electronic arts", "ea"),
    ("rockstar games", "installed"),
    ("cd projekt", "installed"),
    ("wargaming", "installed"),
    ("gaijin", "installed"),
    ("digital extremes", "installed"),
    ("hoyoverse", "installed"),
    ("cognosphere", "installed"),
    ("mihoyo", "installed"),
    ("kuro games", "installed"),
    ("square enix", "installed"),
    ("jagex", "installed"),
    ("nexon", "installed"),
    ("pearl abyss", "installed"),
    ("smilegate", "installed"),
    ("bungie", "installed"),
)

# Einträge dieser Hersteller, die KEINE Spiele sind (Launcher, Anti-Cheat, Werkzeuge).
# Wichtig v. a. für Dienste, die ständig laufen (z. B. Riot Vanguard) – sonst zählte die Uhr dauerhaft.
NON_GAME_WORDS = (
    "launcher", "battle.net", "riot client", "vanguard", "ubisoft connect", "gog galaxy",
    "epic games", "social club", "anticheat", "anti-cheat", "easyanticheat", "battleye",
    "redistributable", "directx", "runtime", "sdk", "dedicated server", "editor", "toolkit",
    "uninstall", "updater", "benchmark",
)
# Exakte Namen (als Teilwort zu gefährlich: „Dragon Age: Origins“, „SteamWorld Dig“ …)
NON_GAME_NAMES = {"origin", "ea app", "ea", "steam", "ubisoft", "rockstar games"}

UNINSTALL_KEYS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "KEY_WOW64_64KEY"),
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "KEY_WOW64_32KEY"),
    ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", None),
)


def read_uninstall_entries():
    """Alle Einträge der Windows-Liste installierter Programme (HKLM 64/32 Bit und HKCU)."""
    if not IS_WINDOWS:
        return []
    import winreg

    out = []
    for root_name, path, view in UNINSTALL_KEYS:
        access = winreg.KEY_READ | (getattr(winreg, view, 0) if view else 0)
        try:
            root = winreg.OpenKey(getattr(winreg, root_name), path, 0, access)
        except OSError:
            continue
        for sub in _reg_subkeys(root):
            try:
                k = winreg.OpenKey(root, sub)
            except OSError:
                continue
            out.append({f: _reg_value(k, f) for f in ("DisplayName", "Publisher", "InstallLocation", "DisplayIcon")})
    return out


def _folder_from_icon(icon):
    """'"C:\\Spiel\\game.exe",0' -> 'C:\\Spiel' (nur bei .exe-Symbolen)."""
    if not icon:
        return None
    path = icon.split(",")[0].strip().strip('"')
    if not path.lower().endswith(".exe"):
        return None
    return os.path.dirname(path) or None


def is_too_generic(folder):
    """Laufwerk, Programme-Ordner, Windows oder Benutzerordner sind niemals „ein Spiel“."""
    n = norm_path(folder).rstrip("\\/")
    parts = [p for p in re.split(r"[\\/]+", n) if p]
    if len(parts) < 2:
        return True
    generic = set()
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "SystemRoot", "windir", "APPDATA",
                "LOCALAPPDATA", "USERPROFILE", "PROGRAMDATA", "PUBLIC"):
        v = os.environ.get(env)
        if v:
            generic.add(norm_path(v).rstrip("\\/"))
    return n in generic


def uninstall_games(entries=None):
    """Spiele bekannter Hersteller aus der Liste installierter Programme."""
    if entries is None:
        entries = read_uninstall_entries()
    out = []
    for e in entries:
        name = (e.get("DisplayName") or "").strip()
        publisher = (e.get("Publisher") or "").lower()
        if not name:
            continue
        source = next((src for word, src in GAME_PUBLISHERS if word in publisher), None)
        low = name.lower()
        if source is None or low in NON_GAME_NAMES or any(w in low for w in NON_GAME_WORDS):
            continue
        loc = (e.get("InstallLocation") or "").strip().strip('"') or _folder_from_icon(e.get("DisplayIcon"))
        if not loc:
            continue
        folder = os.path.normpath(loc)
        if is_too_generic(folder) or os.path.basename(folder).lower() in NON_GAME_FOLDERS:
            continue
        out.append(LibraryEntry(folder, folder_key(folder), name, source, None))
    return out


# ------------------------------------------------------------- Grinding Gear Games
def ggg_games():
    """Path of Exile 1/2 als Standalone-Client (HKCU\\Software\\GrindingGearGames\\<Spiel>)."""
    if not IS_WINDOWS:
        return []
    import winreg

    out = []
    root = _reg_open("HKEY_CURRENT_USER", r"Software\GrindingGearGames")
    if not root:
        return out
    for sub in _reg_subkeys(root):
        try:
            k = winreg.OpenKey(root, sub)
        except OSError:
            continue
        loc = _reg_value(k, "InstallLocation")
        if loc:
            folder = os.path.normpath(loc.strip().strip('"'))
            out.append(LibraryEntry(folder, folder_key(folder), sub, "ggg", None))
    return out


# -------------------------------------------------------- Ordner mit Unterordnern
def subfolder_games(parent, source):
    """Jeder Unterordner von parent ist ein Spiel."""
    out = []
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return out
    for name in names:
        if name.lower() in NON_GAME_FOLDERS or name.startswith("."):
            continue
        folder = os.path.join(parent, name)
        if os.path.isdir(folder):
            out.append(LibraryEntry(folder, folder_key(folder), name, source, None))
    return out


def typical_folders():
    """(Ordner, Quelle) der typischen Spieleordner auf diesem PC."""
    if not IS_WINDOWS:
        return []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    folders = [
        (os.path.join(pf, "EA Games"), "ea"),
        (os.path.join(pf86, "Origin Games"), "ea"),
        (os.path.join(pf, "Epic Games"), "epic"),
        (os.path.join(pf86, "GOG Galaxy", "Games"), "gog"),
        (os.path.join(pf86, "Grinding Gear Games"), "ggg"),
        (os.path.join(pf, "Grinding Gear Games"), "ggg"),
    ]
    for drive in _drives():
        folders.append((os.path.join(drive, "XboxGames"), "xbox"))
        folders.append((os.path.join(drive, "Riot Games"), "riot"))
    return folders


# ----------------------------------------------------------------- Gesamtscan
def scan(extra_folders=()):
    """Alle Quellen einlesen. Doppelte Ordner werden nur einmal gezählt (erste Quelle gewinnt)."""
    entries = []
    # Reihenfolge = Vorrang bei gleichem Ordner (Steam-Einträge behalten ihre AppID und ihr Cover)
    for fn in (steam_games, epic_games, gog_games, ubisoft_games, ggg_games, uninstall_games):
        try:
            entries += fn()
        except Exception:  # noqa: BLE001 – eine kaputte Quelle darf nichts verhindern
            log.exception("Quelle %s konnte nicht gelesen werden", fn.__name__)
    for parent, source in typical_folders():
        try:
            entries += subfolder_games(parent, source)
        except Exception:  # noqa: BLE001
            log.exception("Ordner %s konnte nicht gelesen werden", parent)
    for parent in extra_folders or ():
        try:
            entries += subfolder_games(parent, "custom")
        except Exception:  # noqa: BLE001
            log.exception("Eigener Ordner %s konnte nicht gelesen werden", parent)
    seen, out = set(), []
    for e in entries:
        n = norm_path(e.folder)
        if n in seen or len(n) <= 3:
            continue
        seen.add(n)
        out.append(e)
    return out


def summarize(entries, ignored_keys=()):
    """Für die Einstellungen: erkannte Spiele je Quelle, mit Ausschluss-Status."""
    ignored_keys = set(ignored_keys)
    groups = {}
    for e in entries:
        g = groups.setdefault(e.source, {"source": e.source, "label": SOURCE_LABELS.get(e.source, e.source), "games": []})
        g["games"].append({"name": e.name, "key": e.key, "ignored": e.key in ignored_keys})
    for g in groups.values():
        g["games"].sort(key=lambda x: x["name"].lower())
        g["count"] = len(g["games"])
    return sorted(groups.values(), key=lambda g: -g["count"])
