# Änderungen

Alle nennenswerten Änderungen an NovaTally. Für jedes Release übernimmt der Release-Workflow den passenden
Abschnitt (`## <Version>`) als Beschreibung.

## 1.2.0

- **Eigenes Fenster**: NovaTally öffnet sich jetzt in einem eigenen Programmfenster (Microsoft WebView2, in
  Windows 10/11 eingebaut) statt als Edge-Fenster – mit eigenem Eintrag in der Taskleiste und ohne Edge im
  Hintergrund. Die Oberfläche bleibt gleich.
- Es gibt immer genau **ein** Fenster: Schließen (X) versteckt es nur, ein Tray-Klick oder ein zweiter Start holt
  es zurück. Beim ersten Verstecken erklärt ein kurzer Hinweis, dass NovaTally im Infobereich weiterzählt.
- Fehlt WebView2 ausnahmsweise, öffnet sich die Oberfläche wie bisher über Edge bzw. den Browser.

## 1.1.1

- **Update-Suche repariert**: In der Windows-EXE meldete sie „GitHub ist gerade nicht erreichbar“. NovaTally bringt
  jetzt die nötigen Sicherheitszertifikate selbst mit, nutzt notfalls einen Ausweichweg über die Release-Seite und
  nennt bei Problemen den genauen Grund (z. B. Zertifikat, Zeitüberschreitung, keine Internetverbindung).
- **Kein doppeltes Fenster mehr**: Ein Klick aufs Tray-Symbol (oder ein zweiter Start) holt ein bereits offenes
  NovaTally-Fenster nach vorne, statt ein weiteres zu öffnen.

## 1.1.0

- **Update-Button**: *Einstellungen → Updates → Nach Updates suchen* zeigt neue Versionen samt Änderungen.
  Ein Klick auf *Jetzt aktualisieren* lädt die neue `NovaTally.exe` aus den GitHub-Releases, prüft die
  SHA-256-Prüfsumme, ersetzt die alte Datei und startet NovaTally neu – Daten und Autostart bleiben.
- Läuft NovaTally aus einem Git-Ordner, holt der Button den neuen Stand per `git pull`.
- Gesucht wird nur auf Klick. Optional lässt sich die Suche beim Start einschalten (standardmäßig aus);
  ein gefundenes Update wird dann in der Seitenleiste angezeigt.

## 1.0.1

- **Mehr Spiele werden automatisch erkannt**: NovaTally liest jetzt auch die Windows-Liste der installierten
  Programme und erkennt darin Spiele bekannter Hersteller – z. B. **Path of Exile** (Standalone-Client von
  Grinding Gear Games), Spiele aus der **EA app**, von Blizzard/Activision, Riot, Rockstar, CD Projekt,
  Wargaming, Gaijin, Digital Extremes, HoYoverse, Kuro Games, Square Enix, Jagex u. a.
- Path of Exile 1 und 2 werden zusätzlich über den Ordner `Grinding Gear Games` und den Registry-Eintrag erkannt.
- Launcher, Anti-Cheat-Dienste (z. B. Riot Vanguard, BattlEye) und Werkzeuge werden dabei sicher ausgeschlossen,
  damit nichts dauerhaft als Spielzeit zählt.
- Bereits manuell hinzugefügte Spiele bleiben unverändert und haben weiter Vorrang.
- **Programme ausschließen**: „Ausblenden“ heißt jetzt „Ausschließen“. Neu: In *Einstellungen → Erkannte
  Bibliotheken* hat jedes erkannte Spiel einen Button *Ausschließen* – auch bevor es je gezählt wurde.
- **Keine Spiele**: Bekannte Steam-Programme wie **Wallpaper Engine**, SteamVR, OBS Studio, Lossless Scaling,
  Soundpad oder Blender werden nicht mehr als Spiel erkannt. Wurden sie bereits erfasst, schließt NovaTally sie
  beim ersten Start einmalig aus (unter *Ausgeschlossene Spiele* rückgängig zu machen).

## 1.0.0

Erste Version von NovaTally.

- **Automatisches Tracking im Hintergrund**: läuft im Infobereich, startet mit Windows (abschaltbar),
  zählt mehrere Prozesse eines Spiels als eine Sitzung und verwirft Sitzungen unter 1 Minute.
- **Absturz- und standby-sicher**: laufende Sitzungen werden alle 30 Sekunden gesichert,
  Schlafzeit zählt nicht als Spielzeit. Tracking lässt sich pausieren.
- **Spielerkennung ohne Pflege**: Steam (alle Bibliotheken), Epic, GOG, Ubisoft Connect, Xbox/Game Pass,
  EA, Riot, Battle.net, eigene Spieleordner und manuell hinzugefügte Programme.
- **Statistik-Oberfläche**: Übersicht mit „Jetzt im Spiel“, Kennzahlen, Serien, Verlauf (7 Tage bis Gesamt),
  Top-Spielen, Tageszeiten und Aktivitäts-Kalender; Spieleseite mit Steam-Covern; Verlauf; Einstellungen.
  Dunkles und helles Design.
- **Deine Daten bleiben lokal**: SQLite unter `%APPDATA%\NovaTally`, kein Konto, keine Cloud, CSV-Export.
- Übernimmt Daten der Vorversion „Spielzeit“ automatisch.
