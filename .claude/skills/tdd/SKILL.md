---
name: tdd
description: Use when changing the deterministic core (dmbot/rules/, engine.py, marker.py, any new pure function with verifiable behaviour) and you want the change driven by a failing test first. Enforces red-green-refactor against the repo's fixed-seed pytest setup: write one failing test, confirm red, implement minimal green, refactor. Not for prose/persona/prompt edits or RAG ingestion.
---

# Test-driven a change to the deterministic core

Golden rule #2 (dice = code, deterministic) makes the engine the ideal TDD target: pure
functions, fixed-seed, exact outcomes. Here the test leads: red first, always.

**Scope:** `dmbot/rules/` (engine, marker, profile loader) and any new pure helper with a
checkable result. *Not* for LLM-shaped work (persona, prompts, recaps), RAG, or Discord glue —
those aren't deterministically assertable. For a whole new subsystem use `rules-subsystem`
(it already bakes in fixed-seed tests); reach for `tdd` when you're adding/changing behaviour
in code that already exists.

## The loop — one test at a time

1. **RED — write one failing test.** Add a single test to `tests/test_<area>.py`, modelled on
   `tests/test_psyker.py` / `tests/test_augmetics.py` (seeded RNG, assert the exact outcome).
   Describe the *behaviour you want* (public function in/out), not the implementation. One
   behaviour per cycle — never a batch of speculative tests.
2. **Confirm red.** Run `uv run --with pytest python -m pytest tests/test_<area>.py -q` and
   verify the new test **fails for the right reason** (assertion, not an import/typo error).
   A test that was never red proves nothing.
3. **GREEN — minimal implementation.** Write the smallest change to `engine.py` (or the target
   module) that makes the test pass. Read the profile block as data; keep the function pure.
4. **Confirm green.** Re-run the file, then the full suite
   (`uv run --with pytest python -m pytest`) so the change didn't break a sibling.
5. **REFACTOR.** Only once green: dedupe, rename, extract helpers. Tests stay untouched and
   must stay green throughout.
6. Repeat from 1 for the next behaviour.

## Guardrails (the whole point)

- **Never edit a test to make it pass.** If a test is wrong, say so explicitly and fix it as a
  deliberate, separate step — never silently to chase green. The pre-commit gate + Stop hook
  already run the suite; a test quietly relaxed is the failure mode they can't catch.
- **No green before red.** If you can't show the test failing first, the test isn't pinning the
  behaviour — fix the test, not the implementation.
- **One behaviour per cycle.** Bulk tests written upfront end up asserting mocks instead of real
  code paths.
- **Test public behaviour, not internals.** Assert what `resolve_*` returns, not how it got
  there — so the test survives the refactor step.
- **Deterministic only.** Seed the RNG; assert exact bands incl. crit/fumble/edge. If the result
  isn't deterministic, it doesn't belong to the engine (golden rule #2).

## Close-out

- Full suite green: `uv run --with pytest python -m pytest`.
- Commit test + implementation **together**, imperative scoped message
  (`rules(im): success-level edge band`). Direct to `main` (no feature branch for this repo).
- A real design trade-off → write an ADR; pure red-green of existing behaviour → no ADR needed.
