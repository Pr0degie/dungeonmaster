# One variable per live run

**Live sessions are the scarcest resource — never confound them. Tune → verify the baseline
live → only then compare or swap (model, host, delivery mode). Stack independent gate
checks into one scripted run, but never bundle a comparison with unverified tuning.**

## What happened

The rule was restated independently twice, a month apart: the model A/B against nemo is
deferred until after the gate session ("sonst zwei Variablen gleichzeitig"), and the
live model comparison must not start before the tuning live-run is through — otherwise it
compares an untuned setup. The stacked-gates discipline (all open gates in ONE scripted
run, fixed order, `docs/live-run-script.md`) is the same economics applied to
verification.

## The correction

Sequence live work: tune first, live-verify the baseline, then compare. Stacking
*independent verifications* into one run is fine and encouraged; confounding a
*comparison* with unverified changes is not.

## Why it matters

Live sessions need three players' schedules, so "also try the new model while we're at it"
resurfaces before every run. CLAUDE.md's WIP limit governs gate *count*; this governs
confounding.
