# Party-Ordner (neue Charaktere)

Sammelstelle für die **Charakter-JSONs der neuen Party** (ersetzen Garran/Eli/Yann).
Eine Datei pro Spieler. Dieser Ordner wird **committet** (`.gitignore`-Allowlist um
`data/party/` erweitert) — anders als die echten per-Channel-Session-Ordner.

**Aktuell hier:**
- `fridolin_feuchtgebietheld.json` — Tobi (Interrogator/Psioniker)

**Noch erwartet:** Sezgins + Timos Charakter (je eine `.json`-Datei hier ablegen).

## Format

Jede Datei im Schema von `fridolin_feuchtgebietheld.json` bzw. `tools/example_garran_vex.json`
(self-contained: `system`, `characters: [ … ]`, `aliases`). Gebaut wird ein Charakter über
`docs/how-to-create-a-character.html` (90-Punkte-Kauf, Herkunft +5/+5, 6 Skill-Steigerungen
à +5 / max 2 je Skill, Wunden = StrB + 2×TghB + WilB).

Pflicht fürs Würfel-Engine: `name`, `characteristics`, `skills`, `wounds`/`max_wounds`,
`inventory`; optional `player` (→ Alias). Psyker zusätzlich: `psyker: true`, `disciplines`,
`known_powers` (**Namen müssen Katalog-Schlüssel in `data/systems/imperium_maledictum.json`
treffen**, sonst kein `<<MANIFEST>>`-Wurf).

## Wenn alle drei da sind

Claude führt die drei Dateien zur **einen** vom Bot geladenen
`data/sessions/<channel_id>/characters.json` zusammen (gemeinsame `characters`-Liste +
`aliases`), füllt optional die PDF-Bögen (`tools/fill_character_sheet.py`) und setzt den
alten Session-State/History/Recap zurück, damit Chemical Burn frisch mit der neuen Party startet.
