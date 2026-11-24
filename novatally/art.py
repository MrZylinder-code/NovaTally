"""Spiel-Logos: Programmsymbol aus der Spiel-EXE und eigene Bilder pro Spiel.

Dateien liegen neben der Datenbank im Ordner `art/`:
  icon_<id>.png    – automatisch aus der EXE gelesenes Symbol (nur Windows)
  cover_<id>       – vom Nutzer gewähltes Bild (PNG, JPEG, WebP oder GIF)
In der Tabelle `games` merken sich `icon_v`/`cover_v` den Zeitpunkt (dient im Browser als Cache-Schlüssel).
Reihenfolge in der Oberfläche: eigenes Bild > Steam-Cover > EXE-Symbol > Buchstaben.
"""

import logging
import os
import struct
import threading
import time
import zlib

from .config import IS_WINDOWS
from .db import norm_path

log = logging.getLogger(__name__)

ICON_SIZE = 256
MAX_UPLOAD = 10 * 1024 * 1024
FIND_MAX_DEPTH = 3
FIND_MAX_ENTRIES = 20000


def art_dir(db):
    return os.path.join(os.path.dirname(os.path.abspath(db.path)), "art")


def icon_path(db, game_id):
    return os.path.join(art_dir(db), f"icon_{int(game_id)}.png")


def cover_path(db, game_id):
    return os.path.join(art_dir(db), f"cover_{int(game_id)}")


