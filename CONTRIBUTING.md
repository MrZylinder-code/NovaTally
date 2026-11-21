# Mitmachen bei NovaTally

Danke, dass du helfen möchtest! Alle Änderungen kommen über **Pull Requests**. Direkt auf `main` wird nicht gepusht.

## Ablauf

1. **Forken** (Button „Fork“ oben rechts auf GitHub) und deinen Fork klonen.
2. Einen **Branch** anlegen, z. B. `git switch -c erkennung-ea-app`.
3. Änderung machen und **Tests ausführen**:
   ```bash
   python -m unittest discover -s tests -v
   ```
4. Committen (gerne auf Deutsch, kurz und beschreibend) und den Branch in deinen Fork pushen.
5. Auf GitHub einen **Pull Request** gegen `main` öffnen und die Vorlage ausfüllen.

Jeder Pull Request wird automatisch unter Windows und Linux getestet, und unter Windows wird probeweise die
`NovaTally.exe` gebaut. Gemergt wird erst, wenn die Tests grün sind und jemand den PR geprüft hat.

## Lokal starten

```bash
python NovaTally.pyw --demo --headless     # Demo-Daten, ohne Tray, dann http://127.0.0.1:47815 öffnen
```

Unter Windows startet `start.bat` die App mit Tray, `build.bat` baut die EXE.

## Leitlinien

- **Datenschutz zuerst:** Keine Telemetrie, keine Konten, keine Cloud. Verbindungen nach außen gibt es nur für die
  Steam-Coverbilder und die Update-Suche bei GitHub (nur auf Klick oder ausdrücklich eingeschaltet, ohne
  persönliche Daten). Weitere Verbindungen nach außen werden nicht angenommen.
- **Kernlogik nur mit der Standardbibliothek** (`db`, `stats`, `tracker`, `server`, `library`). `psutil`, `pystray`,
  `Pillow` und `winreg` nur dort importieren, wo sie gebraucht werden, damit alles andere überall testbar bleibt.
- **Oberfläche ohne Frameworks und ohne CDN:** Vanilla JS, eigene SVG-Diagramme. Texte auf Deutsch.
- **Neue Erkennungsregeln** (Launcher, ignorierte Programme) bitte mit einem Test in `tests/test_novatally.py`.
- **Nicht-Ziele** (siehe `docs/GOAL.md`): Freundesliste, Chat, Screenshots, Overlay, Cloud-Sync, Achievements.

## Neue Version veröffentlichen (nur Maintainer)

1. In `novatally/__init__.py` die Version erhöhen (z. B. `1.1.0`) und in `CHANGELOG.md` einen Abschnitt
   `## 1.1.0` mit den Änderungen ergänzen. Beides per Pull Request nach `main`.
2. Auf dem gemergten Stand das Tag setzen und pushen:
   ```bash
   git tag v1.1.0
   git push origin v1.1.0
   ```
3. Der Workflow „Release“ prüft, dass Tag und Version zusammenpassen, testet, baut `NovaTally.exe`,
   startet sie probeweise und veröffentlicht sie mit Prüfsumme und Changelog-Text unter *Releases*.

## Fehler melden

Bitte ein Issue öffnen mit Windows-Version, Spiel und Launcher sowie den letzten Zeilen aus
`%APPDATA%\NovaTally\novatally.log`. Vorher prüfen, ob die Datei persönliche Pfade enthält, die du nicht teilen möchtest.
