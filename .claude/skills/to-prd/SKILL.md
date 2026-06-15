---
name: to-prd
description: Turn the current conversation context — ideally after a /grill-me session — into a PRD written to the repo. Do NOT interview; synthesize what's already been decided. Use when Tobi wants to turn a grilled-out plan into a written spec, or says "to-prd" / "schreib den Plan".
---

# Synthesize the grilled context into a PRD

The companion to `/grill-me`: grill-me builds the shared understanding, this writes it up.
**Do NOT interview** — synthesize what's already been decided in this conversation and the
codebase. If the context is thin (no grilling happened), say so and suggest `/grill-me` first.

## Process

1. **Explore.** Read the current state of the area in code, plus `architecture.md` and the
   ADRs in `docs/decisions/` governing it (decision log + phase→ADR map in `progress.md`). Use
   `architecture.md`'s domain vocabulary throughout the PRD; respect the ADRs — don't
   re-decide what they settled.
2. **Sketch the test seams.** Name the seams the feature will be tested at. Prefer existing
   seams; use the highest seam possible. For this repo the natural high seam is the
   deterministic engine boundary — pure functions in `dmbot/rules/` (dice = code, golden
   rule #2). Check with Tobi that the seams match his expectation before writing.
3. **Write the PRD** to `docs/plans/<feature-slug>.md` using the template below. Then point
   `progress.md`'s `## Next concrete step` at it. No issue tracker — the file *is* the artifact.

<prd-template>
## Problem Statement   — the problem, from the user's perspective (player / GM / Tobi-as-operator)
## Solution            — the solution, from the user's perspective
## User Stories        — a LONG numbered list, "As a <player|GM|operator>, I want <feature>, so that <benefit>"; cover all aspects
## Implementation Decisions — modules/interfaces/architecture/schema/data-shape/marker contracts.
                              NO file paths or code snippets (they rot fast). Exception: a prototype-derived
                              snippet that pins a decision more precisely than prose (state machine, schema, dataclass) —
                              inline just the decision-rich bit, noting it came from a prototype.
## Testing Decisions   — what makes a good test here (assert external behaviour, fixed-seed, exact bands —
                          golden rule #2); which modules get tested; prior art (e.g. tests/test_psyker.py)
## Out of Scope
## Further Notes
</prd-template>

## Hand-offs
- Build the result test-first with `/tdd` if it's deterministic-core work.
- A real architectural trade-off uncovered while writing → `/session-ritual` scaffolds an ADR
  (the PRD is the plan; the ADR records the decision — different artifacts, both on disk).
