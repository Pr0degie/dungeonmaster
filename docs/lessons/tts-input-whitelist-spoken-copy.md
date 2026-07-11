# TTS input: whitelist, on a spoken-only copy

**Sanitizing TTS input by blocklist always leaks — emoji, arrows, middle-dots and lone
punctuation are invisible or harmless-looking in text logs but become gibberish or 15 s of
babble in audio. Normalize with NFKC + a character whitelist, on a spoken-only copy (never
the stored/posted text), guard every chunk for speakability, and stay under the engine's
real length limit.**

## What happened

- The first normalizer was a blocklist and still spoke gibberish: emojis (🎲🌀🜏💥), arrows,
  bullets, middle-dots slipped through — none of which show up as suspicious in the
  transcript (W6 round, redone in D53 as NFKC + whitelist).
- A marker-only answer left a lone backtick that XTTS read aloud for ~15 s → per-chunk
  `has_speakable_content()` guard (D42).
- XTTS silently truncates German chunks over ~253 chars → <240-char splitting.
- Punctuation is a babble trigger for autoregressive XTTS, not decoration (D55) — which is
  why `speech_transform` is applied to the spoken text only, chat text untouched (ADR 031),
  and intonation became a config axis rather than a bug to fix (ADR 033).

## The correction

Everything reaching the TTS engine passes the whitelist normalizer (letters/digits/
whitespace + a fixed punctuation set, after NFKC — legitimately returning "" is fine) on a
spoken-only copy; guard each chunk for speakable content; keep chunks under the engine's
real, undocumented limit. Verify new markers/formatting against the **strip path**, not the
transcript — "looks clean in the log" proves nothing, the offending characters don't render
there. New markers keep the shared `<<…>>` delimiter or the strip guard is lost (ADR 026).

## Why it matters

The failure evidence is audio heard at the table while debugging happens in text logs where
the trigger characters are invisible — the same failure shape as the STT resample gotcha in
CLAUDE.md (garbage output, no error), on the output side.
