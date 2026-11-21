"""Eigenes NovaTally-Fenster mit pywebview + WebView2 (in Windows 10/11 eingebaut).

Es gibt immer genau ein Fenster. Schließen (X) versteckt es nur – NovaTally zählt im Infobereich weiter.
Fehlt pywebview oder WebView2, öffnet die App die Oberfläche wie früher über Edge bzw. den Browser.
"""

import logging
import threading

from . import APP_NAME

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1320, 880
MIN_SIZE = (960, 640)
BACKGROUND = "#0f1013"  # wie die Oberfläche (dunkel), damit beim Öffnen nichts weiß aufblitzt


def available():
    """Ist pywebview installiert? (Ob WebView2 vorhanden ist, zeigt sich erst beim Start.)"""
    try:
        import webview  # noqa: F401
    except Exception:  # noqa: BLE001 – ImportError, aber auch kaputte Abhängigkeiten (pythonnet …)
        return False
    return True


class AppWindow:
    def __init__(self, url, storage_path, hidden=False, on_first_hide=None):
        import webview

        self.webview = webview
        self.url = url
        self.storage_path = str(storage_path)
        self.on_first_hide = on_first_hide
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
