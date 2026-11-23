"""Eigenes NovaTally-Fenster mit pywebview + WebView2 (in Windows 10/11 eingebaut).

Es gibt immer genau ein Fenster. Schließen (X) versteckt es nur – NovaTally zählt im Infobereich weiter.
Fehlt pywebview oder WebView2, öffnet die App die Oberfläche wie früher über Edge bzw. den Browser.
"""

import logging
import threading

from . import APP_NAME
from .config import IS_WINDOWS

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1320, 880
MIN_SIZE = (960, 640)
BACKGROUND = "#0f1013"  # wie die Oberfläche (dunkel), damit beim Öffnen nichts weiß aufblitzt


def windows_is_shutting_down():
    """True, während Windows herunterfährt oder der Benutzer sich abmeldet (SM_SHUTTINGDOWN)."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))
    except Exception:  # noqa: BLE001
        return False


def available():
    """Ist pywebview installiert? (Ob WebView2 vorhanden ist, zeigt sich erst beim Start.)"""
    try:
        import webview  # noqa: F401
    except Exception:  # noqa: BLE001 – ImportError, aber auch kaputte Abhängigkeiten (pythonnet …)
        return False
    return True


class AppWindow:
    def __init__(self, url, storage_path, hidden=False, on_first_hide=None, on_session_end=None,
                 shutting_down=windows_is_shutting_down):
        import webview

        self.webview = webview
        self.url = url
        self.storage_path = str(storage_path)
        self.on_first_hide = on_first_hide
        self.on_session_end = on_session_end
        self.shutting_down = shutting_down
        self.quitting = False
        self.visible = not hidden
        self._hidden_once = False
        self._started = threading.Event()
        try:  # pywebview ≥ 5: CSV-Export erlauben, Links (z. B. Releases) im Browser öffnen
            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception:  # noqa: BLE001
            pass
        self.window = webview.create_window(
            APP_NAME, url, width=WIDTH, height=HEIGHT, min_size=MIN_SIZE,
            hidden=hidden, background_color=BACKGROUND, text_select=True,
        )
        self.window.events.closing += self._on_closing
        self.window.events.shown += lambda *a: self._started.set()

    # ------------------------------------------------------------ Ereignisse
    def _on_closing(self, *args):
        """X gedrückt: nur verstecken. Beim echten Beenden (Tray → Beenden) schließen lassen."""
        if self.quitting:
            return True
        if self.shutting_down():
            # Windows fährt herunter: NIE abbrechen – sonst meldet Windows „NovaTally verhindert das Herunterfahren“
            self.quitting = True
            if self.on_session_end:
                try:
                    self.on_session_end()
                except Exception:  # noqa: BLE001
                    log.exception("Beenden beim Herunterfahren fehlgeschlagen")
            return True
        threading.Thread(target=self.hide, name="FensterVerstecken", daemon=True).start()
        if not self._hidden_once:
            self._hidden_once = True
            if self.on_first_hide:
                try:
                    self.on_first_hide()
                except Exception:  # noqa: BLE001
                    log.exception("Hinweis beim Verstecken fehlgeschlagen")
        return False

    # ------------------------------------------------------------- Steuerung
    def run(self):
        """Blockiert im Hauptthread, bis das Fenster zerstört wird. Wirft, wenn WebView2 fehlt."""
        self.webview.start(gui="edgechromium", private_mode=False, storage_path=self.storage_path)

    def show(self):
        """Fenster zeigen und nach vorne holen (darf aus jedem Thread aufgerufen werden)."""
        self.visible = True
        for action in ("show", "restore"):
            try:
                getattr(self.window, action)()
            except Exception:  # noqa: BLE001 – restore gibt es erst ab pywebview 4
                pass

    def hide(self):
        self.visible = False
        try:
            self.window.hide()
        except Exception:  # noqa: BLE001
            log.exception("Fenster ließ sich nicht verstecken")

    def destroy(self):
        """Wirklich schließen (Tray → Beenden oder Neustart nach Update)."""
        self.quitting = True
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass
