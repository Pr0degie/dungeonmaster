# tests/golden/ — Golden-Transcripts für das Replay-Harness (`uv run dm-eval`, ADR 046)

Jede `.jsonl`-Datei hier ist eine aufgezeichnete (oder synthetische) Session im erweiterten
`history.jsonl`-Journal-Format: ein `{"kind": "session", …}`-Header, danach pro DM-Turn ein
Record mit den Replay-Feldern (`lines`/`results`/`notes`/`raw`/`markers`/`router`/
`state_before`/`scene_verdict`/`flag_verdicts`/`uhr_verdicts`/`zeit_verdicts` — die letzten
drei seit ADR 047/048). `dm-eval` spielt die Turns mit **gemocktem LLM** (Playback
der `raw`-Antworten) durch die heutige Pipeline und difft Ist gegen Soll — Kategorien `turn`
(Turn-Komposition), `answer` (Sanitizer), `marker` (Marker-Parsing + Suppression), `router`
(Roll-Router-Entscheidung), `state` (Szenen-/Flag-/Uhr-/Zeit-Verdikte), `llm`
(Call-Buchhaltung). **Regression, nicht Qualität** — Details in ADR 046.

## Bestand

| Datei | Deckt ab |
|---|---|
| `dice_flow.jsonl` | `<<TEST>>`-Parse, Router-Verdikt (ja/nein), Results-only-Suppression |
| `scene_flags.jsonl` | `<<ORT>>`/`<<ERLEDIGT>>`-Parse, Move-Gate + Flag-Validierung (Fixture-Abenteuer) |

Beide sind synthetisch: `uv run python tests/golden/generate_synthetic.py` erzeugt sie über
den echten Capture-Pfad neu. Nur laufen lassen, wenn eine Verhaltensänderung **gewollt** ist —
und dann den git-Diff der `.jsonl` lesen: jede geänderte Zeile ist eine Änderung, die du
absegnest. `fixtures/mini_adventure/` ist ein eigenes Mini-Abenteuer (keine Buch-Inhalte).

## Ein frisches Golden aus einer Live-Session ziehen

1. Nach der Session (`!leave` rotiert das Journal):
   `data/sessions/<channel_id>/history.<stamp>.jsonl` kopieren — z. B. nach
   `tests/golden/live_<datum>.jsonl`.
2. **Kürzen:** nur den einen `{"kind": "session"}`-Header + eine Handvoll interessanter,
   aufeinanderfolgender Turns behalten (Würfel-Schleife, Szenenwechsel, Flags). Keine
   2-Stunden-Session einchecken; `redo`-Turns und unterdrückte (leere) Antworten fliegen
   beim Laden ohnehin raus.
3. Referenziert der Header ein gekauftes Abenteuer (z. B. `chemical_burn`), bleibt das Golden
   **lokal** (data/adventures/ ist git-ignored — auf Maschinen ohne das Abenteuer wird die
   state-Kategorie mit Hinweis übersprungen). Committbare Goldens zeigen per
   `"adventure_path": "fixtures/…"` auf ein Fixture.
4. `uv run dm-eval tests/golden/live_<datum>.jsonl` → muss **sofort** Exit 0 sein (die
   Aufzeichnung IST das heutige Verhalten). Wenn nicht: Journal-Artefakt (z. B. Turn aus
   einem Pfad ohne Replay-Felder) — Turn rausschneiden.
5. Committen. Ab jetzt ist die Datei ein Regressions-Gate: `uv run dm-eval` vor dem Merge
   von Refactor-Runden (siehe docs/conventions.md).

## Gewollte Verhaltensänderung (Goldens erneuern)

Schlägt `dm-eval` nach einer *beabsichtigten* Änderung an (neue Marker-Grammatik, anderer
Sanitizer, strengere Gates): Diff lesen, prüfen, dass **nur** die beabsichtigte Kategorie
abweicht, dann synthetische Goldens per Generator neu erzeugen bzw. Live-Goldens aus einer
frischen Session neu ziehen. Goldens nie von Hand „grün editieren" — sie sind der Kontrakt.
