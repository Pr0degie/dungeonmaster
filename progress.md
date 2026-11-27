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
- **Newest round:** 27.11.: zweiter Claude-Lauf ausgewertet, fünf Befunde gebaut — D151 genanntes Ziel, D152 ein
  Erzählzug zur Zeit (ADR 067), D153 Psi-Schaden, D154 Bogen-Antwort, D155 Schaden nur um Rüstung. Danach Runde 1
  der Zerlegung ([Plan](docs/plans/split-state-dicecog-orchestrator.md)): `memory/state.py` 1457 → 868 Zeilen
  (`records.py`, `state_text.py`, ADR 034 Nachtrag), und Runde 2: `orchestrator.py` 1421 → 608 Zeilen (Paket
  `dmbot/brain/`: `channel.py` + vier Mixins, ADR 065 Nachtrag). Beide nur verschoben. „Last session“.
- **Suite:** `uv run dm-check` grün — 1647 Tests, 4 xfail; ruff (F) sauber; `dm-eval` Exit 0.
- **Live-unverifiziert:** D151–D155 (Prüfpunkte W7, F11, W8, W4 im Beipackzettel
  [phase-11-abend.md](docs/phase-11-abend.md), „Nächster Lauf“). Aus D140–D147 noch offen: F2 (nur die
  Hängeschleife belegt), F4, F6, F7, F9, F10, W2, W3, W6 (Schicksal nach Fehlschlag). Dazu D139 (Pause statt
  Nemo — nie gespielt), D137, `DMBrain`-Befunde Nr. 1–4/9/12, D134. Die Zerlegungen von `state.py` und
  `orchestrator.py` (Prüfung im Plan, „Live-unverified after each round“).
- **Next concrete step:** Bot neu starten (der Stand von 16:00 am 27.11. kennt weder D151–D155 noch die beiden
  Zerlegungen), dann ein kurzer
  Lauf für F11, W4, W7, W8 und die offenen Punkte, danach die Pause-Probe (D139). Abschnitt „Next concrete
  step“.
- **Open live gates:** **eins** — das Live-Gate von Phase 11. Die 17 alten sind seit 2026-10-06
  geparkt (ADR 061, im [Live-Run-Skript](docs/live-run-script.md) markiert) und werden nach dem
  Abend neu gesichtet.

## Current focus

**Phase 11 — Claude als Erzähler (ADR 061), code-komplett; Live-Gate offen.** Opus erzählt, Haiku klassifiziert,
über Tobis Abo; fällt Claude aus, pausiert das Spiel (D139). Zwei Läufe gespielt (14.11., 27.11.); die Runden
D151–D155 aus dem zweiten und der Rest der Folgerunde D140–D147 warten auf ihren Lauf (Prüfliste im
Beipackzettel), die Pause-Probe steht noch aus.

_Ältere Current-focus-Blöcke: siehe [docs/progress-archive.md](docs/progress-archive.md), `## Current focus (Verlauf)`._

## Last session

**Zweiter Claude-Lauf ausgewertet, fünf Befunde daraus gebaut (2026-11-27, D151–D155).** Drei Spieler
haben 44 Minuten gespielt (18 Erzählantworten, `!wrap`). Der Lauf zeigte vor allem, dass zwei Erzählzüge
gleichzeitig laufen und ineinander gesprochen werden. Das und vier weitere Punkte sind behoben; am Tisch
geprüft ist davon nichts, der Bot braucht einen Neustart. `uv run dm-check` grün (1647 Tests, 4 xfail).
Belege des Laufs: [phase-11-abend.md](docs/phase-11-abend.md), „Ergebnis vom 27.11.2026“.
- **D152 — ein Erzählzug zur Zeit** (ADR 067): nie zwei Erzählanfragen gleichzeitig, jede Antwort wird ganz
  gesprochen, mehrere Proben eines Zugs ergeben eine Erzählung (höchstens `DM_ROLL_BATCH_WAIT_SECONDS` = 30 s
  Wartezeit). `[latency]` zeigt `queued=` und `spoke_after=`; `!wrap` schreibt seinen Recap ins Log.
