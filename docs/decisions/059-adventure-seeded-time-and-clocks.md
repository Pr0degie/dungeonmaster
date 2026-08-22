# ADR 059 — The adventure ships its own clock; time advances per turn

- **Status:** Accepted (specified; the build and the next debug run are the verification)
- **Date:** 2026-08-23
- **Refs:** completes **ADR 048** (in-game time and deadlines) and **ADR 047** (consequence
  clocks), both of which were code-complete and never ran live; depends on **ADR 057** for the
  scene-change increment; the `<<ZEIT>>` marker contract stays as specified in **ADR 051**.
  Plan: `docs/plans/coherent-campaign-run.md`.

## Context

"Die Mitternachtsfracht" is built on a hard deadline: the lighter leaves Pier Nine at the
midnight siren, the only clearance of the night. Every scene's guidance leans on that pressure.

Through the whole live run of 2026-08-22 the in-game clock read **day 1, 08:00, morning**, while
the fiction played out on the night before midnight. No `<<UHR>>` and no `<<ZEIT>>` marker fired
in 22 turns. The pressure panel therefore never appeared, no deadline ever came closer, and the
only pressure the table experienced was an NPC saying "die Zeit läuft uns davon" in eight of ten
answers — a phrase the model took from the scene's standing guidance, because that guidance is
the only characterisation input it receives.

Two independent causes, both structural. Time only moves when the model emits a marker, and the
markers sit where truncation destroys them (ADR 057). And neither the start time, nor the
deadline, nor a single consequence clock can be shipped with an adventure — they exist solely as
operator commands typed at the table. A campaign whose entire dramaturgy is a deadline had no way
to *state* that deadline to the machine that runs it.

The result is a mechanism that has been code-complete across two ADRs and has never once
functioned in play.

## Decision

1. **Start time, deadlines and consequence clocks become campaign data**, seeded at session start
   from the adventure file. The Midnight Freight starts in the evening with a midnight deadline
   because its own file says so, not because someone remembered to type it.
2. **Time advances per turn, in code.** Each turn costs a small fixed amount of in-game time; a
   scene change costs more. The clock moves whether or not the model cooperates.
3. **The `<<ZEIT>>` marker survives for deliberate jumps** — "you travel for two hours" — with its
   existing clamp. It is now an accelerator on top of a clock that already runs, not the only
   thing that makes time exist.
4. **The deadline is visible to the table** on the player panel, not only inside NPC dialogue.
   Pressure the players can read does not need an NPC to repeat it, which is also what lets the
   scene's standing guidance stop being injected every turn.

## Alternatives

- **Keep marker-only time (the status quo):** rejected. It is the most honest model of fictional
  time — time passes when the story says it does — and it produced a frozen clock for an entire
  evening. A mechanism that depends on a marker this model does not emit is not a mechanism.
- **Advance time only on scene changes:** rejected as insufficient on its own. It ties the clock
  to ADR 057 alone, so a long scene — and this run spent 22 turns in one — costs no time at all.
  Retained as the larger of the two increments.
- **Real time drives in-game time (one minute is one minute):** rejected. It punishes table talk,
  rules questions and technical pauses, and this group's sessions are full of all three.
- **Operator commands only, better documented:** rejected. It is the current design; the
  documentation was not the failure. Something only a human can supply, in the middle of running
  a game, is something that will be missing.

## Consequences

- **+** Two ADRs' worth of finished mechanism (clocks, deadlines, the pressure panel) get their
  first chance to run.
- **+** A campaign built on a deadline can express that deadline, and any future adventure
  inherits the capability.
- **+** The visible deadline removes the reason for the standing guidance that produced the
  repeated clock-checking line.
- **−** Fictional time now advances on a mechanical schedule and will sometimes disagree with the
  narration; the per-turn increment must stay small enough that the disagreement stays cosmetic.
- **−** The adventure format grows fields, and campaigns without them must default cleanly — the
  same migration shape ADR 048 already established for state files missing a clock.
- **−** A deadline that actually expires is now reachable in play. That is the point, but it means
  the failure branch ("the lighter leaves without the Ossarium") stops being theoretical and needs
  to be playable.
