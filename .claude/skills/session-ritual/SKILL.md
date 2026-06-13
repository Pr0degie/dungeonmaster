---
name: session-ritual
description: Use at the start of a working session for the handshake (read CLAUDE.md → progress.md → the latest ADR, then state where we are and what's next), and at the end of a session or on "wrap up" / "update progress" to update progress.md and scaffold the next-numbered ADR. Keeps continuity across context clears and model switches.
---

# Session ritual — start handshake, end wrap-up, ADR scaffold

State lives on disk so the project survives context clears and model switches. This skill is
the one canonical procedure; it formalizes the prose in `CLAUDE.md`.

## Start handshake

1. Read in order: `CLAUDE.md` (conventions) → `progress.md` (where we are, what's next) →
   the **highest-numbered** file in `docs/decisions/` (most recent decision).
2. State in 2–3 sentences: where we are, what we're about to do. **Don't touch files until
   this handshake is done.**
3. **At a phase transition only:** also read the ADR(s) that govern the new phase — the
   decision log + **phase → ADR map** in `progress.md` say which apply (this is how the older
   ADRs 001–005 get used). And remind the user of the recommended `/model` + `/effort` for the
   phase from `roadmap.md` (the running instance can't switch its own dial).

Read on demand, **not** every session: `architecture.md` (only when the task touches design),
`roadmap.md` (phase transitions / "goal of Phase X?"), `docs/SETUP.md` (Phase 0 / install
steps), older ADRs (when working in their area). Eager-loading everything burns the context
window before useful work starts.

## End-of-session wrap-up (trigger: "wrap up" / "update progress", or unprompted at session end)

Update `progress.md`:
- `## Current focus` — only if the phase changed
- `## Last session` — what we actually did
- `## Next concrete step` — the specific next action, not a vague goal
- `## Open questions` — anything that surfaced but isn't actionable yet
- the affected phase's `VERIFY EVIDENCE` field — when a gate was met

Silence here is the failure mode that breaks continuity. Do it even if not asked.

## new-adr — scaffold the next decision record

Only when a decision weighed a real trade-off with alternatives seriously on the table (trivia
stays in the `progress.md` decision log). Next sequential number, never reused:
`docs/decisions/NNN-short-title.md`.

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

If a decision changes a prior one, set the old ADR's status to `Superseded by ADR NNN` and keep
it. If the decision changes a design choice, update `architecture.md` in the same change.