- **D151 — ein Angriff trifft das genannte Ziel:** nennt die eigene Zeile des Angreifers genau einen
  anwesenden NSC, entfällt die Zielauswahl; bei Verneinung, Mehrdeutigkeit oder einem Mitspieler kommt sie.
- **D153 — Psi-Schaden wird gebucht** (ADR 022, Nachtrag): Smite, Force Bolt und Bio-Lightning ziehen Wunden
  ab, Ziel aus der Ansage oder der Auswahl mit „Niemand davon“. Nova bleibt Erzählung.
- **D154 — „Was kann ich?“ aus dem Bogen:** der eigene Bogen als Textnachricht, die Erzählung bleibt; Zeilen
  ohne Buchstaben oder Ziffern gehen nicht mehr an den DM. Persona unverändert.
- **D155 — Schaden nach Regelbuch** (ADR 015, Nachtrag): nur Rüstung mindert Schaden, der Widerstandsbonus
  nicht mehr. Jeder Treffer ist 2–4 Wunden härter. Tobis Entscheidung.
- **Arbeitsweise:** Psi-Schaden, Bogen-Antwort und der Beipackzettel kamen von drei parallelen Agenten, zwei
  davon auf eigenen Zweigen; vier `/code-review`-Durchgänge (7, 8 und 9 Funde, alle bis auf zwei notierte
  behoben). D155 lief ohne Review. Belegt im Lauf: F1, F3, F5 (Cache), F8, W1, W5, W6 (erster Teil), N1, N2, N5.
- **Plan für die drei größten Dateien** (kein Code bewegt):
  [split-state-dicecog-orchestrator.md](docs/plans/split-state-dicecog-orchestrator.md) — Zielmodule,
  Methodenzuordnung, Schrittfolge und Prüfung je Schritt für `memory/state.py`, `orchestrator.py` und
  `voice/dicecog.py`. Reihenfolge: `state.py` zuerst, `dicecog.py` erst nach dem nächsten Lauf. Tobi hat alle
  sechs Entscheidungen wie empfohlen getroffen; siehe „Next concrete step“. **Am selben Tag geändert
  (Entscheidung 7 im Plan): `dicecog.py` läuft vor dem nächsten Lauf**, alles wird danach in einem Lauf geprüft.
- **Zerlegung Runde 1 — `memory/state.py`** (ADR 034, Nachtrag): zwei Umzüge, je ein Commit, Byte für Byte —
  die deutschen Prompt-/Panel-Zeilen nach `memory/state_text.py`, die Datensätze (`Combatant`, `Clock`, `Fact`,
  `Quest`, …) nach `memory/records.py`; `state.py` exportiert alles weiter, `WorldState` bleibt ganz. 1457 → 868
  Zeilen, null Test-Änderungen, `state.json` byte-gleich zur Basis. Ergebnistabelle im Plan. Einziger sichtbarer
  Unterschied: zwei NSC-Logzeilen tragen jetzt `dmbot.memory.records`.
- **Zerlegung Runde 2 — `orchestrator.py`** (ADR 065, Nachtrag): fünf Umzüge, je ein Commit, Byte für Byte, in
  das neue Paket `dmbot/brain/` — die Datensätze (`ChannelSession`, `TurnAnswer`, `_Turn`, …) nach `channel.py`
  (von `orchestrator.py` weiter exportiert), dann vier Mixins: `pending.py` (was die Cogs holen und ablegen),
  `opening.py` (`!start`/`!intro`), `side_calls.py` (Klassifizierer, Recap, Regelantwort), `generation.py` (eine
  Antwort durch die Wächter). 1421 → 608 Zeilen, null Test-Änderungen, alle 74 `DMBrain`-Attribute mit gleicher
  Signatur und gleichem Quelltext erreichbar. `_build_request` und `_log_classifier` bleiben wegen zweier
  Bindungen (`text_replay`, Logger-Name im Test) in `orchestrator.py`. Ergebnistabelle im Plan. Einziger
  sichtbarer Unterschied: die Zeilen des Erzählpfads (`🪵 LLM roh`, Echo-Wächter, `[consistency]`, `✂`) tragen
  im `debug.log` jetzt `dmbot.brain.generation`, zwei Zeilen `dmbot.brain.side_calls`.

