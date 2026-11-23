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
import socket
import ssl
import subprocess
import sys
import tempfile
import urllib.error
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
SETUP_NAME = "NovaTally-Setup.exe"
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


_SSL_CONTEXT = None


def ssl_context():
    """Zertifikate aus Windows UND aus certifi (falls mitgeliefert).

    Python unter Windows liest nur die Zertifikate, die schon im Windows-Speicher liegen. Windows lädt fehlende
    Stammzertifikate aber erst bei Bedarf nach – dann scheitert die Prüfung von github.com. certifi bringt
    die üblichen Stammzertifikate selbst mit.
    """
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        ctx = ssl.create_default_context()
        try:
            import certifi

            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:  # noqa: BLE001 – certifi ist optional
            pass
        _SSL_CONTEXT = ctx
    return _SSL_CONTEXT


def _request(url, method="GET"):
    return urllib.request.Request(url, method=method, headers={
        "User-Agent": f"{APP_NAME}/{__version__}",  # bewusst ohne persönliche Daten
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*",
    })


def _fetch(url, timeout=15):
    """HTTP-GET, gibt den Inhalt zurück."""
    with urllib.request.urlopen(_request(url), timeout=timeout, context=ssl_context()) as r:
        data = r.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise UpdateError("Download ist unerwartet groß – abgebrochen.")
    return data


def _resolve(url, timeout=15):
    """Folgt Weiterleitungen und gibt die endgültige Adresse zurück."""
    with urllib.request.urlopen(_request(url, "HEAD"), timeout=timeout, context=ssl_context()) as r:
        return r.geturl()


def describe(e):
    """Verständlicher Grund für einen Netzwerkfehler."""
    if isinstance(e, UpdateError):
        return str(e)
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (403, 429):
            return f"GitHub begrenzt gerade die Anfragen (HTTP {e.code}). Bitte in einer Stunde noch einmal versuchen."
        return f"GitHub antwortet mit einem Fehler (HTTP {e.code})."
    reason = getattr(e, "reason", e)
    text = str(reason)
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return "Das Sicherheitszertifikat von GitHub konnte nicht geprüft werden (SSL). " \
               "Ein Virenscanner oder Proxy kann das verursachen."
    if isinstance(reason, ssl.SSLError):
        return f"Sichere Verbindung zu GitHub fehlgeschlagen ({text})."
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in text:
        return "Zeitüberschreitung bei der Verbindung zu GitHub."
    if isinstance(reason, socket.gaierror):
        return "github.com wurde nicht gefunden – besteht eine Internetverbindung?"
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError)):
        return "Die Verbindung zu GitHub wurde abgelehnt (Firewall oder Proxy?)."
    return f"Verbindung zu GitHub fehlgeschlagen ({type(reason).__name__}: {text})."


def release_notes(body):
    """Nur den Änderungsteil des Release-Texts (ohne Installationsanleitung und Prüfsumme)."""
    text = (body or "").replace("\r\n", "\n")
    return text.split("\n### Installation")[0].strip()


def is_writable(folder):
    """Darf NovaTally in diesem Ordner Dateien anlegen? (z. B. nicht in C:\\Program Files ohne Adminrechte)"""
    try:
        with tempfile.NamedTemporaryFile(dir=str(folder), prefix=".novatally-", delete=True):
            return True
    except OSError:
        return False


def select_mode(frozen, windows, exe_dir_writable, has_git):
    """'exe' (EXE selbst ersetzen), 'setup' (neuen Installer starten), 'git' oder 'manual'."""
    if frozen:
        if not windows:
            return "manual"
        return "exe" if exe_dir_writable else "setup"
    return "git" if has_git else "manual"


def mode():
    frozen = bool(getattr(sys, "frozen", False))
    return select_mode(
        frozen, IS_WINDOWS,
        is_writable(Path(sys.executable).parent) if frozen else True,
        (ROOT / ".git").exists() and bool(shutil.which("git")),
    )


