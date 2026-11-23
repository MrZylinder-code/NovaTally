"""Prozess-Abfrage und Sitzungslogik.

Die Prozessquelle ist austauschbar (für Tests mit Fake-Prozessen): ein Objekt mit
`snapshot()` -> Liste von (pid, name, exe) – exe darf None sein.
"""

import logging
import os
import threading
import time

from . import library
from .config import HEARTBEAT_SECONDS, LIBRARY_RESCAN_SECONDS, POLL_SECONDS
from .db import norm_path

log = logging.getLogger(__name__)

IGNORED_EXE_PARTS = (
    "unins", "setup", "install", "vc_redist", "vcredist", "dxsetup", "dotnet", "crashhandler",
    "crashreport", "crashpad", "bugsplat", "easyanticheat_setup", "uploader", "updater",
    "steamwebhelper", "steam.exe", "epicgameslauncher", "galaxyclient", "ubisoftconnect", "upc.exe",
    "eadesktop", "battle.net", "riotclient",
    # zusätzlich: Overlays und Hilfsprogramme der Launcher
    "gameoverlayui", "steamservice", "steamerrorreporter", "unitycrashhandler", "errorreporter",
    # Anti-Cheat-Dienste laufen teils dauerhaft im Hintergrund
    "vgc.exe", "vgtray", "battleye", "beservice", "easyanticheat.exe",
)


def is_ignored_exe(exe_or_name):
    base = os.path.basename(exe_or_name or "").lower()
    return any(part in base for part in IGNORED_EXE_PARTS)


class PsutilSource:
    """Echte Prozessquelle (Windows). EXE-Pfade werden pro PID zwischengespeichert."""

    def __init__(self):
        import psutil  # noqa: F401 – ImportError wird von der App abgefangen

        self.psutil = psutil
        self._exe_cache = {}  # pid -> (name, exe)

    def snapshot(self):
        out, alive = [], set()
        for p in self.psutil.process_iter(["pid", "name"]):
            try:
                pid, name = p.info["pid"], p.info["name"]
            except Exception:  # noqa: BLE001
                continue
            alive.add(pid)
            cached = self._exe_cache.get(pid)
            if cached and cached[0] == name:
                exe = cached[1]
            else:
                try:
                    exe = p.exe() or None
                except Exception:  # AccessDenied, NoSuchProcess, ZombieProcess …  # noqa: BLE001
                    exe = None
                self._exe_cache[pid] = (name, exe)
            out.append((pid, name, exe))
        for pid in list(self._exe_cache):
            if pid not in alive:
                del self._exe_cache[pid]
        return out


