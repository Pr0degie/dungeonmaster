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

## Amendment (2026-11-14) — Fate on a failed Manifest Test

- **Status:** built 2026-11-14, **live-unverified** — suite only. Decision row **D145**.
- **Rule check (IM Core):** "Spending Fate" (p.220) lists "Reroll a failed Test" with no exception for
  the Psychic Mastery Test; the Manifest Test *is* that Test (p.161). The only named exception in the
  book is reading the Emperor's Tarot. Tobi asked for it after the run of 2026-11-14.

A failed Manifest Test by a player character with Fate left gets the same two buttons as a skill
test. **Warp Charge, a Sustained power and the Perils risk are booked only after the choice**, from
the result that stands: step 3 of manifesting ("Gain Warp Charge", p.161) depends on that result.
A reroll runs against the same Warp Charge as the first roll and is thrown like it.
