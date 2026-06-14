# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
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

_Ältere `## Last session`-Einträge: siehe **[docs/progress-archive.md](docs/progress-archive.md)**._

## Next concrete step
**`!intro`-Eröffnungs-Monolog: ERLEDIGT (2026-06-14, D62 → ADR 031).** Suite 300 grün; nichts Code-seitig
offen. **Live-Gate** (im selben circlejerk-Run mit abprüfen): `!join` → `!intro` → der DM spricht **einen**
zusammenhängenden Monolog, der **Ort** (Hive Rokarth / Welt Voll), **Auftrag** (Halikarn/Gratis) und das
**Hergekommensein** nennt **und jede Figur namentlich** mit einem passenden persönlichen Moment einbindet;
**keine** Würfel-Aufforderung; **keine** wörtlich vorgelesenen privaten Ziele/Arc. Gegen-Check: `!start` ist
weiterhin das kurze 2–4-Sätze-Briefing. Bei nemo-Abschweifen/Auslassen einer Figur: `DM_INTRO_NUM_PREDICT`
senken oder (Fallback) auf die verworfene Multi-Beat-Sequenz umstellen (ADR 031 Alternatives).

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
| D54 | Anti-repetition persona rule | **Prompt-side W4 fix** — a persona rule in `prompts/dm_core_de.md`: established facts (Was bisher geschah, world state, ongoing scene) are **already known to the players**; reference them briefly, describe in detail only **new** things + the **consequences** of the latest action. Plus the recap label in `_build_request` sharpened to „(den Spielenden bereits bekannt — nicht erneut ausführlich erzählen)". Prompt-only; no code guard built (D45's fuzzy `is_self_repetition` stays the fallback) | The DM re-explained settled context (places/NPCs/events) in full every turn instead of advancing — the persona side of W4, which D45's after-the-fact echo guard can't pre-empt. ADR 016 itself flagged W4 as open, and this lives in ADR 016's persona-output-discipline domain → **Nachtrag in ADR 016**, no new ADR. Live-observe nemo's adherence |
| D55 | XTTS-Babble bei Satzzeichen | **Zwei XTTS-Sampling-Hebel** (`dmbot/tts/xtts.py` `_SYNTH_KWARGS`, an beide `tts_to_file`-Pfade): **`split_sentences=False`** (`textsplit` chunkt bereits in <240-Zeichen-Satzgruppen; XTTS' eigener pysbd-Splitter zerlegte die in Satzzeichen-Fragmente → GPT-Decoder-Loops/Babble) + **`repetition_penalty=10.0`** (Model-Config liefert 5.0, XTTS' eigener `inference`-Default ist das stärkere Anti-Loop-10.0; tunbar via `XTTS_REPETITION_PENALTY`). 246 grün; live-unverifiziert | D53 härtete den *Text* zu XTTS (Whitelist + Sprechbarkeits-Guard) und stellte diese zwei Sampling-Hebel „nur bei Bedarf nach Live-Test" zurück — der Test brauchte sie („Psychosen bei Satzzeichen": autoregressives Loopen an Kommas/Satzenden, kein Normalisierungs-Leak). Kwarg-Fluss per API-Inspektion bestätigt (`tts_to_file`→`Synthesizer.tts`→`Xtts.synthesize`). Nächster Hebel bei Persistenz: `temperature` runter → **Nachtrag in ADR 016** |
| D56 | Auto scene transitions | **Third LLM marker `<<ORT <scene-id>>>`** (mirrors `<<TEST>>`/`<<MANIFEST>>`): the DM *requests* a scene move in-band; code strips+validates it and a **human confirms** via a `SceneChangeView` button before the deterministic move runs (`_set_scene`, shared with `!ort`). Profile-free `extract_scenes` (scenes belong to the adventure, not the rules profile); `finalize_answer` → 4-tuple; `_pending_scenes` queued only under the `_last_action` post-roll guard. Switchable target mode `DM_SCENE_MODE` / `!ortmodus`: **`verbunden`** (default — only `leads_to` neighbours, via pure `Adventure.resolve_move`) vs **`frei`** (any scene); illegal/unknown → ignored+logged. Manual `!ort` stays as override. +12 tests (246 grün); live-unverified | `!ort` mid-scene was friction (ADR 020 deferred this exact step: "re-evaluate once live play shows `!ort` friction"). Upholds golden rule #3 — the LLM never *writes* `scene_id`, it emits a validated request like it requests dice (golden rule #2); the confirm button is the human-in-the-loop gate. Reverses only ADR 020's "moved by humans only" binding → **ADR 026** |
| D57 | Context budget (1st live round) | **(a) `num_ctx` configurable + high.** New `OLLAMA_NUM_CTX` env (Config `ollama_num_ctx`, default **24576**), threaded config → cog → `OllamaClient(num_ctx=…)` → request `options`; removes the hardcoded 8192. **(b) Rolling auto-recap (`DM_AUTORECAP`, default on).** When `prompt_eval` crosses `ctx_over_budget` (0.85·num_ctx), *after* the turn is spoken (off the hot path): a **cumulative** recap (`summarize(cid, prior_recap=…)`) is generated, persisted like `!wrap up`, and the in-memory history **cleared** — so the next prompt's head (persona + adventure) is never truncated. Per-channel `_compacting` guard. +18 tests (262 green) | The 1st live round's loudest failure ("geht null auf die Story ein") was a **silent truncation**: `num_ctx` ran at 8192 (the 24000 Tobi thought he'd set was read nowhere); from ~turn 16 the prompt head (persona + adventure summary) fell out — simultaneously causing story-ignored, runaway length, puppeting, pre-roll resolution. Two layers (big window + proactive compaction) close it GPU-independently. Chose compact-and-clear on the real budget signal over the `prompt-6` fold-before-trim spec → **ADR 027** |
| D58 | `!start` briefing + persona steer | **(a) `!start`** (aliases `!briefing`/`!auftrag`): a dedicated opening turn — the DM narrates the `auftrag` briefing (Halikarn message, mission, leads as atmosphere) via the existing stream/speak path; a thin `respond_opening*` path leaves `_last_action` None so dice routing is suppressed; sets `scene_id` to the start scene if unset. **(b) Persona** (`prompts/dm_core_de.md`): keep the current scene's goal in view + steer gently toward open leads (not a list, not railroad); every turn ends with the **world in motion** (an NSC acts/speaks or a concrete hook), never a flat description that stops; **spotlight** — bring other named/silent characters in by name | 1st-round complaints: "am Anfang nicht gesagt, was abgeht" (`!join` only printed status), the DM stopped on static descriptions with passive NPCs, and one player sat idle all session. Prompt/feature tuning in ADR 016's persona-discipline domain (like D54) — effective only because D57 stops the persona being truncated → D-entry, no new ADR. Live-unverified |
| D59 | RAG junk-shape filter | **Distance-independent `_is_junk_hit`** in `fetch_block` (per-turn narration gate only; `!rules`/`!lore`/`lookup` untouched): drops dash-run headings (`-{4,}`), statblock-tag headings (`(eLite)`/`(trOOP)`/`(LeaDer)`), and picture-text bodies. `MAX_DISTANCE` stays **0.45**. 103/2482 chunks become narration-ineligible; recall@1/@3 **unchanged** (52%/81%) | 1st round: pure-RP turns injected OCR/TOC garbage at the 0.43–0.45 edge (`WARRIOR`, `MACHARIAN TOMES`, `--- PSYCHIC POWERS ---`), wasting the context budget D57 fights. Calibration (ADR 025) showed tightening the threshold costs real recall (`CRITICAL HIT` @0.439) — a shape filter is surgical instead. Known gap: `WARRIOR`-style epigraph rows need ingest-level re-chunking (out of scope) → **ADR 028** |
| D60 | Voice cog split → SessionRuntime | **Pure structural refactor (zero behaviour change).** The 2300-line `VoiceReceiveCog` split into a shared **`SessionRuntime`** (`dmbot/runtime.py`, built once from `Config`, injected into every cog — the 26 ctor kwargs collapse into it) + three thin cogs: **VoiceCog** (join/leave/vstatus/mic/pause, VAD-sink), **DiceCog** (roll/test/turn/rules/npc/damage/heal, dice+manifest buttons, auto-combat, turn-order render), **DMCog** (batch+streaming delivery, TTS speak, auto-recap, !dm/!redo/!start/!wrap/!say/!voice **and** scenes !ort/!szenen/!ortmodus + the `<<ORT>>` marker + !lore). **No `bot.get_cog`** — five hooks registered on the runtime (`run_and_deliver`/`auto_dm_turn`/`handle_dice`/`reanchor_mic`/`post_turn_order`). `commands.py` deleted; suite **263 green** (only test-import paths + one `test_autorecap` fixture rewired to a stub runtime — assertions unchanged) | The file had become a god-cog with a 26-kwarg ctor; every session paid for the whole thing and the concern boundaries had blurred. Moved-not-rewritten (per-agent AST/reverse-rename diffs + a streaming-pipeline spot-check confirm byte-identical bodies; only `self._X`→`self._rt._X` renames + the hook calls). Boot path unchanged (preflights once, same order; `TEARDOWN_STEPS` sum still 4 → shutdown display byte-identical). Binds later work: Phase 10b profile bootstrap hangs off the runtime, not a cog → **ADR 029** |
| D61 | Code-review correctness round (post-cog-split) | **9 verified defects in the day's feature work + cleanup, behaviour preserved.** Correctness: (1) **Warp-containment Test → Disziplin (Psi)** not Psi-Meisterschaft (IM p.163) — new `ResolvedManifest.contain_base` wires the previously-unused `psyker_purge_skill()`; (2) **party psyker not in WorldState** no longer silently drops Warp Charge — one-time German warning (no safe single-char state add); (3) **batch delivery** awaits dice/scene tasks in `finally` so the 🎲 button isn't lost when speak raises; (4) **auto-recap** `clear_history` clears only the `summarize`-consumed prefix (`_compact_consumed`) so a turn appended during the LLM await survives; (5) **glued markers** `\b`→`[\s:]*` so `<<ORT1>>`/`<<ORTmud_gate>>`/`<<MANIFESTSmite>>` strip+fire instead of being read aloud; (6) **`resolve_test`** signature-dispatch (`inspect.signature`) replaces the `except TypeError` that swallowed real errors + double-rolled (golden rule #2); (7) **streaming** cancels orphaned prod/synth/play tasks + drains queued WAVs on a mid-stream bridge failure (permanent-mute claim **refuted** — `finally` always unmutes, mute logic untouched); (8) **layer-2 mute → depth counter** so DM-speak vs operator pause/resume nest (resume mid-playback can't unmute); (9) **soak** uses `skill_value` (strip+CI) so a `"Tgh "` key isn't 0 soak. Cleanup: shared `_catalog_lookup` (profile), shared `tts/wavio.write_silent_wav`, dead `reduce_warp_charge` removed, no-op `[:80]` slices dropped, **thread-local cached sqlite conn** + `<<`-free StreamAssembler fast path. Suite **293 green** | Tobi asked `/code-review` over the day's commits, "Funktionalität soll bleiben". Multi-agent review (9 finder angles + per-finding verifiers over `5d672b6~1..HEAD`) cleared the cog split as faithful and found these in the parallel feature work. The **altitude findings — system-agnostic generalisation of engine/marker/RAG-sources — are DEFERRED to the second-profile / Phase-10b point** (no second system to generalise against yet; large + behaviour-risky; ADR 005 stance is "generalise when the 2nd system arrives") → **ADR 030** |
| D62 | `!intro` opening monologue | **New `!intro` command (aliases `!einleitung`/`!eroeffnung`): one long opening monologue that involves every PC, by reusing + parameterising the `!start` opening path.** New `CharacterStore.intro_roster_de()` builds a full-depth German party roster from `Character.raw` (concept/origin/faction/distinguishing/goals/connections/arc, tolerant of lean sheets); new pure `build_intro_director_msg(roster)` wraps it in a `[Regie]` instruction (one monologue: place → arrival → mission from the scene card/summary, then a personal beat per named figure — weave in, only hint at private goals, no dice) with the roster embedded in the **director (user) message** so the ADR-019 prompt order is untouched. An optional `num_predict` override is threaded through `_build_request`/`_chat_once`/`_generate`/`_stream_and_store`/`respond_opening`/`respond_opening_streaming` (default `None` → unchanged); `!intro` runs on `DM_INTRO_NUM_PREDICT` (default 800). `!intro` mirrors `!start`'s safe scaffolding (deterministic scene-pointer move only if unset, dice suppressed, stream/speak). `!start` left as the short briefing. +7 tests (**300 green**); live-unverified | Tobi (plan mode): the 1st-round "sagt am Anfang nicht, was abgeht … bezieht die Figuren nicht ein" gap needed a real opener. Chose a **monologue** over a scripted multi-beat sequence, a **separate `!intro`** over extending `!start`, and **full** figure depth — all his calls. Reuse-not-duplicate per ADR 030; roster-in-director-message avoids per-turn prompt bloat (ADR 019). Risk (nemo-12B rambling at length) watched live; fallback = multi-beat or lower `DM_INTRO_NUM_PREDICT` → **ADR 031** |

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
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) + **ADR 015** (sheet/state split, auto-combat damage) + **ADR 027** (rolling auto-recap / context handoff — recap is no longer wrap-up-only) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) + **ADR 019** (3-stage hybrid: scene tracker + rulebook-only RAG, bge-m3, W4 guard) + **ADR 021** (curated German lore compendium: `lore_imperium`/`lore_chaos` sources) + **ADR 025** (German rules glossary + 0.45 calibration) + **ADR 028** (RAG junk-shape filter) + **ADR 027** (configurable `num_ctx`, context-budget compaction) |

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
