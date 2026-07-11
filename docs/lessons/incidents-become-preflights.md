# Every external-state incident becomes a preflight

**Every live session lost to external state — daemon not running, wrong branch, missing
DLLs, version/artifact drift — was converted into a boot-time preflight, an exact pin, an
offline canary, or a fingerprint diff. Build the check that would have caught it; don't
just fix the instance.**

## What happened

- A Phase-8 gate run died because Ollama simply wasn't running → `llm/preflight.py` +
  warm-up in the start script.
- The voice stack's silent-breakage risk → exact `==` pins (not `>=`), `voice/preflight.py`
  boot/join checks, runtime detection of the DAVE `0xFAFA` signature (warn + skip instead
  of Opus-decoding ciphertext to garbage), and `tests/test_voice_stack.py` as the offline
  canary (ADR 006).
- The venv silently held CPU-only torch (PyPI default) and crashed only at XTTS load;
  `httpx` turned out to be an undeclared direct dependency one churn away from breaking
  boot (ADR 009); after dep changes, faster-whisper was re-verified explicitly — the
  breakage lands next door, not in the changed package (ADR 008).
- Two-machine drift of `.env`/rag.db/adventures → the `dm-sync` fingerprint diff (D89/D90).
- A Phase-6 bridge failure was Bot A sitting on the wrong branch.

## The correction

After any incident caused by external state, spend the follow-up building the check that
would have caught it at boot: preflight ping/version/attribute check, offline canary test,
fingerprint diff, exact pins with the known failure signature encoded as a warn-and-skip.
After any dependency churn, re-run the *adjacent* consumers (does STT still transcribe?
does boot reach ready?).

## Why it matters

External processes and second machines are outside the test suite's reach; each new
dependency re-creates "it silently isn't there" with a new face, and the incident always
costs a scarce live session. `docs/conventions.md`'s "stuck on reality" list holds the
per-symptom checks — this is the habit that produces them.
