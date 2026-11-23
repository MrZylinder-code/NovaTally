"""Auswertungen für die API. Zeiten sind Unix-Sekunden, ausgewertet in lokaler Zeit.

Sitzungen über Mitternacht (bzw. über Stundengrenzen) werden anteilig aufgeteilt.
"""

import time
from collections import defaultdict
from datetime import date, datetime, timedelta

TOP_SLOTS = 7  # so viele Spiele bekommen eine feste Farbe, der Rest ist "Andere"
OTHER_ID = 0
MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def midnight_ts(d: date) -> float:
    return datetime(d.year, d.month, d.day).timestamp()


def split_days(start, end):
    """(Datum, Sekunden) je lokalem Kalendertag."""
    if end <= start:
        return
    cur = start
    while cur < end:
        d = datetime.fromtimestamp(cur).date()
        nxt = midnight_ts(d + timedelta(days=1))
        stop = min(end, nxt)
        yield d, stop - cur
        cur = stop


def split_hours(start, end):
    """(Stunde 0–23, Sekunden) je lokaler Uhrzeit-Stunde."""
    cur = start
    while cur < end:
        dt = datetime.fromtimestamp(cur)
        nxt = (dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()
        stop = min(end, nxt)
        yield dt.hour, stop - cur
        cur = stop


def color_slots(sessions):
    """Feste Farbe je Spiel: die 7 Spiele mit der höchsten Gesamtspielzeit -> Slot 1–7."""
    totals = defaultdict(float)
    for s in sessions:
        totals[s["game_id"]] += s["end"] - s["start"]
    ranked = sorted(totals, key=lambda g: -totals[g])[:TOP_SLOTS]
    return {gid: i + 1 for i, gid in enumerate(ranked)}


def _now(now):
    return time.time() if now is None else now


def _session_end(s, now):
    return max(s["end"], now) if s.get("open") else s["end"]


def _day_map(sessions, now):
    """{(datum, game_id): sekunden}"""
    out = defaultdict(float)
    for s in sessions:
        for d, sec in split_days(s["start"], _session_end(s, now)):
            out[(d, s["game_id"])] += sec
    return out


def _streaks(days, today):
    if not days:
        return 0, 0
    cur = 0
    d = today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    longest, run, prev = 0, 0, None
    for d in sorted(days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return cur, longest


def _game_info(g, slots):
    """Spielinfos aus einer Spielzeile oder einer Sitzungszeile (mit game_id)."""
    gid = g["game_id"] if "game_id" in g else g["id"]
    return {
        "id": gid,
        "name": g["name"],
        "appid": g.get("appid"),
        "source": g.get("source"),
        "slot": slots.get(gid),
    }


def _buckets(range_key, today, first_day):
    """Liste von (startdatum, enddatum_exkl, label, tooltip-label)."""
    out = []
    if range_key in (7, 30, 90):
        for i in range(range_key - 1, -1, -1):
            d = today - timedelta(days=i)
            out.append((d, d + timedelta(days=1), d.isoformat(), "day"))
        return out, "day"
    if range_key == 365:
        monday = today - timedelta(days=today.weekday())
        for i in range(52, -1, -1):
            d = monday - timedelta(weeks=i)
            out.append((d, d + timedelta(days=7), d.isoformat(), "week"))
        return out, "week"
    # Gesamt: Monate seit dem ersten Spieltag
    first = first_day or today
    y, m = first.year, first.month
    if (today.year - y) * 12 + today.month - m < 11:  # mindestens 12 Monate zeigen
        total = today.year * 12 + today.month - 1 - 11
        y, m = total // 12, total % 12 + 1
    while (y, m) <= (today.year, today.month):
        start = date(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((start, date(ny, nm, 1), start.isoformat(), "month"))
        y, m = ny, nm
    return out, "month"


def overview(db, range_key="30", now=None):
    now = _now(now)
    try:
        range_key = int(range_key)
    except (TypeError, ValueError):
        range_key = "all"
    if range_key not in (7, 30, 90, 365):
        range_key = "all"

    sessions = db.all_sessions()
    games = {g["id"]: g for g in db.games()}
    slots = color_slots(sessions)
    days = _day_map(sessions, now)
    today = datetime.fromtimestamp(now).date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    per_day = defaultdict(float)
    for (d, gid), sec in days.items():
        per_day[d] += sec
    played_days = {d for d, sec in per_day.items() if sec >= 60}
    first_day = min(per_day) if per_day else None

    kpis = {
        "today": sum(sec for d, sec in per_day.items() if d == today),
        "week": sum(sec for d, sec in per_day.items() if d >= week_start),
        "month": sum(sec for d, sec in per_day.items() if d >= month_start),
        "total": sum(per_day.values()),
    }
    cur_streak, best_streak = _streaks(played_days, today)
    longest = None
    for s in sessions:
        dur = _session_end(s, now) - s["start"]
        if longest is None or dur > longest["seconds"]:
            longest = {"seconds": dur, "start": s["start"], "game": _game_info(s, slots)}

    # ---- Verlauf
    buckets, unit = _buckets(range_key, today, first_day)
    range_start = buckets[0][0]
    bucket_index = {}
    for i, (b0, b1, _, _) in enumerate(buckets):
        d = b0
        while d < b1:
            bucket_index[d] = i
            d += timedelta(days=1)
    values = [defaultdict(float) for _ in buckets]
    range_games = defaultdict(float)
    for (d, gid), sec in days.items():
        i = bucket_index.get(d)
        if i is None:
            continue
        series = gid if gid in slots else OTHER_ID
        values[i][series] += sec
        range_games[gid] += sec
    present = {sid for v in values for sid, sec in v.items() if sec > 0}
    series = [
        {"id": gid, "name": games[gid]["name"], "slot": slot}
        for gid, slot in sorted(slots.items(), key=lambda kv: kv[1])
        if gid in present and gid in games
    ]
    if OTHER_ID in present:
        series.append({"id": OTHER_ID, "name": "Andere", "slot": None})
    history = {
        "unit": unit,
        "series": series,
        "buckets": [
            {"start": b[2], "values": [round(values[i].get(s["id"], 0)) for s in series]}
            for i, b in enumerate(buckets)
        ],
    }

    top = sorted(range_games.items(), key=lambda kv: -kv[1])
    top_list = []
    for gid, sec in top[:8]:
        if gid in games and sec > 0:
            info = _game_info(games[gid], slots)
            info["seconds"] = round(sec)
            top_list.append(info)
    range_total = sum(range_games.values())

    # ---- Tageszeit im Zeitraum
    hours = [0.0] * 24
    range_start_ts = midnight_ts(range_start)
    for s in sessions:
        end = _session_end(s, now)
        if end <= range_start_ts:
            continue
        for h, sec in split_hours(max(s["start"], range_start_ts), end):
            hours[h] += sec

    # ---- Heatmap: 53 Wochen, beginnend an einem Montag
    heat_start = today - timedelta(days=364)
    heat_start -= timedelta(days=heat_start.weekday())
    heat = []
    d = heat_start
    while d <= today:
        heat.append(round(per_day.get(d, 0)))
        d += timedelta(days=1)

    range_days = (today - range_start).days + 1
    active_days = sum(1 for d in played_days if range_start <= d <= today)
    return {
        "range": range_key,
        "kpis": {k: round(v) for k, v in kpis.items()},
        "games": len({s["game_id"] for s in sessions}),
        "sessions": len(sessions),
        "streak": {"current": cur_streak, "longest": best_streak},
        "longest_session": longest,
        "range_total": round(range_total),
        "range_days": range_days,
        "active_days": active_days,
        "history": history,
        "top": top_list,
        "hours": [round(h) for h in hours],
        "heatmap": {"start": heat_start.isoformat(), "days": heat},
        "today": today.isoformat(),
    }


def games_list(db, now=None):
    now = _now(now)
    sessions = db.all_sessions()
    slots = color_slots(sessions)
    agg = {}
    for s in sessions:
        a = agg.setdefault(s["game_id"], {"seconds": 0, "sessions": 0, "last": 0, "first": s["start"]})
        end = _session_end(s, now)
        a["seconds"] += end - s["start"]
        a["sessions"] += 1
        a["last"] = max(a["last"], end)
        a["first"] = min(a["first"], s["start"])
    out = []
    for g in db.games():
        info = _game_info(g, slots)
        a = agg.get(g["id"], {"seconds": 0, "sessions": 0, "last": None, "first": None})
        info.update(seconds=round(a["seconds"]), sessions=a["sessions"], last=a["last"], first=a["first"])
        out.append(info)
    return out


def game_detail(db, game_id, now=None):
    now = _now(now)
    g = db.game(game_id)
    if not g:
        return None
    all_sessions = db.all_sessions()
    slots = color_slots(all_sessions)
    sessions = db.game_sessions(game_id)
    durations = [_session_end(s, now) - s["start"] for s in sessions]
    total = sum(durations)
    today = datetime.fromtimestamp(now).date()
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    months.reverse()
    per_month = defaultdict(float)
    for s in sessions:
        for d, sec in split_days(s["start"], _session_end(s, now)):
            per_month[(d.year, d.month)] += sec
    info = _game_info(g, slots)
    info.update(
        key=g["key"],
        path=g["path"],
        ignored=bool(g["ignored"]),
        only_exe=g.get("only_exe"),
        exes=[{"exe": e["exe"], "display": e["display"] or e["exe"], "last_seen": e["last_seen"]}
              for e in db.game_exes(game_id)],
        seconds=round(total),
        session_count=len(sessions),
        average=round(total / len(sessions)) if sessions else 0,
        longest=round(max(durations)) if durations else 0,
        first=min((s["start"] for s in sessions), default=None),
        last=max((_session_end(s, now) for s in sessions), default=None),
        months=[{"start": date(y, m, 1).isoformat(), "seconds": round(per_month.get((y, m), 0))} for y, m in months],
        sessions_list=[
            {"id": s["id"], "start": s["start"], "end": _session_end(s, now), "open": bool(s["open"])}
            for s in sessions
        ],
    )
    return info


def sessions_list(db, limit=300, now=None):
    now = _now(now)
    slots = color_slots(db.all_sessions())
    out = []
    for s in db.recent_sessions(limit):
        out.append({
            "id": s["id"], "start": s["start"], "end": _session_end(s, now), "open": bool(s["open"]),
            "game": _game_info(s, slots),
        })
    return out


def status_running(db, now=None):
    now = _now(now)
    slots = color_slots(db.all_sessions())
    running = [
        dict(_game_info(s, slots), start=s["start"], session_id=s["id"]) for s in db.open_sessions()
    ]
    last = db.last_closed_session()
    last_info = None
    if last:
        last_info = dict(_game_info(last, slots), start=last["start"], end=last["end"])
    return running, last_info
