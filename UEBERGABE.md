# Übergabe: Spielzeit – Windows-Spielzeit-Tracker fertig entwickeln

Du übernimmst ein angefangenes Projekt in `/home/dev/projects/Spielzeit`.
**Lies zuerst `GOAL.md`** – das ist die verbindliche Zielbeschreibung (Muss-Anforderungen,
Nicht-Ziele, Abnahmekriterien). Diese Übergabe ergänzt die dort getroffenen Entscheidungen
um den Bauplan. Sprache der App und der Antworten an den Nutzer: **Deutsch**.

## Ziel dieser Session
Die komplette App bauen, mit Demo-Daten testen, einen Screenshot der Oberfläche prüfen
und dem Nutzer am Ende erklären, wie er auf Windows die `Spielzeit.exe` baut und startet.

## Was schon existiert
- `GOAL.md` – Zielbeschreibung (fertig)
- `spielzeit/__init__.py` – `__version__ = "1.0.0"`, `APP_NAME = "Spielzeit"`
- `spielzeit/config.py` – Konstanten (`POLL_SECONDS=5`, `HEARTBEAT_SECONDS=30`,
  `MIN_SESSION_SECONDS=60`, `LIBRARY_RESCAN_SECONDS=600`, `PORT=47815`),
  `data_dir()` (`%APPDATA%\Spielzeit`, überschreibbar mit Env `SPIELZEIT_DATA`), `db_path()`,
  `resource_dir()` (funktioniert auch in PyInstaller-EXE), `IS_WINDOWS`

## Git
- Der Ordner ist ein Git-Repo mit `origin` = `git@github.com:MrZylinder-code/Spielzeit.git` (privat),
  Branch `main`. `gh` ist angemeldet.
- In sinnvollen Schritten committen (deutsche Commit-Nachrichten). Am Ende nach erfolgreichen
  Tests nach `origin/main` pushen.

## Wichtige Rahmenbedingungen der Entwicklungsumgebung
- Entwickelt wird auf **Linux**, Ziel ist **Windows**. Python 3.13 ist da, aber **kein pip,
  kein node**. `psutil`, `pystray`, `Pillow` lassen sich hier nicht installieren.
- Darum: Kernlogik (DB, Statistik, Erkennung, Server) **nur mit der Standardbibliothek**;
  `psutil`, `pystray`, `PIL`, `winreg` nur dort importieren, wo sie gebraucht werden, und
  so kapseln, dass alles andere auf Linux testbar bleibt.
- `/usr/bin/chromium` ist vorhanden → Oberfläche headless rendern und Screenshots prüfen
  (`chromium --headless --screenshot=… --window-size=1440,1000 http://127.0.0.1:…`).

## Architektur-Entscheidungen (bereits getroffen – nicht neu diskutieren)
- **Kein pywebview.** Eingebauter Mini-Server (`http.server`, `ThreadingHTTPServer`) nur auf
  `127.0.0.1:47815`, liefert Web-UI + JSON-API. Das Fenster öffnet sich über
  `msedge --app=http://127.0.0.1:47815` (Fenster ohne Adressleiste), Fallback: `webbrowser.open`.
  Fenster schließen = nur Ansicht zu; das Tracking läuft im Tray weiter.
- **Eine Instanz**: Der belegte Port dient als Sperre. Ist er belegt und `GET /api/ping`
  antwortet als Spielzeit → nur Fenster öffnen und beenden.
- **Sicherheit des lokalen Servers**: Host-Header muss `127.0.0.1:47815` bzw. `localhost:47815`
  sein (gegen DNS-Rebinding); alle `/api/*`-Aufrufe brauchen den Header `X-Spielzeit: 1`
  (fremde Webseiten scheitern am CORS-Preflight). Keine CORS-Header senden.
- **Threads**: Tray (`pystray`) im Hauptthread, Tracker und Server als Daemon-Threads.
  SQLite: eine Verbindung mit `check_same_thread=False` + `threading.Lock`, WAL-Modus.
- Zeiten als Unix-Sekunden (int) speichern, Auswertung in lokaler Zeit; Sitzungen über
  Mitternacht beim Auswerten auf die Tage aufteilen.

