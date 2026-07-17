# ADR 055 — Debug-run sandbox for session memory + gate G10 on the existing seeds

- **Status:** Accepted (code-complete; the live table run is the verification, gate G10)
- **Date:** 2026-07-17
- **Refs:** replaces the ingest *skip* left by **ADR 054** (decision 5) at the
  `SessionRuntime._session_ingest_source` seam; the debug-run marker rides the **ADR 052**
  `testplan.json` sidecar (whose LLM-invisibility invariant stays test-pinned) and the
  **D41/ADR 046** rotation; runbook: `docs/debug-campaign-runbook.md`. Touches
  `dmbot/memory/history.py`, `dmbot/voice/voicecog.py`, `dmbot/runtime.py`,
  `dmbot/rag/ingest_session.py`, `dmbot/rag/retrieve.py`.

## Context

The debug campaign "Die Mitternachtsfracht" is played in the SAME Discord channel as live
play (`circlejerk`), so debug-run archives and the live session store would share one
directory and one `session_<channel_id>` RAG source. ADR 054 stopgapped this by skipping
ingest for debug runs entirely — which also means the session-RAG feature (ADR 054) has no
gate in the debug campaign: nothing exercises ingest, catch-up, or retrieval at the table.
Worse, the runbook's reset instructions sat one careless delete away from real session
archives. Two goals, strictly additive: make the feature testable as gate **G10**, and make
cross-contamination between debug and live memory structurally impossible.

## Decision

1. **File-presence detection.** A run is a debug run iff a `testplan.json` exists next to
   the loaded `adventure.json` — a pure path check (`SessionRuntime.is_debug_run`),
   deliberately independent of `DM_DEBUG_OVERLAY` (the overlay may be off while the debug
   campaign is still played). Only the file's *presence* is used; its content never reaches
   any prompt or RAG path, so the ADR 052 invariant (and its source-inspection test) holds
   unchanged. The word "testplan" stays confined to `runtime.py` — every other module
   speaks only of "debug runs".
2. **`.debug` rotation marker.** During a debug run, `rotate()` names the archive
   `history.<stamp>.debug.jsonl`. The filename is the durable marker: in a directory shared
   with live archives it keeps debug records distinguishable forever, survives restarts and
   mode switches, and lets every later consumer route without any session-state lookup.
3. **Routing by filename, isolation by construction.** Ingest maps `.debug` archives to
   `session_debug_<channel_id>` and plain archives to `session_<channel_id>` — keyed on the
   filename alone, so no caller can cross-route. The `!join` catch-up scans only the current
   mode's archives (separate stamp bookkeeping per source); retrieval in a debug run reads
   only the debug source and a normal run never does (`debug_sessions` on the retriever,
   set from the same path check). Both directions are pinned by tests, not convention.
4. **Reset tooling.** `python -m dmbot.rag.ingest_session --wipe-debug <channel_id>`
   deletes only the sandbox source's rows (chunks, vec + FTS mirrors, stamp bookkeeping) —
   the runbook reset can now re-run the debug campaign without touching live memory, and
   the runbook warns explicitly that plain archives are real session records.
5. **G10 reuses the G9 seeds.** No new scenes, no new campaign content: the G9 session-2
   callbacks (Münze from `schrein`, Fenks Hymne from `pfandhalle`) double as G10 probes —
   one natural-language question (semantic/KNN) and one proper-name question mid-sentence
   (FTS). Evidence is the already-existing log lines (`🗂 session memory: ingested …`,
   `🗂 Szene …`) plus one new catch-up line on `!join` — the only previously silent step.

## Alternatives

- **Keep the ADR 054 skip:** rejected — the session-RAG feature would stay untestable in
  the debug campaign, and the shared-channel delete hazard in the reset would remain.
- **Detection via `DM_DEBUG_OVERLAY`:** rejected — the kill-switch exists precisely so the
  campaign can be played with the overlay off; sandbox-ness must not flip with a UI toggle
  mid-campaign (a half-debug store would contaminate one side or the other).
- **A separate rag.db for debug runs:** rejected — a second store forks the degrade story,
  the per-thread connection cache, and the calibration tooling; a separate *source* in the
  same store gives the same isolation with the machinery that already exists (ADR 021/054).
- **Session-state or env-var routing at ingest time:** rejected — only the filename travels
  with the archive; anything else can desync between rotation and (much later) catch-up
  ingest, which is exactly how a debug archive would leak into the live source.
- **New G10 scenes/seeds in the campaign:** rejected — the second session already exists
  for G9; new content would violate the additive-only constraint and test authoring, not
  the feature.

## Consequences

- **+** The debug campaign now exercises the full ADR 054 path (rotate → ingest → catch-up
  → hybrid retrieval) as gate G10, with greppable evidence, at zero risk to live memory.
- **+** A debug re-run resets cleanly: delete `.debug` archives + `--wipe-debug`; live
  archives and their store rows are structurally out of reach.
- **−** One more filename shape (`history.<stamp>.debug.jsonl`) every journal consumer's
  pattern must consider — centralized in `_STAMP_RE`/`is_debug_archive`.
- **−** Playing the debug campaign *without* a `testplan.json` (file deleted) would ingest
  into the live source; the runbook treats the sidecar as part of the campaign.
- **Live-unverified:** the G10 table run itself (two short sessions) — it rides the already
  planned debug-campaign run and opens no new live-gate slot beyond it.