**Arbeitsablauf entschlackt (2026-11-15, D150).** Am Tisch ändert sich nichts. Ein Prüfbefehl ersetzt die drei
Einzelprüfungen, der Commit-Hook prüft nach einem grünen Lauf nicht noch einmal, die WIP-Grenze ist weg.
`uv run dm-check` grün (pytest 1561 grün, 4 xfail; ruff (F) sauber; `dm-eval` Exit 0).
- **`uv run dm-check`** (`dmbot/tools/dm_check.py`): ruff (F), Suite, `dm-eval`, ein Gesamtergebnis. Grün → der
  git-Tree-Hash von `dmbot/` `tests/` `data/systems/` im Arbeitsbaum (inkl. ungetrackter Dateien) landet in
  `.dm-check.stamp`; der pre-commit-Hook lässt den Commit ohne Lauf durch, solange der Hash passt. Ein roter Lauf löscht
  den Merkzettel vorher. `tools/hooks/test-on-change.sh` entfällt; `tools/cleanup_15aug.py` bleibt (zwei Doku-Verweise).
- **`characters.local.json`** (git-ignoriert) gewinnt im Lader über die getrackte `characters.json`; die lokale
  Party-Änderung des Stamm-Channels (ohne Gellicus) liegt jetzt dort, die getrackte Datei ist wieder sauber.
- **Werkzeuge:** Freigabeliste in `.claude/settings.json`; Subagent `log-reader` (Opus, nur lesen) für die Lesearbeit
  in `playtest-triage`; Skill `adopt-workflow` (angelegt, nie ausgeführt). CLAUDE.md: Regeln für den Abschlussbericht
  und „Doku im selben Commit“, Sprachkonvention und Bot-A-Abschnitt in die Golden Rules #5/#8 gefaltet.
  `docs/conventions.md`: Regel für Review-Befunde (höchstens ein Review pro Runde, am Ende).

_Die fünf Runden vom 27.11. im Einzelnen (D151–D155, Auswertung) und das Log-Archiv D149: [Archiv](docs/progress-archive.md), „rotiert (2026-11-27, Lauf und D151–D155)“._
_Nacharbeiten D148 (ADR 066 B verworfen): [Archiv](docs/progress-archive.md), „rotiert (2026-11-15, Arbeitsablauf D150)“. Textvergleich D146/D147: [Archiv](docs/progress-archive.md), „rotiert (2026-11-15, Log-Archiv D149)“. Der
Claude-Abend vom 14.11. und die Folgerunde D140–D145: [Archiv](docs/progress-archive.md), „rotiert (2026-11-14,
Textvergleich D146/D147)“; Ergebnis des Abends im Beipackzettel [phase-11-abend.md](docs/phase-11-abend.md)._

## Next concrete step

**Bot neu starten, dann ein kurzer Lauf für die Runden vom 27.11.** Der laufende Bot (Start 27.11., 16:00)
kennt D151–D155 nicht. Prüfpunkte im Beipackzettel [phase-11-abend.md](docs/phase-11-abend.md), „Nächster
Lauf“: F11 (zwei Proben im selben Zug ergeben eine Erzählung, keine Antwort wird in eine andere gesprochen),
W7 (das genannte Ziel wird getroffen), W8 (Smite zieht Wunden ab, ohne Abzug), W4 („Was kann ich?“ postet den
Bogen); dazu die offenen F2, F4, F6, F7, F9, F10, W2, W3, W6. Danach Teil B: Pause statt Nemo (D139,
PowerShell als Administrator — die Firewall-Regel trennt auch Claude-Code-Sitzungen).
Die Sandbox hält den Stand vom 27.11. (Pfandhalle, Tag 1, 23:06, Recap vom `!wrap`): weiterspielen oder vorher
`ingest_session --wipe-debug`. `characters.local.json` enthält Fridolin, Gellicus und Rektalus.

