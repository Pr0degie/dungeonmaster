# ADR 027 — Context budget: configurable num_ctx + rolling auto-recap

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D57 in progress.md; builds on ADR 015 (recap/state split), ADR 017
  (streaming), ADR 019 (prompt order); supersedes the design sketch in
  `prompts/prompt-6-rolling-recap.md`

## Context

The first live playtest exposed the loudest failure ("der Bot geht null auf die Story ein")
as a **context-window truncation**, not a model regression. `num_ctx` was hardcoded to **8192**
in `dmbot/llm/client.py` with no env override (the 24000 Tobi believed he had set was never
read anywhere). The prompt order is persona → recap → adventure → state → RAG → history; Ollama
truncates the **head** on overflow, so from ~turn 16 (7578/8192, logged) the **persona + the
adventure summary fell out of the prompt first**. That single fault simultaneously produced:
story ignored, runaway length (the "2–4 Sätze" rule gone), puppeting, and pre-roll resolution.
The bot now runs on a 4080 (16 GB), so we have headroom — but even with a large window, a long
session eventually fills any budget. The players explicitly asked for a "handoff when context
gets tight."

## Decision

Two coordinated changes, gated to be reversible:

1. **`num_ctx` is configurable and high by default.** New `OLLAMA_NUM_CTX` env (Config field
   `ollama_num_ctx`, default **24576**), threaded config → cog → `OllamaClient(num_ctx=…)` →
   the Ollama request `options` (still overridable per call). Removes the hardcoded 8192.
2. **Rolling auto-recap ("context handoff", `DM_AUTORECAP`, default on).** When a turn's
   `prompt_eval` crosses the existing `ctx_over_budget` threshold (0.85 · num_ctx), then **after**
   the answer is delivered/spoken (off the hot path, like the autosave), the channel is compacted:
   a **cumulative** recap is generated (`summarize(cid, prior_recap=…)` folds the previous recap in
   so nothing is lost), persisted exactly like `!wrap up` (state.json + recap.md + re-injected),
   and the in-memory history is **cleared**. The next prompt = persona + adventure + the longer
   recap + state + empty history — safely under budget, so the head is never truncated again.
   A per-channel `_compacting` guard prevents double-trigger/races.

## Alternatives

- **Only raise num_ctx, no compaction.** Rejected: any fixed window still overflows in a long
  session, and the truncation is silent — the failure would just reappear later.
- **Only compaction, keep 8192.** Rejected: needlessly tight on a 16 GB GPU; more frequent
  compaction = more LLM calls + more "the DM forgot the verbatim exchange" seams.
- **Fold-before-trim with hysteresis (the `prompt-6-rolling-recap.md` spec):** fold only the
  overflow batch and keep recent turns, triggered by a turn-count high-water mark. We chose the
  simpler **compact-and-clear triggered by the real budget signal** instead — it ties the action
  directly to the truncation cause (prompt_eval), not a proxy turn count. Trade-off recorded under
  Consequences.

## Consequences

- **Positive:** the persona + adventure summary can no longer be silently truncated — the root
  cause of "ignores the story" is closed at two layers (big window *and* proactive compaction),
  independent of the GPU. `num_ctx` is now a one-line `.env` knob. The cap warning already reads
  the real `num_ctx` from Ollama's response stats, so no mismatch.
- **Negative / to watch:** clear-all (vs fold-overflow) means the turn right after a compaction
  has **no verbatim history**, only the summary — a possible discontinuity seam. Acceptable for
  now; a refinement is to keep the last 2–4 turns. The cumulative recap grows over a very long
  session; if it ever pressures the budget, cap the recap harder rather than raising num_ctx.
  Large num_ctx costs KV-cache VRAM (XTTS + Whisper share the GPU) — lower `OLLAMA_NUM_CTX` if OOM.
- **Binds:** future prompt-budget work should treat compaction as the overflow valve and keep the
  ADR-019 prompt order intact (compaction changes the recap's *content*, never its slot).

## Addendum — detail preserved from decision log D57 (2026-07-11)

- Landed with **+18 tests (suite 262 green)**.
