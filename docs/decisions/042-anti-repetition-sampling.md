# ADR 042 — Anti-repetition sampling (repeat_penalty), with a deterministic carve-out for the roll router

- **Status:** Accepted
- **Date:** 2026-06-18
- **Refs:** decision log **D85** in progress.md. Part of the playability tuning round (model kept —
  mistral-nemo — per Tobi; "am Drumherum drehen"). Touches `dmbot/llm/client.py`, `dmbot/config.py`,
  `dmbot/runtime.py`, and `dmbot/orchestrator.py` (the roll-router call). Builds on **ADR 014** (the
  constrained-JSON roll router) and is bound by **golden rule #2** (dice routing = code, deterministic).

## Context
The DM's answers loop and drift into generic filler — one of the three playability complaints Tobi
raised (alongside latency and `!intro`). The Ollama client sent only `temperature=0.8, top_p=0.9`
and **no** anti-repetition penalty, so a 12B model has nothing discouraging it from re-treading the
same phrasing. The only counter was *post-hoc*: the echo guard (ADR 018) retries/suppresses a turn
that parrots a player or re-narrates the previous answer — and in the streaming path a long
repetition can already be spoken before the guard can judge it (the W4 gap). A per-token sampling
penalty attacks the cause, not the symptom.

## Decision
Add `repeat_penalty` (default **1.1**) and `repeat_last_n` (default **256**) as **OllamaClient
instance defaults** — threaded like `num_ctx` (`DM_REPEAT_PENALTY` / `DM_REPEAT_LAST_N` → config →
runtime), merged onto every call by a shared `_merged_options()` so the batch and streaming paths
can't drift. Per-call `options` still win over the instance default.

**Carve-out (essential):** the roll router's `classify_test` call sets `repeat_penalty=1.0,
repeat_last_n=0` explicitly. Its system prompt lists every allowed skill and every difficulty-ladder
value inside the look-back window, so a penalty would discourage the very enum value the classifier
must pick — corrupting a deterministic, reliability-critical path (golden rule #2). This was caught
by the adversarial verify pass and is pinned by `test_roll_router_call_disables_repeat_penalty`.

## Alternatives
- **Leave it off (status quo):** rejected — that is the complaint.
- **Static in `_DEFAULT_OPTIONS`:** rejected — not live-tunable; the right penalty is empirical and
  Tobi wants to tune by ear, so it must be an env knob.
- **DMBrain-level, only on narration turns:** rejected as more plumbing for the same effect — the
  instance-default + one explicit override on the deterministic router is simpler and greppable. The
  free-text recap/rules-Q calls inheriting a *mild* penalty is acceptable (a recap especially benefits
  — they love to loop); only the constrained verdict genuinely needs the carve-out.
- **A stronger penalty (≥1.3):** rejected — frays German fluency and blocks legitimate re-use of a
  proper noun (a name recurs naturally). 1.1 is the gentle starting point.

## Consequences
- **+** Repetition/generic-filler is discouraged at generation time, before the post-hoc echo guard
  has to act — and it covers the streaming path the guard can't fully protect.
- **+** Live-tunable (`DM_REPEAT_PENALTY` 1.0 = off), consistent with the other `DM_*` knobs.
- **+** The roll router stays byte-for-byte deterministic as before B1 (override + regression test).
- **−** The penalty is a global instance default, so the recap summariser and rules-Q answerer inherit
  it too — a conscious, low-risk acceptance (free-text, mild penalty), not a per-turn decision. If a
  rules answer ever needs exact faithfulness, add the same per-call `repeat_penalty=1.0` override.
- **Live-unverified:** the quality win is a model-behaviour claim; confirm at the table and tune
  `DM_REPEAT_PENALTY` / `DM_REPEAT_LAST_N` if nemo still loops or, conversely, sounds stilted.
