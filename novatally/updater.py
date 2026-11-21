"""Updates: neue Version aus den GitHub-Releases (EXE) oder per `git pull` (Quellcode-Installation).

Nur auf ausdrücklichen Wunsch: Geprüft wird per Klick in den Einstellungen oder – wenn eingeschaltet – beim Start.
Heruntergeladen wird ausschließlich aus den Releases dieses Repos, und nur wenn die SHA-256-Prüfsumme stimmt.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import APP_NAME, __version__
from .config import IS_WINDOWS

log = logging.getLogger(__name__)

REPO = "MrZylinder-code/NovaTally"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
EXE_NAME = "NovaTally.exe"
MAX_DOWNLOAD = 300 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW: kein Konsolenfenster für git


class UpdateError(Exception):
    """Verständliche Fehlermeldung für die Oberfläche."""


# --------------------------------------------------------------------- Hilfen
def parse_version(text):
    """'v1.2.3' -> (1, 2, 3); Unlesbares -> (0,)."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def is_newer(latest, current):
    a, b = list(parse_version(latest)), list(parse_version(current))
    n = max(len(a), len(b))
    return a + [0] * (n - len(a)) > b + [0] * (n - len(b))


def _fetch(url, timeout=15):
    """HTTP-GET. Bewusst ohne persönliche Daten: nur App-Name und Version im User-Agent."""
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME}/{__version__}",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise UpdateError("Download ist unerwartet groß – abgebrochen.")
    return data


def release_notes(body):
    """Nur den Änderungsteil des Release-Texts (ohne Installationsanleitung und Prüfsumme)."""
    text = (body or "").replace("\r\n", "\n")
    return text.split("\n### Installation")[0].strip()


def mode():
    """'exe' (gebaute EXE), 'git' (Quellcode mit Git) oder 'manual'."""
    if getattr(sys, "frozen", False):
        return "exe" if IS_WINDOWS else "manual"
    if (ROOT / ".git").exists() and shutil.which("git"):
        return "git"
    return "manual"


# ------------------------------------------------------------------ EXE-Modus
def check_release(current=__version__, fetch=_fetch):
    try:
        data = json.loads(fetch(LATEST_API).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001 – Netzwerk, JSON …
        raise UpdateError("GitHub ist gerade nicht erreichbar. Bitte später noch einmal versuchen.") from e
    tag = data.get("tag_name") or ""
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    exe_url, sha_url = assets.get(EXE_NAME), assets.get(EXE_NAME + ".sha256")
    for url in (exe_url, sha_url):
        if url and not url.startswith(DOWNLOAD_PREFIX):
            raise UpdateError("Unerwartete Download-Adresse im Release – abgebrochen.")
    return {
        "mode": "exe",
        "current": current,
        "latest": tag.lstrip("v"),
        "newer": bool(tag) and is_newer(tag, current),
        "notes": release_notes(data.get("body")),
        "url": data.get("html_url") or RELEASES_URL,
        "exe_url": exe_url,
        "sha_url": sha_url,
        "installable": bool(exe_url and sha_url),
    }


def download_verified(info, target_dir, fetch=_fetch):
    """Lädt die EXE nach target_dir/NovaTally.new.exe – nur wenn die Prüfsumme stimmt."""
    if not info.get("installable"):
        raise UpdateError("Im Release fehlt die EXE oder ihre Prüfsumme.")
    try:
        sha_text = fetch(info["sha_url"]).decode("ascii", "replace")
        data = fetch(info["exe_url"])
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UpdateError("Download fehlgeschlagen. Bitte später noch einmal versuchen.") from e
    m = re.search(r"\b([0-9a-fA-F]{64})\b", sha_text)
    if not m:
        raise UpdateError("Die Prüfsummen-Datei im Release ist unlesbar.")
    if hashlib.sha256(data).hexdigest().lower() != m.group(1).lower():
        raise UpdateError("Die Prüfsumme stimmt nicht – die Datei wurde nicht installiert.")
    new_path = Path(target_dir) / "NovaTally.new.exe"
    try:
        new_path.write_bytes(data)
    except OSError as e:
        raise UpdateError(f"Keine Schreibrechte im Ordner {target_dir}. Lege NovaTally an einen Ort mit "
                          "Schreibrechten (z. B. C:\\Tools) oder lade das Update manuell herunter.") from e
    return new_path


def swap_exe(current_exe, new_exe):
    """Laufende EXE umbenennen (das erlaubt Windows) und die neue an ihren Platz legen."""
    current_exe, new_exe = Path(current_exe), Path(new_exe)
    old = current_exe.with_name("NovaTally.old.exe")
    try:
        if old.exists():
            old.unlink()
        os.replace(current_exe, old)
    except OSError as e:
        raise UpdateError(f"Die laufende Datei {current_exe.name} lässt sich nicht ersetzen.") from e
    try:
        os.replace(new_exe, current_exe)
    except OSError as e:
        os.replace(old, current_exe)  # zurückrollen
        raise UpdateError("Die neue Version konnte nicht abgelegt werden – alte Version bleibt.") from e
    return old


def cleanup_old(exe=None):
    """Nach einem Update: die alte EXE wegräumen (klappt erst, wenn sie nicht mehr läuft)."""
    exe = Path(exe or sys.executable)
    old = exe.with_name("NovaTally.old.exe")
    for p in (old, exe.with_name("NovaTally.new.exe")):
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ Git-Modus
def _git(args, cwd=ROOT, timeout=60):
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UpdateError("Git konnte nicht ausgeführt werden.") from e
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise UpdateError("git " + args[0] + " fehlgeschlagen: " + (msg[-1] if msg else "unbekannter Fehler"))
    return r.stdout


def check_git(current=__version__, cwd=ROOT):
    _git(["fetch", "--quiet"], cwd)
    try:
        log_text = _git(["log", "--format=%s", "HEAD..@{u}"], cwd)
    except UpdateError as e:
        raise UpdateError("Dieser Git-Stand folgt keinem Branch auf GitHub (kein Upstream).") from e
    commits = [line for line in log_text.splitlines() if line.strip()]
    return {
        "mode": "git",
        "current": current,
        "latest": f"{len(commits)} neue Änderung{'en' if len(commits) != 1 else ''}" if commits else current,
        "newer": bool(commits),
        "notes": "\n".join("- " + c for c in commits[:30]),
        "url": RELEASES_URL,
        "installable": bool(commits),
    }


def pull_git(cwd=ROOT):
    return _git(["pull", "--ff-only", "--quiet"], cwd)


# ----------------------------------------------------------------- Gesamt
def check(current=__version__):
    m = mode()
    if m == "git":
        return check_git(current)
    info = check_release(current)
    if m != "exe":
        info["mode"] = "manual"
        info["installable"] = False
    return info


def install(info):
    """Führt das Update aus und gibt den Befehl zurück, mit dem die neue Version gestartet wird."""
    m = mode()
    if m == "exe":
        exe = Path(sys.executable)
        new = download_verified(info, exe.parent)
        swap_exe(exe, new)
        return [str(exe), "--updated"]
    if m == "git":
        pull_git()
        return [sys.executable, str(ROOT / "NovaTally.pyw"), "--updated"]
    raise UpdateError("Automatisches Aktualisieren ist bei dieser Installation nicht möglich. "
                      "Bitte die neue Version unter Releases herunterladen.")
