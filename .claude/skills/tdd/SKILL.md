---
name: tdd
description: Use when a change to the deterministic core (dmbot/rules/, engine.py, marker.py, any new pure function with verifiable behaviour) has real logic or an invariant worth pinning with a failing test first. Red-green-refactor against the repo's fixed-seed pytest setup, tests in blocks allowed. Not for trivial additions, prose/persona/prompt edits or RAG ingestion.
---

# Test-driven a change to the deterministic core

Golden rule #2 (dice = code, deterministic) makes the engine the ideal TDD target: pure
functions, fixed-seed, exact outcomes. Where it pays, the test leads.

## When it pays — and when it doesn't

Tobi's rule (2026-10-06, stated in the hollowdeep repo and asked to apply here too):
test-first only where it is worth it, not for every small thing.

**Test first:** a rule with branches or edge cases (success levels, crit/fumble bands, marker
parsing), an invariant, or a reported engine bug — reproduce it as a failing test before fixing.

**A test alongside or after is enough:** a trivial addition — a clamp, one more profile field
read in one place, a formula with no branch. Don't write empty stubs just to watch it fail.

**No unit test at all:** persona, prompts, recaps, RAG ingestion, Discord glue — see Scope.

**Scope:** `dmbot/rules/` (engine, marker, profile loader) and any new pure helper with a
checkable result. *Not* for LLM-shaped work (persona, prompts, recaps), RAG, or Discord glue —
those aren't deterministically assertable. For a whole new subsystem use `rules-subsystem`
(it already bakes in fixed-seed tests); reach for `tdd` when you're adding/changing behaviour
in code that already exists.

## The loop — for the cases above that are test-first

1. **RED — write the failing test(s).** Add them to `tests/test_<area>.py`, modelled on
   `tests/test_psyker.py` / `tests/test_augmetics.py` (seeded RNG, assert the exact outcome).
   Describe the *behaviour you want* (public function in/out), not the implementation. A block
   of tests for one feature is fine; one behaviour per test, and none that are speculative.
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
- **No green before red** — for the test-first cases. If you can't show the test failing first,
  the test isn't pinning the behaviour — fix the test, not the implementation. For a trivial
  addition this step is skipped by design, see above.
- **One behaviour per test.** A block of tests for one feature is fine; tests that assert mocks
  instead of real code paths are not.
- **Test public behaviour, not internals.** Assert what `resolve_*` returns, not how it got
  there — so the test survives the refactor step.
- **Deterministic only.** Seed the RNG; assert exact bands incl. crit/fumble/edge. If the result
  isn't deterministic, it doesn't belong to the engine (golden rule #2).

## Close-out

- Full suite green: `uv run --with pytest python -m pytest`.
- Commit test + implementation **together**, imperative scoped message
  (`rules(im): success-level edge band`). Direct to `main` (no feature branch for this repo).
- A real design trade-off → write an ADR; pure red-green of existing behaviour → no ADR needed.
