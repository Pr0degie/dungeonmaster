# Read the installed library's source, mock its real contract

**When behaviour contradicts expectations, the truth is in the installed third-party code —
which swallows exceptions, hardcodes waits, and differs from both the docs and your mental
model. Mocks written from the mental model confirm the wrong assumption.**

## What happened

- A 30 s shutdown hang was root-caused by reading the *installed* `voice_client.py` /
  `voice_state.py` — the cause was in discord.py's code, not ours (D67).
- `disconnect_voice` "always returned True" because against the real discord.py + Py 3.12
  the failure branch is dead — the library swallows the bound cancel; the test's naive
  sleep-mock masked it, and the fix included rewriting the test to the library's actual
  swallow-and-cleanup contract (D76).
- Silero v5 needed a 64-sample context prepended — a bare 512-sample window scored prob≈0
  with no error (Phase 3); Discord's DAVE/E2EE decrypt requirement was discovered live
  (Phase 2, ADR 006).

## The correction

Before fixing "your" bug, read the exact installed version's source of the API you wrap
(`docs/conventions.md` already warns this for the voice-recv sink signature — this is the
general method). Write tests against the library's real exception/cancel contract, not an
idealized mock: a mock that encodes your assumption will green-light the dead branch.

## Why it matters

The pipeline doesn't lie about itself — but real-time audio and foreign libraries do, and
they fail with misleading symptoms (silent zeros, dead branches, hangs) rather than errors.
