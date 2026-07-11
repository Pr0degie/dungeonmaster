# Optional layers fail open, the core fails loud

**Optional guards and extractors degrade, skip, or fall back — with a log line and a
kill-switch — and never block the table. The deterministic core (dice, state) fails loud.
The economics: a false positive costs every player real time; a miss costs immersion once.**

## What happened

- ADR 045 states the economics outright: a missed violation costs immersion once, a false
  positive costs every player 10+ seconds of silence — "the guard is a net, not a wall";
  when in doubt, do not flag; fail open on any internal error.
- A `requires` typo must not lock an exit forever (ADR 043 — fails open); extraction gets
  one retry then skip + warn, never blocking the scene change (ADR 044/049); XTTS degrades
  to CPU or text-only mode instead of crashing (ADR 009/024); an unparseable dice marker
  still yields a generic manual button (ADR 004/012).
- The counterexample that proves the rule: a broad `except TypeError` in the dice path
  silently re-rolled the d100 and masked real bugs (ADR 030 #6) — fail-open done *wrong*,
  on the core, silently.

## The correction

For every new guard/extractor/subsystem, declare the failure posture explicitly: optional
narrative layers fail open **loudly** (log line + kill-switch env); the deterministic core
fails loud and never swallows errors. Budget retries at one. Log what was skipped so live
triage can see it.

## Why it matters

Each new guard is written in "catch the bad thing" mindset, and the blocking/strict variant
is the natural first draft every time — while the silent-swallow variant is the natural
first draft for robustness code. Both are wrong in opposite directions.
