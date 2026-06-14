# ADR 034 — Extract orchestrator's pure helpers into dmbot/llm/* (context-leanness)

- **Status:** Accepted (E1–E3 landed; E4 `stream_assembler` + the `dmcog.py` splits deferred)
- **Date:** 2026-06-14
- **Refs:** decision log D70 in progress.md; same context-cost motivation as **ADR 032** (lean live
  docs vs. on-demand archive) and **ADR 029** (the voice god-cog → runtime + thin cogs). Governed by
  golden rules: marker grammar stays in `rules/marker.py`, prompt order in `_build_request` (ADR 019).

## Context
`dmbot/orchestrator.py` had grown to ~1175 lines — the second-largest hand-maintained file — so an
agent editing *any* part of it pulled the whole brain into context. A two-agent fan-out analysis
found the file was already two-tier: a band of **pure, module-level helpers** (sanitisers, echo
guards, director-message builders — all regex/text, zero `DMBrain` state) sitting above the stateful
`DMBrain` class. The pure band is exactly what gets edited most often in the playtest-tuning loop
(every "the model read X aloud" fix lands in the sanitisers), yet it has nothing to do with
`DMBrain`'s per-channel state. Extracting it makes those frequent edits a small focused file instead
of the whole brain. Tobi's directive: extract large/cohesive functions for token-efficiency, with
**no functional change**.

## Decision
Move the three pure clusters into new modules under `dmbot/llm/` and keep **re-export shims** in
`orchestrator.py` so every existing reference (tests, `DMBrain`, the streaming assembler, the cog)
keeps importing the names from `orchestrator` unchanged:
- `dmbot/llm/sanitize.py` — the spoken-answer sanitisers (`_ROLE_LABEL`, the meta/preamble/trailing
  regexes, `_cut_at_labels`, `_strip_leading_label`, `_sanitize*`, `_trim_to_last_sentence`).
- `dmbot/llm/echo_guard.py` — `is_echo` / `is_self_repetition` + the `_*_NUDGE` / `_ROLL_DIRECTIVE`
  strings (D43 / ADR 018, W4).
- `dmbot/llm/director_msgs.py` — `build_opening_director_msg` / `build_intro_director_msg` (ADR 031).

`orchestrator.py` 1175 → 933 lines. The move was done by a **byte-exact line-slice script** (no
retranscription of the intricate regexes), then verified: behaviour is identical — the suite is
**319 green**, unchanged, with no test edits (the re-exports keep the import surface stable).
`finalize_answer` and the `StreamAssembler` (E4) and the `DMBrain` body stay in `orchestrator.py`.

## Alternatives
- **Split the stateful `DMBrain` body too:** rejected — its ~20 per-channel dicts are read/written
  across prepare/generate/clear/summarize; splitting would either thread `self` around (no context
  saving) or fragment state ownership (correctness risk). Only the pure top band moves.
- **Repoint the test/cog imports to the new modules instead of re-exporting:** deferred — re-exports
  give a zero-diff, behaviour-identical landing now; a later cleanup can repoint imports if desired.
- **Also extract `_build_request` prompt assembly / the aux LLM calls (`classify_test`, `summarize`,
  `answer_rules`):** rejected for now — they read `DMBrain` state/client, so extraction re-couples
  for little gain. Prompt-order (ADR 019) is best left in `_build_request`.
- **Do it as hand-typed Edits:** rejected — the sanitiser block is ~130 lines of fragile German
  regex; a byte-exact slice eliminates transcription risk, which matters for "no functional change".

## Consequences
- **+** ~240 lines off `orchestrator.py`; the most-edited pure logic (sanitisers, echo guards, intro
  prompts) is now three focused 80–150-line modules an agent loads in isolation.
- **+** Behaviour provably unchanged: re-export shims + 319-green suite with zero test edits.
- **+** The new modules are independently unit-testable without constructing a `DMBrain`.
- **−** Re-export shims add a small indirection (`orchestrator` imports the names back). Acceptable;
  they're marked `# noqa: F401` and documented. A missed re-export is caught instantly by the suite
  (it caught `_ROLE_LABEL` during this very landing).
- **Deferred (next rounds):** E4 — extract `StreamAssembler` + `finalize_answer` into
  `dmbot/llm/stream_assembler.py`; and the `dmcog.py` splits (lore → its own cog after moving
  `_speak`/`_synthesize` to the runtime; a scene mixin) which need a new mixin idiom and their own ADR.
