# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## State header

_The only mandatory session-start read from this file (CLAUDE.md ritual). Everything below
is on-demand._

- **Phase:** 11 (Claude-Backend, ADR 061) **code-komplett**, Live-Gate offen; 9 + 10 code-komplett,
  0–8 live-validiert. Phase 10b (Profil-Bootstrap) bleibt zurückgestellt.
- **Project priority:** der isolierte Claude-Abend — nur das Modell ist die Variable. Plan:
  [claude-backend.md](docs/plans/claude-backend.md), Zielbild: [target-vision.md](docs/plans/target-vision.md).
- **Newest round:** D128 + D129 / **ADR 064** (2026-10-30) — Würfel-Wurfanimation. Der Probe-Post zeigt den
  Zielwürfel „≤Ziel“ groß, der Klick ein Wurf-GIF, dann das Ergebnisbild; Engine und DM warten nicht darauf.
  Die 75 Flug-GIFs liegen einmal in `#botcommands` (`DM_DICE_ASSET_CHANNEL`), der Klick zeigt nur auf den Link.
  **1344 Tests grün, `dm-eval` Exit 0.** Am Tisch gesehen: Zielwürfel, GIF, Ergebnis; ADR 064 noch nicht live.
  31.10.: Zahlen auf allen W20-Seitenflächen (Flug-GIFs gehen beim nächsten Start einmal neu hoch); D130: jeder
  DMbot-Befehl tritt vorher dem Voice-Kanal bei (`DM_AUTO_JOIN`), sanftes Plopp beim Login („logged in as …“).
  D131: `!test` ohne „für“ — ohne Name die eigene Figur, Name am Ende reicht, eindeutige Vornamen gelten.
- **Davor (2026-10-25):** D123/D124 (ADR 062, improvisierte NSCs anwesend), D125 (XTTS-Sperre + `gpu_health`),
  D126 (ADR 063, Schicksalspunkte), D127 (Würfel-Thumbnails) — alle code-komplett, Details im Archiv/Log.
- **Next concrete step:** Bot neu starten und im Log `dice assets: 75/75 throw GIFs ready` prüfen; ein paar
  `!test Wahrnehmung für Tobi` — GIF in ~0,5 s? spielt es einmal und landet mit dem Ergebnisbild? Dann der
  fünfte Lauf (Sandbox leeren, Bot A starten!) mit der Prüfliste im Abschnitt „Next concrete step“ unten.
- **Open live gates:** **eins** — das Live-Gate von Phase 11. Die 17 alten sind seit 2026-10-06
  geparkt (ADR 061, im [Live-Run-Skript](docs/live-run-script.md) markiert) und werden nach dem
  Abend neu gesichtet; sie zählen nicht gegen die WIP-Grenze.

## Current focus

**Phase 11 — ein zweites LLM-Backend hinter einer Naht (D116/D117, ADR 061), code-komplett.** Der DM kann statt Mistral Nemo Claude sprechen lassen (Opus erzählt, Haiku übernimmt die Klassifikatoren), über Tobis eigenes Abo und ohne API-Key; fällt Claude aus, antwortet Nemo weiter und im Chat steht genau eine ⚠-Zeile. Mit `DM_LLM_BACKEND=ollama` (Default) ist es der Bot von vorher.
Belegt: 1192 Tests grün (1090 alte unverändert, 102 neue), `dm-eval` Exit 0, Lint sauber. Live auf dieser Maschine: der Boot-Preflight meldet Opus und Haiku in 2,9 s als erreichbar und einen falschen Modellnamen mit Knopfnamen; ein Haiku-Smoke lieferte Text, Schema-Antwort, Stream mit Verlauf und einen sauberen Schnitt an der Ausgabegrenze.
Ein unabhängiger Verifier hat den ganzen Diff gegen ADR 061 und die Golden Rules gelesen. Sieben Funde sind behoben, acht bewusst zurückgestellt; beides steht im ADR, letzter Nachtrag.
Nicht verifiziert: Opus mit vollem Systemprompt, ein ganzer Zug mit Stimme, alles am Tisch. Das ist der Abend.

