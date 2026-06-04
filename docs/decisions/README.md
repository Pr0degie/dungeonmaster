# Architecture Decision Records (ADRs)

This is where decisions live that weighed a real trade-off — not every little thing.
Trivia stays in the decision log in `progress.md`.

## When an ADR?

When a decision had alternatives that were seriously on the table, and the choice binds
later work. Rule of thumb: if a new model would ask in three months "why this way and not
another?", it belongs here.

## Convention

- One file per decision, numbered sequentially: `NNN-short-title.md`
  (e.g. `001-ruleset-imperium-maledictum.md`).
- Numbers are never reused. If an ADR is superseded, the old one gets the status
  `Superseded by ADR NNN` and stays (history rather than deletion).
- The highest-numbered file is mandatory reading at session start (session ritual in
  `CLAUDE.md`).

## Format

```markdown
# ADR NNN — Title

- **Status:** Proposed | Accepted | Superseded by ADR NNN
- **Date:** YYYY-MM-DD
- **Refs:** decision log DX in progress.md, optionally architecture.md §Y

## Context
What problem was at hand? What constraints (hardware, style, effort)?

## Decision
What was chosen — in one sentence.

## Alternatives
What else was on the table and why not.

## Consequences
What follows — positive and negative. What does this bind for later work?
```