## Dateistruktur (anzulegen)
```
Spielzeit/
  GOAL.md, UEBERGABE.md, README.md (deutsch: Installation, Bauen, Bedienung, FAQ)
  requirements.txt        psutil, pystray, Pillow  (+ pyinstaller nur im Build-Skript)
  Spielzeit.pyw           Einstieg (ruft spielzeit.app.main)
  build.bat               venv anlegen, requirements + pyinstaller installieren,
                          `pyinstaller --noconsole --onefile --name Spielzeit --icon spielzeit\web\icon.ico
                          --add-data "spielzeit\web;spielzeit\web" Spielzeit.pyw`
  start.bat               ohne Build direkt starten (pythonw Spielzeit.pyw)
  spielzeit/
    app.py        main(): Einzelinstanz-Prüfung, DB öffnen, offene Sitzungen schließen,
                  Tracker + Server starten, Tray starten, Fenster beim ersten Start öffnen.
                  Optionen: --demo (DB mit Demo-Daten in eigenem Datenordner füllen),
                  --no-tray / --headless (nur Server+Tracker, zum Testen auf Linux)
    db.py         Schema + alle Lese-/Schreibfunktionen
    library.py    installierte Spiele erkennen (siehe unten)
    tracker.py    Prozess-Abfrage + Sitzungslogik
    stats.py      Auswertungen für die API
    server.py     HTTP-Server, API, statische Dateien, CSV-Export
    tray.py       Tray-Symbol (Icon mit Pillow zeichnen), Menü
    autostart.py  HKCU\Software\Microsoft\Windows\CurrentVersion\Run (winreg);
                  EXE → sys.executable; sonst pythonw.exe + Pfad zu Spielzeit.pyw
    demo.py       realistische Demo-Daten (≈15 Spiele, 14 Monate, Steam-AppIDs für Cover)
    web/index.html, web/app.css, web/app.js, web/icon.ico (mit Pillow erzeugen, wenn möglich;
                  sonst build.bat erzeugt es auf Windows)
```

## Datenbank
```
games(id INTEGER PK, key TEXT UNIQUE, name TEXT, source TEXT, appid TEXT,
      path TEXT, ignored INT DEFAULT 0, created INT)
sessions(id INTEGER PK, game_id INT, start INT, end INT, open INT DEFAULT 0)   -- Index auf start, game_id
settings(key TEXT PK, value TEXT)   -- JSON-Werte: paused, extra_folders, theme, first_run
```
- `key`: `steam:<appid>`, `epic:<ordner>`, `gog:<id>`, `folder:<normierter pfad>`, `exe:<normierter exe-pfad>`.
- Ein Spiel bekommt erst eine Zeile, wenn es zum ersten Mal gespielt wird (Bibliothek ≠ Spieleliste).
- Manuell hinzugefügte Spiele: Zeile mit `key = exe:<pfad>`, `source='manual'`, wird vom Tracker als Regel geladen.

