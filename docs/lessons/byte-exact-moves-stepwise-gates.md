# Refactors: byte-exact moves, zero test edits, stepwise gates

**Move code with byte-exact line-slice scripts (never retype), cut the seam so existing
tests need zero edits, and migrate one seam at a time with suite + ruff-F + `dm-eval` green
after every step. Review effort belongs on new logic — the moves are the safe part.**

## What happened

- Six-plus extraction rounds (D60, D70–D74, D90, D98 → ADR 029/034/035/037/038/039/051)
  re-established the same method: slice scripts, char-count/AST/reverse-rename verification
  against HEAD, re-export shims or thin delegators so callers and tests stay untouched.
- The evidence for where risk actually lives: a 14-finding fan-out review confirmed 3 —
  **all** in new logic/test code, not one in the byte-exact move commits (D76, cited in
  `docs/conventions.md`).
- Hand-retyping is where drift enters: intricate regexes (ADR 034), German strings with
  glyphs like 🜏 (ADR 037) — the suite once instantly caught a missed re-export.
- Boundary cases: sometimes **no** shim is right — a silently drifting stale copy is worse
  than a hard break (D90); and don't generalize the concrete parts (handlers, verdicts)
  while consolidating the seam — that's the feature, not the naht (ADR 051 #5).

## The correction

Slice, don't retype. Choose the cut so tests need zero edits — a needed test edit is a
design smell of the cut, and "zero test edits" is the strongest no-behaviour-change signal.
Verify the move mechanically, migrate incrementally with all gates green after each step
(`dm-eval` exists precisely as the refactor gate — ADR 046), and no big-bang diffs.

## Why it matters

Every few weeks another god-file needs splitting, and refactor anxiety points review budget
at the moves — the evidence says the opposite: the moves are safe when mechanical, the new
glue is where the bugs are. The review-side rules live in `docs/conventions.md` (Gates);
this is the execution method.
