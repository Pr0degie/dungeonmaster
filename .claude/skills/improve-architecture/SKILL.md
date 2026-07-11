---
name: improve-architecture
description: Find deepening opportunities across the codebase — refactors that turn shallow pass-through modules into deep ones, for testability and AI-navigability. Informed by architecture.md and the ADRs in docs/decisions/; never re-litigates a decided ADR. Use when Tobi wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a part of the bot more testable. Whole-codebase altitude — not /simplify or /code-review (those are diff-scoped).
---

# Improve codebase architecture

Surface architectural friction and propose **deepening opportunities**: refactors that turn
shallow modules into deep ones. The aim is **testability and AI-navigability** — which is this
project's survival strategy (many sessions, many models, the deterministic core must stay
testable). This runs at whole-codebase altitude; for cleaning up a diff use `/simplify` or
`/code-review`.

## Vocabulary — use these exact terms, don't drift into "service/component/boundary"

- **Module** — anything with an interface and an implementation (function, class, package, cog).
- **Interface** — everything a caller must know: types, invariants, error modes, ordering,
  config. Not just the signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: much behaviour behind a small interface. **Deep** =
  high leverage; **shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can change without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Locality** — change, bugs, knowledge concentrated in one place.

**Three principles:**
- **Deletion test** — imagine deleting the module. If complexity vanishes, it was a
  pass-through. If it reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

## Process

### 1. Explore
Read `architecture.md` and the ADRs governing the area first — the decision log + phase→ADR map
in `progress.md` say which (e.g. ADR 029 for `runtime.py` injection, 034/035 for the
orchestrator/delivery split). Then use the **Explore** subagent to walk the code and note where
*you* feel friction — don't follow rigid heuristics:
- Understanding one concept requires bouncing between many small modules.
- A module is **shallow** — interface nearly as complex as its implementation.
- Pure functions were extracted just for testability, but the real bugs hide in *how they're
  called* (no **locality**) — likely spots: `orchestrator.py` ↔ the extracted `llm/` helpers,
  the voice cogs ↔ `delivery.py`.
- Tightly-coupled modules leak across their seams; or a part is hard to test through its
  current interface.

Apply the **deletion test** to anything you suspect is shallow.

### 2. Present candidates (Markdown, in chat)
For each candidate, a short card:
- **Files** — which modules are involved
- **Problem** — why the current shape causes friction
- **Solution** — plain English, what would change
- **Benefits** — in terms of locality, leverage, and how tests would improve
- **Before / After** — a compact sketch (ASCII/prose) of the shallow shape vs the deepened one
- **Strength** — `Strong` · `Worth exploring` · `Speculative`

Use `architecture.md`'s names for the domain (talk about "the turn-delivery pipeline", not
"the FooHandler"). End with a **Top recommendation**: which one you'd tackle first, and why.
**Do NOT propose interfaces yet.** Then ask: "Which of these would you like to explore?"

**ADR conflicts:** only surface a candidate that contradicts an ADR when the friction is real
enough to reopen it — flag it clearly (_"contradicts ADR 029, but worth reopening because…"_).
Don't list every refactor an ADR forbids.

### 3. Nail down the chosen candidate
Once Tobi picks one, settle the design before building — but **scale the ceremony to the
refactor; don't grill by reflex**:
- **Small / obvious** (extract this, inline that, collapse a pass-through): state the target
  shape in a line or two and build it. No grilling.
- **Real design forks** (what sits behind the seam, which tests survive, cross-cutting
  constraints): grill them out — run `/grill-me` if it helps, or just walk the forks here.

Either way, two side effects are **mandatory** — they outlast this session:
- **Naming a deepened module after a concept not in `architecture.md`, or sharpening a fuzzy
  term?** Update `architecture.md` right there — design decisions live there and "if you change
  a decision, update architecture.md in the same change" (CLAUDE.md).
- **Tobi rejects a candidate with a load-bearing reason?** Offer to record it as an ADR
  (`/session-ritual` scaffolds the next number) — _"so future architecture reviews don't
  re-suggest it"_. Only when the reason would actually be needed by a future explorer; skip
  ephemeral ("not worth it now") and self-evident ones.

## Respect the invariants
Deepening must not cross a golden rule (#2–#5, #7 — `CLAUDE.md`). A refactor that would merge
the bridge into DMbot logic, or move dice resolution toward the LLM, is wrong by construction
— don't propose it.
