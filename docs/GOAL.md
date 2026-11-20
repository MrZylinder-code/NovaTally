# Zielbeschreibung (Goal Prompt): „Spielzeit“

> Baue eine schlanke Windows-Anwendung, die – wie früher Xfire – automatisch erfasst,
> wie lange ich welches PC-Spiel spiele, und mir das in einer schönen, modernen
> Oberfläche als Statistik zeigt. Chat- und Social-Funktionen sind ausdrücklich **nicht** gewünscht.

## Ziel
Ich will ohne eigenes Zutun wissen: Wie viele Stunden habe ich insgesamt, pro Spiel,
pro Tag/Woche/Monat/Jahr gespielt – über **alle** Launcher hinweg (Steam, Epic, GOG,
Xbox/Game Pass, Ubisoft, EA, Battle.net, Riot und Spiele ohne Launcher).

## Muss-Anforderungen
1. **Automatisches Tracking im Hintergrund**
   - Startet mit Windows (abschaltbar), läuft unauffällig als Symbol im Infobereich (Tray).
   - Prüft alle paar Sekunden die laufenden Prozesse und erkennt Spiele.
   - Mehrere Prozesse desselben Spiels zählen als **eine** Sitzung.
   - Sitzungen unter 1 Minute werden verworfen (Fehlstarts, Updater).
   - **Absturzsicher**: Laufende Sitzungen werden regelmäßig zwischengespeichert;
     nach Absturz/Stromausfall gehen höchstens ~30 Sekunden verloren.
   - **Standby-sicher**: Schläft der PC, zählt die Schlafzeit nicht als Spielzeit.
   - Tracking lässt sich pausieren.
2. **Automatische Spielerkennung ohne Pflege**
   - Liest installierte Spiele aus Steam (inkl. aller Bibliotheksordner und echten Spielnamen),
     Epic, GOG, Ubisoft Connect, Xbox/Game Pass (`XboxGames`) sowie typischen Spieleordnern.
   - Eigene Spieleordner können ergänzt werden (jeder Unterordner = ein Spiel).
   - Spiele können **manuell** aus der Liste laufender Programme hinzugefügt werden.
   - Installer, Crash-Reporter, Launcher und Redistributables werden ignoriert.
3. **Statistik-Oberfläche (deutsch, dunkles Gaming-Design, optional hell)**
   - **Übersicht**: „Jetzt im Spiel“ mit Live-Timer · Kennzahlen (Heute, Woche, Monat, Gesamt) ·
     Spielzeit-Verlauf als gestapeltes Balkendiagramm nach Spiel (7 Tage / 30 Tage / 90 Tage /
     1 Jahr / Gesamt) · Top-Spiele · „Wann spielst du?“ nach Tageszeit ·
     Aktivitäts-Kalender der letzten 12 Monate · Serie (Tage am Stück).
   - **Spiele**: Kachelansicht mit Cover (Steam-Cover automatisch, sonst schönes Platzhalterbild),
     Suche und Sortierung; Detailseite pro Spiel mit Kennzahlen, Monatsverlauf und allen Sitzungen.
   - **Verlauf**: Alle Sitzungen nach Tagen gruppiert.
   - **Einstellungen**: Autostart, Pause, Spiel manuell hinzufügen, eigene Spieleordner,
     ausgeblendete Spiele, CSV-Export, Datenordner.
   - Spiele umbenennen, ausblenden und einzelne Sitzungen löschen.
   - Alle Diagramme mit Tooltips beim Darüberfahren.
4. **Daten gehören mir**
   - Alles lokal in einer SQLite-Datei unter `%APPDATA%\Spielzeit`. Kein Konto, keine Cloud.
   - Einzige Internetverbindung: Laden der Steam-Coverbilder (optional, fällt sauber zurück).
   - CSV-Export aller Sitzungen.
5. **Einfach zu installieren**
   - Ein Doppelklick-Skript baut eine eigenständige `Spielzeit.exe`.
   - Zweiter Start der App öffnet nur das Fenster der bereits laufenden Instanz.

## Technik
- Python 3.11+ · `psutil` (Prozesse) · `pystray` + `Pillow` (Tray-Symbol) · SQLite (eingebaut).
- Oberfläche: lokale Web-UI (HTML/CSS/JS ohne Frameworks, eigene SVG-Diagramme), ausgeliefert von
  einem eingebauten Mini-Server nur auf `127.0.0.1`, geöffnet als App-Fenster über Microsoft Edge
  (ohne Adressleiste) – Fallback: Standardbrowser.
- Schutz des lokalen Servers: nur `127.0.0.1`, Host-Prüfung, Pflicht-Header für API-Aufrufe.
- Verpackung mit PyInstaller.

## Nicht-Ziele
Freundesliste, Chat, Screenshots/Videos, Overlay im Spiel, Cloud-Sync, Achievements.

## Fertig ist es, wenn
- Ich ein Steam- und ein Nicht-Steam-Spiel starte und beide nach dem Beenden mit korrekter
  Dauer in der Übersicht erscheinen.
- Die App nach einem Neustart von Windows von selbst weiterzählt.
- Alle Ansichten mit Demo-Daten sauber und ohne Layoutfehler aussehen.
