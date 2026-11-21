# NovaTally

[![Tests](https://github.com/MrZylinder-code/NovaTally/actions/workflows/tests.yml/badge.svg)](https://github.com/MrZylinder-code/NovaTally/actions/workflows/tests.yml)

NovaTally erfasst automatisch, wie lange du welches PC-Spiel spielst, wie früher Xfire, nur ohne Chat und ohne Konto.
Die App läuft unauffällig im Infobereich (Tray) und zeigt deine Spielzeit in einer modernen Oberfläche:
pro Spiel, pro Tag, Woche, Monat und Jahr, über alle Launcher hinweg.

- **Automatisch**: erkennt Spiele aus Steam (alle Bibliotheken), Epic, GOG, Ubisoft Connect, Xbox/Game Pass,
  EA, Riot und Battle.net sowie aus eigenen Spieleordnern. Spiele ohne Launcher lassen sich mit einem Klick hinzufügen.
- **Zuverlässig**: Sitzungen unter 1 Minute werden verworfen. Laufende Sitzungen werden alle 30 Sekunden gesichert
  (bei Absturz oder Stromausfall gehen höchstens ~30 s verloren). Standby wird nicht als Spielzeit gezählt.
- **Privat**: Alles bleibt in einer SQLite-Datei unter `%APPDATA%\NovaTally`. Die einzige Internetverbindung lädt
  die Steam-Coverbilder.

## Installation (Windows 10/11)

1. **Python installieren** (einmalig): <https://www.python.org/downloads/> → „Download Python 3.x“.
   Im Installer unten **„Add python.exe to PATH“ anhaken**, dann „Install Now“.
2. Diesen Ordner (`NovaTally`) irgendwohin auf den PC kopieren, z. B. nach `C:\Tools\NovaTally`.
3. **`build.bat` doppelklicken.** Das Skript richtet alles ein und baut `dist\NovaTally.exe` (dauert 1–3 Minuten).
4. `dist\NovaTally.exe` starten. Wenn du willst, legst du die EXE vorher an einen festen Ort
   (z. B. `C:\Tools\NovaTally.exe`) und startest sie von dort, denn der Autostart merkt sich diesen Pfad.

Beim ersten Start öffnet sich das Fenster, und NovaTally trägt sich in den Windows-Autostart ein
(abschaltbar unter *Einstellungen*). Danach läuft die App im Infobereich unten rechts weiter
(Symbol: blaues Quadrat mit Play-Zeichen; eventuell hinter dem Pfeil `^` versteckt).

**Ohne Bauen** geht es auch: `start.bat` doppelklicken. NovaTally läuft dann direkt mit Python.

> Windows SmartScreen kann bei einer selbst gebauten EXE warnen („Der Computer wurde durch Windows geschützt“).
> Dann auf „Weitere Informationen“ → „Trotzdem ausführen“ klicken.

## Bedienung

| Ansicht | Inhalt |
|---|---|
| **Übersicht** | „Jetzt im Spiel“ mit Live-Timer, Heute/Woche/Monat/Gesamt, Serien, Verlauf (7 T / 30 T / 90 T / 1 J / Gesamt), Top-Spiele, „Wann spielst du?“, Aktivitäts-Kalender |
| **Spiele** | Kacheln mit Cover, Suche und Sortierung. Ein Klick öffnet die Detailseite mit Kennzahlen, Monatsverlauf und allen Sitzungen (einzeln löschbar). Dort kannst du das Spiel auch umbenennen oder ausblenden |
| **Verlauf** | Alle Sitzungen nach Tagen mit Tagessumme |
| **Einstellungen** | Autostart, Pause, Design (System/Dunkel/Hell), Spiel manuell hinzufügen, eigene Spieleordner, ausgeblendete Spiele, CSV-Export, Datenordner, erkannte Bibliotheken |

- **Fenster schließen** schließt nur die Ansicht. Das Tracking läuft im Tray weiter.
  Doppelklick auf das Tray-Symbol (oder ein erneuter Start der App) öffnet das Fenster wieder.
- **Beenden**: Rechtsklick auf das Tray-Symbol → *Beenden*. Dort lässt sich das Tracking auch pausieren.
- Alle Diagramme zeigen beim Darüberfahren mit der Maus die genauen Werte.

## FAQ

**Ein Spiel wird nicht erkannt.**
Starte das Spiel, öffne *Einstellungen → Spiel manuell hinzufügen → Laufende Programme anzeigen* und klicke
beim Spiel auf *Hinzufügen*. Liegen viele Spiele in einem eigenen Ordner (z. B. `D:\Spiele`), füge den Ordner
unter *Eigene Spieleordner* hinzu: Jeder Unterordner zählt dann als ein Spiel.

**Ein Programm wird fälschlich als Spiel gezählt.**
Auf der Detailseite des Spiels *Ausblenden* wählen. Es wird dann nicht mehr erfasst und taucht in keiner Statistik
mehr auf. Unter *Einstellungen → Ausgeblendete Spiele* kannst du es wieder einblenden.

**Werden Launcher wie Steam oder der Epic Games Launcher mitgezählt?**
Nein. Launcher, Installer, Updater, Crash-Reporter und Redistributables werden ignoriert.

**Was passiert bei Absturz, Stromausfall oder Standby?**
Laufende Sitzungen werden alle 30 Sekunden gesichert. Nach einem Absturz endet die Sitzung beim letzten
Zwischenstand. Schläft der PC, endet die Sitzung beim Einschlafen. Läuft das Spiel nach dem Aufwachen weiter,
beginnt eine neue Sitzung.

**Wo liegen meine Daten? Wie mache ich ein Backup?**
In `%APPDATA%\NovaTally\novatally.db` (in die Adressleiste des Explorers eingeben). Für ein Backup NovaTally beenden
und die Datei kopieren. Zusätzlich gibt es den CSV-Export unter *Einstellungen*.

**Das Fenster öffnet sich im normalen Browser statt als eigenes Fenster.**
NovaTally nutzt Microsoft Edge für ein Fenster ohne Adressleiste. Fehlt Edge, wird der Standardbrowser verwendet.

**Port 47815 ist belegt.**
NovaTally nutzt den lokalen Port 47815 (nur auf diesem PC erreichbar). Startest du die App ein zweites Mal,
öffnet sie nur das Fenster der bereits laufenden Instanz.

**Demo ansehen, ohne echte Daten anzufassen:** `NovaTally.exe --demo` startet mit Beispieldaten in einem
eigenen Ordner (`%APPDATA%\NovaTally\demo`). Vorher die normale Instanz beenden.

**Ich hatte die Vorversion „Spielzeit“.**
NovaTally hieß früher „Spielzeit“. Beim ersten Start übernimmt NovaTally die Daten aus `%APPDATA%\Spielzeit`
automatisch (der alte Ordner bleibt als Sicherung liegen) und ersetzt den alten Autostart-Eintrag.
Die alte Version vorher über ihr Tray-Symbol beenden.

**Deinstallieren:** In den Einstellungen den Autostart ausschalten, NovaTally beenden, die EXE und den Ordner
`%APPDATA%\NovaTally` löschen.

## Für Entwickler

```
NovaTally.pyw          Einstieg
novatally/app.py       Einzelinstanz, DB, Tracker, Server, Tray, Fenster  (--demo, --headless, --autostart)
novatally/db.py        SQLite-Schema und Zugriffe (WAL, eine Verbindung + Lock)
novatally/library.py   Spielebibliotheken erkennen
novatally/tracker.py   Prozess-Abfrage (psutil) und Sitzungslogik
novatally/stats.py     Auswertungen (Tagesaufteilung über Mitternacht, Serien, Verlauf …)
novatally/server.py    HTTP-Server nur auf 127.0.0.1:47815, JSON-API, CSV-Export
novatally/tray.py      Tray-Symbol (pystray + Pillow)
novatally/autostart.py Registry-Eintrag HKCU\…\Run
novatally/demo.py      Demo-Daten
novatally/web/         Oberfläche (HTML/CSS/JS, eigene SVG-Diagramme)
tools/make_icon.py     erzeugt icon.ico ohne Zusatzpakete
tests/                 Tests (nur Standardbibliothek)
```

Tests: `python -m unittest discover -s tests -v`
Ohne Tray/Fenster starten (auch unter Linux): `python NovaTally.pyw --demo --headless`, dann <http://127.0.0.1:47815> öffnen.

Sicherheit des lokalen Servers: Er lauscht nur auf `127.0.0.1`, prüft den `Host`-Header (Schutz gegen
DNS-Rebinding), verlangt für alle `/api/*`-Aufrufe den Header `X-NovaTally: 1` (fremde Webseiten scheitern am
CORS-Preflight) und sendet keine CORS-Header.

## Mitmachen

Beiträge sind willkommen: Fehlerberichte, neue Erkennungsregeln für Launcher, Verbesserungen an der Oberfläche.
Änderungen kommen ausschließlich über **Pull Requests** in `main`. Wie das geht, steht in
[CONTRIBUTING.md](CONTRIBUTING.md). Die ursprüngliche Zielbeschreibung und der Bauplan liegen in [`docs/`](docs/).

## Lizenz

[MIT](LICENSE): frei nutzbar, veränderbar und weitergebbar, solange der Lizenzhinweis erhalten bleibt.