_Ältere Current-focus-Blöcke: siehe [docs/progress-archive.md](docs/progress-archive.md), `## Current focus (Verlauf)`._

## Last session

**Würfel-Wurfanimation (2026-10-30, D128/D129, ADR 064).** Eine Probe zeigt jetzt vor dem Klick groß, was man
erreichen muss („≤37“, Steel), nach dem Klick fliegt der Würfel (Flipper-Physik aus Tobis Prototyp, 25 Bahnen) und
landet auf dem Wurf; das Ergebnis steht groß mit Text. Engine und DM-Zeile laufen sofort, nur die zwei Edits warten.
Am Tisch nachgeschärft: Zielzahl größer, GIF ohne Startbild, 32 Farben, Flug 60 ms (604 → 304 KB, 7,2 → 5,4 s),
Ergebnis 1 s nach der Landung. Gemessen blieben ~1,2 s Upload im Edit → ADR 064: 75 Flug-GIFs einmal in
`#botcommands`, der Klick zeigt nur auf den Link, das Ergebnisbild bleibt ein echter Anhang (startet früher).
1333 Tests grün (+34), `dm-eval` Exit 0, `render()` byte-identisch. Lesson: Discord-Seite zuerst messen.
31.10.: Zahlen auf allen Seitenflächen wie bei einem echten W20 (Tobis Variante B, nach außen gedreht, fest pro
Wert); `FRAME_SET_VERSION` 3 → Pool neu, die Flug-GIFs gehen beim nächsten Start einmal neu nach `#botcommands`.

**Test-Leck geschlossen (2026-10-25 nachts).** `tests/test_turn_boundary.py` schrieb bei jedem Suite-Lauf zwei
Szenen-Events in das echte `data/sessions/7/history.jsonl` (seit 2026-08-23, 124 Zeilen; zwei Tests mit
`_autosave=True`). Der Test-Runtime leitet `session_file` jetzt nach `tmp_path` um und schlägt ohne ihn fehl;
der Ordner ist gelöscht. Ein Datei-Schnappschuss um die volle Suite zeigt: nichts unter `data/`/`logs/`
ändert sich mehr. Die zwei `session_fixture`-Chunks im `rag.db` (älteres, schon behobenes Leck vom Juli) sind samt
Vektor-, FTS- und `meta`-Zeile gelöscht; `integrity_check` ok, `dm-sync` zeigt nur die sieben Wissensquellen. Lesson `isolation-must-enumerate-every-artifact`
ergänzt. Sandbox für Lauf 5 geprüft: leer.

_Ältere `## Last session`-Einträge: siehe [docs/progress-archive.md](docs/progress-archive.md), `## Last session (Verlauf)`._

## Next concrete step

**Erst die Würfel-Ablage live, dann der fünfte Lauf.** Bot neu starten (Bot A auch — am 30.10. lief er nicht,
der DM blieb stumm), im Log `dice assets: 75/75 throw GIFs ready in #botcommands` und beim Würfeln
`🎲 throw gif (stored): in Discord … ms` ansehen: Ziel ~0,5 s bis zum GIF; spielt Discord das GIF einmal und
trifft das Ergebnisbild die Landung? Dann Lauf 5 (Sandbox leeren) und prüfen: Würfelbild an jedem Ergebnis (auch
nach „🙏 Neu würfeln“), `👥 anwesend in …` für improvisierte Gegner, Zielauswahl nur Anwesende, kein Psi-Doppelwurf,
kein „Wechseln“ nach Auto-Wechsel, „Was kann ich?“ aus dem Bogen, Schicksal-Buttons nach Fehlschlägen. Danach
`characters.json` zurück (`git checkout`), wenn Timo/Vinnie wieder mitspielen.

## Decision log

