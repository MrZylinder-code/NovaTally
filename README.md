# NovaTally

[![Tests](https://github.com/MrZylinder-code/NovaTally/actions/workflows/tests.yml/badge.svg)](https://github.com/MrZylinder-code/NovaTally/actions/workflows/tests.yml)

NovaTally erfasst automatisch, wie lange du welches PC-Spiel spielst, wie früher Xfire, nur ohne Chat und ohne Konto.
Die App läuft unauffällig im Infobereich (Tray) und zeigt deine Spielzeit in einer modernen Oberfläche:
pro Spiel, pro Tag, Woche, Monat und Jahr, über alle Launcher hinweg.

- **Automatisch**: erkennt Spiele aus Steam (alle Bibliotheken), Epic, GOG, Ubisoft Connect, Xbox/Game Pass,
  EA, Riot und Battle.net sowie aus eigenen Spieleordnern. Spiele ohne Launcher lassen sich mit einem Klick hinzufügen.
- **Zuverlässig**: Sitzungen unter 1 Minute werden verworfen. Laufende Sitzungen werden alle 30 Sekunden gesichert
  (bei Absturz oder Stromausfall gehen höchstens ~30 s verloren). Standby wird nicht als Spielzeit gezählt.
- **Privat**: Alles bleibt in einer SQLite-Datei unter `%APPDATA%\NovaTally`. Ins Internet geht NovaTally nur für die
  Steam-Coverbilder und – ausschließlich auf deinen Wunsch – für die Update-Suche bei GitHub.

## Download (Windows 10/11)

Unter [Releases](https://github.com/MrZylinder-code/NovaTally/releases/latest) gibt es zwei Varianten:

- **`NovaTally-Setup.exe` (empfohlen)** – ein Installations-Assistent, der
  - prüft, ob dein PC alles mitbringt (Windows 10/11, 64 Bit, WebView2 für das NovaTally-Fenster),
  - dich den Installationsordner wählen lässt (Standard: `%LOCALAPPDATA%\Programs\NovaTally`, **ohne Adminrechte**),
  - Startmenü-Eintrag, auf Wunsch Desktop-Verknüpfung und Autostart anlegt,
  - fehlendes WebView2 direkt bei Microsoft nachinstalliert,
  - NovaTally unter *Einstellungen → Apps* sauber deinstallierbar macht (deine Spieldaten bleiben auf Wunsch erhalten).
- **`NovaTally.exe` (portabel)** – ohne Installation: an einen festen Ort legen (z. B. `C:\Tools`) und starten.

Python wird in beiden Fällen nicht gebraucht.

> Windows SmartScreen warnt bei noch nicht signierten Programmen („Der Computer wurde durch Windows geschützt“).
> Dann auf „Weitere Informationen“ → „Trotzdem ausführen“ klicken. Die SHA-256-Prüfsummen stehen im Release.

## Selbst bauen

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

## Bedienung

| Ansicht | Inhalt |
|---|---|
| **Übersicht** | „Jetzt im Spiel“ mit Live-Timer, Heute/Woche/Monat/Gesamt, Serien, Verlauf (7 T / 30 T / 90 T / 1 J / Gesamt), Top-Spiele, „Wann spielst du?“, Aktivitäts-Kalender |
| **Spiele** | Kacheln mit Cover, Suche und Sortierung. Ein Klick öffnet die Detailseite mit Kennzahlen, Monatsverlauf und allen Sitzungen (einzeln löschbar). Dort kannst du das Spiel auch umbenennen oder ausblenden |
| **Verlauf** | Alle Sitzungen nach Tagen mit Tagessumme |
| **Einstellungen** | Autostart, Pause, Design (System/Dunkel/Hell), Spiel manuell hinzufügen, eigene Spieleordner, ausgeschlossene Spiele, CSV-Export, Datenordner, erkannte Bibliotheken |

- **NovaTally hat ein eigenes Fenster.** Schließen (X) versteckt es nur, das Tracking läuft im Tray weiter.
  Doppelklick auf das Tray-Symbol (oder ein erneuter Start der App) holt dasselbe Fenster wieder nach vorne –
  es gibt immer nur eins.
- **Beenden**: Rechtsklick auf das Tray-Symbol → *Beenden*. Dort lässt sich das Tracking auch pausieren.
- Alle Diagramme zeigen beim Darüberfahren mit der Maus die genauen Werte.

## FAQ

**Ein Spiel wird nicht erkannt.**
Starte das Spiel, öffne *Einstellungen → Spiel manuell hinzufügen → Laufende Programme anzeigen* und klicke
beim Spiel auf *Hinzufügen*. Liegen viele Spiele in einem eigenen Ordner (z. B. `D:\Spiele`), füge den Ordner
unter *Eigene Spieleordner* hinzu: Jeder Unterordner zählt dann als ein Spiel.

**Ein Programm wird fälschlich als Spiel gezählt.**
Auf der Detailseite des Spiels *Ausschließen* wählen. Es wird dann nicht mehr erfasst und taucht in keiner Statistik
mehr auf, auch rückwirkend. Unter *Einstellungen → Erkannte Bibliotheken* lassen sich Programme auch ausschließen,
bevor sie je gezählt wurden. Rückgängig geht es unter *Einstellungen → Ausgeschlossene Spiele*.
Bekannte Steam-Programme, die keine Spiele sind (Wallpaper Engine, SteamVR, OBS, Lossless Scaling …), erkennt
NovaTally von sich aus nicht als Spiel.

**Der Launcher bzw. Client eines Spiels wird mitgezählt (z. B. bei League of Legends).**
Auf der Seite des Spiels unter *Was zählt als Spielzeit?* „Nur …“ das eigentliche Spielprogramm wählen – dann zählt
nur die Zeit im Spiel. Bei League of Legends ist das schon voreingestellt: Es zählen nur die Matches.

**Werden Launcher wie Steam oder der Epic Games Launcher mitgezählt?**
Nein. Launcher, Installer, Updater, Crash-Reporter und Redistributables werden ignoriert.

**Was passiert bei Absturz, Stromausfall oder Standby?**
Laufende Sitzungen werden alle 30 Sekunden gesichert. Nach einem Absturz endet die Sitzung beim letzten
Zwischenstand. Schläft der PC, endet die Sitzung beim Einschlafen. Läuft das Spiel nach dem Aufwachen weiter,
beginnt eine neue Sitzung.

**Wo liegen meine Daten? Wie mache ich ein Backup?**
In `%APPDATA%\NovaTally\novatally.db` (in die Adressleiste des Explorers eingeben). Für ein Backup NovaTally beenden
und die Datei kopieren. Zusätzlich gibt es den CSV-Export unter *Einstellungen*.

**Das Fenster öffnet sich im Browser statt als eigenes Fenster.**
Das eigene Fenster nutzt Microsoft **WebView2**, das in Windows 10/11 bereits eingebaut ist. Fehlt es ausnahmsweise,
zeigt NovaTally die Oberfläche als Edge-Fenster ohne Adressleiste bzw. im Standardbrowser. WebView2 lässt sich bei
Microsoft kostenlos nachinstallieren („WebView2 Runtime“).

**Port 47815 ist belegt.**
NovaTally nutzt den lokalen Port 47815 (nur auf diesem PC erreichbar). Startest du die App ein zweites Mal,
öffnet sie nur das Fenster der bereits laufenden Instanz.

**Demo ansehen, ohne echte Daten anzufassen:** `NovaTally.exe --demo` startet mit Beispieldaten in einem
eigenen Ordner (`%APPDATA%\NovaTally\demo`). Vorher die normale Instanz beenden.

**Ich hatte die Vorversion „Spielzeit“.**
NovaTally hieß früher „Spielzeit“. Beim ersten Start übernimmt NovaTally die Daten aus `%APPDATA%\Spielzeit`
automatisch (der alte Ordner bleibt als Sicherung liegen) und ersetzt den alten Autostart-Eintrag.
Die alte Version vorher über ihr Tray-Symbol beenden.

**Wie aktualisiere ich NovaTally?**
*Einstellungen → Updates → Nach Updates suchen.* Gibt es eine neue Version, zeigt NovaTally die Änderungen und
aktualisiert sich auf Klick selbst: Die neue `NovaTally.exe` wird aus den GitHub-Releases geladen, ihre
SHA-256-Prüfsumme geprüft, die alte Datei ersetzt und NovaTally neu gestartet. Deine Daten und der Autostart bleiben.
Läuft NovaTally aus einem Git-Ordner (`start.bat`), holt derselbe Button den neuen Stand per `git pull`.
Gesucht wird nur auf Klick; „Beim Start automatisch suchen“ ist standardmäßig aus. Liegt die EXE in einem Ordner
ohne Schreibrechte (z. B. `C:\Program Files`), lade die neue Version manuell unter Releases herunter.

**Kann ich mehrere NovaTally.exe auf dem PC haben?**
Ja, aber es läuft immer nur eine gleichzeitig, und alle teilen dieselben Daten. Ein Update ersetzt nur die Datei,
die gerade läuft. Am einfachsten: nur die installierte Version behalten und andere Kopien löschen. Startest du
trotzdem eine Kopie, weist NovaTally oben darauf hin – der Autostart bleibt bei der installierten Version.

**Deinstallieren:** Mit Installer: *Windows-Einstellungen → Apps → NovaTally → Deinstallieren* – der
Deinstaller beendet NovaTally, entfernt Autostart und Verknüpfungen und fragt, ob auch die Spieldaten weg sollen.
Portable Version: In den Einstellungen den Autostart ausschalten, NovaTally beenden, die EXE und den Ordner
`%APPDATA%\NovaTally` löschen.

## Für Entwickler

```
NovaTally.pyw          Einstieg
novatally/app.py       Einzelinstanz, DB, Tracker, Server, Tray, Fenster  (--demo, --headless, --autostart)
novatally/window.py    eigenes Fenster (pywebview + WebView2), Schließen = Verstecken
novatally/updater.py   Update-Suche und -Installation (Releases bzw. git pull)
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
tools/build_exe.py     PyInstaller-Aufruf (für build.bat und GitHub Actions)
tools/smoke_test.ps1   startet die EXE testweise und prüft die Oberfläche
installer/NovaTally.iss  Installer (Inno Setup): Systemprüfung, Ordnerwahl, Autostart, WebView2, Deinstallation
tools/build_installer.ps1 / installer_test.ps1  Installer bauen bzw. still installieren/deinstallieren und prüfen
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
