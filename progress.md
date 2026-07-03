# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
**NPC-Gedächtnis gebaut (2026-07-03, D91 → ADR 044). Suite 486 grün (+27), ruff-F sauber, committet auf `main`, live-unverified.** NPCs erinnern jetzt, was mit ihnen besprochen wurde: pro NSC eine gedeckelte `memories`-Liste in `state.json` (Gist + wörtliches Schlüsselzitat bei Versprechen/Lüge/Drohung, `believed`-Flag für Spieler-Lügen), extrahiert durch **einen** LLM-Call pro Szenenwechsel (`!ort` / bestätigter `<<ORT>>`) + `!wrap` als Catch-all — nie pro Turn. Golden Rule #3 überall: der Extraktor schlägt nur vor, Code klemmt die Haltung auf ±1 Stufe/Szene (`hostile→wary→neutral→friendly→loyal`), kippt aufgeflogene Lügen (believed=False + Wichtigkeit-5-Eintrag + eine Stufe Richtung hostile) und verteilt Wichtigkeit-≥4-Neuigkeiten deterministisch als Hörensagen an gleiche-`faction`-NSCs. Top-K pro Szenen-NSC im Prompt (`DM_NPC_MEMORY_TOP_K`, Lügen immer dabei), `DM_NPC_MEMORY=0` = aus, `!npcmem` = Debug-View. **Live-Gate offen** (s. Next step): NSC anlügen → Szene wechseln → zurück → erinnert er sich? Projekt-Prio davor unverändert: der Tuning+Scene-Cards-Live-Run.

