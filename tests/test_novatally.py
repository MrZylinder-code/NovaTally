"""Tests nur mit der Standardbibliothek – laufen auch unter Linux ohne psutil/pystray.

Aufruf:  python -m unittest discover -s tests -v
"""

import json
import os
import socket
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novatally import demo, library, stats  # noqa: E402
from novatally.db import Database  # noqa: E402
from novatally.library import LibraryEntry  # noqa: E402
from novatally.server import AppContext, start_server  # noqa: E402
from novatally.tracker import Tracker  # noqa: E402

SEP = os.sep
GAMES = SEP + os.path.join("spiele")
HADES = os.path.join(GAMES, "steamapps", "common", "Hades II")
FACTORIO = os.path.join(GAMES, "steamapps", "common", "Factorio")
OTHER = os.path.join(GAMES, "Indie")
NESTED = os.path.join(OTHER, "Bonus")

ENTRIES = [
    LibraryEntry(HADES, "steam:1145350", "Hades II", "steam", "1145350"),
    LibraryEntry(FACTORIO, "steam:427520", "Factorio", "steam", "427520"),
    LibraryEntry(OTHER, "folder:indie", "Indie", "custom", None),
    LibraryEntry(NESTED, "folder:bonus", "Bonus", "custom", None),
]


class FakeSource:
    def __init__(self):
        self.procs = []

    def snapshot(self):
        return list(self.procs)


def ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi).timestamp()


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.src = FakeSource()
        self.tr = Tracker(self.db, self.src, scan=lambda extra: ENTRIES)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_ticks(self, start, stop, step=5):
        t = start
        while t <= stop:
            self.tr.tick(t)
            t += step

    def sessions(self):
        return self.db.all_sessions(include_ignored=True)

    def test_start_und_ende(self):
        self.src.procs = [(100, "Hades2.exe", os.path.join(HADES, "Ship", "Hades2.exe"))]
        self.run_ticks(1000, 1300)
        self.assertEqual(len(self.db.open_sessions()), 1)
        self.src.procs = []
        self.tr.tick(1305)
        s = self.sessions()
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["start"], s[0]["end"], s[0]["open"]), (1000, 1305, 0))
        self.assertEqual(s[0]["name"], "Hades II")
        self.assertEqual(self.db.game(s[0]["game_id"])["appid"], "1145350")

    def test_mindestdauer(self):
        self.src.procs = [(1, "factorio.exe", os.path.join(FACTORIO, "bin", "factorio.exe"))]
        self.run_ticks(0, 55)
        self.src.procs = []
        self.tr.tick(59)
        self.assertEqual(self.sessions(), [])

    def test_mehrere_prozesse_eine_sitzung(self):
        self.src.procs = [
            (1, "Hades2.exe", os.path.join(HADES, "Hades2.exe")),
            (2, "helper.exe", os.path.join(HADES, "tools", "helper.exe")),
        ]
        self.run_ticks(0, 120)
        self.src.procs = [(2, "helper.exe", os.path.join(HADES, "tools", "helper.exe"))]
        self.run_ticks(125, 200)
        self.src.procs = []
        self.tr.tick(205)
        s = self.sessions()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["end"] - s[0]["start"], 205)

    def test_zwei_spiele_gleichzeitig(self):
        self.src.procs = [(1, "a.exe", os.path.join(HADES, "a.exe")), (2, "f.exe", os.path.join(FACTORIO, "f.exe"))]
        self.run_ticks(0, 100)
        self.src.procs = []
        self.tr.tick(105)
        self.assertEqual(sorted(s["name"] for s in self.sessions()), ["Factorio", "Hades II"])

    def test_laengster_ordner_gewinnt(self):
        self.src.procs = [(1, "b.exe", os.path.join(NESTED, "b.exe"))]
        self.run_ticks(0, 100)
        self.src.procs = []
        self.tr.tick(105)
        self.assertEqual([s["name"] for s in self.sessions()], ["Bonus"])

    def test_ordnerpraefix_nicht_teilwort(self):
        # "/spiele/Indie2/x.exe" darf nicht zu "/spiele/Indie" passen
        self.tr.tick(0)  # Bibliothek laden
        self.assertIsNone(self.tr.match("x.exe", os.path.join(GAMES, "Indie2", "x.exe")))
        self.assertEqual(self.tr.match("x.exe", os.path.join(OTHER, "x.exe"))[1], "Indie")

    def test_ignorierte_exe(self):
        self.src.procs = [
            (1, "UnityCrashHandler64.exe", os.path.join(HADES, "UnityCrashHandler64.exe")),
            (2, "setup.exe", os.path.join(FACTORIO, "setup.exe")),
            (3, "unins000.exe", os.path.join(OTHER, "unins000.exe")),
        ]
        self.run_ticks(0, 200)
        self.assertEqual(self.db.open_sessions(), [])
        self.assertEqual(self.db.games(include_ignored=True), [])

    def test_unbekannter_prozess(self):
        self.src.procs = [(1, "notepad.exe", os.path.join(SEP + "windows", "notepad.exe")), (2, "x", None)]
        self.run_ticks(0, 100)
        self.assertEqual(self.db.games(include_ignored=True), [])

    def test_standby_luecke(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 600)
        # PC schläft eine Stunde, das Spiel läuft danach weiter
        self.run_ticks(4200, 4500)
        self.src.procs = []
        self.tr.tick(4505)
        s = self.sessions()
        self.assertEqual([(x["start"], x["end"]) for x in s], [(0, 600), (4200, 4505)])

    def test_kleine_verzoegerung_ist_keine_luecke(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 100)
        self.tr.tick(160)  # 60 s Verzögerung < 3×5+60
        self.src.procs = []
        self.tr.tick(165)
        self.assertEqual([(x["start"], x["end"]) for x in self.sessions()], [(0, 165)])

    def test_heartbeat_und_absturz(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 95)  # Heartbeats bei 0, 30, 60, 90
        s = self.sessions()[0]
        self.assertEqual((s["end"], s["open"]), (90, 1))
        # Absturz: kein sauberes Ende. Neustart schließt beim letzten Heartbeat.
        db2 = Database(self.db.path)
        self.assertEqual(db2.close_stale_sessions(), 1)
        s = db2.all_sessions()[0]
        self.assertEqual((s["start"], s["end"], s["open"]), (0, 90, 0))
        db2.close()

    def test_absturz_kurze_sitzung_wird_verworfen(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 40)  # letzter Heartbeat bei 30 -> zu kurz
        self.assertEqual(self.db.close_stale_sessions(), 0)
        self.assertEqual(self.sessions(), [])

    def test_pause(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 100)
        self.db.set_setting("paused", True)
        self.run_ticks(105, 300)
        self.assertEqual(self.db.open_sessions(), [])
        self.assertEqual([(x["start"], x["end"]) for x in self.sessions()], [(0, 105)])
        self.db.set_setting("paused", False)
        self.run_ticks(305, 400)
        self.assertEqual(len(self.db.open_sessions()), 1)

    def test_ausgeblendetes_spiel(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 100)
        gid = self.sessions()[0]["game_id"]
        self.db.set_ignored(gid, True)
        self.run_ticks(105, 300)
        self.assertEqual(self.db.open_sessions(), [])
        self.assertEqual(len(self.sessions()), 1)  # alte Sitzung bleibt, keine neue
        self.assertEqual(self.db.all_sessions(), [])  # ...aber nicht in der Statistik

    def test_manuelles_spiel(self):
        exe = os.path.join(SEP + "irgendwo", "MeinSpiel", "game.exe")
        self.db.add_manual_game(exe, "Mein Spiel")
        self.tr.force_rescan()
        self.src.procs = [(7, "game.exe", exe)]
        self.run_ticks(0, 100)
        self.src.procs = []
        self.tr.tick(105)
        self.assertEqual([s["name"] for s in self.sessions()], ["Mein Spiel"])
        # Prozess ohne lesbaren Pfad: Zuordnung über den Dateinamen
        self.src.procs = [(8, "game.exe", None)]
        self.run_ticks(200, 300)
        self.assertEqual(len(self.db.open_sessions()), 1)

    def test_stop_schliesst_sitzungen(self):
        self.src.procs = [(1, "Hades2.exe", os.path.join(HADES, "Hades2.exe"))]
        self.run_ticks(0, 100)
        self.tr.close_all(150)
        self.assertEqual([(x["end"], x["open"]) for x in self.sessions()], [(150, 0)])


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "s.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_split_mitternacht(self):
        parts = list(stats.split_days(ts(2026, 3, 9, 23, 0), ts(2026, 3, 10, 1, 30)))
        self.assertEqual([(d.isoformat(), round(s)) for d, s in parts], [("2026-03-09", 3600), ("2026-03-10", 5400)])

    def test_split_mehrere_tage(self):
        parts = list(stats.split_days(ts(2026, 3, 9, 22, 0), ts(2026, 3, 11, 2, 0)))
        self.assertEqual([round(s) for _, s in parts], [7200, 86400, 7200])

    def test_split_stunden(self):
        parts = list(stats.split_hours(ts(2026, 3, 9, 23, 30), ts(2026, 3, 10, 1, 15)))
        self.assertEqual([(h, round(s)) for h, s in parts], [(23, 1800), (0, 3600), (1, 900)])

    def test_overview_mitternacht_und_serie(self):
        g = self.db.get_or_create_game("steam:1", "Spiel", "steam", "1")
        now = ts(2026, 3, 12, 12, 0)
        self.db.insert_sessions([
            (g["id"], ts(2026, 3, 9, 23, 0), ts(2026, 3, 10, 1, 30)),
            (g["id"], ts(2026, 3, 11, 20, 0), ts(2026, 3, 11, 21, 0)),
            (g["id"], ts(2026, 3, 12, 9, 0), ts(2026, 3, 12, 9, 45)),
        ])
        o = stats.overview(self.db, "7", now=now)
        days = {b["start"]: sum(b["values"]) for b in o["history"]["buckets"]}
        self.assertEqual(days["2026-03-09"], 3600)
        self.assertEqual(days["2026-03-10"], 5400)
        self.assertEqual(days["2026-03-12"], 2700)
        self.assertEqual(o["kpis"]["today"], 2700)
        self.assertEqual(o["kpis"]["total"], 3600 + 5400 + 3600 + 2700)
        self.assertEqual(o["streak"], {"current": 4, "longest": 4})
        self.assertEqual(sum(o["hours"]), o["kpis"]["total"])
        self.assertEqual(o["hours"][23], 3600)
        self.assertEqual(len(o["heatmap"]["days"]) % 7, 4)  # Montag bis heute (Donnerstag)
        self.assertEqual(o["longest_session"]["seconds"], 9000)

    def test_farben_folgen_dem_spiel(self):
        ids = [self.db.get_or_create_game(f"steam:{i}", f"Spiel {i}", "steam")["id"] for i in range(9)]
        now = ts(2026, 3, 12, 12)
        rows = []
        for i, gid in enumerate(ids):  # Spiel 0 hat am meisten Gesamtzeit
            rows.append((gid, ts(2025, 6, 1, 10) + i * 100000, ts(2025, 6, 1, 10) + i * 100000 + (20 - i) * 3600))
        rows.append((ids[8], ts(2026, 3, 11, 10), ts(2026, 3, 11, 18)))  # Spiel 8 dominiert die letzte Woche
        self.db.insert_sessions(rows)
        o7 = stats.overview(self.db, "7", now=now)
        oall = stats.overview(self.db, "all", now=now)
        slots_all = {s["id"]: s["slot"] for s in oall["history"]["series"]}
        for s in o7["history"]["series"]:
            if s["id"]:
                self.assertEqual(slots_all[s["id"]], s["slot"])
        self.assertIn("Andere", [s["name"] for s in oall["history"]["series"]])
        self.assertEqual(len(oall["history"]["series"]), 8)  # 7 Farben + Andere

    def test_offene_sitzung_zaehlt_live(self):
        g = self.db.get_or_create_game("steam:1", "Spiel", "steam")
        sid = self.db.start_session(g["id"], 1000)
        running, last = stats.status_running(self.db, now=1600)
        self.assertEqual(running[0]["start"], 1000)
        self.assertEqual(stats.game_detail(self.db, g["id"], now=1600)["seconds"], 600)
        self.assertIsNone(last)
        self.assertFalse(self.db.delete_session(sid))  # laufende Sitzungen nicht löschbar

    def test_bereiche(self):
        demo.fill(self.db, now=ts(2026, 3, 12, 22))
        now = ts(2026, 3, 12, 22)
        for rng, n in (("7", 7), ("30", 30), ("90", 90), ("365", 53)):
            o = stats.overview(self.db, rng, now=now)
            self.assertEqual(len(o["history"]["buckets"]), n, rng)
        o = stats.overview(self.db, "all", now=now)
        self.assertEqual(o["history"]["unit"], "month")
        self.assertGreaterEqual(len(o["history"]["buckets"]), 14)
        total = sum(sum(b["values"]) for b in o["history"]["buckets"])
        self.assertAlmostEqual(total, o["kpis"]["total"], delta=len(o["history"]["buckets"]) * 20)


