# Codex Advisor – deutsche Anleitung

Das Hauptmodell arbeitet weiter und zieht bei schwierigen Fragen einen konfigurierbaren Berater hinzu.
Standard: **Sol 6.1 medium** als Basis und **Astra high** als Berater. Beide Modelle und Denkstufen
sind bei der Einrichtung wählbar. Eine Kostenersparnis ist nicht nachgewiesen.

## Installation

Python 3.11+, Git und Codex mit nativen Subagenten und Modellauswahl werden benötigt.

```sh
git clone https://github.com/skillmatic87/codex-advisor.git
cd codex-advisor
python -m venv .venv
```

Umgebung aktivieren: Windows PowerShell `.venv\Scripts\Activate.ps1`, Linux/macOS
`source .venv/bin/activate`. Falls nötig `python3` statt `python` verwenden.

```sh
python -m pip install -r requirements.txt
python scripts/setup.py
```

Im Dialog `de` wählen. Anschließend Basismodell, Denkstufe, Beratermodell und dessen Denkstufe
auswählen. Angeboten werden lokal zwischengespeicherte Fähigkeiten; tatsächlicher Kontozugang
ist dadurch nicht garantiert. Eigene Modell-IDs sind mit Warnung möglich.

Alternativ Codex im Chat um Installation und Einrichtung dieses Repositorys bitten. Nach einer
Installation durch einen allgemeinen Skill-Installer `$codex-advisor` aufrufen und die Einrichtung
abschließen. Das Kopieren des Skills führt keinen Installationsdialog aus.

Die Einrichtung setzt globale Standards für **neue Sitzungen**, installiert den Skill,
eine neutrale Beraterrolle und globale Automatik-Anweisungen. Laufende Chats werden nicht
umgeschaltet. Projekt-, Profil- und Sitzungsvorgaben können die globalen Standards übersteuern.

## Nutzungsstatistik

Im Chat beispielsweise: „Zeige meine Advisor-Statistik der letzten sieben Tage.“ Im Terminal:

```sh
python scripts/stats.py
python scripts/stats.py --group-by model
python scripts/stats.py --since 2026-11-01 --until 2026-11-30 --group-by day
python scripts/stats.py --chat THREAD-ID --json
```

Standardmäßig werden alle lokal erfassten bestätigten Beratungen ausgewertet. Filter:
`--since`, `--until`, `--chat`, `--model`; Gruppierung: `day`, `chat`, `model`.
Die Datumsgrenzen schließen den ganzen jeweiligen lokalen Kalendertag ein. Sprache wird aus der
Installation übernommen oder mit `--language de|en` gewählt. `--codex-home PFAD` ist möglich.
Der Statistikbefehl benötigt nur Python 3.11+, keine zusätzlichen Pakete oder Netzwerkverbindung.

Die Übersicht unterscheidet Berater-Threads und gestartete Beratungsrunden einschließlich
Folgefragen. Sie zeigt laufende Runden sowie Eingabe-, Cache-, Ausgabe-, Gesamt- und Reasoning-Tokens.
Tokens werden ihrem Nutzungszeitpunkt zugeordnet, Runden ihrem Start. Eine Runde über Mitternacht
kann am Folgetag Tokens ohne neu gestartete Runde erzeugen. Bei Modellwechsel kann dieselbe Runde
in mehreren Modellgruppen erscheinen; die Gesamtanzahl bleibt eindeutig gezählt.

Bekannte Beraterrollen und der eigene Taskname `codex_advisor_*` werden bestätigt zugeordnet.
Andere historische Kandidaten erscheinen separat und zählen nicht in die bestätigte Summe.
Ein Astra-Modell allein beweist keine Beratung. Aktive und archivierte Protokolle werden lesend
ausgewertet; doppelte Historien und kumulierte Zähler nicht mehrfach addiert. Fehlende Anfangswerte,
zurückgesetzte Zähler und beschädigte Daten führen zu einem Hinweis auf unvollständige Erfassung.
Unbekannte Tokens sind `?` beziehungsweise JSON `null`, niemals null Tokens.

Cache- und Reasoning-Tokens sind Teilmengen. Es werden keine Euro-Kosten oder Abo-Prozente geschätzt.
Keine Chat-Inhalte werden exportiert, keine Quelldaten verändert und keine Hintergrunddatenbank
angelegt. Nur auf Wunsch per `--json > bericht.json` exportieren. Start-/Endmeldungen bleiben kurz.

## Einstellungen und Updates

```sh
python scripts/setup.py --defaults --language de
python scripts/setup.py --check
git pull --ff-only
python -m pip install -r requirements.txt
python scripts/setup.py
python scripts/setup.py --reconfigure
```

Updates behalten die Auswahl; `--reconfigure` fragt erneut, `--defaults` setzt bewusst die
Standardauswahl. Einstellungen liegen unter `$CODEX_HOME/codex-advisor/settings.json`, sonst
`~/.codex/codex-advisor/settings.json`. `--codex-home PFAD` erlaubt ein anderes Ziel.
`--dry-run` zeigt Änderungen ohne zu schreiben, `--list-models` die lokalen Modellinformationen.

Bekannte alte Astra-Regeln werden migriert; angepasste Altregeln führen zu einem Konflikthinweis.
Andere Einstellungen, Kommentare und Profile bleiben erhalten. Sicherungen liegen lokal unter
`codex-advisor/backups` im Codex-Home. Nach einer unterbrochenen Installation `--recover` verwenden;
spätere fremde Änderungen werden nicht überschrieben. Sicherungen können persönliche Einstellungen
enthalten und gehören nicht ins Repository.

## Beratung

Automatisch bei festgefahrenen Fehlern nach zwei unterschiedlichen begründeten Versuchen,
offenen Architekturabwägungen, widersprüchlichen Befunden und schwierigen Korrektheits- oder
Sicherheitsfragen. Auch ausdrücklich über `$codex-advisor` möglich. Der Berater erhält ein
gezieltes Briefing samt relevanten Änderungen und Git-Verlauf. Umsetzung und Prüfung bleiben
beim Hauptmodell. Start, Ende, Fehler und Abbruch erscheinen im Chat.

Fehlt native Delegation mit der gewünschten Modellauswahl, wird dies gemeldet. Es gibt keinen
stillen Modellwechsel. Details zu Tests und Konfigurationsschema stehen in der [README](README.md).
