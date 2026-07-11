# Parity by construction, not by discipline

**When the same value or decision is computed in two places (batch vs streaming, cog vs
eval harness, engine vs narration), it WILL silently desync — the repeated winner is one
shared pure function both paths call.**

## What happened

- One `finalize_answer` shared by batch and streaming so stored == batch == spoken; the
  sanitizer split into leading/trailing halves "so the two can't drift" (ADR 017).
- Reproducing wound arithmetic in a second place was rejected because future drift would
  silently desync the narrated number from actual state (ADR 037).
- Shared `_merged_options()` so batch/streaming option handling can't drift (ADR 042).
- Verdict rules moved into pure `delivery` functions — one source for the cog AND the
  `dm-eval` harness (ADR 046/047).
- Prompt order existed only as a docstring + scattered ifs → one join-only owner, order
  now assertable without an LLM round-trip (ADR 038).

## The correction

The second path (streaming, eval harness, narration text) always arrives *later* than the
first, making copy-adapt the path of least resistance at that moment — that is exactly when
to extract the shared pure function instead. If an invariant lives only in a comment or in
parallel `if` blocks, promote it to one owned, testable location — and own *only* the
invariant (ADR 038 deliberately left timing/caching where they were).

## Why it matters

The desync is silent and surfaces as a live inconsistency (narrated number ≠ state, eval
verdict ≠ cog behaviour) long after the copy was pasted.
