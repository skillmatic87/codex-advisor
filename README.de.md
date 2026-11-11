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
