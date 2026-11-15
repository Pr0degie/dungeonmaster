# Open questions — triage (2026-11-15)

Sighting of `progress.md` → `## Open questions / to clarify` (lines 227–420) as of commit `9a4f3e1`.
Nothing in `progress.md` was changed; this file is the proposal.

**Result.** 62 entries: 59 bullets / numbered findings plus 3 unbulleted paragraph entries at
the end (lines 408, 411, 414). Categories: **8 felt at the table**, **32 theoretical only**,
**4 done**, **18 duplicates**. After the proposal **17 items** stay in the list (9 kept as they
are, 8 new merged items); 18 entries go into a counterpart that already holds them
(`docs/phase-11-abend.md`, `docs/live-run-script.md`, `progress.md` "Next concrete step" or
the Part 2 backlog), 10 are struck.

**As implemented in `progress.md` (2026-11-15, after Tobi's approval).** The proposal was applied
with three deviations, so **18 items** stay instead of 17:

- **#49 (speech-mode default) stays in the list.** It holds an open decision of Tobi, and its
  counterpart sits in the parked live-run script, which is re-sighted after the evening.
- **#2 (`SystemPrompt` is a `str` subtype) goes into merged item E** (LLM seam hygiene), not into
  check point F5. It is a structural question about the code, not something a run decides.
- **#5 is struck, not absorbed.** ADR 066 B was removed on the same day (D148), and with it the
  counterpart "ADR 066 B einschalten?". Items #3, #4 and #6 lost their mentions of the removed
  code for the same reason.

Final tally: 11 struck, 15 absorbed by a counterpart, 26 merged into 8 items, 10 kept. The
question about German log lines (#34) stays open. The section's old wording is in
`docs/progress-archive.md` under "Open questions (erledigt/archiviert)", rotated 2026-11-15.

Counterparts used:
- **F1–F10, W1–W6, N1–N8:** check points in `docs/phase-11-abend.md` (lines 289–310 and 94–101).
- **LRS:nnn:** `docs/live-run-script.md` — the old live-gate backlog, **parked** since 2026-10-06
  and to be re-sighted after the Phase-11 evening (State header). A duplicate of a parked item
  is marked as such (see "Wavering" below).
- **NCS:** `progress.md` "Next concrete step" (lines 62–88).

Category rules as given: *felt at the table* names what one notices; *theoretical* names the
condition; *done* carries a file:line or a test (the tests below were run this session, 7 passed
plus the open-findings file: 5 passed, 4 xfailed); *code built but live-unverified* is not
*done* — those items are marked **[code fixed, live-unverified]** and filed under their live
check point.

## 1. All entries in progress.md order

| # | Line | Entry (short) | Category | Reason / evidence / counterpart |
|---:|---:|---|---|---|
| 1 | 231 | Context blocks without a heading in the prompt (D142) | Duplicate | = F9 ("Kontext ohne Überschrift"). The remedy (a heading line, needs `dm-eval` + run) is the decision behind F9's outcome. |
| 2 | 235 | `SystemPrompt` is a `str` subtype; a str op drops the cache head | Theoretical | Loss never observed; since `9a4f3e1` it is loud: `dmbot/llm/claude_client.py:586-594` logs an ERROR, test `tests/test_claude_client.py::test_a_spoken_turn_that_lost_its_stable_head_logs_an_error` (passed). Mitigated, not structurally solved. |
| 3 | 237 | `marker_decides` names `"claude"` at a dice site (D140) | Theoretical | Code hygiene only; still there: `dmbot/llm/roll_router.py:82`, used at `dmbot/voice/dicecog.py:100`. No table effect. |
| 4 | 239 | Duplicated code: separate-ask path twice, chat→wait_for→JSON four times (D143) | Theoretical | Refactor debt; still four copies: `fact_router.py:288`, `npc_router.py:261`, `post_turn.py:288`, `scene_router.py:261`. No table effect. |
| 5 | 241 | Before `DM_AUX_COMBINED=1`: two timeouts, three parity runs, dm-eval category, lesson/ADR addenda | Duplicate | = NCS "ADR 066 B einschalten?" (`progress.md:82-83`) and `phase-11-abend.md:322-325`. Only the dm-eval category and the doc addenda are extra. |
| 6 | 243 | Replay notes (incl. `state_before`) overwritten by the next turn (D143) | Duplicate | Same root as #16 (per-channel note buffer overtaken by the next turn); ADR 066 lines 269-276 describe it. Still unfixed. |
| 7 | 246 | What the Claude CLI sends itself (email hint, env message, session-name request) | Duplicate | = F6 (extra Opus request per turn?). The email/env facts are background for F6. |
| 8 | 249 | Character sheets into the cached head? | Theoretical | An optimisation (a few thousand cached tokens); never a table complaint. Open decision of Tobi (changes the order in `docs/conventions.md`). |
| 9 | 256 | DMBrain #1: `!redo` after a suppressed turn deleted the turn before | Duplicate | = N3. **[code fixed, live-unverified]** test `tests/test_orchestrator_open_findings.py::test_redo_after_a_suppressed_turn_keeps_the_turn_before_it` (passed). |
| 10 | 258 | DMBrain #2: `clear_history` swapped the list; in-flight turn lost | Duplicate | = N4. **[code fixed, live-unverified]** `…open_findings.py::test_a_turn_still_in_flight_survives_the_compaction_wipe` (passed). |
| 11 | 262 | DMBrain #3: turn appended during summarize lost at the history cap | Duplicate | = N4. **[code fixed, live-unverified]** `…open_findings.py::test_a_turn_appended_during_summarize_survives_at_the_history_cap` (passed). |
| 12 | 268 | DMBrain #4: opening after a player turn queued dice markers | Duplicate | = N7. **[code fixed, live-unverified]** `…open_findings.py::test_an_opening_after_a_player_turn_requests_no_dice` (passed). |
| 13 | 270 | DMBrain #5: discarded consistency retry leaves its markers | Theoretical | Batch path only: the consistency guard runs in the non-streaming branch (`dmbot/voice/delivery.py:877-880`, ADR 045 "streaming logs only"); evening config is `DM_STREAMING=1`, `stream`. No `[consistency] regenerated` line in the kept logs. xfail `…::test_a_discarded_consistency_retry_leaves_no_markers_behind`. |
| 14 | 272 | DMBrain #6: intro retry leaves the discarded answer's markers | Theoretical | Batch path only (`dmbot/voice/dmcog.py:570-578`, "Streaming !intro can't"). xfail `…::test_a_discarded_weak_opening_leaves_no_markers_behind`. |
| 15 | 274 | DMBrain #7: empty echo retry stored as empty turn (batch path) | Theoretical | Batch path only (`DM_STREAMING=0` / `nahtlos`). xfail `…::test_an_empty_echo_retry_stores_no_empty_turn`. |
| 16 | 276 | DMBrain #8: journal replay fields belong to the next turn (13 of 22) | Theoretical | Seen in journals, never at the table: it only falsifies offline tooling (a live golden, the `aux_parity` recorded column). xfail `…::test_a_turn_started_during_playback_leaves_the_previous_turns_replay_fields`. **Wavering.** |
| 17 | 280 | DMBrain #9: final sentence on `?“`/`.“`/`!“` dropped | Duplicate | = N6. **[code fixed, live-unverified]** `…open_findings.py::test_a_final_sentence_ending_on_the_german_closing_quote_is_spoken_and_stored` (passed). |
| 18 | 285 | DMBrain #10: `!redo` of a turn with a scene impulse runs without it | Felt at the table | The redo of a scene's first turn after a join loses the scene's director impulse (narration drifts from the scene goal) and counts as an extra scene turn. Unfixed: `session/scenes.py:196` counts up before the redo builds, `session/persistence.py:105`. Derived from a 133-token prompt gap. **Wavering.** |
| 19 | 290 | DMBrain #11: journal rotates only on `!leave` | Felt at the table | Unfixed: only call site `dmbot/voice/voicecog.py:363`. Felt across evenings: the campaign memory (ADR 054) misses evenings that ended without `!leave` (1 of 19 starts ended with it) and later files four days as one session. |
| 20 | 294 | DMBrain #12: two sentence-end rules contradicted each other | Duplicate | = N6. **[code fixed, live-unverified]** `dmbot/llm/sanitize.py:18` imports `textsplit.SENTENCE_END`; test `tests/test_tts_chunk.py::test_sanitizer_uses_the_same_rule` (passed). |
| 21 | 296 | DMBrain #13: `!start`/`!intro` mid-turn makes the player turn lose its `<<TEST>>` | Theoretical | Needs someone typing `!start` while the DM streams. Unfixed: `dmbot/orchestrator.py:965` reads `session.last_action` at queue time. No test. |
| 22 | 300 | DMBrain #14: exception in `respond`, then `!redo` → journal replaces the turn before | Theoretical | Needs a failed turn followed by `!redo` and a restart; derived from code. No test. |
| 23 | 306 | DMBrain #15: no ✂ line under Ollama (`done_reason` unread) | Theoretical | Ollama narrator only; Tobi left it out on purpose (13.11.). Still true: no `done_reason` in `dmbot/llm/client.py`. |
| 24 | 311 | Pause: a turn flushes buffers and queries RAG before the client refuses | Theoretical | Only during a Claude outage (D139 never live); costs one embedding per mic release. |
| 25 | 313 | Pause: return while frozen with Esc gets no own turn | Theoretical | Needs an outage and an Esc freeze at once; pending lines wait for the next player line. |
| 26 | 315 | Pause: "turn pending" is a session flag, not a return value | Theoretical | Design note; no observed effect. |
| 27 | 317 | Pause: dice results / director notes of two concurrent turns can swap order | Theoretical | Needs two overlapping turns plus a reordering; never observed. |
| 28 | 318 | Pause: a call started in the pause and failing after it is queued without a new ⏸ line | Theoretical | Narrow timing window; never observed (D139 never live). |
| 29 | 320 | `ON_FAILURE` in `config.py` and `failover.py` | Done | The duplicate is pinned: `tests/test_llm_pause.py::test_config_and_pair_know_the_same_positions` (passed) asserts `config.LLM_ON_FAILURE` (`config.py:19`) == `failover.ON_FAILURE` (`failover.py:44`). |
| 30 | 321 | Ollama path / `fallback`: stream failing before the first delta stores an empty answer | Theoretical | Not the evening config (`DM_LLM_ON_FAILURE=pause`). Still true: `dmbot/orchestrator.py:805-806` catches every error. |
| 31 | 326 | ↩ carries the wrong figures when the next turn started (ADR 062 #6) | Theoretical | Needs ↩ inside the undo minute after the next turn began. Unfixed: `SceneUndo` (`dmbot/rules/scene_flow.py:90-100`) keeps no names. |
| 32 | 329 | `_turn_sightings` survives `!leave`/`!join` (#7) | Theoretical | Needs `!ort` before the first turn of a new session. Unfixed: cleared only at `session/scenes.py:197`. |
| 33 | 332 | NPC prompt asks "statblock = name" for every candidate, schema forbids it (#8) | Theoretical | Without effect while every card figure has a statblock (both adventures). Still true: `dmbot/llm/npc_router.py:100` vs `:138`. |
| 34 | 335 | German log lines in `session/scenes.py` (#10) | Theoretical | Convention, not behaviour. Still German (`session/scenes.py:99, 427-431`) — and `phase-11-abend.md` F7/N1/N2 grep for exactly these strings. |
| 35 | 339 | Die does not spin in the throw GIF | Felt at the table | Visible in every throw GIF. Still true: `tools/dice_throw.py:32` sets `angle`, nothing ever adds `w*dt`. Tobi decides (memory: preview first). |
| 36 | 341 | Dice caches grow without cleanup | Theoretical | Disk and `#bot-commands` clutter only; no cleanup in `dmbot/dice_assets.py`. |
| 37 | 344 | Discord load gap on the image swap | Felt at the table | A short blank picture during the throw — **accepted** by Tobi: `docs/decisions/064-stored-throw-gifs.md:58-60` and D133. Not open any more. |
| 38 | 348 | Larger `CLAUDE_NUM_CTX` (e.g. 65536) | Duplicate | = NCS candidate "`CLAUDE_NUM_CTX` 24 576 → 32 768" (`progress.md:74`); default at `dmbot/config.py:408`. |
| 39 | 349 | `cache=0` in almost every Opus turn | Duplicate | = F5. **[code fixed, live-unverified]** D142 stable head: `dmbot/llm/prompt_assembly.py:53-74`, `claude_client.py:132-142`; test `tests/test_claude_client.py::test_a_dm_turn_writes_only_the_stable_head_into_the_system_file`. |
| 40 | 350 | Recap on Nemo gets capped (`num_predict` 400) | Theoretical | Only when Nemo narrates; on Claude the cap is lifted (`dmbot/llm/__init__.py:70-85`), and `pause` keeps Nemo out. |
| 41 | 351 | `DM_STREAMING=0` on Claude has no speech cap below ~1244 tokens | Theoretical | Not the evening config (says so itself). |
| 42 | 354 | Facts: classifier only adds, retraction manual (`!fakt weg`) | Theoretical | No table case recorded; deliberate scope, held by ADR 058 amendment (`docs/decisions/058-*.md:83-95`). |
| 43 | 356 | `!ortmodus frei` acts only on the marker | Theoretical | Nobody runs `frei`. Still true: `_scene_mode` is read only at `dmbot/voice/delivery.py:221`. |
| 44 | 357 | Discord load of the panel; a 429 vanishes in a warning | Felt at the table | Seen once: `logs/debug-bis-2026-11-14.log:12045-12057` (13.11., 00:40:17–00:40:26), three 429s on one `PATCH …/messages/…` during a scene change, ~13 s of retries → a panel/overlay edit lags. Which message it was is not logged. **Wavering.** |
| 45 | 358 | Three movers on one scene pointer — count `scene_move` triggers | Theoretical | No conflict seen. Partial count exists: 14.11. all three moves came from Opus' fallback `<<ORT>>` marker (`phase-11-abend.md:237`). |
| 46 | 361 | Deterministic meta-sentence filter (D112); residual: incomplete sentence in the stream | Done | `dmbot/llm/sanitize.py:137` (`_drop_meta_sentences`); tests `tests/test_meta_filter.py::test_every_handover_wording_from_the_live_run_goes`, `::test_an_npc_may_apologise_in_dialogue` (both passed). The residual is by construction, not a task. |
| 47 | 364 | STT hallucination blocklist (D114); residual: maintenance | Done | `dmbot/stt/segments.py:93` (`is_stock_phrase_only`), used at `dmbot/stt/transcriber.py:242-246`; test `tests/test_stt_blocklist.py::test_the_combination_from_the_live_run_is_blocked` (passed). Maintenance is standing practice. |
| 48 | 367 | Stall detector: push the story after N turns without progress | Felt at the table | The hang of 14.11., 19:25–19:31 ("Das bewegt sich einfach nicht weiter", `phase-11-abend.md:256-264`). D140/D141 target it (F2); a partial net exists (`dmbot/voice/dicecog.py:181`, `🎲 Sicherheitsnetz`). **Wavering** (vs. duplicate of F2). |
| 49 | 369 | Speech-mode default stays `stream`+`flach` until compared | Duplicate | = LRS:169-171 (parked: "`!sprechmodus nahtlos` live gegen `stream`/`puffer` hören — Kandidat für den neuen Default"). Open decision of Tobi. |
| 50 | 372 | Live model comparison Nemo vs Mistral Small | Duplicate | = LRS:28-30 (parked: "Der Modell-A/B-Test (Mistral Small etc.) kommt erst NACH der Gate-Session"). |
| 51 | 374 | Dice RNG replay deferred | Theoretical | Only matters when a refactor touches roll→damage; the deferral is held in `docs/decisions/046-*.md:100-102`. |
| 52 | 376 | First live golden missing | Duplicate | = LRS:399-400 (parked step 3) and blocked by #16: `tests/golden/` holds only synthetic files. |
| 53 | 379 | `!intro` prose richness | Duplicate | = LRS:196-202 (parked Akt 3) for content, F10 for the table's verdict on prose. **Wavering.** |
| 54 | 384 | Golden-rules conformity skill | Theoretical | Tooling idea, deliberately parked; no such skill in `.claude/skills/`. No table effect. |
| 55 | 388 | `!lore tts` reads each block twice (Bot A?) | Duplicate | = LRS:365-366 (parked "Nebenbei": one `🔊 TTS` + one `/speak` per block ⇒ Bot A). |
| 56 | 392 | Weapon / stat-block tables don't retrieve | Felt at the table | A weapon rule question gets no rulebook chunk (golden rule #7). Still open: `data/rules_de/` holds only `conditions.md`. |
| 57 | 396 | Smoke test after the cog split (June) | Theoretical | Overtaken: `!join`→speak→dice→scene ran live many times since, last on 14.11. (`phase-11-abend.md:235-237`). "Probably done, unproven" in code terms. **Wavering.** |
| 58 | 400 | Deferred altitude debt (IM arithmetic in the engine, IM RAG catalog) | Theoretical | Only with a second system (Phase 10b). Still in code (`dmbot/rules/engine.py:94, 287`, `dmbot/rag/retrieve.py:96, 121`); bound by `docs/decisions/030-codereview-correctness-round.md:86-109`. |
| 59 | 404 | `!lore` answers about Rokarth are English | Felt at the table | A Rokarth `!lore` question shows English chunks. Still true: `setting` is a `!lore` source (`dmbot/voice/lorecog.py:35`). Low weight, since June unnoticed. |
| 60 | 408 | Phase 7: latency grows with context; auto-recap is the fix | Done | Auto-recap triggers on `ctx_over_budget` at `dmbot/voice/dmcog.py:661`; test `tests/test_autorecap.py::test_ctx_over_budget_is_the_compaction_trigger` (passed). Ran live 13.11. and 14.11. (`phase-11-abend.md:239`). |
| 61 | 411 | Loose ends Phase 3: one `!join` `TimeoutError`; Silero idle CPU | Theoretical | No `TimeoutError` in any kept log (`logs/*.log`, `logs/archive/`); Silero cost judged fine. |
| 62 | 414 | Streaming watch items (meta-ramble, `first_audio`/`tts=` gaps, `gen=` caveat) | Duplicate | = LRS:165-168 and LRS:369-371 — the entry says so itself. |

## 2. Proposal

### 2a. Struck (10) — nothing open is left

| # | Line | Reason |
|---:|---:|---|
| 29 | 320 | Done; the test keeps both lists equal, nothing to decide. |
| 46 | 361 | Done (D112); the stream residual is a property of incremental filtering, not a task. |
| 47 | 364 | Done (D114); "add what slips through" is the normal triage loop, the `🚫` line shows coverage. |
| 60 | 408 | Done (ADR 027); the baseline is measurement A of every evening now. |
| 37 | 344 | Decided trade-off, recorded in ADR 064:58-60 and D133. |
| 42 | 354 | Deliberate scope, recorded in the ADR 058 amendment; an additive extension when a table case appears. |
| 51 | 374 | Deferral recorded in ADR 046:100-102 with its own trigger. |
| 57 | 396 | Overtaken by every live run since June; no residual. |
| 58 | 400 | ADR 030:86-109 binds it to the second system; Phase 10b is in the roadmap. |
| 61 | 411 | Not seen again in five months; "only observe" has run its course. |

### 2b. Absorbed by an existing counterpart (18) — removed here, content lives on there

| # | Line | Goes into | Reason |
|---:|---:|---|---|
| 1 | 231 | F9 | Same check; add to F9: "if it fails, the remedy is a heading line before the block (prompt change, `dm-eval` + run)". |
| 2 | 235 | F5 | F5 already checks the cache; add "and no `spoken narration call without a stable system-prompt head` ERROR". The refactor (pass the head through the seam) only if that ERROR shows. |
| 39 | 349 | F5 | Exactly F5's question. |
| 5 | 241 | NCS "ADR 066 B einschalten?" | Same preconditions; add the two missing pieces there (dm-eval classifier category; addenda to lesson `mandatory-decisions-need-a-separate-classifier` and ADR 057/058/062). |
| 7 | 246 | F6 | Same question; the email/env message are background, F6 asks the cost. |
| 38 | 348 | NCS candidate `CLAUDE_NUM_CTX` | Same experiment; note 65536 as the second step there. |
| 9 | 256 | N3 | Code fixed with test; only the live check is open, and N3 is it. |
| 10 | 258 | N4 | Same. |
| 11 | 262 | N4 | Same. |
| 12 | 268 | N7 | Same. |
| 17 | 280 | N6 | Same. |
| 20 | 294 | N6 | Same. |
| 49 | 369 | LRS:169-171 (parked) | Open decision of Tobi; the parked item holds it word for word — must survive the re-sighting of the parked gates. |
| 50 | 372 | LRS:28-30 (parked) | Same experiment; after ADR 061 it is a question about the fallback model only. |
| 53 | 379 | LRS:196-202 (parked) + F10 | Content check parked, prose verdict is F10. |
| 55 | 388 | LRS:365-366 (parked) | The same debug.log test; the fix lives in `Pr0degie/musicbot`. |
| 62 | 414 | LRS:165-168, 369-371 | The entry itself says it is in the script. |
| 54 | 384 | Part 2 backlog (one line) | A parked tooling idea, not an open question; keep it findable as a backlog line. |

(18 entries absorbed, line 384 included. #52 is not here: it goes into merged item A, whose
fix unblocks the parked live-golden step LRS:399-400.)

### 2c. Merged (25 entries → 8 new items)

| New item | From | Proposed wording (one sentence) |
|---|---|---|
| **A — Replay data from overlapping turns** | 16, 6, 52 | When the next turn starts before a turn's playback/autosave ends, its replay fields and post-turn notes (incl. `state_before`) land on the wrong journal record (13 of 22 on 13.11., record 24 on 14.11.), so no live golden can be drawn and the `aux_parity` recorded column stays information only until fixed (xfail `test_a_turn_started_during_playback_leaves_the_previous_turns_replay_fields`). |
| **B — Gaps outside the evening config** | 13, 14, 15, 23, 30, 40, 41 | Known gaps on the batch (`DM_STREAMING=0`, `nahtlos`), Ollama-only and `fallback` paths — retry markers left behind (two xfails), empty echo retry stored (xfail), no ✂ line under Ollama (Tobi: deliberately left out), empty answer after a stream fails before the first delta, Nemo recap capped at 400, no speech cap on Claude batch — revisit when one of these paths is played again. |
| **C — Pause edge cases (D139 review)** | 24, 25, 26, 27, 28 | Five edge cases of the pause (an embedding per mic release while paused, an Esc-frozen return without its own turn, "turn pending" as a session flag, swapped order of two concurrent turns' dice/director notes, a call that began in the pause and fails after it) are looked at again only if Teil B of the next run shows something. |
| **D — Turn-sighting bookkeeping (ADR 062)** | 31, 32 | ↩ inside the undo minute carries the next turn's sightings instead of the moved figures, and `_turn_sightings` survives `!leave`/`!join`; fix idea: keep the carried names on `SceneUndo` and clear the sightings on leave. |
| **E — LLM seam hygiene** | 3, 4 | `marker_decides` names `"claude"` at a dice site and chat→wait_for→JSON exists four times (plus two separate-ask paths) — one hook and one helper in `dmbot/llm`. |
| **F — Who moves the scene pointer** | 43, 45 | On 14.11. all three moves came from Opus' fallback `<<ORT>>` marker and none from the exit classifier, and `!ortmodus frei` acts only on that marker path — recount the `scene →` triggers at the next run. |
| **G — Dice animation follow-ups** | 35, 36 | The die does not spin (`tools/dice_throw.py` never integrates `angle`; Tobi decides, preview first), and old `gif_version` files in `data/dice/anim/` and `#bot-commands` are never cleaned up. |
| **H — RAG content gaps** | 56, 59 | Weapon/stat-block table rows don't retrieve (fix: a German weapon glossary under `data/rules_de/`) and `!lore` answers about Rokarth come from the English setting guide. |

### 2d. Kept as they are (9)

| # | Line | Reason |
|---:|---:|---|
| 8 | 249 | Open decision of Tobi (cached head vs prompt order); no counterpart. |
| 18 | 285 | Unfixed, no test, felt (weakly) on a redo; needs its own fix. |
| 19 | 290 | Unfixed, felt across evenings in the campaign memory; a cheap fix (rotate on shutdown/next join). |
| 21 | 296 | Unfixed, no test; distinct root (per-turn `queued` in the prepare step). |
| 22 | 300 | Unfixed, no test; loses a turn after a restart. |
| 33 | 332 | Bites with the first new adventure whose card figure lacks a statblock (`author-adventure`). |
| 34 | 335 | A real convention conflict to decide: translate, or allow German operator lines — the playbooks grep for them. Suggested rewording: "German operator log lines: allow them in CLAUDE.md or translate them (the `phase-11-abend.md` checks grep these strings)". |
| 44 | 357 | Now with evidence (13.11., 00:40, three 429s); reword to "count `429` warnings at the next run; once seen during a scene change". |
| 48 | 367 | Reword to "Stall detector — build only if F2 fails at the next run"; it is the next lever after D140/D141. |

## 3. Counts

| Category | Entries |
|---|---:|
| Felt at the table | 8 (#18, 19, 35, 37, 44, 48, 56, 59) |
| Theoretical only | 32 |
| Done | 4 (#29, 46, 47, 60) |
| Duplicate | 18 (#1, 5, 6, 7, 9, 10, 11, 12, 17, 20, 38, 39, 49, 50, 52, 53, 55, 62) |
| **Total** | **62** (59 bullets/numbered + 3 paragraphs) |

Among the duplicates, 7 are **[code fixed, live-unverified]**: #9, 10, 11, 12, 17, 20, 39.

| Proposal | Entries |
|---|---:|
| Struck | 10 |
| Absorbed by a counterpart | 18 |
| Merged | 25 → 8 new items |
| Kept | 9 |
| **Left in the list** | **17** (9 + 8) |

## 4. Wavering — entries between two categories

| # | Line | Between | Why this choice |
|---:|---:|---|---|
| 2 | 235 | theoretical / done | The ERROR log makes the failure loud but does not prevent it; "done" would hide the proposed refactor. |
| 16 | 276 | theoretical / felt | Observed in journals (not "never seen"), but invisible to players; it bites the ADR 066 parity runs and goldens, not the table. |
| 18 | 285 | felt / theoretical | Derived from a prompt-size gap, never heard; only a redo of a scene's first turn after a join. |
| 44 | 357 | felt / theoretical | One 429 burst in a log; unknown which message lagged and whether anyone noticed. |
| 46, 47 | 361, 364 | done / theoretical | Both carry a residual line; chose "done" because the residual is inherent (stream) or routine (blocklist upkeep). |
| 48 | 367 | felt / duplicate of F2 | The hang was felt; F2 checks the D140/D141 fix, not a stall detector — so it stays, conditional on F2. |
| 49, 50, 53, 55, 62 | — | duplicate / keep | Their counterpart sits in the **parked** live-run script, not in an open gate; if the re-sighting after the evening drops a parked item, the open question goes with it. #49 holds an open decision of Tobi. |
| 53 | 379 | duplicate / felt | LRS Akt 3 checks the intro's content, not whether the prose sounds formulaic; F10 covers that only as a general verdict. |
| 57 | 396 | done / theoretical | Live evidence is overwhelming, but there is no code or test to point at, so by the rule it is not "done". |
| 35 | 339 | felt / theoretical | Visible in every GIF since 30.10., yet nobody has complained. |
| 37 | 344 | felt / duplicate | Felt, but its counterpart is an ADR, not a check point — so "felt", struck as decided. |

## 5. Not settled

- **The 429 message (#44):** the log names only the message id; whether it was the player panel, the
  debug overlay or the scene-change post is not recorded.
- **Redo without impulse (#18):** the prompt itself is not logged; the gap is inferred from token
  counts, as the entry says.
- **Pause edge cases (C) and #28:** D139 has never run live; none of them can be checked offline.
- **F6 / #7:** whether the CLI's session-name request costs quota is only answerable from a run.
- **#19:** how much the campaign memory actually misses would need a look into the session store
  (not done: data files not read).
- **#55:** whether `!lore tts` still doubles needs a live debug.log; the fix would be in Bot A's repo.
- **The die spin (#35):** whether the static die is intended is a question for Tobi.
- **Count:** "rund 59" matches the bullets and numbered findings; the three unbulleted paragraphs
  at lines 408/411/414 (and the two items inside line 411) are counted as one entry each.
