"""Einstieg: Einzelinstanz, Datenbank, Tracker, Server, Tray, Fenster."""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__, autostart, demo, library, updater, window
from .config import IS_WINDOWS, PORT, data_dir, legacy_data_dir, migrate_legacy_db
from .db import Database
from .server import AppContext, start_server

log = logging.getLogger("novatally")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog=APP_NAME, description="Erfasst automatisch deine Spielzeit.")
    p.add_argument("--demo", action="store_true", help="Demo-Daten in eigenem Datenordner anzeigen")
    p.add_argument("--headless", "--no-tray", dest="headless", action="store_true",
                   help="ohne Tray-Symbol und Fenster (nur Server und Tracker)")
    p.add_argument("--autostart", action="store_true", help="beim Windows-Start: kein Fenster öffnen")
    p.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)  # Neustart nach einem Update
    p.add_argument("--port", type=int, default=PORT, help=argparse.SUPPRESS)
    args, _unknown = p.parse_known_args(argv)
    return args


def setup_logging(folder: Path):
    handlers = []
    try:
        handlers.append(logging.handlers.RotatingFileHandler(
            folder / "novatally.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:  # pythonw/--noconsole hat kein stderr
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def url_for(port):
    return f"http://127.0.0.1:{port}/"


def ping(port, timeout=2.0):
    """Antwortet auf dem Port eine laufende NovaTally-Instanz?"""
    req = urllib.request.Request(url_for(port) + "api/ping", headers={"X-NovaTally": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_NAME
    except Exception:  # noqa: BLE001
        return False


def port_in_use(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def request_show(port, timeout=3.0):
    """Bittet eine laufende Instanz, ihr eigenes Fenster zu zeigen. True bei Erfolg."""
    req = urllib.request.Request(url_for(port) + "api/window/show", data=b"{}", method="POST",
                                 headers={"X-NovaTally": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
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


def is_app_window(title, class_name):
    """Ist das ein Browserfenster mit der NovaTally-Oberfläche? (Edge/Chrome: Klasse Chrome_WidgetWin_*)"""
    if not class_name.startswith("Chrome_WidgetWin"):
        return False
    return title == APP_NAME or title.startswith(APP_NAME + " ")


def focus_existing_window():
    """Holt ein bereits offenes NovaTally-Fenster nach vorne. True, wenn eins gefunden wurde (nur Windows)."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if is_app_window(title.value, cls.value):
                found.append(hwnd)
                return False  # erstes Fenster genügt
            return True

        user32.EnumWindows(callback, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)  # SW_RESTORE / SW_SHOW
        if not user32.SetForegroundWindow(hwnd):
            user32.BringWindowToTop(hwnd)
        log.info("Vorhandenes Fenster nach vorne geholt")
        return True
    except Exception:  # noqa: BLE001 – im Zweifel lieber ein neues Fenster öffnen
        log.exception("Vorhandenes Fenster konnte nicht gesucht werden")
        return False


def open_window(port):
    """Vorhandenes Fenster nach vorne holen – sonst App-Fenster über Edge öffnen, sonst Standardbrowser."""
    if focus_existing_window():
        return
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
        log.info("NovaTally läuft bereits – zeige nur das Fenster")
        if not args.headless and not args.autostart and not request_show(args.port):
            open_window(args.port)
        return 0

    if args.updated:
        log.info("Neustart nach Update auf Version %s", __version__)
        for _ in range(30):  # die alte Instanz gibt den Port gerade frei
            if not port_in_use(args.port):
                break
            time.sleep(0.5)
        if getattr(sys, "frozen", False):
            updater.cleanup_old()

    # ---- Einzelinstanz: zuerst prüfen, bevor die Datenbank verändert wird
    if ping(args.port, timeout=1.0):
        return already_running()

    # ---- Daten der früheren Version „Spielzeit“ übernehmen (nur wenn der Port frei ist,
    #      also keine alte Version mehr läuft und die Datenbank gerade beschreibt)
    if not args.demo and not port_in_use(args.port):
        try:
            if migrate_legacy_db(legacy_data_dir(), folder):
                log.info("Daten der früheren Version „Spielzeit“ übernommen")
        except OSError:
            log.exception("Alte Daten konnten nicht übernommen werden")

    # ---- Server (belegter Port = Sperre). Tracker wird erst danach eingehängt.
    db = Database(folder / "novatally.db")
    ctx = AppContext(db, None, folder, demo=args.demo)
    try:
        server = start_server(ctx, args.port)
    except OSError:
        db.close()
        if ping(args.port):
            return already_running()
        message_box(f"Port {args.port} ist von einem anderen Programm belegt. NovaTally kann nicht starten.\n\n"
                    "Läuft vielleicht noch die frühere Version „Spielzeit“? Dann bitte über ihr Tray-Symbol beenden.")
        return 1

    # ---- Datenbank aufräumen bzw. Demo-Daten
    first_run = db.get_setting("first_run_done") is None
    if args.demo:
        demo.fill(db)
        demo.start_running(db)
    else:
        excluded = db.auto_exclude(f"steam:{appid}" for appid in library.STEAM_EXCLUDED_APPIDS)
        if excluded:
            log.info("Keine Spiele, automatisch ausgeschlossen: %s", ", ".join(excluded))
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
            had_legacy = autostart.remove_legacy()
            if first_run or had_legacy:
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
        log.info("NovaTally wird beendet")
        if tracker is not None:
            tracker.stop()
        server.shutdown()
        server.server_close()  # Port sofort freigeben (wichtig für den Neustart nach einem Update)

    # Fenster beim Start zeigen? Beim Windows-Start (Autostart) nicht – außer beim allerersten Mal.
    show_at_start = not args.headless and (not args.autostart or first_run)

    # ---- Optional: beim Start nach Updates suchen (standardmäßig aus)
    if not args.demo and db.get_setting("update_auto", False):
        def auto_check():
            if stop.wait(20):
                return
            try:
                ctx.update_info = updater.check()
                if ctx.update_info.get("newer"):
                    log.info("Update verfügbar: %s", ctx.update_info.get("latest"))
            except updater.UpdateError as e:
                log.info("Update-Prüfung: %s", e)
        threading.Thread(target=auto_check, name="UpdateCheck", daemon=True).start()

    # ---- Eigenes Fenster (pywebview + WebView2), sonst Edge/Browser
    tray_box = {}

    def first_hide_hint():
        if db.get_setting("hide_hint_shown", False):
            return
        db.set_setting("hide_hint_shown", True)
        t = tray_box.get("tray")
        if t is not None:
            t.notify("NovaTally zählt im Infobereich weiter. Beenden: Rechtsklick auf das Symbol → Beenden.")

    win = None
    if not args.headless and window.available():
        try:
            win = window.AppWindow(url_for(args.port), folder / "webview",
                                   hidden=not show_at_start, on_first_hide=first_hide_hint)
        except Exception:  # noqa: BLE001
            log.exception("Eigenes Fenster nicht verfügbar – nutze Edge/Browser")
            win = None

    def show_ui():
        if win is not None:
            win.show()
        else:
            open_window(args.port)

    def request_quit():
        stop.set()
        if win is not None:
            win.destroy()

    restart_cmd = []

    def request_restart(cmd):
        """Nach einem Update: sauber beenden, danach startet die neue Version."""
        passthrough = (["--headless"] if args.headless else []) + (["--port", str(args.port)] if args.port != PORT else [])
        restart_cmd[:] = list(cmd) + passthrough
        request_quit()

    ctx.request_restart = request_restart
    ctx.show_window = show_ui if not args.headless else None

    # ---- Tray-Symbol in eigenem Thread (der Hauptthread gehört dem Fenster)
    if not args.headless:
        tray_ready = threading.Event()

        def tray_thread():
            try:
                from .tray import Tray

                t = Tray(db, show_ui, request_quit)
            except ImportError:
                log.warning("pystray/Pillow fehlen – kein Tray-Symbol")
                tray_ready.set()
                return
            tray_box["tray"] = t
            ctx.on_change = t.refresh
            tray_ready.set()
            t.run()

        threading.Thread(target=tray_thread, name="Tray", daemon=True).start()
        tray_ready.wait(10)

    def wait_until_stopped():
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

    if win is not None:
        try:
            win.run()  # blockiert, bis das Fenster beim Beenden zerstört wird
        except Exception:  # noqa: BLE001 – z. B. WebView2-Laufzeit fehlt
            log.exception("Eigenes Fenster konnte nicht starten – nutze Edge/Browser")
            win = None
            if show_at_start and not stop.is_set():
                open_window(args.port)
            wait_until_stopped()
    else:
        if show_at_start and not args.updated:
            open_window(args.port)
        wait_until_stopped()

    t = tray_box.get("tray")
    if t is not None:
        try:
            t.icon.stop()
        except Exception:  # noqa: BLE001
            pass
    shutdown()
    db.close()
    if restart_cmd:
        log.info("Starte neue Version: %s", restart_cmd)
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(restart_cmd, creationflags=flags, close_fds=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