# ------------------------------------------------------------------ Bildformate
def sniff(data):
    """Bildtyp anhand der ersten Bytes – None, wenn es kein unterstütztes Bild ist."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def png_encode(width, height, rgba):
    """RGBA-Pixel (Zeilen von oben nach unten) als PNG – ohne Pillow."""
    if len(rgba) != width * height * 4:
        raise ValueError("Pixelanzahl passt nicht zur Größe")
    stride = width * 4
    raw = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def bgra_to_rgba(bgra, mask=None):
    """Windows liefert BGRA. Symbole ohne Alphakanal (alte Icons) bekommen ihn aus der Maske
    (Maske schwarz = sichtbar)."""
    out = bytearray(len(bgra))
    out[0::4], out[1::4], out[2::4], out[3::4] = bgra[2::4], bgra[1::4], bgra[0::4], bgra[3::4]
    if not any(bgra[3::4]):
        if mask is not None and len(mask) == len(bgra):
            out[3::4] = bytes(0 if m else 255 for m in mask[0::4])
        else:
            out[3::4] = b"\xff" * (len(bgra) // 4)
    return bytes(out)


def is_blank(rgba):
    return not any(rgba[3::4])


# ------------------------------------------------------------- Windows: Symbol
def exe_icon_rgba(path, size=ICON_SIZE):
    """Größtes Programmsymbol einer EXE als (breite, höhe, rgba) – None, wenn es keines gibt."""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                    ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD),
                    ("bmBitsPixel", wintypes.WORD), ("bmBits", ctypes.c_void_p)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    shell32.SHDefExtractIconW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.UINT,
                                          ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
                                          wintypes.UINT]
    shell32.SHDefExtractIconW.restype = ctypes.c_long
    user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]

    hicon = wintypes.HICON()
    # Größe: LOWORD = großes Symbol, HIWORD = kleines (wird nicht angefordert)
    hr = shell32.SHDefExtractIconW(path, 0, 0, ctypes.byref(hicon), None, size | (16 << 16))
    if hr != 0 or not hicon:
        return None  # S_FALSE: die Datei hat kein Symbol
    info = ICONINFO()
    hdc = None
    try:
        if not user32.GetIconInfo(hicon, ctypes.byref(info)) or not info.hbmColor:
            return None
        bm = BITMAP()
        if not gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm)):
            return None
        w, h = bm.bmWidth, abs(bm.bmHeight)
        if not (0 < w <= 1024 and 0 < h <= 1024):
            return None
        hdc = user32.GetDC(None)

        def bits(hbm):
            bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            # Puffer großzügig: BITMAPINFO enthält bei 32 bpp keine Farbtabelle, Reserve schadet nicht
            info_buf = ctypes.create_string_buffer(ctypes.sizeof(BITMAPINFOHEADER) + 1024)
            ctypes.memmove(info_buf, ctypes.byref(bih), ctypes.sizeof(bih))
            buf = ctypes.create_string_buffer(w * h * 4)
            if gdi32.GetDIBits(hdc, hbm, 0, h, buf, info_buf, 0) != h:
                return None
            return buf.raw

        color = bits(info.hbmColor)
        if color is None:
            return None
        mask = bits(info.hbmMask) if info.hbmMask else None
        return w, h, bgra_to_rgba(color, mask)
    finally:
        if hdc:
            user32.ReleaseDC(None, hdc)
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)
        user32.DestroyIcon(hicon)


def find_exe(folder, names, max_depth=FIND_MAX_DEPTH, max_entries=FIND_MAX_ENTRIES):
    """Eine der EXE-Dateien (Namen in Kleinbuchstaben) im Spielordner suchen – flach zuerst, begrenzt."""
    names = {n.lower() for n in names if n}
    if not folder or not names or not os.path.isdir(folder):
        return None
    level, seen = [folder], 0
    for _ in range(max_depth + 1):
        nxt = []
        for d in level:
            try:
                with os.scandir(d) as it:
                    for e in it:
                        seen += 1
                        if seen > max_entries:
                            return None
                        try:
                            if e.is_file() and e.name.lower() in names:
                                return e.path
                            if e.is_dir(follow_symlinks=False):
                                nxt.append(e.path)
                        except OSError:
                            continue
            except OSError:
                continue
        level = nxt
    return None


# ------------------------------------------------------------------ Speichern
def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def save_icon(db, game_id, rgba_info):
    w, h, rgba = rgba_info
    if is_blank(rgba):
        return False
    _write(icon_path(db, game_id), png_encode(w, h, rgba))
    db.set_art_version(game_id, "icon_v", int(time.time()))
    return True


def save_cover(db, game_id, data):
    if len(data) > MAX_UPLOAD:
        raise ValueError("Das Bild ist zu groß (max. 10 MB).")
    if not sniff(data):
        raise ValueError("Bitte ein PNG-, JPEG-, WebP- oder GIF-Bild wählen.")
    _write(cover_path(db, game_id), data)
    db.set_art_version(game_id, "cover_v", int(time.time() * 1000))


def remove_cover(db, game_id):
    try:
        os.remove(cover_path(db, game_id))
    except FileNotFoundError:
        pass
    db.set_art_version(game_id, "cover_v", None)


def read(db, game_id, kind):
    """(daten, content_type) für /art/<id>/<icon|cover> – None, wenn nicht vorhanden."""
    path = icon_path(db, game_id) if kind == "icon" else cover_path(db, game_id)
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_UPLOAD + 1)
    except OSError:
        return None
    ctype = sniff(data)
    return (data, ctype) if ctype else None


class IconFetcher:
    """Liest Programmsymbole im Hintergrund – der Tracker wartet nie darauf.
    Pro Spiel und Programmlauf höchstens ein Versuch."""

    def __init__(self, db, extract=exe_icon_rgba, background=True):
        self.db = db
        self.extract = extract
        self.background = background
        self.tried = set()
        self.lock = threading.Lock()

    def request(self, game_id, exe_path):
        """Symbol für ein Spiel holen, falls es noch keines hat (exe_path darf None sein)."""
        with self.lock:
            if game_id in self.tried:
                return
            self.tried.add(game_id)
        if self.background:
            threading.Thread(target=self._fetch, args=(game_id, exe_path), name="Icon", daemon=True).start()
        else:
            self._fetch(game_id, exe_path)

    def backfill(self):
        """Für schon gespielte Spiele ohne Symbol die EXE im Spielordner suchen."""
        def run():
            for g in self.db.games_without_icon():
                self.request(g["id"], None)
        if self.background:
            threading.Thread(target=run, name="Icon-Backfill", daemon=True).start()
        else:
            run()

    def _exe_for(self, game, exe_path):
        if exe_path and os.path.isfile(exe_path):
            return exe_path
        if game["key"].startswith("exe:"):
            path = game["key"][len("exe:"):]
            return path if os.path.isfile(path) else None
        if game.get("only_exe"):  # z. B. LoL: das Symbol des Spiels, nicht das des Clients
            found = find_exe(game.get("path"), [game["only_exe"]])
            if found:
                return found
        return find_exe(game.get("path"), [e["exe"] for e in self.db.game_exes(game["id"])])

    def _fetch(self, game_id, exe_path):
        try:
            game = self.db.game(game_id)
            if not game or game.get("icon_v"):
                return
            exe = self._exe_for(game, exe_path)
            if not exe:
                return
            img = self.extract(exe)
            if img and save_icon(self.db, game_id, img):
                log.info("Symbol für %s aus %s gelesen", game["name"], os.path.basename(norm_path(exe)))
        except Exception:  # noqa: BLE001 – Symbole sind nur Schmuck
            log.exception("Symbol konnte nicht gelesen werden")