**Daneben, vom Lauf unabhängig: die Zerlegung der drei größten Dateien** nach
[split-state-dicecog-orchestrator.md](docs/plans/split-state-dicecog-orchestrator.md); Tobi hat am 27.11. alle sechs
Entscheidungen wie empfohlen getroffen. `memory/state.py` (1457 → 868) und `orchestrator.py` (1421 → 608) sind
erledigt (27.11.), beide fertig und grün vor dem Bot-Neustart. Der erste Lauf danach sollte für `orchestrator.py`
einmal durchspielen: einen erzählten Zug mit Wurf, `!redo`, `!start` oder `!intro`, `!wrap` (Recap) und `!rules`
mit einer Frage. `voice/dicecog.py` (1442 → ≈ 730) läuft seit dem 27.11. als Runde 3, **vor** dem Lauf
(Entscheidung 7 im Plan, mit ihrem Preis); D0 (die Naht `_prepare_throw`) ist committet, D1–D4 folgen. Der Bot
wird erst neu gestartet, wenn die Runde fertig und grün ist.

**Aus dem Lauf vom 27.11., nicht gebaut:**
- **NSCs nennen Charakternamen, die niemand gesagt hat** (16:10:51 „Fridolin, so heißt ihr doch“, 16:15:35
  „Gellicus, Rektalus, oder wie eure Namen auch lauten mögen“). Ob das schon vorher so war, ist ungeprüft.
- **Die Spieluhr** lief in 18 Zügen 126 Minuten, im Log stehen nur zwei `🕐`-Zeilen mit je +15 min. Woher der
  Rest kommt, ist unklar; die Frist des Abenteuers (24:00) wäre nach rund 25 Zügen erreicht.
- **Erster Ton unverändert** (Median 10,3 s gegen 10,2 s am 14.11.), obwohl der Cache greift; `cache_w=` wächst
  jeden Zug (4353 → 10857), nur der feste Kopf wird wiederverwendet.
- **Sprech-Reihenfolge** (ADR 067): `!say`, `!intro test`, Backend-Ansagen und Vorlesen laufen daran vorbei; eine
  Zielauswahl, die niemand bedient, hält die andere Probe des Zugs bis zum Ablauf der Wartezeit auf.
- **`logs/archive/LAYOUT` und `logs/archive/sandbox/`** sind nicht git-ignoriert (Folge von D149).

**Kandidaten für nach dem Lauf (die ersten zwei aus der Runde vom 15.11., der Rest aus dem Textvergleich):**
- **Ortsmarker in der Ankunftsantwort:** ein Persona-Satz, der `<<ORT>>` in dieselbe Antwort zieht, die die Ankunft
  erzählt. Am 14.11. kam der Marker je einen Zug später (Ankunft erzählt 19:11:39, Marker 19:12:46; 19:20:48 und
  19:21:58), und in dieser Lücke landeten Sichtungen in der verlassenen Szene. Nicht gebaut, ungemessen.
- **Spielerzeile für den Anwesenheits-Klassifikator:** er bekommt die Spielerzeile des Zugs mit. Im Abgleich zu
  ADR 066 erkannte nur der Call mit diesem Kontext Bree Marlok („ist der Marlok hier“); das zielt auf die
  Doppelgänger, die keine Ortsregel verhindert. Nicht gebaut.