# ------------------------------------------------------------------ EXE-Modus
def _latest_via_release_page(current, resolve):
    """Ausweichweg ohne GitHub-API: /releases/latest leitet auf /releases/tag/<tag> weiter."""
    final = resolve(f"{RELEASES_URL}/latest")
    m = re.search(r"/releases/tag/([^/?#]+)$", final or "")
    if not m:
        raise UpdateError("Auf GitHub ist noch kein Release veröffentlicht.")
    tag = m.group(1)
    base = f"{DOWNLOAD_PREFIX}{tag}/"
    return {
        "mode": "exe", "current": current, "latest": tag.lstrip("v"),
        "newer": is_newer(tag, current),
        "notes": "Die Änderungen stehen auf der Release-Seite.",
        "url": final, "exe_url": base + EXE_NAME, "sha_url": base + EXE_NAME + ".sha256",
        "setup_url": base + SETUP_NAME, "setup_sha_url": base + SETUP_NAME + ".sha256",
        "installable": True,
    }


def check_release(current=__version__, fetch=_fetch, resolve=_resolve):
    try:
        data = json.loads(fetch(LATEST_API).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as api_error:  # noqa: BLE001 – Netzwerk, JSON, Limit …
        log.warning("Update-Prüfung über die GitHub-API fehlgeschlagen: %r", api_error)
        try:
            return _latest_via_release_page(current, resolve)
        except UpdateError:
            raise
        except Exception as page_error:  # noqa: BLE001
            log.warning("Update-Prüfung über die Release-Seite fehlgeschlagen: %r", page_error)
            raise UpdateError(describe(api_error)) from api_error
    tag = data.get("tag_name") or ""
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    exe_url, sha_url = assets.get(EXE_NAME), assets.get(EXE_NAME + ".sha256")
    setup_url, setup_sha_url = assets.get(SETUP_NAME), assets.get(SETUP_NAME + ".sha256")
    for url in (exe_url, sha_url, setup_url, setup_sha_url):
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
        "setup_url": setup_url,
        "setup_sha_url": setup_sha_url,
        "installable": bool(exe_url and sha_url),
    }


def download_verified(info, target_dir, fetch=_fetch, kind="exe"):
    """Lädt die EXE (bzw. den Installer) nach target_dir – nur wenn die Prüfsumme stimmt."""
    url, sha_url = (info.get("exe_url"), info.get("sha_url")) if kind == "exe" else \
        (info.get("setup_url"), info.get("setup_sha_url"))
    if not (url and sha_url):
        raise UpdateError("Im Release fehlt die Datei oder ihre Prüfsumme.")
    try:
        sha_text = fetch(sha_url).decode("ascii", "replace")
        data = fetch(url)
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("Update-Download fehlgeschlagen: %r", e)
        raise UpdateError("Download fehlgeschlagen: " + describe(e)) from e
    m = re.search(r"\b([0-9a-fA-F]{64})\b", sha_text)
    if not m:
        raise UpdateError("Die Prüfsummen-Datei im Release ist unlesbar.")
    if hashlib.sha256(data).hexdigest().lower() != m.group(1).lower():
        raise UpdateError("Die Prüfsumme stimmt nicht – die Datei wurde nicht installiert.")
    new_path = Path(target_dir) / ("NovaTally.new.exe" if kind == "exe" else SETUP_NAME)
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


def cleanup_temp(max_age_hours=24, temp_dir=None):
    """Heruntergeladene Installer früherer Updates im Temp-Ordner wegräumen."""
    import time

    base = Path(temp_dir or tempfile.gettempdir())
    removed = 0
    try:
        candidates = list(base.glob("novatally-update-*"))
    except OSError:
        return 0
    for p in candidates:
        try:
            if p.is_dir() and time.time() - p.stat().st_mtime > max_age_hours * 3600:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed


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
    info["mode"] = m
    if m == "setup":
        info["installable"] = bool(info.get("setup_url") and info.get("setup_sha_url"))
    elif m != "exe":
        info["installable"] = False
    return info


def _launch(path):
    os.startfile(path)  # noqa: S606 – Windows: startet den Installer (mit UAC-Abfrage, falls nötig)


def install(info, launcher=None):
    """Führt das Update aus.

    Gibt den Befehl zurück, mit dem die neue Version gestartet wird – oder None, wenn ein Installer
    übernimmt (dann beendet sich NovaTally nur; der Installer startet es danach selbst wieder).
    """
    m = mode()
    if m == "setup":
        path = download_verified(info, tempfile.mkdtemp(prefix="novatally-update-"), kind="setup")
        (launcher or _launch)(str(path))
        return None
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
