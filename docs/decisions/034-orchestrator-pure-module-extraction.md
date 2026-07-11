# ADR 034 — Extract orchestrator's pure helpers into dmbot/llm/* (context-leanness)

- **Status:** Accepted (E1–E4 landed; the `dmcog.py` splits deferred)
- **Date:** 2026-06-14
- **Refs:** decision log D70 (E1–E3) + D71 (E4) in progress.md; same context-cost motivation as **ADR 032** (lean live
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
- `dmbot/llm/stream_assembler.py` (**E4**) — the streaming sentence-assembler (`StreamAssembler`,
  `StreamResult`, `_open_marker_index`, `_FIRST_CHUNK_MIN_CHARS`) **and** the shared
  `finalize_answer` post-processing seam (batch + stream both call it → parity, ADR 017). Pure, no
  `DMBrain` state; `orchestrator` re-imports `StreamAssembler` + `finalize_answer` and its now-unused
  marker/`dataclass`/`split_completed` imports were trimmed.

`orchestrator.py` 1175 → 933 (E1–E3) → **783** (E4) lines. Each move was done by a **byte-exact
line-slice script** (no retranscription of the intricate regexes), then verified: behaviour is
identical — the suite stays **319 green**, unchanged, with no test edits (the re-exports keep the
import surface stable).
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
- **+** ~390 lines off `orchestrator.py` (1175 → 783); the most-edited pure logic (sanitisers, echo
  guards, intro prompts, stream assembler) is now four focused 80–180-line modules an agent loads in
  isolation, instead of always paying for the whole brain.
- **+** Behaviour provably unchanged: re-export shims + 319-green suite with zero test edits.
- **+** The new modules are independently unit-testable without constructing a `DMBrain`.
- **−** Re-export shims add a small indirection (`orchestrator` imports the names back). Acceptable;
  they're marked `# noqa: F401` and documented. A missed re-export is caught instantly by the suite
  (it caught `_ROLE_LABEL` during this very landing).
- **Deferred (next rounds):** the `dmcog.py` splits (lore → its own cog after moving
  `_speak`/`_synthesize` to the runtime; a scene mixin) which need a new mixin idiom and their own
  ADR — out of scope here, which is only "extract the self-contained, state-free units."

## Addendum — detail preserved from decision log D73 (2026-07-11)

Continuation of the same extraction pattern applied to `runtime.py` (no new ADR): the per-turn
latency record `_TurnTiming` and its `_CTX_WARN_FRACTION` threshold moved into a new
`dmbot/turn_timing.py` — a self-contained, state-free logging helper (threads `time.monotonic`
timestamps, emits the one `[latency]` line and the `[ctx]` budget warning; no `SessionRuntime`
state). `runtime.py` re-imports both (`# noqa: F401`) so `from ..runtime import _TurnTiming`
(cog/dice/`test_autorecap`/`test_context_budget`) keeps working; the now-unused
`from dataclasses import dataclass` was dropped from `runtime`. `runtime.py` 610 → **516** lines.
Byte-exact body copy, **0 test edits**, ruff clean, suite **319 green**. Sole non-byte effect: the
`[latency]`/`[ctx]` lines now log under logger name `dmbot.turn_timing` instead of `dmbot.runtime`
(message text and the `[latency]` prefix unchanged; the console INFO format drops the name anyway,
and no test asserts it).
