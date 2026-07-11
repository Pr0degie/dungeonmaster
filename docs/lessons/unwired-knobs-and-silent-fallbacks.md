# Unwired knobs and silent fallbacks

**Config values nobody reads, helpers nobody calls, and fallbacks that substitute different
data all fail the same way: zero errors, plausible behaviour, weeks of silent wrongness.
Prove the knob is wired in the same change; make every fallback announce itself.**

## What happened

- The smoking gun: `num_ctx` ran at a hardcoded 8192 — the 24000 Tobi believed he set was
  never read anywhere; one unread value produced four playability symptoms (D57 → ADR 027).
- The live `.env` was 20 keys behind `.env.example`, so a whole tuning round silently ran
  on code defaults — `dm-sync`'s first real finding (D89).
- `stt/segments.py::confident_text` existed but was never wired in while an inline
  duplicate ran (D79); `set_time` had zero callers (D95).
- A session in the wrong channel silently fell back to the **example party** — wrong
  aliases, wrong sheets, diagnosed only from `history.jsonl`; the same class hit again on a
  colleague's channel (D43; D82 → ADR 040). Fix both times: a loud in-channel announcement
  at the moment the fallback triggers.

## The correction

When adding a knob or extracting a helper, grep for the reader/caller **in the same
change**. Where possible read the effective config back from the service instead of
trusting intent (ADR 027 reads real `num_ctx` back from Ollama). Any fallback that
substitutes different data announces itself in the channel/console when it triggers —
degrade per-item with a loud line, never silently and never by crashing. Cheap fingerprint
checks (`dm-sync` .env-key diff, the 85%-ctx warning) turn "running on defaults" from an
assumption into a visible fact.

## Why it matters

An unread env var and an uncalled function produce zero errors; fallbacks are added during
development when the fallback data IS the real data. Nothing surfaces until a live session
degrades in an unrelated-looking way — the most expensive place to find out.
