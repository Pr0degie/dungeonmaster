# ADR 053 — Journal scene events + in-game time on turns (prep for session RAG)

- **Status:** Accepted
- **Date:** 2026-07-17
- **Refs:** extends the **ADR 046** replay journal (whose skip-semantics make this backward
  compatible) with the scene pointer from **ADR 026/043** and the minutes counter from
  **ADR 048**. Prep for the session-transcript retrieval round (semantic RAG over rotated
  `history.jsonl` files). Touches `dmbot/runtime.py`, `dmbot/voice/dmcog.py`,
  `dmbot/memory/history.py` (docstring only).

## Context

The upcoming session-RAG round chunks rotated `history.jsonl` files per scene and stamps
chunks with in-game time. Today the journal records neither: scene changes live only in
`WorldState.scene_id` (code-owned, ADR 026), and turn records carry only the real-time
`ts`. Both signals must land in the journal *as sessions are played*, so the ingest can
chunk cleanly without re-deriving state.

## Decision

1. **Scene journal event.** Whenever `scene_id` actually changes, the single mutator
   `runtime._set_scene` appends `{"kind": "scene", "scene_id", "ts"}` via the existing
   `append_event`. Additionally every `!join` (`seed_session`) writes the current scene
   right after the ADR-046 session header — covering both the fresh start-scene seed and
   a *restored* pointer, so a rotated-fresh journal always opens with a scene before the
   first transition. Same-scene `!ort` calls write nothing (no boundary).
2. **In-game time on turn records.** The autosaved per-turn record carries
   `time_minutes` (the channel's `WorldState.time_minutes` at turn completion, ADR 048)
   via `append_turn`'s existing `extra` mechanism. Metadata for the ingest only — no
   renderer or prompt consumes it.
3. **Backward compatible by ADR 046's skip-semantics.** `load_recent` skips records
   without `user_msg`+`answer`, so scene events are invisible to crash restore and
   dm-eval; old journals simply lack `time_minutes` and every reader must tolerate its
   absence. `load_recent`, redo collapse, rotation and torn-line tolerance are unchanged
   (pinned by tests).

## Alternatives

- **Deriving scene boundaries at ingest time from recorded `state_before` snapshots:**
  rejected — only turns with replay capture carry them, and reconstructing boundaries
  from diffs re-implements state logic the mutator already knows at write time.
- **A separate sidecar file for ingest metadata:** rejected — ADR 046 already settled
  this (one journal per session; loader tolerance makes extensions free).

## Consequences

- **+** Every session played from now on is chunkable per scene with a time anchor —
  the ingest round consumes the journal as-is.
- **−** Journals rotated before this ADR have no scene events; the ingest treats such a
  file as one chunk (or falls back to turn-count chunking) — its problem, not the
  journal's.
- **−** A crash-restored session (`!join` on an unrotated file) writes a duplicate scene
  event mid-file; consumers must tolerate consecutive events with the same `scene_id`.
