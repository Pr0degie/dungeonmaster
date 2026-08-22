# progress-archive — historische Session-Logs, abgeschlossene Phasen, gelöste Open Questions

Hier liegt nur **Historie**. Der Live-Status (current focus, next step, offene Phasen,
Decision-Log, offene Fragen) steht in [`../progress.md`](../progress.md). Dieses Archiv wird
**on demand** gelesen, nicht jede Session. Nichts wird gelöscht — Inhalte werden aus
`progress.md` hierher rotiert, sobald sie nicht mehr aktuell sind.

---

## Last session (Verlauf)

_Aus `progress.md` rotiert (2026-08-22, Charakter-Akten-Runde):_

**Vierter Charakter für den Testabend (2026-08-22, D105). Kein Code geändert; Suite 778 grün, `dm-eval` Exit 0.**
Tobi braucht für die Debug-Kampagne einen Charakter für Vincent. Gebaut wurde ein Enginseer, weil die Party genau dort blind war: keiner der drei hatte Fernkampf über 24 oder Technologie über 32, und „Die Mitternachtsfracht" spielt im Hafen — Zollmanifest, Frachtlukenschlösser, ein Leichter mit Maschinengeist. Der Witz sitzt im Vox-Implantat mit Defekt (jeder fünfte Satz kommt in der viel zu fröhlichen Werksdurchsage-Stimme seiner Schmiedewelt heraus) und in der Klageschrift, in der er Maschinen, Türen und Mitspieler mit Aktenzeichen protokolliert.
- **Gegen das Profil gerechnet, nicht geschätzt:** 90 Punkte (jede Eigenschaft +4…+18), Herkunft Schmiedewelt +5 Int fest / +5 BS gewählt, sechs Steigerungen (Technologie ×2, Fernkampf ×2, Wissen ×1, Wahrnehmung ×1), Wunden = StrB 2 + 2×TghB 3 + WilB 3 = 11, drei Augmetiken ≤ Zähigkeitsbonus 3 mit exakten Katalog-Schlüsseln. Nachgeprüft mit `Character.from_dict`, `CharacterStore.get` (beide Aliase), `skill_value` (Fernkampf 51 / Technologie 53) und `seed_from_store` (vier Figuren, 11/11).
- **Deployment in ZWEI Dateien, nicht einer:** `data/sessions/1343673766487654464/characters.json` **und** `data/sessions/_default/characters.json`. Die zweite ist der Fallback für jeden Channel ohne eigene Datei (D82) — genau der Fall auf einem fremden Server. Nur die erste zu pflegen hätte den vierten Spieler auf Timos Clone stumm verschluckt.
- **Zwei Doku-Funde, die den Abend gekostet hätten:** drei Run-Dokumente (`testabend-ablauf`, `debug-campaign-runbook`, `live-run-script`) nannten die Party namentlich mit drei Namen — eine Vier-Namen-Join-Zeile wäre nach Checkliste ein Abbruchgrund gewesen. Und der Augmetik-Live-Check (D52) stand als „ruht, kein Implantat-Charakter" im Skript. Er läuft jetzt mit, mit nachgerechneter Beweiszahl: Wahrnehmung **44** statt 39, weil `augmetic_bonus` die +5 des Augur-Arrays über dessen `skills`-Liste einrechnet (`resolve_target` offline gegengeprüft).
- **Bewusst NICHT angefasst:** die bestehende `state.json` der Live-Kampagne. `seed_from_store` seedet nur einmal — sie kennt Vinzentius daher nicht, und das ist für den Debug-Run egal (der legt seinen eigenen `state.debug.json` an, ADR 056). Für die Live-Kampagne muss er später von Hand ergänzt oder der State zurückgesetzt werden; beides ist Tobis Entscheidung, nicht meine. Der Hinweis steht jetzt in `data/party/README.md`.
- **Live-unverifiziert:** alles am Charakter, was über die Rechenwege hinausgeht — dass der DM „Vinnie" am Tisch auf die Figur mappt, und dass die Augmetik-Probe im Spiel sichtbar 44 zeigt.

**Playtest-Triage nach dem ersten Debug-Abend (2026-08-15, D103 → ADR 056). Kein neues Live-Gate — der Abend erreichte keines der acht offenen, weil die Kampagne nie startete.**
Vorgeschichte in derselben Session: die Debug-Kampagne wurde committet (`7463d5c`), damit sie auf Timos Clone überhaupt läuft — Original-Content, kein Buchmaterial, drei Allowlist-Zeilen in `.gitignore`; die gekauften Kompendien bleiben lokal, vier Doku-Stellen („git-ignored, nur lokal") nachgezogen.
Fünf Commits: `7463d5c` Kampagne + Doku, `a8af5b0` Sanitize (`antworten/reagieren/erwidern/entgegnen` in den Meta-Preamble-Filter — live zweimal wörtlich vorgelesen, weil der Filter nur `beschreiben/schildern/beginnen/eröffnen` kannte; der `<verb> ich`-Anker unverändert, damit echte Erzählung durchgeht), `0ce23b7` Sandbox-Vervollständigung (`SessionRuntime.session_file()` als eine Naht für state/history/chekhov/recap mit `.debug`-Zwilling im Debug-Run + Guard gegen einen dem Abenteuer fremden Szenenzeiger beim Seed).
- **Diagnose aus dem Log, nicht aus Vermutungen:** `loaded adventure 'Die Mitternachtsfracht'` gefolgt von `loaded world state from …1343673766487654464\state.json` + `restored 20 conversation turns` — die Live-Kampagne desselben Channels. Deshalb Rokarth-Narration den ganzen Abend, kein Startpunkt, kein 🧪-Panel. ADR 055 hatte den Shared-Channel-Hazard nur für Archive und RAG-Source geschlossen.
- **Evidenz:** Suite **763 grün** (+9 Tests: `is_debug_run` an der Sidecar-Präsenz, Live- vs. Debug-Dateinamen für alle vier Artefakte, Pfadmengen disjunkt, geteiltes Verzeichnis, Turn-Append landet nur im eigenen Zwilling, Rotation behält den `.debug`-Marker und lässt die Live-Datei stehen, fremder Szenenzeiger re-seedet mit WARNING; dazu die Sanitize-Fälle inkl. Negativprobe), ruff sauber (der vorbestehende E402 in `tests/test_adventure.py` bleibt), `dm-eval` Exit 0 auf beiden Goldens. **Kein Verifier-Subagent** in dieser Runde (Harness-Vorgabe dieser Session: keine Subagents ohne Auftrag) — der Diff ist dafür klein und vollständig test-gepinnt.
- **Drei Folge-Runden am selben Tag:** `6949171` [`docs/testabend-ablauf.md`](docs/testabend-ablauf.md) (Ablauf eines Testabends: Zweitrechner-Vorbereitung, Boot-Sollbild mit Abbruchkriterien, Szene für Szene mit den Reihenfolge-Zwängen, Übergabe, Nacharbeit; Runbook bleibt Szenen-Referenz) plus die dabei gefundenen Korrekturen an `testplan.json`, Runbook und SETUP.md; `b9a7c61` Kommando-Fehlermeldung (`on_command_error` beantwortet `UserInputError` mit der Nutzungszeile aus dem Docstring — bisher sah der Tisch bei einem Tippfehler nichts; `CommandNotFound` bleibt stumm wegen des geteilten `!`-Präfix); `8b44f92` `tools/cleanup_15aug.py` + die entschiedene Bridge-Topologie (beide Bots auf Timos Rechner).
- **Vier falsche Anweisungen gefunden, die im 🧪-Panel standen:** `!npcmem Bree_Marlok` (exakter Namensvergleich — Unterstriche versteht nur `!npc add`), `!uhr neu` ohne Anführungszeichen (stirbt an der Größen-Konvertierung), vergessenes `!npc add` vor dem Kampf (warnt nicht, bietet die eigenen Mitspieler als Ziel an), Neustart ohne `!j` vor `!wrap` und ohne `!leave` danach (G9/G10 ohne Daten). Methode: Recherche- und Prüf-Workflows mit Gegenprobe, die zwei folgenreichsten Funde selbst im Code nachgesehen. Suite danach **778 grün** (+15), `dm-eval` Exit 0.
- **Live-unverifiziert:** der nächste Debug-Abend. Gate: Boot zeigt Startszene `zollhaus`, 🧪-Panel erscheint beim `!j`, `state.debug.json` entsteht, die Live-`state.json` behält ihre Änderungszeit — und kein „Als Spielleitung antworte ich" im Transkript, wenn ein Spieler einen NSC anspricht.
- **Nicht in dieser Runde, aus demselben Log:** Timos `.env` (3 unparsbare Zeilen → Keys stumm ignoriert; `TTS_SPEAKER=cuda` gehört in `TTS_DEVICE`), englische Einsprengsel („Schritte outside der Tür"), `DM_NUM_PREDICT=220` als faktische Turn-Länge (885 Zeichen = 66 s Wiedergabe, 78 % der Gesamtlatenz), die durch den Fehlstart in die Live-Dateien geschriebenen Turns dieses Abends, und die offene Frage, auf welchem Rechner Bot A für den Testabend läuft.

_Aus `progress.md` rotiert (2026-08-15, Testabend-Doku-Runde):_

**Doku-Drift-Sweep (2026-07-18): alle md-Dateien gegen den Code geprüft (3 parallele Verifier-Agents), 5 Drift-Funde, alle direkt gefixt. Kein Live-Gate, WIP-exempt.**
Zwei Commits: `0912efe` Doku-Nachzug (architecture.md: neue Memory-Schicht §7f Session-Memory + Session-Hälfte im RAG-Kapitel §8 + `.debug`-Marker + Bausteintabelle — die „nur Regelwerk/Lore/Abenteuer in RAG"-Aussage war falsch geworden; conventions.md: RAG/Memory-How-tos um `ingest_session`/Sandbox ergänzt; roadmap.md: „Long-term vector memory" als geliefert markiert [ADR 054] + 2× Embedder-Name nomic→`bge-m3`; live-run-script.md: G10-Registerzeile + Zweitsessions-Absatz, G1–G9-Zeilen unverändert), `aab52a2` ADR-Renumber (Dateinamen 019↔020 getauscht, sodass Dateiname = interner Titel: 019 = Adventure/Scene-Tracker-Hybrid, 020 = Shutdown; die ~11 dateinamens-basierten „ADR 020"-Scene-Tracker-Verweise auf 019 korrigiert [ADR 026 7×, ADR 043 2×, Archiv, author-adventure-Skill]; Refs-Zeile der Shutdown-ADR D44→D47; Erklär-Notiz in ADR 026).
- **Verifiziert aktuell (kein Fix nötig):** sämtliche im Runbook + Live-Run-Skript zitierten Beweis-Logzeilen exakt gegen den Code (inkl. `grep '"kind": "scene"'` matcht die `json.dumps`-Default-Separatoren), Lessons-Index 17/17, Skills-Index 10/10, ADR-Nummern lückenlos, `tests/golden/README.md`, SETUP/README/CLAUDE.md im Rahmen ihres bewusst hohen Anspruchs.

_Aus `progress.md` rotiert (2026-08-15, Playtest-Runde Debug-Sandbox-Artefakte ADR 056):_

**Debug-Sandbox + Gate G10 (2026-07-17, D102 → ADR 055). G10 reitet auf der G9-Zweitsession (kein zusätzlicher Live-Termin); die Sandbox schließt den Shared-Channel-Hazard, BEVOR der Debug-Run Session-RAG anfasst.**
Vier Commits, einzeln revertierbar: `79a5edd` Sandbox (`rotate()`-Marker `history.<stamp>.debug.jsonl`; Ingest-Routing allein nach Dateiname in `session_debug_<channel_id>`; `pending_files`-Catch-up modusgefiltert; Retriever-Flag `debug_sessions`; CLI `--wipe-debug <channel_id>`), `d9cd961` Catch-up-Logzeile beim `!join` als G10-Evidenz (der einzige vorher stumme Schritt — Ingest- und Treffer-Zeilen existierten schon), `d440728` Runbook additiv (Setup: `DM_SESSION_MEMORY` + Sandbox-Satz; G10-Tabellenzeile auf der G9-Session-2; Debrief-Greps inkl. ADR-053-Journal-Check; Reset: `.debug`-Cleanup + Niemals-löschen-Warnung für Plain-Archive; Sidecar-Änderung wörtlich dokumentiert), `bc3c700` ADR 055. Lokales `testplan.json`: `pier_neun` additiv um das G10-Gate + einen Hinweis-Satz ergänzt; G1–G9-Inhalte byte-identisch.
- **Evidenz:** Suite **754 grün** (+6 Tests: Rotationsmarker nur bei `debug=True`; Routing beide Richtungen per Dateiname; `pending_files` sieht nur den eigenen Modus, beidseitig; Retrieval-Isolation beidseitig; `--wipe-debug` löscht nur Sandbox-Rows inkl. Stempel, Live-Rows/FTS bleiben; ADR-052-Source-Inspection unverändert grün), ruff auf allen angefassten Dateien sauber (ein **vorbestehender** E402 in `tests/test_adventure.py`), `dm-eval` Exit 0 gegen unveränderte Goldens. **Nachtrag 2026-08-15:** die Sandbox deckte nur Archive + RAG-Source ab, nicht die laufenden Session-Dateien — genau daran scheiterte der erste Debug-Abend (→ ADR 056).

_Aus `progress.md` rotiert (2026-07-18, Doku-Drift-Sweep):_

**Session-RAG-Runde: Kampagnengedächtnis über gespielte Sessions (2026-07-17, D101 → ADR 054). KEIN neues Live-Gate (offline voll testbar, WIP-exempt); `SESSION_MAX_DISTANCE`-Livetuning reitet auf dem anstehenden Live-Run mit.**
Drei Commits, einzeln revertierbar: `b371857` Ingest (`dmbot/rag/ingest_session.py`: Szenen-Chunker über rotierte Journale mit Redo-Collapse + Größen-Fallback, stamp-idempotenter Store-Write in eigene `session_chunks_vec` + FTS5-Spiegel, `!leave`-Hintergrund-Ingest + `!join`-Catch-up/Backfill, testplan.json-Debug-Skip als Seam, CLI mit Live-Journal-Refusal, `DM_SESSION_MEMORY`), `5154d3f` Retrieval (`fetch_block(query, channel_id=…)`: hybrid KNN 0.38 + Recency-Malus + df-gegated FTS-Eigennamen-Rescue, max 2 Chunks zusätzlich zu TOP_K, Block „## Früher in der Kampagne … Status hat Vorrang", Kanal-Isolation, Buch-Pfad byte-identisch), `7c56d47` Kalibrierung (`session_recall`-Golden-Sektion + Fixture-Session + Sweep mit KNN-only-Spalte) + ADR 054.
- **Verifier-Subagent (fresh context, Diff + Golden Rules): 1 echter Bug + 4 Robustheits-Funde — alle gefixt.** Kern-Fund: vec0s `k` ist tabellen-global, der Source-Filter schneidet erst danach — geteilte `chunks_vec` hätte Session-Recall am echten Store (~1700 Buch-Chunks) ausgehungert UND den Buch-Kandidatenpool schleichend verwässert → eigene `session_chunks_vec`-Tabelle, Isolation test-gepinnt. Dazu: CLI-Refusal fürs Live-Journal, Satzanfangs-Ausschluss in der FTS-Heuristik („Vielleicht…" ist Grammatik, kein Name), kein Bare-DB-Anlegen bei leerem Journal ohne Store, `create_task`-Referenzen gehalten; selbstheilende Mirror-Inserts nach einem live gefundenen `IntegrityError` (Id-Reuse vs. stale FTS-Rows).
- **Evidenz:** Suite **748 grün** (+32 Tests: Chunker/Idempotenz/Catch-up/FTS/Budget/Schwelle/Isolation/Debug-Skip/alle Degrade-Pfade), ruff sauber, `dm-eval` Exit 0 gegen unveränderte Goldens; Kalibrierlauf gegen den echten Store: 5/5 `session_recall`-Positives (alle über die FTS-Hälfte — kurze Eigennamen-Fragen vs. Mini-Fixture liegen KNN-seitig bei 0.38–0.58, genau der Fall, für den die Hybrid-Hälfte gebaut ist), 0/5 Negativ-Leaks über den ganzen Sweep, Buch-Sektionen unverändert (recall@3 17/21 wie zuvor); End-to-End-Smoke mit echtem Ollama: CLI-Ingest 2 Chunks, Vosk-Frage liefert den richtigen Szenen-Chunk mit Label, reine Narration bleibt leer.

_Aus `progress.md` rotiert (2026-07-17, Debug-Sandbox-Runde ADR 055):_

**Journal-Runde: Szenengrenzen + Ingame-Zeit im Session-Journal (2026-07-17, D100 → ADR 053). Prep für die Session-RAG-Folgerunde (`02_session-rag.md`) — KEIN neues Live-Gate (Metadaten-only, WIP-exempt).**
Drei Commits, einzeln revertierbar: `06ed71b` Scene-Events (`_set_scene` journaliert jeden echten Wechsel als `{"kind": "scene", scene_id, ts}`; `!join` öffnet jedes Journal mit der aktuellen Szene — Start-Szenen-Seed **und** restaurierter Pointer, direkt nach dem ADR-046-Session-Header), `a14cfe3` `time_minutes` auf Turn-Records (dmcog `_autosave_turn` stempelt `WorldState.time_minutes` bei Turn-Abschluss über den `extra`-Mechanismus), `c21e8b9` ADR 053. Nichts an `load_recent`-Semantik, Redo-Collapse, Rotation oder Torn-Line-Toleranz geändert; kein RAG-Code in dieser Runde.
- **Evidenz:** Suite **716 grün** (+9 Tests: Scene-Event bei Transition + `!join`-Seed + restauriertem Pointer, Same-Scene/`autosave=off`/fremder State schreiben nichts, `load_recent` skippt Scene-Events und kollabiert Redos weiter, `time_minutes` drin + tolerant fehlend, Cog-Stempel-Pfad); ruff sauber; `dm-eval` Exit 0 — alte Goldens ohne die neuen Felder replayen unverändert.

_Aus `progress.md` rotiert (2026-07-17, Session-RAG-Runde ADR 054):_

**Content-Runde: Debug-Kampagne „Die Mitternachtsfracht“ (2026-07-11) — füllt den `testplan.json`-Vertrag aus ADR 052. KEIN neues Live-Gate (Test-Vehikel für die bestehenden 8).**
`data/adventures/debug-kampagne/` (lokal, git-ignored): `adventure.json` (6 Szenen, ein Abend, Original-Content — kein Buchmaterial), `npcs.json` (8 Statblocks, 4× `faction: kettenbund`, Kessel mit `goal_de`), `testplan.json` (jede Szene → Gates + Ein-Zeilen-Hinweis fürs 🧪-Overlay). Alle G1–G9 mit eingebauten natürlichen Triggern — Design-Details im archivierten Current-focus-Block, Tisch-Referenz im Runbook.
- **Evidenz:** `validate.py` (echter `Adventure.load`): `loaded: Die Mitternachtsfracht — 6 scenes, 8 statblocks, start='zollhaus'` / `RESULT: OK` (0 Errors/Warnings), Gate `lagerhaus -> pier_neun requires 'verladebrief'` erkannt; `Testplan.load` OK (6 Szenen), Gate-Abdeckung G1:1 G2:2 G3:3 G4:1 G5:2 G6:2 G7:3 G8:2 G9:3; alle `Fertigkeit (Schwierigkeit)`-Tokens gegen Profil-`difficulty_ladder` + Party-Skill-Union verifiziert.
- **Committet (nur getrackte Dateien):** `docs/debug-campaign-runbook.md` + Verweis-Zeile im Live-Run-Skript. Die Kampagne selbst bleibt lokal (`data/**`-Ignore, wie chemical_burn) — für Timos Maschine manuell mitkopieren.

_Aus `progress.md` rotiert (2026-07-17, Journal-Runde ADR 053):_

**🧪 Debug-Overlay-Runde (2026-07-11, D99 → ADR 052). Dev-Tooling, KEIN neues Live-Gate (WIP-exempt — die Live-Verifikation reitet auf der Debug-Kampagne, für die das Overlay existiert).**
TDD (rot zuerst): neues pures `dmbot/rag/testplan.py` (Sidecar-Loader, fail-open, `overlay_line_de`), `SessionRuntime.update_debug_overlay()` im Uhr-Panel-Muster (edit-in-place), Call-Sites `!ort` / `<<ORT>>`-Confirm / `!start`+`!intro`-Seed / `!join`, `!leave` räumt das Panel ab; Config-Knöpfe `DM_DEBUG_OVERLAY` + `DM_DEBUG_CHANNEL` (+ `.env.example` für die dm-sync-Deckung).
- **Verifier-Subagent (fresh context; Diff + ADR 026/047 + Golden Rules): kein Blocker.** Übernommen: stärkerer Invisibility-Pin (in `dmbot/` dürfen nur runtime/config die Sidecar überhaupt erwähnen — fängt auch `_testplan`-Attributzugriffe, nicht nur Imports) + das `!join`-Overlay vor die Bottom-Panels (Mic-Button bleibt unten). Bewusst gelassen: das Doppel-Post-Race der zwei Szenen-Pfade (byte-identisch mit dem akzeptierten Uhr-Panel-Race, ADR 047).
- Evidenz: Suite **707 grün** (+18 Tests; 1 bestehender `!ort`-Test um den Overlay-Pin erweitert), ruff-F sauber, `dm-eval` Exit 0 gegen unveränderte Goldens.

_Aus `progress.md` rotiert (2026-07-11, Content-Runde Debug-Kampagne):_

**Live-Gate-Triage: `docs/live-run-script.md` (2026-07-11, Workflow-Migration Runde 5/5 — die letzte). Doc-only, KEIN neues Live-Gate — der nächste Schritt ist der Spieltisch, keine Build-Runde.**
Alle 8 offenen Gates + Tuning-/Sekundär-Checks aus progress.md, Archiv und der alten Checkliste sind in EIN Abend-Drehbuch + kurze Folge-Session gemerged: Gate-Register nach Setup-Kosten (G1–G9), Pre-Flight, 11 Akte, exakte Beweis-Logzeilen pro Gate — per Code-Sweep (Explore-Subagent über Cogs/Delivery/Runtime) verifiziert statt aus der Doku zitiert.
- **Checklisten-Korrekturen aus dem Sweep:** der Psioniker der aktuellen Party ist **Fridolin**, nicht Rektalus; es gibt kein `!pause`-Command (Pause = Esc/⏸-Button); die Gated-Exit-Ablehnung heißt `🚫 Ausgang '…' → '…' verriegelt — Bedingung '…' nicht erledigt`; der Augmetik-Check (D52) ruht, bis ein Implantat-Charakter in der Party ist.
- **Pre-Flight vorgezogen:** `.env` um die 4 fehlenden Gate-Kill-Switches ergänzt (`DM_CONSISTENCY_GUARD`, `DM_NPC_MEMORY`, `DM_NPC_MEMORY_TOP_K`, `DM_SCENE_TIME_ADVANCE`) — `uv run dm-sync` meldet wieder 42/42; das Soll-Bild steht im Skript. Für die Gossip-Kür fehlt noch der `faction`-Seed in `npcs.json` (kein NSC trägt eine — Pre-Flight #5, Tobi am Abend).
- **Doku-Konsolidierung:** `live-test-checklist.md` → Redirect-Stub; der gemergte Gate-Fahrplan aus `## Next concrete step` verbatim ins Archiv; Lesson-Verweis (`one-variable-per-live-run`) + die in Runde 4 offen gelassene tdd-Zeile im Skills-Index nachgezogen.

_Aus `progress.md` rotiert (2026-07-11, D99 Debug-Overlay-Runde):_

**Roadmap-Tabellen-Ersatz + Skill-Sweep (2026-07-11, Workflow-Migration Runde 4/5). Doc/Skill-only, KEIN neues Live-Gate.**
Für den Spieltisch ändert sich nichts — die Runde entfernt totes Gewicht aus den Doks: die phasenindexierte Modell-Tabelle in `roadmap.md` (samt RETIRED-Marker) ist durch einen 9-Zeilen-Effort-first-Block (Fable 5) ersetzt; der stale Tabellen-Verweis in `CLAUDE.md` ist raus.
- **Skill-Sweep (konservativ, De-Präskription):** Golden-Rules-Nacherzählungen → Pointer auf CLAUDE.md (playtest-triage, grill-me, improve-architecture), Prior-Model-Framing gestrichen (grill-me, tdd), Rotations-Mechanik-Duplikat → session-ritual-Pointer (playtest-triage), tote „until the State header exists"-Klammer im session-ritual-Handshake gelöscht. Alle Gates, Confirm-Stops (Scene-Cut, TDD-red-first, Character-Merge) und Gotchas unangetastet.
- **Unverändert (alles KEEP-Kategorie):** author-adventure, character-build, rag-ingest, rules-subsystem, to-prd. Diffstat: roadmap −29, playtest-triage −7, grill-me −5, improve-architecture −3, session-ritual −3, tdd −1, CLAUDE.md −2 Zeilen netto.
- **Offen für Runde 5:** die tdd-Zeile im `.claude/skills/README.md`-Index trägt noch Prior-Model-Framing (bewusst nicht angefasst — der Index lädt nicht in den Arbeitskontext).

_Aus `progress.md` rotiert (2026-07-11, Live-Gate-Triage-Runde 5/5):_

**Lessons-Memory-Runde: `docs/lessons/` angelegt (2026-07-11, Workflow-Migration Runde 3/5). Doc-only, KEIN neues Live-Gate.**
Für den Spieltisch ändert sich nichts — die Runde verhindert, dass teuer gelernte Korrekturen jede Session neu entdeckt werden: **16 Lessons + README-Index** als neue Memory-Schicht (ADRs halten Entscheidungen; Lessons halten wiederkehrende Korrekturen und bestätigte Vorgehensweisen — z. B. „deterministic guards over persona hopes", das Request/Validate-Feature-Template, die zwei stillen Budgets ctx/chars).
- **Mining:** 3 parallele Subagents über `docs/progress-archive.md`, ADRs 001–051 und Decision-Log/Open-Questions; Kandidaten gegen CLAUDE.md-Gotchas/`docs/conventions.md`/Skills dedupliziert — bereits Abgedecktes verworfen („inspect a real chunk", Resample-Klasse, Plot-State-nicht-in-RAG, XTTS-Trade-off), Überschneidendes gemerged (16 Files aus ~20 Kandidaten).
- **Verdrahtung CLAUDE.md:** Session-Start-Schritt 4 = Lessons-README skimmen (Einzel-Lessons on-demand, neue Tabellenzeile); neues „While working"-Bullet: Korrekturen sofort als Lesson erfassen (bestehende updaten statt duplizieren, widerlegte löschen, nichts doppeln was CLAUDE.md/conventions/ADR schon hält); Repo-Layout-Zeile; tote „until the State header exists"-Klammer entfernt.
- **Offen für Runde 4:** der `session-ritual`-Skill spiegelt noch die alte 3-Schritt-Leseordnung (bewusst nicht angefasst — der Skill-Redundanz-Sweep ist die nächste Runde).

_Aus `progress.md` rotiert (2026-07-11, Roadmap-Tabellen/Skill-Sweep-Runde):_

**Doc-Diet-Runde: State header + progress.md-Diät (2026-07-11, Workflow-Migration Runde 2/5). Doc-only, Suite 689 grün als Tripwire, KEIN neues Live-Gate.**
Für den Spieltisch ändert sich nichts — die Runde macht den Session-Start billiger: `progress.md` trägt jetzt einen **`## State header`** (≤ 25 Zeilen, die einzige Pflicht-Lektüre aus dieser Datei laut CLAUDE.md-Ritual).
- **Rotation:** `## Current focus` auf die 2 neuesten Blöcke (D98/D97) gekürzt; die Blöcke D82–D96 und D74-und-älter (bis Phase 9) verbatim per Slice-Skript ins Archiv (`## Current focus (Verlauf)`, chronologisch einsortiert).
- **Decision-Log-Diät:** alle 55 langen Zeilen mit `→ ADR`-Link auf „was + Ein-Satz-Warum + → ADR NNN" gekürzt; Zeilen-Detail, das der ADR nicht schon hielt, vorher als append-only **„Addendum — detail preserved from decision log D#"**-Sektionen in 27 ADRs gerettet (~30 Addenda). Zeilen ohne ADR-Link (26 Stück) bewusst unangetastet (exempt — ihre Rationale hat kein anderes Zuhause).
- **Verifiziert (moved ≠ deleted):** 3 read-only-Audit-Pässe — Rotation byte-identisch (Archiv nur Einfügungen), Detail-Erhalt aller 55 Zeilen (ein Fund: `skill_value`-Mechanik von D61 #9 → in ADR 030 nachgetragen), Struktur-Sweep (ADR-Diffs append-only, exempt-Zeilen byte-identisch, D-Nummern-Menge unverändert). Suite 689 grün.
- **Stand:** progress.md 854 → 579 Zeilen (~52k → ~30k Tokens); über dem 400-Zeilen-Ziel bleiben das lebende Live-Run-Drehbuch in `## Next concrete step` + die exempt No-ADR-Zeilen (laut Regel akzeptiert — Token-Bulk war der Hebel). Alte Open Question „Aufräum-Pass progress.md" (D82–84) damit ✅ (Volltext im Archiv).

_Aus `progress.md` rotiert (2026-07-11, Lessons-Runde):_

**Cleanup-Runde: Marker-Pipeline auf die `MarkerSpec`-Registry konsolidiert + Doku-Sweep (2026-07-04, D98 → ADR 051). Suite 689 grün (+6 neue Registry-Tests, 0 Änderungen an bestehenden Tests), ruff-F sauber, `uv run dm-eval` Exit 0 gegen die unveränderten Goldens — nach JEDEM Migrationsschritt. Verhaltensneutral, KEIN neues Live-Gate.**
- **Teil A — die Registry (`dmbot/rules/marker.py`):** `MarkerSpec{kind, keyword, extract (normalisierte Signatur), needs_profile, suppressible}` × 6 in `MARKER_SPECS`; Tabellen-Reihenfolge ist load-bearing (= Extraktions- UND `markers.*`-Journal-Key-Reihenfolge, per Test gepinnt). `extract_all(text, profile)` kettet die **bestehenden** Extraktoren in exakt der historischen Reihenfolge (byte-identisch per Konstruktion, Paritätstest gegen die handgeschriebene Kette; ohne Profil bleiben TEST/MANIFEST im Text — das alte Guard-Verhalten). `empty_markers()` = das `{kind: []}`-Skelett.
- **Teil A — die Nähte:** `finalize_answer_markers → (answer, {kind: requests})` ist die kanonische Post-Processing-Naht (Batch + `StreamAssembler.finish` — ADR-017-Parität by construction); `finalize_answer` bleibt als 7-Tupel-View (test-gepinnt, ~10 Testdateien unangefasst). `StreamResult{remaining, answer, markers}` mit `__getattr__`-Back-Compat (`res.uhr` etc. lesen `markers[kind]`); `_body` strippt über `extract_all`. Brain: **ein** keyed Store `_pending[kind]` (die Alt-Attribute `_pending_<kind>` sind lebende Aliase der inneren Dicts — `test_clocks` pokt `_pending_uhr` direkt), `_queue_markers` (geteilt von Batch+Stream; Suppression liest `spec.suppressible` — UHR/ZEIT exempt wie gehabt), `_drop_pending` (redo/redo_streaming/reset), Consistency-Snapshot/-Restore als Dict-Loops, generisches `take_pending(kind)` + die sechs Wrapper als öffentliche Surface (dicecog, die test-gepinnten getattr-Guards der Delivery-Handler, dm-eval). Delivery: beide Pfade spawnen die vier Proposal-Handler über EIN labelled `_marker_proposal_tasks` (+ `_await_turn_tasks` statt der 5-Parameter-Signatur); `eval_replay` leitet `_MARKER_KEYS` + den Replay-Drain aus der Registry ab.
- **Bewusst NICHT generalisiert (ADR 051 #5):** die Handler-Bodies (ORT first-request-only + `resolve_move`, ERLEDIGTs load-bearing Guard-Reihenfolge, UHRs Race-Recheck + Panel-Update, ZEITs first-valid + async Apply), die puren Verdicts (bleiben in `delivery.py` — die EINE Quelle für Handler + dm-eval; `rules/` darf nicht `voice/` importieren) und das profilgetriebene TEST/MANIFEST-Parsing. Ein sechster Marker kostet jetzt: Dataclass + Extraktor + eine Registry-Zeile + sein eigentliches Feature (Handler/View/Verdict/Persona) — Tupel, StreamResult, Pending-Store, die vier Lifecycle-Nähte, Journal-Dict und dm-eval-Keys ändern sich nicht mehr.
- **Vorgehen + Gates:** Registry + `extract_all` NEBEN dem Bestand (Commit), dann die Finalize/Stream-Naht in einem Schritt (dichte Marker-Unit-Tests + dm-eval `answer`/`marker` decken sie), dann die Pending-Nähte **einzeln** ZEIT→UHR→ERLEDIGT→MANIFEST→TEST→**ORT zuletzt** — Suite + `ruff --select F` + `uv run dm-eval` grün nach jedem Schritt (der Filter „kind im Store?" verschwand mit dem letzten Umzug von selbst). Journal-Kontrakt unangetastet: `markers.*`, `*_verdicts`, `lines`/`results`/`notes` byte-kompatibel, alte Goldens replayen ohne Anpassung.
- **Teil B — Doku-Sweep:** README-Intro auf den echten Stand („Persistent memory … are next" ersatzlos; neue „What the DM keeps track of"-Liste: NPC-Gedächtnis, Agenden, Konsistenz-Wächter, Uhren, Ingame-Zeit/Fristen, Chekhov, dm-eval — je ein Satz); progress-Rotation per Slice-Skript (Current-focus-Blöcke D75–D81 + die ERLEDIGT-Next-step-Blöcke des D60–D63-Verlaufs verbatim ins Archiv, neue „(Verlauf)"-Sektionen, die drei „gehört ins Archiv"-Hinweise raus); `logsetup._short_name`-Docstring nennt jetzt `voice.delivery` (D60-Kosmetik erledigt); Open questions: D94-Marker-Debt als eingelöst markiert (Volltexte im Archiv); `rules-subsystem`-Skill um den `MARKER_SPECS`-Zeilen-Schritt ergänzt.

_Aus `progress.md` rotiert (2026-07-11, Doc-Diet-Runde):_

**Chekhov-Liste: lose Fäden + Callbacks (2026-07-04, D97 → ADR 050). Suite 683 grün (+24), ruff-F sauber, `dm-eval` Exit 0, live-unverified.**
Ziel: unaufgelöste Details einer Session überleben und kommen später als Callback zurück — das LLM schreibt die Prosa, Code verwaltet die Liste (Cap/Dedupe/Status/Verdrängung; das Recap-/ADR-044-Narrativ-Muster, golden rule #3 dem Geist nach).
- **Schema + Persistenz (`dmbot/memory/chekhov.py`, pure — kein Discord/LLM/Runtime):** `ChekhovThread{id (sequenziell t1, t2 …), detail (1 Satz, 200-Zeichen-Trunkierung), origin_scene, created_session (ISO-Datum), status open|resolved, weight 1–3}` in `ChekhovList` → `data/sessions/<id>/chekhov.json` (atomar, temp + `os.replace` wie `state.json`; fehlende/kaputte Datei = leere Liste, blockiert nie). Cap 20 offene (Verdrängung: ältester mit dem niedrigsten vorhandenen Gewicht), Aufgelöste FIFO-gedeckelt auf 20. Dedupe `is_similar` (normalisiert: Substring ODER Wort-Jaccard ≥ 0.6) gegen ALLE Fäden — ein aufgelöster kommt nicht als „neu" zurück.
- **Extraktion (nur `!wrap`, ein Call):** `request_extraction` bekommt optional `chekhov_section` → Schema-Variante `EXTRACT_SCHEMA_CHEKHOV` (`chekhov: {new: [{detail, weight}], resolved: [ids]}`, required), System-Zusatz `prompts/chekhov_extract_de.md`, `num_predict` 800→1000. **Fenster-Fix:** `extract_npc_memories(include_chekhov=True)` baut die Sektion aus offenen Fäden (nummeriert, für Auflösungs-Erkennung) + dem Verlauf VOR dem Extraktions-Fenster als markiertem „nur für Fäden — keine NSC-Erinnerungen"-Block (der Wrap-up-Call sähe sonst nur die letzte Szene; NSC-Semantik bleibt fensterbezogen, Überreichweite fangen Gist-Dedupe/±1-Clamp). `apply_chekhov` defensiv (kaputte Payload = No-op): erst `resolved` flippen (unbekannte ID → Log), dann max. 5 neue durch den dedupenden, gedeckelten `add_thread`. Early-Return angepasst: Chekhov extrahiert auch ohne Szenen-Fenster/NSC-Kandidaten, solange die Session Verlauf hat.
- **Injektion:** `chekhov_block_de(top_open(3))` (Gewicht absteigend, dann älter zuerst; `(wichtig)` bei Gewicht 3, keine IDs im Prompt) reitet als „## Lose Fäden (… nicht erzwingen)" am Weltzustand-Block (`_persist_and_refresh`, neben Psyker/Augmetik); Persona-Bullet in `prompts/dm_core_de.md` (EINEN aufgreifen wenn er sich natürlich fügt, kein Fremdkörper, Liste nie wörtlich erwähnen).
- **Commands (neuer dünner `dmbot/voice/chekhovcog.py`, TimeCog-Muster):** `!fäden`/`!faeden` (offen + aufgelöst, mit IDs/Gewicht/seit), `!faden neu "<Detail>" [1-3]` (Mensch-Autorität; macht das Zwei-Session-Gate ohne Voll-Extraktion testbar), `!faden erledigt <id>`, `!faden weg <id>` — sofort angewendet, persistiert + Prompt-Refresh. Runtime: `chekhov_list(cid)` lazy-load + `save_chekhov(cid)`.
- **Tests (+24: `tests/test_chekhov.py` 18 + `tests/test_chekhov_commands.py` 6):** Roundtrip + atomar (kein `.tmp`-Rest), kaputte Datei, Weight/Status-Clamp, Cap-Verdrängung (weight-1 + Fallback niedrigstes Gewicht), Resolved-FIFO, Dedupe (Substring/Wortmengen, offen UND aufgelöst), Resolve-Übergang (case-tolerant, idempotent), Top-3-Ordnung, Apply (resolve-dann-add, 5er-Cap, Garbage-Payloads, Dedupe), Sektion-Builder, Prompt-Block, Schema/Prompt-Switch im Call, Command-Pfade. **Scope-Grenzen (ADR 050):** keine Extraktion pro Szene, kein Zwangs-Verweben in jede Antwort, keine Quest-Duplikate.

**NPC-Agenden: `goal` + `agenda_log` + Extraktor-Erweiterung (2026-07-03, D96 → ADR 049). Suite 659 grün (+24), ruff-F sauber, `dm-eval` Exit 0, live-unverified.**
Ziel: die Welt lebt offscreen — wichtige NSCs verfolgen ein Ziel zwischen den Szenen, ohne Welt-Simulator, ohne zweiten LLM-Call, ohne harte Mutationen aus LLM-Prosa (golden rule #3).
- **Schema (`dmbot/memory/state.py`):** `AgendaStep{ts_ingame, text}` (omit-when-empty) + am `Combatant` `goal: str` und `agenda_log` mit `add_agenda_step` (**FIFO-Cap 10** — Timeline, kein Wichtigkeits-Pruning wie bei memories); `add_or_update_npc(goal=…)`. Alte `state.json` lädt unverändert. `AdventureNpc.goal_de` (Autorendaten, optional) wird wie `faction` bei `!npc add` UND bei Extraktor-Registrierung kopiert + auf Alt-States nachgezogen.
- **Extraktor (`dmbot/memory/npc_memory.py` + `prompts/npc_memory_extract_de.md`):** derselbe Szenenwechsel-Call (ADR 044) — Schema um `agenda_step: string` erweitert; `build_extract_user` rendert pro Agenda-NSC `Ziel:` + letzte **2** Schritte und vorn `Aktuelle Ingame-Zeit:` (ADR 048, `render_time_de` — Runtime reicht sie durch); Prompt-Regel: nur für NSCs mit `Ziel:` (auch abwesende), kleine konkrete Bewegungen, betrifft keine Spielfigur, tötet/teleportiert niemanden. `apply_extraction`: **max. 1 Schritt pro NSC pro Call** (Duplikat-Einträge verworfen), ziellos/tot/PC → verworfen + Log, Text auf `GIST_MAX_CHARS` gestutzt, `ts_ingame` = durchgereichte Ingame-Zeit. Defensive wie gehabt (Parse-Fail → skip, blockiert nie).
- **Injektion:** `npc_memory_block_de` rendert Agenda-NSCs auch **ohne** Erinnerungen (`Ziel:` + letzte **3** Schritte als `- (offscreen, Tag 1, 04:00) …`, Header erklärt offscreen); `world_state_summary_de` bekommt eine `Agenden`-Zeile für alle **lebenden** Agenda-NSCs (`Vex → Ziel (zuletzt: …)`, Anweisung: über Gerüchte/Spuren andeuten, wenn abwesend) — so ist Bewegung auch spürbar, wenn der NSC nicht da ist.
- **Commands (DiceCog, neben `!npcmem`):** `!agenda <NSC> "<Ziel>"` (Anführungszeichen tolerant gestrippt) / `!agenda <NSC> weg` (Log bleibt erhalten) / `!agenden` (Ziele + letzte 3 Schritte, tote markiert); Warnung ab dem 6. Agenda-NSC (2–5 gedacht, Mensch bleibt ungeklemmt — ADR-048-Argument). Kein neuer Cog, kein neuer Env-Knopf (`DM_NPC_MEMORY=0` schaltet alles ab).
- **Tests (+24, `tests/test_agenda.py`):** Roundtrip + omit-when-empty + Alt-State, FIFO-Cap, Extraktor-Input (Ziel/letzte-2/Zeit, ziellos ohne `Ziel:`-Zeile), Schema-Feld, Apply (Schritt + ts, Duplikat-Clamp, ziellos/tot verworfen, fehlendes Feld ok, Trunkierung, Statblock-Registrierung + Backfill), Rendering (goal-only-Block, letzte 3, Weltzustand-Zeile lebend/tot), alle Command-Pfade. **Scope-Grenzen (ADR 049):** kein Welt-Simulator, keine Fraktions-Agenden, keine harten Mutationen aus Schritten, kein zweiter Call.


**Ingame-Zeit: Minuten-Zähler + `<<ZEIT>>`-Marker + Fristen + Druck-Panel (2026-07-03, D95 → ADR 048). Suite 635 grün (+62), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.**
Ziel: `time_ingame` (toter Freitext, `set_time` hatte null Aufrufer) wird ein Werkzeug — code-owned Zeitfortschritt, Fristen mit Restzeit im Prompt, bespielbare Tagesphase (golden rule #3, das ADR-043/047-Muster).
- **Zeitmodell (`dmbot/memory/gametime.py`, pure + `state.py`):** `time_minutes: int` seit Tag 1, 00:00 ist das Modell (Start 480 = Tag 1, 08:00); Rendering abgeleitet (`render_time_de` „Tag 2, 14:30", `day_phase_de` Morgen 05–11/Tag 11–17/Abend 17–22/Nacht 22–05, `next_morning`, grobe `remaining_de` „noch ~1 Tag"). `time_ingame` bleibt als **gerenderter Spiegel** (ein Schreiber: Code; nie zurückgeparst); **Migration:** State ohne Zähler startet bei Tag 1, 08:00 + Log, Legacy-Prosa bleibt als Anzeige bis zum ersten Advance. `parse_duration_de` tolerant (m/min/minuten, h/std/stunden, Dezimal, `+` optional), von Marker UND Commands geteilt.
- **Schema:** `Deadline{id, label, due_minutes, notified}` + `WorldState.deadlines` (omit-when-empty, `notified` gelatcht + persistiert → Ablauf-Hinweis feuert exakt einmal, übersteht Neustart), Slug-Ids via `slugify_clock_id` (Fallback-Param). Mutatoren `advance_time` (vorwärts-only, rendert den Spiegel, sammelt frisch abgelaufene Fristen) / `add_deadline`/`remove_deadline`/`find_deadline` (case-tolerant, Numerik-Dedup). `set_time` (tot) entfernt.
- **Marker-Pfad:** `<<ZEIT +30m>>`/`<<ZEIT +4h>>` gespiegelt an jeder UHR-Naht — `extract_zeit` (ZeitRequest mit geparsten Minuten), `finalize_answer` 6→7-Tupel + `StreamResult.zeit` + Partial-Strip, `_pending_zeit` (redo/reset/Consistency-Snapshot erweitert), Drain `_handle_zeit` als fünfte Delivery-Task (beide Pfade). **Pure `delivery.zeit_verdict`:** nur der **erste** valide Marker pro Turn (ORT-Regel — Zeitfortschritt ist nicht idempotent, anders als Flags/Ticks) und **Clamp +12h** (Überschuss geklemmt statt verworfen — die Richtung „viel später" bleibt erhalten; 0/negativ → rejected, Zeit läuft nie rückwärts). Confirm-Button `ZeitView` (discord_ui/zeit.py) unter demselben `DM_FLAG_CONFIRM`; wie UHR von der Results-only-Suppression **ausgenommen** (Konsequenz-Turn = kanonischer Advance-Moment, keine Schleifengefahr).
- **Runtime + Commands:** ein Mutator `runtime._advance_time` (advance → `[Regie]`-Note pro frisch abgelaufener Frist via `add_gm_note` → persist → Prompt-Refresh → Panel) für `!zeit`, Marker-Confirm/Auto UND `advance_scene_time` (Default **+30 min** pro echtem Szenenwechsel — `!ort` + bestätigter `<<ORT>>`, nicht der Start-Seed; `DM_SCENE_TIME_ADVANCE`, 0 = aus). Neuer dünner **`dmbot/voice/timecog.py`** (ADR-039-Abwägung: nicht ClockCog — beides Druck, aber getrennter State): `!zeit` / `!zeit +6h` (ungeklemmt, der Mensch ist die Autorität) / `!zeit tag` / `!frist neu|weg` / `!fristen`.
- **Prompt + Panel:** `world_state_summary_de` rendert `Zeit: Tag 1, 23:00 (Nacht)` **immer** (Zeit ist jetzt immer ein harter Fakt — der eine Alt-Test angepasst) + `Fristen: [id] Label — noch ~2 Std`/`ABGELAUFEN`; das Uhren-Panel ist jetzt das **Druck-Panel** `pressure_panel_de` (🕐-Zeit-Header + ⏳-Fristen + Uhren-Block, edit-in-place, zeigt bei Uhren ODER Fristen). Persona-Absatz in `prompts/dm_core_de.md` (Tagesphase bespielen, `<<ZEIT>>` bei spürbar vergehender Zeit, max. 1 Marker/Beitrag, Fristen erzählerisch anmahnen, `[Regie]`-Ablauf ausspielen).
- **Replay/dm-eval (ADR 046 kompatibel):** `_markers_dict` + Journal um `zeit` erweitert (wie uhr auch bei Suppression aufgezeichnet), Pipeline notiert `zeit_verdicts`, dm-eval re-validiert sie (pure, braucht keinen State) — **alte Goldens replayen grün** (verifiziert, Exit 0). `.env.example` (`DM_FLAG_CONFIRM`-Kommentar + `DM_SCENE_TIME_ADVANCE`), `architecture.md` §7 (Zeit-Absatz, State-Sketch, Journal-Felder).
- **Tests (+62):** `test_gametime.py` (Dauer-Grammatik inkl. Garbage/0/negativ, Rendering, Phasen-Grenzen, next_morning-Kanten, Restzeit, Notiz-Rahmung), `test_zeit_marker.py` (Grammatik inkl. Glue/kaputt, Finalize, Streaming-Split + Parität), `test_time_state.py` (Roundtrip, Omit-when-empty, **Migration alter States**, Ablauf feuert exakt einmal, Summary/Panel), `test_zeit_delivery.py` (`zeit_verdict`-Regeln, First-only+Clamp, Confirm/Auto, `_advance_time`-Note exakt einmal, Stub-Brain-Guard, Scene-Default an/aus). **Scope-Grenzen (ADR 048):** kein Kalender/Imperiale Datierung (nur ADR-Notiz), keine harte NPC-Verfügbarkeit aus der Phase (Agenden-Runde), keine Reisezeit-Tabellen.


**Consequence Clocks: `<<UHR>>`-Marker + ClockCog + Panel (2026-07-03, D94 → ADR 047). Suite 573 grün (+38), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.**
Ziel: Fortschrittsuhren à la Blades in the Dark — die Welt bekommt sichtbaren Druck, ohne dass das LLM je Uhr-Zustand schreibt (golden rule #3, exakt das ADR-043-Muster).
- **Schema (`dmbot/memory/state.py`):** `Clock{id, name, size (4|6|8), filled, visible=True}` + `WorldState.clocks` (omit-when-empty; alte `state.json` lädt unverändert; `from_dict` tolerant: filled geklemmt, kaputte size degradiert). Ids sind Marker-sichere Slugs (`slugify_clock_id`: DE-Transliteration, nie `-`/`_`-final — das Glued-Marker-Strip-Set, ADR 043) mit Numerik-Suffix-Dedup. Helfer `find_clock` (case-tolerant) / `add_clock` / `remove_clock` / `tick_clock` (nie über size; volle Uhr nicht tickbar) / `untick_clock`; pure Render-Helfer `clock_segments` (◉◉◉○○○) / `clock_line_de` (`[id] Name 3/6 — VOLL`) / `clocks_panel_de` / `clock_full_note_de`.
- **Marker-Pfad:** `<<UHR id>>` gespiegelt an jeder ERLEDIGT-Naht — `extract_uhr` (rules/marker.py, Glue-Tolerenz), `finalize_answer` 5→6-Tupel + `StreamResult.uhr` + Partial-Strip im Assembler, `_pending_uhr`-Queue im Brain (redo/reset/Consistency-Snapshot alle erweitert), Drain `_handle_uhr` als vierte Delivery-Task (beide Pfade). Validierung per **pure `delivery.uhr_verdict`** (unbekannt/Duplikat/voll/garbled → rejected) = der **+1-pro-Uhr-pro-Turn-Clamp**; Confirm-Button `ClockView` (discord_ui/clock.py, FlagView-Spiegel) unter demselben `DM_FLAG_CONFIRM`-Knopf, `=0` wendet direkt an. **Bewusste Abweichung (ADR 047):** UHR ist von der Results-only-Marker-Suppression **ausgenommen** — der Post-Roll-Konsequenz-Turn ist der kanonische Tick-Moment, Schleifengefahr null.
- **Volle Uhr → injizierte Konsequenz:** `runtime._tick_clock` (der eine Mutator für `!uhr tick` + Marker-Pfad) reiht beim Füllen eine One-Shot-**GM-Notiz** ein (`DMBrain.add_gm_note`); `_prepare_turn` draint sie NACH dem Leer-Turn-Guard als `[Regie]`-Zeile in die nächste User-Msg (Cap-exempt, Replay-Feld `notes`). `!uhr zurück` von voll zieht eine noch nicht gefeuerte Notiz zurück (`discard_gm_notes`, verlässt sich auf die „…“-Rahmung von `clock_full_note_de`). Die volle Uhr rendert überall VOLL und bleibt bis `!uhr weg`.
- **Sichtbarkeit:** edit-in-place-Panel `runtime.update_clock_panel` (Pause-Panel-Muster, `_clock_panel`-Handle, `!leave` räumt ab, kein Spam — `!uhren` re-ankert es unten); `Uhren (Druck/Fortschritt):`-Zeile in `world_state_summary_de`; Persona-Bullet in `prompts/dm_core_de.md` (nur gelistete IDs, Konsequenz aus Aktion/Fehlschlag, max. 1 Tick/Uhr/Beitrag, Zählerstand nie nennen, `[Regie]`-Voll-Hinweis ausspielen). Commands im neuen dünnen **`dmbot/voice/clockcog.py`** (ADR-039-Abwägung im ADR: nicht SceneCog — Uhren sind nicht abenteuer-gebunden; nicht DiceCog — keine Würfel).
- **Replay/dm-eval (ADR 046 kompatibel):** `_markers_dict` + Journal um `uhr` erweitert (uhr wird auch bei Suppression aufgezeichnet), Turn-Records tragen `notes`, Pipeline notiert `uhr_verdicts`; dm-eval re-feedt Notes, re-validiert Uhr-Verdikte gegen `state_before` (braucht kein Abenteuer) — **alte Goldens replayen grün** (verifiziert, Exit 0). `.env.example`-`DM_FLAG_CONFIRM`-Kommentar, `architecture.md` §7 (Clocks-Absatz + Journal-Felder), CLAUDE.md-Layoutzeile.
- **Tests (+38):** `test_clocks.py` (Roundtrip, Slug, tick/untick, Render, Summary, GM-Notes inkl. Leer-Turn-Überleben + Reset), `test_uhr_marker.py` (Grammatik inkl. Glue/leer, Finalize, Streaming-Split + Parität), `test_clock_delivery.py` (`uhr_verdict`-Regeln, Confirm/Auto, Clamp, Voll-Note exakt beim Füllen, Untick-Retract, Panel edit-in-place, Stub-Brain-Guard), `test_clock_commands.py` (alle `!uhr`-Pfade). **Scope-Grenzen (ADR 047):** keine verdeckten Uhren in der UI, keine LLM-Uhr-Erzeugung, keine Abenteuer-Schema-Uhren, keine verketteten Uhren.

**Replay-Eval-Harness: Golden-Transcripts + `uv run dm-eval` (2026-07-03, D93 → ADR 046, Dev-Tooling). Suite 535 grün (+19), ruff-F sauber, `dm-eval` Exit 0 gegen beide Goldens.**
Ziel: messbar machen, ob Refactors das Verhalten der deterministischen Maschinerie ändern — aufgezeichnete Sessions deterministisch replayen, LLM gemockt.
- **Autosave → Replay-Journal (abwärtskompatibel):** `history.jsonl` trägt jetzt pro `!join` einen `{"kind":"session"}`-Header (Profil/Abenteuer/Szenen-Modus) und pro Turn optionale Replay-Felder: strukturierte `lines`+`results` (aus `_prepare_turn`, post-Cap), `raw` (die Roh-LLM-Antwort der **behaltenen** Antwort, Marker intakt — Echo/Consistency-Retry überschreibt via `_chat_once`), `markers` (was der Turn queue-te; Results-only-Suppression = leere Listen), `router` (Action/Skills + Roh-JSON + geparste Entscheidung, via `DMBrain.last_router` → DiceCog-Note), `state_before` (WorldState-Snapshot vor den Marker-Handlern, beide Delivery-Pfade) + `scene_verdict`/`flag_verdicts` (aus `_handle_scene`/`_handle_erledigt`; Flag-Regel in die **pure** `delivery.erledigt_verdict` extrahiert — eine Quelle für Cog und Harness). Sammelmechanik: Brain-Capture (`take_replay_turn`) + Runtime-Notizen (`replay_note`/`take_replay_notes`, getattr-defensiv für Stub-Runtimes), gemergt in `_autosave_turn` (`append_turn(extra=…)`, Kern-Keys gewinnen). `load_recent` (D41-Crash-Restore) ignoriert alles davon — 2 neue Kompat-Tests.
- **`dmbot/tools/eval_replay.py` (`uv run dm-eval`, D90-Muster):** Golden laden (strikt: kaputtes JSON / fehlender Header / Turn ohne `raw` → sauberer `TranscriptError` + Exit 2; tolerant: `redo` gefaltet wie beim Restore, unterdrückte Leer-Turns übersprungen) → frischer `DMBrain` mit **`PlaybackClient`** (gibt die aufgezeichneten Roh-Antworten in Call-Reihenfolge zurück; batch-only) → pro Turn Ist/Soll-Diff in sechs Kategorien: `turn` (User-Msg-Komposition inkl. `[Würfel]`-Zeilen/Roll-Direktive), `answer` (Sanitizer), `marker` (inkl. Suppression), `router` (`classify_test` mit Playback des Roh-JSON), `state` (Szenen-Move-Gate + Flag-Validierung, re-validiert gegen `state_before` — numerische Mutationen bewusst außen vor, ADR 046), `llm` (Call-Buchhaltung: unverbrauchte/fehlende Antworten). Report im `dm-sync`-Stil (`[eval] DIFF Turn n kategorie: Soll … → Ist …`), fehlendes Abenteuer degradiert zu Hinweis statt Fehler (live gezogene Goldens mit gekauftem Abenteuer bleiben lokal nutzbar).
- **`tests/golden/`:** `dice_flow.jsonl` (Marker-Parse, Router ja/nein, Results-only-Suppression) + `scene_flags.jsonl` (legaler Move + valides Flag / gegated + unbekannt → rejected, gegen `fixtures/mini_adventure/` — eigenes Mini-Abenteuer, keine Buch-Inhalte). Beide über den **echten Capture-Pfad** generiert (`generate_synthetic.py` — der Bless-Schritt bei gewollten Verhaltensänderungen: neu erzeugen, `.jsonl`-Diff absegnen) + README (Live-Golden ziehen: rotiertes Journal kopieren → kürzen → `dm-eval` muss sofort Exit 0 sein → committen).
- **Tests + Doku:** +17 `tests/test_eval_replay.py` (Playback-Kontrakt, Loader-Fehlerpfade, pro Kategorie ein Tamper-Test, End-to-End + `main()`-Exit-Codes) + 2 History-Kompat-Tests; `docs/conventions.md` §Testing (wann `dm-eval` laufen lassen: vor Refactor-Merges; Goldens erneuern nur via Neu-Aufzeichnen/Generator), `architecture.md`-Autosave-Absatz, CLAUDE.md-Layout (`dmbot/tools/`). **Scope-Grenze (ADR 046):** kein Live-Modellvergleich, keine Audio-Replays, kein Würfel-RNG-Replay (Folge-Runde, falls ein Refactor den Roll→Damage-Pfad anfasst).

**Konsistenz-Wächter: deterministischer Check vor der Auslieferung (2026-07-03, D92 → ADR 045). Suite 516 grün (+30 `tests/test_consistency.py`), ruff-F sauber, committet auf `main`, live-unverified.**
Ziel: bevor eine DM-Antwort gesprochen/gepostet wird, prüft reiner Code sie gegen den WorldState — findet er einen Verstoß, wird einmal regeneriert; der Wächter darf die Session niemals blockieren.
- **Neues Modul `dmbot/llm/consistency.py`:** reine Funktion `check(text, world_state, scene) -> list[Violation]` (kein Discord/IO/LLM, testbar wie `rules/combat.py`). Zwei Checks: **toter NSC spricht** (`wounds <= 0`, das `(tot)`-Kriterium der Karte) und **szenenfremder registrierter NSC spricht** (lebend, nicht in `npcs_here`; nur mit Abenteuer+Szene — anonyme Statisten sind nie registriert und damit nie betroffen). Sprech-Attribution über drei Muster: Name→Verb (bis zu zwei Kleinbuchstaben-Wörter Lücke — kein neues großgeschriebenes Subjekt möglich), Verb→Name (`„…", sagt Grendel`), Zeilenanfang `Name: „…"` (öffnendes Anführungszeichen Pflicht).
- **Konservativ by design (False Positive = eine volle Regeneration Latenz):** nur **Präsens**-Sprechverben (Präteritum = Erinnerungen/Recaps → erlaubte bloße Erwähnung), gepaarte Zitat-Spannen werden vor dem Match geblankt (Nacherzählen fremder Worte zählt nicht), indefinite Referenzen („ein/mehrere Kultist(en) ruft") zählen nicht, Namens-Tokens die in mehreren NSC-Namen oder einem PC-Namen vorkommen sind mehrdeutig und fliegen raus (Einwort-Namen inklusive: „Kultist" vs „Verfluchter Kultist"), Titel-Tokens (Lord/Magos/…) nie allein. Mehrwort-Namen matchen pro Token („Gullar spricht" trifft „Vidame Gullar").
- **Verdrahtung:** `DMBrain.respond`/`redo` nehmen ein injiziertes `check`-Callable (Runtime baut es: `consistency_checker(channel)` schließt über State+aktive Szenenkarte); bei Violation ein `_generate`-Retry mit `KORREKTUR: <Name> ist tot …` am User-Msg (Echo/Intro-Nudge-Mechanik), **max. 1**, nur die behaltene Antwort landet in der History (mit der Original-User-Msg). **Marker-Hygiene:** die Pending-Queues (`<<TEST>>`/`<<ORT>>`/…) der verworfenen Erstantwort werden gesnapshottet+geleert und nur bei verworfenem Retry restauriert (Redo-Muster). Fail-open überall: Checker-Exception, leerer Retry (→ Erstantwort behalten), weiter-verstoßender Retry (→ trotzdem ausliefern) — plus `[consistency]`-Log-Zeilen im `[latency]`-Stil.
- **Streaming-Trade-off (ADR 045, bewusst dokumentiert):** `_deliver_streaming` kennt den Volltext erst nach Generation-Ende, das Audio spielt da schon → dort **nur Warn-Log**, kein Regenerate. Der Schutz greift auf dem Batch-Pfad (`nahtlos`-Modus, `!dm`/`!redo`-Batch, Würfel-Folge-Turns). `!start`/`!intro` bewusst ungeprüft (Director-Turns, eigener Intro-Guard).
- **Config:** `DM_CONSISTENCY_GUARD=1` (Kill-Switch, `.env.example` dokumentiert). Live-Gate in **`docs/live-test-checklist.md` §6b** ergänzt: toten NSC provozieren → Regenerate feuert, Retry sauber (im `stream`-Modus stattdessen die Log-only-Zeile sehen).

**NPC-Gedächtnis: Erinnerungen, Attitude-Drift, Fraktions-Gossip (2026-07-03, D91 → ADR 044). Suite 486 grün (+27 `tests/test_npc_memory.py`), ruff-F sauber, committet auf `main`, live-unverified.**
Ziel: NSCs sollen sich wie bei einem menschlichen Spielleiter erinnern, was mit ihnen besprochen wurde — inklusive Lügen der Spieler.
- **Schema (`memory/state.py`):** neue Dataclass `NpcMemory` (about/gist/quote/believed/importance/source/scene/ts, omit-when-empty wie die Combatant-Extras, Alt-States laden unverändert) + `faction`/`memories` an `Combatant`. Cap **30/NSC** via `Combatant.add_memory` (Prune: niedrigste Wichtigkeit, bei Gleichstand ältester; `believed: False` + Wichtigkeit 5 geschützt; alles geschützt → ältester fliegt trotzdem, Warn-Log). `ATTITUDE_SCALE` + `step_attitude` klemmen jeden Vorschlag auf ±1 Stufe (off-scale-Altwerte ankern bei `neutral`, unbekannter Vorschlag = No-op+Log).
- **Extraktor (`memory/npc_memory.py`, neu; Prompt `prompts/npc_memory_extract_de.md`):** reine Funktionen + LLM-Wrapper mit injiziertem OllamaClient (testbar wie `rules/combat.py`). Ollama-Structured-Output-Schema (wie der Roll-Router, temp 0.2, `repeat_penalty` neutralisiert per ADR 042), toleranter JSON-Parse (Fences), **ein** Retry, dann skip+Warn — blockiert nie. Input: History-Fenster seit letzter Extraktion (Runtime-Mark, kompaktions-tolerant; Gist-Dedup beim Anwenden fängt Überlappung) + anwesende NSCs mit **nummerierten** Bestands-Erinnerungen (Referenzbasis für `revealed_lies`). Unbekannter NSC mit erster Erinnerung wird registriert (Statblock-Werte inkl. neuem `AdventureNpc.faction`, Haltung `neutral`); PC-Namen werden verworfen.
- **Lügen-Flip + Gossip (Code, nicht LLM):** `revealed_lies` → `believed=False`, neuer Wichtigkeit-5-Eintrag „Wurde von X belogen …", Haltung eine Stufe Richtung hostile (zusätzlich zum Proposal-Clamp). Danach propagieren neue direct-Erinnerungen ≥4 an gleiche-`faction`-NSCs: `source: "gossip"`, ohne Zitat, Wichtigkeit −1, keine Kaskade, kein Duplikat.
- **Injektion (`llm/prompt_assembly.py`, neuer order-expliziter Slice state→**npc_memory**→rag):** `_persist_and_refresh` rendert pro *lebendem* NSC der aktuellen Szenenkarte einen `[NPC-Gedächtnis: Name — Haltung: …]`-Block, Top-K (`DM_NPC_MEMORY_TOP_K`=6; aufgeflogene Lügen immer dabei, Rest Wichtigkeit→Recency), Gist hart ≤200 Zeichen, Gossip als „(Hörensagen)" markiert. Kill-Switch `DM_NPC_MEMORY` (Default an); `!npcmem <Name>` read-only-Debug in DiceCog.
- **Trigger-Nähte:** `scenecog.!ort` + der Delivery-Scene-Confirm feuern fire-and-forget für die *verlassene* Szene; `!wrap` wartet die Extraktion der letzten Szene ab (Catch-all); `_maybe_compact` setzt das Fenster zurück; `seed_session` startet es am Join-Punkt (restaurierte History wird nicht re-gemint).
- **ADR 044** löst die Spannung zu Golden Rule #3 auf: memories = narrative Schicht (wie Recaps), harte Felder bleiben code-owned — LLM requests, Code entscheidet. `architecture.md` §7 um Schicht (c) ergänzt.
- **Nachtrag (gleiche Session):** alle offenen Live-Gates als abhakbares Drehbuch in **`docs/live-test-checklist.md`** gebündelt (Session-Reihenfolge, inkl. des neuen NPC-Gedächtnis-Gates + optionalem `faction`-Seed für den Gossip-Test); Next-step verweist darauf.

**`uv run dm-sync`: Sync-Check als Package-Entry-Point (2026-07-02, D90, Dev-Tooling). Suite 459 grün (0 neue/geänderte Assertions), ruff ohne neue Findings, committet + gepusht auf `main`.**
Reine Ergonomie, null Verhaltensänderung: der D89-Fingerprint soll auf beiden Maschinen als kurzer Befehl laufen.
- **Move:** `tools/sync_check.py` → **`dmbot/tools/sync_check.py`** (neues Subpackage `dmbot/tools/` mit `__init__.py`). Als Package-Modul entfällt der `sys.path.insert`-Hack; `REPO_ROOT` jetzt `parents[2]`; `main() -> int` + `__main__`-Guard unverändert. **Kein Shim am alten Pfad** — eine stale Kopie, die still driftet, wäre schlimmer als ein harter Bruch.
- **Entry Point:** `[project.scripts] dm-sync = "dmbot.tools.sync_check:main"`. Dafür musste `[tool.uv] package = false` weichen: Script-Entries existieren nur bei installiertem Projekt → **hatchling als Build-Backend** (`packages = ["dmbot"]`), `uv sync` installiert `cogitator` editable. Einziger Zweck ist der Entry Point; Projekt bleibt Anwendung, keine publizierte Library. `uv.lock` entsprechend mitgezogen.
- **Referenzen umgebogen (grep-first, alle Fundstellen):** SETUP.md §„Staying in sync" (+ Hinweis, dass der Entry Point mit `uv sync` landet), `docs/conventions.md` (Two-machines-drift-Bullet), `dmbot/rag/ingest.py`-Docstring, `tests/test_sync_check.py` (Import → `dmbot.tools.sync_check`, Assertions unverändert), progress.md Next-step. Docs sagen jetzt überall `uv run dm-sync`.
- **Kontrakt-Beweis:** `[sync]`-Block vor/nach dem Move byte-identisch (gleiche Zeilen, gleiche Label-Spalte); einzige Abweichung ist die `repo`-Zeile clean→dirty — das sind die Umbau-Änderungen selbst. Nebenbefund: `.env` ist **38/38** — der offene D89-Punkt (20 fehlende Keys) ist von Tobi bereits abgearbeitet.
- **Für Timo:** einmal `git pull` + `uv sync`, dann existiert `dm-sync` auch dort.

**Sync-Check: Fingerprint-Tool für die untracked Muss-Artefakte + SETUP.md-Sync-Sektion (2026-07-02, D89, Dev-Tooling). Suite 459 grün (+15), ruff-F sauber, committet auf `main`.**
Problem: adventure/, rag.db und die .env-Keys reisen nicht mit git und driften still zwischen Tobis und Timos Maschine — „hast du die aktuelle?" wurde geraten.
- **`tools/sync_check.py`** (standalone, offline, `uv run python tools/sync_check.py`): ein `[sync]`-Block — Repo (`rev-parse --short` + clean/dirty), je Abenteuer-JSON `sha=`(7-stelliges sha256, das Vergleichskriterium — Kopieren verändert mtimes, mtime nur menschenlesbarer Zusatz) + Kennzahl über den echten `Adventure.load` (Ladefehler → laute LADEFEHLER-Zeile, selbst ein Befund), rag.db (Größe, model/dim aus der Meta-Tabelle, Chunk-Zahl **pro Source** — bewusst kein Ganz-DB-Hash: Vacuum/Reihenfolge macht gleichen Inhalt binär ungleich —, Ingest-Datum pro Source), .env-**Key**-Abgleich gegen `.env.example` (fehlende/überzählige Namen, **nie Werte**), `git status --porcelain` über die getrackten data-Seeds (der „alte verschickte Kopie kollidiert mit ADR 040"-Fall). Degrade-don't-die pro Zeile (FEHLT/FEHLER statt Crash), Pfade repo-verankert (läuft aus jedem cwd), utf-8-reconfigure für die cp1252-Konsole. Kein Buchinhalt im Output (Dateinamen + Zahlen, keine Headings), keine Secrets.
- **Ingest-Zeitstempel:** `dmbot/rag/ingest.py` schreibt pro Ingest `ingested:<source>` = `YYYY-MM-DD HH:MM` in die bestehende key/value-Meta-Tabelle (Meta-**Rows** statt chunks-Spalte → null Migration; der Model-/Dim-Rebuild-Drop räumt veraltete Stempel mit ab); alte DBs lesen tolerant als „unbekannt". Kein ADR — kein diskussionswürdiger Trade-off.
- **SETUP.md „Staying in sync (second machine)"** (an „Running on another machine" angedockt): Muss-Artefakte-Liste (adventure/, rag.db, .env-Pflege statt -Kopie, Session-State nur bei Host-Wechsel, Token = eine Live-Verbindung) + die Anweisung: beide Maschinen `sync_check`, Blöcke per Auge/Diff vergleichen — die Wahrheit liefert das Tool, nicht der Fließtext.
- **Tests:** `tests/test_sync_check.py` (+15) — Key-Parse/-Diff (Secrets erscheinen nie im Output, per Test gepinnt), Zeilenformat + 7-hex-sha, tolerantes Lesen alter DBs (ohne Stempel / ohne Meta-Tabelle / DB fehlt), Adventure-Zeilen (Loader-Kennzahlen, kaputtes JSON degradiert laut), `ensure_schema`-Rebuild löscht veraltete Stempel.
- **Erster echter Befund beim Lauf auf Tobis Maschine:** die lokale `.env` hängt **20 Keys** hinter `.env.example` (laufen auf Code-Defaults — funktional gleich, aber die Live-Tuning-Knöpfe der D85/D86-Runde wie `DM_REPEAT_PENALTY`/`DM_INTRO_TEMPERATURE` stehen nicht zum Drehen bereit). Vor dem Tuning-Live-Run nachziehen.

**Authoring-Skill `/author-adventure`: adventure-md → `adventure.json`-Draft, offline + human-kuratiert (2026-07-02, D88, Dev-Tooling). Committet + gepusht auf `main` (nur Skill + Doku — Drafts/Buch-Derivate bleiben untracked unter `data/adventures/`).**
Ziel: Abenteuer #2 ff. kosten Redigieren, nicht Autorenarbeit. Gebaut nach Session-Ritual + Schema-Lektüre (`dmbot/rag/adventure.py` inkl. ADR-043-Erweiterungen):
- **`.claude/skills/author-adventure/SKILL.md`:** 5 Pässe — (1) Struktur (Szenenliste + Ortsgraph, **Stopp zur Freigabe**: der Schnitt ist die Design-Entscheidung), (2) Karten (`description_de` 2–4 dichte GM-Sätze, `opportunities_de` als `Fertigkeit (Schwierigkeit): Konsequenz` **aus dem Profil-/Party-Vokabular** — Leiter verbatim aus `difficulty_ladder`, Skills = Party-Sheets ∪ Profil; Mismatches auf die Checkliste statt Begriffe erfinden), (3) NSCs (`AdventureNpc`-Felder; Buch referenziert oft nur Core-Archetypen → Werte `GESCHÄTZT` flaggen), (4) Summary (~300 Tokens, WAHRHEIT geheim-gerahmt), (5) Spoiler-Selbstcheck + Validierung + Review-Checkliste der eigenen Schwachstellen. Harte Regeln: Spielinhalt deutsch; Spoiler nur in `secrets_de`; **`git check-ignore`-Guard vor jedem Schreiben** (Buch-Derivate nie in getrackte Pfade); null Buchinhalt im Skill selbst.
- **`validate.py`** (Helfer, importiert den echten `Adventure.load` statt Schema-Duplikat): Tracked-Pfad-Guard, rohe Szenen-ID-Kollisionen (der Loader kollabiert still per dict), `start_scene`, hängende `leads_to`, Gate-Integrität, Element-ID-Duplikate (Loader-`ERROR`-Capture), Statblock-Abdeckung von `npcs_here`, Erreichbarkeit. ASCII-only-Ausgabe (cp1252-Konsole).
- **Abnahmetest = Dry-Run + Diff:** Chemical-Burn-md (1701 Zeilen, komplett gelesen) → 14-Szenen-Draft nach `data/adventures/_authoring_smoke/` (bewusst OHNE vorherigen Blick ins handgebaute Kompendium), Validierung grün (18 Statblocks, 5 ADR-043-Gates). Diff gegen die 15 Hand-Szenen: Schnitt praktisch deckungsgleich; **4 Abweichungen = Workflow-Lücken, in den Skill zurückgebaut** (eigene `auftrag`-Szene als `start_scene`; sparsamer Vorwärts-Graph statt Voll-Mesh — `verbunden` behandelt `leads_to` als legale Züge; Summary MIT „WAHRHEIT (streng geheim …)"-Rahmung wie im Bestand statt Twist-Auslassung; Statblocks für alle 24 statt 18 Namen). 2 Abweichungen defensibel (Gates — Bestand ist älter als ADR 043; deutsche vs. Buch-Eigennamen → jetzt Konvention „Eigennamen behalten"). Bonus-Fund des Validators: `Dregs`≠`Dreg`-Namens-Join. Neues Skill-Gotcha dokumentiert: deutsche Anführungszeichen in JSON mit U+201C schließen, nie ASCII-`"` (30× im ersten Draft-Wurf kaputt). Wegwerf-Draft gelöscht; Suite unberührt (kein Bot-Code), ruff sauber. Skills-README-Tabelle ergänzt.

**Stateful Scene Cards: `<<ERLEDIGT>>`-Element-Flags, tote NSCs `(tot)`, gated Exits (2026-07-02, D87 → ADR 043). Suite 444 grün (+49, nur die 3 deklarierten mechanischen Unpack-Edits an Bestandstests), ruff sauber, committet + gepusht auf `main`.**
Aus der Task-Spec (Plan-Modus + 3 Explore-Agenten + Plan-Agent; 3 Gabelungen per Rückfrage entschieden: gesperrte Exits **verbergen** bis freigeschaltet, `requires` = Element der **aktuellen** Szene, **alle** validen Marker pro Turn). Die Szenenkarte spiegelt jetzt den Weltzustand — ohne dass das LLM je State schreibt (golden rule #3):
- **Schema (abwärtskompatibel):** `opportunities_de`/`secrets_de`-Einträge sind String (wie bisher, abgeleitete IDs `opp-1`…/`geh-1`… nach Listenposition) oder `{"id","text_de"}`; `leads_to`-Einträge String oder `{"ziel","requires"}` (`Scene.exit_requires`). ID-Kollision/Tippfehler-Gate: lauter `log.error` + degradieren, nie sterben. Chemical Burn (15 Szenen) parst unverändert, keine Kollisionen.
- **Flags:** `WorldState.scene_flags: dict[szene → element-ids]` (erstes dict-Feld, omit-when-empty, `state.json` wie `scene_id`); Mutator `runtime._set_scene_flag` validiert **nur gegen die aktuelle Szene**. Render (`adventure_block_de(scene_id, *, resolved_ids, dead_npcs)`): erledigte Gelegenheit → „Bereits geschehen:", enthülltes Geheimnis → „Bekannt (bereits enthüllt):", IDs inline (`- [opp-1] …`) damit das Modell sie zitieren kann; tote NSCs (wounds ≤ 0, Namens-Join wie `find`) → `<Name> (tot)`; gesperrte Exits fehlen in „Mögliche nächste Orte".
- **Vierter Marker `<<ERLEDIGT id>>`** spiegelt `<<ORT>>` an jeder Naht (Grammatik inkl. glued-Formen, Strip-vor-TTS, Streaming-Withholding gratis über den `<<`-Delimiter, Pending-Queue unter dem Post-Roll-Guard, Drain in `delivery._handle_erledigt` als dritter Task neben Dice/Scene). Default Confirm-Button je Element (`FlagView`, `dmbot/discord_ui/flag.py`); `DM_FLAG_CONFIRM=0` = auto-apply. Manuell: `!erledigt <id>`/`!offen <id>` (Mensch = Confirm), `!ort`/`!szenen` listen die Element-IDs mit ✅/⬜.
- **Gated Exits:** `resolve_move(…, resolved_ids=…)` lehnt unerfüllte Gates in `verbunden` wie unbekannte Ziele ab (fehlende Bedingung **nur** im Konsolen-Log — Spoiler-Disziplin); `frei` + manuelles `!ort` umgehen Gates.
- **Erzwungener Naht-Preis (im Plan deklariert + genehmigt):** `finalize_answer` 4→5-Tupel → 3 mechanische `, _erledigt`-Unpack-Erweiterungen in `test_orchestrator`/`test_streaming` (keine Assertion geändert); `test_delivery`s Fake-Brain blieb unangetastet (Guard-Reihenfolge in `_handle_erledigt`: Adventure-Check VOR dem Brain-Drain, per Test gepinnt).
- Doku: **ADR 043**, `architecture.md` §8 Stage-2, `.env.example` (`DM_FLAG_CONFIRM`), Persona-Bullet in `dm_core_de.md` (nach dem ORT-Bullet). **Live-unverified** — Skript siehe Next step.

**Spielbarkeits-Tuning-Runde: Anti-Wiederholungs-Sampling + deterministischer `!intro`-Retry (2026-06-18, D85+D86 → ADR 042 + ADR 041 Add. 2). Suite 395 grün (+16), Commit `e961b75`.**
Aus „mach die nächste Phase" → im Plan-Modus geklärt: Bootstrap zurückgestellt, stattdessen Spielbarkeit (Modell bleibt nemo). Drei Forks per Rückfrage entschieden (nur Kernmechanik n/a — Bootstrap weg; GPU-Offload verfügbar; erst bauen, dann 1 Live-Run). Gebaut per TDD, adversariale Verify-Stage per Workflow (3 Reviewer, jeder Fund gegengeprüft).
- **B1 (ADR 042):** `OllamaClient` bekam `repeat_penalty`/`repeat_last_n` als Instanz-Defaults (wie `num_ctx`), gemerged über neues `_merged_options()` auf **jeden** Call (batch+stream); per-Call-Options gewinnen. `DM_REPEAT_PENALTY` (1.1) + `DM_REPEAT_LAST_N` (256). **Verify-Fund (bestätigt, gefixt):** der Roll-Router (`classify_test`) muss `repeat_penalty=1.0` explizit setzen — sein Prompt listet alle Skills/Schwierigkeiten im Look-back, sonst bestraft der Penalty genau den Enum, den er wählen muss (golden rule #2). `tests/test_sampling.py` (+5 inkl. Router-Neutralisierung).
- **C1 (ADR 041 Add. 2):** pures `dmbot/llm/intro_guard.py::is_weak_intro(text, roster_names)` (schwach bei <280 Zeichen **oder** Figur ungenannt; Genitiv-`s`-tolerant — Verify-Nit) + `INTRO_RETRY_NUDGE`. `respond_opening` regeneriert bei schwachem Auftakt **einmal**, nur die behaltene Antwort in History; Batch-Pfad (`!intro test`) verdrahtet mit `CharacterStore.character_names()`. Streaming bewusst unverändert (kann nicht mitten im Audio retrien). `tests/test_intro_guard.py` + 4 Retry-Tests.
- **Bewusst gelassen (Verify-Nits):** recap/rules-Q erben den milden Penalty (Freitext, harmlos/hilfreich); `_last_action` stale-None ist vorbestehend, kein C1-Regress. **Workstream A (Tempo/GPU)** ist Tobis Live-Schritt — nur `.env`-Knöpfe, `.env.example` schon Soll. **Live-unverified.**

**`!intro`-Meta-Auftakt deterministisch gestrippt + Temp 0.7 (2026-06-16, D84 → ADR 041 Addendum). Suite 379 grün (+3).**
Live-Retest *mit* D83 (Temp 0.5 + gehärtete Direktive): Party jetzt reich eingewoben (D82 + Brief wirken), aber nemo schrieb **trotzdem** „Als Spielleitung beginne ich die Sitzung:", wickelte alles in `"…"` und schloss „Was werdet ihr als nächstes tun?". → Prompt-Anweisung ist kein verlässlicher Hebel gegen den Tic, also deterministisch in `sanitize.py`:
- **`_META_PREAMBLE`** um Auftakt-Verben (`beginn\w*|eröffn\w*|start\w*|leite?`) + Objekte (`…die Sitzung|Runde|Spielrunde`) erweitert → der !intro-Meta-Auftakt strippt wie die alten `beschreibe`-Formen.
- **Neu `_unwrap_enclosing_quotes`:** entfernt EIN Quote-Paar, das die *ganze* Antwort umschließt (nur sauberer Einzel-Envelope — schließendes Quote darf nicht innen wiederkehren → NPC-Zeilen bleiben). In `_sanitize` **zwischen** Leading und Trailing eingehängt, damit der „Was tut ihr?"-Strip wieder greift (der Umschlag hatte `…?"` statt `…?` hinterlassen). Beide Intro-Pfade finalisieren über `_sanitize` (Batch + Streaming-`finish()`).
- **`DM_INTRO_TEMPERATURE` 0.5 → 0.7:** 0.5 las flach/formelhaft; mit gestripptem Tic ist die reichere höhere Temp leistbar. +3 Sanitizer-Tests. **Live-unverified** — am Tisch prüfen, Temp 0.3–0.8 nachjustieren.

**`!intro`-Zuverlässigkeit: feste Temperatur + gehärtete Direktive (2026-06-16, D83 → ADR 041). Suite 376 grün (+2).**
Aus dem Playtest: `!intro test` lieferte mal top (14.06., jede Figur eingewoben), mal kurz-generisch mit Meta-Erzählen („Als Spielleitung beginne ich die Sitzung…") und ohne Figuren — obwohl Party geladen (D82), Konfig angeglichen, Kollege gepullt. Direktive + Roster nachweislich intakt → **Modell-Varianz** (Opening ohne gesetzte Temperatur → nemo-Default ~0.8).
- **(1) Temperatur:** `config.dm_intro_temperature` (`DM_INTRO_TEMPERATURE`, Default 0.5) → `runtime._intro_temperature`; als optionaler `temperature`-Param **parallel zu `num_predict`** durch `respond_opening`/`respond_opening_streaming` → `_generate`/`_stream_and_store` → `_chat_once` → `_build_request` gereicht (nur in die Ollama-Options, wenn gesetzt → `!start`/Normal-Turns unverändert). Beide Varianten reichen den Wert weiter (`!intro test` über `_deliver_intro_chunked`, `!intro` über `_deliver_streaming(opening_temperature=…)`).
- **(2) Direktive gehärtet** (`director_msgs.py`, beide Varianten): HEAD verbietet Meta-Erzählen + verlangt „mehrere Absätze"; TAIL verlangt Raum + stimmungsvollen Abschluss und verbietet den knappen „Was tut ihr?"-Abbruch. Die Shape-Asserts (`[Regie]`/`Monolog`/`Probe`/`folgenden Figuren`) bleiben.
- **+2 Tests** (`temperature` landet in den Options, wenn gesetzt / fehlt per Default). **Live-unverified** — Temp (0.3–0.8) + Wortlaut am Tisch nachjustieren. ADR 041.

**Default-Party-Fix: die Party hängt nicht mehr an einer Voice-Channel-ID (2026-06-16, D82 → ADR 040). Suite 374 grün (+5), 0 Test-Änderungen.**
Aus Tobis Playtest: `!intro` lieferte „irgendein generisches" Intro statt Fridolin & Co. Diagnose über `logs/terminal.log`: der letzte Join war Voice-Channel **'fett'** (`1355…`) **ohne** committete `characters.json` → `_example`-Party (Seskin/Vask/Mortn) → das gesprochene Intro war sauber, nur die **falsche** Party. Wurzel: Party an die Channel-ID gebunden + `.gitignore`-Allowlist committet nur 'circlejerk' (`1343…`), also hat der Kollege (wo der Bot läuft) für keinen anderen Channel ein Sheet.
- **`config.default_party`** (env `DM_DEFAULT_PARTY`, Default `_default`); **`_load_characters`** löst auf: Channel-Sheet → Default-Party → `_example`. Die laute D43-`fallback`-Warnung feuert **nur** noch im `_example`-Fall (Default-Party = gewollter Fallback, lädt still). Boot-`_load_characters(None)` nimmt die Default-Party ebenfalls.
- **`data/sessions/_default/characters.json`** committet (Kopie der Fridolin-Party) + in `.gitignore` neben `_example` allowlistet → wandert per git zum Kollegen und gilt für **jeden** Channel. `+5 tests/test_load_characters.py`.
- **Entscheidung committete Datei statt env-Pointer** (`.env` wandert nicht per git) und statt `.gitignore`-Wildcard pro Channel. **Repo bleibt öffentlich** → gekaufte `adventures/`/PDFs bleiben lokal (Copyright). ADR 040.

**`/improve-architecture`-Runde 3: Szenen + `!lore` → eigene Sub-Cogs (2026-06-16, D81 → ADR 039). `dmcog.py` 662→502, Suite 369 grün (+10), 0 Test-Änderungen.**
Aus „schau dir orchestrator + dmcog am `/improve-architecture` an, was kann sinnvoll ausgelagert werden" + „Ziel: ein Agent soll nur laden, was seine Aufgabe braucht". Workflow: 3 Finder (orchestrator-vorwärts / dmcog-vorwärts / Retrospektive der bisherigen Auslagerungen), jeder Kandidat durch 3 adversariale Linsen (Kontext-Gewinn real? / golden-rule+ADR? / Deletion-Test ehrlich?). 13 Kandidaten, 7 überlebten; Tobi wählte das dmcog-Paket.
- **`scenecog.py` (`SceneCog`):** `!ort`/`!szenen`/`!ortmodus` byte-identisch verschoben; berührt nur `self._rt.*`, kein Hook nötig. Ein Szenen-Befehl-Fix lädt jetzt ~84 statt 662 Z.
- **`lorecog.py` (`LoreCog`):** `!lore` + `_lore_rundown`/`_lore_speak`/`_lore_question` + die 3 Lore-Dicts; die eine Cross-Cog-Kante (`_lore_speak`→`delivery._speak`) über neuen **`runtime.speak`**-Hook (ADR-029-Muster) → `self._rt.speak`. Lore-only-Importe (`RulesView`/`LoreReadView`/`available_topics`/`lore_pages`/`_DATA_DIR`/`discord`) raus aus `dmcog`.
- **Der entschiedene ADR-035-Fork:** **Sub-Cog statt Mixin** (Mixin-`@commands` riskieren lautlose Nicht-Registrierung — `CogMeta`; verifiziert: `SceneCog.__cog_commands__` = ort/ortmodus/szenen, `LoreCog` = lore), **zwei** Cogs statt einem `AdventureCog` (kein geteilter State).
- **Neu `tests/test_subcogs.py` (+10)** — Scene-Befehle hatten bisher **null** Tests (`ortmodus`-Toggle/Reject, `ort` ohne Abenteuer + deterministischer Zeiger-Move, `_lore_question` ohne RAG/ohne Treffer/Embed-Render, `!lore tts` ohne Stimme). Byte-Check: 150/150 verschobene Zeilen identisch (die eine bewusste `speak_fn`-Änderung herausgerechnet).

**Deepening-Runde 2 aus `/improve-architecture`: Kandidaten #4 + #5 + #6 umgesetzt (2026-06-16, D80 → ADR 038). Suite 359 grün, 0 Test-Änderungen, Commits auf `main`.**
Tobis Wahl „mach 4 5 und 6". Per Workflow: **sequenzielles** Implement (#5→#4→#6, da #4/#6 sich `runtime.py`+`voicecog.py` teilen und der Import-Cascade runtime→orchestrator paralleles pytest riskant macht), danach **3 parallele adversariale Verifier** auf dem stabilen Baum; Main-Loop = volle Suite + Diff-Review + Commits. Disziplin wie D70–D79.
- **#5 — Prompt-Zusammenbau-Besitzer → `dmbot/llm/prompt_assembly.py` (ADR 038):** der System-Prompt wurde in `_build_request` schon in expliziter Reihenfolge gefügt, aber als Inline-`if slice:`-Kette mit der Ordnung nur als Kommentar. **Nur den Join** in die reine `assemble_system_prompt(persona, *, recap, adventure, state_summary, rag, alias_hint)` gezogen (Reihenfolge persona→recap[gewrappt]→adventure→state→rag→alias_hint, Truthiness-Skip, `"\n\n"`-Join, Recap-Header byte-identisch). **Die Schnittgrenze (der Trade-off):** die `.get()`-Cache-Reads + `load_system_prompt()` bleiben in `_build_request` — kein „Provider-Registry", der Berechnung+Caching mitverschluckt, sonst bräche das bewusste cache-vs-pull-Timing (RAG pro Turn, Recap/State nur bei Mutation). `tests/test_prompt_assembly.py` (+6, String-Assert ohne LLM).
- **#4 — `runtime.seed_session(voice_channel, text_channel)` (D-Eintrag):** die ~33-Zeilen-Seed-Sequenz aus dem `!join`-Handler (Party + Alias/Sprecher → Turn-Order → State seeden → Start-Szene-Pointer für frischen State → persist → D41-Crash-Recovery) byte-gleich in eine Runtime-Methode; der Cog ruft nur noch `char_fallback = self._rt.seed_session(channel, ctx.channel)`. Voice-Receive-Verdrahtung (Sink/Listen) + alle Ansagen (inkl. D43-Beispielparty-Warnung) bleiben im Cog. `tests/test_seed_session.py` (Fresh-vs-Loaded-Szene-Fork, Crash-Recovery, char_fallback).
- **#6 — `runtime.clear_panel(attr)` (D-Eintrag):** der „vorheriges Panel löschen + Handle nullen"-Block war **4× byte-identisch** (`_post_mic_button`/`pausebutton`/`_post_turn_order`/Leave-Schleife) → ein Runtime-Helfer. `_refresh_pause_panel` (bewusstes edit-in-place statt löschen+neu) **unangetastet**. `tests/test_clear_panel.py`.
- Damit ist der **`/improve-architecture`-Strang (#1–#6) abgeschlossen** (#3 war verworfen).
- **Nachzug (Doku/Logging, gleiche Session):** Modul-Karten in `CLAUDE.md` + `architecture.md` um `combat.py`/`prompt_assembly`/`segments.py` ergänzt (`68d7dcd`); `logsetup.py` leert `terminal.log` bei jedem Start (`mode="w"`; `debug.log`/`transcript.log` bleiben Append, `f106141`); `.env.example` auf `DM_LOG_FILE=1` (`e8dd54d`). Kein Bot-Verhalten am Spieltisch berührt.

**Deepening-Runde aus `/improve-architecture`: Kandidaten #1 + #2 umgesetzt (2026-06-16, D79 → ADR 037). Suite 343 grün, 0 Test-Änderungen, 3 Commits auf `main`.**
Aus dem `/improve-architecture`-Kandidatenset wählte Tobi #1 + #2 (verworfen #3, geparkt #4/#5/#6). Umgesetzt per Multi-Agenten-Workflow: 2 Implement-Agenten parallel (disjunkte Dateien), je ein adversarialer Verify-Agent (byte-Äquivalenz + scoped grün), danach Main-Loop = volle Suite + Diff-Review + Commits. Disziplin wie D70–D75: Logik byte-gleich verschoben, nur neue Tests dazu, keine bestehende angefasst.
- **#1 — Whisper-Halluzinations-Filter verdrahtet (mechanisch, kein ADR):** `dmbot/stt/segments.py::confident_text` existierte schon (extrahiert, aber untracked + nie eingehängt). `transcriber.py` lief noch das byte-gleiche Inline-Duplikat → ersetzt durch `text, dropped = confident_text(segments)` (Position im getimten Bereich gehalten, da der Generator dort konsumiert wird); tote Konstanten `_NO_SPEECH_MAX`/`_LOGPROB_MIN` + Kommentar raus. `tests/test_segments.py` (+7): u. a. Grenzfall `==0.7`/`==-1.0` werden **behalten** (strikt `>`/`<`), Leeres still übersprungen, Drop-Tupel-Form.
- **#2 — Attack/Warp-Auflösung → reines `dmbot/rules/combat.py` (ADR 037):** `toughness_bonus`, `resolve_attack`→`AttackOutcome`, `resolve_warp_consequences`→`WarpConsequence` — kein Discord, keine WorldState-Mutation, RNG injiziert. **Schnittgrenze (der Trade-off):** die reine Funktion stoppt **vor** der Mutation und gibt Soak-Aufschlüsselung + `DamageResult` (bzw. Perils-Zeilen + `reset_charge`-Flag) zurück; der Cog ruft `state.apply_damage`/`reset_warp_charge` und das schon reine `engine.describe_damage_de` (liest Post-Mutation-Wunden). So **keine Duplikation** des WorldState-Wunden-Clamps (Narration↔State-Drift-Risiko vermieden). `_toughness_bonus` bleibt als dünner Delegator am Cog → **0 Test-Änderungen**; die deutschen Perils/Overt-Strings byte-identisch kopiert (🜏/—/→, sha256-geprüft). `tests/test_combat.py` (+12, fixed-seed: NPC-/PC-Soak-Pfade, Augmetik, Floor bei 0, Containment-Erfolg/-Fehlschlag/Immediate-Perils).
- **#3 verworfen** (Tobi: Turn-Reihenfolge egal — jeder Spieler gibt Input, das LLM treibt die Geschichte). **#4/#5/#6** als „auch gut, später" geparkt.

**Skill-Tooling-Runde: 4 Claude-Code-Skills nach `.claude/skills/` (2026-06-15, D78). Kein Bot-Code — Suite unberührt (324 grün), 5 Commits auf `main`.**
Tobi wollte den (nicht existenten) „tdd"-Skill → recherchiert + repo-eigenen `/tdd` gebaut, dann aus Matt Pococks `mattpocock/skills` drei adaptiert. Stil wie die bestehenden Skills (English, repo-spezifisch), README-Index je Schritt gepflegt.
- **`/tdd` (`abb49c8`):** Red-Green-Refactor am deterministischen Kern (`dmbot/rules/`), fixed-seed; Guardrails gegen die zwei Default-Fehler (impl-first, Tests grün-schreiben).
- **`/grill-me` (`0f371be`):** verhört den Plan Ast für Ast (Entscheidungsbaum), antwortet aus `architecture.md`/ADRs/Code wo möglich, empfiehlt je Frage; mündet in einen ADR.
- **`/improve-architecture` (`1cd671c`, entschärft `76c0b1a`):** Whole-Codebase-Vertiefungs-Review (Deletion-Test → flache Pass-Through-Module → deep), Markdown-Report (kein HTML), informiert durch `architecture.md`/`docs/decisions`. Grillen **bedingt** statt erzwungen (Tobis Einwand) — zwei Seiteneffekte bleiben Pflicht (`architecture.md` fortschreiben, ADR-bei-Ablehnung).
- **`/to-prd` (`0924001`):** Begleiter zu `/grill-me` — synthetisiert den gegrillten Kontext (ohne Interview) zum PRD nach `docs/plans/<slug>.md` (kein Issue-Tracker; das Original published in einen Tracker). Die Kette ist `/grill-me`→`/to-prd`→`/tdd`.
- **Verworfen:** `rohitg00/awesome-claude-code-toolkit` komplett (generische Stack-Tutorials, Cloud-API-orientiert oder überlappend mit `/code-review`·`/simplify`) — nichts importiert, Set bleibt schlank (golden rule #9).

**Dev-Gates-Runde: Lint im Test-Hook + blockierender pre-commit + Review/Simplify-Trigger-Checkliste (2026-06-15, D77). Suite 324 grün, 4 Commits gepusht.**
Aus der Frage „soll `/code-review` (und `/simplify`) automatisch vor jedem Commit laufen?" — Entscheidung **nein** (abgerechnete
LLM-Pässe; `/simplify` *schreibt* Code → widerspricht der Hand-Kontroll-Disziplin, D72). Stattdessen: billige + deterministische
Gates automatisch (0 Tokens), teure LLM-Reviews nach Urteil, als Checkliste verankert.
- **Lint im Stop-Hook (`c80bee2`):** `ruff --select F` (pyflakes: ungenutzte Importe/Namen) läuft jetzt vor pytest — gleiche
  Philosophie (nur bei `dmbot`/`tests`/`data/systems`-Änderungen, still bei grün, nicht-blockierend). F-only bewusst
  (Zeilenlänge/Style `E*` aus — lange Doc-Zeilen Absicht, Re-Export-Shims `# noqa: F401`). Fand + entfernte sofort **2 tote
  Importe** (`re`, `difflib.SequenceMatcher` in `orchestrator.py`, D70-Auslagerungs-Rückstände).
- **Blockierender git pre-commit (`855bf8a`):** `tools/hooks/pre-commit` (aktiviert via `git config core.hooksPath tools/hooks`)
  fährt dieselben ruff-F + Suite bei *Tobis eigenen* Commits, bricht bei Rot ab (Bypass `git commit --no-verify`), Scope-Guard auf
  gestagete `dmbot`/`tests`/`data/systems` (Docs-only-Commits überspringen). Beide Pfade (skip/run) verifiziert.
- **Checkliste in `conventions.md` (`de804ac`, `f63e630`):** neue Sektion „Code-Review-, Simplify- & Lint-Gates" — wann
  `/code-review` (read-only) lohnt vs. der Tagesend-Fan-out, und `/simplify` (schreibender Pass → nie automatisch, race-sensibler
  Code von Hand, D72). Überlebt Context-Clears.
- _Andere Skills (verify/run, security-review) als stehende Erinnerung verworfen — Projekt-Skills stehen im `.claude/skills/README`._

**Review-getriebene Fix-Runde nach Fan-out-`/code-review` über die Tagescommits `7b5af54..HEAD` (2026-06-15, D76). Suite 324 grün, 2 Commits gepusht.**
Tobi: „viele Commits heute — lohnt sich Fan-out + `/code-review`?" Da alles schon auf `main` (synced) lag, hatte der eingebaute
Branch/PR-Review nichts zu diffen → stattdessen Fan-out-Review (21 Agenten, jedes Finding adversarial gegengeprüft) über den
Commit-Range selbst: **14 Findings → 3 bestätigt, 11 entwarnt**. Kein Refactor-Regress (D70–D75) überlebte die Gegenprüfung,
Golden-Rules-Querschnitt (dice=code, memory-split, Feedback-Schutz L1/L2, Two-Bot-Isolation) sauber.
- **#2/#3 (Bug + maskierender Test) — `dmbot/shutdown.py::disconnect_voice` (`2b608e7`):** Der True/False-Rückgabewert hing an
  `asyncio.wait_for`, das `TimeoutError` wirft. Gegen das echte discord.py + Py 3.12 ist der Zweig **tot** — die
  Bestätigungs-Wartung **schluckt** den Bound-Cancel und kehrt normal zurück → `wait_for` *returns*, die Funktion gab immer
  `True`, die „abandoned at shutdown"-Warnung feuerte nie. Der Test maskierte das (nackter `sleep`-Mock, der den Cancel
  propagieren lässt → grünes `False`, das die Produktion nie liefert). **Neu deterministisch:** Disconnect als Task, `asyncio.wait`
  prüft, ob er *im Fenster* fertig wurde (fertig → confirmed, sonst cancel + abandoned) — kein wackeliges Elapsed-Timing. Test auf
  den echten swallow-and-cleanup-Kontrakt umgestellt + zweiter Test für den propagierenden Pfad.
- **#1 (größte Test-Lücke) — `tests/test_delivery.py` neu (`5499066`):** `_deliver_streaming` (die größte ADR-035-Auslagerung)
  hatte für seine neue `puffer`-State-Machine **null** Tests. Vier Verhaltensweisen festgenagelt (echte Pipeline, Fake-Brain +
  Fake-Bridge, nur TTS-Synth gefakt mit echten Temp-Files): Head-Start-Füllung vor dem ersten Play, plain-stream Sofortstart,
  Transform-zu-leer-Skip, **und der early-abort Temp-WAV-Cleanup (Bridge-5xx → kein Leak)**.
- **Eigener Stolperstein:** mein *erster* `disconnect_voice`-Fix (elapsed-basiert) kippte in der vollen Suite um (Flake genau an
  der `timeout`-Grenze) — gefangen, weil die Suite nach dem Fix lief; der task-basierte Zweitwurf ist verhaltensdeterministisch
  (Shutdown-Test 5× wiederholt, stabil).
- **Bewusst liegen gelassen:** die 11 entwarnten Nits — alle intentional (ADR-033 `flach`-Default), unerreichbar
  (`num_predict=0`, leerer `content`) oder „so geboren, kein Regress". Kein ADR (Bugfixes, kein Trade-off).

**`setup.ps1` macht jetzt alles end-to-end + dauerhaft im PATH; winget/ExecutionPolicy-Snags des Kollegen gelöst
(2026-06-14, D75 → ADR 036). parse-OK, Suite 319 grün (nur Skripte/Doku).** Tobi: Setup soll wirklich alles erledigen
(Download/Install/**PATH**/startklar, idempotent); beim Kollegen hakten **winget** + die **Skriptausführungs-Richtlinie**.
- **Persistenter PATH** (vorher nur prozesslokal, `:80-81`): neuer Helfer `Add-ToUserPath` schreibt den User-PATH per
  `[Environment]::SetEnvironmentVariable(…, "User")` (append-only, dedup, normalisiert) und aktualisiert auch `$env:PATH`;
  hängt uv-Bin (`uv python dir --bin` = `~/.local/bin`, enthält uv.exe **+** das python-Shim) und das Ollama-Dir ein.
- **Globales `python`:** `uv python install 3.12 **--default**` (vorher ohne `--default` → kein globales python). Vorhandenes
  3.12 wird nicht verdrängt (nur angehängt). Verifiziert: `--default` existiert in uv 0.11.19; Dedup-Logik read-only getestet.
- **Ollama voll automatisch:** robustes winget (`--disable-interactivity` + Accept-Flags, try/catch) → **offizieller
  Installer-Fallback** (`OllamaSetup.exe /VERYSILENT /NORESTART`) → PATH → Dienst → Modelle. **Bug-Fix:** `ollama pull bge-m3`
  (echter RAG-Embedder) statt veraltetem `nomic-embed-text` (`:178`).
- **Prefetch (STT+XTTS) standardmäßig an** (`-SkipPrefetch` opt-out; `-Prefetch` als No-op-Alias behalten).
- **Fresh-Machine-Härtung im Kopf:** TLS 1.2 erzwungen; `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`; `Unblock-File`
  auf Repo-Skripte; **neues `setup.bat`** (Doppelklick → `powershell -ExecutionPolicy Bypass -File setup.ps1`) umgeht die Policy.
- End-Summary gibt die RAG-Build-Befehle aus, wenn PDFs da sind aber `rag.db` fehlt. SETUP.md-Quickstart angeglichen.
- **Bewusst nicht ausgeführt:** der volle Installer auf Tobis Maschine (persistente PATH-/Policy-/`--default`-Änderungen) —
  Parser-Check (1652 Tokens, OK) + `Add-ToUserPath`-Dedup + `uv python find` read-only verifiziert. _Live offen: `setup.bat`
  beim Kollegen auf frischer Maschine per Doppelklick._

**Delivery-Pipeline aus `dmcog.py` nach `dmbot/voice/delivery.py` ausgelagert (2026-06-14, D74 → ADR 035). `dmcog.py`
1188→662, `delivery.py` 575, Suite 319 grün, 0 Test-Änderungen, ruff sauber.** Tobis Wahl „b" — der eigentliche Hebel
(größte Datei nach dem Cog-Split), per **Komposition** statt Vererbung. Vorgehen:
- **Boundary erst kartiert** (interner Call-Graph in `dmcog` + Test-Surface), dann geschnitten: `DeliveryPipeline`
  (`DMCog` hält `self._delivery = DeliveryPipeline(runtime, post_deliver=self._post_deliver)`) bekommt die
  Antwort→Audio-Methoden `_synthesize`/`_speak`/`_speak_seamless`/`_begin_turn`/`_use_streaming`/`_handle_scene`/
  `_make_scene_confirm`/`_deliver_answer`/`_await_dice_scene`/`_deliver_streaming` + die Hooks `_auto_dm_turn`/`_run_and_deliver`.
- **Auf dem Cog geblieben:** der Recap-Tail (`_post_deliver`/`_autosave_turn`/`_maybe_compact`/`_persist_recap`) — genau das,
  was `test_autorecap` anfasst → als **eine** `post_deliver`-Callback injiziert (ADR-029-Hook-Muster, objekt-lokal) →
  sauberer Schnitt **und 0 Test-Änderungen**. Commands + `_deliver_intro_chunked` + Lore-Helfer rufen jetzt `self._delivery._<m>`.
- **Byte-exakt** per Slice-Skript verschoben (**29 835 Zeichen char-exakt gegen `HEAD` verifiziert**; AST-geprüft: 13 Methoden
  in einer Klasse, keine Leaks im Cog). Glue von Hand (Import, `__init__` + Hook-Rewire, ~16 Call-Site-Prefixe), ruff `--fix`
  für die 8 nun ungenutzten Imports. **ADR 035** geschrieben (Komposition vs Mixin, Callback-Schnitt, deferred Szenen-/Lore-Sub-Cog).
- _Nicht-Byte-Effekt: verschobene `log.*`-Zeilen tragen `voice.delivery` in der `%(name)s`-Spalte (Nachrichten/Formatierung gleich)._

**`_TurnTiming` aus `runtime.py` nach `dmbot/turn_timing.py` ausgelagert (2026-06-14, D73 → ADR 034). `runtime.py`
610→516, Suite 319 grün, ruff sauber, 0 Test-Änderungen.** Fortsetzung der D70/D71-Linie (Kandidat #1 der gescouteten
Liste): den per-Turn-Latenz-Record `_TurnTiming` + die Konstante `_CTX_WARN_FRACTION` byte-exakt in ein eigenes Modul
gezogen (zustandsloser Logging-Helfer, kein `SessionRuntime`-Bezug). **Re-Export-Shim** `from .turn_timing import
_CTX_WARN_FRACTION, _TurnTiming  # noqa: F401` in `runtime` hält alle vorhandenen Importe stabil (`dmcog`-Import-Zeile,
`tests/test_autorecap.py`, `tests/test_context_budget.py`); das jetzt ungenutzte `dataclass`-Import in `runtime` entfernt.
Verifiziert: Import-Kette (`runtime._TurnTiming is turn_timing._TurnTiming`), `dmbot.voice.dmcog` importiert sauber, ruff
`All checks passed`, Suite **319 grün**. _Einziger Nicht-Byte-Effekt: Logger-Name der `[latency]`/`[ctx]`-Zeilen ist jetzt
`dmbot.turn_timing` (Text/Prefix gleich; Konsole-INFO blendet den Namen aus, kein Test prüft ihn)._

**`orchestrator.py`-Verschlankung abgeschlossen (E1–E4): alle abgekapselten Blöcke nach `dmbot/llm/*` ausgelagert
(2026-06-14, D70+D71 → ADR 034). `orchestrator.py` 1175→783, Suite 319 grün, verhaltensidentisch.** Tobis Ziel:
nur **in sich geschlossene** Methoden auslagern, damit sie nicht mitgeladen werden, wenn ein Agent woanders arbeitet —
**Funktionalität unverändert**. Umgesetzt (byte-exakt per Slice-Skript, Re-Export-Shims `# noqa: F401` in `orchestrator`,
**0 Test-Änderungen**):
- **D70 (E1–E3):** `dmbot/llm/sanitize.py` (Sprech-Säuberer: `_ROLE_LABEL` + Meta/Preamble/Trailing-Regexes,
  `_cut_at_labels`, `_strip_leading_label`, `_sanitize*`, `_trim_to_last_sentence` — am häufigsten editiert),
  `dmbot/llm/echo_guard.py` (`is_echo`/`is_self_repetition` + `_*_NUDGE`/`_ROLL_DIRECTIVE`, ADR 018/W4),
  `dmbot/llm/director_msgs.py` (`build_opening/intro_director_msg`, ADR 031). 1175→933.
- **D71 (E4):** `dmbot/llm/stream_assembler.py` (`StreamAssembler` + die geteilte `finalize_answer`-Naht, ADR-017-Parität;
  pure, kein `DMBrain`-State). Ungenutzte Marker-/`dataclass`-/`split_completed`-Importe in `orchestrator` getrimmt. 933→783.
- **Bleibt in `orchestrator`:** der `DMBrain`-Körper (geteilter Per-Channel-State, `_build_request`-Promptreihenfolge,
  Aux-LLM-Calls `classify_test`/`summarize`/`answer_rules`) — Trennung würde nur an `self` koppeln.
- _Aufgeschoben (kein „abgekapselte Methode" → eigenes Mixin-Idiom + ADR nötig): die **`dmcog.py`-Splits**
  (Lore-Cog nach `_speak`/`_synthesize`→Runtime; Scene-Mixin)._ — _Nachgeholt: die Delivery-Pipeline-Auslagerung in D74 → ADR 035._
- **D72-Nachzug (`dmcog.py`):** den doppelten End-of-Turn-Tail (autosave → mic-reanchor → Auto-Recap) von Batch- und
  Streaming-Pfad in `_post_deliver` vereinheitlicht — von Hand (nicht `/simplify` frei laufen lassen), nur die wirklich
  identische Sequenz; die pro-Pfad-`finally`-Platzierung von Dice/Scene (D40/D43) bleibt. Verhaltens-/geschwindigkeitsidentisch,
  Suite 319 grün. Reine Wartbarkeit, kein Größen-Hebel (Datei bleibt groß → echtes Schrumpfen = späterer Cog-Split).

**`orchestrator.py` verschlankt: reine Helfer nach `dmbot/llm/*` ausgelagert (2026-06-14, D70 → ADR 034). Suite 319 grün.**
Ziel: Kontext-Effizienz für künftige Agenten — große, zusammenhängende Funktionen sinnvoll auslagern, **Funktionalität
unverändert** (Tobis Vorgabe). Vorlauf: Fan-out-Analyse (zwei Plan-Agenten über `dmcog.py` + `orchestrator.py`); E1–E3
von `orchestrator` zuerst umgesetzt:
- **`dmbot/llm/sanitize.py`** — die Sprech-Säuberer (`_ROLE_LABEL` + Meta-/Preamble-/Trailing-Regexes, `_cut_at_labels`,
  `_strip_leading_label`, `_sanitize*`, `_trim_to_last_sentence`). Am häufigsten editiert (Playtest-Loop).
- **`dmbot/llm/echo_guard.py`** — `is_echo`/`is_self_repetition` + `_*_NUDGE`/`_ROLL_DIRECTIVE` (D43/ADR 018, W4).
- **`dmbot/llm/director_msgs.py`** — `build_opening_director_msg`/`build_intro_director_msg` (ADR 031).
- **Verhaltensidentisch:** byte-exakt per Slice-Skript verschoben (keine Regex-Abschreibfehler); **Re-Export-Shims** in
  `orchestrator.py` (`# noqa: F401`) halten den Import-Surface stabil → **0 Test-Änderungen**, Suite **319 grün**
  (die Shims fingen prompt `_ROLE_LABEL` ab, das `summarize`/`answer_rules` nutzen). `orchestrator.py` **1175→933**.
  `finalize_answer`, `StreamAssembler` und der `DMBrain`-Körper bleiben (geteilter Per-Channel-State → nicht trennen).
- _Direkt danach **E4** (D71) nachgezogen: `StreamAssembler`+`finalize_answer` → `llm/stream_assembler.py`, 933→783._

**Dritter Lieferart-Modus `puffer` (Head-Start-Puffer) — Tobis Idee umgesetzt (2026-06-14, D69 → ADR 033 Addendum).
Suite 319 grün.** Tobi: „warum lädst du nicht die ersten 3 Sätze und spielst den ersten ab und lädst die anderen
parallel?". Genau das, als **dritte Lieferart** zwischen `stream` und `nahtlos`:
- **`puffer`:** der `_deliver_streaming`-`play_worker` sammelt `DM_SPEECH_PREBUFFER` (Default 3) WAVs **vor** der
  ersten Wiedergabe, spielt sie dann und füllt parallel nach; `wav_q`-maxsize = Puffertiefe (Cushion bleibt erhalten).
  `prebuffer == 1` = altes `stream`. Gepufferte, noch nicht gespielte WAVs werden im `finally` aufgeräumt (kein Leak).
- **Steuerung:** neuer Lieferart-Wert `puffer` + eine **Zahl** in `!sprechmodus` setzt die Tiefe live (`!sprechmodus
  puffer 4`); Config `DM_SPEECH_PREBUFFER` (Floor 1). `runtime.prebuffer_count()` = Tiefe nur in `puffer`, sonst 1.
- **Realität auf CPU:** der Puffer federt den Synthese-Rückstand ab → Lücken später. Kurze Turns (2–5 Sätze) werden
  ~lückenlos bei kleiner Startverzögerung; das lange Intro startet viel früher als `nahtlos`, bekommt aber später
  trotzdem Lücken (Synthese kommt nicht hinterher) + eine kleine Bridge-Lücke je Satz bleibt. Voll lückenlos überall =
  weiterhin GPU (ADR 002). **+3 Tests** (319 grün), Import-Smoke ok.
- _Live offen (nach dem Gate): `!sprechmodus puffer` (+ Tiefe variieren) gegen `stream`/`nahtlos` hören._

**Globaler Sprech-Modus: Lieferart × Intonation als zwei Achsen, für ALLE Turns, laufzeit-umschaltbar
(2026-06-14, D68 → ADR 033). Suite 316 grün.** Tobi will sich auf **eine** Wiedergabe-Art für alle gesprochenen
Texte festlegen (besserer Klang, keine Anfälle) und erst A/B-testen; er bevorzugt bislang nahtlos, will aber auch
eine intonierte Variante hören. Umgesetzt als zwei orthogonale, global gültige Achsen (kein Sonderpfad mehr je Befehl):
- **`DM_SPEECH_MODE`** `stream` (gestreamt, schneller Start, Mini-Lücken) | `nahtlos` (eine durchgehende Spur, ein
  Bridge-Call, lückenlos — wartet aber auf die Vollsynthese). **`DM_SPEECH_PUNCT`** `flach` (`strip_speech_punctuation`,
  kein Gibberish, flacher) | `intoniert` (`None` → Wrapper behält `.,!?;:-` für Betonung, Gibberish-Risiko). Default
  `stream`+`flach`. _Hinweis: normale Turns sind damit per Default satzzeichenfrei (flacher) als bisher._
- **Verdrahtung:** `Config.speech_mode/_punct` → `runtime._speech_mode/_punct` + Helfer `speech_transform()`/
  `deliver_seamless()`; die 6 Turn-Dispatch-Stellen (`!dm`/`!redo`/`!start`/`!intro`/`_auto_dm_turn`/`_run_and_deliver`)
  lesen den Modus statt ihn fest zu verdrahten; `_deliver_streaming`/`_deliver_answer` ziehen Transform/Seamless aus
  der Runtime (keine Per-Call-Args). `_intro_speak_seamless` → allgemeiner `_speak_seamless(text, …, transform=…)`,
  von `_deliver_answer` (nahtlos) und `!intro test` (fix nahtlos+flach) genutzt.
- **`!sprechmodus [stream|nahtlos] [flach|intoniert]`** (Aliase `!sprache`/`!voicemode`) schaltet live um, zeigt den
  Stand, warnt bei `nahtlos` vor der CPU-Wartezeit. **+6 Tests** (`tests/test_speech_mode.py`: Config-Defaults/Parsing/
  Fallback + Helfer-Mapping). Suite **316 grün**, Import-Smoke im venv ok. _(D69 ergänzte dann den dritten Modus `puffer`.)_

**Shutdown: „Voice-Channel verlassen" hing wieder bis zu ~30 s — beschränkt (2026-06-14, D67 → ADR 020 Addendum).
Suite 311 grün.** Tobi: das Herunterfahren dauert wieder lange, das Voice-Leave am längsten, obwohl der Bot den
Channel sofort verlässt. Ursache im **installierten** Code verifiziert (nicht in unserem):
- `VoiceClient.disconnect(force=True)` (`voice_client.py:354-356`) ruft intern `_connection.disconnect(wait=True)`
  (hartkodiert); `VoiceConnectionState.disconnect` (`voice_state.py:508-551`) schließt ws+Socket **zuerst** (sichtbarer
  Leave) und **wartet danach** im `finally` per `asyncio.wait_for(self._disconnected.wait(), timeout=self.timeout)` auf
  die Gateway-Bestätigung — `self.timeout=30.0`. Beim Beenden kommt die oft nicht durch → bis zu 30 s Hänger.
- Der Recv-Reader ist **nicht** schuld: sein `stop()` läuft auf einem nicht-gejointen Daemon-Thread (kann nicht blocken).
- **Fix:** neuer Helfer `disconnect_voice(vc, timeout=VOICE_DISCONNECT_TIMEOUT=2.0)` in `dmbot/shutdown.py` (wraps
  `vc.disconnect(force=True)` in `asyncio.wait_for`); `DMBot.close()` ruft ihn + loggt `voice confirm wait abandoned`
  bei Timeout. Sicher, weil der echte Leave vor dem Wait passiert und discord.py den `CancelledError` fängt + sein
  `cleanup()` trotzdem läuft. `!leave` bewusst unangetastet (dort hat der Wait einen echten Zweck). +2 Tests
  (`tests/test_shutdown.py`), Suite **311 grün**, Import-Smoke im venv ok.
- _Live offen: zweimal Strg+C während eines Streams → die Leave-Stufe beendet in ≤ ~2 s (statt der bis-zu-30 s-Hänger);
  bei abgebrochenem Bestätigungs-Wait erscheint die `voice confirm wait abandoned`-Warnung._

**Ursache von „lädt ewigkeiten" gefunden + `!intro` als Schnellstart-Variante (2026-06-14, D66 → ADR 031 Addendum).
Suite 309 grün.** Tobi: `!intro test` klingt „mega geil", aber lädt ewig. Live-Log entlarvte die Ursache —
`XTTS v2 loaded on cpu` + `first_audio=378s` / `tts=314775ms` / `wav=224.2s` (32 Sätze, 3,7 min Audio):
- **XTTS läuft auf CPU** (`.env TTS_DEVICE=cpu`) — **bewusst**, nicht kaputt: die 4070 hält schon nemo + Whisper;
  XTTS auf cuda kippt das VRAM → CUDA-Device-Assert, vergiftet den Prozess, **STT stirbt mit** (live 2026-06-13,
  dokumentiert in `.env` + ADR 002). torch *kann* CUDA (`cu130`, GPU da) — reines VRAM-Koexistenz-Problem.
- **CPU-Synthese < Echtzeit** → lückenlos (`!intro test`) wartet auf die volle Synthese (Minuten). Auf Rückfrage
  wählte Tobi **Schnellstart mit Mini-Lücken**.
- **Umgesetzt:** optionaler `speech_transform` durch `_deliver_streaming`/`_deliver_answer`/`_speak` (nur auf den
  **gesprochenen** Text, Chat-Text unangetastet, D38). Plain **`!intro`** streamt jetzt punktfrei → spricht nach dem
  1. Satz los; **`!intro test`** bleibt die lückenlose Eine-Spur-Variante. Default-Pfad aller anderen Turns
  byte-identisch (Transform nur wenn gesetzt). Suite **309 grün**, `dmcog`-Import im venv geprüft.
- _Live offen: `!intro` (schnell, kleine Lücken) vs `!intro test` (lückenlos, langsamer Start) vergleichen.
  Größerer Hebel: LLM auf 5080 auslagern (`OLLAMA_HOST`/Tailscale → `TTS_DEVICE=cuda`, ADR 002) ODER Monolog kürzen._

**`!intro test`: gechunkte Synthese, aber Wiedergabe als EINE durchgehende Spur (2026-06-14, D65 → ADR 031 Addendum).
Suite 309 grün.** Kollegen-Feedback nach dem 2000-Zeichen-Fix: Aussprache korrekt/ohne Anfälle, aber zäh — Tobi
benannte den Flaschenhals: die **Synthese jedes Satzes** ist die Totstille zwischen den Chunks. Ziel (geklärt per
Rückfrage): nur Chunks vorlesen (kein Gibberish an Satzzeichen), aber es soll wie **ein voller zusammenhängender
Text** klingen. Harte Randbedingung: XTTS langsamer als Echtzeit → sofortiger Start UND lückenlos geht nicht gleichzeitig;
„klingt wie voller Text" ⇒ Lückenlosigkeit gewählt, Vorsynthese-Wartezeit bewusst in Kauf genommen.
- **`_deliver_intro_chunked` umgebaut** (`dmbot/voice/dmcog.py`): statt seriellem `_speak` pro Satz wird jeder Satz
  einzeln punktfrei synthetisiert (neuer Helfer `_intro_speak_seamless`), die WAVs via `concat_wavs` mit
  `_INTRO_SENTENCE_PAUSE_S` (0,2s) zu **einer** Spur gefügt und in **einem** Bridge-Call gespielt → durchgehend,
  natürlich getaktet, kein Gibberish. try/finally räumt alle Temp-WAVs auf; Pause während Synthese bricht sauber ab.
- **`wavio.concat_wavs`** neu (torch-frei aus `xtts._concat_wavs` herausgezogen, das jetzt dorthin delegiert) — so kann
  die Cog die Join-Logik nutzen, ohne die schwere XTTS-Lib zu laden.
- **+3 Tests** (`tests/test_silent_wav.py`): Reihenfolge+Gap, Null-Gap = reine Konkatenation, Einzelteil ohne
  Trailing-Gap. Suite **309 grün**. _(D66 zeigte dann: der lange Start lag v. a. an XTTS-auf-CPU; plain `!intro` wurde
  zur Schnellstart-Variante, `!intro test` blieb die lückenlose.)_

**`!intro`-Crash beim Kollegen gefixt: Discord-2000-Zeichen-Limit (2026-06-14, D64). Suite 306 grün, committet +
gepusht (`1d48b18`).** Live-Befund aus Kollegen-Run: `!intro test` warf `HTTPException: 400 … 50035: Must be 2000
or fewer in length`. Ursache: die volle Antwort wurde in **einem** `channel.send` gepostet, aber der `!intro`-
Monolog läuft auf großem Längen-Budget (`DM_INTRO_NUM_PREDICT` 800) und sprengt Discords 2000-Zeichen-`content`-Cap.
- **Fix am einzigen Sende-Choke-Point** `SessionRuntime._send_with_retry` (`dmbot/runtime.py`): langer `content` wird
  in ≤2000-Zeichen-Nachrichten zerlegt; `view`/`embed` reiten auf der **letzten** (Würfel-Button/Turn-Order bleibt
  unter dem vollen Text). Der 5xx-Retry ist in einen `_send_once`-Helfer gewandert. Deckt **alle drei** Lieferpfade
  (Batch/Streaming/`!intro test`) auf einmal ab.
- **Neuer reiner Splitter** `split_for_discord` in `dmbot/tts/textsplit.py`: **verbatim** (verwirft nichts, anders als
  der TTS-`chunk_text`), bricht am spätesten Absatz-/Zeilen-/Satz-/Wortrand ≥ halbem Limit, Hard-Cut nur bei einem
  ungebrochenen Über-Limit-Lauf.
- **+4 Tests** (`tests/test_tts_chunk.py`): kurz=1 Stück, langer Monolog splittet verbatim unter Limit, Satzgrenze
  bevorzugt, ununterbrochener Lauf wird hart geschnitten. Suite **306 grün**.

**Kontext-Kosten-Refactor: `progress.md`/`CLAUDE.md` in schlanke Live-Dateien + on-demand `docs/` aufgeteilt
(2026-06-14, D63 → ADR 032). Suite 302 grün, committet + gepusht (`fa6c96d`).** Tobi (Plan-Modus): „der kontext ist
mittlerweile sehr groß und kleinste sachen fressen viele tokens — kann man sachen aus der claude.md auslagern …
und sowas auch mit der progress.md machen?". Geklärt + umgesetzt:
- **`progress.md` 1637→678:** `## Last session`-Historie (D32–D61), Done-Phasen 0–8 (volle Checklisten +
  `VERIFY EVIDENCE`) und ✅-erledigte/abgeschlossene Open Questions **verbatim** nach **`docs/progress-archive.md`**.
  Live bleibt: Current focus, Next step, **kompletter Decision-Log + Phase→ADR-Map**, offene Phasen 9/10 (voll),
  und **alle tatsächlich offenen Fragen** (Tobis Vorgabe). Done-Phasen als Einzeiler + Archiv-Pointer.
- **`CLAUDE.md` 226→153:** per-Modul-Konventionen (DMbot/Rules/Memory/RAG), Testing, Runtime, Troubleshooting,
  Style → **`docs/conventions.md`** (on-demand, in die „read on demand"-Tabelle + README verdrahtet). Inline bleibt:
  Session-Ritual, Golden Rules, Repo-Layout, schlanke Bot-A-Kurzfassung, neuer **Key gotchas**-Block.
- **Rotations-Regel** (CLAUDE.md `## Session ritual` + session-ritual-Skill): beim Eintragen eines neuen
  `## Last session`-Eintrags wandert der vorherige ins Archiv → die Live-Dateien bleiben dauerhaft schlank.
  _Dieser Wrap-up übt sie aus: der D62-`!intro`-Eintrag ist nach `docs/progress-archive.md` rotiert._
- **Konsistenz:** 9 Code-Kommentar-Zeiger (`preflight`/`__main__`/`vad`/`state`/`persona`/`orchestrator`/`resample`)
  von `CLAUDE.md` auf `docs/conventions.md` umgebogen, da ihre zitierten Anker dorthin umgezogen sind.
- **Verifiziert:** 3 parallele read-only Audits (Inhalts-Konservierung verbatim / Querverweise / Live-Korrektheit) →
  alle PASS; Suite **302 grün** (reine Doku-/Kommentar-Änderung). Effekt: ~17K Tokens/Session + ~1.5K/Turn.

**`!intro` — Eröffnungs-Monolog für Chemical Burn, der die Charaktere einbezieht (2026-06-14, D62 → ADR 031).
Suite 300 grün, live-unverified.** Tobi (Plan-Modus): „für chemical burn braucht es eine intro sequenz, in der
der bot erklärt was abgeht, wo man sich befindet, wie man hergekommen ist — und er soll die charaktere mit
einbeziehen." Geklärt: **ein langer Monolog** (kein Skript), als **neuer `!intro`-Befehl** (das kurze `!start`
bleibt), mit **voller Figuren-Tiefe**. Umgesetzt durch **Wiederverwenden + Parametrisieren** des bestehenden
`!start`-Eröffnungspfads (nicht duplizieren, ADR-030-Disziplin), Code-Files per Fan-out über parallele Agenten
auf disjunkten Dateien:
- **`CharacterStore.intro_roster_de()`** (`characters.py`): kompaktes deutsches Party-Roster aus `Character.raw`
  (concept/origin/faction/distinguishing/goals/connections/arc, tolerant gegenüber schlanken `_example`-Sheets,
  Mehrzeiler-Felder auf eine Zeile kollabiert, `""` bei leerem Store).
- **`build_intro_director_msg(roster)`** (`orchestrator.py`): `[Regie]`-Instruktion für **einen** zusammenhängenden
  Monolog (Ort → Ankunft → Auftrag aus Szenenkarte/Summary, dann pro genannter Figur ein persönlicher Moment —
  einweben, geheime/private Ziele nur andeuten, keine Probe). Das Roster reitet in der **Director-(User-)Message**
  mit → ADR-019-Prompt-Reihenfolge unangetastet. Bei leerem Roster degradiert die Instruktion sauber.
- **`num_predict`-Override** durch `_build_request`/`_chat_once`/`_generate`/`_stream_and_store`/`respond_opening`/
  `respond_opening_streaming` durchgereicht (Default `None` → bisheriges Verhalten; alle Altaufrufer unberührt).
  `!intro` läuft auf `DM_INTRO_NUM_PREDICT` (Default **800**; `config.py` + `runtime._intro_num_predict`).
- **`!intro`-Command** (`dmcog.py`, Aliase `einleitung`/`eroeffnung`), modelliert auf `start`: Pause-/Session-Guard,
  Szenen-Pointer deterministisch auf `start_scene` **nur falls ungesetzt** (golden rule #3, kein Reset laufenden
  Fortschritts), Würfel unterdrückt (`_last_action` bleibt None), Stream- **und** Batch-Pfad mit Längen-Override
  (`_deliver_streaming(opening=…, opening_num_predict=…)` bzw. `respond_opening(…, num_predict=…)`). `!start` exakt
  unverändert.
- **Tests:** neues `tests/test_intro.py` (+7): Roster (Volltiefe, lean-Sheet-Toleranz, leerer Store), Director-Shape
  (mit/ohne Roster), `num_predict`-Override greift / Default bleibt 220. Volle Suite **300 grün** (293 → 300).
  Cog importiert sauber, `DMCog.intro` vorhanden. _Offen: Live-Gate (s. Next concrete step)._
- **Nachrunde, testweise Delivery-B-Variante (Tobi): `!intro test`.** Gleicher generierter Monolog, aber andere
  **Sprachausgabe**: erst komplett im Batch erzeugen, dann **satzweise** vorlesen — jeder Satz **ohne jegliche
  Satzzeichen** (`strip_speech_punctuation` = Whitelist, nur Buchstaben/Ziffern/Leerzeichen, inkl. Wort-Bindestrich
  raus — Tobi „alle satzzeichen raus"; XTTS verhaspelt sich an Satzzeichen, D55) über ein eigenes blockierendes
  `_speak`, mit **0,2 s Pause** zwischen den Sätzen (`_deliver_intro_chunked` + `_INTRO_SENTENCE_PAUSE_S=0.2`),
  statt des nahtlosen Streamings — zum Vergleich des Feels. Der gepostete Chat-Text behält die Satzzeichen
  (lesbar, D38). **Nicht** die verworfene Multi-Beat-Sequenz (weiter eine Generierung). Hinter dem `test`-Arg,
  Default-`!intro` unverändert; +2 Unit-Tests für `strip_speech_punctuation` (Delivery-Pfad selbst nicht
  unit-testbar — Live-Vergleich). Wenn es sich nicht bewährt: `test`-Arg + Helfer wieder raus.

**Doku: drei Setup-Dokumente in eine Root-`SETUP.md` zusammengeführt (2026-06-14). Kein Bot-/Phasen-Change,
Suite unverändert 293 grün.** Tobi fragte, ob die SETUP.md noch passt und alles aus der Checkliste drin ist.
Befund: dem B9-Rebuild-Block in `docs/SETUP.md` fehlte die `conditions`-RAG-Quelle, die `docs/CHECKLIST.md`
*und* `retrieve.py` (`_SOURCES`) führen — ein Rebuild strikt nach SETUP.md hätte eine `rag.db` ohne die
deutschen Zustands-Spielwerte gebaut. Tobi wollte alles in **einer** Root-Datei. `docs/SETUP.md` (externe
Prereqs) + `docs/CHECKLIST.md` (Fremd-Maschine) → **Root-`SETUP.md`** gemerged, durchgehend Englisch; die
B1–B9-Labels behalten, damit „SETUP.md B5"-Verweise weiter stimmen. `conditions`-Quelle nachgetragen (alle 7
`_SOURCES` jetzt abgedeckt), B8 auf „Live-Party liegt im Repo" aktualisiert, Tests-Befehl auf
`uv run --with pytest python -m pytest` korrigiert. Alle Live-Verweise (README / architecture / roadmap /
progress / CLAUDE.md / session-ritual-Skill + `vad.py`/`piper.py`-Fehlerstrings) auf die Root-Datei gezogen;
die zwei `docs/`-Dateien gelöscht; historische Erwähnungen (progress-Log, ADR 012) bewusst stehen gelassen.
Commit `a6a011c`. _Kein D-Eintrag/ADR — Doku-Housekeeping, kein Bot-Design._

**Dev-Tooling: projekt-eigene Claude-Code-Skills + Test-Hook (2026-06-14). Kein Bot-/Phasen-Change, Suite
unverändert 293 grün.** Tobi fragte nach Skills für den schnelleren Ausbau. Angelegt unter `.claude/skills/`
(committed via `.gitignore`-Allowlist; `settings.local.json` bleibt lokal): **playtest-triage** (Live-Log →
diagnostizieren → deterministisch fixen → Suite → committen), **rules-subsystem** (neues Profil-Subsystem im
Psyker/Augmetik-Muster), **rag-ingest** (PDF → ingest → kalibrieren → verifizieren), **character-build**
(IM-Charakter validieren+einbauen, Session-Merge erst nach Bestätigung), **session-ritual** (Handshake +
Wrap-up + nächste ADR). Plus ein `Stop`-Hook (`tools/hooks/test-on-change.sh` + committed
`.claude/settings.json`): Suite nur bei Änderungen unter `dmbot/`/`tests/`/`data/systems`, **still bei Grün**
(Output nur bei Rot); `.gitattributes` pinnt `*.sh` auf LF. Index aller Skills in `.claude/skills/README.md`.
_Kein D-Eintrag/ADR — Dev-Workflow-Infra, kein Bot-Design; Rationale im Skills-README._

**Code-Review-Korrektheitsrunde (2026-06-13, D61 → ADR 030). Suite 293 grün, live-unverified.**
Tobi: `/code-review` über die Tagescommits, „Funktionalität soll bleiben", danach „fix alles fan out".
Review als Multi-Agent-Fan-out (9 Finder-Winkel über `5d672b6~1..HEAD` + Pro-Fund-Verifizierer); Fixes
über 7 Agenten auf disjunkten Dateien, zentral mit der vollen Suite verifiziert.
- **9 Korrektheits-Fixes (alle verifiziert, funktionserhaltend):** (1) Warp-Containment → `Disziplin
  (Psi)` via neuem `ResolvedManifest.contain_base` (`characters.py` + `dicecog.py`); (2) Party-Psyker
  nicht in WorldState → einmalige DE-Warnung statt stillem Warp-Charge-Verlust (`dicecog.py`); (3)
  `_deliver_answer` awaitet Dice/Scene-Tasks im `finally` (`dmcog.py`); (4) Auto-Recap `clear_history`
  löscht nur den `summarize`-konsumierten Präfix via `_compact_consumed` (`orchestrator.py`); (5)
  Marker-Regex `\b`→`[\s:]*`, verklebte Marker greifen (`marker.py`); (6) `resolve_test`
  Signatur-Dispatch statt `except TypeError`-Retry (`engine.py`); (7) Streaming cancelt verwaiste
  Tasks + drained WAVs (`dmcog.py`); (8) VadSink-Mute = Tiefenzähler (`recv.py`); (9) Soak via
  `skill_value` strip+CI (`dicecog.py` + `characters.py`).
- **Cleanup/Efficiency:** geteilter `SystemProfile._catalog_lookup` (`profile.py`); geteilter
  `dmbot/tts/wavio.write_silent_wav`; toter `reduce_warp_charge` entfernt (`state.py`); no-op `[:80]`
  auf Konstanten weg (`scene.py`); thread-lokale gecachte sqlite-Connection + Tuple-Rebuilds weg
  (`retrieve.py`); `<<`-freier Fast-Path im `StreamAssembler` (`orchestrator.py`).
- **Bewusst NICHT gemacht:** die Altitude-Punkte (system-agnostische Generalisierung von
  `warp_charge_gain`/`reverse_d100`, der per-Marker-Pipeline, `_SOURCES`/`_is_junk_hit`) — aufgeschoben
  auf den Zweitsystem-/Phase-10b-Punkt (ADR 005); kein zweites System zum Generalisieren da, groß +
  verhaltensriskant. Ebenfalls nicht angefasst: Layer-2-Mute bleibt default-off (D25), XTTS-Sampling
  (D55), Persona-Text; der `marker.py`-`profile`-Param blieb (ein Test außerhalb des Filesets ruft ihn).
- **Verifikation:** volle Suite **293 grün** (+~30 fixed-seed/Unit-Tests in den gefixten Bereichen,
  ein RAG-Fixture-mkdir-Fix). Zwei versehentliche Agenten-Artefakte (`C:…*.diff`) entfernt.

**Cog-Split-Refactor (2026-06-13, D60 → ADR 029). Code-complete, Suite 263 grün, live-unverified
(Smoke-Test reicht).** Reiner Struktur-Refactor (nach Tobis Cog-Split-Spec), Plan-
Modus zuerst, Umsetzung über parallele Agenten auf disjunkten Dateien.
- **Schnitt:** `dmbot/runtime.py` `SessionRuntime` hält allen geteilten State (Brain+OllamaClient,
  STT/TTS, Bridge, Profil+Characters, RAG, Adventure, per-Channel-WorldState, Pause/PTT/Mute-Flags)
  + die State-Helfer (`_persist_and_refresh`/`_set_scene`/`_load_*`/`_send_with_retry`) + die STT/VAD-
  Callbacks (der Transcriber wird hier mit `_on_transcript` gebaut). In `__main__.setup_hook` einmal
  aus `Config` gebaut, in jede Cog injiziert — die 26 Konstruktor-kwargs sind weg.
- **3 Cogs (Tobi-Entscheid statt 4):** VoiceCog (join/leave/vstatus/mic/pause, VAD-Sink),
  DiceCog (roll/test/turn/rules/npc/damage/heal, Würfel+Manifest-Buttons, Auto-Kampf, Turn-Order),
  DMCog (Delivery batch+streaming, `_speak`, Auto-Recap, !dm/!redo/!start/!wrap/!say/!voice + Szenen
  !ort/!szenen/!ortmodus + `<<ORT>>`-Marker + !lore). **Kein `bot.get_cog`:** 5 Runtime-Hooks
  (`run_and_deliver`/`auto_dm_turn`/`handle_dice`/`reanchor_mic`/`post_turn_order`), je von der
  besitzenden Cog im `__init__` registriert.
- **Verschoben statt umgeschrieben:** Methoden-Bodies byte-identisch, nur `self._X → self._rt._X` +
  Hook-Calls; Agenten belegten das per AST/Reverse-Rename-Diff, plus mein Spot-Check der untesteten
  Streaming-Pipeline (`_deliver_streaming`). Boot-Pfad unverändert (Preflights einmal, gleiche
  Reihenfolge); `TEARDOWN_STEPS`-Summe bleibt 4 → Shutdown-Anzeige byte-identisch.
- **Zeilenbilanz:** `commands.py` 2300 (1 Klasse) → runtime 565 / voicecog 412 / dicecog 568 /
  dmcog 838 = 2383 über 4 Module (Mehr = 4× Header/Imports/`__init__`-Gerüst; kein Code verloren).
- **Tests:** 263 grün. Nur Import-Pfade angepasst (`test_context_budget`, `test_autorecap`) + **eine**
  Fixture-Verdrahtung (`test_autorecap` baut die Bare-Cog jetzt mit einer Stub-Runtime statt flacher
  Attribute) — Assertions unverändert; gemeldet, da über reine Imports hinaus (Spec-Smell-Check).
- **Funktional gegengeprüft (ohne Discord):** der `!rules`/`!lore`-Pfad — den die Cogs jetzt über
  `self._rt._retriever` / `self._rt._brain` aufrufen — live gegen `rag.db` + Ollama getestet: 4 Fragen
  (kritischer Erfolg, Zustand Blutend, Gott-Imperator, vier Chaosgötter) treffen die richtigen Quellen
  (d=0.29–0.40) und liefern korrekte, gegroundete Antworten. Offen bleibt nur der **Voice-Smoke-Test**
  (`!join`→sprechen→`!dm`→Würfel→`!leave`), der die zwei Bots im Channel braucht.
- _Kosmetisch (kein Verhaltens-/String-Change): verschobene Log-Calls tragen ihren neuen Modulnamen
  in der opt-in `debug.log`-`%(name)s`-Spalte + in WARNING-Konsolenzeilen (`runtime`/`voice.dmcog`
  statt `voice.commands`); die Log-Messages + Green-Chat/Transcript-Formatierung sind unverändert
  (Filter keyen auf Message-Inhalt + `dmbot`-Präfix, verifiziert)._

**Erste Live-Runde → Playtest-Fix-Runde (2026-06-13, D57–D59, ADR 027/028). Code-complete,
live-unverified.** Die erste echte Runde (Channel circlejerk, Party Gellicus/Fridolin/Rektalus)
lief „teils besser als davor", aber die Hauptklage war: **der Bot geht null auf die Story ein,
sagt am Anfang nicht, was abgeht, und führt nicht durch die Geschichte.** 13 Kritikpunkte aus dem
annotierten Log gezogen; Wurzel-Diagnose + Fixes über parallele Agents (Tobis Vorgabe). Suite
**246 → 262** grün.
- **Smoking Gun (D57 → ADR 027):** `num_ctx` lief real auf **8192** (hartkodiert in `client.py`;
  die 24000, die Tobi zu setzen glaubte, wurden nirgends gelesen). Ab ~Turn 16 lag der Prompt
  >85% → Ollama trunkiert den **Kopf zuerst: Persona + Abenteuer-Zusammenfassung**. Das erzeugte
  gleichzeitig Story-ignoriert, zu lange Antworten, Puppeting, Vorweg-Auflösung. Fix: `num_ctx` per
  `OLLAMA_NUM_CTX` konfigurierbar (Default **24576**, läuft jetzt auf einer 4080) **+** rollierender
  **Auto-Recap** (`DM_AUTORECAP`, default an): bei Budget-Überschreitung nach dem Zug kumulativ
  zusammenfassen (`summarize(..., prior_recap=…)`), wie `!wrap up` persistieren und die
  In-Memory-History leeren → Kopf wird nie mehr trunkiert (der von Pr0degie gewünschte „Handoff").
  _Abweichung von der `prompt-6`-Spec: compact-and-clear am echten Budget-Signal statt
  fold-before-trim — Naht „kein Verbatim-Verlauf direkt nach Kompaktion" als Verfeinerung notiert._
- **Eröffnung + Persona (D58):** neuer **`!start`** (Aliase `!briefing`/`!auftrag`) erzählt das
  `auftrag`-Briefing (Halikarn, Mission, Spuren als Atmosphäre) über die bestehende Stream-/Speak-
  Pipeline; eigener `respond_opening*`-Pfad unterdrückt Würfel-Routing. Persona (`dm_core_de.md`):
  Szenenziel im Blick + sanft auf offene Spuren lenken, **jeder Zug endet mit Welt in Bewegung**
  (NSC handelt/spricht, nie flache Beschreibung die stoppt), **Spotlight** auf andere/stille
  Figuren namentlich.
- **RAG entrauscht (D59 → ADR 028):** `_is_junk_hit` filtert OCR/Statblock-Müll (Dash-Runs,
  `(eLite)`-Tags, Picture-Text) aus dem Pro-Turn-Block; `MAX_DISTANCE` bleibt 0.45, recall@1/@3
  unverändert. Offen: `WARRIOR`-Epigraph-Zeilen brauchen Re-Chunking beim Ingest.
- _Offen / Modell-Ceiling: generische Wurf-Ergebnistexte, NSC-Name/Genus-Halluzinationen, Reste
  von Wiederholung/Vorweg-Auflösung (nemo-12B-Grenze); die Marker-vs-Router-Spannung (#6,
  Inline-`<<TEST>>` verworfen, Router feuert nach der fertigen Erzählung) als spätere Designfrage.
  Live-Gate nächste Runde: `!start` spricht das Briefing, kein `[ctx] … truncating`-Warning mehr
  (bzw. Auto-Recap greift sichtbar), DM nennt Spuren/Szenenziel, kein 📚-Garbage bei reinem RP._

**Auto scene transitions — `<<ORT …>>` marker + confirm button (2026-06-13, ADR 026).** `!ort <id>`
was a manual, human-only pointer move (ADR 019). Now the DM-LLM can *request* a move in-band, code
validates + a human confirms — mirroring the dice/`<<TEST>>` pattern (golden rule #2), so golden
rule #3 still holds (the model never *writes* `scene_id`, only requests).
- **Marker:** third extractor `extract_scenes` in `dmbot/rules/marker.py` (profile-free — scenes
  belong to the *adventure*, not the rules profile) + `SceneRequest`. Reuses the `<<…>>` delimiter so
  the existing strip/withhold TTS guards apply for free.
- **Orchestrator:** `finalize_answer` 3→4-tuple (+`scenes`), `StreamResult.scenes`, `_pending_scenes`
  queue drained via `take_pending_scenes` — queued **only under the `_last_action` post-roll guard**
  (a results-only consequence turn must not move the pointer; same guard tests/manifests use).
- **Move + validation:** `ort()` core refactored into shared `_set_scene(state, id)`; new pure
  `Adventure.resolve_move(current, target, mode)` (unit-tested, no Discord) — `verbunden` (default)
  accepts only the current scene's `leads_to` neighbours, `frei` any known scene; illegal/unknown/
  no-op → None.
- **UI/flow:** `dmbot/discord_ui/scene.py` `SceneChangeView` (Wechseln/Abbrechen, modelled on
  `DiceTestView`); cog `_handle_scene` posts the confirm button from both delivery paths (batch +
  streaming), the move happens on click. Mode is a cog setting: `DM_SCENE_MODE` default + runtime
  `!ortmodus [verbunden|frei]`. Manual `!ort` stays as override.
- Persona bullet in `prompts/dm_core_de.md` ("nur wenn die Gruppe ihn wirklich betritt"). ADR 026.
  Suite **246** (was 234; +12 scene-marker tests). **Live-unverified** — needs a session to confirm
  the marker fires, isn't spoken, and the button moves the pointer.

**Interactive `!lore tts` reader + anti-repetition persona rule (2026-06-13).** Three asks (eval'd
in plan mode against efficiency/speed/correctness):
- **`!lore tts` is now a manual block-by-block reader** (`dmbot/discord_ui/lore_read.py` →
  `LoreReadView`, modelled on `RulesView`): each lore block's **text is shown in chat** and read
  aloud; **⏭ Weiter** advances to + reads the next block (a fast click-through coalesces to the
  latest shown block — Bot A's `/speak` blocks per WAV with no stop, so a running block can't be
  cut mid-playback, one speak task in flight), **🔊 Nochmal**, **⏹ Stopp**. `_lore_speak` rewritten
  to build/post the view; dispatch unchanged.
- **Repetition** (DM re-explained established facts in full): persona rule in `prompts/dm_core_de.md`
  — what's in "Was bisher geschah", the world state and the ongoing scene is **already known to the
  players**; reference it briefly, describe only **new** things + consequences — and the recap label
  in `_build_request` sharpened to "(den Spielenden bereits bekannt — nicht erneut ausführlich
  erzählen)". Prompt-only; live-observe nemo's adherence (a code guard is the fallback, not built).
- **"Reads each block twice":** verified **NOT in DMbot** (lore_pages 17 clean pages, loop/synth/
  concat all 1×, no custom `on_message`) → it's **Bot A's playback** (separate musicbot repo). Beleg
  beim Test: one `🔊 TTS … speaking` + one `/speak` per block in `debug.log`. Suite **234**.

**RAG calibration + a German conditions glossary source (2026-06-13).** Reviewed the open task
prompts 2/5/6 against the goal (efficiency/speed/correctness): did **prompt 5** (RAG calibration —
highest value/risk ratio), deferred 6 (gated on the unmet Phase-9 live gate), skipped 2 (pure
maintainability, zero bot benefit). Built a golden set (`tools/rag_golden_set.json`, 21 positives /
10 negatives, committed — own questions + expected source/heading, no rulebook passages) and
`tools/rag_calibrate.py` (imports the real `retrieve.py` path; per-query hits, recall@1/@3, a
0.35–0.60 threshold sweep per context; report → gitignored `tools/rag_calibrate_report.md`).
- **Finding:** positives (rule questions) and negatives (narration) overlap badly in the embedding
  space — no threshold separates cleanly, so `MAX_DISTANCE` **stays 0.45** (the data didn't support
  a confident change). The real gaps were **content/chunking**, not the threshold: German condition
  names ("Blutend") missed the English condition chunks, and weapon-stat **tables** don't retrieve.
- **Fix (correctness):** a hand-authored German **conditions glossary** — `data/rules_de/conditions.md`
  (12 Zustände, own words grounded in the rulebook), new RAG source **`conditions`** (13 chunks →
  `## Regelwerk`), wired into `_SOURCES` and the `!rules` search. Each section leads with its German
  name **in the body** (the ingest embeds the body, not the heading), which pulled the specific chunk
  to the top (Blutend 0.40→**0.29**). Live: `!rules` now answers Blutend/Betäubt/Vergiftet/Brennend
  **exactly right** (before: Blutend hallucinated). recall@1 38%→**52%**, recall@3 67%→**81%**, narration
  hits 13→**15/21**, **zero** new negative leaks. Store **2482 chunks**, suite **230**. New committed
  source category `data/rules_de/` (`.gitignore` allowlist; pattern of ADR 021). _Open: weapon/stat
  tables still don't retrieve (table-row chunking) — a separate ingestion session._

**Faster startup — background TTS load + parallel Ollama warm-up (2026-06-13 → ADR 024).** Tobi
liked the fast shutdown (ADR 020) and asked for a faster start, then "robust und zuverlässig".
Two synchronous boot costs blocked "bot ready": the XTTS/Coqui load (torch + GPU, several seconds)
in the cog `__init__`, and `start_dmbot.bat`'s `ollama run` warm-up (~15 s cold) *before* launch.
- **TTS now loads on a daemon thread** → `on_ready` fires immediately. A `_tts_enabled` flag drives
  the is-speech-on checks (replacing `self._tts is not None`), and `_synthesize()` waits on a
  `_tts_ready` event **inside the worker thread** (never the loop), so the first spoken line waits
  for the model only if still loading (virtually always warm by first `!join`+speech).
- **`start_dmbot.bat`** backgrounds the model warm-up (`start /b`) so it overlaps boot; the
  boot-time `check_ollama` preflight (reachability + model pulled) is unchanged — only residency is
  deferred. Single-GPU Ollama queues the first turn behind the warm-up; 300 s read timeout covers it.
- **Robustness hardening** (restores ADR 020-era fail-fast without re-blocking boot): bounded wait
  (`_TTS_LOAD_TIMEOUT_S` 90 s → a hung load degrades to text-only, not a frozen synth); loud boot
  logging (`loading … / ready in N s / FAILED`); a `!join` guard that announces ⚠ no-speech / ⏳
  still-loading. Suite **230**. _Live-verify: console reaches "logged in as" fast; `!join` shows the
  notice when relevant; first DM sentence is spoken._

**New player party assembled + deployed, Inquisition guides into the RAG (2026-06-13).** A
player-prep + content session, no core-pipeline change.
- **New party (replaces Garran/Eli/Yann):** built **Fridolin Feuchtgebietheld** (Schreinwelt
  Inquisition interrogator + stealth psyker) via the §how-to rules + ADR 022 (all `known_powers`
  hit the catalog); **Gellicus Schulz** (Timo) + **Rektalus Zerfickus** (Sezgin) came from a parallel
  session, validated (budget 90 / wounds / weapons) and given full backstory. All three live under a
  **committed `data/party/`** (one JSON per player; `.gitignore` allowlist) with filled PDF sheets
  (sheets stay local — bought-sheet derivatives).
- **Deployed to circlejerk:** merged the three into `data/sessions/1343673766487654464/characters.json`
  (+ aliases) and **committed it** (allowlisted) so the bot loads the party on a teammate's clone; the
  old party's sheets archived to `…/archive/2026-06-13_alte_party/`. No `state.json` → first `!join`
  seeds fresh. _Caveat: a different Discord channel needs the file copied into its own `<id>/` folder._
- **Self-service character creation:** `docs/character-creation-prompt.md` — a standalone prompt that
  interviews a new player and emits a budget-correct character JSON (stats + optional psyker + augmetics).
- **Inquisition guides into the RAG** (see Current focus): Player's Guide whole (`player_guide`, 502)
  + GM-Guide spoiler-trimmed (`gm_guide`, 226); `!rules <frage>` now also searches both. Store 2469
  chunks, suite **230**. Docs synced (bge-m3 everywhere, CHECKLIST/SETUP rebuild lists, augmetics).

**Player-prep tooling + `!rules <frage>` (2026-06-13, D50).** A session of player-facing prep and one
new command, no core-pipeline change.
- **`!rules <frage>` answers a rule question from the book (D50).** `!rules` with no arg still pages
  the system's short rules; with a question it retrieves the matching rulebook chunks
  (`source=rulebook`, `lookup(..., max_distance=0.55)`) and the new `DMBrain.answer_rules` has the
  LLM synthesise a **short German answer grounded only in those excerpts** (golden rule #7 — say so
  when the book doesn't cover it; never invent rules). Unlike `!lore <frage>` (raw curated German
  chunks), the rulebook is English layout-soup → an LLM translate/condense step is needed. No hits →
  honest "nichts im Regelbuch". Reading material, never spoken. Verified end-to-end against the live
  store (Ausweichen, kritischer Treffer → correct grounded answers); +3 unit tests. **Suite 191.**
- **Character-creation guide made self-explanatory** (`docs/how-to-create-a-character.html`): a new
  un-numbered **glossary** ("Begriffe") explaining dice notation (1W10+5), bonus = tens digit, how a
  d100 roll-under Probe + difficulty ladder + EG work, and — the main stumbling block — wounds/soak/
  kampfunfähig (`Waffe + EG − Soak`, 0 = down), plus origin and inventory explainers; all grounded in
  the profile + `engine.resolve_damage`. Compact at-a-glance **homeworld** and **weapon** tables added
  at the form's dropdowns so you don't click through.
- **Character-sheet filler reworked to editable PDFs** (`tools/fill_character_sheet.py`): the bought
  sheet is a graphical raster, so every value is now a real **AcroForm text field** (transparent fill)
  pre-filled with the computed value — editable in any reader. **Every** fillable area is a field now
  (all skill rows, weapon/armour/hit-location tables, talents, influence, psychic powers, equipment,
  multi-line goals/connections/notes/combat-notes), with grid/multiline helpers; positions read off
  the raster by pixel analysis (fixed weapon-row drift, the page-1 skill/spec 20-px cumulative drift,
  distinguishing/XP, encumbrance, Body hit-location). New `tools/example_garran_vex.json` (own grimdark
  flavour, committed) drives a fully filled Garran Vex example → `data/pdfs/Garran_Vex.pdf` (git-ignored
  derivative). Back-compat: the mechanical party file still renders. Note: the three Initiative
  Melee/Ranged/Reflexes boxes are a quick-reference (not a required derived stat, IM p.88).

**Lore-Korpus: kuratiertes deutsches Imperium+Chaos-Kompendium (2026-06-13, D48 → ADR 021).**
Tobi fragte „ist die Lore drin?" → Live-Probe gegen `rag.db`: Menschen-Lore trifft aus dem
englischen Rulebook (Imperium d=0.27, Inquisition d=0.34), aber **Chaos-Kosmologie existiert in
den IM-Büchern nicht** („vier Chaosgötter" d=0.53 miss — by design, Chaos als verborgener
Horror); Tyraniden/Necrons/T'au ebenfalls leer (Tobi: bewusst ok). Beschlossen + gebaut:
- **`data/lore/imperium.md` (18 Chunks) + `chaos.md` (17 Chunks)** — handgeschriebene deutsche
  Lore, grimdark in-world (Tobis Wahl: zwei Dateien, beide ausführlich, grimdark). Imperium:
  Imperator/Thron/Astronomican/Custodes/Ekklesiarchie, High Lords/Zehnt, Astartes, Militarum,
  Flotte, Mechanicus, Inquisition+Ordos, Astropathen, Navigatoren, Psioniker, Macharian-Kontext.
  Chaos: Warp/Gellerfeld, die vier Götter (je eigene Sektion), Großes Spiel, Dämonen-Taxonomie,
  Korruption/Kulte, Horus-Häresie + Horus, Chaos Space Marines, Antwort des Imperiums.
  **Committed** (Tobi, Nachrunde gleicher Tag): anders als das Abenteuer-Kompendium keine
  Buch-Ableitung, sondern eigene Formulierung frei zugänglichen 40k-Allgemeinwissens —
  `.gitignore`-Allowlist um `data/lore/*.md` erweitert.
- **`retrieve.py`:** `_SOURCES` + `lore_imperium`/`lore_chaos` (→ `## Weltwissen`), Reihenfolge
  Regeln → breite Lore → lokales Rokarth; `setting`-Label um „lokaler Hintergrund" geschärft.
  Selbstverdrahtend, sonst kein Code-Change. Schwelle bleibt 0.45 global.
- **Probe-getunt:** Entitäts-Sektionen brauchen den definitorischen Satz oben („Wer ist Horus?"
  0.51→0.43 nach eigener `### Horus`-Sektion; „Chaos Space Marines" 0.46→0.36). 24-Fragen-
  Finalprobe: alle Ziel-Fragen treffen die richtige Quelle <0.45; Regressionen sauber (Regelfrage
  → rulebook, Rokarth → setting, Table-Talk + Voll-Spoilerfrage stumm). Tests +2 (Weltwissen-
  Block + Block-Reihenfolge), Suite **183/183**. _Live-Gate offen: `📚 lore_…`-Logzeile in einer
  echten Session._
- **Nachrunde (Doku für den Kollegen):** **`docs/CHECKLIST.md`** (von Tobi aus HANDOVER.md
  umbenannt) — was eine fremde Maschine privat von Tobi braucht (PDFs+md, Abenteuer-Kompendium,
  `rag.db` oder die Rebuild-Befehle) vs. was der Clone mitbringt; **SETUP.md**: B2 stale
  `nomic-embed-text` → `bge-m3` korrigiert + neue **B9-Sektion** (RAG-Store kopieren/neu bauen,
  `DM_ADVENTURE`, `📚`-Sanity-Check) + TL;DR-Schritt 8; README-Transfer-Sektion gefixt
  (bge-m3, CHECKLIST-Link).
- **Nachrunde 2 — `!lore`-Command (D49):** `!lore [topic]`/`!hintergrund` blättert
  `data/lore/<topic>.md` (ohne Arg → imperium, `!lore chaos` → Chaos) über die bestehende
  `RulesView`; neuer pure Parser `dmbot/rag/lore.py` (`lore_pages`: Heading = Seite, H1 +
  Quellen-Blockquote geskippt, 4000-Zeichen-Guard) + `tools/lore_to_html.py` → `docs/lore.html`
  (grimdark Standalone — Tobis Review-Ansicht + Spieler-Handout; nach Lore-Edits neu
  generieren). Kein TTS, kein DM-Turn. Tests +4, Suite **187/187**. Review erledigt: Tobi las
  `docs/lore.html`, ein Begriff-Fix (Gottkaiser → Gott-Imperator, in die md gesynct +
  re-ingestet) → committed.
- **Nachrunde 3 — `!lore <frage>` (D49-Erweiterung, Tobi):** der Command kann jetzt Fragen
  gegen die DB beantworten — `RulebookRetriever.lookup()` (nur Weltwissen-Quellen, k=2,
  eigene Schranke **0.52**: locker genug für erzählerische Formulierungen ~0.48, eng genug
  dass die Off-Korpus-Tyraniden-Frage ehrlich „steht nichts im Weltwissen" bekommt statt des
  nächstbesten falschen Chunks bei 0.54), deterministische Chunk-Anzeige als Embed, kein LLM.
  Topic-Blättern bleibt (`!lore` / `!lore chaos`). Live gegen die DB verifiziert (7 Fragen:
  Gott-Imperator/Dunkle Götter/Navigator/Rokarth treffen; Tyraniden + Regelfrage korrekt
  stumm mit Hinweis). Plus „Dunkle Götter"-Synonym in chaos.md (war knapp drüber). Tests +2,
  Suite **189/189**. Polish nach Tobis erstem Blick: der Frage-Footer im Antwort-Embed flog
  raus (die Frage steht direkt darüber in der Command-Nachricht).

**(Davor) Charaktererstellung (2026-06-12, Runde 2 der Spieler-Doku).** Die Runde will neue
Charaktere (ersetzen Garran/Eli/Yann; Chemical Burn startet dann frisch). Gebaut:
- **`docs/how-to-create-a-character.html`** — deutsche Anleitung (IM-treuer geführter Build:
  Punkte-Kauf 20+90 oder 2W10+20; echte Origin-Tabelle +5/+5; 6 Skill-Steigerungen à +5, max 2
  je Skill; Wunden = StrB+2×TghB+WilB, Buch-verifiziert) **plus interaktives Formular**
  (Vanilla-JS: Live-Punktezähler, Origin-Boni automatisch, Wunden-Autoberechnung,
  Budget-Validierung sperrt den Copy-Button, Live-JSON). JSON-Shape = Character-Schema +
  `player`-Feld (→ Alias; landet harmlos in `raw`, gegen `Character.from_dict` verifiziert).
- **`tools/fill_character_sheet.py`** — füllt den offiziellen IM-Bogen
  (`data/pdfs/…Character sheet.pdf`, KEINE Formularfelder/Text → Koordinaten-Overlay, an
  100-dpi-Renderings kalibriert): Name/Origin/Konzept/Patron, 9 Eigenschaften, Skill-Adv+Totals
  (Adv rekonstruiert aus Wert−Eigenschaft), Initiative, Wunden, Waffenzeile (Testwert + Schaden
  ausm Profil), Inventar ins Equipment-Grid. Sichtgeprüft an der aktuellen Party (3 PDFs nach
  `data/sessions/<id>/sheets/` — git-ignoriert, Ableitung des gekauften Bogens).
- **Einspeise-Prozess (wenn die JSONs kommen):** Spieler → Tobi → Claude validiert (Budgets,
  Formeln, Waffen) → baut `characters.json` + Aliases → löscht circlejerk-State/History/Recap →
  Bögen füllen + verschicken → **how-to-play-Charakterkarten + Checklisten-Namen
  aktualisieren** (Gates sind charakterunabhängig). Suite unverändert 177/177.

**(Same day, earlier) Spieler-Doku (Abschluss):** `docs/how-to-play.html` — deutsches Regel-Primer
(~10 min Lesezeit, gestyltes Standalone-HTML, grimdark): d100-Kernschleife, Schwierigkeitsleiter,
EG, Crits, Kampf mit Schadensformel, Fortgeschrittenes (Vorteil, Zustände, Überlegenheit,
Einfluss/Patron, Korruption) — Beispiele mit den echten Party-Werten durchgerechnet (gegen das
Sheet verifiziert), spoilerfrei, ohne Bot-Bedienung (bewusst, Tobis Wahl). Vor der nächsten
Session an Timo & Sezgin verteilen. Eigene Formulierung → committed trotz public repo.

**Starter Set in den DM (D46, gleicher Tag, direkt nach 10a).** Tobi legte das gekaufte IM
Starter Set nach `data/pdfs/Starter Set/`. Entschieden + gebaut:
- **Setting Guide (68 S.) → Lore-RAG:** `pdf_to_md --pages 1-57` (das „Villains on
  Voll"-Kapitel mit der Mireclaw-Auflösung bleibt bis zum Kampagnenfinale draußen — dieselbe
  Spoiler-Disziplin wie beim Abenteuer) → `ingest --source setting` (201 Chunks). Retrieval
  sucht jetzt rulebook+setting und gruppiert als `## Regelwerk` / `## Weltwissen` (TOP_K=3).
  Sanity verifiziert: „Welche Adelshäuser herrschen in Rokarth?" → NOBLE HOUSES ✓; „Wer steckt
  hinter Gratis?" → **kein Treffer** ✓ (die Spoiler-Frage bleibt stumm).
- **Patron-Sheet Aegidius Halikarn** ins chemical_burn-Kompendium: Motivation Information,
  Auftreten undurchschaubar, 100 Solars/Tag, Boons (Grenzenlose Autorität, Furchteinflößender
  Ruf) + die Sanctum-Obscurus-Ausstattung in der Thaler-Szene.
- **Aufgeschoben:** „The Blazing Seraph" (SS-Adventure-Book, 49 S., eigenes Bestiarium) wird
  erst nach dem Chemical-Burn-Live-Test zum zweiten Szenen-Kompendium; Handouts/Tokens/
  Sektorkarte = Tischmaterial (Backlog-Idee: `!ort` postet Handout-Bilder). Suite **176→177**.

**(Same day, earlier) Phase 10a built — the 3-stage hybrid (same day as D43, after the "perfect gamemaster"
discussion).** Tobi bought *Chemical Burn* (53 pp.), put it in `data/pdfs/`, and asked for a deep
joint planning round ("stell mir sehr viele fragen"). Decisions (via discussion): 3-stage hybrid
over pure RAG, story as guardrail (not railroad), priorities = plot coherence + W5 question
precision, German scene prep, auto-extracted NPC statblocks, story pipeline before Timo's
Tailscale model test (which runs independently via `OLLAMA_HOST`). Built end to end:
- **Compendium:** `tools/pdf_to_md.py` on the story PDF → I read all 53 pages and authored
  `data/adventures/chemical_burn/adventure.json` (15 German scene cards: description, NPCs,
  opportunities with profile-aligned skills/difficulties, secrets flagged "NIE aussprechen",
  leads_to, off-script guidance) + `npcs.json` (24 statblocks from the Core-Rulebook bestiary +
  adventure mods; wounds/TB/armour engine-ready). **Local-only** (public repo — derivative of a
  bought book, like the PDFs). _Tobi: review the cards for tone/quality._
- **Loader + wiring:** `dmbot/rag/adventure.py` (pure, tested); `WorldState.scene_id` (persists
  like HP); prompt order extended (recap → **adventure** → state → **Regelwerk** → hint);
  `DM_ADVENTURE` env; `!join` announces adventure + scene; `!ort <id>`/`!szenen`; `!npc add`
  resolves compendium statblocks (explicit numbers override).
- **Rulebook RAG:** `dmbot/rag/ingest.py` (heading-aware ~400-tok chunks, long pdf_to_md
  paragraph lines split at sentence ends; meta table pins embedder+dim) + `retrieve.py`
  (threshold 0.45 cosine, k=2, source=rulebook only, degrades silently). **Embedder switched
  nomic→bge-m3 after a failed sanity check** (German questions vs English text — exactly the
  CLAUDE.md "inspect a real chunk" reality check). Store: 1505 chunks. Verified: crit/difficulty
  questions hit CRITICAL HIT / DIFFICULTY; "ich gehe zur Tür" stays silent.
- **W4 guard:** `is_self_repetition` (SequenceMatcher ≥0.75, normalized, <60 chars exempt) joins
  the D43 echo guard — catches the live "Warum sind wir hier?" pronoun-swap re-description;
  retry with own nudge, then suppress; streamed-too-late repetitions logged loudly.
- **Tests 157→176** (+`test_adventure.py`, `test_rag.py`; compendium test skips on fresh clones).
  New dep `sqlite-vec` (§3 justified); `bge-m3` pulled. → **ADR 019**, D44/D45.

**(Same day, earlier) The 2026-06-12 echo collapse → diagnosis + the D43/ADR-018 robustness round.** Tobi reported the
bot "fühlt sich nicht mehr wie ein Gamemaster an" with a live log. Diagnosis from `debug.log` +
`data/sessions/1355307134559981709/history.jsonl`:
- **Wrong channel:** the session ran in `1355307134559981709`, not circlejerk (`1343673766487654464`)
  where the party is registered → `_load_characters` silently fell back to the **example party**
  (Pr0degie→Mortn aliases, wrong sheet values). Tobi confirmed circlejerk is the play channel.
- **Echo degeneration:** on the post-roll turn the model answered `Pr0degie: Ich greife den
  Kultisten an.` (predicting the next player line, not narrating); `_strip_leading_label` left a
  clean-looking echo that was spoken + stored → self-reinforced: **three turns in a row the DM
  answered every input — including an elaborate sword attack — with the same parroted sentence.**
- **Trigger:** the model's inline marker requested `<<TEST Heimlichkeit für Pr0degie>>` for an
  *attack* and won the D40 dedupe over the validated router; the bare `[Würfel] …` line carried no
  instruction what to do with it.
- **Race:** a dice click during playback overwrote `_last_turn` before the running turn's autosave
  read it → wrong `(user_msg, answer)` pairs in `history.jsonl` (seen in line 3).
- **Cold start:** the greeting turn hit `httpx.ReadTimeout` after 222 s gen (model load + GPU
  contention) and XTTS ran at RTF 34–45 until warm.

Fixes (all landed, suite **142→157**, live-unverified): echo guard (`is_echo` + retry-with-nudge +
suppress + history-poison protection incl. `restore_history` skipping empty answers), roll-feedback
directive on results-only turns, router-wins dedupe (`roll_button_source`), autosave `user_msg`
snapshot at generation end, `!join` party announcement + ⚠ example-fallback warning, `chat_stream`
read timeout 300 s, `DM_NUM_PREDICT` 160→220 + persona "zwei bis vier Sätze" (ADR 016 partial
rollback — streaming removed the brevity justification). Poisoned session dir
`data/sessions/1355307134559981709/` deleted; circlejerk untouched. **→ ADR 018.**

**(Prior) First live streaming run + tuning (2026-06-10, after the commit).** Tobi ran the streaming
pipeline live and pasted the log. **What worked:** streaming itself (`first_audio=3234ms` on the
narration turn — the old path would've been silent for `gen 6.5s + full synth`), and the **Phase-9
recap came automatically on `!join` and the `!wrap up` of the prior session was very good** (the
memory narrative-thread half is effectively live-confirmed). **Three content bugs fixed (D42 +
cleanup):** (1) the model streamed a **marker-only** answer (`` `<<TEST…>>` ``, code-fenced) → after
stripping it left a lone quote/backtick that XTTS **read aloud for ~15 s** (`total=15719ms` for
nothing) → `has_speakable_content()` now skips synth/post of a content-less answer (the dice button
still posts); (2) `_sanitize` now strips **code-fence backticks** like markdown `*`; (3) the model
appended a `<<TEST>>` on **every** turn incl. the post-roll consequence narration → a **dice loop**
(attack→roll→narrate+marker→roll→…) → inline markers are now **suppressed on results-only turns**
(`_last_action is None`), so a consequence narration can't request a new roll (**D42**). _Still open
(persona/adherence, nemo's ceiling):_ on one turn the model spoke a **meta-ramble** („Nein, tut mir
leid, ich habe mich versprochen. Als Spielleitung beschreibe ich nicht direkt die Szene…") — hard to
catch generically, watch it. Also: characters weren't registered (`für Mortn` → raw d100, „kein
hinterlegter Wert"). Suite **136→142** green (+6).

**Latency & crash-resilience — streaming pipeline + concurrent roll-router + history autosave
(2026-06-10).** Cross-cutting work between Phase 9 and 10, three flag-gated features, suite
**113→136** green (+23 tests). Nothing live-tested at commit time (the run above is the first proof).
- **Streaming pipeline (D39 → ADR 017, `DM_STREAMING=1`).** The DM turn now streams: `OllamaClient.chat_stream()`
  yields deltas; a pure `StreamAssembler` cuts complete sentences under three hold-back rules
  (first-chunk hold for the leading meta-preamble; hold back the latest sentence for the trailing
  strips; withhold from an unmatched `<<` / a mid-text speaker label); the cog synthesises + plays
  each sentence via a producer→synth→play pipeline (synth N+1 while N plays) over the blocking
  `/speak`. **History parity is by construction:** the batch chain is factored into one
  `finalize_answer(raw, labels, profile)` that both paths call, and `StreamAssembler.finish()`
  recomputes it on the accumulated raw — stored == spoken == the non-streaming result. `_sanitize`
  split into `_sanitize_leading` (incremental) + `_sanitize_trailing` (held tail). Layer-2 mute spans
  the whole answer; pause/Esc stops cleanly without replay; a mid-stream httpx error keeps what was
  spoken + notes history `… [Antwort unterbrochen]`. `[latency]` gained `first_audio=…ms` + a `stream`
  marker (tts/wav/bridge summed). `!redo` has its own streaming path. `DM_STREAMING=0` = byte-identical
  old single-WAV path; streaming only engages with a TTS backend.
- **Roll-router concurrent with playback (D40, no ADR — supersedes ADR 014's *timing* only).** The
  ADR-014 classifier now fires at **generation-end** and posts the 🎲 button **concurrently with
  playback** (`_deliver_answer` / `_deliver_streaming` run `_speak`/playback and `_handle_dice` as
  parallel tasks), so the button appears while the DM still speaks instead of after the whole turn.
  Single-GPU Ollama serialises, so firing at turn-start would just queue the classifier behind the
  narration — gen-end is the earliest point that doesn't delay it. Inline `<<TEST>>` marker still wins
  the dedupe (new pure `should_post_router(router_on, marker_posted)`).
- **Per-turn history autosave (D41, no ADR — extends ADR 015's artifact set, `DM_AUTOSAVE=1`).** New
  `dmbot/memory/history.py`: `append_turn`/`load_recent`/`rotate` over append-only
  `data/sessions/<id>/history.jsonl` (`{ts, user_msg, answer, redo}`; a `redo` record replaces the
  prior turn; corrupt tail tolerated). The cog appends after every turn (`asyncio.to_thread`, never
  blocks the loop), restores the last `max_history_turns` into an **empty** `DMBrain` history on
  `!join` (`restore_history`; `_last_turn` not restored → `!redo` unavailable for the restored last
  turn, documented), and rotates to `history.<timestamp>.jsonl` on `!leave`. Code-owned like
  `state.json`; the read-only `characters.json` split (ADR 015) is unchanged.
- **Tests (+23):** `tests/test_streaming.py` (assembler hold-back rules: meta-preamble in chunk 1,
  trailing "Was tut ihr?" split across deltas, `<<TEST` split across a boundary, stop-label mid-stream,
  num_predict mid-sentence cut, history parity vs the batch chain; `_parse_stream_line`;
  `respond_streaming`/`redo_streaming` history + spoken-equals-stored + mid-stream-error degrade),
  `tests/test_history_autosave.py` (append→load round-trip, redo-replaces, cap, corrupt line, rotate,
  restore-into-empty/noop-when-nonempty), `tests/test_roll_router.py` (+`should_post_router` dedupe).
  Flags documented in `.env.example`; architecture.md §4/§6/§7/§9 updated.

**Playtest-tuning round — stop the DM puppeting the party + cut runaway length + TTS punctuation
(2026-06-10).** Tobi pasted three live logs (one 06-09 box, two from one continued 06-10 session —
**all pre-change**). The dominant, repeatedly-voiced failure: the DM **spoke and acted for the
player characters** — scripting `Pr0degie: …` / `Seskin: …` / `Als Spielleitung beschreibe ich: …`
for the whole party (players: *"hat noch nicht gerafft, dass es mehrere Spieler gibt"*; one dictated
a corrected persona aloud). The `[latency]` lines (D35) showed **this puppeting IS the latency**:
scripted turns hit 700+ chars → `wav=55–80 s`, `total` up to **183 s** (each spoken char ≈ 0.1 s of
XTTS audio Bot A's blocking `/speak` waits through); clean short turns ran ~15 s. Fixes (→ **ADR
016**; commits `17adcfe` / `dc33d64` / `f36b5de` / `4564ecb`):
- **Persona + alias hint reframed** — positive top-of-file scoping (only NSCs/enemies/environment,
  never speak/think/act for the PCs, *multiple* players); the alias hint turned from a neutral cast
  list into a hard "these figures belong to the players" boundary placed **last** (recency).
- **Deterministic speaker-label backstop (the real fix; the persona alone never held nemo across 3
  sessions):** `CharacterStore.speaker_labels()` → `DMBrain.set_known_speakers` (wired on join) →
  every character + player name joins the turn's speakers as `_cut_at_labels` cut-points + Ollama
  stop sequences, so an appended `Seskin:`/`Pr0degie:` script is truncated **even when those names
  didn't speak this turn**. Kills the puppet display **and** the runaway length together.
- **Length cap:** `num_predict` 220→160 + persona "zwei bis drei kurze Sätze, die Gruppe wartet".
- **W6 TTS normalization:** `normalize_for_tts()` (XTTS + Piper synth, **not** the Discord post)
  drops quotes/brackets/symbols, maps ellipsis + em/en dashes to a pause, keeps `. , ! ? ; :` +
  word hyphens; also fixed XTTS's single-chunk branch synthesising the **raw** text.
- **`!npc add`** tolerant parsing (the `armour` `BadArgument` that blocked the gate) + a `_sanitize`
  strip for a "…als Sprachmodell … Hier ist die korrekte Antwort:" self-correction frame.
- **Wishlist compiled (W1–W9, now-vs-later):** W1 (puppeting) + **W3 (stop button — Tobi built it
  himself)** + W6 done (W1/W6 unverified live); W7 = the Phase-9 gate; deep latency **W2 = Part-2
  streaming TTS** (roadmap); W4 (within-session repetition) / W5 (answer the exact question asked) /
  W8 (engage provocative content) = persona/adherence, re-assess after the live check. **Suite
  113/113.** _All four commits are **live-unverified** — every log was pre-change; the next run is
  the proof._

**Per-turn latency instrumentation — logging only, baseline groundwork (2026-06-10).** Before any
streaming/latency work touches the pipeline, threaded a per-turn timing record (`_TurnTiming`,
`voice/commands.py`) through the DM turn flow and emit **one `[latency]` INFO line per turn** (console
+ `debug.log`), e.g.
`[latency] turn=42 auto stt=480ms wait=900ms trigger→llm_done=6200ms ctx=3100/8192 gen=180 chars=412 tts=3100ms wav=8.2s bridge_wait=4900ms total=14700ms`.
- **Stages** (all `time.monotonic`, carried in the existing flow — no new threads/globals): **stt**
  (reuses the Transcriber's `transcribe_ms` of the last DM-routed utterance — not re-measured),
  **trigger→llm_done** (turn start → Ollama returned, with the autosend `wait_idle` portion broken
  out as `wait=`), **tts** (synth → WAV), **bridge_wait** (`/speak` POST → return), **total**
  (trigger → `/speak` returned), plus the answer's `chars=` and the WAV's `wav=…s`.
- **Ollama token counts** (`prompt_eval_count`/`eval_count`, previously discarded) are now kept on
  `OllamaClient.last_stats` (the chat return type is **unchanged** for existing callers) → surfaced
  as `ctx=<prompt>/<num_ctx> gen=<eval>`, which shows for free whether the growing system prompt
  (persona + recap + state block + 20-turn history) is nearing the `num_ctx: 8192` cap. The brain
  copies them to `DMBrain.last_llm_stats` only on the **narration** call, so the roll-router /
  summarize calls can't clobber the turn's numbers.
- **Once per turn:** the line is emitted in `_deliver_answer`, the shared funnel for all four
  triggers (`!dm`, `!redo`, autosend, dice-result feedback); `!say` (TTS smoke test) deliberately
  produces none. Speech-less turns (typed `!dm`, redo, dice-feedback) log `stt=—`; text-only turns
  (TTS off) log `tts=—`/`bridge_wait=—`. The existing `⏱ LLM` line is unchanged (its value now
  derived from the record). **Zero behavior change, no new deps; suite 102/102 green** (D35, no ADR).
- **Context-budget warning + a test (same day, D36).** Building on those token counts: the per-turn
  record now also emits a **WARNING** — `[ctx] prompt N/8192 tokens (>85% of num_ctx) …` — when a
  narration prompt fills >85% of `num_ctx`, the early smoke signal *before* Ollama truncates the
  prompt **head** (the persona leads the system prompt — the worst part to silently lose). Narration
  turns only (only those build a `_TurnTiming`; the roll-router / recap calls are exempt), via a pure
  `_TurnTiming.ctx_over_budget()` predicate beside the `ctx=` display. New `tests/test_context_budget.py`
  fakes the `/api/chat` response and asserts the client's meta extraction (counts + default/overridden
  `num_ctx`, `chat()` return type unchanged) and the 85% boundary. **Suite now 107/107 green.**
- _Tobi: run one live session and paste a few `[latency]` lines → that's the baseline before the
  streaming work starts. A `[ctx] … >85%` WARNING in the same paste means the prompt is near the cap
  (trim history/recap/state)._

**Phase 9 built — memory: world state, deterministic advancement, recaps, auto-combat damage (2026-06-09).**
Read ADR 004 + the §7 schema + the wiring points first, then asked Tobi the two shaping decisions →
**split** state-file model + **auto-combat-damage** now (→ **ADR 015**). Built end to end:
- **`dmbot/memory/state.py`** — `WorldState` (+ `Combatant`/`Quest`), pure deterministic advancement
  (`apply_damage` clamps at 0 + sets `kampfunfähig`; `heal` clamps at max + clears it; NPCs, quests,
  location), **atomic** save/load (temp + `os.replace`), `seed_from_store` (once-only sheet → state),
  and `world_state_summary_de` (compact structured prompt block).
- **Engine combat math** — `resolve_damage` (weapon + SL − soak, never < 0) + `describe_damage_de`;
  **profile `combat` block** (attack_skills, weapons table, default_damage, soak source) + accessors,
  so it's system-agnostic. IM profile gained the block (weapon damage = approximate Core-Rulebook).
- **Recap** — `dmbot/memory/recap.py` (German summariser prompt + history renderer) + `DMBrain.summarize`;
  `DMBrain.set_context` injects recap + state into the system prompt in the CLAUDE.md order; `reset` clears it.
- **Cog wiring** — `!join` loads/seeds state + injects recap (and shows "📜 Was bisher geschah"); the
  dice-roll callback runs the **auto-combat** flow on an attack hit (weapon pick → target dropdown
  `discord_ui/target.py` → soak → apply → persist → narrate); new commands `!damage`/`!heal`/`!npc`/
  `!wrap`(`wrapup`); `!leave` persists the final state. State saved on every change.
- **Tests** — `tests/test_memory_state.py` + `test_memory_recap.py` (seed, clamp/down/heal, save→load
  round-trip = the gate's code half, summary, engine damage math, profile accessors, recap + injection).
  **Suite 102/102 green.** All changed modules import clean. _Live gate (HP survives restart; recap on
  next session) pending Tobi._
- **Logging trimmed for token-light pastes (D34, same day).** Dropped the redundant logger name on
  INFO console/mirror lines (the curated console only shows `dmbot.*` anyway), and stripped the common
  `dmbot.` prefix on WARNING/ERROR + in `debug.log` (`dmbot.voice.commands` → `voice.commands`) via a
  `_short_name` helper + a new `_DebugFormatter`; third-party names (httpx, faster_whisper, discord.*)
  kept intact. `ERROR`/`WARNING` levels + colour + tracebacks unchanged — only the noise around them
  shrank. _Tobi sets `DM_LOG_FILE=1` + `DM_TRANSCRIPT_FILE=1` (both already on in `.env`) before the
  live test, then pastes `debug.log` / `transcript.log` for the playtest-tuning round._

**Ops/UX polish during the Phase-8 live test (2026-06-08).** Tobi started the Phase-8 gate; the dice
math verified perfectly live (5 rolls, targets/SL/auto-bands/doubles-crit all correct against the
example party), but every post-roll narration failed with `httpx.ConnectError` — **Ollama simply
wasn't running** (not a bug; an external process). Built around that + two requested features:
- **Ollama can't silently be down anymore.** `start_dmbot.bat` now warms a **local** Ollama before
  launch (`ollama list` boots the daemon, `ollama run <model>` loads it — skipped for a remote
  `OLLAMA_HOST`), and a new boot **preflight** (`dmbot/llm/preflight.py`, wired in `__main__`) pings
  the host + checks the model is pulled, logging a clear error instead of a mid-game traceback.
- **Two-stage Ctrl+C** (`__main__._install_sigint_guard`): first press prints `Quit?` and keeps
  running, second prints `Shutting down …` and raises `KeyboardInterrupt` so discord.py's `run()`
  tears down cleanly (verified discord.py 2.7.1 installs no SIGINT handler of its own).
- **Pause control (D27 / ADR 013):** one shared `_paused` freeze, driven by **Esc in the terminal**
  (Variante A, animated `rich` box) **and** a **Discord ⏸ button** (Variante C, status embed). Pause
  mutes the VAD/STT pipeline + blocks all DM turns; resume reverses both. New dep `rich`. New
  `discord_ui/pause.py`, `!pausebutton`, `paused=` in `!vstatus`.
- **`!rules` / `!regeln`:** paged (◀/▶) Discord embed of the **active system's essentials**, derived
  from the profile (`rules/summary.py` + `discord_ui/rules.py`) so it stays system-agnostic — how a
  test works, the difficulty ladder, SL/auto-bands/crit, damage. Localised the IM profile's `damage`
  field to German (free-text, display-only).
- **Cosmetic:** dropped the double `🎲 🎲` in the dice log line (`commands.py`).
- **Suite 74/74** (new: `test_llm_preflight`, `test_shutdown`, `test_pause`, `test_rules_summary`).

**Then — Phase-8 live test → the marker problem → the roll-detection router (2026-06-08, same day).**
The live run worked for dice (`!test`), turn order and the voice loop, but the LLM **wasn't emitting
the `<<TEST>>` marker** — it self-resolved actions in prose. Diagnosed from `debug.log` (added a raw-LLM
`🪵` line, debug-only). First sharpened the persona (don't self-resolve, emit the marker + example),
stripped the repetitive trailing "Was tut ihr?" closer, and fixed a stray "So:" preamble leftover.
Then a **gemma3:12b vs nemo** taste test: gemma3 narrates cleaner (no meta-ramble/English-leak/tic) but
its markers were **no** better (still self-resolves), and nemo's tone is preferred → **kept nemo**.
**Researched it** (Tobi pushed back on "model-limited"): it's a *documented, model-size-independent*
LLM-GM failure; the fix is a separate roll step, not a bigger model — and an **experiment confirmed it**
(nemo 8/8 as a separate constrained-JSON classifier). Built the **roll-detection router** (D29 / ADR
014): after narration, a stateless constrained-JSON call classifies the action → posts the dice button;
inline marker kept as fallback; **now the default**. Tobi live-confirmed: "funktioniert jetzt besser" →
**Phase 8 flipped to ✅**. Also: split file logging into `terminal.log` (console mirror) + `debug.log`
(heartbeat-collapsed, pasteable). Research written up in `docs/research-notes.md`. **Suite 81/81.**

**Phase 8 built — dice engine, IM profile, marker flow, turn-order buttons (2026-06-07).** The whole
deterministic core, decoupled from the LLM (golden rule #2). New `dmbot/rules/`: `profile.py` (load +
validate `data/systems/<system>.json`, difficulty-ladder lookup), `engine.py` (seeded-RNG dice parser
+ `resolve_test` via a resolver registry — IM `roll_under` first; SL = tens-difference, crit/fumble on
doubles, 01–05 / 96–00 auto-bands; `describe_result_de`), `characters.py` (lean character JSON store +
alias map + pure `resolve_target`: skill value + difficulty → target, all in code), `marker.py`
(tolerant `<<TEST …>>` parser, strips markers, fallback to a manual button). First profile
`data/systems/imperium_maledictum.json` (1d100 roll-under, ladder, auto-bands) + an example party
`data/sessions/_example/characters.json`. **The IM numbers were then verified against the bought Core
Rulebook** (converted via the new `tools/pdf_to_md.py`): the Difficulty Table (Very Easy +60 … Very
Hard −30), SL = tens-difference, 01–05/96–00 auto-bands as Marginal (engine now sets SL 0 + no
crit/fumble on an auto result), crit/fumble-on-doubles is IM's combat rule, damage = weapon + SL (the
inherited d10/d5 guess was wrong — corrected). Two new
Discord views (`discord_ui/dice.py` + `turnorder.py`) on the `mic.py` View→cog pattern, new commands
`!roll`/`!test`/`!turn`, `DM_SYSTEM` env. Orchestrator extended: it extracts markers (before the
sentence-trim, which would otherwise eat a trailing marker), surfaces pending tests, feeds rolled
results back into the next turn, and appends a who-plays-whom alias hint to the prompt (fixes F). The
players' contract (K) is realised: the GM rolls **for** the player and the difficulty number comes from
the profile, never the LLM. **Decisions D26 → ADR 012.** **Suite 63/63 green** (34 new tests). _Live
Discord gate (dice button, turn rotation) pending Tobi._

**(Earlier) Phase 7 (feedback layer 2) implemented + a music-bot bridge race fixed (2026-06-05, later).**
- **Bridge race (music-bot repo, own commit `82393da`).** A `!dm` turn ran fully (STT→LLM→TTS) but
  Bot A returned `HTTP 500 'playback failed'` (`ClientException: Already playing audio.`). Root
  cause: the music cog's `after_playing` auto-advances the queue on **any** track end — including
  the bridge's own `vc.stop()` — so two `play()` owners fought over the voice client. Fix: a shared
  `bot.dm_speaking` flag — `dm_bridge._play_file` sets it (finally-cleared) around playback, and
  `music.play_next` bails while it's set (at the top + again right before `vc.play()`, re-queuing the
  popped track). Diagnosis came straight from `logs/dmbot.log` (now opt-in `DM_LOG_FILE=1`) + the
  music bot's `bot.log`. _Tobi must restart the music bot to load it._
- **Phase 7 — turn-taking & feedback protection layer 2 (this repo).** `VadSink.mute()/unmute()`
  pause the whole segmentation pipeline while Bot A speaks; `voice/commands._speak` mutes around the
  blocking `/speak` and unmutes in `finally`. `mute()` flushes open utterances so pre-DM speech is
  buffered, not glued across the gap. `!leave` now resets per-channel session state
  (`DMBrain.reset` + sink/counters). New `tests/test_feedback_layer2.py`. _(No new ADR — this
  implements ADR 003's existing layer-2 mandate, no fresh trade-off.)_ **Live-tested by Tobi: layer 2
  works (no feedback).**
- **Playability tuning — players' input now drives the narration more (Phase-5 open tuning).** Live
  play showed nemo drifting: it set atmosphere and continued its own thread instead of resolving the
  stated action, and opened every turn with a "Als Spielleitung beschreibe ich:" preamble. Two
  levers (Tobi picked both): (1) **persona sharpened** — new top section "Worauf du reagierst"
  makes resolving the latest action the primary directive + forbids the preamble; (2) **buffer
  noise cut** — `DMBrain` now forwards only the most recent `DM_MAX_LINES` (default 8) so table
  talk between !dm presses doesn't drown the action. Plus `_sanitize` strips the preamble as a net.
  _Still open: the nemo-vs-gemma3:12b taste test._
- **First live session → the criticism-driven fixes (D24/ADR 011).** Read `logs/dmbot.log` of a real
  4-player run. Findings + fixes: **(1) STT ~1.5 min behind** (unbounded queue + CPU whisper + all
  table talk) → **GPU whisper** + **push-to-talk button** so only DM-directed speech is transcribed;
  **(2) the DM answered AS a player** ("SezBoss69: …") → `_strip_leading_label` (the `\n<label>:` stop
  misses a leading label; `_cut_at_labels` skips position 0); **(3) preamble** → sanitized.
- **Second live session → playability polish (the players' requests).** Push-to-talk + GPU whisper
  confirmed working live (`→DM` markers, ~100–1000 ms transcribe). Five fixes from their feedback:
  **(1)** persona forbids the read-aloud meta-disclaimer + `_sanitize` strips a trailing meta
  parenthetical ("(Bitte beachte…)"); **(2)** new persona section: NPCs in **third person**, no
  "Tech-Priester:" script, never address a player AS the NPC; **(3)** vary the closing hook (not
  always "Was tut ihr?"); **(4)** the mic button is **re-posted to the bottom** after each DM turn
  (`_post_mic_button`, delete+resend) so it stops scrolling away; **(5)** a clean **session
  transcript** `logs/transcript.log` (`DM_TRANSCRIPT_FILE=1`) — just the conversation (player lines
  incl. table talk + DM answers) with timestamps, separate from the debug log. Suite **22/22**.
  _Live-tested: layer 2 + push-to-talk + GPU whisper work; the persona/UI polish is NOT yet live-tested._
- **Feedback layer 2 → opt-in, off by default (D25).** Tobi wanted the table to keep being
  transcribed *while the DM speaks* (full record). Layer 1 (Bot-A user-ID filter) already blocks
  self-transcription and the routing gate keeps narration table talk out of the DM, so the VAD pause
  was redundant. Now `DM_PAUSE_VAD_WHILE_SPEAKING=0` by default; mechanism kept for mic-bleed cases.
  `architecture.md` §5 updated; golden rule #4 (layer 1) unchanged.
- **Third live session → more persona/quality fixes.** From the transcript: **(A)** the
  "Als Spielleitung beschreibe ich …" preamble was *still* there — my `_META_PREAMBLE` only matched
  the colon form; rewrote it to strip the colon-less shapes too ("… beschreibe ich die Szene, wie …",
  "… eine dunkle Gasse …") and re-capitalise. **(B)** persona: the DM is **not** in the party — say
  "ihr/euch", never "wir/uns/ich" inside the scene (it kept writing "auf uns zu", "sehen wir").
  **(C)** ask "Was tut ihr?" only when something open is presented, never every turn, never with
  action suggestions. **(D)** no content warnings / lectures / setting commentary (turn 1 produced an
  LGBTQ disclaimer). **(E)** new **`!redo`/`!r`** — re-run the last DM turn with the same input
  (DMBrain.redo, replaces the last history pair) for when the DM misunderstood. Suite **25/25**.
  _Open (F): player→character name mapping_ — the LLM confuses "SezBoss69" vs the character "Seskin"
  and mixes up who did what. Belongs to character registration (D13/ADR 003, Phase 8); a light alias
  map could help sooner.
- **Fourth live session → audio bug + more persona.** **(J)** real bug: XTTS truncates a single
  chunk >253 chars for German (the "bricht mitten im Satz ab" reports) — the wrapper now splits a
  long answer into <240-char chunks (`tts/textsplit.py`, unit-tested) and concatenates the WAVs.
  Persona: **(G)** attribute each action to the *named* player when several acted, not a vague
  "du/dein"; **(H)** don't auto-advance — answer the immediate thing (esp. a perception question),
  NPCs wait until the group reacts; **(I)** engage with *every* player action incl. provocative
  ones, don't dodge/sanitise (model-dependent). Suite **29/29**.
  _Open (K) — Phase-8 dice design input from the players:_ a real GM rolls **for** the player
  ("ich würfle für Tobi auf Spurenlesen, Wert 6, Ziel 12 — nicht geschafft"); skill-check
  **difficulty** must come from the system profile / rulebook, the LLM can't balance it on the fly.
  Confirms "dice = code" (golden rule #2) — fold into ADR 005 / the engine when building Phase 8.
- **Fifth live session → mic-button auto-send (L) + polish.** Persona fixes confirmed working
  (clean answers, no preamble, good POV, NSCs in 3rd person — players: "beste Story die wir je
  hatten"). Built their most-repeated request: **releasing the mic button now auto-runs the DM
  turn** (`DM_BUTTON_AUTOSEND=1`) — no separate `!dm` — and it **waits for the just-said utterances
  to finish transcribing** first (new `Transcriber.wait_idle`), fixing the "it answered in the next
  message instead" race. **(M)** persona balance: lead the scene actively (introduce NSCs/events that
  follow from the group's actions) without railroading — counterweight to the "don't auto-advance"
  rule. **(N)** transient Discord `503` on send (seen mid-session) now retried once (`_send_with_retry`).
  Suite **29/29**.

**(Earlier same day) GPU XTTS via CUDA torch + portable per-machine GPU profiles (non-Phase work, ADR 009).** The
GPU rebalance (whisper→CPU, XTTS→cuda) crashed at first: the venv's torch was the **CPU-only**
build, so `TTS_DEVICE=cuda` raised `Torch not compiled with CUDA enabled` and left the DM mute.
Fixed end to end:

- **CUDA torch:** `torch`/`torchaudio`/`torchcodec` now pulled from the PyTorch **cu130** index
  (CUDA 13.0; `[tool.uv.sources]` + `[[tool.uv.index]]`). Verified live: `torch 2.12.0+cu130`,
  `cuda available: True`, XTTS `loaded on cuda`, RTF **0.34** (≈3× realtime; CPU was ~1.9).
  _(Started on cu126, but that tops out at sm_90 and failed on a colleague's **RTX 5080**
  (Blackwell, sm_120) — moved to cu130, which covers Ada (4070) + Blackwell (5080); re-verified
  on the 4070.)_ Then GPU whisper on the 5080 died at `encode()` with **`cublas64_12.dll cannot
  be loaded`**: `nvidia-cuda-runtime-cu12` (cudart64_12.dll, a cuBLAS dependency) was missing.
  Added it as a win32 dep. **But that alone still failed on the 5080** — root cause: `os.add_dll_directory`
  is not enough, CTranslate2's loader doesn't reliably search the added user dirs, so it only worked
  on the 4070 because that box has a **system CUDA toolkit (v12.3) on PATH**; the fresh 5080 box has
  none. Fix: `transcriber._register_cuda_dll_dirs` now **preloads the CUDA-12 DLLs by full path**
  (`ctypes.WinDLL`, in dep order cudart→cublasLt→cublas→cudnn). **Verified on the 4070 with the system
  CUDA stripped from PATH** (simulating the 5080) — GPU whisper runs. Lesson: ctranslate2's CUDA-12
  trio (cublas + cudnn + **cudart**) must be self-complete *and explicitly preloaded*, independent of
  torch's CUDA version and of any system CUDA install. **Result: the 5080 runs everything on GPU**
  (XTTS cuda + whisper cuda), full voice receive + transcription confirmed by the colleague.
- **Log noise tamed:** voice-recv's benign `Error unpacking packet` RTP-parse flood (alpha lib,
  drops the odd packet, audio keeps flowing) is now throttled in `logsetup.py` — first occurrence
  logged, then a running count every 500th, tracebacks suppressed (console + file).
- **Diagnostic tool:** `tools/diag_stt.py` — one-shot CUDA/STT check (commit, wheels, DLL preload,
  torch GPU, a real cuda transcription) for debugging a fresh box remotely.
- **Resolver fix:** CUDA torch pins `nvidia-cudnn-cu12==9.10.2.21` on linux, clashing with
  faster-whisper's `>=9.23`. Resolved by locking **win32-only** (`environments = ["sys_platform
  == 'win32'"]`, legit per D16) + `requires-python` pinned to the 3.12 line + win32 markers on
  the cudnn/cublas wheels. Lock is now Windows-only.
- **Robust device:** `dmbot/tts/xtts.py` `_resolve_device` + load-time fallback → XTTS degrades to
  CPU (warns, never crashes) when CUDA is absent or the GPU OOMs. Same `.env` is portable.
- **httpx bug:** found `httpx` was an **undeclared direct dep** (used by `llm/client.py` +
  `bridge.py`); the dep churn dropped it. Now declared `httpx>=0.28.1`.
- **Profiles + docs:** `.env` = 4070 dev profile; `.env.example` documents both (4070 dev / 5080
  full-GPU); `architecture.md` §3 updated; **ADR 009** written; README gained a "Running on
  another machine" section; `docs/SETUP.md` token-var line corrected (`DISCORD_TOKEN_DMBOT`, Bot A
  token lives in the music bot repo). Voice-stack smoke test re-run after the dep change: **5/5**.

**Then (same session) — playability + ops polish:**
- **XTTS is now the default engine** (Piper = fallback); D21 flipped once XTTS ran on GPU.
- **Answer length capped** (`DM_NUM_PREDICT`, env, default 220) + sentence-trim on a cut turn +
  persona tightened ("2–4 Sätze, keine Monologe") — XTTS-GPU made monologues the latency, not TTS.
- **Prompt shutdown:** transcriber `stop()` drops its backlog + short join (daemon), run off the
  loop in `cog_unload` → one Ctrl+C, no "heartbeat blocked" hang.
- **Bridge debuggability:** `!say` reports playback failure instead of a false 🔊; `bridge.speak`
  surfaces the bridge's real reason (401/404/409/unreachable). This pinned the colleague's issue to
  Bot A not reachable / not in voice (not a WAV/path bug).
- **Network bridge (ADR 010, D23):** hybrid `/speak` — loopback sends the WAV *path* (unchanged),
  remote sends the WAV *bytes* + shared secret (`DM_BRIDGE_SECRET`) over Tailscale; Bot A plays its
  own copy. **Both repos changed** (DMbot + the music bot's `cogs/dm_bridge.py`, its own commit).
  Localhost path mode verified unchanged; the remote/Tailscale path is **implemented but not yet
  live-tested** (they run both bots on one machine for now). Split-hosting documented in the README.
- **Lean logging:** console shows only `dmbot.*` lines + WARN/ERROR (timestamps kept); the
  full file log `logs/dmbot.log` is **off by default**, opt-in via `DM_LOG_FILE=1`; the benign
  voice-recv unpack notice is kept off the console (file-only).

_(Prior session — voice-stack hardening, ADR 006 — and Phases 3–6 (the playable loop) are captured
in ADR 006 and each phase's VERIFY EVIDENCE below.)_

---

## Current focus (Verlauf)

_Aus `progress.md` rotiert (2026-08-22, Umbenennungs-Runde D106):_

**Vierter Spieler: Vinzentius Kabelbrand (2026-08-22, D105). Suite 778 grün, `dm-eval` Exit 0.** Vincent spielt ab dem Testabend mit, und die Party bekommt damit zum ersten Mal jemanden, der schießen und Maschinen anfassen kann — Fridolin, Gellicus und Rektalus hatten Fernkampf 24/24/24 und Technologie 32/24/24, während das Abenteuer im Hafendistrikt zwischen Zollmanifesten, Frachtlukenschlössern und einem Leichter voller Maschinengeister spielt. Der Bogen ist gegen das Profil durchgerechnet (90 Punkte, Herkunft Schmiedewelt, sechs Steigerungen, Wunden 11, drei Augmetiken ≤ Zähigkeitsbonus mit exakten Katalog-Schlüsseln) und in beide vom Bot geladenen `characters.json` einsortiert: die des circlejerk-Channels und die `_default`-Party, die auf jedem Channel ohne eigene Datei einspringt. Nur die erste zu pflegen hätte gereicht, um den vierten Spieler auf Timos Clone stumm verschwinden zu lassen, sobald ihr in einem anderen Channel landet. Beim Nachziehen der Doku fielen zwei Sachen auf, die den Abend gekostet hätten: drei Run-Dokumente nannten die Party namentlich mit drei Namen, und der Augmetik-Live-Check (D52) stand als „ruht — kein Implantat-Charakter" im Skript, obwohl der neue Charakter drei trägt. Er läuft jetzt mit, mit einer nachgerechneten Beweiszahl statt einer Vermutung: Vinzentius' Wahrnehmungsprobe muss auf **44** kommen, nicht auf die 39 vom Bogen, weil `augmetic_bonus` die +5 des Augur-Arrays über dessen `skills`-Liste einrechnet.

_Aus `progress.md` rotiert (2026-08-22, Charakter-Akten-Runde):_

**Testabend-Doku + Kommando-Fehlermeldung (2026-08-15, D104). Suite 778 grün (+15 Tests), `dm-eval` Exit 0.** Damit der zweite Anlauf nicht an derselben Sorte Kleinkram scheitert wie der erste, hält [`docs/testabend-ablauf.md`](docs/testabend-ablauf.md) jetzt den zeitlichen Faden eines Abends: Vorbereitung am Zweitrechner, Sollbild beim Boot mit Abbruchkriterien, der Abend Szene für Szene mit den Reihenfolge-Zwängen, Übergabe und Nacharbeit. Das Runbook bleibt die Szenen-Referenz und wird verlinkt, nicht kopiert. Beim Schreiben fielen vier Anweisungen auf, die im Runbook UND im 🧪-Panel standen und den Abend gekostet hätten: `!npcmem Bree_Marlok` findet nichts (exakter Namensvergleich, Unterstriche versteht nur `!npc add`), `!uhr neu` ohne Anführungszeichen stirbt an der Größen-Konvertierung, ein vergessenes `!npc add` vor dem Kampf warnt nicht sondern bietet die eigenen Mitspieler als Ziel an, und der Neustart-Test braucht `!j` vor `!wrap` plus `!leave` danach. Daraus folgte die letzte Runde: `on_command_error` beantwortet Argument-Fehler jetzt mit der Nutzungszeile aus dem Docstring des Kommandos, statt nur zu loggen — vorher sah der Tisch bei einem Tippfehler überhaupt nichts.

**Testabend-Vorbereitung abgeschlossen (2026-08-15). Suite 778 grün, `dm-eval` Exit 0.** Der zweite Anlauf kann starten: Topologie entschieden (beide Bots auf Timos Rechner, Loopback ohne Secret — der geteilte Aufbau mit Musikbot bei Tobi bleibt ein eigener Lauf danach, damit nicht zwei Variablen an einem Abend hängen; Anleitung dafür steht bereits in `README.md`). Der Fehlstart vom 15.08. hatte seine Turns in die LIVE-`history.jsonl` des geteilten Channels geschrieben — auf Tobis Rechner nachweislich nicht, dort steht alles unverändert auf dem 14. Juni, betroffen ist nur die Maschine, auf der der Abend lief. Gefährlich wäre das erst beim nächsten echten `!leave`, der die Datei rotiert und ins Kampagnengedächtnis `session_<channel-id>` ingestiert. `tools/cleanup_15aug.py` schneidet am ersten Record des Stichtags, sichert nach `.bak` und legt das Entfernte AUSSERHALB des Session-Ordners ab (drinnen würde es beim nächsten `!join` wieder eingelesen); Bericht ohne `--apply`, idempotent, listet den Ordner mit. Verifiziert an einer nachgebauten verschmutzten Datei (21 echte Records behalten, 7 entfernt) und an der echten lokalen Session, die sauber blieb. Datierter Einmalfix — fliegt raus, sobald beide Maschinen sauber sind.

_Aus `progress.md` rotiert (2026-08-15, Testabend-Vorbereitung):_

**Playtest-Triage nach dem ersten Debug-Abend (2026-08-15, D103 → ADR 056). Suite 763 grün (+9 Tests), `dm-eval` Exit 0, ruff sauber. KEIN neues Live-Gate — die Gates sind dieselben, sie wurden nur nie erreicht.** Der Abend auf Timos Rechner lief die ganze Zeit in der ALTEN Kampagne: das Abenteuer wurde korrekt geladen, aber `!j` zog danach `state.json` und 20 Turns Gesprächs-Autosave der Live-Kampagne desselben Channels — der DM erzählte Rokarth weiter, der gespeicherte Szenenzeiger gehörte zu jenem Abenteuer, `get_scene()` lieferte überall `None`, und damit gab es weder Szenenkarte noch 🧪-Overlay (das hängt am Szenenwechsel). ADR 055 hatte nur Archive und RAG-Source getrennt; die vier laufenden Session-Dateien hatten weiter je einen Pfad pro Channel. Jetzt führt `SessionRuntime.session_file()` state/history/chekhov/recap im Debug-Run auf `.debug`-Zwillinge — Kampagnenwechsel hin und her ist gefahrlos, jede Kampagne behält ihren Stand, nur `characters.json` teilen sich beide Modi absichtlich. Dazu ein Guard beim Seed: ein dem Abenteuer unbekannter Szenenzeiger fällt laut protokolliert auf die Startszene zurück (deckt auch umbenannte Szenen innerhalb eines Abenteuers). Zweiter Fix aus demselben Log: der Meta-Preamble-Filter kannte die Antwort-Verben nicht, deshalb wurde „Als Spielleitung antworte ich: …" zweimal wörtlich vorgelesen statt den NSC zu spielen. Offen aus dem Log, nicht in dieser Runde: Timos `.env` (3 unparsbare Zeilen, `TTS_SPEAKER=cuda`), englische Einsprengsel, und `DM_NUM_PREDICT=220` → 885 Zeichen → 66 s Wiedergabe pro Turn.

_Aus `progress.md` rotiert (2026-08-15, Testabend-Doku-Runde):_

**Debug-Sandbox + Gate G10 (2026-07-17, D102 → ADR 055). Suite 754 grün (+6 Tests), ruff auf allen angefassten Dateien sauber, `dm-eval` Exit 0. G10 (Kampagnen-Gedächtnis am Tisch) reitet auf der ohnehin nötigen G9-Zweitsession — kein zusätzlicher Live-Termin; die Sandbox selbst ist offline voll testbar.** Die Debug-Kampagne spielt im SELBEN Channel wie das echte Spiel (`circlejerk`); der ADR-054-Stopgap (Ingest-Skip) wich einer echten Sandbox, damit der Debug-Run Session-RAG gefahrlos mittestet: Erkennung über die pure Datei-Präsenz von `testplan.json` neben dem Abenteuer (unabhängig vom Overlay-Kill-Switch; Inhalt bleibt LLM-unsichtbar, ADR-052-Pin unverändert grün), `rotate()` markiert Debug-Archive als `history.<stamp>.debug.jsonl`, Ingest routet allein nach Dateiname in die separate Source `session_debug_<channel_id>`, Catch-up und Retrieval sehen nur den eigenen Modus — Kreuz-Kontamination in beide Richtungen strukturell unmöglich (test-gepinnt). Reset per `uv run python -m dmbot.rag.ingest_session --wipe-debug <channel_id>` (löscht nur Sandbox-Rows); Runbook additiv erweitert (Setup, G10-Zeile, Debrief-Greps, Reset-Warnung: Plain-Archive sind ECHTE Session-Aufzeichnungen), G1–G9 byte-identisch. Projekt-Prio unverändert: der Live-Run (Debug-Kampagne oder One-Shot-Skript).

_Aus `progress.md` rotiert (2026-08-15, Playtest-Runde Debug-Sandbox-Artefakte ADR 056):_

**Session-RAG-Runde: Kampagnengedächtnis über gespielte Sessions (2026-07-17, D101 → ADR 054). Suite 748 grün (+32 Tests), ruff sauber, `dm-eval` Exit 0 gegen unveränderte Goldens, Kalibrierung: 5/5 `session_recall`-Positives, 0/5 Negativ-Leaks über den ganzen Sweep. KEIN neues Live-Gate — offline voll testbar; nur das `SESSION_MAX_DISTANCE`-Livetuning wartet auf echte rotierte Sessions.** Der DM kann jetzt Details aus früheren Abenden wörtlich erinnern („Was hat Vosk in Session 3 gesagt?"): auf `!leave` wird das rotierte Journal pro Szene gechunkt (ADR-053-Events; Redo-Collapse; Header `[Session vom …, Szene: …]` im Chunk) und in `rag.db` unter `session_<channel_id>` eingebettet — eigene vec0-Tabelle (`k` ist tabellenglobal; geteilt würden sich Buch- und Session-Korpus gegenseitig aushungern — Verifier-Fund) + FTS5-Spiegel für Eigennamen-Recall. `!join` holt fehlende Stempel nach (Crash-Recovery + Backfill). Retrieval: max 2 Chunks zusätzlich zu TOP_K=3, Schwelle 0.38 + Recency-Malus, FTS-Exakt-Treffer (satzmittig-großgeschrieben, df-gegated) übertrumpfen; Block „## Früher in der Kampagne … aktueller Status hat Vorrang". Debug-Kampagnen-Runs (testplan.json) werden nie ingestiert; Live-Journal nie; Buch-Retrieval byte-identisch (test-gepinnt).

_Aus `progress.md` rotiert (2026-07-17, Debug-Sandbox-Runde ADR 055):_

**Journal-Runde: Szenengrenzen + Ingame-Zeit im Session-Journal (2026-07-17, D100 → ADR 053). Suite 716 grün (+9 Tests), ruff sauber, `dm-eval` Exit 0 gegen unveränderte Goldens. Prep für die Session-RAG-Folgerunde — KEIN neues Live-Gate (Metadaten-only).** Zwei Ergänzungen am bestehenden append-only `history.jsonl` (ADR 046), damit die kommende Session-Transcript-Retrieval-Runde rotierte Journale pro Szene chunken und mit Ingame-Zeit stempeln kann: (1) jeder echte Szenenwechsel (`_set_scene`) und jeder `!join` (Start-Szenen-Seed **oder** restaurierter Pointer — so öffnet jedes Journal mit einer Szene) schreibt ein `{"kind": "scene", scene_id, ts}`-Event; (2) jeder Turn-Record trägt `time_minutes` (`WorldState.time_minutes` bei Turn-Abschluss) über den bestehenden `extra`-Mechanismus von `append_turn`. `load_recent`, Redo-Collapse, Rotation und Torn-Line-Toleranz unverändert — die ADR-046-Skip-Semantik macht beides rückwärtskompatibel (test-gepinnt); kein Renderer/Prompt konsumiert die neuen Felder. 3 Commits, einzeln revertierbar. Projekt-Prio unverändert: der Live-Run (Debug-Kampagne oder One-Shot-Skript).

_Aus `progress.md` rotiert (2026-07-17, Session-RAG-Runde ADR 054):_

**Debug-Kampagne „Die Mitternachtsfracht“ authored (2026-07-11, Content-Runde — füllt den `testplan.json`-Vertrag aus ADR 052). Skill-Validator gegen den echten Loader: `RESULT: OK` (0 Errors/Warnings, Statblocks 8/8), `Testplan.load` OK, Gate-Abdeckung G1–G9 vollständig, Fertigkeiten/Schwierigkeiten gegen Profil-`difficulty_ladder` + Party-Vokabular verifiziert. KEIN neues Live-Gate — das ist das Test-Vehikel für die 8 offenen.** Ein Original-Abenteuer (kein Buchmaterial), ein Abend, 6 Szenen (`zollhaus → schrein → pfandhalle → lagerhaus → siedehaus → pier_neun`), 8 NSC-Statblocks — jedes Gate hat einen natürlichen Story-Trigger: G4-Gate `lagerhaus → pier_neun requires 'verladebrief'` fest im File; 4× `faction: kettenbund`, sodass die G5-Lüge an Bree Marlok per Gossip bei Dockmeister Kessel ankommt; Kessel mit `goal_de` (G7, über mehrere Szenenwechsel beobachtbar); Lastenservitor Ohm-3 stirbt im Lagerhaus-Kampf und das Finale erwähnt Servitoren (G6-Versuchung); zwei Chekhov-Saaten (glattgeschliffene Münze, Fenks Hymne) mit verdrahteter Ernte in `pier_neun` (G9); Psi-Nachbild für Fridolin (G1); Sirenen-Frist + Kettenbund-Wachsamkeit als organische G2/G3-Anker; Kampf so bemessen, dass Wunden fallen, aber niemand stirbt (G8). Spieler-Text rein in-fiction — Gate-Hinweise NUR über die LLM-unsichtbare `testplan.json` (ADR 052). Kampagne lokal (`data/**` git-ignored; Timos Maschine braucht eine Handkopie, `dm-sync` zeigt die shas); committet sind `docs/debug-campaign-runbook.md` (Szenen→Beweis-Tabelle mit wörtlichen Logzeilen, Debrief-in-5-Minuten-Greps, Reset-Notiz) + eine Verweis-Zeile im Live-Run-Skript.

_Aus `progress.md` rotiert (2026-07-17, Journal-Runde ADR 053):_

**🧪 Debug-Overlay für Test-Runs gebaut (2026-07-11, D99 → ADR 052). Suite 707 grün (+18 Tests inkl. Invisibility-Pin), ruff-F sauber, `dm-eval` Exit 0 gegen unveränderte Goldens. Dev-Tooling, KEIN neues Live-Gate — die Live-Verifikation fällt als Nebeneffekt der Debug-Kampagne ab, für die das Overlay existiert.** Liefert ein Abenteuer eine `testplan.json` neben der `adventure.json` (`{"scenes": {"<id>": {"gates": [...], "hint_de": "…"}}}`), postet jeder Szenenwechsel EINE kompakte 🧪-OOC-Zeile (Szene, Gates unter Test, Ein-Zeilen-Hinweis) — edit-in-place nach dem Uhr-Panel-Muster (ADR 047), aufgefrischt von `!ort`, bestätigtem `<<ORT>>`, dem `!start`/`!intro`-Seed und `!join`; `!leave` räumt das Panel ab. **Kern-Invariante: LLM-Unsichtbarkeit by construction** — die Sidecar wird in der Runtime NEBEN, nie IN das Adventure geladen (neues pures `dmbot/rag/testplan.py`); ein Source-Inspection-Test pinnt, dass in `dmbot/` außer runtime/config kein Modul sie auch nur erwähnt (fängt auch `_testplan`-Attributzugriffe). Null LLM-Calls, null Prompt-Bytes; fail-open (keine Sidecar → schlafend, kaputte → EINE laute Logzeile), Kill-Switch `DM_DEBUG_OVERLAY=0`, optional `DM_DEBUG_CHANNEL` (unauflösbar → einmal warnen + Spielkanal). Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run — als Nächstes die Debug-Kampagne, die den Vertrag füllt.

_Aus `progress.md` rotiert (2026-07-11, Content-Runde Debug-Kampagne):_

**Cleanup-Runde: Marker-Pipeline konsolidiert + Doku-Sweep (2026-07-04, D98 → ADR 051). Suite 689 grün (+6 Registry-Tests, 0 Änderungen an bestehenden Tests), ruff-F sauber, `dm-eval` Exit 0 gegen die unveränderten Goldens — nach jedem Migrationsschritt. Verhaltensneutral, KEIN neues Live-Gate.** Das selbst notierte D94-Debt ist eingelöst, **bevor** ein sechster Marker kommt: die fünfmal handkopierte Marker-Naht (TEST/MANIFEST/ORT/ERLEDIGT/UHR/ZEIT — je eigene Regex+Dataclass+`_pending_*`-Dict, `finalize_answer` als 7-Tupel) läuft jetzt über eine **deklarative `MarkerSpec`-Registry** (`dmbot/rules/marker.py`; Tabellen-Reihenfolge = Extraktions- UND Journal-Key-Reihenfolge) + EINE generische Naht: `extract_all` (kettet die bestehenden Extraktoren byte-identisch), `finalize_answer_markers → (answer, {kind: requests})` (das 7-Tupel bleibt als test-gepinnte View), keyed Pending-Store im Brain (Queue/Redo/Reset/Consistency-Snapshot als Loops, Suppression aus `spec.suppressible`; `take_pending_<kind>`-Wrapper + Alias-Attribute halten die öffentliche Surface), labelled Task-Liste statt zwei kopierter Dispatch-Blöcke in der Delivery, dm-eval liest Keys+Drain aus der Registry. Die per-Marker-**Eigenheiten sind unangetastet** (ZEIT first-valid+12h-Clamp, UHR +1/Uhr/Turn, UHR/ZEIT suppressions-exempt, Confirm-Views unter `DM_FLAG_CONFIRM`, verklebte Marker strippen weiter); Handler-Bodies + pure Verdicts bewusst NICHT generalisiert (ADR 051 #5 — das ist das Feature, nicht die Naht). Migration marker-weise (ORT zuletzt), Journal byte-kompatibel. **Teil B:** README auf den echten Stand (Memory/RAG gelandet + Session-Tools-Liste), progress-Rotation (D75–D81-Focus-Blöcke + D60–D63-Next-step-Verlauf ins Archiv), `logsetup`-Docstring-Kosmetik, Open-questions ausgeräumt. Ein sechster Marker kostet jetzt: Dataclass + Extraktor + eine Registry-Zeile + sein eigentliches Feature. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

_Aus `progress.md` rotiert (2026-07-11, D99 Debug-Overlay-Runde):_

**Chekhov-Liste gebaut (2026-07-04, D97 → ADR 050). Suite 683 grün (+24), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.** Menschliche GMs merken sich lose Fäden und spielen sie später zurück („die Münze aus Session 1? *Die* Münze.") — der Bot hat dafür jetzt eine **code-verwaltete Chekhov-Liste**: `data/sessions/<id>/chekhov.json` (atomar wie `state.json`; neues pures `dmbot/memory/chekhov.py`) mit `Thread{id (t1, t2 …), detail, origin_scene, created_session, status open|resolved, weight 1–3}`, Cap **20 offene** (Überlauf: der älteste mit dem niedrigsten vorhandenen Gewicht fliegt), Aufgelöste bleiben als Historie (gedeckelt 20). **Extraktion nur beim Wrap-up** (Fäden sind Session-Granularität, keine Szenen-Extraktion): der EINE ADR-044-Extraktor-Call bekommt bei `!wrap` eine `chekhov`-Sektion (Schema-Variante + `prompts/chekhov_extract_de.md` als System-Zusatz) — max. **5 neue** unaufgelöste Details pro Session (erwähnte Objekte, Andeutungen, offene Versprechen, unbeantwortete Fragen; KEINE aktiven Quests) + IDs in dieser Session **aufgelöster** Fäden. Code klemmt alles: Dedupe per normalisiertem Substring-/Wortmengen-Vergleich gegen ALLE Fäden (ein aufgelöster kommt nicht wieder), Auflösung wird **erkannt, nicht erzwungen** (LLM nennt IDs, Code flippt den Status; unbekannte IDs verworfen + Log). **Fenster-Problem gelöst:** der Wrap-up-Call sieht nur die letzte Szene (das Extraktions-Fenster) — der Chekhov-Input trägt deshalb zusätzlich den früheren Sitzungsverlauf als klar markierten „nur für Fäden"-Kontextblock + die offenen Fäden nummeriert; das NSC-Gedächtnis bleibt per Prompt-Anweisung aufs Szenen-Fenster gebunden (Überreichweite fangen Gist-Dedupe/±1-Clamp — Trade-off im ADR). **Injektion bewusst klein:** die Top 3 offenen (Gewicht, dann **älter zuerst** — alte Fäden sind die besten Callbacks) als „Lose Fäden (… nicht erzwingen)"-Block am Weltzustand + Persona-Absatz (einen aufgreifen, wenn er sich natürlich fügt; Liste nie wörtlich erwähnen). Commands im neuen dünnen **ChekhovCog** (TimeCog-Muster): `!fäden`, `!faden neu "<Detail>" [1-3]` (Mensch-Autorität + macht das Live-Gate ohne Voll-Extraktion testbar), `!faden erledigt <id>`, `!faden weg <id>`. Kill-Switch geerbt (`DM_NPC_MEMORY=0` schaltet die Extraktion ab; kein neuer Env-Knopf). **Live-Gate offen** (s. Next step, braucht ZWEI Sessions): in Session 1 ein Detail fallen lassen → `!wrap` → spielt Session 2 es zurück? Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

_Aus `progress.md` rotiert (2026-07-11, Doc-Diet-Runde): die „Current focus“-Blöcke D82–D96 (verbatim; D97/D98 bleiben live)._

**NPC-Agenden gebaut (2026-07-03, D96 → ADR 049). Suite 659 grün (+24), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.** Wichtige NSCs verfolgen ihr Ziel jetzt **zwischen den Szenen** (der Schmuggler, den ihr verpfiffen habt, sitzt beim nächsten Besuch nicht mehr brav in seiner Bar): ein nicht-leeres `goal` am NSC macht ihn zum **Agenda-NSC** — gesetzt nur von Menschen (`!agenda <NSC> "<Ziel>"` / `weg`, `!agenden` listet; DiceCog neben `!npcmem`) oder autorenseitig (`goal_de` in `npcs.json`, wird wie `faction` bei Registrierung kopiert + auf Alt-States nachgezogen), nie vom LLM. Gedacht sind **2–5** (kein Welt-Simulator; Command warnt ab dem 6.). Der **eine** ADR-044-Extraktor-Call pro Szenenwechsel (kein zweiter — Latenz) darf pro Agenda-NSC einen `agenda_step` vorschlagen (1–2 Sätze: was hat er offscreen für sein Ziel getan — Input des Calls trägt jetzt Ziel + letzte 2 Schritte + die ADR-048-Ingame-Zeit, damit der Schritt zur verstrichenen Zeit plausibel bleibt); Code klemmt hart: **max. 1 Schritt pro NSC pro Szenenwechsel** (Duplikat-Einträge verworfen), nur lebende NSCs mit Ziel (PCs/tote/ziellose → verworfen + Log), Text auf den Gist-Cap gestutzt. Schritte sind **rein narrativ** — `agenda_log` (`AgendaStep{ts_ingame, text}`, FIFO-Cap 10, Ältestes fliegt), harte Mutationen (NSC-Tod, Ortswechsel) bleiben Code/Tobi. Injektion zweiseitig: **anwesender** Agenda-NSC trägt `Ziel:` + letzte 3 offscreen-Schritte in seinem `[NPC-Gedächtnis]`-Block (rendert jetzt auch ohne Erinnerungen); **abwesende** bekommen je eine Zeile im Weltzustand-Block („Agenden … deute Bewegungen über Gerüchte und Spuren an"). Kill-Switch geerbt: alles reitet in der ADR-044-Extraktion (`DM_NPC_MEMORY=0` = aus; kein neuer Env-Knopf). **Live-Gate offen** (s. Next step): einem NSC ein Ziel geben → zwei Szenen spielen → hat sich seine Lage glaubwürdig bewegt? Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Ingame-Zeit gebaut (2026-07-03, D95 → ADR 048). Suite 635 grün (+62), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.** `WorldState.time_ingame` (toter Freitext-String) ist jetzt ein Werkzeug: **ein code-owned Minuten-Zähler** `time_minutes` (seit Tag 1, 00:00; Start/Migration alter States: Tag 1, 08:00 + Log) ist das Modell, alles andere abgeleitetes Rendering (pure `dmbot/memory/gametime.py`: „Tag 2, 14:30" + Tagesphase Morgen/Tag/Abend/Nacht); der String bleibt als gerenderter Spiegel. Das LLM **schlägt Zeitfortschritt vor** per neuem Marker `<<ZEIT +30m>>`/`<<ZEIT +4h>>` (Einheiten tolerant; exakt das ADR-043/047-Muster an jeder Naht, Confirm-Button `ZeitView` unter `DM_FLAG_CONFIRM`), Code klemmt: **nur der erste valide Marker pro Turn** (Fortschritt ist nicht idempotent — Duplikate würden doppelt schieben) und **max +12h** (pure `zeit_verdict`, geteilt mit dm-eval); rückwärts/unlesbar → verworfen. Mensch ist ungeklemmt: `!zeit +6h` / `!zeit tag` (nächster Morgen 08:00); Szenenwechsel kostet default **+30 min** (`DM_SCENE_TIME_ADVANCE`, nur bei echtem Move — nicht beim Start-Seed). **Fristen** (`!frist neu "<Label>" <+Dauer>` / `weg` / `!fristen`, nur Menschen — ADR-047-Argument) reiten mit grober Restzeit im Weltzustand-Prompt („noch ~1 Tag"); läuft eine ab, injiziert Code **einmalig** die `[Regie]`-Konsequenz-Notiz (geliebtes Volle-Uhr-Muster, `notified` gelatcht + persistiert) und die Frist bleibt ABGELAUFEN sichtbar bis `!frist weg`. Anzeige: das Uhren-Panel ist jetzt das **Druck-Panel** (Zeit-Header + Fristen + Uhren, edit-in-place, kein neues Panel). Neuer dünner **TimeCog**; `<<ZEIT>>` ist wie `<<UHR>>` von der Results-only-Suppression ausgenommen. Journal/dm-eval kompatibel erweitert (`markers.zeit`, `zeit_verdicts` — alte Goldens replayen grün). **Live-Gate offen** (s. Next step): Frist setzen → verstreichen lassen → DM spielt die Konsequenz; Tagesphase im Erzählton. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Consequence Clocks gebaut (2026-07-03, D94 → ADR 047). Suite 573 grün (+38), ruff-F sauber, `dm-eval` Exit 0 gegen die alten Goldens, live-unverified.** Code-owned Fortschrittsuhren à la Blades in the Dark geben der Welt Druck („Arbites-Ermittlung 3/6"): `WorldState.clocks` (Schema abwärtskompatibel, `visible`-Feld für verdeckte Uhren reserviert — UI ignoriert es bewusst), Uhren **nur von Menschen** angelegt (`!uhr neu "<Name>" <4|6|8>` / `tick` / `zurück` / `weg` / `!uhren`, neuer dünner **ClockCog** im ADR-039-Stil). Das LLM **schlägt Ticks vor** per neuem Marker `<<UHR id>>` (exakt das ADR-043-Muster: Grammatik/Strip/Streaming-Withholding/Pending-Queue/Confirm-Button `ClockView` unter demselben `DM_FLAG_CONFIRM`-Knopf), Code validiert + klemmt hart auf **+1 Tick pro Uhr pro Turn** (pure `uhr_verdict`, geteilt mit dm-eval); unbekannte id → verworfen + Log. **Bewusste Abweichung:** `<<UHR>>` ist von der Results-only-Suppression ausgenommen — der Konsequenz-Turn nach einem Fehlschlag ist DER Tick-Moment, und ein Tick kann keine Schleife erzeugen (ADR 047). **Volle Uhr:** Code reiht eine One-Shot-Regie-Notiz ein → nächster Turn trägt `[Regie] Die Uhr „X“ ist voll — die Konsequenz tritt JETZT ein` (`!uhr zurück` von voll zieht eine noch nicht gefeuerte Notiz zurück); die Uhr bleibt VOLL sichtbar bis `!uhr weg`. Sichtbar für alle: edit-in-place-Panel (◉◉◉○○○, Pause-Panel-Muster) + `Uhren:`-Zeile im Weltzustand + Persona-Absatz (wann ein Tick angemessen ist). Replay-Journal kompatibel erweitert (`markers.uhr`, `notes`, `uhr_verdicts` — alte Goldens replayen grün). **Live-Gate offen** (s. Next step): Uhr anlegen → DM einen Tick provozieren → Panel prüfen. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Replay-Eval-Harness gebaut (2026-07-03, D93 → ADR 046, Dev-Tooling). Suite 535 grün (+19), ruff-F sauber, `uv run dm-eval` Exit 0 gegen die eingecheckten Goldens.** Aufgezeichnete Sessions werden zu **Golden-Transcripts**: das `history.jsonl`-Autosave ist abwärtskompatibel zum **Replay-Journal** erweitert (Session-Header pro `!join`; pro Turn zusätzlich `lines`/`results`, die **rohe** LLM-Antwort mit Markern, die gequeueten Marker, das Router-Verdikt samt Roh-JSON, `state_before` + Szenen-/Flag-Verdikte — `load_recent`/Crash-Restore ignorieren alles davon). Neues Tool **`dmbot/tools/eval_replay.py`** (`uv run dm-eval`, `[project.scripts]` wie dm-sync/D90) spielt die Turns mit **gemocktem LLM** (Playback der Roh-Antworten) durch den echten Orchestrator und difft pro Turn: Kategorien `turn`/`answer`/`marker`/`router`/`state`/`llm`, eine `[eval] DIFF`-Zeile pro Abweichung, Exit 0/1/2 → taugt als Gate vor Refactor-Merges. **Regression, nicht Qualität** (der Live-Modellvergleich Nemo vs. Mistral Small ist die explizite Folge-Runde auf genau diesem Harness). Bewusst NICHT verglichen: Timing/Audio, Prompt-Inhalte, numerische State-Mutationen (Würfel-RNG/Wunden — Verdikte statt Snapshots, ADR 046). `tests/golden/`: 2 synthetische, committbare Goldens (Würfel-Loop + Szenen/Flags gegen ein Mini-Fixture-Abenteuer) über den echten Capture-Pfad generiert (`generate_synthetic.py` = Bless-Schritt) + README (wie man aus einer Live-Session ein frisches Golden zieht). Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run — der nebenbei das erste echte Live-Golden liefert.

**Konsistenz-Wächter gebaut (2026-07-03, D92 → ADR 045). Suite 516 grün (+30), ruff-F sauber, committet auf `main`, live-unverified.** Vor der Auslieferung einer DM-Antwort prüft jetzt **deterministischer Code** (kein LLM-Judge, `dmbot/llm/consistency.py`) gegen den WorldState: ein **toter** NSC (Karte rendert `(tot)`) oder ein **szenenfremder** registrierter NSC (nicht in `npcs_here`) darf keine wörtliche Rede zugeschrieben bekommen. Heuristiken bewusst konservativ (nur Präsens-Sprechverben, Zitat-Spannen gestrippt, „ein Kultist ruft" zählt nicht, mehrdeutige Namens-Tokens fliegen raus — im Zweifel NICHT anschlagen, jeder False Positive kostet eine Regeneration). Bei Verstoß **einmal** regenerieren mit konkretem deutschen KORREKTUR-Hinweis; besteht auch der Retry nicht → trotzdem ausliefern + Warn-Log (fail-open, blockiert nie). **Trade-off (im ADR festgehalten):** der Streaming-Pfad kennt den Volltext erst, wenn das Audio schon läuft — dort loggt der Wächter nur; der Regenerate-Schutz greift auf dem Batch-Pfad (`nahtlos`, Würfel-Folge-Turns). `DM_CONSISTENCY_GUARD=0` = aus. **Live-Gate offen** (Checkliste §6b): toten NSC provozieren → `[consistency]`-Regenerate feuert, Retry sauber. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**NPC-Gedächtnis gebaut (2026-07-03, D91 → ADR 044). Suite 486 grün (+27), ruff-F sauber, committet auf `main`, live-unverified.** NPCs erinnern jetzt, was mit ihnen besprochen wurde: pro NSC eine gedeckelte `memories`-Liste in `state.json` (Gist + wörtliches Schlüsselzitat bei Versprechen/Lüge/Drohung, `believed`-Flag für Spieler-Lügen), extrahiert durch **einen** LLM-Call pro Szenenwechsel (`!ort` / bestätigter `<<ORT>>`) + `!wrap` als Catch-all — nie pro Turn. Golden Rule #3 überall: der Extraktor schlägt nur vor, Code klemmt die Haltung auf ±1 Stufe/Szene (`hostile→wary→neutral→friendly→loyal`), kippt aufgeflogene Lügen (believed=False + Wichtigkeit-5-Eintrag + eine Stufe Richtung hostile) und verteilt Wichtigkeit-≥4-Neuigkeiten deterministisch als Hörensagen an gleiche-`faction`-NSCs. Top-K pro Szenen-NSC im Prompt (`DM_NPC_MEMORY_TOP_K`, Lügen immer dabei), `DM_NPC_MEMORY=0` = aus, `!npcmem` = Debug-View. **Live-Gate offen** (s. Next step): NSC anlügen → Szene wechseln → zurück → erinnert er sich? Projekt-Prio davor unverändert: der Tuning+Scene-Cards-Live-Run.

**`uv run dm-sync` als Entry Point (2026-07-02, D90, Dev-Tooling — committet + gepusht auf `main`).** Das D89-Tool ist von `tools/sync_check.py` nach **`dmbot/tools/sync_check.py`** gezogen (Package-Modul, `sys.path`-Hack weg) und läuft jetzt als `uv run dm-sync` (`[project.scripts]`). Dafür ist das Projekt jetzt **packaged** (hatchling, editable install von `dmbot` — nur damit der Script-Entry existiert; weiterhin Anwendung, keine Library). Output byte-identisch zum D89-Format (Kontrakt), Doku-Zeiger (SETUP.md/conventions.md) + Tests umgebogen, kein Shim am alten Pfad. Suite 459 grün. **Timo braucht einmal `git pull` + `uv sync`**, bevor `dm-sync` bei ihm existiert. Nebenbefund: Tobis `.env` ist inzwischen **38/38** — der D89-Befund (20 fehlende Keys) ist abgearbeitet. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Sync-Check-Tool gebaut (2026-07-02, D89, Dev-Tooling — committet auf `main`).** Neues Standalone-`tools/sync_check.py`: ein kompakter `[sync]`-Fingerprint-Block (Repo-Commit, Abenteuer-Dateien sha+mtime+Kennzahl über den echten Loader, rag.db Größe/Embedder/Chunks-pro-Source/Ingest-Datum, .env-Key-Abgleich gegen `.env.example` ohne Werte, geänderte data-Seeds) — beide Maschinen lassen es laufen und diffen die Blöcke; die abweichende Zeile ist das, was zu schicken/neu zu bauen ist. `dmbot/rag/ingest.py` stempelt jetzt `ingested:<source>` in die Meta-Tabelle (alte DBs tolerant „unbekannt"). SETUP.md-Sektion „Staying in sync (second machine)". Suite 459 grün (+15). **Erster echter Befund:** Tobis lokale `.env` hängt 20 Keys hinter dem Template — vor dem Tuning-Live-Run nachziehen (s. Next step). Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Authoring-Skill `/author-adventure` gebaut + Smoke-Test bestanden (2026-07-02, D88, Dev-Tooling — committet auf `main`; nur der Skill selbst, keine Buch-Derivate).** Neuer Claude-Code-Skill (`.claude/skills/author-adventure/` = SKILL.md + `validate.py`, D78-Infrastruktur): 5-Pass-Workflow (Struktur-Pass **mit Stopp zur Szenenschnitt-Freigabe** → Karten → NSCs → Summary → Spoiler-Selbstcheck + Loader-Validierung + Review-Checkliste), damit Abenteuer #2 („The Blazing Seraph", 49 S.) einen Redigier-Nachmittag kostet statt Tage. Dry-Run gegen das Chemical-Burn-md → 14-Szenen-Draft, Loader-valide (inkl. ADR-043-Gates), dann Diff gegen das handgebaute Kompendium: 4 echte Konventions-Lücken gefunden und in den Skill zurückgebaut (Auftakt-Szene als `start_scene`; `leads_to` dramaturgisch-sparsam statt Orts-Mesh; Summary enthält die WAHRHEIT mit Geheim-Rahmung; Statblock für **jeden** `npcs_here`-Namen). Wegwerf-Draft gelöscht. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run (s. Next step).

**Stateful Scene Cards gebaut (2026-07-02, D87 → ADR 043). Suite 444 grün (+49), ruff sauber, committet + gepusht auf `main`.** Die Szenenkarte spiegelt jetzt den Weltzustand: Element-Flags (`<<ERLEDIGT id>>`-Marker mit Confirm-Button/`DM_FLAG_CONFIRM`, manuell `!erledigt`/`!offen`) verschieben erledigte Gelegenheiten nach „Bereits geschehen" und enthüllte Geheimnisse nach „Bekannt"; tote NSCs rendern `(tot)`; `leads_to` kann per `{"ziel","requires"}` gegatet werden (verborgen + abgelehnt bis freigeschaltet). Alles code-owned (`WorldState.scene_flags`, golden rule #3), Schema abwärtskompatibel (Chemical Burn unverändert). **Offen/live:** das Live-Test-Skript (siehe Next step) — hängt sich an den ohnehin offenen Spielbarkeits-Live-Run. Davor/danach unverändert offen: der Tuning-Live-Run unten.

**Spielbarkeits-Tuning-Runde (2026-06-18, D85+D86 → ADR 042 + ADR 041 Addendum 2). Suite 395 grün (+16), Commit `e961b75` auf `main`, live-unverified.** Bootstrap (Phase 10 Hälfte 2) **zurückgestellt** auf Tobis Ansage „das Modell läuft noch nicht so richtig, dass man wirklich spielen kann" — Fokus ist jetzt Spielbarkeit, Modell bleibt nemo („am Drumherum drehen"). Drei Fronten: **Antwortqualität** → `repeat_penalty`/`repeat_last_n` als OllamaClient-Instanz-Defaults (1.1/256, `DM_REPEAT_PENALTY`/`DM_REPEAT_LAST_N`, live-tunebar), reiten auf jedem Call; der **Roll-Router** neutralisiert sie explizit (1.0) → Würfel-Routing bleibt deterministisch (ADR 042, vom adversarialen Verify gefunden). **!intro** → pures `intro_guard.is_weak_intro` (zu kurz **oder** Figur ungenannt, Genitiv-`s`-tolerant) + Einmal-Retry in `respond_opening` (Batch-Pfad), nur die bessere Antwort in die History (ADR 041 Add. 2). **Tempo** → GPU-Offload (Workstream A) ist Tobis **Live-Schritt**: lokale `.env` `OLLAMA_HOST` auf die Offload-Box + `TTS_DEVICE=cuda` (XTTS frei → ~3× schneller, Lücken weg); `.env.example` dokumentiert das bereits als Soll. **Offen/live:** der eine geplante Live-Run (s. Next step) — verifiziert Tempo (first_audio/tts fallen), Intro-Qualität, weniger Wiederholung, und nebenbei Phase-10-Gate-Hälfte 1 (Regelfrage aus RAG).

**Playtest-Fix-Runde (2026-06-16): drei Fixes aus Tobis Live-Sessions auf `main` (`e36bad7`), live-unverified.** Default-Party lädt jetzt **channel-unabhängig** (committete `data/sessions/_default/characters.json`, vor `_example` geladen — D82 → ADR 040), also Fridolin & Co. in jedem Voice-Channel + beim Kollegen. `!intro` gegen **Modell-Varianz** gehärtet: feste, niedrigere `!intro`-Temperatur (`DM_INTRO_TEMPERATURE`) + Director-Brief (D83), und der Meta-Auftakt („Als Spielleitung beginne ich…") + `"…"`-Umschlag **deterministisch** im Sanitizer gestrippt + Default-Temp auf **0.7** (D84 → ADR 041 + Addendum). Suite **379 grün**. **Offen/live:** klingt `!intro` jetzt zuverlässig wie der gelobte 14.06.-Lauf? Kollege testet `e36bad7`; ggf. `DM_INTRO_TEMPERATURE` Richtung 0.8 oder Brief-Wortlaut. Projekt sonst: Phase-9/10-Live-Gates (siehe Phasen-Status).

_Aus `progress.md` rotiert (2026-07-04, D98): die Vorsessions-„Current focus“-Blöcke D75–D81 (verbatim)._

**`/improve-architecture`-Runde 3 (2026-06-16, D81 → ADR 039): Szenen + `!lore` aus `DMCog` in eigene dünne Sub-Cogs (`scenecog.py`/`lorecog.py`) ausgelagert — der zurückgestellte ADR-035-Folgeschritt. `dmcog.py` 662→502; Suite 369 grün (359 + 10 neue Sub-Cog-Tests), 0 Test-Änderungen, byte-identische Bodies.** Der offene ADR-035-Fork ist entschieden: **Sub-Cog statt Mixin** (umgeht die `CogMeta`-Sammel-Frage), **zwei** Cogs statt einem `AdventureCog` (kein geteilter State). Die eine Cross-Cog-Kante (`!lore tts` → `delivery._speak`) läuft über einen neuen `runtime.speak`-Hook (ADR 029). Gewählt aus dem `/improve-architecture`-Befund (Workflow: 3 Finder + adversariale Verify, 13 Kandidaten → 7 überlebt); Tobis Ziel: ein Agent soll nur laden, was seine Aufgabe braucht. Von Hand gebaut (kleiner, klarer Schnitt). Damit ist das ADR-035-Deferred-Umbrella für `DMCog` abgeschlossen.

**Deepening-Runde 2 aus `/improve-architecture` (2026-06-16, D80 → ADR 038): Kandidaten #4 + #5 + #6 umgesetzt, verhaltensneutral. Suite 359 grün (343 + 16 neue Tests), 0 Test-Änderungen, Commits auf `main`.** #5: den System-Prompt-Join aus `orchestrator._build_request` in die reine, reihenfolge-explizite `llm/prompt_assembly.py::assemble_system_prompt` gezogen — **nur den Join**, die `.get()`-Cache-Reads bleiben in `_build_request` (cache-vs-pull-Timing unangetastet). #4: die `!join`-Seed-Sequenz in `runtime.seed_session(voice_channel, text_channel)` gebündelt (Voice-Receive + Ansagen bleiben im Cog). #6: der 4× byte-identische „Panel löschen"-Block in `runtime.clear_panel(attr)` (Pause-Panel-edit-in-place unangetastet). Per Workflow: sequenzielles Implement (geteilte Dateien) + 3 parallele adversariale Verifier. Damit ist der `/improve-architecture`-Strang (#1–#6) abgeschlossen.

**Deepening-Runde aus `/improve-architecture` (2026-06-16, D79 → ADR 037): Kandidaten #1 + #2 umgesetzt, verhaltensneutral. Suite 343 grün (324 + 7 + 12), 0 Test-Änderungen, 3 Commits auf `main`.** #1: die schon extrahierte reine `stt/segments.py::confident_text` (Whisper-Halluzinations-Guard) in `transcriber.py` verdrahtet (Inline-Duplikat + tote Konstanten raus) + `tests/test_segments.py`. #2: Attack-Soak-Arithmetik + Warp-Containment→Perils-Kette aus `dicecog.py` ins neue reine `dmbot/rules/combat.py` gezogen (kein Discord, keine WorldState-Mutation, RNG injiziert) — Schnitt **vor** der Mutation (keine Wunden-Clamp-Duplikation), der Cog delegiert + behält `state.apply_damage`/`reset_warp_charge` + das schon reine `describe_damage_de`. Reiner Testbarkeits-Gewinn am deterministischen Kern (Würfel = Code). Gebaut per 2-Agenten-Workflow (parallel implement + adversarial verify).

**Skill-Tooling-Runde (2026-06-15, D78): 4 Claude-Code-Skills nach `.claude/skills/` — `/tdd` (eigen) + `/grill-me`·`/improve-architecture`·`/to-prd` (aus `mattpocock/skills` adaptiert). Kein Bot-Code, Suite unberührt (324 grün), 5 Commits auf `main`.** Nebenstrang (Dev-Tooling); die eigentliche Projekt-Priorität bleibt das `!intro`-Live-Gate (siehe „Next concrete step").

**Dev-Gates-Runde gelandet (2026-06-15, D77): Lint im Test-Hook, blockierender git pre-commit, Review/Simplify-Trigger-Checkliste. Suite 324 grün, 4 Commits gepusht.**
Entscheidung aus „auto-`/code-review` vor jedem Commit?": **nein** — billige + deterministische Gates automatisch (0 Tokens: `ruff --select F` im Stop-Hook **und** neuem blockierenden `tools/hooks/pre-commit` via `core.hooksPath`), teure LLM-Reviews (`/code-review`, `/simplify`) nach Urteil, als Checkliste in `docs/conventions.md` verankert (`/simplify` nie automatisch — schreibt Code, D72). Der Lint-Gate fand + entfernte sofort 2 tote Importe in `orchestrator.py` (D70-Rückstände).

**Review-Runde nach Fan-out-`/code-review` der Tagescommits gelandet (2026-06-15, D76): 14 Findings → 3 bestätigt / 11 entwarnt, Suite 324 grün, 2 Commits gepusht.**
Fan-out-Review (21 Agenten, jedes Finding adversarial gegengeprüft) über `7b5af54..HEAD` — **kein Refactor-Regress (D70–D75) überlebte die Gegenprüfung**, Golden-Rules-Querschnitt sauber. Gefixt: **`disconnect_voice`** gab durch einen toten `TimeoutError`-Zweig immer `True` (die „abandoned at shutdown"-Warnung feuerte nie, weil das echte discord.py den Bound-Cancel schluckt) → deterministisch via `asyncio.wait` neu, Test auf den echten swallow-and-cleanup-Kontrakt umgestellt (`2b608e7`); **`tests/test_delivery.py`** neu — nagelt die ungetestete `puffer`-State-Machine in `_deliver_streaming` fest inkl. early-abort Temp-WAV-Cleanup (`5499066`). Die 11 entwarnten Nits bewusst gelassen (intentional/unerreichbar/„so geboren"). _Bugfixes, kein Trade-off → kein ADR._

**`setup.ps1` kümmert sich jetzt um ALLES + alles dauerhaft im PATH (2026-06-14, D75 → ADR 036): parse-OK, Suite 319 grün (nur Skripte/Doku).**
Tobis Wunsch: Setup soll wirklich alles erledigen — herunterladen, installieren, **uv + python dauerhaft im PATH**, startklar,
idempotent; beim Kollegen hakten zusätzlich **winget** und die **Skriptausführungs-Richtlinie**. Umgesetzt: neuer `Add-ToUserPath`
(schreibt den persistenten User-PATH, append-only/dedup) für uv-Bin (`~/.local/bin`) + Ollama-Dir; `uv python install 3.12
**--default**` → globales `python`-Shim; **Ollama voll automatisch** (robustes winget → offizieller Installer-Fallback → PATH →
Modelle); **Bug-Fix `ollama pull bge-m3`** statt veraltetem `nomic-embed-text`; **Prefetch standardmäßig an** (`-SkipPrefetch`);
Kopf-Härtung (TLS 1.2, ExecutionPolicy RemoteSigned, `Unblock-File`) + neuer **`setup.bat`** Ein-Klick-Starter (`-ExecutionPolicy
Bypass`). Den vollen Installer **bewusst nicht** auf Tobis Hauptmaschine laufen lassen (persistente PATH-/Policy-/`--default`-
Änderungen) — `Add-ToUserPath`-Dedup + `uv python find` read-only verifiziert. _Live offen: einmal `setup.bat` beim Kollegen
auf frischer Maschine per Doppelklick gegenchecken (der ursprüngliche Schmerzpunkt)._

_Aus `progress.md` rotiert (2026-07-11, Doc-Diet-Runde): die älteren „Current focus“-Blöcke (D74 und früher, zurück bis Phase 9; verbatim)._

**`dmcog.py` halbiert: Delivery-Pipeline nach `dmbot/voice/delivery.py` ausgelagert (2026-06-14, D74 → ADR 035): Suite 319 grün, 0 Test-Änderungen.**
Der eigentliche Hebel (Tobis Wahl „b"): die größte Datei nach dem Cog-Split. Die Antwort→Audio-Maschinerie (TTS-Speak,
Batch- + Streaming-Lieferung, `<<ORT>>`-Marker-Drain, `[latency]`-Zeile, die beiden Turn-Hooks) ist in eine neue Klasse
**`DeliveryPipeline`** gezogen — **Komposition statt Vererbung**: `DMCog` hält `self._delivery = DeliveryPipeline(runtime,
post_deliver=self._post_deliver)` und ruft hinein. **Verschoben byte-identisch** (29 835 Zeichen char-exakt gegen `HEAD`
geprüft, kein Abtippen — Slice-Skript). **Auf dem Cog geblieben:** der End-of-Turn-Tail (`_post_deliver`/`_autosave_turn`/
`_maybe_compact`/`_persist_recap` — Recap/Session-Belang **mit Tests**), als **eine** `post_deliver`-Callback injiziert →
sauberer Schnitt **und 0 Test-Änderungen**. `dmcog.py` 1188→**662**, `delivery.py` 575. Ruff sauber. _Nicht-Byte-Effekt:
die verschobenen `log.*`-Zeilen tragen jetzt `voice.delivery` in der `%(name)s`-Spalte (Nachrichten/Formatierung gleich)._
_Aufgeschoben (eigene Runde unter ADR 035): die **Szenen**-Commands (`!ort`/`!szenen`/`!ortmodus`) + **`!lore`** → Mixin/
Sub-Cog (das sind Commands → `CogMeta`-Frage, nicht diese Kompositions-Verschiebung)._

**`runtime.py` weiter verschlankt: `_TurnTiming` nach `dmbot/turn_timing.py` ausgelagert (2026-06-14, D73 → ADR 034): Suite 319 grün.**
Nächster gescouteter Kontext-Lean-Kandidat (#1) aus der D70/D71-Liste, gleiche Mechanik (Tobis Linie: nur **in sich
geschlossene, zustandslose** Einheiten auslagern, Funktionalität unverändert). Der per-Turn-Latenz-Record `_TurnTiming` +
die Konstante `_CTX_WARN_FRACTION` (threadet `time.monotonic`-Stempel, emittiert die `[latency]`-Zeile + `[ctx]`-Warnung —
kein `SessionRuntime`-State) → neues **`dmbot/turn_timing.py`**; **Re-Export-Shim** in `runtime` (`# noqa: F401`) hält
`from ..runtime import _TurnTiming` (Cog/Dice/`test_autorecap`/`test_context_budget`) stabil, ungenutztes
`from dataclasses import dataclass` aus `runtime` entfernt. `runtime.py` 610→**516**. Byte-exakte Körper-Kopie,
**0 Test-Änderungen**, ruff sauber. _Einziger Nicht-Byte-Effekt: die `[latency]`/`[ctx]`-Zeilen loggen jetzt unter
Logger-Name `dmbot.turn_timing` statt `dmbot.runtime` (Nachrichtentext + `[latency]`-Prefix unverändert; Konsole-INFO
zeigt den Logger-Namen ohnehin nicht, kein Test prüft ihn)._

**`dmcog.py`: doppelten End-of-Turn-Tail in `_post_deliver` vereinheitlicht (2026-06-14, D72): Suite 319 grün.**
Reine DRY-Politur (kein ADR): Batch- und Streaming-Lieferpfad teilten die identische Abschluss-Sequenz (autosave →
mic-reanchor → Auto-Recap) → ein Helfer `_post_deliver`, von beiden nach ihrem **pro-Pfad** belassenen
`timing.end`/`log_line`/`_await_dice_scene`-Schritt aufgerufen. **Verhaltens- und geschwindigkeitsidentisch** (gleiche
Aufrufe/Reihenfolge/Args, läuft off-hot-path); die bewusst unterschiedliche `finally`-Platzierung von Dice/Scene (D40/D43)
**nicht** zusammengeführt — von Hand statt `/simplify` frei laufen zu lassen. _Datei bleibt groß; echtes Schrumpfen = späterer Cog-Split._

**`orchestrator.py` weiter verschlankt: Streaming-Assembler + `finalize_answer` ausgelagert (2026-06-14, D71 → ADR 034 E4): Suite 319 grün.**
Letzter sauber **abgekapselter** Block (Tobis Vorgabe: nur in sich geschlossene Methoden auslagern, damit sie nicht
mitgeladen werden, wenn ein Agent woanders arbeitet — Funktionalität unverändert). Neu: **`dmbot/llm/stream_assembler.py`**
(`StreamAssembler` + die geteilte `finalize_answer`-Naht, ADR-017-Parität; pure, kein `DMBrain`-State). Re-Export-Shim
hält Tests/`DMBrain` stabil; jetzt-ungenutzte Marker-/`dataclass`-/`split_completed`-Importe in `orchestrator` getrimmt.
`orchestrator.py` 933→**783** (gesamt 1175→783 über E1–E4). Byte-exakt verschoben, **0 Test-Änderungen**, Suite **319 grün**.
_`DMBrain`-Körper bleibt ganz (geteilter State). `dmcog.py`-Splits (Mixin/Runtime-Move) sind kein „abgekapselte Methode" → bleiben offen._

**`orchestrator.py` verschlankt: reine Helfer nach `dmbot/llm/*` ausgelagert (2026-06-14, D70 → ADR 034): Suite 319 grün.**
Kontext-Effizienz für künftige Agenten (Tobis Vorgabe: große Funktionen sinnvoll auslagern, **Funktionalität unverändert**).
Fan-out-Analyse ergab: `orchestrator.py` ist zweigeteilt — oben reine, zustandslose Helfer, unten die zustandsbehaftete
`DMBrain`. Das obere Band (E1–E3) in drei Module gezogen: **`llm/sanitize.py`** (Sprech-Säuberer, am häufigsten editiert),
**`llm/echo_guard.py`** (Echo/Selbstwiederholung, ADR 018/W4), **`llm/director_msgs.py`** (`!start`/`!intro`-Regie, ADR 031).
`orchestrator.py` 1175→933. **Re-Export-Shims** halten den Import-Surface stabil (Tests/`DMBrain`/Cog unverändert) →
verhaltensidentisch, **0 Test-Änderungen**, byte-exakt per Slice-Skript verschoben. `DMBrain`-Körper bleibt ganz.
_Aufgeschoben: E4 (`StreamAssembler`+`finalize_answer`) und die `dmcog.py`-Splits (Lore-Cog nach `_speak`→Runtime, Scene-Mixin)._

**Dritter Lieferart-Modus `puffer` (Head-Start-Puffer) ergänzt (2026-06-14, D69 → ADR 033 Addendum): Suite 319 grün.**
Tobis Idee: erst ein paar Sätze vorsynthetisieren, dann Satz 1 abspielen, Rest parallel weiter. Umgesetzt als
**dritte Lieferart** zwischen `stream` und `nahtlos`: `play_worker` sammelt `DM_SPEECH_PREBUFFER` (Default 3) WAVs vor
der ersten Wiedergabe (cushion gegen CPU-Synthese-Rückstand → Lücken später). `!sprechmodus puffer [zahl]` setzt Modus
+ Tiefe live. **Auf CPU:** kurze Turns ~lückenlos bei kleiner Startverzögerung; langes Intro startet viel früher als
`nahtlos`, bekommt aber später trotzdem Lücken (Synthese fällt zurück) — voll lückenlos überall bleibt GPU-Sache (ADR 002).
Live noch zu hören (nach dem Gate).

**Globaler Sprech-Modus (Lieferart × Intonation) für ALLE Turns (2026-06-14, D68 → ADR 033): Suite 316 grün.**
Tobi will sich auf **eine** Wiedergabe-Art für alle gesprochenen Texte festlegen (besser, ohne Anfälle) und vorher
A/B-testen. Zwei orthogonale Achsen, global + laufzeit-umschaltbar via **`!sprechmodus`**: **Lieferart** `stream`
(gestreamt, schneller Start, Mini-Lücken) vs `nahtlos` (eine durchgehende Spur, lückenlos, wartet auf Vollsynthese);
**Intonation** `flach` (alle Satzzeichen raus, kein Gibberish, flacher) vs `intoniert` (`.,!?` für Betonung behalten,
Gibberish-Risiko). `DM_SPEECH_MODE`/`DM_SPEECH_PUNCT` (Default `stream`+`flach`), Helfer auf der Runtime, Dispatch an
allen 6 Turn-Stellen liest global; `!intro test` bleibt fixer nahtlos+flach-Vergleichsanker. **Auf CPU**: `nahtlos`
wartet pro Turn auf die Synthese — flüssig erst auf GPU (LLM-Auslagerung, ADR 002, separat). Live A/B noch offen.

**Shutdown-Hänger „Voice-Channel verlassen" beschränkt (2026-06-14, D67 → ADR 020 Addendum): Suite 311 grün.**
Die Leave-Stufe hing wieder bis zu ~30 s, obwohl der Bot sofort sichtbar geht — Ursache war discord.py selbst:
`VoiceClient.disconnect(force=True)` macht den echten Leave zuerst, **wartet danach** aber bis zu
`VoiceClient.timeout`=30 s auf die Gateway-Bestätigung (`voice_state.py`, `wait=True` hartkodiert) — beim Beenden
wertlos. Neuer Helfer `dmbot/shutdown.py::disconnect_voice` beschränkt diesen Wait per `asyncio.wait_for`
(`VOICE_DISCONNECT_TIMEOUT`=2.0 s); `DMBot.close()` nutzt ihn + loggt eine Warnung bei Abbruch. Recv-Reader nicht
schuld (Daemon-Thread). `!leave` bewusst unangetastet. +2 Tests. _Live: zweimal Strg+C → Leave-Stufe ≤ ~2 s._

**`!intro` jetzt zweimodus + CPU-Ursache von „lädt ewigkeiten" gefunden (2026-06-14, D66 → ADR 031 Addendum): Suite 309 grün.**
Live-Log zeigte: **XTTS läuft auf CPU** (`.env TTS_DEVICE=cpu`, bewusst — 4070-VRAM voll mit nemo+Whisper, GPU-XTTS
crasht den Prozess + killt STT, ADR 002) → CPU-Synthese < Echtzeit, und das lückenlose `!intro test` wartet auf die
volle ~3,7-min-Synthese (`first_audio=378s`). Tobi wählte **Schnellstart mit Mini-Lücken**: plain `!intro` streamt jetzt
punktfrei (neuer `speech_transform` durch `_deliver_streaming`/`_deliver_answer`/`_speak`), spricht nach dem 1. Satz los
— Lücken bleiben (CPU-Synth kommt nicht hinterher). `!intro test` bleibt die lückenlose Variante. Live noch zu hören.
_Größerer Hebel offen: LLM auf 5080 auslagern (`OLLAMA_HOST`/Tailscale → `TTS_DEVICE=cuda`, ADR 002) oder Monolog kürzen._

**`!intro test` klingt jetzt wie EIN durchgehender Text (2026-06-14, D65 → ADR 031 Addendum): Suite 309 grün.**
Kollegen-Feedback: `!intro test` korrekt ausgesprochen, aber zäh — die Synthese jedes Satzes lag als Totstille
zwischen den Chunks (serielles `_speak` pro Satz). Tobis Ziel: gechunkt synthetisieren (kein Gibberish), aber
**lückenlos** abspielen. Umbau in `_deliver_intro_chunked`: jeder Satz wird einzeln (punktfrei) synthetisiert, die
WAVs via neuem `wavio.concat_wavs` mit 0,2s-Satzpause zu **einer** Spur gefügt und in **einem** Bridge-Call gespielt
→ durchgehend, natürlich getaktet. **Bewusster Trade-off:** erster Ton kommt erst nach Vollsynthese (XTTS ~0,5×
Echtzeit) — Preis für Lückenlosigkeit; schneller Start gäbe zwangsläufig Lücken (Streaming-Pfad). Live noch zu hören.

**`!intro`-Crash (Discord 2000-Zeichen-Limit) gefixt (2026-06-14, D64): Suite 306 grün, committet+gepusht (`1d48b18`).**
Kollegen-Run warf bei `!intro test` HTTP 400 / 50035 („Must be 2000 or fewer in length"). `SessionRuntime._send_with_retry`
zerlegt langen `content` jetzt zentral in ≤2000-Zeichen-Nachrichten (verbatim, neuer `split_for_discord`); deckt Batch/
Streaming/`!intro test` ab. Das `!intro`-Live-Gate unten ist damit vom Crash entkoppelt — bleibt aber inhaltlich offen.

**Kontext-Kosten gesenkt: Live-Docs verschlankt, Historie/Detail nach `docs/` ausgelagert (2026-06-14, D63 → ADR 032).**
`progress.md` 1637→678, `CLAUDE.md` 226→153: `## Last session`-Historie/Done-Phasen/erledigte Open Questions →
**`docs/progress-archive.md`**; Modul-Konventionen/Testing/Runtime/Troubleshooting/Style → **`docs/conventions.md`**
(beide on-demand, in Tabelle + README verdrahtet). Neue **Rotations-Regel** hält die Live-Dateien schlank; nichts
gelöscht (verbatim, 3 read-only Audits grün, Suite **302**). 9 Code-Kommentar-Zeiger auf verschobene Anker umgebogen.
_Effekt: ~17K Tokens/Session + ~1.5K/Turn. Commit `fa6c96d`._

**`!intro`-Eröffnungs-Monolog gelandet (2026-06-14, D62 → ADR 031): Suite 300 grün, live-unverified.**
Neuer `!intro`-Befehl (Aliase `!einleitung`/`!eroeffnung`) für Chemical Burn: **ein langer Eröffnungs-
Monolog**, der Ort/Ankunft/Auftrag etabliert **und jede Spielfigur mit voller Tiefe einbezieht** (Konzept/
Herkunft/Ziele/Verbindungen/Arc aus den Sheets). Gebaut durch **Wiederverwenden + Parametrisieren** des
`!start`-Pfads (nicht duplizieren, ADR 030): neues `CharacterStore.intro_roster_de()` + `build_intro_director_msg`
(Roster reitet in der Director-User-Message → ADR-019-Reihenfolge unangetastet) + durchgereichter
`num_predict`-Override (`DM_INTRO_NUM_PREDICT`, Default 800). `!start` bleibt das kurze Briefing. Szenen-Pointer
deterministisch (golden rule #3), Würfel unterdrückt, Stream+Batch. +7 Tests. _Live-Gate offen: `!intro` spricht
einen Monolog, der Ort/Auftrag/Ankunft nennt und jede Figur namentlich einbindet — kein Würfel, keine wörtlich
vorgelesenen privaten Ziele._

**Code-Review-Korrektheitsrunde gelandet (2026-06-13, D61 → ADR 030): Suite 293 grün, live-unverified.**
`/code-review` über die Tagescommits (`5d672b6~1..HEAD`) — der Cog-Split selbst sauber, **9 verifizierte
Bugs in der Feature-Arbeit** gefixt (funktionserhaltend): Warp-Containment würfelt jetzt gegen **Disziplin
(Psi)** statt Psi-Meisterschaft (IM p.163, der ungenutzte `psyker_purge_skill()` ist verdrahtet); ein
Party-Psyker außerhalb des Encounters verliert die **Warp-Aufladung** nicht mehr still (einmalige Warnung);
der **Würfel-Button** geht bei Sprach-Fehler nicht mehr verloren; **Auto-Recap** löscht keinen Turn mehr,
der während des `summarize`-await dazukommt; **verklebte Marker** (`<<ORT1>>`) werden gestrippt statt
vorgelesen; `resolve_test` schluckt keine echten Fehler mehr (golden rule #2); Streaming räumt verwaiste
Tasks/WAVs auf; **Layer-2-Mute ist ein Tiefenzähler** (Pause/Resume während der Wiedergabe unmutet nicht
mehr); Soak ist whitespace-robust. Plus Aufräumen (geteilte Helfer, toter Code weg, thread-lokale RAG-DB).
**Die Altitude-Punkte (system-agnostische Generalisierung von Engine/Marker/RAG-Quellen) sind bewusst auf
den Zweitsystem-/Phase-10b-Punkt aufgeschoben** (noch kein zweites System; ADR 005). _Nächstes Live-Gate
prüft das mit den unteren Prioritäten mit._

**Cog-Split-Refactor gelandet (2026-06-13, D60 → ADR 029): code-complete, Suite 263 grün.** Die
2300-Zeilen-`VoiceReceiveCog` ist in ein injiziertes `SessionRuntime` (`dmbot/runtime.py`) +
VoiceCog/DiceCog/DMCog zerlegt — rein strukturell, Verhalten exakt unverändert; `commands.py`
gelöscht, Cross-Cog-Fluss über fünf Runtime-Hooks (kein `bot.get_cog`). Kein eigenes Live-Gate:
ein Smoke-Test (`!join`→sprechen→`!dm`→Würfel-Button→`!leave`) deckt es ab; die Live-Prioritäten
unten (Playtest-Fixes) bleiben unverändert.

**Erste Live-Runde gespielt (2026-06-13) → Playtest-Fix-Runde gelandet (D57–D59, ADR 027/028),
live-unverified.** Hauptbefund: die Klage „geht null auf die Story ein" war eine **stille
`num_ctx`-Trunkierung** (8192 hartkodiert → Persona+Abenteuer fielen mitten in der Session aus dem
Prompt). Gefixt: `num_ctx` konfigurierbar+hoch (`OLLAMA_NUM_CTX=24576`, 4080) + rollierender
Auto-Recap, neuer `!start`-Eröffnungs-Command, Persona-Steuerung (Story/Spotlight/NSC-Initiative),
RAG entrauscht. Suite 262 grün. Details unter „Last session". _Nächstes Live-Gate prüft genau das._

**Phase 10a — the adventure is in the DM (D44/D45 → ADR 019): code-complete, live-unverified.**
The "perfect gamemaster" discussion (Tobi + Timos architecture critique) concluded that the
loudest failure — *the DM improvises from nothing* — needed Phase 10 pulled forward as a
**3-stage hybrid**, not pure vector RAG: (1) a German **adventure summary** always in the prompt,
(2) a deterministic **scene tracker** (Chemical Burn hand-authored into 15 German scene cards +
24 NPC statblocks under `data/adventures/chemical_burn/` — local-only, public repo; pointer =
`WorldState.scene_id`, moved via `!ort`/`!szenen`, statblocks via `!npc add`), and (3)
**rulebook-only RAG** (`sqlite-vec` + **bge-m3** — nomic failed German→English retrieval —
threshold-gated `## Regelwerk` block; store built offline, 1505 chunks, verified: "kritischer
Erfolg"/"Schwierigkeit" hit the right sections, table talk stays silent). Plus the **W4
self-repetition guard** (fuzzy match against the DM's own previous answer, retry-then-suppress).
Suite **191/191**. `DM_ADVENTURE=chemical_burn` is set in `.env`. _Open in Phase 10: the profile
bootstrap (gate half 2, ADR 005); the lore corpus is now covered for the needed factions —
**D48/ADR 021** curated German Imperium+Chaos compendium (`data/lore/`, sources `lore_imperium`/
`lore_chaos`), offline-verified; only D28's broad wiki corpus stays a later option._ **Both live
gates are now stacked: Phase 9 (HP survives restart) AND Phase 10 half 1 (rule question from the
book) — one circlejerk session can cover both.**

**Psyker / Warp subsystem (D51 → ADR 022, 2026-06-13): code-complete, live-unverified.** Tobi
wanted psykers **voll regeltreu** (not narrative-only) and pointed at the Inquisition Player's
Guide. Built as a **profile-driven** subsystem (engine stays system-agnostic, ADR 005): the IM data
— power catalog (Warp Rating + Difficulty per power), Warp-Threshold formula (= Willpower Bonus),
and the d100 Perils-of-the-Warp + Psychic Phenomena tables — lives in a new `psyker` block in
`data/systems/imperium_maledictum.json`; the engine gains pure functions `resolve_manifest`
(Manifest Test via `resolve_test`, Warp Charge per p.163 incl. Critical/Fumble/**Push**=Advantage),
`resolve_perils`/`resolve_phenomena` (banded d100), and `reverse_d100` + an `advantage` kwarg for
IM's reverse-the-digits Advantage (p.189). New `<<MANIFEST power [für name] [push]>>` marker mirrors
the `<<TEST>>` flow (marker → `ManifestRequest` → cog button → engine rolls + bookkeeps → fed back
to narrate). Warp Charge is a code-owned mutable resource on `Combatant` (persisted, shown in the
state summary). Catalog = all Core minor powers + core Biomancy + representative Player's Guide
Inquisition powers; full per-power prose comes from RAG (golden rule #7). The example psyker is
**Mortn** (Psi-Meisterschaft 45, Wil 48 → Schwelle 4). **Suite 220/220** (29 new fixed-seed psyker
tests, `tests/test_psyker.py`). _Timing simplification: the end-of-turn containment Test is resolved
at the end of the manifesting action (the conversational loop has no hard round boundary) — see ADR
022. Open: the Psychic Phenomena table has OCR-merged band boundaries to verify against the book;
`Psi-Meisterschaft`/`Disziplin (Psi)` skill names to confirm against the German edition._

**Inquisition guides embedded into the RAG (2026-06-13, follow-up to D51).** Both Inquisition
books are now in `rag.db` (bge-m3): the **Player's Guide** whole (`player_guide`, 502 chunks →
`## Regelwerk`) and the **GM-Guide spoiler-trimmed** (`gm_guide`, 226 chunks → `## Weltwissen`,
only p4–61/74–83/172–174 = Ordos/Philosophien, Lex Imperialis, Signs of Chaos/Xenos, Rosetten,
Radical Methods, Bestiarium). **Deliberately out** (same discipline as the Setting Guide's p1–57):
the *Heresies Macharia* campaign (p84–121), Sector-Threat villains, Open Case Files, the Inquisitor
patron sheets incl. **Halikarn** (p62–73), and the index (p175). Both sources wired into
`dmbot/rag/retrieve.py` `_SOURCES`. Verified: psyker/Monodominant/Forbidden-Knowledge questions hit
the new sources; spoiler probes ("Heresies Macharia", "Halikarn's secret") return nothing usable
(secret pages aren't in the DB; generic hits sit >0.45, gated out). Store now **2469 chunks**; suite
**230 green**. The generated `…GM-Guide.md` + `rag.db` stay git-ignored (bought-book derivatives)._

**TTS-Kauderwelsch gefixt (D53 → ADR 016 Nachtrag, 2026-06-13): code-complete, live-unverified.**
Live-Klage: beim Vorlesen Kauderwelsch v. a. an Satzzeichen, nicht im Transkript. Aktive Engine ist
XTTS (`.env TTS_ENGINE=xtts`); `normalize_for_tts` war eine **Blocklist** und ließ Emojis (🎲🌀🜏💥),
Pfeile/Bullets/`·` und exotische Leerzeichen durch, und leere/nur-Satzzeichen-Chunks erreichten die
Synthese ungefiltert. Fix in `dmbot/tts/`: `normalize_for_tts` ist jetzt eine **Whitelist** (NFKC,
Striche/`…`→Pause, dann nur Buchstaben/Ziffern/Whitespace + `. , ! ? ; : -`), und `chunk_text` +
beide `synthesize` haben einen **Pro-Chunk-Sprechbarkeits-Guard** (kurze Stille statt Junk an die
Engine). +6 Tests (233 grün). _Offen: live by ear prüfen; bei Restproblemen XTTS `repetition_penalty`/
`enable_text_splitting=False` nachziehen (in ADR 016 vermerkt)._

**Augmetik/Implantate + Psyker-Erstellungs-Backfill (D52 → ADR 023, 2026-06-13): code-complete,
live-unverified.** Implantate nachgezogen, im selben profil-getriebenen Muster wie Psyker (ADR 022)
— aber **passiv, kein Wurf** (kein Marker/Button). Neuer `augmetics`-Block im IM-Profil (Katalog:
Core-Augmetika S.152-154 + Inquisition-PG S.94-96, mit Körperzone/Verfügbarkeit/Kosten/`effects`;
weiches Limit = Zähigkeits-Bonus). `effects.type` `armour` → addiert zur PC-Soak in
`_apply_attack_damage`; `characteristic` (z. B. Augur-Array +5 Per) → addiert in `resolve_target`,
gematcht über Merkmalsname **oder** optionale `skills`-Liste am Effekt (Augur→Wahrnehmung);
`skill_sl`/`special` (Auspex, Mechadendrite, Kampfdrüse …) bleiben narrativ (Prompt-Block + RAG).
Helfer `augmetic_armour`/`augmetic_bonus` in `characters.py`; `_augmetic_block` im State-Summary;
Persona-Hinweis in `dm_core_de.md`. **Erstellungs-Backfill (dieselben Dateien, die für Psyker noch
fehlten):** `docs/how-to-create-a-character.html` bekam eine Augmetik-Checkbox-Liste (weicher
Zähigkeits-Limit-Hinweis) + eine Psioniker-Sektion (Disziplinen + Kräfte) → JSON-Block-Felder
(Katalognamen hartkodiert = müssen zum Profil passen); `tools/fill_character_sheet.py` füllt jetzt
die schon vorhandene (aber leere) Psi-Tabelle aus `known_powers` × Profil-Katalog + Warp-Schwelle =
WillkürB, und rendert Augmetika in die mittlere Ausrüstungsspalte (kein eigenes Bogenfeld). Beispiel:
Vask hat „Augmetischer Arm", Mortn „Augur-Array". **Suite 230/230** (+10 Augmetik-Tests,
`tests/test_augmetics.py`). _Offen: Katalognamen HTML↔Profil synchron halten; deutsche
Fertigkeits-/Merkmalsnamen gegen die deutsche Edition prüfen._

**Visible, fast shutdown (D47 → ADR 020, 2026-06-13): code-complete, live-unverified.** Tobi: "der
Bot geht nur sehr schwer aus und das dauert sehr lange" + wanted to see what/how many things shut
down. Two causes, two fixes. **(1) The slow exit** was TTS synth on `asyncio.to_thread` — asyncio's
default executor threads are **non-daemon**, so the interpreter joined an in-flight multi-second GPU
XTTS synth at exit (dead wait — the WAV is moot when quitting). New `dmbot/shutdown.py`
`to_daemon_thread()` runs synth on an abandonable daemon thread; both `_speak` and the streaming
`synth_worker` use it. **(2) No feedback:** the second Ctrl+C painted a bare `Shutting down...` dots
line. New `ShutdownProgress` prints `[i/n] label` per teardown stage (animated, then ✓ + duration);
`DMBot.close()` declares the count up front (voice disconnects + each cog's `TEARDOWN_STEPS` + the
Discord close) and wraps each stage, `VoiceReceiveCog.cog_unload` reports its four closes
(STT/LLM/RAG/bridge), and a final summary names any dropped synth. Two-stage Ctrl+C unchanged. Suite
**181/181** (count includes the adventure/RAG tests landed between sessions). _Verify live: Ctrl+C
twice during a streamed turn → prompt exit + the `[i/n]` lines._

**Post-roll robustness round (D43 → ADR 018) after the 2026-06-12 echo collapse: code-complete,
live-unverified — the Phase-9 gate is STILL pending (the gate attempt ran in the wrong channel).**
Tobi's session "fühlt sich nicht mehr wie ein Gamemaster an" diagnosed from `debug.log` +
`history.jsonl` as a failure chain, not model regression: wrong channel → silent example-party
fallback (Mortn/Seskin instead of the registered party); the unreliable inline marker won the
dedupe and requested **Heimlichkeit for an attack**; the bare `[Würfel]` feedback line made nemo
**predict the next player line** instead of narrating — the label-strip turned that into a
clean-looking echo that was spoken, stored, and self-reinforced (three turns of "Ich greife den
Kultisten an."). Fixes landed (all deterministic): **echo guard** (retry once with nudge, then
suppress + keep the pair out of history), **roll-feedback directive** on results-only turns,
**router-wins dedupe** (flips D40's marker-wins), **autosave race fix** (snapshot `user_msg` at
generation end), `!join` **party announcement + example-fallback warning**, `chat_stream` read
timeout 300 s (the cold-start ReadTimeout), and the **ADR 016 length squeeze rolled back**
(160→220, "zwei bis vier Sätze" — streaming removed the latency justification). Suite **157/157**.

**Cross-cutting latency/robustness work (ADR 017 streaming + D40 router timing + D41 autosave):
live-confirmed in part.** Streaming works (`first_audio≈3.2s`, 2026-06-10) and the **Phase-9 recap
auto-loaded on `!join` + a strong `!wrap up`** (memory narrative half effectively confirmed); D42
fixed marker-only turns + the dice loop. _Still to prove live:_ the **HP-survives-restart** half of
the Phase-9 gate, the D43 fixes above, the router-button-during-speech feel, the crash-restore, and
the open meta-ramble (persona/adherence).

**Phase 9 — memory: code-complete, live gate still pending — plus a playtest-tuning round
(2026-06-10) that is itself live-unverified.** Three live logs drove fixes for the DM **puppeting
the whole party**, **runaway turn length (= the latency)**, and **XTTS reading punctuation aloud**
(→ **ADR 016**). Every log was *pre-change*, so the next Discord run is the first proof of both the
tuning **and** the Phase-9 memory gate.

**Phase 9 — memory — code-complete (2026-06-09); live gate pending.** Phases 0–8 are live-validated
⭐. Phase 9 (JSON world state + recaps) is now **built and unit-proven (102/102)**; what's left is the
**live Discord gate** Tobi must run: an HP change survives a restart, and the next session opens with
a correct recap. Design (D32/D33 → **ADR 015**): a **split** — `characters.json` stays the read-only
sheet, a new code-owned `data/sessions/<id>/state.json` holds the mutable layer (wounds/conditions/
inventory, NPCs, quests, location, recap), seeded once from the sheet and saved atomically on every
change. **Auto-combat damage** is wired: a successful attack rolls weapon damage and applies
**weapon + SL − soak** (TB + armour) to a target (auto if one candidate, else a dropdown; `!npc add`
registers enemies; `!damage`/`!heal` are GM overrides). The recap is generated by `!wrap up`
(`DMBrain.summarize`), stored in `state.json` (+ `recap.md`), and re-injected on `!join` with a compact
world-state block (CLAUDE.md prompt order). **Model: mistral-nemo.** Recommended dial for the live
gate / any follow-up: **Opus 4.8 / xhigh**.

---

## Next concrete step (Verlauf)

_Aus `progress.md` rotiert (2026-07-17, Journal-Runde ADR 053): der datierte
Carry-over-Block aus „Next concrete step" — verbatim._

_Carry-overs & future directions (Stand 2026-06-12 abends):_
1. **Modell-Test (Timo):** Mistral Small (o.ä.) auf Timos Box / der 5080 via Tailscale —
   unabhängig vom Story-Code, Umschalten = `OLLAMA_HOST`-Einzeiler (D6/ADR 002). A/B gegen nemo
   mit identischer Story fahren, erst NACH der Gate-Session (sonst zwei Variablen gleichzeitig).
2. **Director→Narrator-Experiment (Timos Architektur-Idee, Diskussion 2026-06-12):** ein
   constrained-JSON-Call entscheidet pro Turn strukturiert *was passiert* (Szenenziel,
   NSC-Aktionen, State-Änderungen), nemo macht nur Prosa. **Bewusst aufgeschoben** — der
   Szenen-Tracker (ADR 019) ist die deterministische Vorstufe; erst bauen, wenn Live-Spiel
   zeigt, dass `!ort`-Handarbeit nervt oder die Szenen-Kohärenz trotz Karten kippt.
   Kosten wären ~+1–3 s pro Turn (Single-GPU).
3. **„The Blazing Seraph"** (Starter-Set-Abenteuer, 49 S., eigenes Bestiarium) → zweites
   Szenen-Kompendium, NACH dem Chemical-Burn-Live-Test (Feedback einarbeiten). Danach:
   `DM_ADVENTURE` umschalten genügt.
4. **„Villains on Voll" (Setting Guide S. 58–67) nachingestieren**, sobald die
   Chemical-Burn-Kampagne durch ist (`pdf_to_md --pages 58-68` → `ingest --source setting`).
5. **RAG-Schwelle tunen:** `MAX_DISTANCE` 0.45 ist auf wenigen Fragen kalibriert; deutsche
   Zustandsnamen („Blutend") liegen knapp drüber. Gegen Live-`📚`-Logzeilen nachjustieren.
6. **Repo-Sichtbarkeit (Tobi-Entscheidung):** Repo ist PUBLIC → `data/adventures/` bleibt
   untracked (Ableitung gekaufter Bücher). Auf privat stellen + whitelisten, wenn das
   Kompendium versioniert/auf die 5080-Box synchronisiert werden soll.
7. **Remote/Tailscale bridge (ADR 010)** — implemented, **never live-tested**; two-machine check
   per README "Split hosting" when wanted.
8. **Roll-router live feel** — router-wins ist seit D43 die einzige Quelle; spurious/odd buttons →
   classifier prompt (`dmbot/llm/roll_router.py`) tunen. Inline `<<TEST>>` nur noch bei
   `DM_ROLL_ROUTER=0`.
9. Older: STT confidence filter on noisy speech; toggleable edit/review window (Part 2; pause
   control D27/ADR 013 is its groundwork); **input bleed** (stream audio into mics — wake-word
   concern, not a bug); benign `voice_recv` `voice_member_disconnect` traceback (alpha lib — watch).
10. **Player-wish status (ADR 016 W-Liste):** **W1** (puppeting) Code-Backstops seit ADR 016,
    **W2** (Latenz) ✅ Streaming ADR 017, **W3** (Stop-Button) ✅ Tobi, **W4** (Wiederholung)
    Code-Guard seit D45 (live-unverified), **W5** (exakte Frage) adressiert über
    Roll-Direktive + Szenenkarten + W4-Nudge (live-unverified), **W6** (TTS-Interpunktion) ✅,
    **W7** = Phase-9-Gate (pending), **W8** (derbe Inhalte engagen) **offen** — nemos Ceiling,
    beim Modell-Test (Punkt 1) mitbewerten.

_Aus `progress.md` rotiert (2026-07-11, Live-Gate-Triage-Runde 5/5): der Gate-Fahrplan
des Live-Runs, gemerged in `docs/live-run-script.md` — hier der Wortlaut (verbatim)._

**Live-gate triage round → docs/live-run-script.md** (Workflow-Migration Runde 5/5, die letzte; der Live-Run-Fahrplan unten bleibt die Projekt-Prio).

> **Drehbuch für den Live-Run:** alle offenen Gates unten sind als abhakbare Checkliste in
> **[docs/live-test-checklist.md](docs/live-test-checklist.md)** ausformuliert (Session-Reihenfolge:
> Vorbereitung → Tempo → Intro → Gespräch → Würfel → Scene Cards → Konsistenz-Wächter →
> **Uhren** → **Zeit & Fristen** → NPC-Gedächtnis → **NPC-Agenden** → **Lose Fäden (Hälfte 1, §7c)** → RAG → Neustart-Gate → Nachbereitung; Chekhov-Hälfte 2 = Folge-Session). Nach dem Run:
> Ergebnisse hierher zurückschreiben, Liste ausmisten.

**0. Vorab (D89 ✅ / D90):** Die 20 fehlenden `.env`-Keys sind nachgezogen (`dm-sync` meldet 38/38, 2026-07-02). Vor dem nächsten Timo-Sync auf beiden Maschinen `uv run dm-sync` (Timo vorher einmal `git pull` + `uv sync`), Blöcke diffen (SETUP.md §„Staying in sync").

**1. Der EINE Live-Run der Spielbarkeits-Tuning-Runde (Top-Prio, Tobi nächste Session — pullt `f44cba8` + Neustart).** Zwei Teile in einem Run:
- **Workstream A (Tempo/GPU-Offload) zuerst, reine `.env`:** `OLLAMA_HOST` auf die Offload-Box + `TTS_DEVICE=cuda` setzen → `nvidia-smi` (kein OOM, XTTS-cuda + Whisper passen auf die freie 4070) → `[latency]`-Zeile vorher/nachher (`first_audio`/`tts` fallen klar, Sprech-Lücken weg). Wenn schnell genug: Default-Lieferart Richtung `nahtlos` live abwägen; dann **ADR-002-Addendum + `architecture.md` §3** nachziehen.
- **Dann `!intro test` + ein paar Spieler-Turns + eine Regelfrage:** Intro zuverlässig **ein** Monolog mit **jeder Figur** (C1-Retry greift bei zu kurz/Figur fehlt, D86), **weniger Wiederholung/Generik** (B1 repeat_penalty, D85). Tuning live: `DM_REPEAT_PENALTY` (1.0 = aus, höher = strenger), `DM_INTRO_TEMPERATURE` (0.8 mehr Flair / 0.3 ruhiger). Schließt nebenbei **Phase-10-Gate-Hälfte 1** (Regelfrage aus RAG) + die offenen D82–D84-Intro-Punkte ab.
- **Neu dazu (D91, im selben Run abprüfbar) — das NPC-Gedächtnis-Gate:** eine Szene spielen und einem NSC etwas Markantes erzählen (ideal: ihn **anlügen**, z. B. eine falsche Identität behaupten) → Szene wechseln (`!ort` oder bestätigter `<<ORT>>`-Button; Konsole zeigt `🧠 NPC-Gedächtnis: N neue Erinnerungen`) → `!npcmem <Name>` zeigt den Eintrag (Lüge mit Zitat, `believed` noch true) → **zurückkommen** und prüfen, ob der DM sich im Dialog erinnert (der `[NPC-Gedächtnis: …]`-Block reitet im Prompt). Kür: die Lüge im Spiel auffliegen lassen → nächster Szenenwechsel → `!npcmem` zeigt „LÜGE aufgeflogen" + Wichtigkeit-5-Eintrag, Haltung eine Stufe Richtung hostile. Feature ist **live-unverified** bis dahin; Fehlverhalten (Small Talk als Wichtigkeit 5, erfundene Erinnerungen) → `prompts/npc_memory_extract_de.md` nachschärfen oder `DM_NPC_MEMORY=0`.
- **Neu dazu (D92, im selben Run abprüfbar) — das Konsistenz-Wächter-Gate (Checkliste §6b):** einen NSC auf 0 Wunden bringen (oder das tote-NSC-Setup aus dem D87-Skript nutzen), dann das Gespräch gezielt auf ihn lenken („frag Grendel, was er gesehen hat") → im Batch-Pfad (`!sprechmodus nahtlos` oder ein Würfel-Folge-Turn) sollte bei einem Verstoß die `[consistency] violated … regenerating once`-Zeile feuern und die gelieferte Antwort den Toten **nicht** sprechen lassen; im Default-`stream`-Modus stattdessen die Log-only-Warnzeile beobachten (Trade-off, ADR 045). Fehlverhalten (False Positives → unnötige Regenerationen) → Verbliste/Muster in `dmbot/llm/consistency.py` schärfen oder `DM_CONSISTENCY_GUARD=0`.
- **Neu dazu (D87, im selben Run abprüfbar):** Stateful-Scene-Cards-Live-Skript — (a) `!ort` zeigt die Element-IDs (⬜); (b) eine Gelegenheit im Spiel abschließen → `<<ERLEDIGT>>`-Button erscheint, Antwort enthält kein `<<`, nach „Abhaken" zeigt `!ort` ✅ und der nächste Prompt-Dump „Bereits geschehen:"; (c) `!offen`/`!erledigt` togglen ohne Button; (d) einen `leads_to`-Eintrag testweise auf `{"ziel": …, "requires": "opp-1"}` setzen → Ziel fehlt in „Mögliche nächste Orte", Auto-`<<ORT>>` dorthin wird abgelehnt (🚫-Konsolen-Zeile nennt `opp-1`, nichts im Channel), nach `!erledigt opp-1` geht's; (e) NSC auf 0 Wunden → Karte rendert `(tot)`, übersteht Neustart. (Stand ist committet + gepusht — nur pullen + Neustart.)
- **Neu dazu (D94, im selben Run abprüfbar) — das Consequence-Clocks-Gate:** vor oder während der Session eine Uhr anlegen (`!uhr neu "Arbites-Ermittlung" 6` — Panel erscheint mit ◉/○-Segmenten), dann den DM einen Tick provozieren (etwas Lautes/Riskantes tun oder eine Probe verhauen — die Uhr steht als `[arbites-ermittlung] … 0/6` im Weltzustand-Prompt) → ein `⏱ Tick vorgeschlagen`-Button erscheint (Antwort enthält kein `<<`), nach Bestätigung zeigt das **Panel** den neuen Stand (edit-in-place, keine neue Nachricht). Kür: per `!uhr tick` bis auf voll ticken → nächster DM-Turn trägt die `[Regie] Die Uhr „…“ ist voll`-Zeile und der DM erzählt die Konsequenz; danach `!uhr weg`. Fehlverhalten (Marker feuert nie / bei jedem Beitrag) → Persona-Bullet in `prompts/dm_core_de.md` nachschärfen; Misfires bleiben dank Confirm-Button folgenlos.
- **Neu dazu (D95, im selben Run abprüfbar) — das Ingame-Zeit-Gate:** `!zeit` zeigt „Tag 1, 08:00 (Morgen)"; eine kurze Frist setzen (`!frist neu "Treffen mit dem Informanten" +2h` — Druck-Panel zeigt 🕐-Zeit + ⏳-Frist), dann spielen: (a) der DM webt die **Tagesphase** in Beschreibungen ein (abends/nachts andere Stadt); (b) bei spürbar vergehender Zeit (Durchsuchung, Fußmarsch, Rast) erscheint ein `🕐 Zeitfortschritt vorgeschlagen`-Button (Antwort enthält kein `<<`), nach Bestätigung zeigen Panel + `!zeit` den neuen Stand; (c) ein Szenenwechsel schiebt +30 min (Konsole/Panel); (d) die Frist per `!zeit +3h` **verstreichen lassen** → nächster DM-Turn trägt `[Regie] Die Frist „…“ ist verstrichen` und der DM spielt die Konsequenz ein; `!fristen` zeigt ABGELAUFEN bis `!frist weg`. Fehlverhalten (Marker feuert nie / ständig / absurde Sprünge) → Persona-Absatz nachschärfen; Misfires bleiben dank Confirm-Button + 12h-Clamp folgenlos.
- **Neu dazu (D96, im selben Run abprüfbar) — das NPC-Agenden-Gate:** einem markanten NSC ein Ziel geben (`!agenda <NSC> "will die Ware aus der Stadt schaffen"` — `!agenden` zeigt es), dann **zwei Szenen spielen** (jeder Szenenwechsel triggert die 🧠-Extraktion, die jetzt auch den Agenda-Schritt vorschlägt) → `!agenden` zeigt nach jedem Wechsel den neuen offscreen-Schritt (mit Ingame-Zeitstempel) und die Frage ist: **hat sich seine Lage glaubwürdig bewegt** (kleine konkrete Schritte, plausibel zur verstrichenen Zeit — keine Festungsbauten über Nacht)? Dann zurück zum NSC: der DM spielt die veränderte Lage (Block trägt Ziel + Schritte); während er woanders ist, sollten Gerüchte/Spuren auftauchen (Weltzustand-Zeile). Fehlverhalten (absurde Sprünge, Schritte für ziellose NSCs im Text, tote Planer) → `prompts/npc_memory_extract_de.md`-Agenda-Regel nachschärfen; `!agenda <NSC> weg` oder `DM_NPC_MEMORY=0` schaltet ab.
- **Neu dazu (D97, braucht ZWEI Sessions) — das Chekhov-Gate:** in Session 1 beiläufig ein markantes Detail etablieren (oder direkt seeden: `!faden neu "Die Münze aus der Bar" 2`), am Ende `!wrap` — Konsole zeigt `🧵 Chekhov-Liste: N neue Fäden, M aufgelöst`, `!fäden` zeigt die Liste. In Session 2 prüfen: spielt der DM das Detail bei passender Gelegenheit zurück (der Top-3-Block „Lose Fäden" reitet im Weltzustand) — und zwängt er es NICHT in jede Antwort? Kür: den Faden im Spiel auflösen → das nächste `!wrap` markiert ihn `resolved` (`!fäden`). Fehlverhalten (Quest-Duplikate, Banalitäten als Faden, Dauer-Callbacks) → `prompts/chekhov_extract_de.md` bzw. den Persona-Bullet nachschärfen; `!faden weg <id>` räumt auf.
- **Neu dazu (D93, Nachbereitung des Runs):** aus dem rotierten Journal der Session ein **frisches Live-Golden** ziehen (`tests/golden/README.md`: kopieren → auf eine Handvoll Turns kürzen → `uv run dm-eval <datei>` muss sofort Exit 0 sein). Referenziert es Chemical Burn, bleibt es lokal (data/adventures/ ist git-ignored) — trotzdem wertvoll als Regressions-Gate auf Tobis Maschine. Ab dann: `uv run dm-eval` vor jedem Refactor-Merge (conventions.md §Testing).
- Danach: Log pasten → Playtest-Triage-Iteration. **Bootstrap bleibt zurückgestellt**, bis das Spielen rund läuft.
- **Parat, wenn Abenteuer #2 dran ist (D88):** `/author-adventure <md> <id>` — erst „The Blazing Seraph" per `/rag-ingest`-Konverter nach `data/pdfs/md/`, dann der Skill (stoppt zur Szenenschnitt-Freigabe). Drafts landen im untracked `data/adventures/<id>/` — Buch-Derivate bleiben lokal, nur der Skill ist committet.

**2. Die offenen Phase-9/10-Live-Gates abhaken (Code ist da, nur Live-Abnahme fehlt):**
- **Phase 9:** eine HP-Änderung übersteht einen echten Neustart + der Recap erscheint beim nächsten `!join` (in-prompt).
- **Phase 10:** eine konkrete **Regelfrage** wird korrekt aus dem Regelbuch-RAG beantwortet. Danach das **einzige noch zu bauende** Feature: **Profil-Bootstrap (§9)** — der DM schlägt aus dem Regelbuch ein System-Profil vor → Tobi bestätigt → speichern.

**Zusätzlich diese Session live zu verifizieren** (alle code-complete, unverifiziert) — fällt im
selben circlejerk-Run mit ab:
- **Schneller Start** (ADR 024): Konsole erreicht zügig „logged in"; `!join` zeigt ggf. ⏳/⚠-TTS-Hinweis; erster Satz wird gesprochen.
- **`!lore tts`**-Reader: Block-Text im Chat + ⏭/🔊/⏹; **Doppel-Beleg** in `debug.log` (eine `🔊 TTS … speaking` + ein `/speak` pro Block ⇒ Doppeln liegt an **Bot A**).
- **Conditions/`!rules`**: „Was bewirkt Blutend/Betäubt?" → korrekte deutsche Antwort (neue `conditions`-Quelle); Inquisitions-Fragen treffen player_guide/gm_guide.
- **Wiederholung**: verweist der DM auf Etabliertes knapp, statt es neu auszuerzählen?
- **Auto-Szenenwechsel** (ADR 026): die Gruppe betritt einen verbundenen Ort → DM beendet den Zug mit `<<ORT …>>` (**nicht** gesprochen), ein **„Wechseln"-Knopf** erscheint, Klick verschiebt den Pointer wie `!ort`; eine erfundene/Nicht-Nachbar-ID im `verbunden`-Modus wird ignoriert+geloggt. `!ortmodus frei` testen, dann zurück. `scene_id` überlebt Neustart.

**ONE live session in circlejerk covers everything (Tobi).** Before it: **review the compendium**
(`data/adventures/chemical_burn/adventure.json` + `npcs.json` — spot-check scene cards for tone
and the never-say secrets). Then `!j` **in circlejerk** and check in this order:
1. **Join line-up:** party named (**die drei neuen Charaktere** — a ⚠ warning = wrong channel,
   stop) + `📖 Abenteuer: Chemical Burn — Szene: Der Auftrag`.
2. **Phase 10 gate half 1:** ask a rule question by voice („Was passiert bei einem kritischen
   Erfolg?") → answer grounded in the book (a `📚 Regelwerk:` line appears in `debug.log`).
3. **Plot coherence (D44):** the DM opens with Halikarns Auftrag, not improv; `!ort mud_gate` →
   the narration moves to the harbour; a part-1 „wer steckt dahinter?" stays unspoiled.
4. **D43 checks:** post-roll turn narrates the consequence (no parroted player line — watch for
   `echo guard` WARNINGs); attack → **combat-skill** button (router decides); `history.jsonl`
   pairs correct when 🎲 is clicked mid-speech.
5. **Phase 9 gate:** `!npc add Kultist` (statblock auto-fills now) → attack → `💥 …` → **restart**
   → `!j` → wounds unchanged; recap flow as before.
6. **W4/W5:** ask „Warum sind wir hier?" twice — expect an answer, not a re-description (watch
   for the self-repetition WARNING). Then fill the Phase-9 + Phase-10(half) VERIFY EVIDENCE.
7. **Lore (D46):** eine Rokarth-Frage („Wem gehört diese Stadt eigentlich?") → Antwort mit
   Setting-Färbung (`📚`-Logzeile zeigt `setting:`); „wer steckt hinter Gratis?" bleibt vage.
8. **Lore (D48/ADR 021):** eine Chaos-Frage („Was weiß man über die Chaosgötter?") → grimdark
   Antwort mit Kompendiums-Färbung (`📚`-Logzeile zeigt `lore_chaos:`); eine Imperiums-Frage
   („Was ist das Astronomican?") zeigt `lore_imperium:`.
9. **`!lore` (D49):** `!lore` blättert (◀/▶), `!lore wer ist der Imperator?` antwortet als
   Embed (Retrieval offline schon verifiziert — hier nur checken, dass Embed + Buttons im
   echten Discord rendern).
10. **Psyker (D51/ADR 022):** with a psyker in the party (the example **Mortn**, or a new build
    with a `psyker: true` + `known_powers` + a `Psi-Meisterschaft` skill), have them wield a power
    by voice → a `🌀 Manifestation angefordert` button appears; click it → a `🌀 … Warp X/4` line,
    and the DM narrates the effect. Push a power a few times to drive Warp Charge over the threshold
    → a `🜏 Perils of the Warp` line fires and Warp resets; the value survives a restart. First do
    the **Player's Guide RAG ingest** (command in Current focus) so a psyker rule question
    („Was sind Perils of the Warp?") retrieves the book.
11. **Augmetik + Erstellung (D52/ADR 023):** ein Charakter mit Implantat (Beispiel: Vask
    „Augmetischer Arm", Mortn „Augur-Array"). Greif Vask an → Soak +1 (1 Wunde weniger); ein
    Wahrnehmungs-Wurf für Mortn liegt +5 höher. Im Weltzustand erscheint der
    `## Augmetik/Implantate`-Block. Erstellung: `docs/how-to-create-a-character.html` öffnen →
    Implantate/Psioniker wählen → JSON enthält `augmetics`/`known_powers`;
    `tools/fill_character_sheet.py` → Psi-Tabelle, Warp-Schwelle und Augmetik-Spalte sind im PDF gefüllt.
Watch `ctx=` in the `[latency]` lines — the adventure block adds ~1k tokens; the D36 warning
fires above 85% of 8192. Dial: **Opus 4.8 / xhigh** (roadmap recommends opusplan/high for
Phase 10 planning; the building is done — the run is verification).

**✅ Prerequisite resolved (2026-06-10) — party registered + session reset.** The
`circlejerk` channel (`1343673766487654464`) now has a hand-authored
`data/sessions/<id>/characters.json` with three deliberately-different IM builds (so rolls aren't
raw any more): **Garran Vex** (Pr0degie/Tobi — Nahkampf bruiser, Kettenschwert 1d10+5, Tgh 52),
**Eli Castor** (Timo — Fernkampf, Lasgewehr 1d10+4), **Magos Yann** (Sezgin/SezBoss69 — tech/skill,
„Schockstab" not in the weapons table → tests the `default_damage` 1d10 fallback, starting condition
„Benommen"), with aliases mapping each Discord name → character. The old `state.json` + `history.jsonl`
+ `recap.md` (seeded from the example party, test-run garbage, bar recap) were **deleted**, so the
next `!join` re-seeds the world state fresh from the new sheet. (Channel files are git-ignored —
session-local.)

**Secondary live checks (same session, when convenient — older landed-but-unproven work):**
- **D42 re-confirm:** no empty/marker-only turn read aloud (no 15-s lone quote), **no dice loop**.
- **Crash recovery (D41):** kill the bot hard (not `!leave`) → `!j` → `restored N conversation
  turns`; a clean `!leave` → next `!j` is fresh.
- **Router timing (D40):** the 🎲 appears **while the DM still speaks**; exactly one per action.
- **first_audio contrast** + `!redo` + pause/Esc mid-stream: one turn with `DM_STREAMING=0`.
- **Shutdown (D47 + D67):** Ctrl+C twice during a streamed turn → exit is prompt (no multi-second hang)
  and prints `[i/n] … ✓` per stage + a summary that names the dropped synth. **D67:** the
  „Voice-Channel verlassen" stage now finishes in ≤ ~2 s (no more up-to-30 s confirmation hang); a
  `voice confirm wait abandoned` warning is fine (the channel is already left).
- **Vor der Session:** `docs/how-to-play.html` an Timo & Sezgin verteilen (deutsches
  Regel-Primer, 2026-06-12 erstellt) — spart die Regelerklärung am Tisch.

**Watch (persona/adherence, not gate blockers):** the **meta-ramble** („Als Spielleitung beschreibe
ich nicht direkt die Szene…") — nemo's ceiling, report if frequent; and whether XTTS still reads any
*real* punctuation aloud (the lone-quote bug is fixed; `. , ! ?` are kept on purpose for intonation).

**Exact test sequence (durable copy of the chat checklist — `DM_LOG_FILE=1` + `DM_TRANSCRIPT_FILE=1`
are already on in `.env`):**
1. _Auto-combat:_ `!j` → `!npc add Kultist 10 3` (10 Wunden, ToughnessBonus 3; optional armour as a
   4th arg) → `!test Nahkampf für Timo` (or a voice "ich greife den Kultisten an" → router posts the
   button) → click 🎲 → on success, pick **Kultist** in the target dropdown → expect a `💥 … = N Wunden
   → Kultist M/10` line. Confirm it fires **only** on Nahkampf/Fernkampf + only on success.
2. _Gate 1 (HP survives restart):_ check `data/sessions/<id>/state.json` shows the reduced wounds;
   `!npc list`; try `!damage Kultist 5` / `!heal Kultist 3` (0 → "kampfunfähig"). **Restart the bot** →
   `!j` → wounds still reduced.
3. _Gate 2 (recap):_ play a few turns → `!wrap up` (or `!wrapup`) → German "Was bisher geschah" posted +
   stored (`state.json` recap + `data/sessions/<id>/recap.md`). **Restart** → `!j` → "📜 Was bisher
   geschah" shown and the DM continues from it.
4. _Watch & report (paste `debug.log` + `transcript.log`):_ damage numbers sane? target dropdown listing
   fellow PCs annoying or fine? does the DM honour the injected world-state HP without inventing values?
   recap quality (German, factual, length)? any `ERROR` lines?
5. _Latency / streaming (D35 + ADR 017):_ every DM turn logs `[latency] turn=… [stream] stt=…
   trigger→llm_done=… ctx=…/8192 gen=… chars=… first_audio=…ms tts=… bridge_wait=… total=…`. Paste a
   few — the **before/after** is `first_audio` (streamed) vs `trigger→llm_done + tts` (the old
   pre-audio gap). Toggle `DM_STREAMING=0` for one turn to see the old single-WAV line for contrast.
6. _Crash recovery (D41):_ play a few turns → **kill the bot** (not `!leave`) → `!j` → expect
   `restored N conversation turns`. Then a clean `!leave` → next `!j` is fresh and the old log is at
   `data/sessions/<id>/history.<ts>.jsonl`.
- Run the unit suite with **`uv run --with pytest python -m pytest -q`** (pytest isn't in the default
  venv — see [[run-tests-command]] memory). Currently **177/177** green.

_Resolved this session (no longer open):_ the **gemma3 vs nemo** taste test (gemma3 didn't fix the
marker problem; nemo kept for tone — the fix was the **roll-detection router**, ADR 014); **two-stage
Ctrl+C** shutdown (done); the **auto-test** (router, live-validated).

_Aus `progress.md` rotiert (2026-07-04, D98): die erledigten „Next concrete step“-Einträge des D60–D63-Verlaufs (verbatim)._

**Kontext-Split erledigt (2026-06-14, D63 → ADR 032):** Live-Docs verschlankt, Historie/Detail in `docs/`; nichts
Code-/Bot-seitig offen, Rotations-Regel aktiv. Der eigentliche nächste Schritt bleibt das `!intro`-Live-Gate unten.

**`!intro`-Eröffnungs-Monolog: ERLEDIGT (2026-06-14, D62 → ADR 031).** Suite 300 grün; nichts Code-seitig
offen. **Live-Gate** (im selben circlejerk-Run mit abprüfen): `!join` → `!intro` → der DM spricht **einen**
zusammenhängenden Monolog, der **Ort** (Hive Rokarth / Welt Voll), **Auftrag** (Halikarn/Gratis) und das
**Hergekommensein** nennt **und jede Figur namentlich** mit einem passenden persönlichen Moment einbindet;
**keine** Würfel-Aufforderung; **keine** wörtlich vorgelesenen privaten Ziele/Arc. Gegen-Check: `!start` ist
weiterhin das kurze 2–4-Sätze-Briefing. Bei nemo-Abschweifen/Auslassen einer Figur: `DM_INTRO_NUM_PREDICT`
senken oder (Fallback) auf die verworfene Multi-Beat-Sequenz umstellen (ADR 031 Alternatives).
_Der **2000-Zeichen-Crash** des ersten Kollegen-Runs ist gefixt (D64) — `!intro` postet jetzt mehrteilig; das
Live-Gate ist nur noch eine **Inhalts-/Qualitäts**-Prüfung, kein Crash-Test mehr._

**Code-Review-Korrektheitsrunde: ERLEDIGT (2026-06-13, D61 → ADR 030).** Suite 293 grün; nichts
Code-seitig offen. Im Live-Run **gezielt mitprüfen**, was die Fixes berühren: (1) ein Psyker mit
hoher Psi-Meisterschaft / niedriger Disziplin manifestiert über Schwelle → Perils erupten jetzt
*häufiger* (Containment gegen Disziplin); (2) verklebte `<<ORT…>>`/`<<MANIFEST…>>` werden nicht mehr
vorgelesen; (3) der Würfel-Button erscheint auch wenn die Sprachausgabe mal hakt. Die Altitude-Punkte
sind bewusst aufgeschoben (s. Open questions).

**Cog-Split-Refactor: ERLEDIGT (2026-06-13, D60 → ADR 029).** Code-complete, Suite 263 grün;
abzunehmen mit einem **Smoke-Test** (`!join` → sprechen → `!dm` → Würfel-Button → `!leave`) — kein
eigenes Live-Gate. Die Live-Prioritäten unten (Playtest-Fixes + Phase-9/10-Gates) sind unberührt.

**Schritt 0 — neue Party: ERLEDIGT (2026-06-13).** Die drei neuen Charaktere (Fridolin / Gellicus /
Rektalus) sind gebaut, validiert, zur `data/sessions/1343673766487654464/characters.json` + Aliases
gemergt und **committet** (allowlisted → läuft beim Kollegen); kein `state.json` → erster `!join`
seedet frisch; die alten Party-Bögen sind archiviert, neue Bögen gefüllt. **→ Der Blocker für den
Gate-Run ist weg.** _(Sezgin könnte Rektalus' Werte noch finalisieren, sonst startklar.)_

---

## Phase status — abgeschlossene Phasen (volle Details)

### ✅ Phase 0 — Foundation & setup
- [x] Repo + project structure (skeleton per `architecture.md` §12; uv/Python-3.12, `.gitignore`, `.env.example`)
- [x] Discord DMbot app + token (in `.env`). _(Bot A token already exists in the music bot repo.)_
- [x] Ollama installed locally on the 4070 + models pulled (`mistral-nemo`, `nomic-embed-text`) + reachable
- [x] Model taste test → primary model chosen: **mistral-nemo**
- **Manual setup (outside the agent): see `SETUP.md`.**
- **Gate:** `curl` to Ollama from Tobi's machine → German answer.
- **VERIFY EVIDENCE:** Gate met 2026-06-04 — `curl http://localhost:11434/api/generate` with
  `mistral-nemo` returned a plausible grimdark German answer ("Die Finsternis hat sich über die
  Welt gelegt wie ein Grabtuch aus Eisen…"). Tooling: git 2.42, Python 3.12.10, uv 0.11.19,
  Ollama 0.30.4 on `:11434`, models `mistral-nemo` + `nomic-embed-text` pulled, NVIDIA 596.49
  (RTX 4070). Discord DMbot created, token in `.env`. **Primary model: `mistral-nemo`**, chosen
  via taste test (scene description + NSC dialogue) over gemma3:12b / qwen3.5:9b / glm-4.7-flash
  (glm 19 GB doesn't fit 12 GB; nemo gave the most idiomatic German + dialogue). Deferred to
  later phases (flagged, not blocking): cuDNN/cuBLAS DLLs (B3→Phase 4), Piper voice (B5→Phase 6),
  Opus DLL + mic (B6→Phase 2), rulebook/adventure PDFs (B7→Phase 10).

### ✅ Phase 1 — Bridge: Bot A `/speak`  (Bot A side done, out of order)
- [x] `POST /speak` (aiohttp) in the music bot
- [x] `/speak` blocks until playback ends (return = resume signal)
- [x] `/health` + `!dm` status command; localhost only; serialized by lock; music stopped first
- **Gate:** `curl -X POST .../speak` with a test WAV → audible.
- **VERIFY EVIDENCE:** Implemented & code-reviewed — `Pr0degie/musicbot` branch
  `dungeon_master`, commit `249cc38`. Contract in `architecture.md` §3. Music cogs untouched.
  **Gate met 2026-06-04:** `GET /health` → `{"status":"ok","bot":"EarRape#8961"}`;
  `curl -X POST :8765/speak` with a 2 s test WAV (both bots in voice channel `circlejerk`) →
  `HTTP 200 {"status":"played"}`, the call **blocked 2.09 s** (= the WAV's full length,
  confirming the blocking-return contract D15), and Tobi confirmed the tone was **audible**.

### ✅ Phase 2 — DMbot scaffold: voice receive
- [x] Voice join + `discord-ext-voice-recv` sink (`!join`/`!j`/`!leave`/`!vstatus`)
- [x] per-user PCM log (decoded 48 kHz stereo s16le; heartbeat every 2 s)
- [x] Bot A's user-ID filtered (protection layer 1) — explicit `BOT_A_USER_ID` + `.bot` flag
- [x] Windows: Opus loaded via discord.py's bundled DLL (B6 satisfied, no manual install)
- [x] _(unforeseen)_ DAVE/E2EE layer decrypted on receive → clean Opus (ADR 006)
- **Gate:** PCM frames in the log; Bot A's own voice absent.
- **VERIFY EVIDENCE:** Gate met 2026-06-04. Live test in voice channel `circlejerk`: two human
  speakers (`Pr0degie`, `Timo`) logged with `▶ receiving audio` + `PCM ⟳` heartbeats; **Bot A
  ("EarRape", id 1361375360784273409) filtered** — `layer-1: filtering out …`, never tallied.
  After wiring the DAVE/E2EE decrypt (ADR 006): consistent Opus TOC `0x78…`, **~100 % decode,
  0 dropped**; a captured WAV analysed as real speech (ZCR 0.061, 13 % silent frames). Stack:
  `discord.py 2.7.1`, `discord-ext-voice-recv 0.5.2a179`, `davey 0.1.4`, Opus bundled DLL.
  Remaining `lost being flushed` jitter (sender voice-activation) is benign, quieted in logs.

### ✅ Phase 3 — VAD segmentation
- [x] Resample 48k/stereo → 16k/mono (`voice/resample.py`, `soxr.ResampleStream` per user)
- [x] silero-vad → cut utterances (`voice/vad.py`; onnx via onnxruntime, ADR 007; wired as `VadSink`)
- [x] **Live gate met** — clean per-speaker utterances; Tobi confirmed the WAVs sound right
- **Gate:** one sentence = one utterance, start/end correct.
- **VERIFY EVIDENCE:** _Offline (2026-06-04):_ resample ratio ≈ 16000 samples/s; pure silence →
  **0 utterances** (no false trigger); `UtteranceSegmenter` state machine verified with a
  scripted fake model — clean utterance cut=1, sub-250 ms blip dropped, mid-sentence pause
  <600 ms not split, real >600 ms gap splits into 2, flush mid-speech emits. Stack:
  `onnxruntime 1.26.0`, `soxr 1.1.0`, `numpy 2.4.6`, vendored silero v5 onnx (~2 MB).
  _Live (2026-06-04):_ first live run surfaced **two bugs, both fixed + offline-reproduced:**
  (1) silero v5 needs a **64-sample context** prepended (576-sample input, not bare 512) — bare
  512 scored prob≈0 on clear speech (0/1874 frames), fixed → 1451/1874 voiced; (2) **voice
  activation** means clients send no RTP while silent, so utterances never closed — fixed by
  wrapping in `SilenceGeneratorSink` (injects silence; lock-guarded sink). After the fixes a
  live utterance + WAV was produced. _Final gate met (2026-06-04):_ clean run (bot start
  18:56:56) segmented **both** speakers per sentence — Pr0degie 9 utterances (0.99–5.06 s),
  Timo 4 (1.06–8.51 s), each dumped as a 16 kHz mono WAV; **Tobi listened to the WAVs and
  confirmed they sound clean/correct**. Utterances also close now while a speaker is silent
  (silence injection), so separate sentences no longer merge. Stack live: `discord.py 2.7.1`,
  `discord-ext-voice-recv 0.5.2a179`, `onnxruntime 1.26.0`, `soxr 1.1.0`.

### ✅ Phase 4 — STT (faster-whisper)
- [x] faster-whisper wrapper (`dmbot/stt/transcriber.py`): worker thread + queue (off the audio
      path), 16k mono s16le → German text via `WhisperModel`, CPU-int8 fallback
- [x] Windows cuDNN/cuBLAS: `os.add_dll_directory()` for the `nvidia-*-cu12` wheel `bin` dirs in
      `stt/transcriber.py` — no manual `PATH` (SETUP B3 done)
- [x] Wired into `VoiceReceiveCog`: `_on_utterance` → `transcriber.submit`; transcript logged
      as `📝 <name> | <clip>·<ms> | <text>`; model via `WHISPER_MODEL/DEVICE/COMPUTE` env
- [x] **`medium` is the default** (beat `small` clearly in the live German test)
- [x] Hallucination guard: drop segments with high `no_speech_prob` / low `avg_logprob`
      (kills the "Vielen Dank für's Zuhören" phantoms on short/quiet clips)
- **Gate:** German sentence transcribed correctly.
- **VERIFY EVIDENCE:** _Live (2026-06-04):_ a ~16-min two-speaker session transcribed German
  correctly throughout — long, complex, well-punctuated sentences (e.g. *"Nichtsdestotrotz steht
  mir der Christoph, Markos Vater im Wege."*; a 60-word run captured verbatim). Players confirmed
  in-channel: *"ihr habt's perfekt transkribiert"* + *"ging echt schnell"*. `medium` clearly beat
  `small` (small mis-heard the quieter speaker; medium got him). GPU: `faster-whisper 'medium'
  loaded on cuda (float16)` via in-code DLL registration; ~0.77 s to transcribe 8 s audio.
  Remaining: rare stock-phrase hallucinations on short/near-silent clips → now filtered by
  confidence. Stack: `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `nvidia-cudnn-cu12 9.23`.

### ✅ Phase 5 — LLM wiring + DM persona
- [x] Ollama client (`llm/client.py`, async httpx, `/api/chat`; host+model from config — ADR 002)
- [x] `prompts/dm_core_de.md` (generic GM persona, German) + `campaign_tone_de.md` (Eisenhorn overlay) — layered loader `llm/persona.py` (ADR 005)
- [x] `DMBrain` (`orchestrator.py`): per-channel history (in-memory) + lock-guarded player-line buffer
- [x] Wired: voice transcripts buffer per channel; `!dm` / `!dm <Text>` triggers a turn → answer logged `🎭` + posted to the text channel
- [x] Output hygiene for TTS: strip role labels/markdown; `stop` sequences + truncation so the model plays **one** DM turn and never fabricates player replies
- **Gate:** text prompt → German DM answer in the campaign's tone.
- **VERIFY EVIDENCE:** _Offline (2026-06-04), real Ollama + `mistral-nemo` + the real persona:_ a
  German player line ("Ich öffne die schwere Eisentür…") yields an atmospheric grimdark DM answer
  in Eisenhorn tone (flackernde Lumen, Rost/Weihrauch, ein Adept-NSC mit Stimme), addresses players
  by name, ends with "Was tut ihr?"; a follow-up turn correctly uses the history. After hardening:
  exactly one DM turn, no fabricated player lines, no "Spielleitung:"/markdown leakage.
  _Tuning (2026-06-05, after live play):_ nemo added a "Als Spielleitung beschreibe ich:" preamble
  and drifted off the players' actions → **mitigated** — persona sharpened (top "Worauf du
  reagierst" directive), buffer capped to the recent `DM_MAX_LINES`, `_sanitize` strips the
  preamble (`tests/test_orchestrator.py`). _Still open:_ the **nemo vs gemma3:12b** taste test with
  this persona, if the tone/responsiveness still needs more.

### ✅ Phase 6 — TTS + first full loop ⭐  (PLAYABLE)
- [x] Piper wrapper (`tts/piper.py`): `de_DE-thorsten-medium` → WAV in the OS temp dir
      (`tempfile.gettempdir()`, not `/tmp`); loaded once, synth off the event loop
- [x] Bridge client (`bridge.py`): async httpx `GET /health` + blocking `POST /speak`
      (architecture §3 contract); WAV deleted after playback so temp doesn't fill
- [x] Wired: `!dm` answer → Piper → `/speak` (spoken); `!say <Text>` smoke test; LLM + TTS
      times logged (`⏱`, `🔊`). Piper missing → text-only, bot still runs
- [x] **Live full loop confirmed** (2026-06-04, 21:37): `!dm` → German DM answer → spoken aloud,
      Tobi heard it; no self-hearing (layer-1 filters Bot A)
- **Gate:** speak → DM answers audibly; latency measured; no self-hearing.
- **VERIFY EVIDENCE:** Live full loop works end to end and is **audible** (player line → nemo →
  Piper → Bot A `/speak`). Piper: voice loads ~1.3 s, synth ~130–1250 ms (length-dependent).
  **Latency caveat (the Phase-6 tuning target):** `⏱ LLM = 15.2 s` on the first turn. Root cause
  is **VRAM pressure** — `ollama ps` shows nemo at **9.5 GB / 100% GPU with a 16384 context**, and
  total VRAM sat at **11.8/12.3 GB** (nemo + whisper-medium 2.5 GB + desktop apps), so nemo
  cold-loads/runs under near-full memory. _Mitigations applied in code:_ `num_ctx=8192` (smaller
  KV cache) + `keep_alive=30m` (no cold reload between turns). _Biggest remaining lever (Tobi):_
  run whisper on CPU or `small` to free ~2.5 GB, and/or offload Ollama to the 5080 via Tailscale
  (ADR 002). Bridge fix this session: Bot A had to be on the `dungeon_master` branch (the `main`
  branch has no DMBridge → "All connection attempts failed").

### ✅ Phase 7 — Turn-taking & feedback protection layer 2  (live-validated)
- [x] VAD pause while Bot A speaks — `VadSink.mute()/unmute()` (`voice/recv.py`); `_speak()` mutes
      around the **blocking** `/speak` and unmutes in `finally` (D15: blocking return = Bot A quiet).
      `mute()` flushes in-progress utterances first. **Now opt-in, off by default** (D25,
      `DM_PAUSE_VAD_WHILE_SPEAKING=0`): redundant beside layer 1 + the routing gate, and it blocked
      transcribing the table during narration — which players wanted recorded. Mechanism kept for
      mic-bleed cases. Layer 1 (Bot-A user-ID filter) stays mandatory (golden rule #4).
- [x] Session state per channel — cog keeps the `self._sink` handle (set on `!join`); `!leave`
      now `self._brain.reset(channel)` + drops the sink + clears the per-user counters, so a
      re-join starts a fresh session.
- [x] **Push-to-talk DM-routing gate (D24/ADR 011)** — a shared Discord mic button (`discord_ui/mic.py`,
      the project's first View). The whole table is **always transcribed + logged** (full record,
      Tobi wanted it — recap/memory groundwork); the button gates only **what reaches the DM**:
      utterances are tagged `for_dm` when cut (carried through the STT worker) and only those are
      buffered. `→DM` marks routed lines in the log. `!mic` re-posts; `DM_PUSH_TO_TALK=0` routes all.
- [x] **Latency + quality fixes from the first live session** — GPU whisper (`WHISPER_DEVICE=cuda`,
      D24); buffer capped to recent `DM_MAX_LINES` (default 8) so table talk doesn't drown the action;
      persona sharpened (action-resolution as the top directive); `_sanitize`/`_strip_leading_label`
      kill the "Als Spielleitung beschreibe ich:" preamble and a leaked leading "Name:" (the DM was
      answering **as** a player — `tests/test_orchestrator.py`).
- [x] **Unit tests** (deterministic parts): `tests/test_feedback_layer2.py` (mute + listen gate)
      + `tests/test_orchestrator.py` (sanitize, label strip, buffer cap). **20/20 green.**
- **Gate:** two people speak → orderly reaction, no feedback loop.
- **VERIFY EVIDENCE:** _Live, four real multi-player sessions (2026-06-05/06, 3 players: Timo,
  Sezgin/SezBoss69, Pr0degie)._ Confirmed in the transcripts: multiple speakers captured per-user;
  **push-to-talk routing works** — only button-window speech carries the `→DM` marker and reaches
  the DM, the rest is log-only (`push-to-talk → 🎙 an die Spielleitung` / `⏸ nur Protokoll`);
  **no feedback loop** — Bot A filtered every turn (`layer-1: filtering out EarRape`), the DM never
  re-transcribed its own voice; the DM answers the routed lines **in order**; players confirmed
  "transkribiert er unsre Zeug trotzdem noch" while the DM spoke (layer-2 opt-out working). GPU
  whisper kept up (~100–1000 ms/clip). Quality tuning (preamble, POV, no-advance, TTS chunking) was
  done from these transcripts and is in the unit suite (**29/29**) — but is **persona/model-limited**
  (nemo); residual drift is the gemma3 lever, not a Phase-7 gate failure.

### ✅ Phase 8 — Dice engine, system profile & turn-order buttons  (live-validated)
- [x] `rules/engine.py` — generic dice + resolution engine (profile-driven, seeded RNG) **+ unit tests**.
      Dice parser (`XdY±N`, `d5`), `resolve_test` via a resolver registry (IM `roll_under` first), SL =
      tens-difference, crit/fumble on doubles, 01–05 / 96–00 auto-bands, `describe_result_de` (the
      "🎲 Tobi auf Wahrnehmung … — Erfolg, 2 EG" line that feeds back into the prompt).
- [x] `data/systems/imperium_maledictum.json` — first hand-written profile (1d100 roll-under, SL =
      tens-difference) + the **difficulty ladder** (name → modifier) + aliases. Loader/validator
      `rules/profile.py`. **Numbers now VERIFIED against the IM Core Rulebook** (Difficulty Table p.188,
      Success Levels, Automatic Success/Failure) — ladder Very Easy +60 … Very Hard −30, auto-bands
      01–05/96–00 (Marginal → SL 0), crit/fumble-on-doubles noted as IM's combat rule, damage =
      weapon Damage + SL (not d10/d5). Done via `tools/pdf_to_md.py` on the bought PDF (2026-06-07).
- [x] `rules/characters.py` — lean character JSON store (schema follows the profile) + display-name→
      character **alias map** (fixes F) + pure `resolve_target` (skill value + difficulty → target, all
      in code). Example party `data/sessions/_example/characters.json` ships so it runs out of the box.
- [x] `rules/marker.py` — tolerant `<<TEST skill [difficulty|±N] [für name]>>` parser; strips markers
      from the spoken text; unparseable marker → generic manual button (ADR 004 fallback).
- [x] Text-channel views (`discord_ui/dice.py` + `turnorder.py`, the `mic.py` View→cog pattern):
      dice button rolls via the engine + narrates the consequence; turn-order rotates over the voice
      members. New commands `!roll` / `!test` / `!turn`(`!order`); `DM_SYSTEM` env.
- [x] LLM marker flow wired: persona documents the marker + difficulty words; orchestrator extracts
      tests (before the sentence-trim), posts a dice button per test, feeds the result back so the next
      DM turn narrates the outcome.
- [x] **Roll-detection router (D29 / ADR 014)** — the inline `<<TEST>>` proved unreliable live (the model
      self-resolves; only 2 good markers/session, model-size-independent per research). Added a separate,
      stateless **constrained-JSON classifier** (`llm/roll_router.py` + `DMBrain.classify_test`, skill enum
      = the character's sheet) that picks the test after narration and posts the button; the inline marker
      stays as fallback. Behind `DM_ROLL_ROUTER` (off by default, A/B). Verified: nemo **8/8** offline,
      full path smoke-tested end-to-end vs Ollama. _Live A/B pending Tobi (`DM_ROLL_ROUTER=1`)._
- [x] **Unit tests (deterministic core):** `tests/test_rules_engine.py`, `test_profile.py`,
      `test_marker.py`, `test_characters.py`. **Suite 63/63 green** (34 new + 29 existing).
- **Gate:** button roll correct (result + degrees for the profile); turn order rotates; tests green.
- **VERIFY EVIDENCE:** _Code + unit level (2026-06-07):_ the engine's correctness is unit-proven with a
  seeded RNG (success/fail boundaries, SL tens-difference, crit/fumble on doubles, auto-bands, the
  d100-as-"00" case) and the full marker→resolve→roll path verified end to end against the real IM
  profile + example party (`<<TEST Wahrnehmung Schwer für Tobi>>` → Mortn, Wahrnehmung 44 − Schwer 20 =
  target 24 → roll 42 → "Fehlschlag, 2 EG").
  _Live (Tobi, Discord, 2026-06-08):_ **(2a)** `!test … Schwer für Tobi` → the dice button posts and the
  result + degrees match the engine (verified live across several rolls, incl. the doubles-crit on 44);
  **(2c)** `!turn` rotates over the voice members with ▶/◀; **(3)** the voice loop + push-to-talk
  auto-send work; **(4)** the **auto-test now fires reliably via the roll-detection router (D29/ADR 014)**
  — the inline `<<TEST>>` was unreliable live (the model self-resolves; root-caused from the debug log),
  so a separate constrained-JSON classifier picks the test after narration and posts the button. Tobi:
  "funktioniert jetzt besser." **Suite 81/81.** Router is the default auto-test path; inline marker stays
  as fallback.


---

## Open questions (erledigt/archiviert)

**Aus der Doc-Diet-Runde rotiert (2026-07-11):**
- ✅ **Aufräum-Pass `progress.md` — erledigt (2026-07-04 D98 Teil B + 2026-07-11 Doc-Diet-Runde).**
  Ursprünglicher Eintrag (aus der D82–D84-Runde): „Current focus“ (D75–D81) + „Next concrete step“
  (D61–D74) haben Vorsessions-Verlauf angesammelt, der eigentlich ins `docs/progress-archive.md`
  gehört (Rotation wurde übersprungen). Ein dedizierter Lean-Pass steht aus — bei Gelegenheit,
  kein Bot-Risiko. — Erledigt durch die D98-Teil-B-Rotation + die Doc-Diet-Runde (State header,
  Current-focus-Rotation auf 2 Blöcke, Decision-Log-Diät mit ADR-Addenda).

**Aus der Content-Runde Debug-Kampagne rotiert (2026-07-11) — vier alte Prose-Blöcke, je eine
Ein-Zeilen-Summary bleibt live (Volltexte hier verbatim):**

- **Deferred altitude debt from the code-review round (2026-06-13, D61 / ADR 030):**
  These are the review's *altitude* findings — real, but the **system-agnostic generalisation** they
  ask for is postponed to the **second-profile / Phase-10b** point (ADR 005's profile bootstrap). There
  is no second system yet to generalise against, the changes are large + behaviour-risky, and the
  project's stance (D1) is "IM is the first profile; generalise when the second arrives". Revisit each
  when a second system is actually loaded:
  - **Engine hardcodes IM arithmetic.** `engine.warp_charge_gain` (Success=Warp-Rating, Critical−WB,
    Fumble×2, Push+1d10) and `reverse_d100` + the `advantage` digit-reversal bake IM's p.163/p.189 rules
    into the generic engine. Move the charge-gain + advantage model into the profile alongside the
    resolution/degrees rules that are already data.
  - **RAG corpus catalog is IM-/OCR-specific in code.** `retrieve._SOURCES` (source names + German
    group labels) and `_is_junk_hit` (IM-PDF OCR-noise regexes) live in the retriever. A second ruleset
    needs them in data/profile + ingest-time denoise, not hardcoded.
- **From the Phase-7 playtests (2026-06-06) — carry into Phase 8 / quality work:**
  **Latency grows with context** as history accumulates; the 20-turn cap helps but recaps (Phase 9)
  are the real fix. **Now observable (D35/D36):** the per-turn `[latency]` line shows
  `ctx=<prompt>/8192 gen=<eval>`, and a WARNING fires once the prompt passes ~85% of `num_ctx` — so
  the cap-creep is no longer silent. Capture the live baseline before the streaming work; don't raise
  `num_ctx` (KV-cache VRAM) — trim history/recap/state if the warning shows.
- **Loose ends / housekeeping (from the Phase 3 session):**
  - **Intermittent voice-connect `TimeoutError` on `!join`** (seen once, ~18:45): the discord.py
    voice handshake occasionally times out; the command errored but a retry joined fine. Benign
    so far — watch it; if it recurs, look at the connect timeout / a clean error message in
    `voice/commands.py` rather than the raw traceback.
  - Logging now also writes `logs/dmbot.log` (UTF-8, gitignored) — handy for inspecting a run
    after the window closes.
  - Continuous silence injection runs silero on every silent user ~50×/s (cheap, ~1–2 %/core
    each); fine for a small table, revisit only if many idle users ever cost CPU.
- **From the streaming/robustness session (2026-06-10) — open, carry forward:**
  - **Pending live validation (Tobi tests 2026-06-11).** What's already confirmed live: streaming
    (`first_audio≈3.2s`) + the Phase-9 recap. Still open: HP-survives-restart (+ auto-combat),
    re-confirm the D42 tuning (no empty read-aloud, no dice loop), crash-restore (D41), router timing
    (D40), first_audio before/after. (2026-07-11: alles ins Live-Run-Skript gemerged.)
  - **Open persona/adherence — meta-ramble (nemo's ceiling).** On one live turn the model broke the
    fiction mid-narration („Nein, tut mir leid, ich habe mich versprochen. Als Spielleitung beschreibe
    ich nicht direkt die Szene. Ich reagiere lediglich auf das, was die Spielenden tun…") and it got
    spoken. Not the leading-preamble shape `_strip_meta_preamble` catches, and a generic mid-text
    meta-stripper risks false positives. Left as a persona/tone-LoRA item; watch frequency.
  - **Caveat — `[latency] gen=` can be stale on a *client-side* stop-label abort (streaming).** When a
    mid-text speaker label trips `StreamAssembler.stopped` and the brain aborts the httpx stream, the
    Ollama `done` object (which carries `eval_count`) never arrives, so `last_stats` — hence the
    `[latency]` line's `gen=`/`ctx=` — holds the **previous** turn's numbers. In practice Ollama's
    server-side `options.stop` (the `\n<label>:` sequences) usually stops generation first **with** a
    `done` object, so this rarely shows; the client-side cut is only the safety net. Not worth fixing
    now — but if a `gen=` ever looks implausibly carried-over after a truncated turn, this is why.
    (Stored history is unaffected — `finalize_answer` recomputes from the accumulated raw either way.)
  - **first_audio reliability depends on XTTS-on-GPU latency per sentence.** Streaming spreads synthesis
    over sentences, so per-sentence synth must keep up with playback or gaps appear between sentences.
    Watch the live `tts=` (now summed) vs `wav=`; if synth lags, the `wav_q` (maxsize=1) backpressure
    just means the table hears a short gap — acceptable, but a signal that XTTS is the next bottleneck
    (→ Part-2 streaming-TTS, the deeper W2 latency lever).

**Aus der Cleanup-Runde rotiert (2026-07-04, D98):**
- ✅ **Kosmetik (D60/ADR 029) geputzt (D98).** Ursprünglicher Eintrag: „ein Docstring-Beispiel in
  `dmbot/logsetup.py` (`_short_name`) nennt noch das gelöschte `dmbot.voice.commands` als Beispiel;
  und verschobene Log-Calls tragen ihren neuen Modulnamen in der opt-in `debug.log`-`%(name)s`-Spalte
  + WARNING-Konsolenzeilen (`runtime`/`voice.dmcog` statt `voice.commands`). Bewusst nicht angefasst
  (außerhalb des Refactor-Scopes); Log-Messages + Green-Chat/Transcript-Format unverändert. Bei
  Gelegenheit putzen." — Das Docstring-Beispiel heißt jetzt `voice.delivery`; die neuen Modulnamen in
  der `%(name)s`-Spalte sind kein Mangel, sondern der korrekte Stand nach dem Cog-Split.
- ✅ **Per-marker pipeline grows linearly (D61/ADR 030 Altitude-Debt) — eingelöst (D98 → ADR 051).**
  Ursprünglicher Eintrag: „Each new director marker means a bespoke regex + dataclass in `marker.py`,
  a wider `finalize_answer` tuple, and a third/fourth parallel `_pending_*` dict in the orchestrator
  + a `take_pending_*`. One keyed marker structure (`{kind: [...]}`) would collapse the triplication;
  do it before the next marker, not after. _Stand D94: NICHT eingelöst — `<<UHR>>` (ADR 047) ist der
  fünfte Marker auf demselben Muster (`finalize_answer` jetzt 6-Tupel, fünftes `_pending_*`-Dict);
  der Seam-Preis war erneut rein mechanisch, aber er wächst. Die Konsolidierung ist jetzt ein guter
  `/improve-architecture`-Kandidat MIT dm-eval als Regressions-Gate (ADR 046 existiert inzwischen
  genau dafür) — vor einem etwaigen sechsten Marker wirklich machen._" — Umgesetzt als deklarative
  `MarkerSpec`-Registry + generische Strip/Queue/Pending-Naht, marker-weise migriert (ORT zuletzt),
  Suite/ruff/dm-eval nach jedem Schritt grün (ADR 051).

**From the Phase-7 playtests (2026-06-06):**
- ✅ **(gemma3) Taste test done (2026-06-08).** gemma3:12b narrates cleaner than nemo (no
  meta-ramble/English-leak/"Was-tut-ihr"-tic) but its **dice markers were no better** (still
  self-resolves), and nemo's tone is preferred → **kept nemo**. The marker problem was *not* the model
  (documented LLM-GM failure) — fixed architecturally by the roll-detection router (D29/ADR 014). The
  residual narration drift (POV, attribution) stays nemo's ceiling; a tone-LoRA is the Part-2 lever.
- ✅ **(F) Player → character name mapping — addressed in Phase 8 (ADR 012).** The character JSON
  carries a display-name→character **alias map**, injected as a light prompt hint
  (`CharacterStore.alias_hint_de`), and turn order shows character names. _Verify live whether nemo
  actually stops confusing them; a fuller fix is still character registration (D13/ADR 003)._
- ✅ **(K) Dice/skill-check design — realised in Phase 8 (ADR 012).** The GM rolls **for** the player
  and the difficulty number comes from the profile ladder, never the LLM: marker names a skill +
  difficulty *word* → `rules/characters.resolve_target` (skill value + ladder modifier) → engine.
  _The IM ladder/SL/auto-bands are verified against the bought rulebook (2026-06-07); verify the live feel._

**Only empirical, to decide in Phase 0 (try it, not design):**
- ✅ **Model:** decided — **mistral-nemo** as primary (taste test 2026-06-04 vs gemma3:12b /
  qwen3.5:9b / glm-4.7-flash: best idiomatic German + NSC dialogue; glm too big for 12 GB).
  `gemma3:12b` is the atmospheric runner-up — worth re-checking against nemo in Phase 5 with the
  real persona prompt if the tone needs more richness.
- **TTS voice:** `de_DE-thorsten-medium` vs. `thorsten_emotional` — listen. _(Phase 6.)_

**From the streaming/robustness session (2026-06-10):**
- ✅ **Gate prerequisite resolved (2026-06-10) — party registered + session reset.** The first run
  couldn't run the HP-gate because the PC wasn't in `characters.json` (raw rolls, no damage
  persisted). Now the `circlejerk` channel has a hand-authored sheet (Garran Vex / Eli Castor / Magos
  Yann, three different builds + aliases) and its old `state.json`/`history.jsonl`/`recap.md` were
  deleted so `!join` re-seeds fresh. (Channel files are git-ignored; only the `_example` party is
  checked in.)

**Loose ends / housekeeping (from the Phase 2 session):**
- ✅ `docs/pipeline-diagram.*` removed (Tobi, 2026-06-05) — no longer a loose end.
- ✅ **Voice stack now safeguarded against silent breakage (2026-06-05).** The version
  sensitivity (DAVE decrypt into `_connection.dave_session`; voice-recv alpha) is now caught,
  not just documented: the three voice dists are pinned `==` in `pyproject.toml`;
  `voice/preflight.py` checks versions + attribute paths at boot and the live `dave_session`
  at join (loud warnings on drift); `recv.py` warns+skips a DAVE frame (magic `0xFAFA`) when no
  session is reachable instead of decoding garbage; `tests/test_voice_stack.py` is the offline
  canary (5/5 green). Verified-stack table added to ADR 006. **Still required on any upgrade:**
  run the smoke test + a live re-verify, then bump `KNOWN_GOOD` + the pins + the ADR table.
- DAVE decrypt skips frames received before the MLS group is `ready` (brief startup gap), and
  single-packet RTP jitter ("lost being flushed", sender voice-activation) is benign for STT.

**Resolved design questions (now in the decision log / ADRs):**
- ✅ Ollama host → D6 / ADR 002
- ✅ Conversational control (when the DM speaks) → D10 / ADR 003
- ✅ VAD vs. push-to-talk → resolved: VAD segments, button triggers the DM turn (D10)
- ✅ Dice test trigger → D11 / ADR 004
- ✅ Character stats in the JSON state → D12 / ADR 004
- ✅ Character registration → D13 / ADR 003
- ✅ Recap trigger → D14
- ✅ Bot A status signal → D15
