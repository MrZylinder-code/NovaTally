"""Einstieg: Einzelinstanz, Datenbank, Tracker, Server, Tray, Fenster."""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__, autostart, demo
from .config import IS_WINDOWS, PORT, data_dir
from .db import Database
from .server import AppContext, start_server

log = logging.getLogger("spielzeit")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog=APP_NAME, description="Erfasst automatisch deine Spielzeit.")
    p.add_argument("--demo", action="store_true", help="Demo-Daten in eigenem Datenordner anzeigen")
    p.add_argument("--headless", "--no-tray", dest="headless", action="store_true",
                   help="ohne Tray-Symbol und Fenster (nur Server und Tracker)")
    p.add_argument("--autostart", action="store_true", help="beim Windows-Start: kein Fenster öffnen")
    p.add_argument("--port", type=int, default=PORT, help=argparse.SUPPRESS)
    args, _unknown = p.parse_known_args(argv)
    return args


def setup_logging(folder: Path):
    handlers = []
    try:
        handlers.append(logging.handlers.RotatingFileHandler(
            folder / "spielzeit.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:  # pythonw/--noconsole hat kein stderr
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def url_for(port):
    return f"http://127.0.0.1:{port}/"


def ping(port, timeout=2.0):
    """Antwortet auf dem Port eine laufende Spielzeit?"""
    req = urllib.request.Request(url_for(port) + "api/ping", headers={"X-Spielzeit": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_NAME
    except Exception:  # noqa: BLE001
        return False


def find_edge():
    if not IS_WINDOWS:
        return None
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("msedge")


def open_window(port):
    """App-Fenster über Edge öffnen (ohne Adressleiste), sonst Standardbrowser."""
    url = url_for(port)
    edge = find_edge()
    if edge:
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([edge, f"--app={url}"], creationflags=flags, close_fds=True)
            return
        except OSError:
            log.exception("Edge konnte nicht gestartet werden")
    webbrowser.open(url)


def message_box(text):
    if IS_WINDOWS:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
            return
        except Exception:  # noqa: BLE001
            pass
    print(text, file=sys.stderr or sys.stdout)


def main(argv=None):
    args = parse_args(argv)
    folder = data_dir()
    if args.demo:
        folder = folder / "demo"
        folder.mkdir(parents=True, exist_ok=True)
    setup_logging(folder)
    log.info("%s %s startet (Daten: %s)", APP_NAME, __version__, folder)

    def already_running():
        log.info("Spielzeit läuft bereits – öffne nur das Fenster")
        if not args.headless and not args.autostart:
            open_window(args.port)
        return 0

    # ---- Einzelinstanz: zuerst prüfen, bevor die Datenbank verändert wird
    if ping(args.port, timeout=1.0):
        return already_running()

    # ---- Server (belegter Port = Sperre). Tracker wird erst danach eingehängt.
    db = Database(folder / "spielzeit.db")
    ctx = AppContext(db, None, folder, demo=args.demo)
    try:
        server = start_server(ctx, args.port)
    except OSError:
        db.close()
        if ping(args.port):
            return already_running()
        message_box(f"Port {args.port} ist von einem anderen Programm belegt. Spielzeit kann nicht starten.")
        return 1

    # ---- Datenbank aufräumen bzw. Demo-Daten
    first_run = db.get_setting("first_run_done") is None
    if args.demo:
        demo.fill(db)
        demo.start_running(db)
    else:
        closed = db.close_stale_sessions()
        if closed:
            log.info("%d offene Sitzung(en) vom letzten Lauf beim letzten Heartbeat beendet", closed)

    # ---- Tracker
    tracker, note, source = None, None, None
    if args.demo:
        note = "Demo-Modus: Es wird nichts erfasst."
    else:
        try:
            from .tracker import PsutilSource, Tracker

            source = PsutilSource()
            tracker = Tracker(db, source)
        except ImportError:
            note = "psutil ist nicht installiert – die Spielerkennung ist deaktiviert."
            log.warning(note)
    ctx.tracker, ctx.tracker_note, ctx.process_source = tracker, note, source

    if tracker is not None:
        tracker.start()

    if not args.demo and autostart.supported():
        try:
            if first_run:
                autostart.set_enabled(True)  # Standard: mit Windows starten (abschaltbar)
            else:
                autostart.repair()
        except OSError:
            log.exception("Autostart konnte nicht gesetzt werden")
    db.set_setting("first_run_done", True)

    stop = threading.Event()       # Signal zum Beenden (ohne Tray)
    stopped = threading.Event()    # Aufräumen nur einmal

    def shutdown():
        if stopped.is_set():
            return
        stopped.set()
        log.info("Spielzeit wird beendet")
        if tracker is not None:
            tracker.stop()
        server.shutdown()

    if not args.headless and (not args.autostart or first_run):
        open_window(args.port)

    tray = None
    if not args.headless:
        try:
            from .tray import Tray

            tray = Tray(db, lambda: open_window(args.port), shutdown)
            ctx.on_change = tray.refresh
        except ImportError:
            log.warning("pystray/Pillow fehlen – kein Tray-Symbol")

    if tray is not None:
        tray.run()  # blockiert im Hauptthread bis „Beenden“
        shutdown()
    else:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: stop.set())
            except (ValueError, OSError):
                pass
        try:
            while not stop.wait(1):
                pass
        except KeyboardInterrupt:
            pass
        shutdown()
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
