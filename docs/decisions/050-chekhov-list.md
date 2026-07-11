# ADR 050 — Chekhov list: unresolved threads extracted at wrap-up, callbacks offered to the DM

- **Status:** Accepted
- **Date:** 2026-07-04
- **Refs:** decision log **D97** in progress.md, architecture.md §7 (memory). Extends
  **ADR 044** (NPC memory — this rides the *same* wrap-up extractor call) and follows the
  narrative-layer precedent of the recap (§7b) and ADR 044/049: **LLM writes the prose, code
  owns the list** (cap, dedupe, status — golden rule #3 in spirit). Touches
  new `dmbot/memory/chekhov.py`, `dmbot/memory/npc_memory.py`, `dmbot/runtime.py`,
  `dmbot/voice/dmcog.py`, new `dmbot/voice/chekhovcog.py`, `prompts/dm_core_de.md`,
  new `prompts/chekhov_extract_de.md`.

## Context

Human GMs remember loose ends and play them back later ("the coin from session one? *That*
coin."). The bot forgets them: the recap compresses the session into its main thread, NPC
memories are scoped to one NPC's knowledge, and quests track active objectives — none of them
keeps the *unresolved details*: a mentioned object, a hint, an open promise, an unanswered
question. Those are the raw material of callbacks, the thing that makes a campaign feel
authored rather than episodic.

Two tensions. First, granularity: threads are **session**-level (a human GM jots them down
after the evening, not after every room), so per-scene extraction would churn the list with
noise. Second, coverage: the existing wrap-up extraction call (ADR 044's `!wrap` catch-all)
only sees the history window *since the last scene-change extraction* — the final scene. A
detail dropped in scene 1 would be invisible to a wrap-up-only extractor, and that is exactly
the core use case.

## Decision

1. **The Chekhov list is a narrative layer (like recaps), but code-managed.** New
   `data/sessions/<session>/chekhov.json` beside the other session files, written atomically
   like `state.json`. Schema: `Thread{id, detail (one sentence), origin_scene,
   created_session, status: "open"|"resolved", weight: 1–3}`; ids are short sequential tokens
   (`t1`, `t2`, …) so commands stay typeable. Cap: **max 20 open** threads — on overflow the
   oldest open thread with the lowest weight present is evicted. Resolved threads are kept
   for display/history but capped at the newest 20.
2. **A separate file, deliberately.** ADR 044 argued *against* a separate `memories.json`
   (same lifecycle as state). Threads differ: the list is pure LLM prose curated by its own
   commands, and keeping it out of `state.json` keeps the code-owned state file free of a
   second narrative payload and lets Tobi inspect/edit it by hand. The lifecycle cost (one
   more file to delete on a session reset) is accepted.
3. **Extraction rides the ADR-044 wrap-up call only — one call, no per-scene churn.** At
   `!wrap`, the existing extractor call gains a `chekhov` output section
   (`{new: [{detail, weight}], resolved: [ids]}`, schema-forced): (a) up to **5 new**
   unresolved details per session (objects, hints, open promises, unanswered questions —
   explicitly NOT active quests, those live in `quests`), (b) ids of existing threads this
   session resolved. Scene-change extractions are unchanged. Parsing stays ADR-044-defensive:
   parse failure → skip + log, never block the wrap-up.
4. **Coverage fix for the window problem:** the wrap-up call's input additionally carries the
   session history *before* the extraction window as a clearly labelled context block
   ("bereits fürs NSC-Gedächtnis ausgewertet — hier nur nach losen Fäden durchsuchen"), plus
   the current open threads (numbered, for resolution detection and against re-recording).
   NPC memories stay bound to the scene window by prompt instruction; if the model overreaches
   into the old turns anyway, the existing gist-dedupe and the ±1 attitude clamp bound the
   damage. Trade-off accepted and preferred over a second LLM call.
5. **Code owns every hard effect.** New threads are deduped against *all* existing threads
   (open **and** resolved, so a resolved coin doesn't come back) via a normalised
   substring-/word-overlap comparison; details are truncated to one-sentence length; weights
   clamped to 1–3; the 5-per-extraction and 20-open caps are enforced in code. Resolution is
   **recognised, not forced**: the LLM names ids, code flips `status` — unknown ids are
   dropped + logged.
6. **Injection is deliberately small — an offer, not a mandate.** The **top 3** open threads
   (weight first, then age — *older* first, old threads make the best callbacks) render as a
   compact block appended to the world-state summary: „Lose Fäden (bei Gelegenheit
   aufgreifen, nicht erzwingen)". A persona paragraph in `dm_core_de.md` explains the block.
   No weaving into every answer, no forced callbacks.
7. **Commands — Tobi keeps his hands on the list.** Thin `ChekhovCog` (TimeCog precedent:
   distinct state, distinct commands): `!fäden` lists open + recently resolved,
   `!faden neu "<Detail>" [1-3]` seeds a thread by hand (human authority, and it makes the
   live gate testable without a full extraction), `!faden erledigt <id>`, `!faden weg <id>`.
8. **Kill switch inherited:** extraction rides inside the ADR-044 call
   (`DM_NPC_MEMORY=0` disables it); the prompt block renders only when threads exist. No new
   env knob.

## Alternatives

- **Per-scene extraction:** rejected — threads are session-granularity; a per-scene pass
  would churn the list with details the same session still resolves, and the dedupe would
  have to fight the extractor every scene.
- **A second, dedicated wrap-up LLM call:** rejected — the wrap-up already runs extraction +
  recap sequentially; the chekhov section is a few schema fields on a call that happens
  anyway, and one call keeps the ADR-044 budget intact.
- **Window-only input (no earlier-history block):** rejected — misses the core use case (the
  detail from scene 1). The labelled-context compromise keeps one call and bounded risk.
- **Storing threads in `state.json`:** rejected — see decision #2.
- **Auto-resolving threads by string-matching the session text:** rejected — resolution is a
  judgment ("was the coin's mystery actually answered?"), exactly what the extractor is for;
  code just flips the status it proposes.
- **Weaving the top threads into every answer / forcing a callback:** rejected — a callback
  lands because it *fits*; the block is phrased as an offer and capped at 3.

## Consequences

- **+** The DM gets a persistent supply of callbacks; a detail dropped in session 1 can
  resurface in session 3 — the "human GM" feel the recap alone can't provide.
- **+** Fully code-managed lifecycle (cap, dedupe, status, eviction) — pure-function testable
  like ADR 044/049; `chekhov.json` is human-readable and hand-editable.
- **−** The wrap-up extractor's input grows (earlier-session block + open threads); bounded
  by the auto-compacted history buffer and the 20-thread cap.
- **−** The model may mine NPC memories from the earlier-history block despite the
  instruction; bounded by the existing dedupe/clamps (documented, accepted).
- **−** Thread details are LLM prose in a session file — like `memories`, never to be read
  as hard facts.
- **Live-unverified:** whether nemo extracts *callback-worthy* details (and recognises
  resolutions) is a model-behaviour claim — the gate spans two sessions: drop a detail in
  session 1, wrap, check session 2 offers it back.

## Addendum — detail preserved from decision log D97 (2026-07-11)

- The extractor's `num_predict` was raised **800 → 1000** for the added chekhov schema section.
- Dedupe threshold: normalised substring match or word-Jaccard **≥ 0.6**.
- Test evidence from the round: suite **683 green** (+24 new tests).
