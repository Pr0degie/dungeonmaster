---
name: session-ritual
description: Use at the start of a working session for the handshake (read CLAUDE.md → the State header at the top of progress.md → the latest ADR, then state where we are and what's next), and at the end of a session or on "wrap up" / "update progress" to update progress.md within its wrap-up caps and scaffold the next-numbered ADR. Keeps continuity across context clears and model switches.
---

# Session ritual — start handshake, end wrap-up, ADR scaffold

State lives on disk so the project survives context clears and model switches. This skill is
the one canonical procedure; it formalizes the prose in `CLAUDE.md`.

## Start handshake

1. Read in order: `CLAUDE.md` (conventions) → ONLY the `## State header` at the top of
   `progress.md` (until the State header exists — it's created in a follow-up round — read
   `## Current focus` instead) → the **highest-numbered** file in `docs/decisions/` (most
   recent decision). Full `progress.md`, the decision log, and older ADRs are on-demand
   reads when the task touches them.
2. State in 2–3 sentences: where we are, what we're about to do. **Don't touch files until
   this handshake is done.** If the WIP limit (max 3 open live gates, see wrap-up below)
   makes this a live-verification session, say so here.
3. **Before touching a subsystem or starting a phase:** read the ADR(s) that govern it — the
   decision log + **phase → ADR map** in `progress.md` say which apply (this is how the older
   ADRs 001–005 get used). On-demand, but mandatory for that case.

Read on demand, **not** every session: `architecture.md` (only when the task touches design),
`roadmap.md` (phase transitions / "goal of Phase X?"), `SETUP.md` (Phase 0 / install
steps), older ADRs (when working in their area), `docs/conventions.md` (per-module how-tos +
testing/runtime/troubleshooting/style detail), `docs/progress-archive.md` (history only — old
session logs, completed-phase evidence, resolved questions). Eager-loading everything burns the
context window before useful work starts.

## End-of-session wrap-up (trigger: "wrap up" / "update progress", or unprompted at session end)

Update `progress.md`:
- `## Current focus` — only if the phase changed
- `## Last session` — what we actually did
- `## Next concrete step` — the specific next action, not a vague goal
- `## Open questions` — anything that surfaced but isn't actionable yet
- the affected phase's `VERIFY EVIDENCE` field — when a gate was met

**Keep it lean (rotation + caps, enforced every wrap-up, not "eventually"):** the live
`progress.md` holds only the current state. When you prepend a new `## Last session` entry, move
the *previous* one to `docs/progress-archive.md` (`## Last session (Verlauf)`) — keep only the
newest 1–2 live. Rotate ✅-resolved `## Open questions` and just-completed phases (full
`VERIFY EVIDENCE` → one-line summary live) there too. Caps: State header max 25 lines;
`## Current focus` max 2 blocks live (rotate in the same edit that adds a new one); decision-log
rows max 2 lines ("what + one-clause why + → ADR NNN" — the rationale lives in the ADR; rows
without an ADR are exempt); `progress.md` over 400 lines → rotate rotatable content (archived
history, old Current-focus blocks) before committing — the exempt no-ADR decision-log rows don't
count against this. The `## Decision log` and `### Phase → ADR map` stay fully live (stable
`D##` refs).

**WIP limit (checked at wrap-up, announced in the next handshake):** max 3 open live gates. If
this round would leave a FOURTH open, it doesn't start — the next session is a live-verification
session; set `## Next concrete step` accordingly and propose the shortest script to close the
oldest gates. Exempt: rounds that open no new live gate (dev tooling, refactors covered by
suite + dm-eval). Tobi can explicitly override ("WIP-Override") when a live session isn't
schedulable — note the override in the wrap-up.

Wrap-up messages and Current-focus blocks are for a fresh reader: one plain sentence on what
changed and why it matters for play, then evidence, then at most five lines of mechanism — the
rest goes in the ADR. No arrow chains, no hyphen-stacked compounds.

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
