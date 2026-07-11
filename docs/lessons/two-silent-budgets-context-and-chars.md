# The two silent budgets: context tokens and spoken characters

**Two budgets fail without any error: prompt tokens (Ollama silently truncates the HEAD —
i.e. the persona — so overflow presents as gradual quality collapse) and spoken characters
(~0.1 s of audio per char with blocking delivery — long answers ARE the latency). Read the
`[latency]` line before blaming the model or the infrastructure.**

## What happened

- The first live round's failures ("ignores the story") traced to silent prompt-head
  truncation at an unread `num_ctx` — persona tuning was meaningless while truncation ate
  the persona (D36, D57 → ADR 027; the 85%-ctx WARNING exists because of this).
- Scripted/puppeted turns hit 700+ chars → 55–80 s WAVs, total turn latency up to 183 s;
  clean short turns ran ~15 s — "this puppeting IS the latency" (ADR 016 round).
- `!intro test` "loading forever" decomposed to 32 sentences × CPU synth = 378 s to first
  audio — length × synth speed, not a bug (D66 → ADR 031).

## The correction

- Persona drift or "got dumber" complaint → check `ctx=` in the `[latency]` line and the
  85% WARNING **first**. Fix by compaction (rolling recap, trimming history/state), not by
  casually raising `num_ctx` (KV-cache VRAM on the 4070).
- Latency complaint → compute chars→audio-seconds from the `[latency]` line **first**; cap
  `num_predict`/persona length or change delivery mode before optimizing infrastructure.
- Every new always-in-prompt block (adventure summary, NPC memory, clocks, Chekhov) gets
  costed against the context budget when it's added.

## Why it matters

Both failures are invisible at the point of cause: output stays fluent while the persona is
truncated, and latency intuitively reads as a GPU/network problem. Each new in-prompt block
and each new delivery feature re-raises the budget question.
