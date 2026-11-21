# Änderungen

Alle nennenswerten Änderungen an NovaTally. Für jedes Release übernimmt der Release-Workflow den passenden
Abschnitt (`## <Version>`) als Beschreibung.

## 1.0.1

- **Mehr Spiele werden automatisch erkannt**: NovaTally liest jetzt auch die Windows-Liste der installierten
  Programme und erkennt darin Spiele bekannter Hersteller – z. B. **Path of Exile** (Standalone-Client von
  Grinding Gear Games), Spiele aus der **EA app**, von Blizzard/Activision, Riot, Rockstar, CD Projekt,
  Wargaming, Gaijin, Digital Extremes, HoYoverse, Kuro Games, Square Enix, Jagex u. a.
- Path of Exile 1 und 2 werden zusätzlich über den Ordner `Grinding Gear Games` und den Registry-Eintrag erkannt.
- Launcher, Anti-Cheat-Dienste (z. B. Riot Vanguard, BattlEye) und Werkzeuge werden dabei sicher ausgeschlossen,
  damit nichts dauerhaft als Spielzeit zählt.
- Bereits manuell hinzugefügte Spiele bleiben unverändert und haben weiter Vorrang.

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
