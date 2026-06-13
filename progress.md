# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
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

## Next concrete step
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
- **Shutdown (D47):** Ctrl+C twice during a streamed turn → exit is prompt (no multi-second hang)
  and prints `[i/n] … ✓` per stage + a summary that names the dropped synth.
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

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) + **ADR 016** (anti-puppeting backstop, length cap, output cleanup) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM) + `architecture.md` §3 (bridge contract) + **ADR 016** (TTS speech-only normalization) + **ADR 017** (streaming pipeline: sentence-chunked TTS, hold-back rules, history parity) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) + **ADR 013** (pause control) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) + **ADR 012** (difficulty ladder, character store, marker grammar) + **ADR 014** (roll-detection router; timing now D40 — fires concurrent with playback) + **ADR 018** (router wins the dedupe; echo guard + roll-feedback directive on post-roll turns) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) + **ADR 015** (sheet/state split, auto-combat damage) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) + **ADR 019** (3-stage hybrid: scene tracker + rulebook-only RAG, bge-m3, W4 guard) + **ADR 021** (curated German lore compendium: `lore_imperium`/`lore_chaos` sources) |

---

## Phase status (Part 1 — MVP)

Legend: ⬜ open · 🔄 in progress · ✅ done (with proof)

### ✅ Phase 0 — Foundation & setup
- [x] Repo + project structure (skeleton per `architecture.md` §12; uv/Python-3.12, `.gitignore`, `.env.example`)
- [x] Discord DMbot app + token (in `.env`). _(Bot A token already exists in the music bot repo.)_
- [x] Ollama installed locally on the 4070 + models pulled (`mistral-nemo`, `nomic-embed-text`) + reachable
- [x] Model taste test → primary model chosen: **mistral-nemo**
- **Manual setup (outside the agent): see `docs/SETUP.md`.**
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

**Cross-repo (Bot A):**
- **`!lore tts` reads each block twice** — verified NOT in DMbot (lore_pages/loop/synth/concat all
  1×, no custom `on_message`). If the live `debug.log` shows **one** `🔊 TTS … speaking` + **one**
  `/speak` per block, the doubling is **Bot A's playback** (separate `Pr0degie/musicbot` repo) → fix
  there (two-bot isolation). A Bot-A `/stop` would also enable true mid-block skip in the lore reader.
- **Weapon / stat-block tables don't retrieve** (calibration finding, ADR 025) — table-row chunking;
  a German weapon glossary under `data/rules_de/` (same pattern as `conditions.md`) is the likely fix.

**From the lore work (2026-06-13):**
- **`!lore`-Antworten zu Rokarth sind englisch** — die `setting`-Quelle ist der englische
  Setting-Guide-Text; eine Rokarth-Frage liefert also rohe englische Chunks ins Spieler-Embed
  (Imperium/Chaos kommen deutsch aus dem Kompendium). Kosmetik; Optionen wären eine deutsche
  Rokarth-Sektion im Kompendium oder `setting` aus den `!lore`-Quellen nehmen. Erst mal
  beobachten, ob es die Runde stört.

**From the Phase-7 playtests (2026-06-06) — carry into Phase 8 / quality work:**
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
- **Latency grows with context** as history accumulates; the 20-turn cap helps but recaps (Phase 9)
  are the real fix. **Now observable (D35/D36):** the per-turn `[latency]` line shows
  `ctx=<prompt>/8192 gen=<eval>`, and a WARNING fires once the prompt passes ~85% of `num_ctx` — so
  the cap-creep is no longer silent. Capture the live baseline before the streaming work; don't raise
  `num_ctx` (KV-cache VRAM) — trim history/recap/state if the warning shows.

**Only empirical, to decide in Phase 0 (try it, not design):**
- ✅ **Model:** decided — **mistral-nemo** as primary (taste test 2026-06-04 vs gemma3:12b /
  qwen3.5:9b / glm-4.7-flash: best idiomatic German + NSC dialogue; glm too big for 12 GB).
  `gemma3:12b` is the atmospheric runner-up — worth re-checking against nemo in Phase 5 with the
  real persona prompt if the tone needs more richness.
- **TTS voice:** `de_DE-thorsten-medium` vs. `thorsten_emotional` — listen. _(Phase 6.)_

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
- ✅ **Gate prerequisite resolved (2026-06-10) — party registered + session reset.** The first run
  couldn't run the HP-gate because the PC wasn't in `characters.json` (raw rolls, no damage
  persisted). Now the `circlejerk` channel has a hand-authored sheet (Garran Vex / Eli Castor / Magos
  Yann, three different builds + aliases) and its old `state.json`/`history.jsonl`/`recap.md` were
  deleted so `!join` re-seeds fresh. (Channel files are git-ignored; only the `_example` party is
  checked in.)
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

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
