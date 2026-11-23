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

    def test_anti_cheat_dienst_im_spielordner(self):
        self.src.procs = [(1, "vgc.exe", os.path.join(OTHER, "vgc.exe")),
                          (2, "BEService.exe", os.path.join(OTHER, "BEService.exe"))]
        self.run_ticks(0, 200)
        self.assertEqual(self.db.open_sessions(), [])

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


LOL = os.path.join(GAMES, "Riot Games", "League of Legends")


class SpielprogrammTest(unittest.TestCase):
    """Nur das eigentliche Spielprogramm zählen – z. B. bei League of Legends nur das Match, nicht den Client."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.src = FakeSource()
        entries = ENTRIES + [LibraryEntry(LOL, "folder:lol", "League of Legends", "riot", None)]
        self.tr = Tracker(self.db, self.src, scan=lambda extra: entries)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_ticks(self, start, stop, step=5):
        t = start
        while t <= stop:
            self.tr.tick(t)
            t += step

    def test_league_of_legends_zaehlt_nur_matches(self):
        client = [(10, "LeagueClient.exe", os.path.join(LOL, "LeagueClient.exe")),
                  (11, "LeagueClientUx.exe", os.path.join(LOL, "LeagueClientUx.exe"))]
        match = (20, "League of Legends.exe", os.path.join(LOL, "Game", "League of Legends.exe"))
        self.src.procs = client                 # Lobby, Warteschlange, Champion-Auswahl
        self.run_ticks(0, 600)
        self.src.procs = client + [match]       # Match: 25 Minuten
        self.run_ticks(605, 2105)
        self.src.procs = client                 # zurück in der Lobby
        self.run_ticks(2110, 2700)
        self.src.procs = []
        self.tr.tick(2705)
        s = self.db.all_sessions()
        self.assertEqual([(x["name"], x["start"], x["end"]) for x in s], [("League of Legends", 605, 2110)])
        game = self.db.game_by_key("folder:lol")
        self.assertEqual(game["only_exe"], "league of legends.exe")  # Vorgabe greift automatisch
        seen = {e["exe"] for e in self.db.game_exes(game["id"])}
        self.assertEqual(seen, {"leagueclient.exe", "leagueclientux.exe", "league of legends.exe"})

    def test_alle_programme_zaehlen_wieder(self):
        self.src.procs = [(10, "LeagueClient.exe", os.path.join(LOL, "LeagueClient.exe"))]
        self.run_ticks(0, 30)
        game = self.db.game_by_key("folder:lol")
        self.db.set_only_exe(game["id"], None)  # Nutzer: „Alle Programme im Spielordner“
        self.run_ticks(35, 300)
        self.src.procs = []
        self.tr.tick(305)
        self.assertEqual([(x["start"], x["end"]) for x in self.db.all_sessions()], [(35, 305)])

    def test_eigene_wahl_fuer_anderes_spiel(self):
        self.db.get_or_create_game("steam:427520", "Factorio", "steam", "427520")
        self.db.set_only_exe(self.db.game_by_key("steam:427520")["id"], "Factorio.exe")
        launcher = (1, "launcher.exe", os.path.join(FACTORIO, "launcher.exe"))
        spiel = (2, "factorio.exe", os.path.join(FACTORIO, "bin", "factorio.exe"))  # Groß/klein egal
        self.src.procs = [launcher]
        self.run_ticks(0, 300)
        self.assertEqual(self.db.open_sessions(), [])
        self.src.procs = [launcher, spiel]
        self.run_ticks(305, 600)
        self.assertEqual(len(self.db.open_sessions()), 1)

    def test_vorgabe_fuer_bestehende_spiele_nur_einmal(self):
        g = self.db.get_or_create_game("folder:alt", "Platzhalter", "riot")
        self.db.rename_game(g["id"], "League of Legends")
        self.db._run("UPDATE games SET only_exe=NULL WHERE id=?", (g["id"],))  # wie in einer alten Datenbank
        self.assertEqual(self.db.apply_only_exe_defaults(), ["League of Legends"])
        self.assertEqual(self.db.game(g["id"])["only_exe"], "league of legends.exe")
        self.db.set_only_exe(g["id"], None)  # Nutzer will alles zählen
        self.assertEqual(self.db.apply_only_exe_defaults(), [])
        self.assertIsNone(self.db.game(g["id"])["only_exe"])

    def test_alte_datenbank_wird_erweitert(self):
        import sqlite3
        path = Path(self.tmp.name) / "alt.db"
        con = sqlite3.connect(path)
        con.executescript("CREATE TABLE games (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, name TEXT NOT NULL,"
                          " source TEXT NOT NULL DEFAULT '', appid TEXT, path TEXT, ignored INTEGER NOT NULL DEFAULT 0,"
                          " created INTEGER NOT NULL);"
                          "INSERT INTO games(key, name, created) VALUES('steam:1', 'Alt', 0);")
        con.close()
        db = Database(path)
        self.assertIsNone(db.game_by_key("steam:1")["only_exe"])
        db.close()


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

    def test_bekannte_nicht_spiele_einmalig_ausschliessen(self):
        we = self.db.get_or_create_game("steam:431960", "Wallpaper Engine", "steam", "431960")
        self.db.insert_sessions([(we["id"], 1000, 90000)])
        keys = [f"steam:{a}" for a in library.STEAM_EXCLUDED_APPIDS]
        self.assertEqual(self.db.auto_exclude(keys), ["Wallpaper Engine"])
        self.assertTrue(self.db.game(we["id"])["ignored"])
        self.assertEqual(self.db.all_sessions(), [])  # zählt nicht mehr in der Statistik
        # Nutzer schließt es bewusst wieder ein -> darf beim nächsten Start nicht erneut passieren
        self.db.set_ignored(we["id"], False)
        self.assertEqual(self.db.auto_exclude(keys), [])
        self.assertFalse(self.db.game(we["id"])["ignored"])

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
            acf(lib2, "431960", "Wallpaper Engine", "wallpaper_engine")
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

    def test_installierte_programme(self):
        root = SEP + os.path.join("pf86")
        poe = os.path.join(root, "Grinding Gear Games", "Path of Exile")
        entries = [
            # Standalone-Client: Ordner nur über das Symbol bekannt
            {"DisplayName": "Path of Exile", "Publisher": "Grinding Gear Games", "InstallLocation": None,
             "DisplayIcon": '"%s",0' % os.path.join(poe, "PathOfExile.exe")},
            {"DisplayName": "Diablo IV", "Publisher": "Blizzard Entertainment",
             "InstallLocation": os.path.join(root, "Diablo IV") + SEP},
            {"DisplayName": "Dragon Age: Origins", "Publisher": "Electronic Arts",
             "InstallLocation": os.path.join(root, "Dragon Age")},
            # nicht als Spiel zählen:
            {"DisplayName": "Riot Vanguard", "Publisher": "Riot Games, Inc.",
             "InstallLocation": os.path.join(root, "Riot Vanguard")},
            {"DisplayName": "Battle.net", "Publisher": "Blizzard Entertainment",
             "InstallLocation": os.path.join(root, "Battle.net")},
            {"DisplayName": "EA app", "Publisher": "Electronic Arts", "InstallLocation": os.path.join(root, "EA")},
            {"DisplayName": "Origin", "Publisher": "Electronic Arts", "InstallLocation": os.path.join(root, "Origin")},
            {"DisplayName": "Rockstar Games Launcher", "Publisher": "Rockstar Games",
             "InstallLocation": os.path.join(root, "Rockstar Games", "Launcher")},
            {"DisplayName": "Notepad++", "Publisher": "Notepad++ Team", "InstallLocation": os.path.join(root, "npp")},
            {"DisplayName": "Kaputt", "Publisher": "Blizzard Entertainment", "InstallLocation": SEP},
            {"DisplayName": "Ohne Ort", "Publisher": "Wargaming.net", "InstallLocation": "", "DisplayIcon": "x.ico"},
            {"DisplayName": None, "Publisher": "Blizzard Entertainment", "InstallLocation": os.path.join(root, "X")},
        ]
        games = library.uninstall_games(entries)
        self.assertEqual([(g.name, g.source) for g in games],
                         [("Path of Exile", "ggg"), ("Diablo IV", "battlenet"), ("Dragon Age: Origins", "ea")])
        self.assertEqual(games[0].folder, poe)
        self.assertEqual(games[1].folder, os.path.join(root, "Diablo IV"))  # ohne abschließenden Trenner

    def test_zu_allgemeine_ordner(self):
        self.assertTrue(library.is_too_generic(SEP))
        self.assertTrue(library.is_too_generic(SEP + "Games"))
        self.assertFalse(library.is_too_generic(os.path.join(SEP + "Games", "Path of Exile")))
        old = os.environ.get("ProgramFiles")
        os.environ["ProgramFiles"] = os.path.join(SEP + "x", "Programme")
        try:
            self.assertTrue(library.is_too_generic(os.path.join(SEP + "x", "Programme") + SEP))
        finally:
            if old is None:
                del os.environ["ProgramFiles"]
            else:
                os.environ["ProgramFiles"] = old

    def test_nur_feste_laufwerke(self):
        # Bitmaske: A, C, D, E, Z vorhanden
        mask = (1 << 0) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 25)
        types_ = {"C:\\": 3, "D:\\": 5, "E:\\": 2, "Z:\\": 4}  # fest, DVD, Wechseldatenträger, Netz
        self.assertEqual(library.fixed_drives(mask, lambda r: types_.get(r, 0)), ["C:\\"])

    def test_unterordner(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in ("Spiel A", "Riot Client", "Launcher", "Spiel B"):
                Path(tmp, n).mkdir()
            Path(tmp, "datei.txt").write_text("x")
            games = library.subfolder_games(tmp, "custom")
            self.assertEqual([g.name for g in games], ["Spiel A", "Spiel B"])
            self.assertEqual(library.scan([tmp])[-1].source, "custom")


class FensterTest(unittest.TestCase):
    def test_novatally_fenster_erkennen(self):
        from novatally.app import is_app_window
        self.assertTrue(is_app_window("NovaTally", "Chrome_WidgetWin_1"))
        self.assertTrue(is_app_window("NovaTally - Microsoft Edge", "Chrome_WidgetWin_1"))
        self.assertFalse(is_app_window("NovaTally", "CabinetWClass"))  # Explorer-Ordner namens NovaTally
        self.assertFalse(is_app_window("NovaTallyX", "Chrome_WidgetWin_1"))
        self.assertFalse(is_app_window("GitHub - NovaTally", "Chrome_WidgetWin_1"))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_fenstersuche_laeuft_unter_windows(self):
        from novatally.app import focus_existing_window
        self.assertIn(focus_existing_window(), (True, False))  # darf nie abstürzen


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

    def test_bibliothek_ausschliessen(self):
        entry = LibraryEntry(SEP + os.path.join("x", "wallpaper_engine"), "folder:wallpaper", "Wallpaper App", "custom", None)
        self.ctx._library_cache = [entry]
        try:
            _, st, _ = self.req("/api/settings")
            self.assertEqual(st["libraries"][0]["games"], [{"name": "Wallpaper App", "key": "folder:wallpaper", "ignored": False}])
            status, data, _ = self.req("/api/library/ignore", {"key": "folder:wallpaper", "ignored": True})
            self.assertEqual(status, 200)
            self.assertTrue(self.db.game(data["id"])["ignored"])
            _, st, _ = self.req("/api/settings")
            self.assertTrue(st["libraries"][0]["games"][0]["ignored"])
            self.assertIn("Wallpaper App", [g["name"] for g in st["ignored"]])
            self.assertEqual(self.req("/api/library/ignore", {"key": "folder:wallpaper", "ignored": False})[0], 200)
            self.assertFalse(self.db.game(data["id"])["ignored"])
            self.assertEqual(self.req("/api/library/ignore", {"key": "gibt:esnicht"})[0], 404)
        finally:
            self.ctx._library_cache = None

    def test_update_pruefen_und_installieren(self):
        from novatally import updater
        calls = []
        orig_check, orig_install = updater.check, updater.install
        updater.check = lambda: {"mode": "exe", "current": "1.0.1", "latest": "9.9.9", "newer": True,
                                 "notes": "- Neu", "url": "https://github.com/x", "installable": True,
                                 "exe_url": "geheim-intern"}
        updater.install = lambda info: ["neue.exe", "--updated"]
        self.ctx.request_restart = calls.append
        try:
            self.ctx.update_info = None
            self.assertEqual(self.req("/api/update/install", {})[0], 400)  # erst prüfen
            status, data, _ = self.req("/api/update/check")
            self.assertEqual(status, 200)
            self.assertEqual(data["latest"], "9.9.9")
            self.assertNotIn("exe_url", data)  # interne Details bleiben im Server
            _, st, _ = self.req("/api/status")
            self.assertEqual(st["update"], {"latest": "9.9.9"})
            status, data, _ = self.req("/api/update/install", {})
            self.assertEqual((status, data["restarting"]), (200, True))
            time.sleep(1.5)
            self.assertEqual(calls, [["neue.exe", "--updated"]])
            # automatische Suche ein-/ausschalten
            self.assertTrue(self.req("/api/settings", {"update_auto": True})[1]["update_auto"])
            self.assertFalse(self.req("/api/settings", {"update_auto": False})[1]["update_auto"])
        finally:
            updater.check, updater.install = orig_check, orig_install
            self.ctx.request_restart = None
            self.ctx.update_info = None

    def test_spielprogramm_waehlen(self):
        gid = self.db.games()[0]["id"]
        self.db.record_exe(self.db.game(gid)["key"], "game.exe", "Game.exe", 1000)
        _, d, _ = self.req(f"/api/game/{gid}")
        self.assertIsNone(d["only_exe"])
        self.assertEqual(d["exes"], [{"exe": "game.exe", "display": "Game.exe", "last_seen": 1000}])
        status, r, _ = self.req(f"/api/game/{gid}/only_exe", {"exe": "Game.exe"})
        self.assertEqual((status, r["only_exe"]), (200, "game.exe"))
        self.assertEqual(self.req(f"/api/game/{gid}")[1]["only_exe"], "game.exe")
        self.assertEqual(self.req(f"/api/game/{gid}/only_exe", {"exe": "C:\\x\\game.exe"})[0], 400)
        self.assertEqual(self.req(f"/api/game/{gid}/only_exe", {"exe": None})[1]["only_exe"], None)
        self.assertEqual(self.req("/api/game/999999/only_exe", {"exe": "x.exe"})[0], 404)

    def test_sauber_beenden_per_api(self):
        calls = []
        self.ctx.request_quit = lambda: calls.append("quit")
        try:
            self.assertEqual(self.req("/api/quit", {})[0], 200)
            time.sleep(0.6)
            self.assertEqual(calls, ["quit"])
        finally:
            self.ctx.request_quit = None
        self.assertEqual(self.req("/api/quit", {})[0], 409)

    def test_update_per_installer(self):
        from novatally import updater
        calls = []
        orig_install = updater.install
        updater.install = lambda info: None  # Installer übernimmt
        self.ctx.update_info = {"newer": True, "installable": True, "latest": "9.9.9"}
        self.ctx.request_quit = lambda: calls.append("quit")
        try:
            status, data, _ = self.req("/api/update/install", {})
            self.assertEqual((status, data["installer"], data["restarting"]), (200, True, False))
            time.sleep(1.8)
            self.assertEqual(calls, ["quit"])
        finally:
            updater.install = orig_install
            self.ctx.update_info = None
            self.ctx.request_quit = None

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
