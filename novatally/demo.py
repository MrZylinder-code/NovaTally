"""Realistische Demo-Daten: ≈15 Spiele über 14 Monate (mit Steam-AppIDs für Cover)."""

import random
import time
from datetime import datetime, timedelta

# (key, name, source, appid, Beginn vor x Tagen, Ende vor x Tagen, Spielwahrscheinlichkeit, Ø Minuten)
GAMES = [
    ("steam:1086940", "Baldur's Gate 3", "steam", "1086940", 420, 250, 0.55, 150),
    ("steam:1245620", "ELDEN RING", "steam", "1245620", 330, 180, 0.45, 120),
    ("steam:730", "Counter-Strike 2", "steam", "730", 425, 0, 0.30, 55),
    ("steam:1145350", "Hades II", "steam", "1145350", 120, 0, 0.40, 50),
    ("steam:1091500", "Cyberpunk 2077", "steam", "1091500", 200, 110, 0.50, 130),
    ("steam:413150", "Stardew Valley", "steam", "413150", 425, 0, 0.10, 70),
    ("steam:427520", "Factorio", "steam", "427520", 95, 20, 0.45, 160),
    ("steam:367520", "Hollow Knight", "steam", "367520", 380, 330, 0.40, 75),
    ("steam:1174180", "Red Dead Redemption 2", "steam", "1174180", 260, 200, 0.35, 110),
    ("steam:548430", "Deep Rock Galactic", "steam", "548430", 425, 0, 0.12, 60),
    ("steam:292030", "The Witcher 3: Wild Hunt", "steam", "292030", 425, 380, 0.40, 100),
    ("steam:526870", "Satisfactory", "steam", "526870", 60, 0, 0.30, 140),
    ("folder:demo-league", "League of Legends", "riot", None, 425, 0, 0.12, 40),
    ("epic:fortnite", "Fortnite", "epic", None, 300, 150, 0.08, 35),
    ("folder:demo-forza", "Forza Horizon 5", "xbox", None, 150, 40, 0.10, 45),
]

RUNNING_GAME = "steam:1145350"  # läuft in der Demo gerade ("Jetzt im Spiel")
RUNNING_MINUTES = 47


def fill(db, now=None, seed=42):
    """Demo-Daten einfügen, falls die Datenbank leer ist."""
    if db.session_count() > 0:
        return False
    now = time.time() if now is None else now
    rng = random.Random(seed)
    ids = {}
    for key, name, source, appid, *_ in GAMES:
        ids[key] = db.get_or_create_game(key, name, source, appid, None)["id"]

    today = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    latest_allowed = now - (RUNNING_MINUTES + 20) * 60  # vor der "laufenden" Demo-Sitzung enden
    rows = []
    for day_offset in range(425, -1, -1):
        day = today - timedelta(days=day_offset)
        weekend = day.weekday() >= 4  # Fr–So
        # Urlaubswochen/Pausen ohne Spielen
        if rng.random() < 0.12:
            continue
        busy_until = None
        for key, name, source, appid, begin, end, prob, avg in GAMES:
            if not (end <= day_offset <= begin):
                continue
            p = prob * (1.35 if weekend else 0.85)
            if rng.random() > p:
                continue
            minutes = min(330, max(5, rng.gauss(avg * (1.3 if weekend else 1.0), avg * 0.45)))
            if weekend and rng.random() < 0.5:
                hour = rng.choice([11, 13, 14, 15, 16, 17])
            else:
                hour = rng.choice([16, 17, 18, 18, 19, 19, 19, 20, 20, 21])
            start = day + timedelta(hours=hour, minutes=rng.randint(0, 59))
            if busy_until and start < busy_until:
                start = busy_until + timedelta(minutes=rng.randint(10, 40))
                if start >= day + timedelta(hours=23):
                    continue  # zu spät für ein weiteres Spiel
            stop = start + timedelta(minutes=minutes)
            s, e = int(start.timestamp()), int(stop.timestamp())
            if e > latest_allowed:
                continue
            busy_until = stop
            rows.append((ids[key], s, e))
    # Eine lange Nacht über Mitternacht und eine kurze Sitzung heute früh
    nacht = today - timedelta(days=9) + timedelta(hours=22, minutes=40)
    rows.append((ids["steam:427520"], int(nacht.timestamp()), int((nacht + timedelta(hours=4, minutes=5)).timestamp())))
    frueh = today + timedelta(hours=7, minutes=10)
    if frueh.timestamp() + 35 * 60 < latest_allowed:
        rows.append((ids["steam:730"], int(frueh.timestamp()), int(frueh.timestamp()) + 35 * 60))
    db.insert_sessions(rows)
    # Programme, die NovaTally bei League of Legends gesehen hat (für „Was zählt als Spielzeit?“)
    for exe, ago in (("LeagueClient.exe", 2), ("LeagueClientUx.exe", 2), ("League of Legends.exe", 3)):
        db.record_exe("folder:demo-league", exe.lower(), exe, now - ago * 86400)
    return True


def start_running(db, now=None):
    """Eine 'laufende' Sitzung für die Ansicht „Jetzt im Spiel“ anlegen."""
    now = time.time() if now is None else now
    db.delete_open_sessions()
    game = db.game_by_key(RUNNING_GAME)
    if game:
        sid = db.start_session(game["id"], now - RUNNING_MINUTES * 60)
        db.touch_sessions([sid], now)