## Tracker-Logik (`tracker.py`)
- Alle 5 s: `psutil.process_iter(["pid","exe","name"])` (AccessDenied/None tolerieren),
  Zuordnung pid→Spiel cachen. Zuordnung: erst exakte manuelle EXE-Regeln, dann
  **längster passender Ordner-Präfix** aus der Bibliothek (`os.path.normcase`, mit `\` am Ende).
- Mehrere Prozesse eines Spiels = eine Sitzung (gruppiert nach `key`).
- Neu erkannt → Spiel anlegen/holen; `ignored` → überspringen; Sitzung mit `open=1`, `start=end=now`.
- Verschwunden → `end=now`, `open=0`; Dauer < `MIN_SESSION_SECONDS` → Sitzung löschen.
- Alle 30 s Heartbeat: `end=now` für offene Sitzungen (Absturzsicherheit).
- Programmstart: alle `open=1` schließen (Ende = letzter Heartbeat), zu kurze löschen.
- **Standby**: Lücke seit letztem Durchlauf > 3×Intervall + 60 s → laufende Sitzungen beim
  letzten Durchlauf beenden, danach normal neu beginnen.
- Pause-Einstellung respektieren (laufende Sitzungen beim Pausieren schließen).
- Prozessquelle injizierbar machen (für Tests auf Linux mit Fake-Prozessen).
- Ignorierte EXE-Namen (Teilstrings, klein): `unins`, `setup`, `install`, `vc_redist`, `vcredist`,
  `dxsetup`, `dotnet`, `crashhandler`, `crashreport`, `crashpad`, `bugsplat`, `easyanticheat_setup`,
  `uploader`, `updater`, `steamwebhelper`, `steam.exe`, `epicgameslauncher`, `galaxyclient`,
  `ubisoftconnect`, `upc.exe`, `eadesktop`, `battle.net`, `riotclient`.

## Bibliothekserkennung (`library.py`, alles in try/except, fehlende Quellen still überspringen)
- **Steam**: `HKCU\Software\Valve\Steam` → `SteamPath`; `steamapps\libraryfolders.vdf` per
  Regex `"path"\s+"(.+?)"` (doppelte Backslashes auflösen); je Bibliothek `appmanifest_*.acf` →
  `appid`, `name`, `installdir` → Ordner `steamapps\common\<installdir>`. Ausschließen:
  AppID 228980, Namen mit `Redistributable`, `Proton`, `Steam Linux Runtime`, `SDK`, `Dedicated Server`.
- **Epic**: `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item` (JSON) → `DisplayName`, `InstallLocation`.
- **GOG**: `HKLM\SOFTWARE\WOW6432Node\GOG.com\Games\*` → `gameName`, `path`.
- **Ubisoft**: `HKLM\SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs\*` → `InstallDir` (Name = Ordnername).
- **Xbox/Game Pass**: auf allen Laufwerken `X:\XboxGames\<Name>` (Name = Ordnername).
- **Typische Ordner** (jeder Unterordner = Spiel): `Program Files\EA Games`,
  `Program Files (x86)\Origin Games`, `Program Files\Epic Games`, `Program Files (x86)\GOG Galaxy\Games`,
  `Riot Games` (ohne `Riot Client`) + vom Nutzer ergänzte `extra_folders`.
- Alle 10 min neu einlesen. Ergebnis: Liste `(ordner, key, name, source, appid)`.

## API (`server.py`)
GET: `/api/ping`, `/api/status` (laufende Spiele mit Startzeit, paused, Version),
`/api/overview?range=7|30|90|365|all` (Kennzahlen heute/Woche/Monat/Gesamt, Anzahl Spiele/Sitzungen,
aktuelle + längste Serie, längste Sitzung, Verlauf gestapelt nach Spiel – Tage bis 90,
Wochen bei 365, Monate bei all –, Top-Spiele im Zeitraum, Verteilung nach Stunde 0–23,
Heatmap letzte 365 Tage), `/api/games`, `/api/game/<id>` (Kennzahlen, 12 Monate, Sitzungen),
`/api/sessions?limit=300`, `/api/processes` (laufende Programme mit EXE zum manuellen Hinzufügen),
`/api/settings` (inkl. erkannte Bibliotheken je Quelle, Datenordner, Autostart-Status),
`/api/export.csv`.
POST (JSON): `/api/game/<id>/rename`, `/api/game/<id>/ignore`, `/api/session/<id>/delete`,
`/api/games/add` (`exe`, `name`), `/api/settings` (`autostart`, `paused`, `extra_folders`, `theme`).

## Oberfläche (`web/`, Vanilla JS, eigene SVG-Diagramme, keine CDN-Abhängigkeit)
- Dunkles Gaming-Design als Standard, helles Thema per Einstellung (`system/dunkel/hell`),
  Farben als CSS-Variablen auf `:root`. Schrift: `"Segoe UI Variable", "Segoe UI", system-ui`.
- **Seitenleiste**: Logo „Spielzeit“, Übersicht · Spiele · Verlauf · Einstellungen, unten Status
  (Tracking aktiv / pausiert). Hash-Routing (`#/uebersicht`, `#/spiele/12` …).
- **Übersicht**: „Jetzt im Spiel“-Karte mit Cover und Live-Timer (sonst „zuletzt gespielt …“),
  4 Kennzahl-Kacheln, Zeitraum-Umschalter (7 T / 30 T / 90 T / 1 J / Gesamt) in einer Zeile über
  den Diagrammen, gestapeltes Balkendiagramm, Top-Spiele (horizontale Balken mit Cover-Thumbnail),
  „Wann spielst du?“ (Balken je Stunde), Aktivitäts-Kalender (52 Wochen, Wochentage als Zeilen).
- **Spiele**: Suche + Sortierung (Spielzeit, zuletzt gespielt, Name), Kacheln mit Cover, Stunden,
  zuletzt gespielt. **Detail**: großer Kopf mit Cover, Kennzahlen (Gesamt, Sitzungen, Ø Sitzung,
  längste, erstes Mal, zuletzt), Monatsbalken, Sitzungsliste mit Löschen, Umbenennen, Ausblenden.
- **Verlauf**: Sitzungen nach Tagen gruppiert mit Tagessumme.
- **Einstellungen**: Autostart, Pause, Thema, Spiel manuell hinzufügen (laufende Programme
  auflisten, Namen vergeben), eigene Spieleordner, ausgeblendete Spiele (wieder einblenden),
  CSV-Export, Datenordner, erkannte Bibliotheken.
- **Cover**: Steam `https://cdn.cloudflare.steamstatic.com/steam/apps/<appid>/header.jpg`;
  bei Fehler/sonst Platzhalter mit Farbverlauf (aus Namens-Hash) und Initialen.
- Zeitformat deutsch: `12 Std 34 Min`, `45 Min`, Kacheln `123,4 Std`; Datum `Mo, 18.11.`.
- Live-Aktualisierung: `/api/status` alle 5 s, Übersicht alle 60 s.

### Diagramm-Regeln (aus dem dataviz-Skill – beim Bauen den Skill `dataviz` laden)
- Kategorie-Farben in **fester Reihenfolge** (dunkel): `#3987e5 #d95926 #199e70 #c98500 #d55181
  #0ca30c #9085e9`; hell: `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #6250d6`.
- **Farbe folgt dem Spiel, nicht dem Rang im Zeitraum**: die 7 Spiele mit der höchsten
  Gesamtspielzeit (all-time) bekommen fest Slot 1–7; alle anderen = „Andere“ in neutralem Grau.
  Ein Zeitraumwechsel darf keine Farben umfärben.
- Heatmap: eine Farbe (blau), sequenziell, leere Tage fast Flächenfarbe.
- Dünne Balken, 4 px abgerundete Enden an der Grundlinie, 2 px Abstand zwischen gestapelten Segmenten,
  zurückhaltendes Raster, Legende bei ≥ 2 Reihen, Text nie in Reihenfarbe.
- Tooltip beim Darüberfahren für jeden Balken/jede Zelle (eine gemeinsame Tooltip-`div`).
- Kein Doppel-Achsen-Diagramm.

## Testen (Pflicht, bevor du fertig meldest)
1. Unit-artige Prüfungen per Python-Skript (Standardbibliothek): Tracker mit Fake-Prozessen
   (Start/Ende, Mindestdauer, Gruppierung, Standby-Lücke, Absturz-Wiederherstellung),
   Aufteilung über Mitternacht, alle API-Endpunkte liefern gültiges JSON.
2. App auf Linux im Testmodus starten: `SPIELZEIT_DATA=<scratchpad> python3 Spielzeit.pyw --demo --headless`
   (psutil fehlt → Tracker deaktiviert sich mit Hinweis, Server läuft).
   Der Header-Zwang gilt auch für den Browser: die UI sendet ihn selbst per `fetch`.
3. Mit `chromium --headless` Screenshots aller vier Ansichten (dunkel + hell) erstellen, ansehen,
   Layoutfehler beheben. Auch Breite ~1100 px prüfen.
4. Python-Dateien mit `python3 -m py_compile` prüfen.

## Abschluss
Dem Nutzer (deutsch, einfach erklärt) sagen: Python auf Windows installieren
(„Add to PATH“ anhaken) → Ordner kopieren → `build.bat` doppelklicken → `dist\Spielzeit.exe`
starten. Ehrlich angeben, was nur auf Linux getestet wurde (Windows-Teile: winreg, Tray,
Edge-Fenster, echte Prozesserkennung) und was er auf Windows einmal ausprobieren sollte.
