---
name: session-ritual
description: Use at the start of a working session for the handshake (CLAUDE.md + the State header of progress.md, more only for subsystem/phase work), and at the end of a bigger round or on "wrap up" / "update progress" to update progress.md within its size caps, rotate history, check the WIP limit and scaffold the next-numbered ADR. Small rounds update progress.md inside the change's own commit and don't need this skill.
---

# Session ritual — handshake, wrap-up, ADR scaffold

State lives on disk so the project survives context clears and model switches. `CLAUDE.md`
holds the short form; this skill holds the full procedure. Reading costs context, so read only
what the task needs.

## Start handshake

1. **Always:** `CLAUDE.md` (auto-loaded) and ONLY the State header:
   `sed -n '/^## State header/,/^## Current focus/p' progress.md`.
2. **Subsystem or phase work only:** the governing ADR(s) from the **phase → ADR map** in
   `progress.md` (mandatory in that case), and skim `docs/lessons/README.md`. In an ADR, grep
   the headings first (`grep -n "^## " <adr>`), read `## Decision` and the newest amendment,
   the rest only if the task needs it. A small task (one feature, a fix, a doc edit, a
   question) skips this step.
3. State in 2–3 sentences where we are and what's next. Don't touch files before that. If the
   WIP limit makes this a live-verification session, say so here.

Never read eagerly: `architecture.md`, `roadmap.md`, `SETUP.md`, `docs/conventions.md`, older
ADRs, single lessons, `docs/progress-archive.md`, and `docs/decision-log.md` (grep one
`| D## |` row instead).

## Wrap-up

**Small round** (one feature or fix, no phase change, no new live gate): put the progress update
**into the change's own commit**: one bullet under `## Last session`, the State header's
`Newest round` / `Next concrete step` line if it changed. A later `wrap up` then only checks the
caps below and says "already done". Don't reload this skill just to confirm that.

**Bigger round:** update `progress.md`:
- `## Current focus` — only if the phase changed
- `## Last session` — what we actually did
- `## Next concrete step` — the specific next action, not a vague goal
- `## Open questions` — what surfaced but isn't actionable yet
- the phase's `VERIFY EVIDENCE` field — when a gate was met
- a decision with a trade-off → next `D##` row in `docs/decision-log.md` (+ ADR, below)

**Caps (checked every wrap-up, cheap: `wc -c progress.md` and `awk 'length>600' progress.md`):**
- `progress.md` **≤ 40 KB**. Over it → rotate before committing.
- State header ≤ 25 lines. `## Current focus` ≤ 2 blocks. `## Last session` ≤ 2 entries — when
  you add one, move the oldest to `docs/progress-archive.md` (`## Last session (Verlauf)`).
- No line over ~600 chars in `progress.md`: long index lists of archived entries belong in the
  archive, live keeps a one-line link.
- ✅-resolved open questions and finished phases (full `VERIFY EVIDENCE` → one-line summary live)
  rotate to the archive.
- Decision-log rows with an ADR: max 2 lines (what + one-clause why + → ADR NNN). The log and
  the phase → ADR map are never rotated (stable `D##` refs).

**WIP limit:** max 3 open live gates. A round that would leave a fourth open doesn't start —
set `## Next concrete step` to a live-verification session and propose the shortest script to
close the oldest gates. Exempt: rounds that open no live gate (dev tooling, refactors covered by
suite + dm-eval). Tobi can say "WIP-Override" when a live session isn't schedulable — note it.

Write for a fresh reader: one plain sentence on what changed and why it matters for play, then
the evidence, then at most five lines of mechanism — the rest goes in the ADR. No arrow chains.

## new-adr — scaffold the next decision record

Only when a decision weighed a real trade-off with alternatives seriously on the table (trivia
stays a row in `docs/decision-log.md`). Next sequential number, never reused:
`docs/decisions/NNN-short-title.md`.

```markdown
# ADR NNN — Title

- **Status:** Proposed | Accepted | Superseded by ADR NNN
- **Date:** YYYY-MM-DD
- **Refs:** decision log DX (docs/decision-log.md), optionally architecture.md §Y

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
it. If it changes a design choice, update `architecture.md` in the same change. An ADR that has
grown past ~15 KB of amendments: put a 3–5 line `## Current state` summary right under
`## Decision`, so a reader gets the live truth without reading every amendment.
