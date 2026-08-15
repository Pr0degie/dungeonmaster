# Lessons — recurring corrections, confirmed the hard way

A memory layer distinct from the ADRs: **ADRs hold decisions; lessons hold corrections and
confirmed approaches that kept getting rediscovered** across sessions. Mined from the
progress archive, the decision log, and ADRs 001–051 (2026-07-11).

**How to use:** skim this list at session start (part of the CLAUDE.md ritual); open a full
lesson only when its summary touches the task. **How to maintain:** record new corrections
as they happen — update the existing lesson rather than duplicating it, delete lessons
proven wrong, keep this index in sync. Don't record what CLAUDE.md, `docs/conventions.md`,
or an ADR already holds — link there instead.

## The lessons

### LLM behaviour
- [deterministic-guards-over-persona-hopes](deterministic-guards-over-persona-hopes.md) —
  Prompt instructions don't hold a 12B model; code owns removal, the prompt only shapes.
- [llm-requests-code-validates](llm-requests-code-validates.md) — The feature template:
  LLM requests → code validates/clamps → confirm button → kill-switch; new LLM work rides
  an existing call, never a new one.
- [mandatory-decisions-need-a-separate-classifier](mandatory-decisions-need-a-separate-classifier.md) —
  Inline markers fail model-size-independently; mandatory decisions get their own
  constrained-JSON call, inline markers only for optional confirmed proposals.
- [sampling-defaults-leak-into-aux-calls](sampling-defaults-leak-into-aux-calls.md) —
  Client-wide temperature/penalty defaults sabotage specific call types; every call type
  pins its own sampling.

### Pipeline & delivery
- [spoken-audio-cannot-be-retracted](spoken-audio-cannot-be-retracted.md) — Quality guards
  are batch-first with log-only streaming degradation, or the fix moves upstream into
  sampling.
- [optional-layers-fail-open-core-fails-loud](optional-layers-fail-open-core-fails-loud.md) —
  Optional guards degrade loudly with a kill-switch and never block the table; the dice/
  state core never swallows errors.
- [tts-input-whitelist-spoken-copy](tts-input-whitelist-spoken-copy.md) — TTS sanitizing by
  blocklist always leaks; NFKC + whitelist on a spoken-only copy, per-chunk speakability
  guard.
- [two-silent-budgets-context-and-chars](two-silent-budgets-context-and-chars.md) — Context
  overflow silently truncates the persona; spoken chars ARE the latency — read the
  `[latency]` line before blaming model or infrastructure.

### Code structure & async
- [parity-by-construction](parity-by-construction.md) — The same value computed in two
  places WILL desync; extract one shared pure function when the second path arrives.
- [snapshot-state-at-event-time](snapshot-state-at-event-time.md) — State read after an
  `await` is the recurring race class; snapshot at event time, refcounts over booleans.
- [byte-exact-moves-stepwise-gates](byte-exact-moves-stepwise-gates.md) — Refactors: slice
  don't retype, zero test edits as the signal, all gates green after every step; review the
  new logic, not the moves.
- [isolation-must-enumerate-every-artifact](isolation-must-enumerate-every-artifact.md) —
  "Isolated" is per artifact, not per feature; enumerate every shared file/table, route them
  through one seam, and assert the two path sets are disjoint.

### Config, dependencies & ops
- [unwired-knobs-and-silent-fallbacks](unwired-knobs-and-silent-fallbacks.md) — Unread
  config and data-substituting fallbacks fail silently for weeks; prove the knob is wired,
  make every fallback announce itself.
- [incidents-become-preflights](incidents-become-preflights.md) — Every external-state
  incident becomes a boot preflight, pin, canary, or fingerprint diff — build the check,
  not just the fix.
- [read-the-installed-library-source](read-the-installed-library-source.md) — The truth is
  in the installed library's code; mock its real contract, not your mental model.

### RAG & live process
- [topk-post-filter-starves-partition-the-index](topk-post-filter-starves-partition-the-index.md) —
  KNN `k` is global per table and the source filter prunes after; a minority corpus behind a
  shared index gets starved — partition by table, and make rowid-keyed mirrors self-healing.
- [rag-misses-are-content-gaps](rag-misses-are-content-gaps.md) — Retrieval misses are
  fixed by content (language, curated German, term in the chunk body, shape), never by the
  threshold; threshold changes need golden-set evidence.
- [one-variable-per-live-run](one-variable-per-live-run.md) — Never confound a scarce live
  session: tune, verify the baseline live, only then A/B.