**`uv run dm-sync` als Entry Point (2026-07-02, D90, Dev-Tooling — committet + gepusht auf `main`).** Das D89-Tool ist von `tools/sync_check.py` nach **`dmbot/tools/sync_check.py`** gezogen (Package-Modul, `sys.path`-Hack weg) und läuft jetzt als `uv run dm-sync` (`[project.scripts]`). Dafür ist das Projekt jetzt **packaged** (hatchling, editable install von `dmbot` — nur damit der Script-Entry existiert; weiterhin Anwendung, keine Library). Output byte-identisch zum D89-Format (Kontrakt), Doku-Zeiger (SETUP.md/conventions.md) + Tests umgebogen, kein Shim am alten Pfad. Suite 459 grün. **Timo braucht einmal `git pull` + `uv sync`**, bevor `dm-sync` bei ihm existiert. Nebenbefund: Tobis `.env` ist inzwischen **38/38** — der D89-Befund (20 fehlende Keys) ist abgearbeitet. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Sync-Check-Tool gebaut (2026-07-02, D89, Dev-Tooling — committet auf `main`).** Neues Standalone-`tools/sync_check.py`: ein kompakter `[sync]`-Fingerprint-Block (Repo-Commit, Abenteuer-Dateien sha+mtime+Kennzahl über den echten Loader, rag.db Größe/Embedder/Chunks-pro-Source/Ingest-Datum, .env-Key-Abgleich gegen `.env.example` ohne Werte, geänderte data-Seeds) — beide Maschinen lassen es laufen und diffen die Blöcke; die abweichende Zeile ist das, was zu schicken/neu zu bauen ist. `dmbot/rag/ingest.py` stempelt jetzt `ingested:<source>` in die Meta-Tabelle (alte DBs tolerant „unbekannt"). SETUP.md-Sektion „Staying in sync (second machine)". Suite 459 grün (+15). **Erster echter Befund:** Tobis lokale `.env` hängt 20 Keys hinter dem Template — vor dem Tuning-Live-Run nachziehen (s. Next step). Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run.

**Authoring-Skill `/author-adventure` gebaut + Smoke-Test bestanden (2026-07-02, D88, Dev-Tooling — committet auf `main`; nur der Skill selbst, keine Buch-Derivate).** Neuer Claude-Code-Skill (`.claude/skills/author-adventure/` = SKILL.md + `validate.py`, D78-Infrastruktur): 5-Pass-Workflow (Struktur-Pass **mit Stopp zur Szenenschnitt-Freigabe** → Karten → NSCs → Summary → Spoiler-Selbstcheck + Loader-Validierung + Review-Checkliste), damit Abenteuer #2 („The Blazing Seraph", 49 S.) einen Redigier-Nachmittag kostet statt Tage. Dry-Run gegen das Chemical-Burn-md → 14-Szenen-Draft, Loader-valide (inkl. ADR-043-Gates), dann Diff gegen das handgebaute Kompendium: 4 echte Konventions-Lücken gefunden und in den Skill zurückgebaut (Auftakt-Szene als `start_scene`; `leads_to` dramaturgisch-sparsam statt Orts-Mesh; Summary enthält die WAHRHEIT mit Geheim-Rahmung; Statblock für **jeden** `npcs_here`-Namen). Wegwerf-Draft gelöscht. Projekt-Prio unverändert: der Tuning+Scene-Cards-Live-Run (s. Next step).

**Stateful Scene Cards gebaut (2026-07-02, D87 → ADR 043). Suite 444 grün (+49), ruff sauber, committet + gepusht auf `main`.** Die Szenenkarte spiegelt jetzt den Weltzustand: Element-Flags (`<<ERLEDIGT id>>`-Marker mit Confirm-Button/`DM_FLAG_CONFIRM`, manuell `!erledigt`/`!offen`) verschieben erledigte Gelegenheiten nach „Bereits geschehen" und enthüllte Geheimnisse nach „Bekannt"; tote NSCs rendern `(tot)`; `leads_to` kann per `{"ziel","requires"}` gegatet werden (verborgen + abgelehnt bis freigeschaltet). Alles code-owned (`WorldState.scene_flags`, golden rule #3), Schema abwärtskompatibel (Chemical Burn unverändert). **Offen/live:** das Live-Test-Skript (siehe Next step) — hängt sich an den ohnehin offenen Spielbarkeits-Live-Run. Davor/danach unverändert offen: der Tuning-Live-Run unten.

**Spielbarkeits-Tuning-Runde (2026-06-18, D85+D86 → ADR 042 + ADR 041 Addendum 2). Suite 395 grün (+16), Commit `e961b75` auf `main`, live-unverified.** Bootstrap (Phase 10 Hälfte 2) **zurückgestellt** auf Tobis Ansage „das Modell läuft noch nicht so richtig, dass man wirklich spielen kann" — Fokus ist jetzt Spielbarkeit, Modell bleibt nemo („am Drumherum drehen"). Drei Fronten: **Antwortqualität** → `repeat_penalty`/`repeat_last_n` als OllamaClient-Instanz-Defaults (1.1/256, `DM_REPEAT_PENALTY`/`DM_REPEAT_LAST_N`, live-tunebar), reiten auf jedem Call; der **Roll-Router** neutralisiert sie explizit (1.0) → Würfel-Routing bleibt deterministisch (ADR 042, vom adversarialen Verify gefunden). **!intro** → pures `intro_guard.is_weak_intro` (zu kurz **oder** Figur ungenannt, Genitiv-`s`-tolerant) + Einmal-Retry in `respond_opening` (Batch-Pfad), nur die bessere Antwort in die History (ADR 041 Add. 2). **Tempo** → GPU-Offload (Workstream A) ist Tobis **Live-Schritt**: lokale `.env` `OLLAMA_HOST` auf die Offload-Box + `TTS_DEVICE=cuda` (XTTS frei → ~3× schneller, Lücken weg); `.env.example` dokumentiert das bereits als Soll. **Offen/live:** der eine geplante Live-Run (s. Next step) — verifiziert Tempo (first_audio/tts fallen), Intro-Qualität, weniger Wiederholung, und nebenbei Phase-10-Gate-Hälfte 1 (Regelfrage aus RAG). _(Hinweis: die älteren „Current focus"-Blöcke unten [D75–D81] sind Vorsessions-Verlauf — eigener Archiv-Aufräum-Pass weiterhin offen.)_

**Playtest-Fix-Runde (2026-06-16): drei Fixes aus Tobis Live-Sessions auf `main` (`e36bad7`), live-unverified.** Default-Party lädt jetzt **channel-unabhängig** (committete `data/sessions/_default/characters.json`, vor `_example` geladen — D82 → ADR 040), also Fridolin & Co. in jedem Voice-Channel + beim Kollegen. `!intro` gegen **Modell-Varianz** gehärtet: feste, niedrigere `!intro`-Temperatur (`DM_INTRO_TEMPERATURE`) + Director-Brief (D83), und der Meta-Auftakt („Als Spielleitung beginne ich…") + `"…"`-Umschlag **deterministisch** im Sanitizer gestrippt + Default-Temp auf **0.7** (D84 → ADR 041 + Addendum). Suite **379 grün**. **Offen/live:** klingt `!intro` jetzt zuverlässig wie der gelobte 14.06.-Lauf? Kollege testet `e36bad7`; ggf. `DM_INTRO_TEMPERATURE` Richtung 0.8 oder Brief-Wortlaut. Projekt sonst: Phase-9/10-Live-Gates (siehe Phasen-Status). _(Hinweis: die älteren „Current focus"-Blöcke unten [D75–D81] sind Vorsessions-Verlauf — gehören eigentlich ins Archiv; eigener Aufräum-Pass offen.)_

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

## Last session
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

_Ältere `## Last session`-Einträge (D89 Sync-Check-Fingerprint-Tool [`[sync]`-Block, Ingest-Stempel, SETUP.md-Sync-Sektion], D88 `/author-adventure`-Authoring-Skill [5-Pass-Workflow + `validate.py`, Dry-Run-Abnahme gegen Chemical Burn], D87 Stateful Scene Cards [`<<ERLEDIGT>>`-Flags, tote NSCs, gated Exits → ADR 043], D85+D86 Spielbarkeits-Tuning [repeat_penalty + Roll-Router-Carve-out, `intro_guard`-Retry], D84 `!intro`-Meta-Auftakt-Strip + Temp 0.7, D83 `!intro`-Temperatur + Direktive, D82 Default-Party-Fix, D81 Scene-/Lore-Sub-Cogs, D80 Deepening #4–#6 [prompt_assembly/seed_session/clear_panel], D79 Deepening #1+#2 [`combat.py`-Auslagerung + `segments.py`-Verdrahtung], D78 Skill-Tooling-Runde [4 Claude-Code-Skills: /tdd, /grill-me, /improve-architecture, /to-prd], D77 Dev-Gates [Lint-Stop-Hook + blockierender git-pre-commit + Review/Simplify-Checkliste], D76 `disconnect_voice`-Kontrakt + neuer Delivery-Test, D75 One-Shot-Setup, D74
Delivery-Pipeline-Auslagerung, D73 `_TurnTiming`-Auslagerung, D70–D72 `orchestrator`-E1–E4-Verschlankung, D69 `puffer`-Modus,
D68 globaler Sprech-Modus, D67 Shutdown-Leave-Limit u. a.): siehe **[docs/progress-archive.md](docs/progress-archive.md)**._

## Next concrete step
> **Drehbuch für den Live-Run:** alle offenen Gates unten sind als abhakbare Checkliste in
> **[docs/live-test-checklist.md](docs/live-test-checklist.md)** ausformuliert (Session-Reihenfolge:
> Vorbereitung → Tempo → Intro → Gespräch → Würfel → Scene Cards → **NPC-Gedächtnis** → RAG →
> Neustart-Gate → Nachbereitung). Nach dem Run: Ergebnisse hierher zurückschreiben, Liste ausmisten.

**0. Vorab (D89 ✅ / D90):** Die 20 fehlenden `.env`-Keys sind nachgezogen (`dm-sync` meldet 38/38, 2026-07-02). Vor dem nächsten Timo-Sync auf beiden Maschinen `uv run dm-sync` (Timo vorher einmal `git pull` + `uv sync`), Blöcke diffen (SETUP.md §„Staying in sync").

**1. Der EINE Live-Run der Spielbarkeits-Tuning-Runde (Top-Prio, Tobi nächste Session — pullt `f44cba8` + Neustart).** Zwei Teile in einem Run:
- **Workstream A (Tempo/GPU-Offload) zuerst, reine `.env`:** `OLLAMA_HOST` auf die Offload-Box + `TTS_DEVICE=cuda` setzen → `nvidia-smi` (kein OOM, XTTS-cuda + Whisper passen auf die freie 4070) → `[latency]`-Zeile vorher/nachher (`first_audio`/`tts` fallen klar, Sprech-Lücken weg). Wenn schnell genug: Default-Lieferart Richtung `nahtlos` live abwägen; dann **ADR-002-Addendum + `architecture.md` §3** nachziehen.
- **Dann `!intro test` + ein paar Spieler-Turns + eine Regelfrage:** Intro zuverlässig **ein** Monolog mit **jeder Figur** (C1-Retry greift bei zu kurz/Figur fehlt, D86), **weniger Wiederholung/Generik** (B1 repeat_penalty, D85). Tuning live: `DM_REPEAT_PENALTY` (1.0 = aus, höher = strenger), `DM_INTRO_TEMPERATURE` (0.8 mehr Flair / 0.3 ruhiger). Schließt nebenbei **Phase-10-Gate-Hälfte 1** (Regelfrage aus RAG) + die offenen D82–D84-Intro-Punkte ab.
- **Neu dazu (D91, im selben Run abprüfbar) — das NPC-Gedächtnis-Gate:** eine Szene spielen und einem NSC etwas Markantes erzählen (ideal: ihn **anlügen**, z. B. eine falsche Identität behaupten) → Szene wechseln (`!ort` oder bestätigter `<<ORT>>`-Button; Konsole zeigt `🧠 NPC-Gedächtnis: N neue Erinnerungen`) → `!npcmem <Name>` zeigt den Eintrag (Lüge mit Zitat, `believed` noch true) → **zurückkommen** und prüfen, ob der DM sich im Dialog erinnert (der `[NPC-Gedächtnis: …]`-Block reitet im Prompt). Kür: die Lüge im Spiel auffliegen lassen → nächster Szenenwechsel → `!npcmem` zeigt „LÜGE aufgeflogen" + Wichtigkeit-5-Eintrag, Haltung eine Stufe Richtung hostile. Feature ist **live-unverified** bis dahin; Fehlverhalten (Small Talk als Wichtigkeit 5, erfundene Erinnerungen) → `prompts/npc_memory_extract_de.md` nachschärfen oder `DM_NPC_MEMORY=0`.
- **Neu dazu (D87, im selben Run abprüfbar):** Stateful-Scene-Cards-Live-Skript — (a) `!ort` zeigt die Element-IDs (⬜); (b) eine Gelegenheit im Spiel abschließen → `<<ERLEDIGT>>`-Button erscheint, Antwort enthält kein `<<`, nach „Abhaken" zeigt `!ort` ✅ und der nächste Prompt-Dump „Bereits geschehen:"; (c) `!offen`/`!erledigt` togglen ohne Button; (d) einen `leads_to`-Eintrag testweise auf `{"ziel": …, "requires": "opp-1"}` setzen → Ziel fehlt in „Mögliche nächste Orte", Auto-`<<ORT>>` dorthin wird abgelehnt (🚫-Konsolen-Zeile nennt `opp-1`, nichts im Channel), nach `!erledigt opp-1` geht's; (e) NSC auf 0 Wunden → Karte rendert `(tot)`, übersteht Neustart. (Stand ist committet + gepusht — nur pullen + Neustart.)
- Danach: Log pasten → Playtest-Triage-Iteration. **Bootstrap bleibt zurückgestellt**, bis das Spielen rund läuft.
- **Parat, wenn Abenteuer #2 dran ist (D88):** `/author-adventure <md> <id>` — erst „The Blazing Seraph" per `/rag-ingest`-Konverter nach `data/pdfs/md/`, dann der Skill (stoppt zur Szenenschnitt-Freigabe). Drafts landen im untracked `data/adventures/<id>/` — Buch-Derivate bleiben lokal, nur der Skill ist committet.

**2. Die offenen Phase-9/10-Live-Gates abhaken (Code ist da, nur Live-Abnahme fehlt):**
- **Phase 9:** eine HP-Änderung übersteht einen echten Neustart + der Recap erscheint beim nächsten `!join` (in-prompt).
- **Phase 10:** eine konkrete **Regelfrage** wird korrekt aus dem Regelbuch-RAG beantwortet. Danach das **einzige noch zu bauende** Feature: **Profil-Bootstrap (§9)** — der DM schlägt aus dem Regelbuch ein System-Profil vor → Tobi bestätigt → speichern.

_(Die älteren „Next concrete step"-Einträge unten [D61–D74] sind erledigter Verlauf — Aufräum-Pass offen, wie beim Current-focus-Hinweis.)_

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

---

## Decision log

**This log is the index to the ADRs.** Each row with a real trade-off links its decision to
a full ADR under `docs/decisions/` (the `→ ADR NNN` at the end of the rationale). The
session-start read covers only the *newest* ADR for recency; the **older ADRs are read on
demand** — when you start a phase or touch a subsystem, follow the `→ ADR` links of the
decisions that govern it (see the phase → ADR map below). A new non-trivial decision →
create the next-numbered ADR.

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Ruleset approach | **System-agnostic** — generic engine + per-system profile; **Imperium Maledictum is the first** profile (1d100 roll-under, SL) | Reusable DM, not a 40k one-off; IM only the first loaded system → ADR 005 |
| D2 | Mechanic depth v1 | Voice narration **+ dice & turn buttons** in the text channel | Playable without the bot having to manage all the rules |
| D3 | Memory | **JSON world state + session recaps** | JSON = hard facts, recap = narrative thread; together coherent without context overflow |
| D4 | Knowledge source | **RAG over rulebook & story PDFs** (NOT character sheets) | Rule knowledge ingestible; reduces rule hallucination. Sheets → JSON (D12) |
| D5 | Bot language | **Python (discord.py)** for both bots | Music bot is discord.py; the voice-recv ecosystem is Python |
| D6 | LLM host | **Dev: everything local on Tobi's 4070** (Nemo 12B); later optionally only Ollama on the 5080 via Tailscale | Develop/debug locally; separate networks are a non-issue for the MVP; upgrade = one `OLLAMA_HOST` switch → ADR 002 |
| D7 | Language/tone | **German play language**; generic GM persona + **per-campaign tone overlay** (first: Eisenhorn / Dan Abnett grimdark) | Tone is campaign-specific, not the DM's fixed identity → ADR 005 |
| D8 | Player count | 2–5, semi-turn-based | — |
| D9 | Output bot | **Reuse the music bot** + `/speak` bridge | Already in the voice channel, can play audio |
| D10 | Conversational control | **Transcribe continuously + buffer, DM turn triggered by button**; VAD only for segmentation. Wake word is a later goal | DM doesn't talk over anyone, no table talk in the game, semi-turn-based → ADR 003 |
| D11 | Dice test trigger | **LLM emits a test marker** (`<<TEST …>>`), code rolls; manual button fallback | Loop mostly automatic but robust against parse errors → ADR 004 |
| D12 | Character data | **Lean structured JSON**; the stat/skill/resource shape follows the **active system profile**; sheets transferred once, NOT RAG | Enables stat-aware rolls + resource tracking per system; Phases 8/9 one piece → ADR 004 + 005 |
| D13 | Registration | **Guided & sequential** — bot asks character by character, a click maps user-ID → character | Bot must know who plays whom (addressing + rolls) → ADR 003 |
| D14 | Recap trigger | **`wrap up` command** ends the session & generates the recap; rolling mid-summary later | Clear trigger; 128k context has headroom |
| D15 | Bot A signal | **`/speak` blocks until playback ends** | Return moment = resume signal; no status/shared state needed. _Confirmed in implementation (commit `249cc38`); a redundant callback was removed._ |
| D16 | Runtime environment | **Windows** (both bots + pipeline) | No `/tmp` (OS temp dir); Opus DLL for voice; cuDNN/cuBLAS DLLs on `PATH` for faster-whisper. _WSL considered but rejected — keeps both bots co-located so the file-path bridge works without path translation. Co-location is no longer mandatory: the bridge now also runs split across machines via bytes-over-Tailscale (D23 / ADR 010)._ |
| D17 | Doc language | **Dev docs in English** (game content stays German) | Token efficiency on docs read every session; matches the schema precedent |
| D18 | System-agnostic engine | **Generic dice/resolution engine + per-system profile**; DM **proposes the profile from the PDF**, user confirms (MVP). Persona = generic GM + per-campaign tone overlay | Reusable across rulesets; "paste PDFs → DM knows what's played"; dice still code → ADR 005 |
| D19 | DAVE/E2EE on voice receive | **Decrypt the DAVE layer via discord.py's `dave_session`** (keep E2EE; sink takes `wants_opus=True`, decrypts each frame before Opus-decode) | Discord calls are end-to-end encrypted; voice-recv only undoes transport → garbage. Declining DAVE is rejected (voice close 4017) → ADR 006 |
| D20 | VAD segmentation stack | **silero-vad via `onnxruntime`** (no torch) + **`soxr`** streaming resampler; model vendored in-repo | Robust neural VAD without torch's ~GB weight; webrtcvad too noise-prone; soxr is the smallest correct resampler → ADR 007 |
| D21 | TTS engine | **XTTS v2 (`coqui-tts`) default + Piper fallback**, selectable via `TTS_ENGINE`; XTTS speaker **Dionisio Schuyler**. _(Default flipped Piper→XTTS 2026-06-05 once XTTS ran on GPU.)_ | Piper's German voices were rejected; XTTS gives 58 voices + cloning (local, no cloud); torch is a hard dep regardless + XTTS degrades to CPU, so it's a safe default → ADR 008 + 009 |
| D22 | GPU XTTS / portability | **CUDA torch from the `cu130` index** (`+cu130` builds; CUDA 13.0 covers Ada **and** Blackwell), device env-driven (`TTS_DEVICE`/`WHISPER_DEVICE`); same Windows-only lock for both boxes, XTTS auto-degrades to CPU | CPU-only torch made GPU XTTS impossible; cu130 gives the GPU build (RTF 0.34 verified) for both 4070 (sm_89) + 5080 (sm_120); win32-only lock dodges the cudnn pin clash; one repo runs 4070 dev + 5080 full-GPU → ADR 009 |
| D23 | Bridge transport | **Hybrid `/speak`**: loopback → WAV path (unchanged); remote → WAV bytes + shared secret over Tailscale; Bot A plays its own copy | Lets DMbot + Bot A run on different machines without breaking the proven localhost path; partially relaxes D16/ADR 002 co-location for the bridge → ADR 010 |
| D24 | STT latency | **GPU whisper** (`WHISPER_DEVICE=cuda`) **+ push-to-talk DM-routing gate** (shared Discord mic button; whole table always transcribed + logged, button gates only what reaches the DM, `DM_PUSH_TO_TALK=1`) | CPU whisper fell ~1.5 min behind; GPU + routing only the button-window speech to the DM keeps the full transcript record (Tobi's call) while cutting DM noise. Supersedes the 4070 "whisper on CPU" profile → ADR 011 |
| D25 | Feedback layer 2 | **Pausing the VAD while Bot A speaks is now opt-in, off by default** (`DM_PAUSE_VAD_WHILE_SPEAKING=0`). Layer 1 (Bot-A user-ID filter) stays mandatory | Layer 1 already stops self-transcription and the push-to-talk routing gate keeps narration table talk out of the DM, so layer 2 was redundant and blocked transcription during the DM's narration — players wanted the table kept in the record. golden rule #4 (layer 1) unchanged; updates `architecture.md` §5 |
| D26 | Phase-8 dice flow | **Difficulty is a ladder *word*, resolved to a number in code** (`<<TEST Wahrnehmung Schwer für Tobi>>` → profile maps *Schwer* → −20; `±N` only as manual override). **Minimal character JSON + alias map pulled into Phase 8** (GM rolls *for* the player; alias map also fixes F). **Turn order seeded from the voice channel.** | Honours "dice = code" / open item K (the number lives in the profile/character data, not the LLM); the lean party JSON is cheap and is the heart of K; the alias map quietly fixes F; the voice channel is a zero-setup turn-order source (full registration, ADR 003, stays deferred) → ADR 012 |
| D27 | Pause control | **One shared `_paused` freeze, driven by the terminal Esc key (Variante A, animated `rich` box) AND a Discord ⏸ button (Variante C, status embed).** Pause mutes the VAD/STT pipeline + blocks all DM turns; resume reverses it | Tobi wanted both controls + a visible state, and a real freeze (not "keep transcribing"); reuses the layer-2 `mute()/unmute()`; new light dep `rich`; first half of the "Edit/Review window" backlog (same human-in-the-loop gate) → ADR 013 |
| D28 | Lore representation (Phase 10) | **RAG, not fine-tuning, for facts.** 40k lore from **both** wiki sources (Fandom official XML dump + Lexicanum via MediaWiki API / archive.org), **text only**, chunked + `nomic-embed-text` → **`sqlite-vec`** with rulebook vs lore as separate `source`s. Fine-tuning only later as a **tone-LoRA** (style, not facts) | Fine-tuning hallucinates facts, can't cite, needs retraining to update + a wiki doesn't fit in 12B weights/context; RAG is grounded/citeable/updatable (golden rule #7). Both wikis ≈ 0.8–1.3 GB (images excluded). Plan saved; → a new ADR when Phase 10 starts |
| D29 | Auto-test trigger | **Roll-detection router** — a separate, stateless **constrained-JSON classifier** picks the test (skill + difficulty, skill enum = the character's sheet) **after** narration, instead of the model's inline `<<TEST>>` (kept as fallback). **ON by default** (`DM_ROLL_ROUTER`, validated live 2026-06-08; `=0` disables) | The inline marker failed live (only 2 good markers/session; the model self-resolves uncertain actions) — a **documented, model-size-independent** LLM-GM failure, not a 12B limit (web + an experiment: the same nemo scored **8/8** as a separate step). Costs +1 short stateless call/turn, doesn't bloat the DM context. Revisits ADR 004 → ADR 014 |
| D30 | Ollama readiness | **`start_dmbot.bat` warms a *local* Ollama before launch** (boots the daemon + loads the model; skipped for a remote `OLLAMA_HOST`) + a **boot preflight** (`llm/preflight.py`) pings the host / checks the model is pulled | A not-running Ollama failed turns mid-game with a cryptic `ConnectError`; warm-up + a clear boot message turn that into a startup-time signal. Ops polish, no ADR |
| D31 | Shutdown UX | **Two-stage Ctrl+C** — first press prints "Quit?" and keeps running, the second an animated "Shutting down …" then tears down cleanly | Avoids killing a live session on a single fat-fingered Ctrl+C; discord.py 2.7.1 installs no SIGINT handler so ours stays in effect. Ops polish, no ADR |
| D32 | Memory state file | **Split** — `characters.json` stays the read-only sheet (transferred once), a new code-owned `data/sessions/<id>/state.json` holds the mutable layer (wounds/conditions/inventory, NPCs, quests, location, recap), seeded once from the sheet, saved atomically on every change | Keeps the hand-authored source pristine/diffable, gives a clean reset (delete state.json) and a clean gate (save-on-change → HP survives a restart); avoids code corrupting the sheets. Rejected: one blob that code rewrites → ADR 015 |
| D33 | Combat damage | **Auto-applied on a hit** — a successful attack (skill ∈ profile `combat.attack_skills`) rolls weapon damage, applies **weapon + SL − soak** (TB + armour) to a target (auto if one, else a dropdown; `!npc add` registers enemies; `!damage`/`!heal` GM overrides) | Tobi chose auto-combat over a manual command; realises the dice engine's damage in play (the natural Phase-8→9 hook). Profile-driven (`combat` block) so it stays system-agnostic; weapon values approximate, tune live → ADR 015 |
| D34 | Log verbosity | **Trim the logger name** — drop it entirely on INFO console/mirror lines, strip the `dmbot.` prefix on WARNING/ERROR + in `debug.log`; third-party names kept | Tobi pastes logs for the playtest-tuning loop; the repeated `dmbot.voice.commands` prefix wasted tokens while the message (often emoji-prefixed) already carries the context. Levels/colour/tracebacks unchanged. Ops polish, no ADR |
| D35 | Latency instrumentation | **One `[latency]` log line per DM turn** — a `_TurnTiming` record (monotonic) threaded through the existing turn flow: stt (reused `transcribe_ms`) · trigger→llm_done (+ broken-out autosend `wait=`) · tts · bridge_wait · total, plus `chars`/`wav` and Ollama `ctx=<prompt>/<num_ctx> gen=<eval>`. Emitted once in `_deliver_answer` (all four triggers; not `!say`). `OllamaClient.last_stats` keeps the previously-discarded token counts without changing `chat()`'s return type | Need a baseline of where a turn's seconds go *before* the streaming optimisation; reuses existing measurements + surfaces for free whether the growing prompt is nearing `num_ctx`. Logging only, zero behaviour change, no trade-off → no ADR |
| D36 | Context-budget warning | **WARNING when a narration prompt exceeds ~85% of `num_ctx`** (`[ctx] prompt N/8192 …`), beside the per-turn `ctx=` display; pure `_TurnTiming.ctx_over_budget()` predicate, narration turns only (router/recap exempt) | The persona leads the system prompt, so Ollama truncates **it** first when prompt+history overflow — a silent quality cliff. 85% gives a turn or two to trim history/recap/state before the cap (raising `num_ctx` costs KV-cache VRAM we don't have on the 4070). Logging only, no trade-off → no ADR |
| D37 | Anti-puppeting + length | **Deterministic speaker-label backstop** — every character + player name (`CharacterStore.speaker_labels` → `DMBrain.set_known_speakers`, on join) becomes a `_cut_at_labels` cut-point + Ollama stop sequence, so an appended `Seskin:`/`Pr0degie:` puppet script is truncated even when those names didn't speak this turn; **plus** positive top-of-persona scoping + the alias hint reframed into a hard "PCs belong to the players" boundary placed **last**; **plus** `num_predict` 220→160 | The persona forbade puppeting and nemo ignored it across 3 live sessions; `[latency]` (D35) showed the puppeting **is** the latency (scripted 700+-char turns → 55–80 s of audio → `total` up to 183 s). A code-level guard the model can't ignore, mirroring ADR 014's "don't trust the model" stance; rejected a fuller PC-dialogue stripper (false-positive risk) → ADR 016 |
| D38 | TTS speech-only normalization | **`normalize_for_tts()`** (XTTS + Piper synth, **not** the Discord post) drops quotes/brackets/stray symbols + maps the ellipsis and em/en dashes to a pause, while **keeping** `. , ! ? ; :` + word hyphens | Players: *"er liest die Interpunktion mit vor"*; the TTS path had no normalization (quotes/ellipses went raw to XTTS, which verbalises them). Keep the prosody-bearing punctuation (the intonation they want), strip only what XTTS reads aloud; also fixed XTTS's single-chunk branch synthesising the raw text → ADR 016 |
| D39 | Streaming pipeline | **Stream the DM turn** — `chat_stream()` deltas → a pure `StreamAssembler` cuts complete sentences (first-chunk hold for the leading meta-preamble; hold back the latest sentence for the trailing strips; withhold from an unmatched `<<` / mid-text speaker label) → the cog synthesises + plays each sentence over the blocking `/speak` (synth N+1 while N plays). History parity by construction: one `finalize_answer()` shared by both paths; `finish()` recomputes it on the accumulated raw. `DM_STREAMING=1` default; `0` = byte-identical batch path | Time-to-first-audio was full generation + full synthesis of silence (D35 `[latency]`); the blocking `/speak` (D15) is already the queue, so shrink the unit to one WAV per sentence and pipeline. Rejected: streaming TTS (heavier, Part 2) + progressive Discord edits (rate limits); recompute-at-finish beats an incremental emitter because the global self-correction frame can retroactively drop spoken text → ADR 017 |
| D40 | Roll-router timing | **Fire the ADR-014 classifier at generation-end and post the 🎲 button concurrently with playback** (`_handle_dice` runs as a task beside `_speak`/the streaming playback), so the button appears while the DM still speaks. Inline `<<TEST>>` still wins the dedupe (`should_post_router`) | The button used to appear only after generation **and** playback. Input (action + skills) is known earlier, but single-GPU Ollama serialises — firing at turn-start would just queue the classifier behind the narration (or delay it), so gen-end is the earliest point that overlaps playback without delaying narration. Supersedes ADR 014's *timing* only, not its design → D-entry, no new ADR |
| D41 | History autosave | **Third session artifact** `data/sessions/<id>/history.jsonl` (`dmbot/memory/history.py`) — append-only, one line per turn (`{ts, user_msg, answer, redo}`), appended off-loop after each turn, restored into an empty `DMBrain` history on `!join`, rotated to `history.<ts>.jsonl` on `!leave`. `DM_AUTOSAVE=1` | World state already persists (ADR 015); a crash still lost the conversational thread. Code-owned like `state.json` (the read-only `characters.json` split is unchanged). Append-only (no atomic dance; torn tail tolerated); a `redo` record replaces the prior turn. `_last_turn` not restored → `!redo` unavailable for the restored last turn (documented). Extends ADR 015's artifact set → D-entry, no new ADR |
| D42 | Streaming content tuning (first live run) | **(a)** skip TTS+post of a **content-less** answer (`has_speakable_content`: no letter/digit) — a marker-only / code-fenced turn no longer makes XTTS read a lone quote for ~15 s; the dice button still posts. **(b)** `_sanitize` strips **code-fence backticks** (`` ` ``) like markdown `*`. **(c)** suppress inline `<<TEST>>` markers on **results-only turns** (`_last_action is None`) so a post-roll consequence narration can't request a new roll | First live streaming run: the model emitted marker-only turns (15 s of lone-quote audio each) and a `<<TEST>>` on every turn incl. consequence narrations → an endless attack→roll→narrate+marker→roll **dice loop**. (a)/(b) are output cleanup (ADR 016 family); (c) is the real flow decision — a consequence narration legitimately *never* needs a fresh roll; the router handles real player-action rolls on the next turn. Builds on ADR 014/D40 + ADR 016/017 → D-entry, no new ADR |
| D43 | Post-roll robustness (echo collapse, 2026-06-12) | **(a) Echo guard** — pure `is_echo()` flags an answer that parrots a player line (normalized exact/fragment/≥90%-coverage); retry once with a corrective nudge, then **suppress the turn** (nothing spoken, the pair stays out of history); `restore_history` skips empty answers. **(b) Roll-feedback directive** — a results-only `[Würfel]` turn appends "Beschreibe als Spielleitung kurz die Folgen …". **(c) Router wins the dedupe** (flips D40's marker-wins; `roll_button_source` replaces `should_post_router`) — inline markers stripped but discarded when the router is on. **(d) Autosave race fix** — the cog snapshots `user_msg` at generation end and passes it to `_autosave_turn` (a dice click during playback overwrites `_last_turn`). **(e) ADR 016 partial rollback** — `num_predict` 160→220, persona "zwei bis vier Sätze". Plus: `!join` names the party + warns loudly on the `_example` fallback; `chat_stream` read timeout 120→300 s | The 2026-06-12 session collapsed: a nonsense marker roll (Heimlichkeit for an attack — the unreliable marker won the dedupe over the validated router) + a bare `[Würfel]` feedback line made nemo predict the *next player line*; the label-strip turned it into a clean-looking echo that was spoken, stored, and self-reinforced ("Ich greife den Kultisten an." three turns straight). Deterministic guards over persona hopes (the ADR 016 lesson); the brevity squeeze predates streaming and the praised sessions ran at 220 → ADR 018 |
| D44 | Adventure into the DM (Phase 10a) | **3-stage hybrid** instead of pure vector RAG: (1) a ~300-token German **adventure summary** always in the prompt; (2) a deterministic **scene tracker** — the adventure hand-authored once into German scene cards (`data/adventures/<id>/adventure.json` + `npcs.json` statblocks; local-only, not in git — derivative of a bought book in a public repo), pointer = `WorldState.scene_id`, moved by humans via `!ort`/`!szenen`, never by the model; `!npc add` resolves compendium statblocks; (3) **rulebook-only RAG** — heading-aware chunks → Ollama embed → `sqlite-vec`, threshold-gated `## Regelwerk` block per turn (offline CLI `python -m dmbot.rag.ingest`). The adventure is deliberately NOT in the vector store | Similarity search can't answer "wo sind wir im Plot" (the loudest player critique: the DM improvised from nothing) and surfaces part-3 spoilers in part 1; plot position must be code state (golden rule #3). Matches Timo's independently-formed architecture (prepared docs + state outside the narrator). First compendium: **Chemical Burn** (15 scenes, 24 statblocks). `DM_ADVENTURE` env; profile bootstrap (gate half 2) stays open → ADR 019 |
| D45 | Embedder + W4 guard | **(a)** RAG embedder = **`bge-m3`** (multilingual), replacing D28's `nomic-embed-text` for the store; the store's meta table pins model+dim so retrieval always matches. **(b)** Echo guard extended by **`is_self_repetition`** (SequenceMatcher ≥0.75 on normalized text, <60 chars exempt): retry with a "beantworte die Frage direkt"-nudge, then suppress; streamed long repetitions only logged (audio can't be retracted) | (a) Verified against real questions: German queries barely matched the English rulebook with nomic ("kritischer Erfolg" → miss/wrong hit); bge-m3 hits DIFFICULTY/CRITICAL HIT while table talk stays under the 0.45 threshold. (b) W4 from the wishlist, seen live 2026-06-12: "Warum sind wir hier?" → near-verbatim re-description with pronoun swaps — substring checks miss that, fuzzy ratio catches it → ADR 019 (extends ADR 018) |
| D46 | Starter Set as lore + patron source | **(a)** The Starter Set's **Setting Guide → `source=setting`** in the existing RAG store (pages 1–57 only — the „Villains on Voll" chapter with the Mireclaw reveal stays out until the campaign finale); retrieval searches rulebook+setting and groups hits as `## Regelwerk` / `## Weltwissen (… nur als Färbung nutzen)`, TOP_K=3 total. **(b)** The **Aegidius-Halikarn patron sheet** folded into the chemical_burn compendium (Motivation Information, Auftreten undurchschaubar, Boons incl. Sanctum-Obscurus-Ausstattung in der Thaler-Szene). „The Blazing Seraph" (SS adventure book) wird erst NACH dem Chemical-Burn-Live-Test zum zweiten Kompendium | The Setting Guide is a better first lore source than D28's wiki plan: campaign-specific (Chemical Burn plays in Rokarth), curated, already owned — wikis stay the later broad-lore step. Spoiler discipline (ADR 019) applies to lore too: similarity must not surface the villain chapter on „wer steckt dahinter?" (verified: the question returns nothing). Applies ADR 019, no new trade-off → D-entry, no new ADR |
| D47 | Visible, fast shutdown | **(a)** TTS synth runs on an **abandonable daemon thread** (`dmbot/shutdown.py` `to_daemon_thread`, replacing `asyncio.to_thread` in `_speak` + the streaming `synth_worker`) so a synth in flight at Ctrl+C is dropped, never join-blocking exit. **(b)** A thread-safe **`[i/n] label` step display** (`ShutdownProgress`/`progress`): `DMBot.close()` declares the count up front (voice disconnects + each cog's `TEARDOWN_STEPS` + the Discord close) and wraps every stage; `cog_unload` reports its four closes; a final summary names any dropped synth. Outside a shutdown, `step()` is a plain log line | Tobi: the bot quit slowly and silently. Cause of the slowness: asyncio's default executor threads are **non-daemon**, so the interpreter joined a multi-second GPU XTTS synth at exit — pure dead wait, the WAV is moot once quitting. Daemon-abandon is the only real lever (XTTS isn't cancelable). The display answers "what/how many is being shut down". Targeted to TTS only (close paths keep normal threads) → **ADR 020** |
| D48 | Curated German lore compendium | **Hand-authored `data/lore/imperium.md` + `chaos.md`** (German, grimdark in-world; **committed** — own wording of freely available 40k common knowledge, revised same day from the initial local-only stance) → two new RAG sources **`lore_imperium`/`lore_chaos`**, grouped as `## Weltwissen (Imperium …)` / `## Weltwissen (Chaos — verbotenes Wissen …)`, block order rules → broad lore → local Rokarth. Threshold stays 0.45 global. Tobi's calls: two files/two sources, both ausführlich, grimdark | Live probe (2026-06-13): human lore retrieves from the English rulebook (Imperium d=0.27) but **Chaos cosmology doesn't exist in the IM books** ("vier Chaosgötter" d=0.53 miss — by design, Chaos as hidden horror); RAG can't retrieve what was never written, and German-vs-English inflates distances. German authored text wins TOP_K for German lore questions (verified 0.28–0.44) while rules keep hitting the rulebook. Wiki dump (D28) stays the later breadth step; Tyranids/Necrons/T'au deliberately absent (Tobi) → **ADR 021** |
| D50 | `!rules <frage>` command | **Two modes** — `!rules` (alias `!regeln`) still pages the system's short rules (◀/▶); **`!rules <frage>`** retrieves the matching rulebook chunks (`RulebookRetriever.lookup(sources=("rulebook",), k=3, max_distance=0.55)`) and the new **`DMBrain.answer_rules`** has the LLM synthesise a short German answer grounded **only** in those excerpts (golden rule #7: no invented rules; "Regelbuch hergibt nichts" when uncovered). No hits → honest "nichts im Regelbuch". Read-only embed, never spoken; +3 unit tests | Counterpart to D49's `!lore <frage>`, but the rulebook is **English layout-soup**, so raw chunk display (the `!lore` model) is unreadable — a rule question needs an LLM translate/condense step, unlike curated German lore. Grounding it in retrieved chunks (not the model's gut) is golden rule #7 applied, not a new trade-off → D-entry, no ADR. Verified end-to-end against the live store (Ausweichen, kritischer Treffer → correct) |
| D53 | TTS-Normalisierung gehärtet (Whitelist + Pro-Chunk-Guard) | **`normalize_for_tts` von Blocklist auf Whitelist** (`dmbot/tts/textsplit.py`): NFKC, Strich-/Minus-Varianten + `…` → Pause, dann nur Buchstaben/Ziffern/Whitespace + `. , ! ? ; : -` behalten — Emojis (🎲🌀🜏💥), Pfeile/Bullets/`·`, exotische Leerzeichen fallen generisch raus (darf jetzt `""` liefern). Plus **Pro-Chunk-Sprechbarkeits-Guard**: `chunk_text` verwirft nicht-sprechbare Chunks; XTTS/Piper `synthesize` geben kurze Stille statt einen reinen Satzzeichen-Chunk an die Engine. +6 Tests (233 grün). Härtet ADR 016 #3 | Live-Klage: „beim Vorlesen Kauderwelsch, vor allem bei Satzzeichen — taucht im Transkript nicht auf". Aktive Engine XTTS (`.env TTS_ENGINE=xtts`) vokalisierte durchgerutschte Unicode-Symbole; Blocklist fing sie nicht, und leere/nur-Satzzeichen-Chunks erreichten die Synthese ungefiltert (XTTS las einen einzelnen Punkt ~15 s / halluzinierte). Whitelist = zukunftssicher; XTTS-Param-Tuning (repetition_penalty) zurückgestellt → Nachtrag in **ADR 016** |
| D52 | Augmetik/Implantate + Psyker-Erstellungs-Backfill | **Profile-driven, passiv (kein Wurf).** Neuer optionaler `augmetics`-Block im IM-Profil (Katalog mit Körperzone/Verfügbarkeit/Kosten/`effects` + weiches Limit = Zähigkeits-Bonus). `Character.augmetics`. Engine wendet `armour` (→ PC-Soak in `_apply_attack_damage`) und `characteristic` (→ `resolve_target`, via Merkmalsname oder optionale `skills`-Liste am Effekt) deterministisch an; `skill_sl`/`special` narrativ (Prompt-Block `_augmetic_block` + RAG). Backfill derselben Erstellungs-Dateien, die Psyker noch nicht kannten: HTML-Creator (Augmetik-Checkliste + Psioniker-Sektion → JSON-Felder) und `fill_character_sheet.py` (leere Psi-Tabelle aus `known_powers`×Katalog + Warp-Schwelle füllen; Augmetik in Ausrüstungsspalte). +10 Tests (230 grün) | Tobi: Implantate „auch nachziehen" + in die nötigen Dateien integrieren. Engine bleibt system-agnostisch (ADR 005) → Katalog ist Profildaten. Effekte, die die Würfel betreffen, gehören in Code (golden rule #2): Rüstung/Merkmal auto, der konditionale Rest (Auspex/Mechadendrite/EG-Boni) bleibt DM-narrativ aus dem RAG statt unsicherer Auto-Anwendung. Psyker-Backfill mitgenommen, weil dieselben Dateien offen waren und Psyker sonst nicht eingebbar/druckbar sind → **ADR 023** |
| D51 | Psyker / Warp subsystem | **Profile-driven, voll regeltreu (IM ch. VI).** New optional `psyker` block in `data/systems/imperium_maledictum.json` (power catalog with Warp Rating + Difficulty; Warp-Threshold = Willpower Bonus; d100 Perils-of-the-Warp + Psychic Phenomena tables). Engine gains pure `resolve_manifest` (Manifest Test via `resolve_test`; Warp Charge per p.163 incl. Critical/Fumble/Push), `resolve_perils`/`resolve_phenomena` (banded d100), `reverse_d100` + `advantage` kwarg (IM reverse-the-digits, p.189). New `<<MANIFEST power [für name] [push]>>` marker → `ManifestRequest` → cog button → engine rolls + bookkeeps Warp Charge (code-owned on `Combatant`, persisted) → fed back to narrate. Catalog = Core minor + core Biomancy + PG Inquisition powers; prose via RAG. +29 fixed-seed tests (220 green) | Tobi chose full fidelity over narrative-only and pointed at the Inquisition Player's Guide. Engine must stay system-agnostic (ADR 005) → tables/threshold are profile data, not code; per-power bespoke effects stay LLM-narrated from RAG (golden rule #7) rather than re-encoded. Timing: end-of-turn containment Test resolved at the manifesting action's end (no hard round boundary in the voice loop) → **ADR 022** |
| D49 | `!lore` command | **Weltwissen, two modes** — `!lore [topic]` (alias `!hintergrund`) pages `data/lore/<topic>.md` (no arg → `imperium`, `!lore chaos` → Chaos) through the existing `RulesView` (◀/▶); **`!lore <frage>`** (same-day extension, Tobi) looks the question up in the vector store and posts the best-matching compendium sections as an embed — new `RulebookRetriever.lookup()` (caller-picked sources = `lore_imperium`/`lore_chaos`/`setting` only, k=2, **own ceiling 0.52**), deterministic chunk display, no LLM. New pure `dmbot/rag/lore.py` (`lore_pages`: heading = page, H1 + `>`-source-note skipped, >4000-char guard; `available_topics`). Read-only — no TTS, no DM turn. Plus `tools/lore_to_html.py` → `docs/lore.html` (grimdark standalone, review/handout view, re-run after lore edits) | Tobi wants players to read an ausführlicher human-lore rundown (reviewed via HTML first) AND ask direct lore questions; the readable file covers the rundown case. Single source of truth: command, RAG Weltwissen and handout all read the same committed files. Lookup ceiling tuned on live probes: looser than the 0.45 prompt gate (narrative phrasings ~0.48 deserve an answer on an explicit ask) but under 0.54 where the off-corpus Tyranid question grabbed the nearest wrong chunk — "steht nichts im Weltwissen" beats a misleading hit. Rulebook excluded (English layout soup; rule questions → `!rules`/DM turn). Applies existing patterns → D-entry, no ADR |
| D54 | Anti-repetition persona rule | **Prompt-side W4 fix** — a persona rule in `prompts/dm_core_de.md`: established facts (Was bisher geschah, world state, ongoing scene) are **already known to the players**; reference them briefly, describe in detail only **new** things + the **consequences** of the latest action. Plus the recap label in `_build_request` sharpened to „(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)". Prompt-only; no code guard built (D45's fuzzy `is_self_repetition` stays the fallback) | The DM re-explained settled context (places/NPCs/events) in full every turn instead of advancing — the persona side of W4, which D45's after-the-fact echo guard can't pre-empt. ADR 016 itself flagged W4 as open, and this lives in ADR 016's persona-output-discipline domain → **Nachtrag in ADR 016**, no new ADR. Live-observe nemo's adherence |
| D55 | XTTS-Babble bei Satzzeichen | **Zwei XTTS-Sampling-Hebel** (`dmbot/tts/xtts.py` `_SYNTH_KWARGS`, an beide `tts_to_file`-Pfade): **`split_sentences=False`** (`textsplit` chunkt bereits in <240-Zeichen-Satzgruppen; XTTS' eigener pysbd-Splitter zerlegte die in Satzzeichen-Fragmente → GPT-Decoder-Loops/Babble) + **`repetition_penalty=10.0`** (Model-Config liefert 5.0, XTTS' eigener `inference`-Default ist das stärkere Anti-Loop-10.0; tunbar via `XTTS_REPETITION_PENALTY`). 246 grün; live-unverifiziert | D53 härtete den *Text* zu XTTS (Whitelist + Sprechbarkeits-Guard) und stellte diese zwei Sampling-Hebel „nur bei Bedarf nach Live-Test" zurück — der Test brauchte sie („Psychosen bei Satzzeichen": autoregressives Loopen an Kommas/Satzenden, kein Normalisierungs-Leak). Kwarg-Fluss per API-Inspektion bestätigt (`tts_to_file`→`Synthesizer.tts`→`Xtts.synthesize`). Nächster Hebel bei Persistenz: `temperature` runter → **Nachtrag in ADR 016** |
| D56 | Auto scene transitions | **Third LLM marker `<<ORT <scene-id>>>`** (mirrors `<<TEST>>`/`<<MANIFEST>>`): the DM *requests* a scene move in-band; code strips+validates it and a **human confirms** via a `SceneChangeView` button before the deterministic move runs (`_set_scene`, shared with `!ort`). Profile-free `extract_scenes` (scenes belong to the adventure, not the rules profile); `finalize_answer` → 4-tuple; `_pending_scenes` queued only under the `_last_action` post-roll guard. Switchable target mode `DM_SCENE_MODE` / `!ortmodus`: **`verbunden`** (default — only `leads_to` neighbours, via pure `Adventure.resolve_move`) vs **`frei`** (any scene); illegal/unknown → ignored+logged. Manual `!ort` stays as override. +12 tests (246 grün); live-unverified | `!ort` mid-scene was friction (ADR 020 deferred this exact step: "re-evaluate once live play shows `!ort` friction"). Upholds golden rule #3 — the LLM never *writes* `scene_id`, it emits a validated request like it requests dice (golden rule #2); the confirm button is the human-in-the-loop gate. Reverses only ADR 020's "moved by humans only" binding → **ADR 026** |
| D57 | Context budget (1st live round) | **(a) `num_ctx` configurable + high.** New `OLLAMA_NUM_CTX` env (Config `ollama_num_ctx`, default **24576**), threaded config → cog → `OllamaClient(num_ctx=…)` → request `options`; removes the hardcoded 8192. **(b) Rolling auto-recap (`DM_AUTORECAP`, default on).** When `prompt_eval` crosses `ctx_over_budget` (0.85·num_ctx), *after* the turn is spoken (off the hot path): a **cumulative** recap (`summarize(cid, prior_recap=…)`) is generated, persisted like `!wrap up`, and the in-memory history **cleared** — so the next prompt's head (persona + adventure) is never truncated. Per-channel `_compacting` guard. +18 tests (262 green) | The 1st live round's loudest failure ("geht null auf die Story ein") was a **silent truncation**: `num_ctx` ran at 8192 (the 24000 Tobi thought he'd set was read nowhere); from ~turn 16 the prompt head (persona + adventure summary) fell out — simultaneously causing story-ignored, runaway length, puppeting, pre-roll resolution. Two layers (big window + proactive compaction) close it GPU-independently. Chose compact-and-clear on the real budget signal over the `prompt-6` fold-before-trim spec → **ADR 027** |
| D58 | `!start` briefing + persona steer | **(a) `!start`** (aliases `!briefing`/`!auftrag`): a dedicated opening turn — the DM narrates the `auftrag` briefing (Halikarn message, mission, leads as atmosphere) via the existing stream/speak path; a thin `respond_opening*` path leaves `_last_action` None so dice routing is suppressed; sets `scene_id` to the start scene if unset. **(b) Persona** (`prompts/dm_core_de.md`): keep the current scene's goal in view + steer gently toward open leads (not a list, not railroad); every turn ends with the **world in motion** (an NSC acts/speaks or a concrete hook), never a flat description that stops; **spotlight** — bring other named/silent characters in by name | 1st-round complaints: "am Anfang nicht gesagt, was abgeht" (`!join` only printed status), the DM stopped on static descriptions with passive NPCs, and one player sat idle all session. Prompt/feature tuning in ADR 016's persona-discipline domain (like D54) — effective only because D57 stops the persona being truncated → D-entry, no new ADR. Live-unverified |
| D59 | RAG junk-shape filter | **Distance-independent `_is_junk_hit`** in `fetch_block` (per-turn narration gate only; `!rules`/`!lore`/`lookup` untouched): drops dash-run headings (`-{4,}`), statblock-tag headings (`(eLite)`/`(trOOP)`/`(LeaDer)`), and picture-text bodies. `MAX_DISTANCE` stays **0.45**. 103/2482 chunks become narration-ineligible; recall@1/@3 **unchanged** (52%/81%) | 1st round: pure-RP turns injected OCR/TOC garbage at the 0.43–0.45 edge (`WARRIOR`, `MACHARIAN TOMES`, `--- PSYCHIC POWERS ---`), wasting the context budget D57 fights. Calibration (ADR 025) showed tightening the threshold costs real recall (`CRITICAL HIT` @0.439) — a shape filter is surgical instead. Known gap: `WARRIOR`-style epigraph rows need ingest-level re-chunking (out of scope) → **ADR 028** |
| D60 | Voice cog split → SessionRuntime | **Pure structural refactor (zero behaviour change).** The 2300-line `VoiceReceiveCog` split into a shared **`SessionRuntime`** (`dmbot/runtime.py`, built once from `Config`, injected into every cog — the 26 ctor kwargs collapse into it) + three thin cogs: **VoiceCog** (join/leave/vstatus/mic/pause, VAD-sink), **DiceCog** (roll/test/turn/rules/npc/damage/heal, dice+manifest buttons, auto-combat, turn-order render), **DMCog** (batch+streaming delivery, TTS speak, auto-recap, !dm/!redo/!start/!wrap/!say/!voice **and** scenes !ort/!szenen/!ortmodus + the `<<ORT>>` marker + !lore). **No `bot.get_cog`** — five hooks registered on the runtime (`run_and_deliver`/`auto_dm_turn`/`handle_dice`/`reanchor_mic`/`post_turn_order`). `commands.py` deleted; suite **263 green** (only test-import paths + one `test_autorecap` fixture rewired to a stub runtime — assertions unchanged) | The file had become a god-cog with a 26-kwarg ctor; every session paid for the whole thing and the concern boundaries had blurred. Moved-not-rewritten (per-agent AST/reverse-rename diffs + a streaming-pipeline spot-check confirm byte-identical bodies; only `self._X`→`self._rt._X` renames + the hook calls). Boot path unchanged (preflights once, same order; `TEARDOWN_STEPS` sum still 4 → shutdown display byte-identical). Binds later work: Phase 10b profile bootstrap hangs off the runtime, not a cog → **ADR 029** |
| D61 | Code-review correctness round (post-cog-split) | **9 verified defects in the day's feature work + cleanup, behaviour preserved.** Correctness: (1) **Warp-containment Test → Disziplin (Psi)** not Psi-Meisterschaft (IM p.163) — new `ResolvedManifest.contain_base` wires the previously-unused `psyker_purge_skill()`; (2) **party psyker not in WorldState** no longer silently drops Warp Charge — one-time German warning (no safe single-char state add); (3) **batch delivery** awaits dice/scene tasks in `finally` so the 🎲 button isn't lost when speak raises; (4) **auto-recap** `clear_history` clears only the `summarize`-consumed prefix (`_compact_consumed`) so a turn appended during the LLM await survives; (5) **glued markers** `\b`→`[\s:]*` so `<<ORT1>>`/`<<ORTmud_gate>>`/`<<MANIFESTSmite>>` strip+fire instead of being read aloud; (6) **`resolve_test`** signature-dispatch (`inspect.signature`) replaces the `except TypeError` that swallowed real errors + double-rolled (golden rule #2); (7) **streaming** cancels orphaned prod/synth/play tasks + drains queued WAVs on a mid-stream bridge failure (permanent-mute claim **refuted** — `finally` always unmutes, mute logic untouched); (8) **layer-2 mute → depth counter** so DM-speak vs operator pause/resume nest (resume mid-playback can't unmute); (9) **soak** uses `skill_value` (strip+CI) so a `"Tgh "` key isn't 0 soak. Cleanup: shared `_catalog_lookup` (profile), shared `tts/wavio.write_silent_wav`, dead `reduce_warp_charge` removed, no-op `[:80]` slices dropped, **thread-local cached sqlite conn** + `<<`-free StreamAssembler fast path. Suite **293 green** | Tobi asked `/code-review` over the day's commits, "Funktionalität soll bleiben". Multi-agent review (9 finder angles + per-finding verifiers over `5d672b6~1..HEAD`) cleared the cog split as faithful and found these in the parallel feature work. The **altitude findings — system-agnostic generalisation of engine/marker/RAG-sources — are DEFERRED to the second-profile / Phase-10b point** (no second system to generalise against yet; large + behaviour-risky; ADR 005 stance is "generalise when the 2nd system arrives") → **ADR 030** |
| D62 | `!intro` opening monologue | **New `!intro` command (aliases `!einleitung`/`!eroeffnung`): one long opening monologue that involves every PC, by reusing + parameterising the `!start` opening path.** New `CharacterStore.intro_roster_de()` builds a full-depth German party roster from `Character.raw` (concept/origin/faction/distinguishing/goals/connections/arc, tolerant of lean sheets); new pure `build_intro_director_msg(roster)` wraps it in a `[Regie]` instruction (one monologue: place → arrival → mission from the scene card/summary, then a personal beat per named figure — weave in, only hint at private goals, no dice) with the roster embedded in the **director (user) message** so the ADR-019 prompt order is untouched. An optional `num_predict` override is threaded through `_build_request`/`_chat_once`/`_generate`/`_stream_and_store`/`respond_opening`/`respond_opening_streaming` (default `None` → unchanged); `!intro` runs on `DM_INTRO_NUM_PREDICT` (default 800). `!intro` mirrors `!start`'s safe scaffolding (deterministic scene-pointer move only if unset, dice suppressed, stream/speak). `!start` left as the short briefing. +7 tests (**300 green**); live-unverified | Tobi (plan mode): the 1st-round "sagt am Anfang nicht, was abgeht … bezieht die Figuren nicht ein" gap needed a real opener. Chose a **monologue** over a scripted multi-beat sequence, a **separate `!intro`** over extending `!start`, and **full** figure depth — all his calls. Reuse-not-duplicate per ADR 030; roster-in-director-message avoids per-turn prompt bloat (ADR 019). Risk (nemo-12B rambling at length) watched live; fallback = multi-beat or lower `DM_INTRO_NUM_PREDICT` → **ADR 031** |
| D90 | `dm-sync` entry point for the sync check (dev-tooling) | **The D89 tool moved from `tools/sync_check.py` to `dmbot/tools/sync_check.py` (new subpackage) and runs as `uv run dm-sync` via `[project.scripts]`.** As a package module the `sys.path.insert` hack is gone (`REPO_ROOT` = `parents[2]`); `main() -> int` + `__main__` guard unchanged. To make the script entry exist, `[tool.uv] package = false` was replaced by a **hatchling build backend** (`packages = ["dmbot"]`) — `uv sync` now installs `cogitator` editable, solely for the entry point (still an application, not a published library). All references repointed (SETUP.md, conventions.md, ingest.py docstring, `tests/test_sync_check.py` import — assertions unchanged); **no shim at the old path** (a silently-drifting stale copy is worse than a hard break). `[sync]` block verified byte-identical pre/post move (only the repo line's clean→dirty = the change itself). Suite **459 green**, no new ruff findings | The long `uv run python tools/sync_check.py` should be one short command on both machines — the fingerprint format is now a mini-contract Timo may diff against, so zero output change was the constraint. Packaging the project is the one real cost, accepted as the only way `[project.scripts]` materializes under uv. Timo needs one `git pull` + `uv sync` before `dm-sync` exists on his machine. Pure ergonomics → D-entry, no ADR |
| D91 | NPC memory: how do NPCs remember conversations without violating golden rule #3? | **Memories are a narrative layer on the NPC entries in `state.json` (LLM-extracted gist + verbatim key quote, capped 30/NPC, prune-protected lies/importance-5); every hard effect is code:** the extractor only *proposes* — `step_attitude` clamps drift to ±1 step per scene on the fixed `hostile→wary→neutral→friendly→loyal` scale, revealed lies are flipped by code (believed=False + importance-5 entry + one step toward hostile), and importance-≥4 news spreads deterministically to same-`faction` NPCs as hearsay (no quote, importance −1, no cascade, gist-deduped). One structured-JSON LLM call per **scene exit** (`!ort` / confirmed `<<ORT>>`) + `!wrap` catch-all — never per turn; tolerant parse, one retry, then skip (never blocks the scene change). Top-K per scene NPC in the prompt (`DM_NPC_MEMORY_TOP_K`, lies always included, gossip rendered as „Hörensagen“); `DM_NPC_MEMORY=0` kill switch, `!npcmem` read-only debug. Suite **486 green** (+27) | The same request/validate/apply pattern as dice/ORT/ERLEDIGT: LLM requests, code decides. Per-turn extraction (latency on local hardware), embedding retrieval over memories, and an LLM gossip pass were rejected — details + live gate (lie → scene change → return → NPC remembers) in **→ ADR 044** |
| D89 | Sync fingerprint tool for the untracked must-haves (dev-tooling) | **New standalone `tools/sync_check.py` (`uv run python tools/sync_check.py`): one compact `[sync]` block — repo commit (clean/dirty), per adventure JSON a short sha256 + mtime + scene/NPC count via the real `Adventure.load` (a broken compendium prints a loud LADEFEHLER line instead of crashing), `rag.db` size + meta (model/dim) + chunk count PER SOURCE + per-source ingest date, `.env` KEY coverage vs `.env.example` (missing/extra names only — never values), and `git status --porcelain` over the tracked data seeds.** Offline (no bot/Ollama), degrade-don't-die per line (missing artifact → FEHLT line), repo-anchored paths (runs from any cwd). Companion: `dmbot/rag/ingest.py` now stamps `ingested:<source>` (`YYYY-MM-DD HH:MM`) into the existing key/value meta table per ingest and clears stale stamps on the model/dim rebuild-drop; pre-stamp DBs read tolerantly as „unbekannt". SETUP.md gained „Staying in sync (second machine)". +15 tests (`tests/test_sync_check.py`); suite **459 green** | The untracked must-haves (adventure cards, rag.db, .env keys) drift silently between Tobi's and Timo's machines — „hast du die aktuelle?" was answered by guessing; now both run the tool and diff the blocks. Short sha256 over mtime as truth (copying changes mtimes — mtime stays as a human-readable hint); rag.db compared by meta + per-source counts, deliberately NO whole-DB hash (vacuum/row order makes identical content binary-unequal). Ingest stamp as meta ROWS (key per source), not a chunks column — the meta table is already key/value, so old DBs need zero migration. Output = file names + counts only: no book content, no `.env` values (pinned by test). First real run surfaced drift immediately: Tobi's local `.env` is 20 keys behind the template. No ADR: no design trade-off worth a record |
| D88 | `/author-adventure` authoring skill (adventure-md → compendium draft, dev-tooling) | **New Claude-Code skill `.claude/skills/author-adventure/` (SKILL.md + `validate.py`): 5-pass offline workflow — structure pass with a HARD STOP for scene-cut approval, card/NPC/summary passes in profile-aligned German (difficulties verbatim from `difficulty_ladder`, skills = party sheets ∪ profile; mismatches go on the checklist, never invented), spoiler self-check, loader validation via the real `Adventure.load` (id collisions, dangling `leads_to`, gate integrity, statblock coverage), and a review checklist of the draft's own weak spots.** Hard rules: `git check-ignore` guard before writing (bought-book derivatives never in tracked paths), zero book content in the skill file, never commit. Acceptance test: blind dry-run against the Chemical-Burn md → 14-scene draft, loader-valid incl. ADR-043 gates; diff vs the 15-scene hand-built compendium found 4 convention gaps, folded back into the skill (dedicated opening scene as `start_scene`; sparse forward-dramaturgical `leads_to` — `verbunden` treats it as the legal-move list; summary carries the WAHRHEIT with an explicit secrecy frame; a statblock for EVERY `npcs_here` name). Throwaway deleted; no bot code touched | Adventure #2 („The Blazing Seraph", 49 pp.) and later books should cost an afternoon of *redigieren*, not days of authoring — the human stays Kurator (draft + checklist, never a silently-finished compendium). Validation imports the existing loader instead of duplicating schema knowledge; the diff-vs-hand-built comparison is the honest acceptance test (draft written before looking at the hand-built cut). No ADR: precedent-following conventions, no new schema/design trade-off |
| D87 | Stateful scene cards (element flags, dead NPCs, gated exits) | **The scene card reflects world state — via code-owned flags, never LLM-written (golden rule #3).** (1) Backward-compatible element ids: `opportunities_de`/`secrets_de` entries stay plain strings (derived positional ids `opp-N`/`geh-N`) or become `{"id","text_de"}`; unique per scene across both lists (collision → `log.error` + positional fallback). (2) `WorldState.scene_flags: dict[scene → element ids]` (first dict field, omit-when-empty, persists like `scene_id`); mutator `runtime._set_scene_flag` validates against the CURRENT scene only. (3) Render: resolved → „Bereits geschehen:", revealed → „Bekannt (bereits enthüllt):", ids inline (`- [opp-1] …`), dead NPCs (wounds ≤ 0, case-insensitive name join) → `(tot)`, locked exits hidden from „Mögliche nächste Orte". (4) Fourth marker `<<ERLEDIGT id>>` mirrors `<<ORT>>` at every seam (glued grammar, strip-before-TTS, streaming withholding via the shared `<<` delimiter, pending queue under the post-roll guard, drain as a third delivery task) — but ALL valid markers per turn are processed; confirm button per element (`FlagView`), `DM_FLAG_CONFIRM=0` = auto-apply; manual `!erledigt`/`!offen`. (5) Gated exits: `leads_to` entry `{"ziel","requires"}` (requires = element of the OWNING scene); `verbunden` `resolve_move` rejects unmet gates like unknown targets (condition named in the console log only — spoiler discipline); `frei` + manual `!ort` bypass; typo'd requires fails open (`ERROR`, gate dropped). Forced seam cost (declared in the approved plan): `finalize_answer` 4→5-tuple = 3 mechanical unpack widenings in existing tests, zero assertion changes. +49 tests, suite **444 green**; live-unverified | Static cards contradict the world after play: revisits re-offer used Gelegenheiten, re-hide known Geheimnisse, dead NPCs stand around. Forks decided with Tobi: locked exits **hidden** (persona says "use only offered ids" — visible-but-locked invites rejected moves + hints), `requires` scoped to the current scene (derived ids repeat across scenes → global lookup ambiguous), all-valid-per-turn (one narration can resolve several elements; flags idempotent + low-stakes, unlike the single scene pointer). Confirm-by-default = ADR 026's human-in-the-loop argument; auto-apply acceptable as opt-in since flags only change the render → **ADR 043** |
| D86 | Deterministic `!intro` weakness check + one-shot retry | **New pure `dmbot/llm/intro_guard.py::is_weak_intro(text, roster_names)` — the opening is "weak" if too short (<280 chars) OR a roster figure's first name is never named (whole-word, genitive-`s` tolerant). `respond_opening` gained an optional `is_weak` callback: when weak it regenerates ONCE with `INTRO_RETRY_NUDGE` appended, keeping only the better answer in history (never speaks less).** Wired on the batch path (`!intro test`) with the live roster (`CharacterStore.character_names()`); streaming `!intro` left unchanged (can't retry mid-audio). +5 tests (`test_intro_guard.py` truth table incl. genitive/word-boundary; 4 retry-path tests in `test_intro.py`). Part of the playability tuning round | ADR 041 + add. 1 fix *what the opening says wrong* (meta-open/quote/curt close); this fixes *when it comes out thin* (the other live failure: short/generic, skips a figure — sampling variance). Same lesson: don't trust the prompt, add a deterministic backstop. Batch-only by design → it's the lever that makes the validated gapless opener preferable once TTS is GPU-fast (Workstream A) → **ADR 041 addendum 2** |
| D85 | Anti-repetition sampling (`repeat_penalty`) + deterministic roll-router carve-out | **`OllamaClient` gained `repeat_penalty`/`repeat_last_n` as instance defaults (like `num_ctx`), merged onto every call by a shared `_merged_options()` (batch+stream can't drift); per-call options still win. `DM_REPEAT_PENALTY` (1.1) + `DM_REPEAT_LAST_N` (256), live-tunable.** nemo with no penalty loops/drifts into generic filler on 12B; this attacks the cause before the post-hoc echo guard (and covers the streaming gap it can't). **Carve-out (adversarial-verify find):** the roll router's `classify_test` sets `repeat_penalty=1.0` explicitly — its prompt lists every skill+difficulty in the look-back window, so a penalty would discourage the very enum it must pick → corrupting the deterministic verdict (golden rule #2 / ADR 014). Pinned by `test_roll_router_call_disables_repeat_penalty`. +5 `test_sampling.py`; suite 395 green | Playability tuning round (Tobi: model stays nemo, "am Drumherum drehen"). Trade-offs weighed: instance-default vs static vs per-narration-turn (chose instance-default + one explicit deterministic override — simplest, greppable); penalty 1.1 (higher frays German). Conscious accept: recap/rules-Q inherit the mild penalty (free-text, harmless/helpful) → **ADR 042** |
| D84 | Strip the `!intro` meta-open deterministically + raise intro temperature to 0.7 (ADR 041 addendum) | **Follow-up to D83 after a live retest *with* D83 active still showed nemo emitting "Als Spielleitung beginne ich die Sitzung:", wrapping the whole monologue in `"…"`, and closing "Was werdet ihr … tun?".** Lesson: a prompt instruction can't reliably suppress the tic → strip it deterministically. In `dmbot/llm/sanitize.py`: (1) `_META_PREAMBLE` gained opener verbs (`beginn\w*|eröffn\w*|start\w*|leite?`) + objects (`…die Sitzung|Runde|Spielrunde`) so the !intro meta-open strips like the older `beschreibe`-forms; (2) new `_unwrap_enclosing_quotes` drops ONE pair of quotes wrapping the *whole* answer (clean single envelope only — closing quote must not recur inside, so an NPC line keeps its quotes), wired into `_sanitize` **between** leading and trailing so the now-unblocked "Was tut ihr?" strip fires (the wrap had left `…?"` not `…?`). Both intro paths finalise through `_sanitize` (batch + streaming `finish()`). Also: default `DM_INTRO_TEMPERATURE` **0.5 → 0.7** — 0.5 read flat/formulaic; with the tic now stripped deterministically the richer higher-temp weaving is affordable. +3 sanitiser tests; suite **379 green** | Deterministic post-processing owns *removing* the tic (guaranteed, model-independent), the brief + temperature own *shaping* the prose (best-effort). The two existing sanitiser strips already covered "beschreibe ich …"/"Was tut ihr?" — they just had a verb gap + a quote-wrap blind spot → **ADR 041 addendum** |
| D83 | Make `!intro` reliable (fixed low temperature + hardened director brief) | **Two complementary changes so the campaign opener stops being a coin-flip.** **(1) Temperature:** new config `dm_intro_temperature` (env `DM_INTRO_TEMPERATURE`, default **0.5**), threaded as an optional `temperature` param parallel to `num_predict` through `respond_opening`/`respond_opening_streaming` → `_generate`/`_stream_and_store` → `_chat_once` → `_build_request` (added to Ollama options **only when set**); `!start`/normal turns pass `None` → model default, unchanged. Both `!intro` (streaming, via `_deliver_streaming(opening_temperature=…)`) and `!intro test` (batch, `_deliver_intro_chunked`) forward `runtime._intro_temperature`. **(2) Hardened brief** (`director_msgs.py`, both variants): HEAD forbids meta-narration ("schreibe NICHT, dass du die Sitzung eröffnest …", asks for "mehrere Absätze"); TAIL asks for room + a thematic close and forbids the curt "Was tut ihr?"-bail. +2 tests (temp reaches options when set / absent by default); suite **376 green** | Live 2026-06-16: with the party confirmed loaded (D82), config aligned, teammate pulled, `!intro test` still flipped between the great 14.06. opener (rich, every figure woven in) and a short generic turn that *narrated* the brief ("Als Spielleitung beginne ich die Sitzung…") with no characters. Director text + roster were intact → root cause is **model variance**: the opening set no temperature, running at mistral-nemo's ~0.8 default. Scoped the fix to the opening (normal turns are fine); 0.5 not 0 (keep some flair); a threaded param not a hidden attribute (mirrors `num_predict`, no cross-turn leak). Live-unverified (model-behaviour claim) → **ADR 041** |
| D82 | Default party so the real party isn't bound to one voice-channel id | **New committed `data/sessions/_default/characters.json`, loaded for any voice channel that has no own sheet — *before* the `_example` fallback.** New config `default_party` (env `DM_DEFAULT_PARTY`, default `_default`); `SessionRuntime._load_characters` resolves channel-sheet → default party → `_example`, and the loud D43 `fallback` warning now fires **only** for the `_example` case (the default party is the *intended* fallback → loads silently). `_default/characters.json` allowlisted in `.gitignore` next to `_example`, so it ships via git to a teammate's clone and serves **every** channel; boot `_load_characters(None)` also picks it up. +5 `tests/test_load_characters.py`; suite **374 green** | Live 2026-06-16: `!intro` in a *new* voice channel ("fett", `1355…`) named the **example** party (Seskin/Vask/Mortn) and read as "the intro went generic" — because the party was bound to a channel id and only "circlejerk" (`1343…`) had a committed sheet, so a teammate's clone (where the bot runs) had no sheet for any other channel. Chose a committed default **file** over a per-channel `.gitignore` wildcard or a `DM_DEFAULT_PARTY=<id>` **env** (env doesn't travel via git → a manual step on the clone, defeating the point). Bought `adventures/`/PDFs stay local — repo is public (copyright) → **ADR 040** |
| D81 | Split scenes + lore out of DMCog into thin sub-cogs (`/improve-architecture`, deferred ADR-035 follow-up) | **Move `!ort`/`!szenen`/`!ortmodus` → new `dmbot/voice/scenecog.py` (`SceneCog`) and `!lore` + its 3 helpers + 3 dicts → `dmbot/voice/lorecog.py` (`LoreCog`); both registered in `__main__`.** Moved bodies **byte-identical** (150/150 lines verified) except one deliberate change: `_lore_speak`'s `speak_fn=self._delivery._speak` → `self._rt.speak`, routed through a new **`runtime.speak`** hook DMCog sets (ADR 029 cross-cog pattern), so LoreCog never reaches into another cog/the bridge. SceneCog needs no hook (only `self._rt.*`, no other caller). Lore-only imports (`RulesView`/`LoreReadView`/`available_topics`/`lore_pages`/`_DATA_DIR`/`discord`) left DMCog. `dmcog.py` 662→**502**; `scenecog.py` 84, `lorecog.py` 126. New `tests/test_subcogs.py` (+10, the `object.__new__`+`Cog.<cmd>.callback` pattern) — scenes/lore had **zero** command tests before. Suite **369 green**, 0 existing-test edits, ruff clean | The largest hand-maintained file after ADR 035, which **explicitly deferred** these two splits and flagged the discord.py `CogMeta` command-collection risk for a mixin. Chose **sub-cogs over a mixin** (sidestep the metaclass; mixin `@commands` may silently not register) and **two cogs over one `AdventureCog`** (scenes/lore share no state → two narrow files beat one medium for "read only what the task needs", Tobi's goal). Surfaced + chosen via a `/improve-architecture` workflow (3 finders + 3-lens adversarial verify; 13 candidates → 7 survived). Resolves the open ADR-035 fork → **ADR 039** |
| D80 | Deepen prompt assembly + session seed + panel helper (`/improve-architecture` #4/#5/#6) | **Three behaviour-neutral deepenings; finishes the `/improve-architecture` strand.** **#5 (ADR 038):** extract ONLY the system-prompt string-join out of `orchestrator._build_request` into a pure, order-explicit `assemble_system_prompt(...)` in new `dmbot/llm/prompt_assembly.py`; the `.get()` cache reads stay in `_build_request` so the cache-vs-pull timing (RAG per turn, recap/state/adventure cached) is untouched. **#4 (D-entry):** bundle the ~33-line `!join` seed sequence into `runtime.seed_session(voice_channel, text_channel)` (party/turn-order/state/scene-pointer/D41 crash-recovery); voice-receive wiring + announcements stay in the cog. **#6 (D-entry):** the delete-previous-pinned-panel block, byte-identical in 4 places, into `runtime.clear_panel(attr)`; the pause panel's edit-in-place stays. Built via a workflow: sequential implement (shared files) + 3 parallel adversarial verifies. Suite **359 green** (+16 tests), 0 test edits, ruff clean | From `/improve-architecture` (Tobi: "mach 4 5 und 6"). #5 has the real trade-off: join-only extraction, NOT a provider registry that would own computation+caching and break the deliberate timing → **ADR 038**. #4/#6 are faithful moves (seam = cog IO vs runtime state; the identical block) → D-entries. Strand #1–#6 now done (#3 rejected) |
| D79 | Deepen STT filter + combat resolution (`/improve-architecture` #1+#2) | **Two behaviour-neutral deepenings from the `/improve-architecture` candidate set.** **#1 (mechanical, no ADR):** the already-extracted pure `stt/segments.py::confident_text` (Whisper hallucination guard) wired into `transcriber.py` — inline duplicate + dead `_NO_SPEECH_MAX`/`_LOGPROB_MIN` constants removed, `tests/test_segments.py` added (boundary `==0.7`/`==-1.0` kept — strict `>`/`<`). **#2:** the attack soak montage + the Warp containment→Perils chain pulled out of `dicecog.py` into a new pure **`dmbot/rules/combat.py`** (`toughness_bonus`, `resolve_attack`→`AttackOutcome`, `resolve_warp_consequences`→`WarpConsequence`) — no Discord, no WorldState mutation, RNG injected; the cog delegates and keeps the mutations + post-mutation `describe_damage_de`. Built via a 2-agent workflow (parallel implement + adversarial verify); German Perils/Overt strings copied byte-identical. Suite **343 green** (+7/+12), **0 test edits**, ruff clean | From `/improve-architecture`; Tobi picked #1 + #2 (verworfen #3 turn-order; #4/#5/#6 parked). The **seam** is the real trade-off: the pure function stops **before** the WorldState mutation rather than reproducing the wound-clamp (which would duplicate `apply_damage` → narration↔state drift risk). `_toughness_bonus` stays a thin cog delegator → zero test edits. Hardens the deterministic core (dice = code) → **ADR 037** (#2); #1 is D-entry only |
| D78 | Curated agent-skill set (Pocock-derived) | **Added 4 Claude Code skills under `.claude/skills/` — own `/tdd` + 3 adapted from `mattpocock/skills`: `/grill-me`, `/improve-architecture`, `/to-prd`.** `/grill-me`+`/to-prd` are a designed pair (grill builds the context, to-prd writes the PRD to `docs/plans/<slug>.md` — no issue tracker, unlike the original). `/improve-architecture` = whole-codebase deepening review (deletion test), repo-adapted (architecture.md/docs/decisions, golden rules), Markdown not HTML, grilling conditional not forced. `/tdd` = red-green-refactor on the deterministic core. README index kept in sync; commits abb49c8/0f371be/1cd671c/0924001/76c0b1a on main; no bot code, suite untouched (324) | Tobi asked for a "tdd skill" (none existed) → researched + built, then surveyed external skill repos. **Adopted** Pocock's workflow skills, each adapted to this repo's invariants (issue-tracker→`docs/plans`, CONTEXT.md→`architecture.md`, forced-grill→conditional). **Rejected** the `rohitg00/awesome-claude-code-toolkit` aggregator wholesale (generic stack tutorials, cloud-API-oriented or overlapping `/code-review`·`/simplify`) — keep the skill set lean (golden rule #9). Tooling/process → D-entry, no ADR |
| D77 | Auto gates: ruff in the hooks + review/simplify trigger checklist | **Cheap zero-token checks run automatically; the expensive LLM reviews stay on judgement.** (1) The Claude Stop hook (`tools/hooks/test-on-change.sh`) now runs **`ruff --select F`** (pyflakes: unused imports/names) before pytest — same philosophy (only on dmbot/tests/data-systems changes, silent on green, non-blocking); F-only on purpose (line-length/style E* off — long doc lines are deliberate, re-export shims carry `# noqa: F401`). It immediately caught + removed 2 dead imports (`re`, `difflib.SequenceMatcher` in `orchestrator.py`, D70 extraction leftovers). (2) New **blocking git pre-commit hook** (`tools/hooks/pre-commit`, activated via `git config core.hooksPath tools/hooks`) runs the same ruff-F + suite on the *user's own* commits, aborting on red (bypass `git commit --no-verify`), scope-guarded to staged dmbot/tests/data-systems. (3) New `docs/conventions.md` section "Code-Review-, Simplify- & Lint-Gates": when `/code-review` (read-only) is worth pulling vs. the day-end fan-out, and `/simplify` (write-pass → never automatic; hand-simplify race-sensitive code per D72). Suite 324 green throughout | Tobi asked whether to auto-run `/code-review` (and later `/simplify`) before every commit. Decided **no**: those are billed LLM passes (the D76 fan-out ≈ 983k tokens) and `/simplify` *mutates* code — auto-running it contradicts the project's hand-control discipline (D72). Right split: **cheap + deterministic = automatic (0 tokens), expensive LLM review = on judgement**, the judgement encoded as a checklist that survives context-clears. Other skills (verify/run, security-review) judged not worth a standing reminder. Tooling/process → D-entry, no ADR |
| D76 | Review-round fixes: `disconnect_voice` contract + delivery test-gap | **Fan-out `/code-review`-style pass over the day's commits `7b5af54..HEAD` (21 agents, every finding adversarially verified): 14 findings → 3 confirmed, 11 dismissed; no D70–D75 refactor regression survived, golden-rules sweep clean.** Fixed in 2 pushed commits. **(1) `dmbot/shutdown.py::disconnect_voice`** keyed its True/False on `asyncio.wait_for` raising `TimeoutError`, but against the real discord.py + Py 3.12 that branch is dead — the post-leave confirmation wait **swallows** the bounding cancel and returns normally, so `wait_for` returns and the function always returned `True` (the caller's "abandoned at shutdown" warning never fired); the slow-confirmation test masked it with a bare-`sleep` mock that lets the cancel propagate (a green `False` production never yields). Rewrote to decide via `asyncio.wait` (finished-in-window → confirmed, else cancel the lingering wait + report abandoned) — deterministic, no elapsed-time boundary flake; the test now models the real swallow-and-cleanup contract + a second propagating-cancel test (`2b608e7`). **(2) New `tests/test_delivery.py`** pins the previously-untested `puffer` head-start state machine in `_deliver_streaming`: prebuffer fill before the first play, plain-stream instant start, transform-to-empty skip, and **mid-stream-failure temp-WAV cleanup (no leak)** (`5499066`). Suite **324 green** (319 → +4 delivery, +2 shutdown −1 replaced) | The day's big refactors (D70–D75) were claimed behaviour-preserving; a thorough fan-out review confirmed that (adversarial verify killed every refactor-regression finding, golden-rules sweep clean) and surfaced one real low-impact bug + the largest coverage gap (`delivery.py`, the biggest extraction, had zero tests). The 11 dismissed = nits / intentional (ADR-033 `flach` default) / unreachable (`num_predict=0`, empty `content`) / born-that-way. Bugfixes, not trade-offs → D-entry, no ADR |
| D75 | One-shot setup: install + persistent PATH + robust Ollama/exec-policy | **`setup.ps1` now does the whole machine side end-to-end and idempotently, and puts everything on the PERSISTENT user PATH.** New `Add-ToUserPath` (writes the registry user PATH via `SetEnvironmentVariable(…, "User")`, append-only/dedup, also updates the process) persists uv's bin dir (`uv python dir --bin` = `~/.local/bin`) + the Ollama dir. `uv python install 3.12 **--default**` drops a global `python` shim (was plain `install`, so no global python). Ollama is now **fully auto**: robust winget (`--disable-interactivity` + accept flags, in try/catch) → **official-installer fallback** (`OllamaSetup.exe /VERYSILENT`) → PATH → service → pulls. **Bug fixed:** pulls **`bge-m3`** (the real RAG embedder) instead of the stale `nomic-embed-text`. Prefetch (STT+XTTS) is now **on by default** (`-SkipPrefetch` opt-out; `-Prefetch` kept as no-op). Two fresh-machine snags handled at the top: TLS 1.2 forced; ExecutionPolicy set to RemoteSigned (CurrentUser) + `Unblock-File`; new **`setup.bat`** one-click launcher runs the script with `-ExecutionPolicy Bypass`. End-summary surfaces the RAG-build commands when PDFs exist but `rag.db` is missing. parse-OK, suite **319 green** (scripts/docs only) | Tobi: setup should "really take care of everything — download, install, **uv + python on PATH**, startklar"; the colleague additionally snagged on **winget** and the **script-execution policy**. The old script only touched the *process* PATH (nothing persisted), never made a global `python`, and pulled the wrong embedder. Decisions: global `python` = uv-managed 3.12 (append PATH, don't displace an existing 3.12); prefetch default-on; Ollama full-auto with installer fallback; `setup.bat` to sidestep ExecutionPolicy. Not auto-run (legal/calibrated): Discord token, PDFs, RAG build, Bot A — listed as TODOs → **ADR 036** |
| D74 | Extract the delivery pipeline → `dmbot/voice/delivery.py` (composition) | **Pull the answer→audio turn-delivery machinery out of the 1188-line `DMCog` into a new `DeliveryPipeline` class (composition, not inheritance).** Moved (12 methods, **byte-identical** bodies, char-exact vs `HEAD`): `_synthesize`, `_speak`, `_speak_seamless`, `_begin_turn`, `_use_streaming`, `_handle_scene`, `_make_scene_confirm`, `_deliver_answer`, `_await_dice_scene`, `_deliver_streaming`, + the turn-running hooks `_auto_dm_turn`/`_run_and_deliver` (cog registers them on the runtime). The pipeline holds the shared `SessionRuntime` and reaches everything through it exactly as before. **Stays on `DMCog`:** the post-turn tail (`_post_deliver`/`_autosave_turn`/`_maybe_compact`/`_persist_recap` — a recap/session concern with its own tests), injected into the pipeline as a single `post_deliver` callback; all commands + `_deliver_intro_chunked` + lore helpers (now call `self._delivery._<m>`). `dmcog.py` 1188→**662**; `delivery.py` 575. Suite **319 green, 0 test edits**, ruff clean. _Non-byte effect: moved `log.*` lines' `%(name)s` column now `voice.delivery` (messages/formatting unchanged, filters key on content + `dmbot` prefix)._ | The largest file after ADR 029, and the cheap byte-exact lever (ADR 034) was spent — the remaining volume is cog methods that bind `self`. Tobi: extract the big delivery block so it isn't always loaded, **functionality + performance unchanged**. Chose **composition** over a mixin (explicit, isolated, sidesteps discord.py's `CogMeta` command-collection question) and **kept the recap tail on the cog** via one callback (cleaner concern split + zero test edits). Scene/lore sub-cog splits stay deferred (those are commands → mixin/sub-cog idiom) → **ADR 035** |
| D73 | Extract `_TurnTiming` → `dmbot/turn_timing.py` (ADR 034 continuation) | **Move the per-turn latency record `_TurnTiming` and its `_CTX_WARN_FRACTION` threshold out of `runtime.py` into a new `dmbot/turn_timing.py`.** Self-contained, state-free logging helper (threads `time.monotonic` timestamps, emits the one `[latency]` line + the `[ctx]` budget warning — no `SessionRuntime` state). `runtime.py` re-imports both (`# noqa: F401`) so `from ..runtime import _TurnTiming` (cog/dice/`test_autorecap`/`test_context_budget`) keeps working; the now-unused `from dataclasses import dataclass` dropped from `runtime`. `runtime.py` 610→**516**. Byte-exact body copy, **0 test edits**, ruff clean, suite **319 green**. _Sole non-byte effect: the `[latency]`/`[ctx]` lines now log under logger name `dmbot.turn_timing` instead of `dmbot.runtime` (message text/`[latency]` prefix unchanged; console INFO drops the name anyway, no test asserts it)._ | Next queued context-lean candidate (#1) from D70/D71's list — same motivation and mechanics (Tobi: extract only self-contained, state-free units; functionality unchanged). Re-export shim + byte-exact move, identical to D70/D71 → continues **ADR 034** (no new ADR) |
| D72 | Unify the twin delivery tail (`_post_deliver`) | **Extract the byte-identical end-of-turn tail shared by `_deliver_answer` (batch) and `_deliver_streaming` into one `_post_deliver` helper** (autosave → mic re-anchor → off-hot-path rolling auto-recap, D56). Both paths call it after their own `timing.end`/`log_line()`/`_await_dice_scene` step. Behaviour- and speed-identical (same calls/order/args; runs after `/speak`, off the hot path). The deliberately per-path bit is **not** merged: batch awaits dice/scene in a `finally` (button still posts if speak raised), streaming after the pipeline cleanup — that D40/D43 placement stays. Suite **319 green** | The two paths duplicated the tail (spotted in the `/simplify`-scope discussion). Did the extraction **by hand** (3 lines) rather than letting `/simplify` auto-edit the D40/D43-race-sensitive delivery code, per the agreed plan: only the twin paths, no functional/speed regression. Maintainability only — not a size win (the file stays large; that needs the deferred cog split) → D-entry, no ADR |
| D71 | Extract stream-assembler + finalize_answer (ADR 034 E4) | **Move the streaming sentence-assembler and the shared `finalize_answer` post-processing seam out of `orchestrator.py` into `dmbot/llm/stream_assembler.py`.** `StreamAssembler`/`StreamResult`/`_open_marker_index`/`_FIRST_CHUNK_MIN_CHARS` + `finalize_answer` are pure (no `DMBrain` state); `finalize_answer` is the batch+stream parity seam (ADR 017). `orchestrator` re-imports `StreamAssembler` + `finalize_answer` (`# noqa: F401`) and its now-unused `clean_narration`/`extract_*`/`dataclass`/`split_completed` imports were trimmed. Byte-exact slice migration; `orchestrator.py` 933→**783** (1175→783 over E1–E4); behaviour identical, **0 test edits**, suite **319 green** | Last self-contained, state-free block in `orchestrator` (Tobi: extract only the encapsulated methods so unrelated work doesn't load them, no functional change). The `DMBrain` body stays (shared per-channel state). Same re-export-shim + byte-exact-slice approach as D70 → **ADR 034** (E4) |
| D70 | Extract orchestrator pure helpers → `dmbot/llm/*` | **Move the pure top-band of `orchestrator.py` into three modules, keep re-export shims so nothing else changes.** `llm/sanitize.py` (spoken-answer sanitisers: `_ROLE_LABEL` + meta/preamble/trailing regexes, `_cut_at_labels`, `_strip_leading_label`, `_sanitize*`, `_trim_to_last_sentence`), `llm/echo_guard.py` (`is_echo`/`is_self_repetition` + `_*_NUDGE`/`_ROLL_DIRECTIVE`, ADR 018/W4), `llm/director_msgs.py` (`build_opening/intro_director_msg`, ADR 031). `orchestrator.py` re-imports them (`# noqa: F401`) so tests/`DMBrain`/`StreamAssembler`/cog keep importing from `orchestrator`. 1175→933 lines; behaviour identical (byte-exact slice migration, **0 test edits**, suite **319 green**). `finalize_answer`, `StreamAssembler`, the `DMBrain` body stay | Context-leanness for future agents (Tobi: extract big functions, no functional change). A 2-agent fan-out found `orchestrator.py` was already two-tier (pure helpers over stateful `DMBrain`); the pure band is the most-edited (sanitisers) yet state-free, so it extracts cheaply. DMBrain body NOT split (shared per-channel state). Deferred: E4 (`StreamAssembler`+`finalize_answer`) and the `dmcog.py` lore-cog/scene-mixin splits → **ADR 034** |
| D69 | `puffer` head-start delivery mode | **A third delivery value between `stream` and `nahtlos`: synthesise a few sentences ahead before the first plays, then keep synthesising in parallel** (Tobi's idea). `_deliver_streaming`'s `play_worker` now accumulates `DM_SPEECH_PREBUFFER` (default 3) WAVs before the first playback (`wav_q` maxsize bumped to the depth so the cushion holds during playback); `prebuffer == 1` is the old `stream`. A number in `!sprechmodus` sets the depth live (`!sprechmodus puffer 4`); new `runtime.prebuffer_count()`; buffered-unplayed WAVs cleaned in `finally`. +3 tests (**319 green**) | The buffer cushions CPU synth running slower than realtime, so gaps appear later: short turns become ~gapless with a modest start delay, and the long intro starts far sooner than `nahtlos` (though it still gaps later — synth can't keep up, and a small per-sentence bridge gap remains). A tunable middle point; gapless-everywhere still needs the GPU offload (ADR 002) → **ADR 033 Addendum** (no new ADR) |
| D68 | Global spoken-delivery mode (delivery × intonation) | **Two orthogonal, global, runtime-switchable axes applied to EVERY DM turn.** `DM_SPEECH_MODE` = `stream` (sentence-by-sentence, fast start, small gaps) \| `nahtlos` (synth all → one continuous track → one bridge call; gapless but waits for the full synthesis). `DM_SPEECH_PUNCT` = `flach` (`strip_speech_punctuation` — no XTTS babble, flatter) \| `intoniert` (`None` → wrapper keeps `.,!?;:-` for prosody, may babble). Wired `Config.speech_mode/_punct` → `runtime._speech_mode/_punct` + helpers `speech_transform()` / `deliver_seamless()`; the six turn-dispatch sites (`!dm`/`!redo`/`!start`/`!intro`/`_auto_dm_turn`/`_run_and_deliver`) read the mode instead of hardcoding the path, and `_deliver_streaming`/`_deliver_answer` pull transform/seamless from the runtime (no per-call args). `_intro_speak_seamless` → general `_speak_seamless(text, …, transform=…)` reused by `_deliver_answer` (nahtlos) and `!intro test` (fixed nahtlos+flach anchor). New `!sprechmodus [stream\|nahtlos] [flach\|intoniert]` (aliases `!sprache`/`!voicemode`) toggles live. Default `stream`+`flach`. +6 tests (**316 green**) | Tobi wants ONE spoken style for all output (better sound, no "Anfälle") and to A/B both axes live first; prefers nahtlos but wants to hear an intonated variant too. On CPU, instant-start and gapless are mutually exclusive (synth < realtime), so a switch + the GPU offload (ADR 002) as the real `nahtlos`-everywhere enabler, not a forced choice now. Default `flach` keeps the intro gibberish-free + is the consistent end-state (normal turns go punctuation-free by default; documented) → **ADR 033** |
| D67 | Shutdown voice-leave hang | **Bound discord.py's post-leave confirmation wait at exit.** The "Voice-Channel verlassen" teardown step hung up to ~30 s even though the bot left the channel instantly — root cause in discord.py, not our code: `VoiceClient.disconnect(force=True)` does the real leave first (closes voice ws+UDP socket), then `VoiceConnectionState.disconnect` (`voice_state.py`) **awaits a gateway `voice_state_update` confirmation for up to `VoiceClient.timeout`=30 s** (`wait=True` hardcoded). At exit that confirmation rarely arrives in time (the gateway is closed in the next step) and the wait only guards a disconnect→reconnect race → moot. New `dmbot/shutdown.py::disconnect_voice(vc, timeout=VOICE_DISCONNECT_TIMEOUT=2.0)` wraps `vc.disconnect(force=True)` in `asyncio.wait_for`; `DMBot.close()` calls it + logs `voice confirm wait abandoned` on timeout. Safe: the network leave precedes the wait, and discord.py catches the `CancelledError` and still runs its own `cleanup()`. The recv reader is **not** involved (its `stop()` is a non-joined daemon thread). `!leave` left as-is (the wait is meaningful mid-session). +2 tests (**311 green**) | Tobi: shutdown "dauert jetzt plötzlich wieder länger", voice-leave longest though it leaves immediately. Likely resurfaced with the discord.py voice-state rewrite. A bounded `wait_for` (not daemon-abandon — the blocking `await` lives inside discord.py's own coroutine, no daemon lever) truncates nothing real → **ADR 020 Addendum** (no new ADR) |
| D66 | `!intro` fast streamed mode + CPU root-cause | **Plain `!intro` = streamed, punctuation-free; `!intro test` stays the gapless one-track. Two modes to pick by feel.** Root cause of "lädt ewigkeiten" found in the live log: **XTTS runs on CPU** (`.env TTS_DEVICE=cpu`, deliberate — the 4070 VRAM is full with nemo+Whisper; cuda XTTS crashes the process & kills STT, ADR 002) → CPU synth is slower than realtime, and the gapless `!intro test` waits for the full ~3.7 min synth before any sound (`first_audio=378s`). Tobi chose **fast start with minor gaps** over gapless. Added an optional `speech_transform` to `_deliver_streaming`/`_deliver_answer`/`_speak` (applied to the spoken text only, chat text untouched, D38); plain `!intro` now passes `strip_speech_punctuation` so the **streamed** monologue is clean *and* starts after the first sentence — gaps remain because CPU synth can't keep up with playback. Suite **309 green** | The seamless track (D65) sounds great but, on CPU, the up-front full-synthesis wait is minutes. Can't have instant start AND gapless on CPU (synth < realtime). Bigger structural fix = GPU offload (5080/Tailscale → `TTS_DEVICE=cuda`, ADR 002) or shorten `DM_INTRO_NUM_PREDICT`; both offered, Tobi took the fast-stream mode now. Reuses the existing streaming pipeline (no new path) → refines **ADR 031** (addendum, no new ADR) |
| D65 | `!intro test` seamless chunked playback | **Join the per-sentence (punctuation-stripped) synth WAVs into ONE continuous track, play once.** `_deliver_intro_chunked` no longer speaks sentence-by-sentence (each its own blocking `_speak`/bridge call, with the synthesis sitting as dead air between chunks); a new helper `_intro_speak_seamless` synthesises every sentence, `concat_wavs`-joins them with a `_INTRO_SENTENCE_PAUSE_S` (0.2 s) silence between, and plays the single track in one layer-2-muted bridge call. New torch-free `wavio.concat_wavs` (pulled out of `xtts._concat_wavs`, which now delegates) so the cog reuses the join without importing XTTS. +3 tests (**309 green**) | Colleague: `!intro test` pronounced correctly but felt slow/choppy; Tobi pinned the bottleneck (per-sentence synthesis = dead time between chunks) and the goal (chunked synth to avoid XTTS punctuation babble, but it must **sound like one continuous text**). Hard constraint: XTTS synthesises at ~0.5× realtime, so instant-start AND gapless are mutually exclusive — streaming starts fast but must gap (synth can't keep up). Chose **gapless** (matches "sounds like full text") and accept the up-front full-synthesis wait; the fast-start streaming `!intro` and shortening (`DM_INTRO_NUM_PREDICT`) are the documented levers if the wait is too long → refines **ADR 031** (Addendum, no new ADR) |
| D64 | `!intro` Discord 2000-char crash | **Split long message `content` at the single send choke point.** `SessionRuntime._send_with_retry` now splits `content` > 2000 chars into several messages (any `view`/`embed` on the last) instead of one `channel.send`; the 5xx retry moved into a `_send_once` helper. New pure `split_for_discord` in `dmbot/tts/textsplit.py` — **verbatim** (drops nothing, unlike the TTS `chunk_text`), breaking at the latest paragraph/line/sentence/word boundary ≥ half-limit, hard-cutting only an unbroken over-limit run. Covers all three delivery paths (batch/streaming/`!intro test`). +4 tests (**306 green**) | Colleague's live run: `!intro test` raised `HTTPException 400 / 50035 ("Must be 2000 or fewer in length")` — the `!intro` monologue runs on a large length budget (`DM_INTRO_NUM_PREDICT` 800) and exceeds Discord's content cap. Pure correctness fix at the one send path every delivery route already shares; no trade-off → D-entry, no new ADR |
| D63 | Lean live docs vs. on-demand archive | **Split `progress.md` history + `CLAUDE.md` per-module detail into two on-demand `docs/` files** (`progress-archive.md`, `conventions.md`); the live files keep only current state; a **rotation rule** (CLAUDE.md `## Session ritual` + session-ritual skill) keeps them lean. progress.md 1637→678, CLAUDE.md 226→153; **nothing deleted** (verbatim move, 3 parallel read-only audits + 302-green suite); every still-open question stays live; 9 code-comment doc-anchors repointed to `docs/conventions.md` | The always-loaded continuity docs had outgrown their context budget — `## Last session` alone was ~756 lines a fresh agent never reads, so even trivial edits paid for the whole bulk (Tobi). Chose aggressive split + preserve-everything-in-`docs/` + keep-open-questions-live (all Tobi's calls) over trim-in-place / delete-history → **ADR 032** |

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) + **ADR 016** (anti-puppeting backstop, length cap, output cleanup) + **ADR 038** (single owner for the system-prompt assembly order) + **ADR 031** (`!intro` opening monologue) + **ADR 041** (`!intro` reliability: fixed low temperature + hardened director brief; add. 2 = deterministic weak-intro retry) + **ADR 042** (anti-repetition sampling `repeat_penalty`, with a deterministic carve-out for the roll router) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM, GPU offload) + `architecture.md` §3 (bridge contract) + **ADR 016** (TTS speech-only normalization) + **ADR 017** (streaming pipeline: sentence-chunked TTS, hold-back rules, history parity) + **ADR 033** (global spoken-delivery mode: stream vs nahtlos × flach vs intoniert, `!sprechmodus`) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) + **ADR 013** (pause control) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) + **ADR 012** (difficulty ladder, character store, marker grammar) + **ADR 014** (roll-detection router; timing now D40 — fires concurrent with playback) + **ADR 018** (router wins the dedupe; echo guard + roll-feedback directive on post-roll turns) + **ADR 040** (committed default party — party loading no longer bound to one voice-channel id) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) + **ADR 015** (sheet/state split, auto-combat damage) + **ADR 027** (rolling auto-recap / context handoff — recap is no longer wrap-up-only) + **ADR 037** (attack/Warp resolution → pure `rules/combat.py`) + **ADR 044** (NPC memory: per-NPC Erinnerungen, clamped attitude drift, faction gossip) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) + **ADR 019** (3-stage hybrid: scene tracker + rulebook-only RAG, bge-m3, W4 guard) + **ADR 021** (curated German lore compendium: `lore_imperium`/`lore_chaos` sources) + **ADR 025** (German rules glossary + 0.45 calibration) + **ADR 028** (RAG junk-shape filter) + **ADR 027** (configurable `num_ctx`, context-budget compaction) + **ADR 026** (auto scene transitions, `<<ORT>>`) + **ADR 043** (stateful scene cards: `<<ERLEDIGT>>` element flags, gated exits, dead-NPC render) |

---

## Phase status (Part 1 — MVP)

Legend: ⬜ open · 🔄 in progress · ✅ done (with proof)

> Abgeschlossene Phasen 0–8 (volle Checklisten + `VERIFY EVIDENCE`): **[docs/progress-archive.md](docs/progress-archive.md)**.

### ✅ Phase 0 — Foundation & setup — Gate met 2026-06-04
### ✅ Phase 1 — Bridge: Bot A `/speak` — Gate met 2026-06-04
### ✅ Phase 2 — DMbot scaffold: voice receive — Gate met 2026-06-04 (ADR 006)
### ✅ Phase 3 — VAD segmentation — Gate met 2026-06-04 (ADR 007)
### ✅ Phase 4 — STT (faster-whisper) — Gate met 2026-06-04
### ✅ Phase 5 — LLM wiring + DM persona — Gate met 2026-06-04 (ADR 002/005)
### ✅ Phase 6 — TTS + first full loop ⭐ (PLAYABLE) — Gate met 2026-06-04 (ADR 002)
### ✅ Phase 7 — Turn-taking & feedback protection layer 2 — Gate met 2026-06-05/06 (live, ADR 011)
### ✅ Phase 8 — Dice engine, system profile & turn-order buttons — Gate met 2026-06-07 (live, ADR 014/004/012)

### 🔄 Phase 9 — Memory (JSON + recaps)  (code-complete; live gate pending)
- [x] **`dmbot/memory/state.py`** — `WorldState` (+ `Combatant`/`Quest`): per-channel mutable state in
      `data/sessions/<id>/state.json` (wounds/conditions/inventory, NPCs, quests, location, time, recap).
      **Split** from the read-only `characters.json` (ADR 015): seeded once from the sheet, code-owned,
      **atomic** save (temp + `os.replace`) on every change. Pure deterministic advancement
      (`apply_damage` clamps at 0 + sets `kampfunfähig`; `heal` clamps at max + clears it; NPCs/quests/
      location) + `world_state_summary_de` (compact structured prompt block).
- [x] **Auto-combat damage** — engine `resolve_damage` (weapon + SL − soak, ≥0) + `describe_damage_de`;
      profile `combat` block (attack_skills, weapons table, default_damage, soak source) + accessors. On
      a successful Nahkampf/Fernkampf test the cog rolls the weapon's damage, computes soak (TB = tens of
      Tgh + armour), applies it to a target (auto if one candidate, else `discord_ui/target.py` dropdown),
      persists, and feeds it back so the DM narrates. `!npc add` registers enemies; `!damage`/`!heal` GM
      overrides. IM weapon values are approximate Core-Rulebook figures (tune live).
- [x] **Recap** — `dmbot/memory/recap.py` (German summariser prompt + history renderer) +
      `DMBrain.summarize`; `!wrap`/`!wrapup` generates → stores in `state.json` (+ `recap.md`) → `!join`
      re-injects it. `DMBrain.set_context` injects recap + state block into the system prompt (CLAUDE.md
      order: persona → recap → state → who-plays-whom → history); `reset` clears it.
- [x] **Unit tests** — `tests/test_memory_state.py` + `test_memory_recap.py` (seed, clamp/down/heal,
      save→load round-trip = the gate's code half, summary, engine damage math, profile accessors, recap
      + prompt injection). **Suite 102/102 green.** All changed modules import clean.
- **Gate:** HP change survives a restart; next session starts with a correct recap.
- **VERIFY EVIDENCE:** _Code + unit level (2026-06-09):_ persistence is unit-proven —
  `test_save_load_round_trip_survives` writes a damaged party (Seskin 11→6, an NPC, location, a quest, a
  recap), reloads, and asserts the reduced wounds + recap + quest survive; damage math
  (`weapon + SL − soak`, clamp ≥0) and the profile `combat` accessors are seeded-tested. _Live Discord
  gate (HP survives a real restart; recap shown + in-prompt on the next `!join`): **pending Tobi.**_

### 🔄 Phase 10 — adventure + rulebook into the DM + system-profile bootstrap
- [x] **10a (ADR 019, code-complete 2026-06-12, live-unverified):** adventure as 3-stage hybrid —
  summary + deterministic scene tracker (`data/adventures/chemical_burn/`, `!ort`/`!szenen`,
  `WorldState.scene_id`, `!npc add` statblocks) instead of vector RAG; **rulebook** ingestion
  (`dmbot/rag/ingest.py` → `sqlite-vec`, bge-m3, 1505 chunks) + threshold-gated retrieval into
  the prompt. The adventure is deliberately NOT in the vector store (spoilers).
- [x] **Lore source 1 (D46, 2026-06-12):** Starter-Set Setting Guide (ohne Villains-Kapitel) als
  `source=setting`, gruppiert als `## Weltwissen`; Patron-Sheet ins Kompendium. Wiki-Korpus
  (D28: Fandom + Lexicanum) bleibt der spätere Breiten-Ausbau.
- [x] **Lore source 2 (D48, 2026-06-13 → ADR 021):** kuratiertes deutsches Lore-Kompendium
  `data/lore/imperium.md` + `chaos.md` (grimdark, **committed** — eigene Formulierung freien
  40k-Wissens, keine Buch-Ableitung) als `source=lore_imperium`/
  `lore_chaos` → `## Weltwissen`. Schließt die Tobi-Anforderung „Menschen- + Chaos-Lore";
  Chaos-Kosmologie steht in keinem IM-Buch (verifiziert: „vier Chaosgötter" d=0.53 miss → jetzt
  d=0.43 hit). 24-Fragen-Offline-Probe grün; Tyraniden/Necrons/T'au bewusst draußen. Spieler-
  Zugang: **`!lore [topic]`** (D49, paged Embed) + `docs/lore.html` (Handout/Review).
- [ ] **Gate half 1 (live):** a concrete rule question answered correctly from the PDF
- [ ] Profile bootstrap: DM proposes a draft system profile from the rulebook → user confirms → saved
- VERIFY EVIDENCE: _(pending the circlejerk run)_
- **Decided approach (D28, 2026-06-08 — lore + RAG; full plan in this session's plan file):**
  - **→ superseded on the embedder:** D28 planned `nomic-embed-text`; Phase 10a (ADR 019) switched to
    **`bge-m3`** because nomic barely aligns German queries with the English rulebook (DE-query↔EN-text).
    The `nomic` mentions below record the original plan.
  - **Lore = RAG, never fact-fine-tuning** (golden rule #7). Fine-tuning only later as a **tone-LoRA**
    (style, on `logs/transcript.log`), Part-2 backlog — facts always stay in RAG.
  - **Both wiki sources** into one **`sqlite-vec`** DB, **text only (no images)**: **Fandom** (official
    XML dump, ~7.3k articles) + **Lexicanum** (MediaWiki API, throttled + cached, or an archive.org/
    WikiTeam dump, ~48.6k). Rulebook vs lore kept as separate `source`s so a rule question pulls the
    rulebook, a lore question the wiki. ≈ 0.8–1.3 GB total, ~40–100 min one-time embedding on the 4070.
  - **Pipeline mirrors `tools/pdf_to_md.py`:** new offline `tools/wiki_to_md.py` (`mwparserfromhell`,
    `mwclient`) → shared `dmbot/rag/{ingest,embed,store,retrieve}.py` (`nomic-embed-text` via Ollama
    `/api/embed`) → `!lore <frage>` (`discord_ui/lore.py`), then fold lore into DM turns behind
    `DM_RAG_LORE`; rule-retrieval into DM turns from the start.
  - **New deps to declare (§3, rule #9):** `sqlite-vec` (runtime), `mwparserfromhell` + `mwclient` (offline CLI).
- **Gate:** a concrete rule question answered correctly from the PDF; a fresh ruleset yields a working profile.
- **VERIFY EVIDENCE:** _(empty)_
- _Groundwork done:_ `tools/pdf_to_md.py` (`pymupdf4llm`) converts a rulebook PDF → Markdown
  (`data/pdfs/md/`, gitignored) as the ingestion front-end. The bought IM Core Rulebook is already
  converted. **Tool decision (Tobi 2026-06-07):** stay with `pymupdf4llm` until Phase 10 *or* until it
  causes problems; only then benchmark vs **Marker / Docling / MinerU** (ML+OCR, GPU — better on
  image/table-heavy pages) and, if switching, add a `--backend` flag rather than a second script. Note:
  IM tables can be **embedded images** (the Difficulty Table was) — `pymupdf4llm` does no real OCR, so
  table extraction is the thing to spot-check when building ingestion.

---

## Part 2 — Beyond the MVP (backlog)
- [ ] **XTTS as its own process/service** — XTTS v2 (`coqui-tts`) is wired in-process as an
      alternative TTS (`TTS_ENGINE=xtts`, picked speaker **Dionisio Schuyler**), but it drags the
      torch/torchaudio/torchcodec stack into the bot venv and is slow on CPU (~1.5× realtime).
      Move it behind a small local service (own venv, GPU once VRAM is freed) to keep DMbot lean
      and get near-realtime synthesis. Until then it runs on CPU. _Tobi chose Dionisio 2026-06-04
      after auditioning all 58 built-in speakers (samples in `voices/samples/`, pitch-ranked)._
- [ ] **Edit/review window before the DM speaks** — a toggleable human-in-the-loop step that
      briefly intercepts the DM response (and optionally the transcript) so a player can read /
      correct it before TTS. Off once trusted, so play flows. _Requested live by Pr0degie + Timo,
      2026-06-04; fits Phase 7 (turn-taking) — keep it switchable, not a permanent gate._
      _Groundwork done (2026-06-08, D27/ADR 013):_ the **pause control** (Esc + Discord ⏸ button →
      one `_paused` freeze) is the same human-in-the-loop gate; a review step can hook the same flag.
- [x] **Pause control (Esc + Discord ⏸ button)** — done 2026-06-08 (D27/ADR 013). Esc in the DMbot
      terminal *and* a Discord button flip one shared freeze (mute VAD/STT + block DM turns);
      animated `rich` box in the terminal, status embed in Discord. _Live test pending Tobi._
- [ ] GUI for the bot (session/turn/dice/sheets)
- [ ] LLM finetuning (LoRA on session logs)
- [ ] Streaming TTS (latency)
- [ ] Wake word / push-to-talk
- [ ] Per-NPC voices
- [ ] Automatic character progression
- [ ] Long-term vector memory

---

## Open questions / to clarify

**Vom Playtest-Fix-Runde (2026-06-16, D82–D84) — live-unverified:**
- **Klingt `!intro` jetzt zuverlässig wie der 14.06.-Lauf?** Party lädt channel-unabhängig (D82), die drei
  Chat-Tics (Meta-Auftakt, `"…"`-Umschlag, „Was tut ihr?"-Abwürgen) werden deterministisch gestrippt (D84),
  Temp auf 0.7 (D84). Ob die **Prosa-Reichheit** (atmosphärisch vs. formelhaft) jetzt passt, ist Modell-Sache —
  am Tisch prüfen; Stellschraube `DM_INTRO_TEMPERATURE` (0.3–0.8) bzw. Director-Brief-Wortlaut.
- **Aufräum-Pass `progress.md`:** „Current focus" (D75–D81) + „Next concrete step" (D61–D74) haben Vorsessions-
  Verlauf angesammelt, der eigentlich ins `docs/progress-archive.md` gehört (Rotation wurde übersprungen). Ein
  dedizierter Lean-Pass steht aus — bei Gelegenheit, kein Bot-Risiko.

**From the skill-tooling round (2026-06-15, D78):**
- **Golden-Rules-Konformitäts-Check noch offen** — die brauchbare Idee aus Pococks `review`-Skill (Standards-Achse als
  paralleler Sub-Agent) auf euren Fall gemünzt: ein kleiner Skill, der einen Diff gegen die Golden Rules + `docs/conventions.md`
  prüft (dice=code / Memory-Split / Feedback-Schutz / Two-Bot-Isolation). Heute prüft das nichts (`/code-review` sucht Bugs,
  nicht Regelbruch). Bewusst auf „später" geschoben.

**Cross-repo (Bot A):**
- **`!lore tts` reads each block twice** — verified NOT in DMbot (lore_pages/loop/synth/concat all
  1×, no custom `on_message`). If the live `debug.log` shows **one** `🔊 TTS … speaking` + **one**
  `/speak` per block, the doubling is **Bot A's playback** (separate `Pr0degie/musicbot` repo) → fix
  there (two-bot isolation). A Bot-A `/stop` would also enable true mid-block skip in the lore reader.
- **Weapon / stat-block tables don't retrieve** (calibration finding, ADR 025) — table-row chunking;
  a German weapon glossary under `data/rules_de/` (same pattern as `conditions.md`) is the likely fix.

**From the cog-split refactor (2026-06-13, D60 / ADR 029):**
- **Kosmetik, kein Verhaltens-Change:** ein Docstring-Beispiel in `dmbot/logsetup.py` (`_short_name`)
  nennt noch das gelöschte `dmbot.voice.commands` als Beispiel; und verschobene Log-Calls tragen ihren
  neuen Modulnamen in der opt-in `debug.log`-`%(name)s`-Spalte + WARNING-Konsolenzeilen
  (`runtime`/`voice.dmcog` statt `voice.commands`). Bewusst nicht angefasst (außerhalb des
  Refactor-Scopes); Log-Messages + Green-Chat/Transcript-Format unverändert. Bei Gelegenheit putzen.
- **Smoke-Test offen:** der Schnitt ist test-grün (263), aber live nur per Smoke-Test abzunehmen
  (`!join`→sprechen→`!dm`→Würfel→`!leave`) — siehe „Next concrete step".

**Deferred altitude debt from the code-review round (2026-06-13, D61 / ADR 030):**
These are the review's *altitude* findings — real, but the **system-agnostic generalisation** they
ask for is postponed to the **second-profile / Phase-10b** point (ADR 005's profile bootstrap). There
is no second system yet to generalise against, the changes are large + behaviour-risky, and the
project's stance (D1) is "IM is the first profile; generalise when the second arrives". Revisit each
when a second system is actually loaded:
- **Engine hardcodes IM arithmetic.** `engine.warp_charge_gain` (Success=Warp-Rating, Critical−WB,
  Fumble×2, Push+1d10) and `reverse_d100` + the `advantage` digit-reversal bake IM's p.163/p.189 rules
  into the generic engine. Move the charge-gain + advantage model into the profile alongside the
  resolution/degrees rules that are already data.
- **Per-marker pipeline grows linearly.** Each new director marker means a bespoke regex + dataclass
  in `marker.py`, a wider `finalize_answer` tuple, and a third/fourth parallel `_pending_*` dict in
  the orchestrator + a `take_pending_*`. One keyed marker structure (`{kind: [...]}`) would collapse
  the triplication; do it before the next marker, not after.
- **RAG corpus catalog is IM-/OCR-specific in code.** `retrieve._SOURCES` (source names + German
  group labels) and `_is_junk_hit` (IM-PDF OCR-noise regexes) live in the retriever. A second ruleset
  needs them in data/profile + ingest-time denoise, not hardcoded.

**From the lore work (2026-06-13):**
- **`!lore`-Antworten zu Rokarth sind englisch** — die `setting`-Quelle ist der englische
  Setting-Guide-Text; eine Rokarth-Frage liefert also rohe englische Chunks ins Spieler-Embed
  (Imperium/Chaos kommen deutsch aus dem Kompendium). Kosmetik; Optionen wären eine deutsche
  Rokarth-Sektion im Kompendium oder `setting` aus den `!lore`-Quellen nehmen. Erst mal
  beobachten, ob es die Runde stört.

**From the Phase-7 playtests (2026-06-06) — carry into Phase 8 / quality work:**
- **Latency grows with context** as history accumulates; the 20-turn cap helps but recaps (Phase 9)
  are the real fix. **Now observable (D35/D36):** the per-turn `[latency]` line shows
  `ctx=<prompt>/8192 gen=<eval>`, and a WARNING fires once the prompt passes ~85% of `num_ctx` — so
  the cap-creep is no longer silent. Capture the live baseline before the streaming work; don't raise
  `num_ctx` (KV-cache VRAM) — trim history/recap/state if the warning shows.

**Loose ends / housekeeping (from the Phase 3 session):**
- **Intermittent voice-connect `TimeoutError` on `!join`** (seen once, ~18:45): the discord.py
  voice handshake occasionally times out; the command errored but a retry joined fine. Benign
  so far — watch it; if it recurs, look at the connect timeout / a clean error message in
  `voice/commands.py` rather than the raw traceback.
- Logging now also writes `logs/dmbot.log` (UTF-8, gitignored) — handy for inspecting a run
  after the window closes.
- Continuous silence injection runs silero on every silent user ~50×/s (cheap, ~1–2 %/core
  each); fine for a small table, revisit only if many idle users ever cost CPU.

**From the streaming/robustness session (2026-06-10) — open, carry forward:**
- **Pending live validation (Tobi tests 2026-06-11).** What's already confirmed live: streaming
  (`first_audio≈3.2s`) + the Phase-9 recap. Still open: HP-survives-restart (+ auto-combat),
  re-confirm the D42 tuning (no empty read-aloud, no dice loop), crash-restore (D41), router timing
  (D40), first_audio before/after. The prioritised checklist + exact sequence live in **`## Next
  concrete step`**.
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

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
