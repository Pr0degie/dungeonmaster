# ADR 063 — Fate points: spend one to reroll a failed test

- **Status:** Accepted (built 2026-10-25; the next run at the table is the verification)
- **Date:** 2026-10-25
- **Refs:** IM Core Rulebook p.220 (Fate, Spending Fate, Burning Fate); subsystem pattern of
  **ADR 022** (psyker) / **ADR 023** (augmetics); code-owned resource per **ADR 015**; golden
  rules #2 and #3. Decision row **D126**.

## Context

In the third Opus run every one of nine tests failed; in the fourth, six of twenty succeeded. The
table asked whether it was them. Starting IM characters sit at skill 35–50 against a default of
Challenging (+0), so roughly one test in three succeeds — that is the system. IM's answer to it is
Fate: every character begins with 3 points, and spending one rerolls a failed Test. Fridolin's
sheet lists 3 Fate; the bot knew nothing about it. Tobi asked for it directly.

## Decision

1. **Profile block `fate`** (`start`: Fate a character begins with when the sheet is silent; IM 3).
   A profile without it has no Fate flow, like `combat`/`psyker`.
2. **Code-owned resource on `Combatant`:** `fate_total` (sheet `fate_total`/`fate`, else the
   profile's start) and `fate_spent` (this session). Persisted in `state.json`, shown in the
   world state as `Schicksal x/y`.
3. **Session start = `!join`:** unset totals are filled from the profile and spent Fate is
   recovered (IM p.220 "at the start of each session").
4. **Spend = reroll a failed test, the second result stands.** A failed test by a player
   character with Fate left gets two buttons, "🙏 Neu würfeln" and "Hinnehmen"; no click within
   `DM_FATE_WAIT_SECONDS` (20) counts as "Hinnehmen". The DM narrates only after the decision,
   so one test is narrated once. The rerolled line says "dieses Ergebnis gilt"; the persona
   tells the DM to narrate only that result.
5. **Scope:** only plain skill tests (the dice button). Manifest tests, the other Spend effects
   (+1 SL, initiative, conditions) and Burning Fate are not modelled; the GM can still grant them.

## Alternatives

- **Reroll after the narration** ("das Schicksal greift ein") — no waiting, but the DM would
  narrate a failure and then reverse it, two narrations per test. Rejected.
- **A `!schicksal` command** instead of a button — slower at the table and easy to forget.

## Consequences

- A failed roll with Fate left now waits for a click (or 20 s) before the DM speaks.
- A `!join` mid-evening recovers spent Fate; the table can exploit that, but a restart after a
  crash should not cost the players their points.
- Spent Fate survives restarts with `state.json`; NPCs never have Fate.
