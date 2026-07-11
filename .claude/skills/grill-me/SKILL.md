---
name: grill-me
description: Interview Tobi relentlessly about a plan or design decision until reaching shared understanding, resolving each branch of the decision tree one fork at a time. Use when he wants to stress-test a plan before building, asks to "get grilled", or says "grill me". For design/architecture forks — not for mechanical edits.
---

# Grill the plan before any code

Resolve the decision tree *with Tobi* first, then build. Use it before a non-trivial design
choice — the kind that would otherwise become an ADR.

## How to grill

1. **Answer it yourself first.** Before asking Tobi anything, check whether the docs or code
   already decide it: `architecture.md` (design wins, per CLAUDE.md), the ADRs in
   `docs/decisions/` (the decision log + phase→ADR map in `progress.md` point to the governing
   one), `progress.md` itself, then the code. Only ask what genuinely needs his call.
2. **One fork at a time.** Walk the decision tree branch by branch, resolving dependencies in
   order — never dump a list. Each answer narrows the next question.
3. **Always recommend.** For every question, give your recommended answer with a one-line why.
   Use `AskUserQuestion` (recommended option first, labelled "(Empfohlen)") for clean 2–4-way
   forks; ask in chat for open-ended points. Questions in **German**; this file stays English.
4. **Be relentless, but converge.** Keep going until the design is unambiguous — architecture,
   data shape, edge cases, failure modes — but stop the moment there's nothing left that would
   change what gets built. Don't manufacture questions.

## Respect the golden rules while grilling

Surface tensions with the golden rules (#2–#5, #7 — `CLAUDE.md`) as forks, don't silently
assume them. If a plan would cross one, that's a question, not a given.

## Close-out

When the tree is resolved, summarise the agreed design in a few lines and — if it settled a
real trade-off — offer to scaffold the next-numbered ADR (hand off to `session-ritual`). Then,
and only then, start building (or run `/tdd` if it's deterministic-core work).
