"""Eingebauter Mini-Server: Web-Oberfläche + JSON-API, nur auf 127.0.0.1.

Schutz: Host-Header-Prüfung (gegen DNS-Rebinding) und Pflicht-Header `X-NovaTally: 1`
für alle /api/*-Aufrufe (fremde Webseiten scheitern am CORS-Preflight). Keine CORS-Header.
"""

import csv
import io
import json
import logging
import os
import re
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import APP_NAME, __version__, autostart, library, stats, updater
from .config import IS_WINDOWS, resource_dir
from .db import norm_path

log = logging.getLogger(__name__)

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/icon.ico": ("icon.ico", "image/x-icon"),
    "/favicon.ico": ("icon.ico", "image/x-icon"),
}

CSP = (
    "default-src 'self'; img-src 'self' data: https://cdn.cloudflare.steamstatic.com; "
    "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

SYSTEM_DIRS = ("\\windows\\", "\\program files\\windowsapps\\microsoft.", "\\system32\\")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class AppContext:
    """Alles, was der Server von der App braucht."""

    def __init__(self, db, tracker=None, data_dir="", demo=False, tracker_note=None, process_source=None):
        self.db = db
        self.tracker = tracker
        self.data_dir = str(data_dir)
        self.demo = demo
        self.tracker_note = tracker_note
        self.process_source = process_source
        self.on_change = None  # z. B. Tray-Symbol aktualisieren
        self.request_restart = None  # von der App gesetzt: beenden und neue Version starten
        self.update_info = None  # Ergebnis der letzten Update-Prüfung
        self._library_cache = None

    def library_entries(self):
        if self.tracker is not None and self.tracker.last_scan is not None:
            return self.tracker.entries
        if self._library_cache is None:
            self._library_cache = library.scan(self.db.get_setting("extra_folders", []) or [])
        return self._library_cache

    def library_changed(self):
        self._library_cache = None
        if self.tracker is not None:
            self.tracker.force_rescan()

    def notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("on_change fehlgeschlagen")


class NovaTallyServer(ThreadingHTTPServer):
    daemon_threads = True
    # Unter Windows erlaubt SO_REUSEADDR das doppelte Belegen eines Ports – dann wäre
    # die Einzelinstanz-Sperre wirkungslos. Stattdessen den Port exklusiv belegen.
    allow_reuse_address = not IS_WINDOWS

    def __init__(self, ctx, port):
        self.ctx = ctx
        self.port = port
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        super().__init__(("127.0.0.1", port), Handler)

    def server_bind(self):
        if IS_WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = APP_NAME
    sys_version = ""

    def log_message(self, fmt, *args):  # leise
        log.debug("%s - %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------------- Antworten
    def _send(self, status, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status=200):
        self._send(status, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json({"error": message}, status)

    def _guard(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in self.server.allowed_hosts:
            self._error(403, "Ungültiger Host")
            return False
        path = urlparse(self.path).path
        if path.startswith("/api/") and self.headers.get("X-NovaTally") != "1":
            self._error(403, "Header X-NovaTally fehlt")
            return False
        return True

    # ---------------------------------------------------------------- Routing
    def do_GET(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        try:
            if url.path.startswith("/api/"):
                self._api_get(url.path, parse_qs(url.query))
            else:
                self._static(url.path)
        except ApiError as e:
            self._error(e.status, e.message)
        except Exception:  # noqa: BLE001
            log.exception("Fehler bei GET %s", self.path)
            self._error(500, "Interner Fehler")

    do_HEAD = do_GET

    def do_POST(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 65536:
                raise ApiError(413, "Anfrage zu groß")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                raise ApiError(400, "Ungültiges JSON")
            if not isinstance(body, dict):
                raise ApiError(400, "JSON-Objekt erwartet")
            self._api_post(url.path, body)
        except ApiError as e:
            self._error(e.status, e.message)
        except Exception:  # noqa: BLE001
            log.exception("Fehler bei POST %s", self.path)
            self._error(500, "Interner Fehler")

    def _static(self, path):
        entry = STATIC.get(path)
        if not entry:
            self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")
            return
        fname, ctype = entry
        try:
            with open(resource_dir() / "web" / fname, "rb") as f:
                data = f.read()
        except OSError:
            self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")
            return
        self._send(200, data, ctype)

    # -------------------------------------------------------------------- GET
    def _api_get(self, path, query):
        ctx = self.server.ctx
        db = ctx.db
        if path == "/api/ping":
            return self._json({"app": APP_NAME, "version": __version__})
        if path == "/api/status":
            running, last = stats.status_running(db)
            return self._json({
                "app": APP_NAME,
                "version": __version__,
                "now": time.time(),
                "paused": bool(db.get_setting("paused", False)),
                "tracking": ctx.tracker is not None,
                "tracker_note": ctx.tracker_note,
                "demo": ctx.demo,
                "running": running,
                "last": last,
                "theme": db.get_setting("theme", "dark"),
                "update": ({"latest": ctx.update_info["latest"]}
                           if ctx.update_info and ctx.update_info.get("newer") else None),
            })
        if path == "/api/overview":
            rng = (query.get("range") or ["30"])[0]
            return self._json(stats.overview(db, rng))
        if path == "/api/games":
            return self._json(stats.games_list(db))
        m = re.fullmatch(r"/api/game/(\d+)", path)
        if m:
            detail = stats.game_detail(db, int(m.group(1)))
            if detail is None:
                raise ApiError(404, "Spiel nicht gefunden")
            return self._json(detail)
        if path == "/api/sessions":
            try:
                limit = max(1, min(5000, int((query.get("limit") or ["300"])[0])))
            except ValueError:
                limit = 300
            return self._json(stats.sessions_list(db, limit))
        if path == "/api/processes":
            return self._json(self._processes())
        if path == "/api/settings":
            return self._json(self._settings())
        if path == "/api/export.csv":
            return self._export()
        if path == "/api/update/check":
            try:
                info = updater.check()
            except updater.UpdateError as e:
                raise ApiError(502, str(e))
            ctx.update_info = info
            return self._json(self._public_update(info))
        raise ApiError(404, "Unbekannter Endpunkt")

    @staticmethod
    def _public_update(info):
        return {k: info.get(k) for k in ("mode", "current", "latest", "newer", "notes", "url", "installable")}

    def _processes(self):
        ctx = self.server.ctx
        src = ctx.process_source
        if src is None:
            return {"available": False, "processes": []}
        known = {g["key"] for g in ctx.db.games(include_ignored=True)}
        tracker = ctx.tracker
        seen, out = set(), []
        for pid, name, exe in src.snapshot():
            if not exe:
                continue
            n = norm_path(exe)
            low = n.lower().replace("/", "\\")
            if n in seen or any(d in low for d in SYSTEM_DIRS):
                continue
            seen.add(n)
            match = tracker.match(name, exe) if tracker else None
            out.append({
                "name": name or os.path.basename(exe),
                "exe": exe,
                "title": os.path.splitext(os.path.basename(exe))[0],
                "tracked": bool(match) or ("exe:" + n) in known,
                "game": match[1] if match else None,
            })
        out.sort(key=lambda p: (p["tracked"], p["name"].lower()))
        return {"available": True, "processes": out}

    def _settings(self):
        ctx = self.server.ctx
        db = ctx.db
        entries = ctx.library_entries()
        return {
            "paused": bool(db.get_setting("paused", False)),
            "theme": db.get_setting("theme", "dark"),
            "extra_folders": db.get_setting("extra_folders", []) or [],
            "autostart": autostart.is_enabled(),
            "autostart_supported": autostart.supported() and not ctx.demo,
            "data_dir": ctx.data_dir,
            "db_path": db.path,
            "version": __version__,
            "demo": ctx.demo,
            "tracking": ctx.tracker is not None,
            "tracker_note": ctx.tracker_note,
            "libraries": library.summarize(entries, db.ignored_keys()),
            "update_auto": bool(db.get_setting("update_auto", False)),
            "update_mode": updater.mode(),
            "releases_url": updater.RELEASES_URL,
            "library_total": len(entries),
            "ignored": [{"id": g["id"], "name": g["name"], "appid": g["appid"], "source": g["source"]}
                        for g in db.ignored_games()],
        }

    def _export(self):
        db = self.server.ctx.db
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(["Spiel", "Quelle", "Start", "Ende", "Dauer (Minuten)", "Ausgeschlossen"])
        for s in db.all_sessions(include_ignored=True):
            fmt = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
            w.writerow([s["name"], library.SOURCE_LABELS.get(s["source"], s["source"]), fmt(s["start"]),
                        fmt(s["end"]), str(round((s["end"] - s["start"]) / 60, 1)).replace(".", ","),
                        "ja" if s["ignored"] else "nein"])
        name = f"novatally-{datetime.now():%Y-%m-%d}.csv"
        self._send(200, "﻿" + buf.getvalue(), "text/csv; charset=utf-8",
                   {"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------------- POST
    def _api_post(self, path, body):
        ctx = self.server.ctx
        db = ctx.db
        m = re.fullmatch(r"/api/game/(\d+)/(rename|ignore)", path)
        if m:
            gid = int(m.group(1))
            if not db.game(gid):
                raise ApiError(404, "Spiel nicht gefunden")
            if m.group(2) == "rename":
                name = str(body.get("name") or "").strip()
                if not name or len(name) > 200:
                    raise ApiError(400, "Bitte einen Namen (max. 200 Zeichen) angeben")
                db.rename_game(gid, name)
            else:
                db.set_ignored(gid, bool(body.get("ignored", True)))
                if ctx.tracker is not None:
                    ctx.tracker.tick()
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/session/(\d+)/delete", path)
        if m:
            if not db.delete_session(int(m.group(1))):
                raise ApiError(404, "Sitzung nicht gefunden oder läuft noch")
            return self._json({"ok": True})
        if path == "/api/update/install":
            if ctx.demo:
                raise ApiError(400, "Im Demo-Modus wird nicht aktualisiert.")
            info = ctx.update_info
            if not info or not info.get("newer") or not info.get("installable"):
                raise ApiError(400, "Kein installierbares Update gefunden – bitte zuerst nach Updates suchen.")
            try:
                cmd = updater.install(info)
            except updater.UpdateError as e:
                raise ApiError(500, str(e))
            if ctx.request_restart is not None:
                threading.Timer(1.0, ctx.request_restart, args=(cmd,)).start()
            return self._json({"ok": True, "restarting": ctx.request_restart is not None})
        if path == "/api/library/ignore":
            # Ein erkanntes Spiel ausschließen – auch wenn es noch nie gespielt wurde
            key = str(body.get("key") or "")
            ignored = bool(body.get("ignored", True))
            entry = next((e for e in ctx.library_entries() if e.key == key), None)
            game = db.game_by_key(key)
            if game is None and entry is None:
                raise ApiError(404, "Spiel nicht gefunden")
            if game is None:
                game = db.get_or_create_game(entry.key, entry.name, entry.source, entry.appid, entry.folder)
            db.set_ignored(game["id"], ignored)
            if ctx.tracker is not None:
                ctx.tracker.tick()
            return self._json({"ok": True, "id": game["id"]})
        if path == "/api/games/add":
            exe = str(body.get("exe") or "").strip()
            name = str(body.get("name") or "").strip()
            if not exe or not name or len(name) > 200:
                raise ApiError(400, "EXE-Pfad und Name werden benötigt")
            if not exe.lower().endswith(".exe") and IS_WINDOWS:
                raise ApiError(400, "Bitte eine .exe-Datei angeben")
            game = db.add_manual_game(exe, name)
            ctx.library_changed()
            return self._json({"ok": True, "id": game["id"]})
        if path == "/api/settings":
            if "paused" in body:
                db.set_setting("paused", bool(body["paused"]))
                if ctx.tracker is not None:
                    ctx.tracker.tick()
                ctx.notify()
            if "theme" in body:
                if body["theme"] not in ("system", "dark", "light"):
                    raise ApiError(400, "Unbekanntes Thema")
                db.set_setting("theme", body["theme"])
            if "extra_folders" in body:
                folders = body["extra_folders"]
                if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
                    raise ApiError(400, "Liste von Ordnern erwartet")
                clean = []
                for f in folders:
                    f = f.strip().strip('"')
                    if f and os.path.normpath(f) not in clean:
                        clean.append(os.path.normpath(f))
                missing = [f for f in clean if not os.path.isdir(f)]
                if missing:
                    raise ApiError(400, "Ordner nicht gefunden: " + ", ".join(missing))
                db.set_setting("extra_folders", clean)
                ctx.library_changed()
            if "update_auto" in body:
                db.set_setting("update_auto", bool(body["update_auto"]))
            if "autostart" in body:
                if not autostart.supported() or ctx.demo:
                    raise ApiError(400, "Autostart ist nur unter Windows (und nicht im Demo-Modus) möglich")
                autostart.set_enabled(bool(body["autostart"]))
            return self._json(self._settings())
        raise ApiError(404, "Unbekannter Endpunkt")


def start_server(ctx, port):
    """Server im Daemon-Thread starten. Wirft OSError, wenn der Port belegt ist."""
    srv = NovaTallyServer(ctx, port)
    t = threading.Thread(target=srv.serve_forever, name="Server", daemon=True)
    t.start()
    log.info("Server läuft auf http://127.0.0.1:%d", port)
    return srv
