"""SQLite-Datenbank: Schema und alle Lese-/Schreibfunktionen.

Eine einzige Verbindung (check_same_thread=False), abgesichert durch ein Lock,
damit Tracker-Thread und Server-Threads sie gemeinsam nutzen können.
"""

import json
import os
import sqlite3
import threading
import time

from .config import MIN_SESSION_SECONDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id      INTEGER PRIMARY KEY,
    key     TEXT UNIQUE NOT NULL,
    name    TEXT NOT NULL,
    source  TEXT NOT NULL DEFAULT '',
    appid   TEXT,
    path    TEXT,
    ignored INTEGER NOT NULL DEFAULT 0,
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id      INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    start   INTEGER NOT NULL,
    end     INTEGER NOT NULL,
    open    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start);
CREATE INDEX IF NOT EXISTS idx_sessions_game ON sessions(game_id);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS game_exes (
    game_id   INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    exe       TEXT NOT NULL,          -- Dateiname in Kleinbuchstaben, z. B. 'league of legends.exe'
    display   TEXT,                   -- wie Windows ihn meldet, z. B. 'League of Legends.exe'
    last_seen INTEGER,
    PRIMARY KEY (game_id, exe)
);
"""

# Spiele, bei denen von Haus aus nur ein bestimmtes Programm zählt (Name in Kleinbuchstaben -> EXE).
# League of Legends: Der Client (LeagueClient*.exe) liegt im Spielordner – gezählt wird nur das Match.
DEFAULT_ONLY_EXE = {
    "league of legends": "league of legends.exe",
}


def norm_path(path: str) -> str:
    """Pfad vergleichbar machen (unter Windows: Kleinschreibung, Backslashes)."""
    return os.path.normcase(os.path.normpath(path))


class Database:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self._migrate()

    def _migrate(self):
        """Ältere Datenbanken um neue Spalten ergänzen."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(games)").fetchall()}
        if "only_exe" not in cols:
            # Nur dieses Programm (Dateiname, klein) zählt als Spielzeit – NULL: alle Programme im Spielordner
            self.conn.execute("ALTER TABLE games ADD COLUMN only_exe TEXT")

    # ------------------------------------------------------------------ intern
    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql, args=()):
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def _run(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args)

    def close(self):
        with self.lock:
            self.conn.close()

    # --------------------------------------------------------------- settings
    def get_setting(self, key, default=None):
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        if row is None or row["value"] is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set_setting(self, key, value):
        self._run(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    # ------------------------------------------------------------------ games
    def get_or_create_game(self, key, name, source, appid=None, path=None):
        with self.lock:
            row = self._one("SELECT * FROM games WHERE key=?", (key,))
            if row:
                if appid and not row["appid"]:
                    self._run("UPDATE games SET appid=? WHERE id=?", (appid, row["id"]))
                    row["appid"] = appid
                return row
            cur = self._run(
                "INSERT INTO games(key, name, source, appid, path, created, only_exe) VALUES(?,?,?,?,?,?,?)",
                (key, name, source, appid, path, int(time.time()), DEFAULT_ONLY_EXE.get((name or "").lower())),
            )
            return self.game(cur.lastrowid)

    # ------------------------------------------------- welches Programm zählt
    def only_exe_map(self):
        """{key: exe} für Spiele, bei denen nur ein bestimmtes Programm zählt."""
        return {r["key"]: r["only_exe"] for r in self._all("SELECT key, only_exe FROM games WHERE only_exe IS NOT NULL")}

    def set_only_exe(self, game_id, exe):
        self._run("UPDATE games SET only_exe=? WHERE id=?", ((exe or "").lower() or None, game_id))

    def apply_only_exe_defaults(self):
        """Vorgaben (z. B. League of Legends) einmalig auf bestehende Spiele anwenden – eigene Wahl bleibt."""
        done = set(self.get_setting("only_exe_defaults", []) or [])
        changed = []
        for g in self._all("SELECT id, name, only_exe FROM games"):
            exe = DEFAULT_ONLY_EXE.get((g["name"] or "").lower())
            if exe and g["id"] not in done:
                if g["only_exe"] is None:
                    self.set_only_exe(g["id"], exe)
                    changed.append(g["name"])
                done.add(g["id"])
        self.set_setting("only_exe_defaults", sorted(done))
        return changed

    def record_exe(self, key, exe, display, now):
        """Merkt sich, welches Programm bei einem Spiel lief. False, wenn es das Spiel noch nicht gibt."""
        with self.lock:
            row = self._one("SELECT id FROM games WHERE key=?", (key,))
            if not row:
                return False
            self._run(
                "INSERT INTO game_exes(game_id, exe, display, last_seen) VALUES(?,?,?,?) "
                "ON CONFLICT(game_id, exe) DO UPDATE SET display=excluded.display, last_seen=excluded.last_seen",
                (row["id"], exe.lower(), display, int(now)),
            )
            return True

    def game_exes(self, game_id):
        return self._all("SELECT exe, display, last_seen FROM game_exes WHERE game_id=? ORDER BY last_seen DESC",
                         (game_id,))

    def game(self, game_id):
        return self._one("SELECT * FROM games WHERE id=?", (game_id,))

    def game_by_key(self, key):
        return self._one("SELECT * FROM games WHERE key=?", (key,))

    def games(self, include_ignored=False):
        sql = "SELECT * FROM games"
        if not include_ignored:
            sql += " WHERE ignored=0"
        return self._all(sql + " ORDER BY name COLLATE NOCASE")

    def ignored_games(self):
        return self._all("SELECT * FROM games WHERE ignored=1 ORDER BY name COLLATE NOCASE")

    def ignored_keys(self):
        return {r["key"] for r in self._all("SELECT key FROM games WHERE ignored=1")}

    def rename_game(self, game_id, name):
        self._run("UPDATE games SET name=? WHERE id=?", (name, game_id))

    def set_ignored(self, game_id, ignored):
        self._run("UPDATE games SET ignored=? WHERE id=?", (1 if ignored else 0, game_id))

    def auto_exclude(self, keys):
        """Bekannte Nicht-Spiele einmalig ausschließen (der Nutzer kann sie danach wieder einschließen)."""
        done = set(self.get_setting("auto_excluded", []) or [])
        changed = []
        for key in keys:
            if key in done:
                continue
            row = self.game_by_key(key)
            if row:
                if not row["ignored"]:
                    self.set_ignored(row["id"], True)
                    changed.append(row["name"])
                done.add(key)
        self.set_setting("auto_excluded", sorted(done))
        return changed

    def add_manual_game(self, exe, name):
        key = "exe:" + norm_path(exe)
        with self.lock:
            row = self.game_by_key(key)
            if row:
                self._run("UPDATE games SET name=?, ignored=0 WHERE id=?", (name, row["id"]))
                return self.game(row["id"])
            return self.get_or_create_game(key, name, "manual", None, exe)

    def manual_games(self):
        return self._all("SELECT * FROM games WHERE source='manual'")

    # --------------------------------------------------------------- sessions
    def start_session(self, game_id, now):
        cur = self._run(
            "INSERT INTO sessions(game_id, start, end, open) VALUES(?,?,?,1)",
            (game_id, int(now), int(now)),
        )
        return cur.lastrowid

    def touch_sessions(self, session_ids, now):
        """Heartbeat: Ende der offenen Sitzungen auf jetzt setzen."""
        if not session_ids:
            return
        with self.lock:
            self.conn.executemany(
                "UPDATE sessions SET end=? WHERE id=? AND open=1",
                [(int(now), sid) for sid in session_ids],
            )

    def end_session(self, session_id, end):
        """Sitzung schließen; zu kurze Sitzungen werden gelöscht. Gibt True zurück, wenn sie bleibt."""
        with self.lock:
            row = self._one("SELECT start FROM sessions WHERE id=?", (session_id,))
            if not row:
                return False
            end = max(int(end), row["start"])
            if end - row["start"] < MIN_SESSION_SECONDS:
                self._run("DELETE FROM sessions WHERE id=?", (session_id,))
                return False
            self._run("UPDATE sessions SET end=?, open=0 WHERE id=?", (end, session_id))
            return True

    def close_stale_sessions(self):
        """Beim Programmstart: offene Sitzungen beim letzten Heartbeat beenden."""
        with self.lock:
            self._run("DELETE FROM sessions WHERE open=1 AND end - start < ?", (MIN_SESSION_SECONDS,))
            cur = self._run("UPDATE sessions SET open=0 WHERE open=1")
            return cur.rowcount

    def delete_open_sessions(self):
        self._run("DELETE FROM sessions WHERE open=1")

    def delete_session(self, session_id):
        cur = self._run("DELETE FROM sessions WHERE id=? AND open=0", (session_id,))
        return cur.rowcount > 0

    def insert_sessions(self, rows):
        """Viele Sitzungen auf einmal (Demo-Daten): [(game_id, start, end), ...]."""
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(
                    "INSERT INTO sessions(game_id, start, end, open) VALUES(?,?,?,0)", rows
                )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def session_count(self):
        return self._one("SELECT COUNT(*) AS n FROM sessions")["n"]

    def all_sessions(self, include_ignored=False):
        """Alle Sitzungen mit Spielinfos, älteste zuerst."""
        sql = (
            "SELECT s.id, s.game_id, s.start, s.end, s.open, g.name, g.appid, g.source, g.ignored "
            "FROM sessions s JOIN games g ON g.id = s.game_id"
        )
        if not include_ignored:
            sql += " WHERE g.ignored=0"
        return self._all(sql + " ORDER BY s.start")

    def recent_sessions(self, limit=300):
        return self._all(
            "SELECT s.id, s.game_id, s.start, s.end, s.open, g.name, g.appid, g.source "
            "FROM sessions s JOIN games g ON g.id = s.game_id WHERE g.ignored=0 "
            "ORDER BY s.start DESC LIMIT ?",
            (int(limit),),
        )

    def game_sessions(self, game_id):
        return self._all(
            "SELECT id, game_id, start, end, open FROM sessions WHERE game_id=? ORDER BY start DESC",
            (game_id,),
        )

    def open_sessions(self):
        return self._all(
            "SELECT s.id, s.game_id, s.start, s.end, g.name, g.appid, g.source "
            "FROM sessions s JOIN games g ON g.id = s.game_id "
            "WHERE s.open=1 AND g.ignored=0 ORDER BY s.start"
        )

    def last_closed_session(self):
        return self._one(
            "SELECT s.id, s.game_id, s.start, s.end, g.name, g.appid, g.source "
            "FROM sessions s JOIN games g ON g.id = s.game_id "
            "WHERE s.open=0 AND g.ignored=0 ORDER BY s.end DESC LIMIT 1"
        )