Lives in [docs/decision-log.md](docs/decision-log.md) (moved 2026-10-25, `D##` numbers unchanged).
Grep one row (`grep -n "| D87 |" docs/decision-log.md`); a new decision gets the next `D##` there.

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) + **ADR 060** (the STT hallucination blocklist: content, not confidence — D114) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) + **ADR 016** (anti-puppeting backstop, length cap, output cleanup) + **ADR 038** (single owner for the system-prompt assembly order) + **ADR 031** (`!intro` opening monologue) + **ADR 041** (`!intro` reliability: fixed low temperature + hardened director brief; add. 2 = deterministic weak-intro retry) + **ADR 042** (anti-repetition sampling `repeat_penalty`, with a deterministic carve-out for the roll router) + **ADR 045** (deterministic consistency guard: dead/absent NPC speech → regenerate once, fail-open; streaming logs only) + **ADR 060** (deterministic guards on the spoken text: two signals must coincide, whole sentences only, a quote is sanctuary, negative cases written first — the shape D112/D113/D114 all follow) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM, GPU offload) + `architecture.md` §3 (bridge contract) + **ADR 016** (TTS speech-only normalization) + **ADR 017** (streaming pipeline: sentence-chunked TTS, hold-back rules, history parity) + **ADR 033** (global spoken-delivery mode: stream vs nahtlos × flach vs intoniert, `!sprechmodus`) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) + **ADR 013** (pause control) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) + **ADR 012** (difficulty ladder, character store, marker grammar) + **ADR 014** (roll-detection router; timing now D40 — fires concurrent with playback) + **ADR 018** (router wins the dedupe; echo guard + roll-feedback directive on post-roll turns) + **ADR 040** (committed default party — party loading no longer bound to one voice-channel id) + **ADR 063** (Fate: spend to reroll a failed test, recovered on `!join`) + **ADR 064** (throw GIFs stored once in Discord, clicks point at them) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) + **ADR 015** (sheet/state split, auto-combat damage) + **ADR 027** (rolling auto-recap / context handoff — recap is no longer wrap-up-only) + **ADR 037** (attack/Warp resolution → pure `rules/combat.py`) + **ADR 044** (NPC memory: per-NPC Erinnerungen, clamped attitude drift, faction gossip) + **ADR 049** (NPC agendas: human-set goals, one clamped offscreen step per scene change riding the ADR-044 extractor) + **ADR 050** (Chekhov list: wrap-up-only thread extraction riding the ADR-044 call, code-owned cap/dedupe/status, top-3 callback offer) + **ADR 062** (improvised NPCs join the scene: presence classifier, `Combatant.scene`, one "present" for prompt + target picker) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) + **ADR 019** (3-stage hybrid: scene tracker + rulebook-only RAG, bge-m3, W4 guard) + **ADR 021** (curated German lore compendium: `lore_imperium`/`lore_chaos` sources) + **ADR 025** (German rules glossary + 0.45 calibration) + **ADR 028** (RAG junk-shape filter) + **ADR 027** (configurable `num_ctx`, context-budget compaction) + **ADR 026** (auto scene transitions, `<<ORT>>`) + **ADR 043** (stateful scene cards: `<<ERLEDIGT>>` element flags, gated exits, dead-NPC render) + **ADR 047** (consequence clocks: `<<UHR>>` ticks, +1/turn clamp, full-clock `[Regie]` injection, clock panel) + **ADR 048** (in-game time: minutes counter, `<<ZEIT>>` advance clamped to first-marker/+12h, deadlines with one-shot expiry `[Regie]`, day phases, shared pressure panel) + **ADR 054** (campaign memory: played-session ingest per scene, hybrid KNN+FTS session retrieval, state wins over memory) + **ADR 055** (debug-run sandbox: `.debug` archives → `session_debug` source, gate G10) + **ADR 056** (the sandbox's other half: `.debug` twins for state/history/chekhov/recap, foreign scene pointer re-seeds) + **ADR 057** (scene advancement belongs to code: exit classifier + flag gate, automatic with undo; the inline `<<ORT>>` marker demoted to a fallback) + **ADR 058** (post-turn fact classifier: narrated commitments become hard facts, retraction manual via `!fakt`) + **ADR 059** (the adventure ships start time, deadlines and clocks; time advances per turn) |
| 11 — Claude backend | **ADR 061** (client seam, tier rule, failover; read the build amendment first) + ADR 002 + ADR 042 (sampling defaults) + ADR 046 (replay eval) + `docs/plans/claude-backend.md` |

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


**Aus der Würfel-Animation (2026-10-30) — offen:**
- **Würfel dreht sich nicht:** Tobis Prototyp integriert `angle` nie (`w` wird berechnet, `angle += w*dt`
  fehlt); wörtlich übernommen. Eine Zeile, ändert nur das Bild, nicht die Seed-Auswahl — Tobi fragen.
- **GIF-Cache wächst** (`data/dice/anim/s*_r*.gif`, ~300 KB je Ergebnis/Bahn/Farbe, ohne Aufräumen).

**Aus den Opus-Läufen (2026-10-25) — offen:**
- **Größeres `CLAUDE_NUM_CTX`** (z. B. 65536) als eigener Versuch nach dem Abend: Gedächtnis vs. Verbrauch und Antwortzeit. Heute bewusst gleich wie Nemo.
- **`cache=0` in fast jedem Opus-Zug** — der Prompt-Cache greift kaum (Zustand und RAG ändern den Prompt jeden Zug). Kostet Verbrauch; prüfen, ob die stabile Persona vorn gecacht werden kann.
- **Recap auf Nemo wird mit der Zeit auch gekappt** (`num_predict` 400, kumulativ) und verliert dann ebenso die neuesten Ereignisse. Auf Claude behoben, auf Nemo latent.
- **`DM_STREAMING=0` auf Claude** hat keine Sprechgrenze unter ~1244 Tokens (ADR 061). Nicht die Abend-Konfiguration.

**Aus dem Review der Bau-Runde (2026-08-23) — nicht behoben, bewusst vertagt:**
- **Gegenrichtung der Fakten** — der Klassifikator kennt nur Hinzufügen; Rücknahme läuft über
  `!fakt weg` von Hand. ADR 058 ist auf den gebauten Umfang korrigiert, die Erweiterung wäre additiv.
- **`!ortmodus frei` wirkt nur noch auf den Marker**, nicht auf den Klassifikator-Pfad. Beobachten.
- **Discord-Last des Panels** — mehrere Edits pro Zug; ein 429 verschwindet in einer Warnung. Messen.
- **Drei Beweger auf einem Szenenzeiger** — beim Debriefing die `scene_move`-Auslöser auszählen.

**Aus der Debug-Lauf-Triage (2026-08-23, D107) — bewusst offen gelassen:**
- **Deterministischer Meta-Satz-Filter** — ✅ erledigt in D112, satzweise und quotensicher.
  Offen bleibt nur die Wirkung im Stream: der Filter läuft auch auf der inkrementellen Naht, aber
  ein Satz, der beim Sprechen noch unvollständig ist, kann per Konstruktion nicht erkannt werden.
- **Halluzinations-Blockliste für STT** — ✅ D114, kuratiert im Code (kein Knopf, der still
  veraltet). Offen bleibt die Pflege: was am nächsten Abend durchrutscht, gehört hinein; die
  `🚫 Whisper-Halluzination verworfen`-Zeile zeigt umgekehrt, was sie schon fängt.
- **Stall-Detektor** — nach N Zügen ohne Fortschritt selbst weiterschieben. Aufgeschoben, weil drei
  Beweger des Szenenzeigers im ersten Lauf schwer auseinanderzuhalten wären (ADR 057).
- **Sprechmodus-Default** — bleibt `stream`+`flach`, bis die drei Modi am Tisch verglichen sind.

**Von der Replay-Eval-Runde (2026-07-03, D93 / ADR 046):**
- **Live-Modellvergleich (Nemo vs. Mistral Small auf Timos Box)** — braucht dieses Harness mit
  echten LLM-Calls; nicht vor dem Tuning-Live-Run starten, sonst vergleicht man ein untuned Setup.
- **Würfel-RNG-Replay aufgeschoben** — lohnt erst, wenn ein Refactor den Roll→Damage-Pfad anfasst;
  die Fixed-Seed-Engine-Tests decken ihn heute dicht ab (ADR 046).
- **Erstes Live-Golden fehlt noch** — die eingecheckten Goldens sind synthetisch; das echte kommt
  aus dem rotierten Journal des nächsten Live-Runs (siehe `## Next concrete step`).

- **`!intro`-Prosa-Reichheit** (Playtest-Fix-Runde 2026-06-16, D82–D84) — die drei Chat-Tics sind
  deterministisch gestrippt, ob die Prosa atmosphärisch statt formelhaft klingt, ist Modell-Sache und
  am Tisch zu prüfen (`DM_INTRO_TEMPERATURE`). Volltext: `docs/progress-archive.md`.

**From the skill-tooling round (2026-06-15, D78):**
- **Golden-Rules-Konformitäts-Check noch offen** — ein Skill, der einen Diff gegen die Golden
  Rules + `docs/conventions.md` prüft (`/code-review` sucht Bugs, nicht Regelbruch). Bewusst geparkt.

**Cross-repo (Bot A):**
- **`!lore tts` reads each block twice** — verified NOT in DMbot (lore_pages/loop/synth/concat all
  1×, no custom `on_message`). If the live `debug.log` shows **one** `🔊 TTS … speaking` + **one**
  `/speak` per block, the doubling is **Bot A's playback** (separate `Pr0degie/musicbot` repo) → fix
  there (two-bot isolation). A Bot-A `/stop` would also enable true mid-block skip in the lore reader.
- **Weapon / stat-block tables don't retrieve** (calibration finding, ADR 025) — table-row chunking;
  a German weapon glossary under `data/rules_de/` (same pattern as `conditions.md`) is the likely fix.

**From the cog-split refactor (2026-06-13, D60 / ADR 029):**
- **Smoke-Test offen:** der Schnitt ist test-grün (263), aber live nur per Smoke-Test abzunehmen
  (`!join`→sprechen→`!dm`→Würfel→`!leave`) — siehe „Next concrete step".

**Deferred altitude debt (2026-06-13, D61 / ADR 030) — geparkt bis Phase 10b (zweites System):**
- Engine-IM-Arithmetik (`warp_charge_gain`, `reverse_d100`) + IM-/OCR-RAG-Katalog
  (`retrieve._SOURCES`, `_is_junk_hit`) wandern dann in Profil/Daten. Volltext im Archiv.

**From the lore work (2026-06-13):**
- **`!lore`-Antworten zu Rokarth sind englisch** — die `setting`-Quelle ist der englische
  Setting-Guide (Imperium/Chaos kommen deutsch aus dem Kompendium). Kosmetik; Fix wäre eine
  deutsche Rokarth-Sektion oder `setting` aus den `!lore`-Quellen nehmen. Erst mal beobachten.

**Phase-7-Playtests (2026-06-06):** Latenz wächst mit dem Kontext (`[latency]`-Zeile, 85-%-
Warnung); Auto-Recap ist der Fix, die Baseline nimmt der Live-Run. Volltext im Archiv.

**Loose ends (Phase 3):** `!join`-Voice-`TimeoutError` einmal gesehen (Retry half — nur beobachten);
Silero läuft auf Stille bei ~1–2 %/Core (fein für einen kleinen Tisch). Volltext im Archiv.

**Streaming/Robustheit (2026-06-10):** die damalige Live-Checkliste ist im Live-Run-Skript
aufgegangen; als Watch-Items bleiben Meta-Ramble (nemos Ceiling) und first_audio/`tts=`-Lücken
(XTTS-Tempo) — beide stehen dort unter „Nebenbei“. Der `gen=`-stale-Caveat nach einem
Stop-Abbruch ist im Skript (Akt 1) notiert; Volltext im Archiv.

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
