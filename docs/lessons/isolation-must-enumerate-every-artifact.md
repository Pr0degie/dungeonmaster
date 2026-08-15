# Isolation is per-artifact — enumerate them, or it's half a sandbox

**The correction:** When a feature claims two things can't contaminate each other, list every
artifact the two share *before* declaring it done. "Isolated" is not a property of a feature;
it's a property of each file, table and path the feature touches. Any one you forget is a
full-strength leak, and it will read as "isolated" in the ADR until a live run says otherwise.

**How it happened (ADR 055 → ADR 056):** The debug-campaign sandbox isolated the rotated
journals (`history.<stamp>.debug.jsonl`) and the RAG source (`session_debug_<id>`), and the ADR
stated the live campaign stays untouched "in both directions". The four *running* session files
— `state.json`, `history.jsonl`, `chekhov.json`, `recap.md` — still had one path per channel. The
first live debug evening loaded the live campaign's state and 20 restored turns and ran entirely
in the wrong adventure: no scene card, no overlay, and the debug run's own turns written into the
live campaign's files. Two of six artifacts isolated reads exactly like six of six until you play.

**How to apply:**
- Before writing "isolated" in an ADR, enumerate the shared resources as a list and mark each
  one: *split*, *shared on purpose*, or *not yet*. The "shared on purpose" entries matter as much
  as the splits (`characters.json` is deliberately shared — the debug campaign uses the real party).
- Prefer one seam over per-call-site decisions: a single `session_file(id, stem, ext)` that all
  paths route through makes the next artifact isolated by default, and makes "which artifacts
  exist" a question you can answer by grepping one function's callers.
- Pin the property, not the plumbing: the test that earns its keep asserts the live path set and
  the sandbox path set are **disjoint**, so a newly added artifact that forgets the seam fails.
- Same shape as [[parity-by-construction]] (two computations of one value desync) and
  [[unwired-knobs-and-silent-fallbacks]] (silent fallbacks hide for weeks): partial mechanisms
  don't announce themselves, so make the invariant structural.