- `CLAUDE_NUM_CTX` 24 576 → 32 768 (als zweiter Schritt 65 536: Gedächtnis gegen Verbrauch und Antwortzeit); eine
  Regiezeile für den nächsten Zug, wenn auf eine Probenanforderung kein Wurf folgt; die Auto-Zusammenfassung lässt
  die letzten sechs Züge im Wortlaut stehen.
- Persona-Variante B („drei bis fünf Sätze, kein Satz über etwa zwanzig Wörter“) und B mit fester Obergrenze
  („höchstens fünf Sätze“, ungemessen). B brachte 100 statt 153 Zeichen je Satz, aber keine kürzeren Züge. Zwei
  Beobachtungen aus der Messung: um 19:19:06 begann B mit einem Planungssatz, der vorgelesen worden wäre („Das
  ist ein Überredungsversuch … Den Wurf fordere ich an.“), und um 19:10:05 gab B das Geständnis der Schwester in
  indirekter statt wörtlicher Rede wieder. Eine spätere Messung nimmt mindestens zwölf Züge und zählt beides mit.
- **Reserve:** der Entwurf „für Karten-Figuren gilt die Karte“ (ADR 062,
  [docs/plans](docs/plans/adr-062-card-is-authoritative-draft-2026-11-15.md)) — nur, wenn der Lauf einen
  Anwesenheitsfehler zeigt, den D144 nicht fängt.

**Klein, Tobi entscheidet:** welcher Sprach-Trigger als nächster gebaut wird (alle nach dem Muster von
`dmbot/voice/kick_phrase.py` + `_maybe_kick`). Rangfolge: (1) „Baby, welcome to the party!“ trennt BloodyP;
(2) Zähler: BloodyPs n-tes nacktes „Ja.“ pro Sitzung; (3) „Yo Marco, baby!“. Weitere Ideen aus dem Dossier:
Timos „Bro“-Zähler, Sezgins „keine Ahnung“ → erzwungene Wahrnehmungsprobe, Tobis „warte“-Zähler, DM-Umfrage „Was tust du?“.

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
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) + **ADR 013** (pause control) + **ADR 067** (one narration at a time: narration lock, speaking order, roll batch) |
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
- [ ] Golden-Rules-Konformitäts-Check — ein Skill, der einen Diff gegen die Golden Rules und
      `docs/conventions.md` prüft (`/code-review` sucht Bugs, nicht Regelbruch). Geparkt seit D78.

---

## Open questions / to clarify

_Gesichtet am 2026-11-15: aus 62 Einträgen wurden 18. Die Einordnung je Eintrag steht in
[open-questions-triage-2026-11-15.md](docs/plans/open-questions-triage-2026-11-15.md), der Abschnitt im alten Wortlaut im
[Archiv](docs/progress-archive.md) unter „Open questions (erledigt/archiviert)“, rotiert 2026-11-15._

**Steht woanders, nicht mehr hier:**
- **Im Beipackzettel [phase-11-abend.md](docs/phase-11-abend.md), „Nächster Lauf“:** Kontext ohne Überschrift (F9),
  Prompt-Cache (F5), Zusatzanfrage der CLI (F6) und die behobenen, live-unverifizierten `DMBrain`-Befunde Nr. 1–4, 9
  und 12 (N3, N4, N6, N7; Tests in `tests/test_orchestrator_open_findings.py`).
- **Unter „Next concrete step“:** das größere `CLAUDE_NUM_CTX`.
- **Im geparkten [Live-Run-Skript](docs/live-run-script.md):** Modellvergleich Nemo gegen Mistral Small, die
  `!intro`-Prosa, `!lore tts` liest jeden Block doppelt (Bot A) und die Streaming-Watch-Items. Diese vier müssen die
  Neusichtung der geparkten Gates nach dem Abend überleben.

**Entscheidungen von Tobi:**
- **Sprechmodus-Default** — bleibt `stream`+`flach`, bis die drei Modi am Tisch verglichen sind (der Vergleich steht
  als Schritt im geparkten Live-Run-Skript).
