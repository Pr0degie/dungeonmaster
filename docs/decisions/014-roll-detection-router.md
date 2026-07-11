# ADR 014 — Roll-detection router (separate classifier) instead of the inline test marker

- **Status:** Accepted
- **Date:** 2026-06-08
- **Refs:** decision log D29 in progress.md; revisits **ADR 004** (test marker) + ADR 005/012;
  `architecture.md` §9. Behind `DM_ROLL_ROUTER` (off by default).

## Context
Phase 8's dice flow has the **narration LLM emit an inline `<<TEST …>>` marker** (ADR 004) when a
roll is due; the engine then rolls. Live play (debug log, 2026-06-08) showed this fails badly on the
actual models: across a whole session only **2** markers fired, both mis-placed (tacked after the
closing question, for the wrong character), while the model **self-resolved** nearly every uncertain
action in prose ("du bemerkst …", "es gelingt dir …"). Swapping mistral-nemo → gemma3:12b did **not**
fix it — both self-resolved.

Web research confirmed this is a **documented, model-size-independent LLM-GM failure**: models are
biased toward non-interactive storytelling ("yes, you succeed") and skip checks; the field's fix is
**function calling / a structured roll step**, not a bigger model ([arXiv 2409.06949] reports a
consistency lift 3.42→4.39 with dice/state functions and a "dice-roll deadlock" without them — though
it only tested GPT-4). A held-out **experiment on our models settled the open question**: as a
*separate, constrained-JSON classification step*, the same nemo that self-resolves in narration scored
**8/8** (gemma3 7/8) on "which test does this action need, or none" — including correct "no test" on
trivial actions.

## Decision
Add a **roll-detection router**: after the narration turn, a separate **stateless, constrained-JSON
LLM call** classifies the latest player action → `{needs_test, skill, difficulty}`, with `skill`
**enum-constrained to the acting character's sheet** and `difficulty` to the profile ladder. On
`needs_test`, the existing `_post_dice_button` path fires. The narration model no longer needs to emit
markers; the **inline `<<TEST>>` stays as a fallback** (if the model *does* emit one, it wins and the
router is skipped for that turn). Gated by `DM_ROLL_ROUTER` (off by default) for A/B.

- Pure helpers (schema/prompt/parse) in `dmbot/llm/roll_router.py`; the call is `DMBrain.classify_test`
  (`OllamaClient.chat` gained a `format=` arg for Ollama structured outputs).
- The cog runs it in `_deliver_answer` only when the inline path posted nothing; it uses
  `DMBrain.last_action` (the latest consumed player line) + `CharacterStore` for the skill list.

## Alternatives
- **Keep the inline marker only:** simplest, but empirically unreliable (2 good markers/session) —
  the failure ADR 004 didn't foresee. Kept as fallback, not the primary path.
- **Bigger model on the 5080:** the research + our experiment show the model isn't the bottleneck for
  *classification*; a separate step fixes it on a 12B. Orthogonal, not required.
- **Native tool/function-calling** (Ollama supports it): viable, but mixing tool-calls into the
  narration turn is fiddlier than a clean second pass; structured-output JSON is simpler and we verified
  it. Can migrate later.
- **Inline marker + grammar (GBNF) to force the syntax:** fixes the *format*, not the *decision* (the
  model still skips the marker). Doesn't address the actual failure.

## Consequences
- **Reliable auto-tests on a 12B**, model-independent — decouples "narrate" from "does this need a
  roll?", honouring "dice = code" (the LLM still names the skill via a constrained call; the engine
  owns the numbers).
- **Cost:** one extra short LLM call per turn (~0.5–1 s, temp 0, ~tens of tokens, format-constrained).
  It is **stateless** — its tiny prompt (action + skill/difficulty lists) does **not** see or grow the
  narration history, and its JSON never re-enters that context, so it does not bloat the DM context.
- **Difficulty is weakly differentiated** by the model (often the default rung) — acceptable: difficulty
  is GM-subjective; default to the profile's and let the GM adjust. The skill enum prevents off-list
  picks (gemma3's one slip).
- v1 classifies the **latest** player action only (matches the "latest intent" buffer rule); multiple
  simultaneous actions are a future extension.
- Revisits ADR 004: the marker is now a fallback, not the mechanism. Verified: pure helpers unit-tested,
  full path smoke-tested against Ollama (nemo) end-to-end. Live A/B pending (`DM_ROLL_ROUTER=1`).

## Addendum — detail preserved from decision log D29 (2026-07-11)

The live A/B has since been completed: the router was **validated live on 2026-06-08** and is now
**ON by default** — `DM_ROLL_ROUTER` defaults to enabled, `DM_ROLL_ROUTER=0` disables it. This
supersedes the "off by default" gating stated in the Decision section above.
