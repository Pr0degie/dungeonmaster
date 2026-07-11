# ADR 032 — Lean live docs vs. on-demand archive (context-cost split)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Refs:** decision log D63 in progress.md; restructures the continuity docs the session
  ritual governs (`CLAUDE.md`, `progress.md`) — see also the session-ritual skill.

## Context
The project's cross-session continuity lives in two always-loaded files: `CLAUDE.md` (re-sent
to the model **every turn**) and `progress.md` (read in full **every session** per the session
ritual). Both had outgrown their useful-context budget. `progress.md` had reached 1637 lines
(~28K tokens), of which `## Last session` alone was ~756 lines of build history a fresh agent
never needs; `CLAUDE.md` had reached 226 lines carrying per-module how-tos that only matter when
working inside that module. Every session/turn paid for the whole bulk, so even trivial edits
were expensive — Tobi's trigger: "der kontext ist mittlerweile sehr groß und kleinste sachen
fressen viele tokens". Hard constraint: the session-ritual and playtest-triage skills hardcode
certain `progress.md` headings (`## Current focus` / `## Last session` / `## Next concrete step` /
`## Open questions`), the `VERIFY EVIDENCE` field, the `### Phase → ADR map`, and stable `D##`
decision-log refs — the split must leave all of those in the live file.

## Decision
Move history and per-module detail into two new **on-demand** files under `docs/`
(`docs/progress-archive.md`, `docs/conventions.md`), keep only the current working state in the
two live files, and add a **rotation rule** to the session ritual so the live files stay lean
over time instead of re-bloating.

## Alternatives
- **Leave as-is / only trim prose:** rejected — the bulk is structural (accumulated session log),
  not verbose wording, so trimming wording wouldn't move the needle.
- **Conservative slim of `CLAUDE.md`** (move only troubleshooting + style): offered, rejected by
  Tobi in favour of the aggressive split (move all per-module how-tos) for the larger per-turn saving.
- **Delete old history outright:** rejected — Tobi wanted everything preserved; the archive holds
  it verbatim, nothing deleted.
- **Also prune still-open questions:** rejected — only ✅-resolved / completed-phase items move;
  every genuinely-open question stays live (Tobi's explicit instruction).

## Consequences
- **+** ~17K tokens/session reclaimed (progress.md 1637→678) and ~1.5K tokens/turn (CLAUDE.md
  226→153); trivial edits are cheap again.
- **+** History and detail are one hop away via the on-demand table in `CLAUDE.md` / the
  session-ritual skill; nothing is lost — three parallel read-only audits (verbatim-conservation,
  cross-reference, live-correctness) and the 302-green suite confirm a pure move.
- **−** Two more files to keep consistent, and a new discipline: the **rotation step** at each
  wrap-up (move the previous `## Last session` entry, ✅-resolved `## Open questions`, and
  just-completed phases to the archive; keep only the newest 1–2 live). If skipped, the live files
  re-bloat — so the rule now lives in **both** `CLAUDE.md` and the session-ritual skill to make it
  the default. `## Decision log` and `### Phase → ADR map` are explicitly exempt (stay fully live).
- **Binds later work:** future per-module convention edits land in `docs/conventions.md`, not
  `CLAUDE.md`; code-comment doc-anchors that cited moved sections now point at `docs/conventions.md`.

## Addendum — detail preserved from decision log D63 (2026-07-11)

The code-comment doc-anchor repoint covered **9** anchors (all now pointing at
`docs/conventions.md`).