- **Charakterbögen in den gecachten Kopf?** Sie stehen im Zustandsblock und gehen jeden Zug frisch raus; in den Kopf
  verschoben würden einige tausend Tokens mehr gecacht. Das ändert die Reihenfolge in `docs/conventions.md`.
- **Deutsche Log-Zeilen in `session/scenes.py`** („mit der Gruppe nach“, „gemeldet als“, „bleibt in“): in CLAUDE.md
  erlauben oder übersetzen. Die Prüfpunkte F7, N1 und N2 im Beipackzettel greppen genau diese Zeilen; die Frage
  bleibt offen, bis der nächste Lauf ausgewertet ist.
- **Waffenschaden nach Buch?** Nach D155 weicht der Kampf noch an zwei Stellen ab: die Waffentabelle würfelt
  (`1d10+4`), das Regelbuch hat feste Werte plus Erfolgsgrade; und Rüstung ist ein Wert je Figur statt je
  Trefferzone (ADR 015, Nachtrag 2026-11-27).
- **Würfel-Animation:** der Würfel dreht sich nicht (`tools/dice_throw.py` schreibt `angle` nie fort; eine Zeile,
  ändert nur das Bild, nicht die Seed-Auswahl — Vorschau zuerst), und alte GIF-Sätze in `data/dice/anim/` und in
  `#bot-commands` werden nie aufgeräumt (ein Aufräum-Schritt beim Start wäre klein).

**Am Tisch spürbar:**
- **Stall-Detektor** — nach N Zügen ohne Fortschritt selbst weiterschieben. Nur bauen, wenn F2 („keine
  Hängeschleife“) im nächsten Lauf scheitert; der Hänger vom 14.11., 19:25–19:31, ist der Anlass, D140/D141 und das
  `🎲 Sicherheitsnetz` sind die erste Antwort darauf.
- **Das Journal rotiert nur bei `!leave`** (`DMBrain`-Befund Nr. 11), nicht beim Beenden: von 19 Starts seit dem
  30.10. endete einer so. Die rotierte Datei enthielt 57 Züge aus vier Tagen, der Session-Ingest hat sie als eine
  Sitzung abgelegt; bis dahin fehlten sie im Kampagnengedächtnis. Kein Test.
- **`!redo` eines Zugs mit Regie-Impuls läuft ohne den Impuls** (Nr. 10): `close_turn` zählt den Szenenzug hoch,
  bevor das Redo seinen Prompt baut, und das Redo zählt als eigener Szenenzug. Aus Code und Promptgröße hergeleitet
  (133 Tokens weniger), nie gehört. Kein Test.
- **RAG-Lücken:** Waffen- und Statblock-Tabellen werden nicht gefunden (Fix wäre ein deutsches Waffen-Glossar unter
  `data/rules_de/`, wie `conditions.md`), und `!lore`-Antworten zu Rokarth kommen englisch aus dem Setting-Guide.
- **Discord-Last des Panels:** einmal gesehen am 13.11., 00:40 — drei 429 auf denselben PATCH während eines
  Szenenwechsels, rund 13 s Retry; welche Nachricht es war, steht nicht im Log. Im nächsten Lauf die
  `429`-Warnungen zählen.

**Nur unter Bedingungen, die im heutigen Betrieb nicht eintreten:**
- **Replay-Daten überlappender Züge** (Nr. 8): startet der nächste Zug, bevor Wiedergabe oder Autosave des vorigen
  enden, landen dessen Replay-Felder und Notizen samt `state_before` beim falschen Journal-Eintrag (13 von 22 Zügen
  am 13.11., Eintrag 24 am 14.11.). Am Tisch unsichtbar; ein Golden aus so einem Journal wäre falsch, deshalb fehlt
  das erste echte Live-Golden noch. xfail `test_a_turn_started_during_playback_leaves_the_previous_turns_replay_fields`.
