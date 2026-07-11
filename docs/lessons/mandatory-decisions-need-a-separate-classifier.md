# Mandatory decisions need a separate classifier call

**A narration model will not reliably emit inline decision markers — model-size-independent.
Decisions that must fire per turn get their own stateless constrained-JSON call; inline
markers are only for optional, human-confirmed proposals where a missed fire costs nothing.**

## What happened

Inline `<<TEST>>` produced ~2 markers in a whole live session, both misplaced — the model
self-resolves rolls in prose instead. A model swap (nemo → gemma3) changed nothing; the
literature calls it the dice-roll deadlock, a documented model-size-independent LLM-GM
failure. The *same* model scored 8/8 when asked in a separate constrained-JSON
classification step (D29 → ADR 014; full research in `docs/research-notes.md` §1). The
pattern was then reused deliberately for every extractor: NPC memory (ADR 044), agendas
(ADR 049), Chekhov threads (ADR 050).

## The correction

Never fix marker unreliability with prompt tuning or a model swap. The boundary:

- **Mandatory per-turn decision** (must fire reliably) → its own stateless side-channel
  call with structured output: schema + enums built from real data, low temperature,
  neutralized penalties (see [[sampling-defaults-leak-into-aux-calls]]), one retry then
  skip.
- **Optional proposal** (nice when it fires, free when it doesn't) → inline marker +
  confirm button, per [[llm-requests-code-validates]] — the UHR/ZEIT family lives here.

## Why it matters

In-band markers look cheaper (no extra call, no latency) and work in offline tests, so each
new decision type re-tempts the in-band route — the boundary above was previously only
implicit across ADR 014 vs ADR 047/048.
