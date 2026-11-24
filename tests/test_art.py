"""Tests für Spiel-Logos: EXE-Symbol, eigenes Bild, Auslieferung an die Oberfläche."""

import json
import os
import socket
import sqlite3
import struct
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novatally import art, stats  # noqa: E402
from novatally.config import IS_WINDOWS  # noqa: E402
from novatally.db import Database  # noqa: E402
from novatally.library import LibraryEntry  # noqa: E402
from novatally.server import AppContext, start_server  # noqa: E402
from novatally.tracker import Tracker  # noqa: E402


def png_pixels(data):
    """Minimaler PNG-Leser für die eigenen PNGs (RGBA, Filter 0)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, size = 8, b"", None
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, payload = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        crc = struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        assert crc == zlib.crc32(tag + payload) & 0xFFFFFFFF, tag
        if tag == b"IHDR":
            size = struct.unpack(">II", payload[:8])
        elif tag == b"IDAT":
            idat += payload
        pos += 12 + n
    w, h = size
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 4 + 1):(y + 1) * (w * 4 + 1)] for y in range(h)]
    assert all(r[0] == 0 for r in rows)
    return w, h, b"".join(r[1:] for r in rows)


def fake_icon(w=4, h=3):
    return w, h, bytes([200, 40, 30, 255]) * (w * h)


PNG = art.png_encode(*fake_icon())


class BildformatTest(unittest.TestCase):
    def test_png_ohne_pillow(self):
        rgba = bytes(range(48))
        w, h, px = png_pixels(art.png_encode(4, 3, rgba))
        self.assertEqual((w, h, px), (4, 3, rgba))
        with self.assertRaises(ValueError):
            art.png_encode(4, 4, rgba)

    def test_bgra_und_maske(self):
        bgra = bytes([1, 2, 3, 200, 4, 5, 6, 0])
        self.assertEqual(art.bgra_to_rgba(bgra), bytes([3, 2, 1, 200, 6, 5, 4, 0]))
        # alte Symbole ohne Alphakanal: Maske schwarz = sichtbar, weiß = durchsichtig
        old = bytes([1, 2, 3, 0, 4, 5, 6, 0])
        mask = bytes([0, 0, 0, 0, 255, 255, 255, 0])
        self.assertEqual(art.bgra_to_rgba(old, mask), bytes([3, 2, 1, 255, 6, 5, 4, 0]))
        self.assertEqual(art.bgra_to_rgba(old)[3::4], b"\xff\xff")
        self.assertTrue(art.is_blank(bytes(8)))

    def test_bildtyp_erkennen(self):
        self.assertEqual(art.sniff(PNG), "image/png")
        self.assertEqual(art.sniff(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(art.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertEqual(art.sniff(b"GIF89a..."), "image/gif")
        self.assertIsNone(art.sniff(b"<svg onload=alert(1)>"))
        self.assertIsNone(art.sniff(b"MZ\x90\x00"))


class SymbolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "t.db")
        self.calls = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def extract(self, path):
        self.calls.append(path)
        return fake_icon()

    def make_exe(self, *parts):
        p = self.root.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"MZ")
        return str(p)

    def test_exe_suchen_flach_zuerst_und_begrenzt(self):
        deep = self.make_exe("game", "a", "b", "c", "d", "PathOfExile.exe")
        flat = self.make_exe("game", "bin", "PathOfExile.exe")
        folder = str(self.root / "game")
        self.assertEqual(art.find_exe(folder, ["pathofexile.exe"]), flat)
        os.remove(flat)
        self.assertIsNone(art.find_exe(folder, ["pathofexile.exe"]))            # zu tief (Tiefe 4)
        self.assertEqual(art.find_exe(folder, ["pathofexile.exe"], max_depth=4), deep)
        self.assertIsNone(art.find_exe(folder, ["pathofexile.exe"], max_depth=4, max_entries=3))
        self.assertIsNone(art.find_exe(str(self.root / "fehlt"), ["x.exe"]))
        self.assertIsNone(art.find_exe(folder, []))

    def test_tracker_holt_symbol_beim_spielstart(self):
        folder = str(self.root / "Grinding Gear Games" / "Path of Exile")
        exe = self.make_exe("Grinding Gear Games", "Path of Exile", "PathOfExile.exe")
        entries = [LibraryEntry(folder, "folder:poe", "Path of Exile", "ggg", None)]
        fetcher = art.IconFetcher(self.db, extract=self.extract, background=False)
        src = type("Src", (), {"snapshot": lambda s: [(1, "PathOfExile.exe", exe)]})()
        tr = Tracker(self.db, src, scan=lambda extra: entries, icons=fetcher)
        tr.tick(1000)
        game = self.db.game_by_key("folder:poe")
        self.assertEqual(self.calls, [exe])
        self.assertTrue(game["icon_v"])
        w, h, px = png_pixels(Path(art.icon_path(self.db, game["id"])).read_bytes())
        self.assertEqual((w, h), (4, 3))
        tr.tick(1005)
        tr.close_all(1100)
        tr.tick(1200)                                      # neuer Start: hat schon ein Symbol
        self.assertEqual(len(self.calls), 1)
        running = stats.games_list(self.db, now=1300)[0]
        self.assertEqual(running["icon"], game["icon_v"])
        self.assertIsNone(running["cover"])

    def test_kein_symbol_kein_absturz(self):
        exe = self.make_exe("Spiel", "spiel.exe")
        g = self.db.get_or_create_game("exe:" + exe, "Spiel", "manual")
        for result in (None, (2, 1, bytes(8))):           # keins / komplett durchsichtig
            f = art.IconFetcher(self.db, extract=lambda p, r=result: r, background=False)
            f.request(g["id"], exe)
            self.assertIsNone(self.db.game(g["id"])["icon_v"])

        def boom(path):
            raise OSError("kaputt")
        art.IconFetcher(self.db, extract=boom, background=False).request(g["id"], exe)  # wird nur geloggt
        self.assertIsNone(self.db.game(g["id"])["icon_v"])

    def test_nachholen_fuer_alte_spiele(self):
        folder = str(self.root / "Riot Games" / "League of Legends")
        self.make_exe("Riot Games", "League of Legends", "LeagueClient.exe")
        match = self.make_exe("Riot Games", "League of Legends", "Game", "League of Legends.exe")
        lol = self.db.get_or_create_game("folder:lol", "League of Legends", "riot", None, folder)
        manual_exe = self.make_exe("Tools", "emu.exe")
        manual = self.db.add_manual_game(manual_exe, "Emulator")
        nie = self.db.get_or_create_game("folder:nie", "Nie gespielt", "custom", None, folder)
        for g in (lol, manual, nie):
            self.db.record_exe(g["key"], "leagueclient.exe", "LeagueClient.exe", 1)
        for g in (lol, manual):
            sid = self.db.start_session(g["id"], 0)
            self.db.end_session(sid, 3600)
        self.assertEqual({g["id"] for g in self.db.games_without_icon()}, {lol["id"], manual["id"]})
        art.IconFetcher(self.db, extract=self.extract, background=False).backfill()
        # LoL: nur das Match-Programm (only_exe) liefert das Symbol, nicht der Client
        self.assertEqual(sorted(self.calls), sorted([match, os.path.normcase(os.path.normpath(manual_exe))]))
        self.assertEqual(self.db.games_without_icon(), [])

    def test_alte_datenbank_bekommt_spalten(self):
        path = self.root / "alt.db"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
                    "source TEXT NOT NULL DEFAULT '', appid TEXT, path TEXT, ignored INTEGER NOT NULL DEFAULT 0, "
                    "created INTEGER NOT NULL)")
        con.execute("INSERT INTO games(key, name, created) VALUES('steam:1', 'Alt', 0)")
        con.commit()
        con.close()
        db = Database(path)
        try:
            g = db.game_by_key("steam:1")
            self.assertIsNone(g["icon_v"])
            self.assertIsNone(g["cover_v"])
        finally:
            db.close()

    @unittest.skipUnless(IS_WINDOWS, "Programmsymbole gibt es nur unter Windows")
    def test_echtes_windows_symbol(self):
        for exe in (sys.executable, os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")):
            w, h, rgba = art.exe_icon_rgba(exe)
            self.assertGreaterEqual(min(w, h), 32, exe)
            self.assertEqual(len(rgba), w * h * 4)
            self.assertFalse(art.is_blank(rgba), exe)
            png_pixels(art.png_encode(w, h, rgba))
        # Datei ohne Symbol / gar keine EXE: None statt Absturz
        txt = self.root / "kein.exe"
        txt.write_bytes(b"kein Programm")
        self.assertIsNone(art.exe_icon_rgba(str(txt)))
        self.assertIsNone(art.exe_icon_rgba(str(self.root / "fehlt.exe")))


class ArtApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Database(Path(cls.tmp.name) / "api.db")
        cls.game = cls.db.get_or_create_game("folder:poe", "Path of Exile", "ggg")
        sid = cls.db.start_session(cls.game["id"], 0)
        cls.db.end_session(sid, 3600)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.srv = start_server(AppContext(cls.db, None, cls.tmp.name), cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.db.close()
        cls.tmp.cleanup()

    def req(self, path, data=None, headers=None):
        h = {"X-NovaTally": "1"}
        h.update(headers or {})
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_eigenes_bild_hochladen_zeigen_entfernen(self):
        gid = self.game["id"]
        self.assertEqual(self.req(f"/art/{gid}/cover")[0], 404)
        status, body, _ = self.req(f"/api/game/{gid}/cover", PNG, {"Content-Type": "image/png"})
        self.assertEqual(status, 200, body)
        version = json.loads(body)["cover"]
        self.assertTrue(version)
        # <img> schickt keinen X-NovaTally-Header – die Bilder müssen trotzdem laden
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/art/{gid}/cover?v={version}")
        with urllib.request.urlopen(r, timeout=10) as resp:
            self.assertEqual(resp.read(), PNG)
            self.assertEqual(resp.headers["Content-Type"], "image/png")
            self.assertEqual(resp.headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertIn("immutable", resp.headers["Cache-Control"])
            self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
            # die Oberfläche liest gewählte Bilder als blob:-URL zum Verkleinern
            self.assertIn("blob:", resp.headers["Content-Security-Policy"])
        games = json.loads(self.req("/api/games")[1])
        self.assertEqual(games[0]["cover"], version)
        self.assertEqual(json.loads(self.req(f"/api/game/{gid}")[1])["cover"], version)

        status, _, _ = self.req(f"/api/game/{gid}/cover/remove", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(self.req(f"/art/{gid}/cover")[0], 404)
        self.assertIsNone(json.loads(self.req("/api/games")[1])[0]["cover"])

    def test_upload_wird_geprueft(self):
        gid = self.game["id"]
        status, body, _ = self.req(f"/api/game/{gid}/cover", b"<svg onload=alert(1)>", {"Content-Type": "image/svg+xml"})
        self.assertEqual(status, 400)
        self.assertIn("PNG", json.loads(body)["error"])
        self.assertEqual(self.req("/api/game/9999/cover", PNG)[0], 404)
        self.assertEqual(self.req(f"/api/game/{gid}/cover", PNG, {"X-NovaTally": "0"})[0], 403)
        self.assertEqual(self.req(f"/api/game/{gid}/cover", b"", {"Content-Type": "image/png"})[0], 400)

    def test_kaputte_art_pfade(self):
        for path in ("/art/1/icon", "/art/x/icon", "/art/1/../../api.db", "/art/1/logo", "/art/"):
            self.assertEqual(self.req(path)[0], 404, path)

    def test_symbol_ausliefern(self):
        gid = self.game["id"]
        art.save_icon(self.db, gid, fake_icon())
        status, body, headers = self.req(f"/art/{gid}/icon?v=1")
        self.assertEqual((status, headers["Content-Type"]), (200, "image/png"))
        self.assertEqual(png_pixels(body)[:2], (4, 3))


if __name__ == "__main__":
    unittest.main()