- **Lücken außerhalb der Abend-Konfiguration** — erst wieder ansehen, wenn einer dieser Pfade gespielt wird.
  Batch-Pfad (`DM_STREAMING=0`, `nahtlos`): ein verworfener Konsistenz- oder Intro-Retry lässt seine Marker stehen,
  ein leerer Echo-Retry wird als leerer Zug gespeichert (Nr. 5–7, drei xfails), und auf Claude gibt es dort keine
  Sprechgrenze unter ~1244 Tokens. Ollama: ein gekappter Zug schreibt keine ✂-Zeile (Nr. 15, bewusst weggelassen),
  der Recap wird bei `num_predict` 400 gekappt. Ollama und `fallback`: ein gestreamter Zug, der vor dem ersten Delta
  scheitert, steht mit leerer Antwort in der History.
- **Randfälle der Pause (Review D139)** — erst wieder ansehen, wenn die Pause-Probe (Durchgang 3) etwas zeigt: ein
  Zug in der Pause fragt die RAG ab, bevor der Client ablehnt; die Rückkehr bei eingefrorenem Spiel (Esc) bekommt
  keinen eigenen Zug; „Zug vorgemerkt“ ist ein Sitzungs-Flag statt eines Rückgabewerts; Würfelergebnisse und
  Regie-Notizen zweier gleichzeitiger Züge können die Reihenfolge tauschen; ein Zug, dessen Call in der Pause begann
  und danach scheitert, wird ohne neue ⏸-Zeile vorgemerkt.
- **Buchführung der Zug-Sichtungen (ADR 062, Review Nr. 6 und 7):** ↩ innerhalb der Undo-Minute trägt die
  Sichtungen des nächsten Zugs zurück statt der mitgenommenen Figuren, und `_turn_sightings` überlebt
  `!leave`/`!join`. Fix-Idee: die mitgenommenen Namen am `SceneUndo` merken, die Liste beim Verlassen leeren.
- **LLM-Naht:** `marker_decides` nennt `"claude"` an einer Würfel-Stelle (besser ein Hook neben `recap_cap`); das
  Muster chat → wait_for → JSON steht dreimal in den Routern (ein Helfer in `dmbot/llm`); `SystemPrompt` ist ein
  `str`-Subtyp, jede String-Operation verliert den stabilen Kopf — seit dem 15.11. laut (ERROR-Log), robuster wäre,
  den Kopf explizit durch die `LLMClient`-Naht zu reichen.
- **Wer bewegt den Szenenzeiger:** am 14.11. kamen alle drei Wechsel über Opus' `<<ORT>>`-Marker, keiner über den
  Klassifikator, und `!ortmodus frei` wirkt nur auf den Marker-Pfad. Im nächsten Lauf die `scene →`-Auslöser zählen.
- **`!start`/`!intro` mitten in einem laufenden Spielerzug** (Nr. 13): der Spielerzug verliert seinen `<<TEST>>`,
  weil `_queue_markers` `last_action` erst beim Einreihen liest. Kern: `queued` gehört pro Zug in den Prepare-Schritt.
- **Exception in `respond`, danach `!redo`** (Nr. 14): das Journal ersetzt den Zug davor, nach einem Neustart fehlt
  er. Aus dem Code hergeleitet.
- **Der NSC-Prompt verlangt, was das Schema nicht erlaubt** (ADR 062, Review Nr. 8): „statblock = deren Name“ gilt
  für jede Kandidatin, das Schema lässt nur Statblock-Namen zu. Wirkt erst mit einem Abenteuer, dessen Karten-Figur
  keinen Statblock hat.

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
- **Not again:** Die Vereinheitlichung der vier Marker-Handler (`_handle_scene`/`_handle_erledigt`/`_handle_uhr`/
  `_handle_zeit`) auf einen generischen Handler wurde am 2026-11-13 geprüft und mit Verweis auf ADR 051 §5 verworfen
  (ORT passt nicht ins Vorschlagen-oder-Anwenden-Muster, die übrigen bräuchten ~8–10 Callbacks pro Marker).
