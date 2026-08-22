# Party-Ordner (neue Charaktere)

Sammelstelle für die **Charakter-JSONs der neuen Party** (ersetzen Garran/Eli/Yann).
Eine Datei pro Spieler. Dieser Ordner wird **committet** (`.gitignore`-Allowlist um
`data/party/` erweitert) — anders als die echten per-Channel-Session-Ordner.

**Aktuell hier:**
- `fridolin_feuchtgebietheld.json` — Tobi / `Pr0degie` (Interrogator & Psioniker)
- `gellicus_schulz.json` — Timo (Schwerenöter, Reden/Wissen)
- `rektalus_zerfickus.json` — Sezgin / `SezBoss69` (Nahkämpfer, Athletik)
- `rene_redo.json` — Vincent / `Vinnie` (Enginseer, Fernkampf/Technologie)

Alle vier sind in `data/sessions/1343673766487654464/characters.json` zusammengeführt.

## Format

Jede Datei im Schema von `fridolin_feuchtgebietheld.json` bzw. `tools/example_garran_vex.json`
(self-contained: `system`, `characters: [ … ]`, `aliases`). Gebaut wird ein Charakter über
`docs/how-to-create-a-character.html` (90-Punkte-Kauf, Herkunft +5/+5, 6 Skill-Steigerungen
à +5 / max 2 je Skill, Wunden = StrB + 2×TghB + WilB).

Pflicht fürs Würfel-Engine: `name`, `characteristics`, `skills`, `wounds`/`max_wounds`,
`inventory`; optional `player` (→ Alias). Psyker zusätzlich: `psyker: true`, `disciplines`,
`known_powers` (**Namen müssen Katalog-Schlüssel in `data/systems/imperium_maledictum.json`
treffen**, sonst kein `<<MANIFEST>>`-Wurf).

## Wenn ein Charakter dazukommt

Claude führt die Dateien zur **einen** vom Bot geladenen
`data/sessions/<channel_id>/characters.json` zusammen (gemeinsame `characters`-Liste +
`aliases`) und füllt die PDF-Bögen (`tools/fill_character_sheet.py`, bleiben lokal).

**Achtung State:** `state.json` wird nur **einmal** aus dieser Datei geseedet
(`WorldState.seed_from_store`). Ein bereits existierendes `state.json` nimmt einen neu
dazugekommenen Charakter also **nicht** auf — für die laufende Kampagne muss er entweder
von Hand in `state.json` ergänzt oder der State zurückgesetzt werden. Ein Debug-Run ist
davon nicht betroffen: der legt seinen eigenen `state.debug.json` an (ADR 056) und seedet
dort frisch.
