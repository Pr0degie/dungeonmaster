# Spoken audio cannot be retracted

**On the streaming path the full text is only known when the audio is already playing — so
every post-hoc quality guard is batch-first with an explicit log-only streaming degradation,
or the fix moves upstream into sampling where it acts before generation.**

## What happened

At least four guards independently rediscovered this mid-implementation:

- ADR 017's hold-back design exists because sanitizers assume they see the whole answer.
- The echo guard runs only at `finish()` when nothing was spoken yet (ADR 018); spoken
  repetitions are logged loudly "since audio can't be retracted" (W4 round).
- The weak-intro retry is batch-only by design (D86 → ADR 041).
- The long-repetition fix moved upstream to per-token `repeat_penalty` because the post-hoc
  guard could not act before the repetition was spoken (ADR 042).
- The consistency guard only logs on the streaming path; abort-mid-stream was rejected —
  a violation detected at sentence N has already been spoken (D92 → ADR 045).

## The correction

When designing any answer-quality check, decide its streaming story **up front**, one of:
(a) a hold-back rule in the stream assembler, (b) batch-only with a documented log-only
streaming degradation, (c) move the fix upstream into sampling/options. Never assume a
post-generation guard protects the spoken channel.

## Why it matters

Guards are naturally conceived (and unit-tested) against the full text; the streaming path
invalidates that assumption quietly, and each new guard pays the rediscovery cost at wiring
time instead of design time.
