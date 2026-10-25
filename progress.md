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
- **Newest round:** D123 + D124 — vierter Opus-Lauf (2026-10-25 spätabends, Tobi + Sezgin). D121/D122 halten
  live. D123: sechs kleine Fixes (Psi-Doppelprobe über „Fel“, Puppet-Filter-Subjekt, „Wechseln“ nach Auto-Wechsel,
  Router-Default Herausfordernd, Fertigkeiten im Prompt, Persona-Richtung). D124/**ADR 062**: erfundene NSCs werden
  per drittem Nach-Zug-Klassifikator angelegt und als anwesend geführt; Zielauswahl und Prompt kennen nur noch
  Anwesende (Fridolins Schüsse trafen Kaad, zwei Szenen weiter). **1265 Tests grün, `dm-eval` Exit 0**; Haiku live
  per Einzelaufruf 3/3 Fälle richtig (nach einer Prompt-Schärfung gegen Doppel-Anlage).
- **Nachtrag (D125):** am Ende von Lauf 4 starben TTS und STT: zwei Erzählungen (Psi-Doppelwurf) ließen XTTS
  parallel laufen → `device-side assert`, CUDA-Kontext des Prozesses kaputt, Whisper mit. Jetzt: Sperre um jede
  XTTS-Synthese, `dmbot/gpu_health` meldet den ersten CUDA-Fehler einmal im Kanal („Bot neu starten“), danach
  kurze Logzeilen statt Tracebacks. 1272 Tests grün, `dm-eval` Exit 0.
- **Nachtrag (D126 / ADR 063):** Schicksalspunkte — eine misslungene Probe zeigt „🙏 Neu würfeln / Hinnehmen“,
  der DM erzählt erst danach (20 s Timeout), Erholung bei `!join`, `Schicksal x/y` im Weltzustand. Persona:
  Fehlschlag echt, aber mit Folge statt Sackgasse, Maß nach EG. 1282 Tests grün, `dm-eval` Exit 0.
- **Nachtrag (D127):** Würfelergebnisse als Embed mit dem gewürfelten W20 als Thumbnail (Gold = kritisch,
  Grün = Patzer, aus den Engine-Flags), gerendert bei Bedarf nach `data/dice/`; `DM_DICE_IMAGES=0` = Text.
  Reine Darstellung, Goldens unverändert. 1299 Tests grün, `dm-eval` Exit 0. In Discord live-unverifiziert.
- **Next concrete step:** fünfter Lauf (Sandbox leeren, Bot neu starten). Prüfen: Würfel-Thumbnail an jedem
  Ergebnis (auch nach „🙏 Neu würfeln“ der zweite Würfel), `👥 anwesend in …`-Zeilen für
  improvisierte Gegner, Zielauswahl zeigt nur Anwesende, kein Doppelwurf bei Psi, kein „Wechseln“ nach Auto-Wechsel,
  NSCs sagen, was sie wollen, „Was kann ich?“ wird aus dem Bogen beantwortet, Schicksal-Buttons erscheinen
  nach Fehlschlägen und Fehlschläge führen weiter statt in Sackgassen. `!sprechmodus nahtlos intoniert`
  weiter ausprobieren. Danach `characters.json` zurück (`git checkout`), wenn Timo/Vinnie wieder mitspielen.
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

**Würfel-Thumbnails (2026-10-25 nachts, D127).** Tobis ASCII-W20-Generator liegt jetzt in `tools/generate_dice.py`
(Font-Auflösung DejaVu → Arial/Consolas, eigener RNG statt `random.seed()`, Ausgabe byte-identisch zum Original).
`dmbot/dice_images.py` rendert bei Bedarf (~0,1 s, im Thread) nach `data/dice/<palette>/` und fällt bei Fehlern
auf ein Embed ohne Bild zurück. Button, `!test`, Schicksals-Neuwurf, Manifestation und `!roll` (Summe ≤ 100) zeigen
den Rohwurf als Thumbnail; die Engine blieb unverändert (`critical`/`fumble` gab es schon). `pillow` deklariert.
1299 Tests grün (+17), `dm-eval` Exit 0, ruff ohne neue Meldungen. Am Tisch unverifiziert: das Bearbeiten der
Button-Nachricht mit neuem Anhang.

**Vierter Opus-Lauf, sieben Fixes (2026-10-25 spätabends, D123).** Tobi und Sezgin, nur Fridolin + Rektalus.
Gehalten: D121/D122 live, `cut` 6/47, erstes Audio ~9,9 s im Schnitt. Neu gefunden und behoben:
- **Psi doppelt, zweiter Anlauf:** Dread Presence bekam neben der Manifestation eine Router-Probe auf „Fel“; der
  D121-Fix griff nur bei Psi-Meisterschaft. Jetzt fällt jede Router-Probe der manifestierenden Figur weg.
- **Puppet-Filter (D113) strich Kaads Satz** „Kaad bemerkt, wohin Fridolin schaut, … und sagt: …“. Der Name zählt
  nur noch als Subjekt: am Teilsatzanfang vor dem Verb oder direkt danach (nur Kleinwörter dazwischen, kein „zu/an“).
- **„Wechseln“ nach Auto-Wechsel:** Marker-Vorschlag und Szenen-Klassifikator lösten beide aus. Jeder echte Wechsel
  schließt jetzt den offenen Vorschlag (`retire_scene_proposal`), der Button verschwindet.
- **Fernkampf „Schwierig“ ohne Grund:** Klassifikator-Regel, Standard Herausfordernd, schwerer/leichter nur mit
  klarem Grund aus der Handlung (Tobis Wahl).
- **„Ich weiß mein Skill-Set nicht“ (Sezgin):** Fertigkeiten + Talentnamen stehen als `## Bögen der Spielfiguren`
  im Prompt (Tobis Wahl: per DM fragen, kein Befehl); ~490 Zeichen.
- **„Niemand sagt, was er will“ (Tobi):** Persona — NSCs machen ihr Anliegen deutlich; stockt die Gruppe, nennt der
  DM in einem Satz zwei, drei Möglichkeiten (Tobi: beides).
- **Belegt:** 1248 Tests grün, `dm-eval` Exit 0, `ruff --select F` sauber. Am Tisch unverifiziert.
- **Nachtrag D124 / ADR 062, erfundene Gegner:** beide Laspistolen-Treffer gingen auf Seneschall Kaad (zwei Szenen
  weiter, danach 0/8 und aus dem Prompt verschwunden), weil die Zielauswahl alle NSCs anbot und Opus' Kettenmänner nie
  im Spielstand standen. Tobi wählte „automatisch anlegen“. Jetzt: dritter Nach-Zug-Klassifikator (`npc_router`,
  Haiku, `DM_NPC_ROUTER`, `!automatik nscs`) meldet Neue, Code legt sie mit Abenteuer-Statblock oder
  `combat.improvised_npc` an (`Combatant.scene`), „anwesend“ = Szenenkarte + dort gesehen, für Prompt,
  NSC-Gedächtnis und Zielauswahl. Live per Einzelaufruf: 3/3 nach einer Prompt-Schärfung (vorher legte Haiku den
  Verwundeten doppelt an). 1265 Tests grün, `dm-eval` Exit 0. Offen: einmal las Opus einen Planungssatz vor.

**Dritter Opus-Lauf und vier Regel-/Filter-Fixes (2026-10-25 abends, D121).** Tobi, Sezgin, Timo und BloodyP
spielten ~45 min „Die Mitternachtsfracht“. Tobi: „ich konnte keine Heimlichkeit machen … alle Skillchecks sind
fehlgeschlagen.“ Diagnose aus `terminal.log`/`debug.log`: 9/9 Proben verfehlt bei Zielen 12–51 (P ≈ 1,7 %); die
Engine ist fair (100k-Simulation trifft die Quoten), Fridolins Heimlichkeit 48 −10 (Schwierig) = 38 ist korrekt.
- **Patzer überall:** die Engine markierte jeden Pasch als Patzer/kritisch, IM kennt das nur bei Angriffen
  (S. 213; stand schon im Profil-`_note`). Opus erzählte aus „Heimlichkeit 66 — Patzer“ und „Psi 44 — Patzer“
  Katastrophen, einen Warp-Unfall ohne Perils-Wurf. Jetzt: Profil-Schlüssel `crit_scope: "attack"`,
  `engine.scope_doubles()` am Würfel-Button und an der Warp-Kontrollprobe; Manifestationen behalten ihre Pasch-Regel.
- **Doppelte Psi-Probe:** eine Psi-Aktion bekam einen Dread-Presence-Manifest-Button *und* einen Router-Button
  „Psi-Meisterschaft (Schwierig)“; beide wurden gewürfelt. Jetzt verwirft der Router eine Probe auf die
  Manifest-Fertigkeit, wenn dieselbe Figur in dem Zug manifestiert (`superseded_by_manifest`).
- **Router auf Satzfragment:** Sezgins ganzer Zug „dass wir das Osadium suchen.“ wurde zu Wahrnehmung.
  Jetzt überspringt der Router Züge, die mit „dass/daß/weil“ beginnen (`is_continuation_fragment`, bewusst eng).
- **Puppet-Filter (D113) zu scharf:** „…Helmstimme: „Inquisition, sagst du? Dann zeig mir das Siegel …““ — der
  Satz flog raus, die Antwort begann mitten im Zitat. Jetzt zählt nur die Erzählung außerhalb von Anführungszeichen
  (Zustand über Sätze hinweg, auch im Stream); „„…“, sagst du.“ wird weiter gestrichen.
- **Belegt:** 1232 Tests grün (14 neue), `dm-eval` Exit 0, `ruff --select F` sauber; Live-Fälle mit echtem
  IM-Profil nachgerechnet. Am Tisch unverifiziert.
- **Nachtrag D122, Inventar nie im Prompt:** „Was habe ich dabei?“ → „das weißt nur du“, und die Arbites fanden
  Fridolins Siegel nicht, das auf seinem Bogen steht. Ursache: `world_state_summary_de` rendert seit Phase 9 nur
  Wunden/Zustände; `equipment`/`weapons` kamen nicht mal in den Zustand. Jetzt: `Ausrüstung`-Zeile pro Figur,
  Seed führt `inventory` + `equipment` + Waffennamen zusammen (`merge_gear`). 1238 Tests grün, `dm-eval` Exit 0.
  Alte `state.json` behalten ihre Liste (Seed nur beim ersten `!join`) — die Debug-Sandbox wird ohnehin geleert.
- **Spieler-Feedback ohne Fix:** TTS-Betonung über Satzgrenzen (Modus `flach`), Intro zu lang, Uhrzeit zu genau,
  Codewort für Regelfragen gewünscht. Inhaltlich: die Spieler spielten
  sexuelle Gewalt an; der DM schilderte nichts davon und ließ die Welt reagieren — so gewollt.

**Die ersten Opus-Züge am Tisch, und drei Fixes (2026-10-25, D119/D120).** Tobi hat zweimal mit Opus gespielt (allein, Debug-Kampagne). Ergebnis: Opus erzählt, nachdem drei Fehler raus sind, die erst am Tisch sichtbar wurden; alles steht in ADR 061 (Nachtrag 2026-10-25) und ADR 057 (Nachtrag).
- **Lauf 1, leere Züge:** Opus denkt trotz `thinking=disabled`, und das Denken zählt gegen das Ausgabelimit; bei 220 Tokens blieb für Text nichts. Jetzt: `effort="low"` für Erzählung, 1024 Tokens Puffer pro Anfrage, die Sprechgrenze hält der Client selbst am Text. Live: erstes Wort nach ~3,7 s, `think=` ~70.
- **Lauf 2, abgeschnitten:** 16 von 17 Zügen gekappt, weil 220 Tokens bei Opus nur ~440 Zeichen sind (Nemo ~750). Tobi will keine Satzquote, „ein GM redet mal viel, mal wenig“ — also gilt jetzt Nemos Sprechlänge (3,4 Zeichen pro Token); die Persona bleibt heute unverändert.
- **Lauf 2, Gedächtnis weg:** der Auto-Recap wurde bei 807 Zeichen mitten im Satz gekappt, „Dockmeister Kessel“ fiel raus, der nächste Zug leugnete ihn. Die Sprechgrenze gilt jetzt nur für gestreamte Züge; live über dieselben 15 Züge: 1275 Zeichen, vollständig.
- **Lauf 2, kein Szenenwechsel:** der Router sah nur den aktuellen Zug, der den Ort oft nicht nennt. Er bekommt jetzt den vorigen Zug und die Spielerzeile als Kontext; Haiku-Replay: Betreten 3/3, Gespräch 0/3.
- **Belegt:** 1215 Tests grün (12 neue), `dm-eval` Exit 0, Lint sauber, Preflight live OK. Sandbox danach geleert. Commits `6959481`, `ab25cad`. Am Tisch unverifiziert: alle drei Fixes zusammen.
- **Nachtrag, Spielerzeilen im Kanal:** Tobi: „im Discord soll auch stehen, was die Player gesagt haben, sonst kann man die Geschichte nicht lesen.“ Jede an den DM geroutete Zeile wird jetzt direkt nach der Transkription als `🗣 **Figur:** …` gepostet (Markdown/@everyone entschärft); Tischgespräch ohne Push-to-talk bleibt im Log. Schalter `DM_POST_PLAYER_LINES=0`. 1218 Tests grün, Lint sauber; live unverifiziert.
- **Nachtrag, schlankerer Arbeitsablauf:** Tobi fand, das Ritual verbrauche zu viel Kontext. Gemessen: Pflicht-Lektüre ~41 KB, davon 23 KB die neueste ADR; `progress.md` 85 KB, davon 60 KB Decision-Log. Jetzt: der Start liest nur `CLAUDE.md` + State header, ADRs und Lessons nur bei Subsystem- oder Phasenarbeit (ADR 061 hat dafür einen `## Current state`); das Decision-Log liegt in [docs/decision-log.md](docs/decision-log.md) (`D##` unverändert); `progress.md` ist auf 40 KB gedeckelt (jetzt ~27 KB); kleine Runden tragen ihren Fortschritt im selben Commit ein. Lokal abgeschaltet: Plugins engineering, pdf-viewer, csharp-lsp.

_Ältere `## Last session`-Einträge: siehe [docs/progress-archive.md](docs/progress-archive.md), `## Last session (Verlauf)`._

## Next concrete step

**Ein dritter Opus-Lauf, dann der Phase-11-Abend nach [docs/testabend-ablauf.md §9](docs/testabend-ablauf.md).** Sandbox ist leer (2026-10-25). Vorher: Verbrauchsstand auf claude.ai notieren (die zwei Läufe vom 25.10. stecken schon drin), entscheiden, ob Gellicus/Rektalus/Rene in der Kanal-`characters.json` bleiben. Im Log prüfen: Anteil `cut` (soll die Ausnahme sein), `📖 Auto-Szenenwechsel vorgeschlagen → schrein` beim Betreten, Gedächtnis nach dem ersten `🧵 Auto-Recap`, `think=` pro Zug, und ob jede Spielerzeile als `🗣` vor der DM-Antwort im Kanal steht. Hält das, die Gate-Punkte 0–9 und die drei Messungen aus §9.6; danach in einer eigenen Session: Befunde eintragen, ADR 061 annehmen oder begründet zurücknehmen, die 17 geparkten Gates neu sichten, erst dann das PRD für Phase 12.

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
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) + **ADR 012** (difficulty ladder, character store, marker grammar) + **ADR 014** (roll-detection router; timing now D40 — fires concurrent with playback) + **ADR 018** (router wins the dedupe; echo guard + roll-feedback directive on post-roll turns) + **ADR 040** (committed default party — party loading no longer bound to one voice-channel id) + **ADR 063** (Fate: spend to reroll a failed test, recovered on `!join`) |
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