class LibraryTest(unittest.TestCase):
    def test_steam(self):
        with tempfile.TemporaryDirectory() as tmp:
            steam = Path(tmp) / "Steam"
            lib2 = Path(tmp) / "Bib2"
            (steam / "steamapps").mkdir(parents=True)
            (lib2 / "steamapps").mkdir(parents=True)
            (steam / "steamapps" / "libraryfolders.vdf").write_text(
                '"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n "1"\n {\n  "path"  "%s"\n }\n}\n'
                % (str(steam).replace("\\", "\\\\"), str(lib2).replace("\\", "\\\\")))

            def acf(folder, appid, name, inst):
                (folder / "steamapps" / f"appmanifest_{appid}.acf").write_text(
                    '"AppState"\n{\n "appid"  "%s"\n "name"  "%s"\n "installdir"  "%s"\n}\n' % (appid, name, inst))

            acf(steam, "730", "Counter-Strike 2", "Counter-Strike Global Offensive")
            acf(steam, "228980", "Steamworks Common Redistributables", "Steamworks Shared")
            acf(lib2, "1145350", "Hades II", "Hades II")
            acf(lib2, "1493710", "Proton Experimental", "Proton - Experimental")
            games = library.steam_games(str(steam))
            self.assertEqual(sorted(g.name for g in games), ["Counter-Strike 2", "Hades II"])
            hades = [g for g in games if g.appid == "1145350"][0]
            self.assertEqual(hades.folder, str(lib2 / "steamapps" / "common" / "Hades II"))
            self.assertEqual(hades.key, "steam:1145350")

    def test_vdf_backslashes(self):
        text = '"path"\t\t"D:\\\\SteamLibrary"\n"path" "C:\\\\Program Files (x86)\\\\Steam"'
        self.assertEqual(library.parse_libraryfolders(text), ["D:\\SteamLibrary", "C:\\Program Files (x86)\\Steam"])

    def test_epic(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.item").write_text(json.dumps({"DisplayName": "Fortnite", "InstallLocation": "/x/Fortnite", "AppName": "Fortnite"}))
            Path(tmp, "b.item").write_text("kaputt")
            games = library.epic_games(tmp)
            self.assertEqual([(g.name, g.key, g.source) for g in games], [("Fortnite", "epic:fortnite", "epic")])

    def test_unterordner(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("Spiel A", "Riot Client", "Launcher", "Spiel B"):
                Path(tmp, n).mkdir()
            Path(tmp, "datei.txt").write_text("x")
            games = library.subfolder_games(tmp, "custom")
            self.assertEqual([g.name for g in games], ["Spiel A", "Spiel B"])
            self.assertEqual(library.scan([tmp])[-1].source, "custom")


class LegacyTest(unittest.TestCase):
    def test_alte_daten_werden_uebernommen(self):
        from novatally.config import migrate_legacy_db
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp, "Spielzeit"), Path(tmp, "NovaTally")
            old.mkdir(); new.mkdir()
            db = Database(old / "spielzeit.db")
            g = db.get_or_create_game("steam:1", "Altes Spiel", "steam")
            db.insert_sessions([(g["id"], 1000, 5000)])
            db.close()
            self.assertTrue(migrate_legacy_db(old, new))
            db2 = Database(new / "novatally.db")
            self.assertEqual([s["name"] for s in db2.all_sessions()], ["Altes Spiel"])
            db2.close()
            self.assertTrue((old / "spielzeit.db").exists())  # Original bleibt als Sicherung
            self.assertFalse(migrate_legacy_db(old, new))     # nie eine vorhandene DB überschreiben
            self.assertFalse(migrate_legacy_db(None, new))
            self.assertFalse(migrate_legacy_db(Path(tmp, "gibtsnicht"), Path(tmp)))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Database(Path(cls.tmp.name) / "api.db")
        demo.fill(cls.db)
        demo.start_running(cls.db)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.ctx = AppContext(cls.db, None, cls.tmp.name, demo=False, tracker_note="Test")
        cls.srv = start_server(cls.ctx, cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.db.close()
        cls.tmp.cleanup()

    def req(self, path, body=None, headers=None, raw=False):
        h = {"X-NovaTally": "1"}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                content = resp.read()
                return resp.status, (content if raw else json.loads(content)), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), e.headers

    def test_alle_get_endpunkte_liefern_json(self):
        gid = self.db.games()[0]["id"]
        for path in ["/api/ping", "/api/status", "/api/games", f"/api/game/{gid}", "/api/sessions?limit=50",
                     "/api/processes", "/api/settings"] + [f"/api/overview?range={r}" for r in ("7", "30", "90", "365", "all", "quatsch")]:
            status, data, headers = self.req(path)
            self.assertEqual(status, 200, path)
            self.assertIn("application/json", headers["Content-Type"], path)
            self.assertIsNotNone(data, path)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, data, _ = self.req("/api/status")
        self.assertEqual(data["running"][0]["name"], "Hades II")
        status, data, _ = self.req("/api/sessions?limit=50")
        self.assertEqual(len(data), 50)

    def test_sicherheit(self):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/ping")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r, timeout=5)
        self.assertEqual(cm.exception.code, 403)
        status, _, _ = self.req("/api/ping", headers={"Host": f"boese.example:{self.port}"})
        self.assertEqual(status, 403)
        status, _, _ = self.req("/", headers={"Host": "novatally.example:%d" % self.port}, raw=True)
        self.assertEqual(status, 403)  # auch die Oberfläche selbst (DNS-Rebinding)
        status, _, _ = self.req("/api/game/999999")
        self.assertEqual(status, 404)

    def test_statische_dateien(self):
        for path, ctype in (("/", "text/html"), ("/app.js", "javascript"), ("/app.css", "text/css"), ("/icon.ico", "image/x-icon")):
            r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
            with urllib.request.urlopen(r, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(ctype, resp.headers["Content-Type"])
                self.assertIn("default-src 'self'", resp.headers["Content-Security-Policy"])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/../novatally/db.py", timeout=5)

    def test_csv_export(self):
        status, content, headers = self.req("/api/export.csv", raw=True)
        self.assertEqual(status, 200)
        text = content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        self.assertTrue(lines[0].startswith("Spiel;Quelle;Start;Ende"))
        self.assertEqual(len(lines) - 1, self.db.session_count())
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_post_aktionen(self):
        gid = self.db.game_by_key("steam:730")["id"]
        self.assertEqual(self.req(f"/api/game/{gid}/rename", {"name": "CS2"})[0], 200)
        self.assertEqual(self.db.game(gid)["name"], "CS2")
        self.assertEqual(self.req(f"/api/game/{gid}/rename", {"name": "  "})[0], 400)
        self.assertEqual(self.req(f"/api/game/{gid}/ignore", {"ignored": True})[0], 200)
        _, settings, _ = self.req("/api/settings")
        self.assertIn(gid, [g["id"] for g in settings["ignored"]])
        _, games, _ = self.req("/api/games")
        self.assertNotIn(gid, [g["id"] for g in games])
        self.assertEqual(self.req(f"/api/game/{gid}/ignore", {"ignored": False})[0], 200)

        sid = self.db.game_sessions(gid)[-1]["id"]
        before = self.db.session_count()
        self.assertEqual(self.req(f"/api/session/{sid}/delete", {})[0], 200)
        self.assertEqual(self.db.session_count(), before - 1)
        self.assertEqual(self.req(f"/api/session/{sid}/delete", {})[0], 404)

        status, data, _ = self.req("/api/games/add", {"exe": "/opt/spiel/spiel.exe", "name": "Mein Spiel"})
        self.assertEqual(status, 200)
        self.assertEqual(self.db.game(data["id"])["source"], "manual")

        status, data, _ = self.req("/api/settings", {"paused": True, "theme": "light", "extra_folders": [self.tmp.name]})
        self.assertEqual(status, 200)
        self.assertTrue(data["paused"])
        self.assertEqual(data["theme"], "light")
        self.assertEqual(data["extra_folders"], [os.path.normpath(self.tmp.name)])
        self.assertEqual(self.req("/api/settings", {"theme": "pink"})[0], 400)
        self.assertEqual(self.req("/api/settings", {"extra_folders": ["/gibt/es/nicht"]})[0], 400)
        self.req("/api/settings", {"paused": False, "theme": "dark", "extra_folders": []})

    def test_kaputtes_json(self):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/settings", data=b"{nope",
                                   headers={"X-NovaTally": "1", "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r, timeout=5)
        self.assertEqual(cm.exception.code, 400)

    def test_einzelinstanz(self):
        from novatally.app import ping
        self.assertTrue(ping(self.port))
        with self.assertRaises(OSError):
            start_server(self.ctx, self.port)


if __name__ == "__main__":
    unittest.main(verbosity=2)