class Tracker:
    def __init__(self, db, source, scan=None, clock=time.time, poll=POLL_SECONDS,
                 heartbeat=HEARTBEAT_SECONDS, rescan=LIBRARY_RESCAN_SECONDS):
        self.db = db
        self.source = source
        self.scan = scan or (lambda extra: library.scan(extra))
        self.clock = clock
        self.poll = poll
        self.heartbeat = heartbeat
        self.rescan = rescan
        self.lock = threading.RLock()
        self.active = {}          # key -> {"session_id", "game_id", "start"}
        self.match_cache = {}     # (pid, exe) -> entry | None
        self.seen_noted = set()   # (key, exe) – schon als „gesehen“ gespeichert
        self.prefixes = []        # [(normierter Ordner mit Trenner, LibraryEntry)], längste zuerst
        self.manual = {}          # normierter EXE-Pfad -> (key, name)
        self.manual_names = {}    # EXE-Dateiname -> (key, name) für Prozesse ohne lesbaren Pfad
        self.entries = []
        self.last_scan = None
        self.last_tick = None
        self.last_heartbeat = None
        self._stop = threading.Event()
        self._thread = None

    # --------------------------------------------------------------- Bibliothek
    def force_rescan(self):
        with self.lock:
            self.last_scan = None

    def _load_library(self, now):
        extra = self.db.get_setting("extra_folders", []) or []
        try:
            entries = self.scan(extra)
        except Exception:  # noqa: BLE001
            log.exception("Bibliothek konnte nicht gelesen werden")
            entries = self.entries
        self.entries = entries
        self.prefixes = sorted(
            ((norm_path(e.folder).rstrip(os.sep) + os.sep, e) for e in entries),
            key=lambda pe: len(pe[0]),
            reverse=True,
        )
        self.manual, self.manual_names = {}, {}
        for g in self.db.manual_games():
            exe_norm = g["key"][len("exe:"):]
            self.manual[exe_norm] = (g["key"], g["name"])
            self.manual_names[os.path.basename(exe_norm).lower()] = (g["key"], g["name"])
        self.match_cache.clear()
        self.last_scan = now
        log.info("Bibliothek eingelesen: %d Spiele, %d manuelle Regeln", len(entries), len(self.manual))

    def match(self, name, exe):
        """Prozess einem Spiel zuordnen -> (key, name, source, appid, folder) oder None."""
        if exe:
            n = norm_path(exe)
            if n in self.manual:
                key, gname = self.manual[n]
                return (key, gname, "manual", None, exe)
            if is_ignored_exe(n):
                return None
            for prefix, e in self.prefixes:
                if n.startswith(prefix):
                    return (e.key, e.name, e.source, e.appid, e.folder)
            return None
        if name and name.lower() in self.manual_names:
            key, gname = self.manual_names[name.lower()]
            return (key, gname, "manual", None, None)
        return None

    # ------------------------------------------------------------------ Ablauf
    def tick(self, now=None):
        with self.lock:
            now = self.clock() if now is None else now
            if self.db.get_setting("paused", False):
                self._close_all(now)
                self.last_tick = now
                return
            # Standby/Ruhezustand: große Lücke seit dem letzten Durchlauf
            if self.last_tick is not None and now - self.last_tick > 3 * self.poll + 60:
                log.info("Lücke von %d s erkannt (Standby?) – Sitzungen beim letzten Durchlauf beendet",
                         now - self.last_tick)
                self._close_all(self.last_tick)
            if self.last_scan is None or now - self.last_scan >= self.rescan:
                self._load_library(now)

            found = {}
            only = self.db.only_exe_map()  # Spiele, bei denen nur ein bestimmtes Programm zählt
            for pid, name, exe in self.source.snapshot():
                ck = (pid, exe or name)
                if ck in self.match_cache:
                    m = self.match_cache[ck]
                else:
                    m = self.match(name, exe)
                    self.match_cache[ck] = m
                if not m:
                    continue
                display = os.path.basename(exe or name or "")
                base = display.lower()
                self._note_exe(m[0], base, display, now)
                want = only.get(m[0])
                if want and base != want:
                    continue  # z. B. LeagueClient.exe, wenn nur das Match zählen soll
                if m[0] not in found:
                    found[m[0]] = m
            if len(self.match_cache) > 5000:
                self.match_cache.clear()

            ignored = self.db.ignored_keys()
            for key, (k, gname, source, appid, folder) in found.items():
                if key in self.active or key in ignored:
                    continue
                game = self.db.get_or_create_game(k, gname, source, appid, folder)
                if game["ignored"]:
                    continue
                sid = self.db.start_session(game["id"], now)
                self.active[key] = {"session_id": sid, "game_id": game["id"], "start": now}
                log.info("Spiel erkannt: %s", game["name"])
            for key in list(self.active):
                if key not in found or key in ignored:
                    self._close(key, now)

            if self.last_heartbeat is None or now - self.last_heartbeat >= self.heartbeat:
                self.db.touch_sessions([a["session_id"] for a in self.active.values()], now)
                self.last_heartbeat = now
            self.last_tick = now

    def _note_exe(self, key, exe, display, now):
        if not exe or (key, exe) in self.seen_noted:
            return
        try:
            if self.db.record_exe(key, exe, display, now):
                self.seen_noted.add((key, exe))
        except Exception:  # noqa: BLE001 – Merken ist nur Komfort
            log.exception("Programm konnte nicht gemerkt werden")

    def _close(self, key, end):
        a = self.active.pop(key)
        kept = self.db.end_session(a["session_id"], end)
        log.info("Sitzung beendet (%s): %d s%s", key, end - a["start"], "" if kept else " – verworfen")

    def _close_all(self, end):
        for key in list(self.active):
            self._close(key, end)

    def close_all(self, now=None):
        with self.lock:
            self._close_all(self.clock() if now is None else now)

    # ------------------------------------------------------------------ Thread
    def start(self):
        self._thread = threading.Thread(target=self._run, name="Tracker", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 – der Tracker darf nie sterben
                log.exception("Fehler im Tracker")
            self._stop.wait(self.poll)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.close_all()
