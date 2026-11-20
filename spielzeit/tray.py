"""Tray-Symbol (pystray + Pillow). Läuft im Hauptthread."""

import logging

log = logging.getLogger(__name__)


def draw_icon(paused=False, size=64):
    """Symbol mit Pillow zeichnen: abgerundetes Quadrat mit Play-Zeichen (pausiert: grau mit Pause-Balken)."""
    from PIL import Image, ImageDraw

    s = size * 4  # überabtasten, dann verkleinern -> glatte Kanten
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top, bottom = ((110, 110, 118), (70, 70, 78)) if paused else ((57, 135, 229), (98, 80, 214))
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([s * 0.04, s * 0.04, s * 0.96, s * 0.96], radius=s * 0.22, fill=255)
    img.paste(grad, (0, 0), mask)
    white = (255, 255, 255, 255)
    # Ring
    d.ellipse([s * 0.2, s * 0.2, s * 0.8, s * 0.8], outline=white, width=int(s * 0.07))
    if paused:
        d.rectangle([s * 0.40, s * 0.37, s * 0.46, s * 0.63], fill=white)
        d.rectangle([s * 0.54, s * 0.37, s * 0.60, s * 0.63], fill=white)
    else:
        d.polygon([(s * 0.43, s * 0.36), (s * 0.43, s * 0.64), (s * 0.65, s * 0.50)], fill=white)
    return img.resize((size, size), Image.LANCZOS)


class Tray:
    def __init__(self, db, open_window, on_quit):
        import pystray  # ImportError wird von der App abgefangen

        self.pystray = pystray
        self.db = db
        self.open_window = open_window
        self.on_quit = on_quit
        self.icon = pystray.Icon(
            "Spielzeit",
            icon=draw_icon(self._paused()),
            title=self._title(),
            menu=pystray.Menu(
                pystray.MenuItem("Spielzeit öffnen", self._open, default=True),
                pystray.MenuItem("Tracking pausieren", self._toggle_pause, checked=lambda item: self._paused()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Beenden", self._quit),
            ),
        )

    def _paused(self):
        return bool(self.db.get_setting("paused", False))

    def _title(self):
        return "Spielzeit – pausiert" if self._paused() else "Spielzeit – Tracking aktiv"

    def _open(self, icon=None, item=None):
        self.open_window()

    def _toggle_pause(self, icon=None, item=None):
        self.db.set_setting("paused", not self._paused())
        self.refresh()

    def refresh(self):
        try:
            self.icon.icon = draw_icon(self._paused())
            self.icon.title = self._title()
            self.icon.update_menu()
        except Exception:  # noqa: BLE001
            log.exception("Tray-Symbol konnte nicht aktualisiert werden")

    def _quit(self, icon=None, item=None):
        self.on_quit()
        self.icon.stop()

    def run(self):
        self.icon.run()
