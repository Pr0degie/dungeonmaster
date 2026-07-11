# Sampling defaults leak into other call types

**Client-wide sampling defaults silently sabotage specific call types: an unset temperature
made `!intro` a coin flip, and the instance-wide `repeat_penalty` punished exactly the enum
the roll-router had to choose. Every distinct LLM call type pins its own sampling
explicitly.**

## What happened

- `!intro` alternated between great and generic with identical prompts — not a bug, model
  variance at nemo's default temperature (~0.8) because the opening call never set one;
  fixed by pinning `DM_INTRO_TEMPERATURE` (D83 → ADR 041).
- The instance default `repeat_penalty=1.1` had to be explicitly reset to 1.0 in the
  roll-router: its prompt lists all skills/difficulties in the look-back, so the penalty
  punishes precisely the enum token it must emit (D85 → ADR 042 — caught by the
  adversarial verify pass). The extractors repeat the neutralization deliberately (ADR 044).

## The correction

Every distinct call type (narration, roll-router, extractor, summarizer, intro) declares
its own temperature/penalties explicitly at the call site. When adding any client-wide
default, audit every auxiliary call for interaction with its output format —
enum-in-prompt × repeat-penalty is the canonical non-obvious case.

## Why it matters

Client-level defaults are invisible at the call site, and unpinned sampling presents as
"the model is flaky" rather than as config — both incidents looked like model problems
first.
