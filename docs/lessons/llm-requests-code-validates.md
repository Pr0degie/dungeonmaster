# LLM requests, code validates — the feature template

**Every "the DM should be able to change X" feature converged on the same template: the LLM
emits a request, code validates against a closed set and clamps magnitude, a confirm button
makes misfires free, a kill-switch env exists — and the LLM work rides an existing call.**

## What happened

Seven features re-derived the same answer one at a time, each from the previous ADR instead
of from a written template: `<<ORT>>` scene moves (D56 → ADR 026), `<<ERLEDIGT>>` flags
(D87 → ADR 043), NPC memory (D91 → ADR 044), clocks (D94 → ADR 047), in-game time
(D95 → ADR 048), NPC agendas (D96 → ADR 049), Chekhov threads (D97 → ADR 050).

## The correction

The template, in order:

1. **Request, never write**: in-band `<<MARKER>>` (keep the shared delimiter or the TTS
   strip/withhold guard is lost — ADR 026) or a schema field on an extractor call.
2. **Validate against a closed set** (known ids, enums, current-scene elements); unknown
   ids are discarded + logged, never applied.
3. **Clamp, don't reject**, when the proposal is directionally right (ADR 048: oversized
   time advance clamped to +12h — dropping it loses signal a clamp preserves). Classify
   idempotency explicitly: flags/ticks are idempotent (process all), time advances are not
   (first valid only).
4. **Confirm-by-default** (button under `DM_FLAG_CONFIRM`-style flags) — cheap insurance,
   misfires cost nothing.
5. **Kill-switch env var**, and the failure posture from
   [[optional-layers-fail-open-core-fails-loud]].
6. **Budget: no new LLM call.** Per turn: zero extra calls; per scene change: the ONE
   ADR-044 extractor call; per wrap-up: the one extraction call. New capabilities become
   extra schema fields on the call that happens anyway (+ raised `num_predict`), or run
   off the hot path — where they must never block the scene change (ADR 044/045/049/050
   all rejected a second call for exactly this reason).

## Why it matters

Every new subsystem re-raises "can't the model just write it?" and golden rule #3 only
states the prohibition — this is the positive recipe, so the next feature starts here
instead of re-deriving it from the last ADR.
