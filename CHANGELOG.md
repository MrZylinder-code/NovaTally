# Änderungen

Alle nennenswerten Änderungen an NovaTally. Für jedes Release übernimmt der Release-Workflow den passenden
Abschnitt (`## <Version>`) als Beschreibung.

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
