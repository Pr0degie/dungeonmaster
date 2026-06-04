# ADR 001 — Ruleset: Imperium Maledictum

- **Status:** Accepted (refined by ADR 005)
- **Date:** 2026-06-03
- **Refs:** decision log D1 in `progress.md`; dice logic in `architecture.md` §9

> **Update (ADR 005):** the DM is now system-agnostic. IM remains the **first** ruleset, but
> it is not hardcoded — the `rules/imperium_maledictum.py` mentioned below became the generic
> `rules/engine.py` + the IM **profile** `data/systems/imperium_maledictum.json`.

## Context

The AI DM should run Warhammer 40,000 tabletop in the Eisenhorn tone (investigation,
Inquisition, intrigue). The chosen system determines two things: the tone the setting
carries, and — because the dice logic lives in code (not the LLM) — how complex and
error-prone the deterministic rule engine becomes.

## Decision

Imperium Maledictum (Cubicle 7, d100 roll-under with success levels) as the basis.

## Alternatives

- **Dark Heresy 2e (FFG, d100):** thematically the most direct Eisenhorn hit (you play an
  Inquisitor's acolytes), nearly identical dice logic. But out of print and with known
  balance quirks at higher tiers.
- **Wrath & Glory (Cubicle 7, d6 pool):** more heroic power level, combat-heavy. The d6
  success pool with special symbols would be more error-prone in code, and the tone fits
  the investigative Eisenhorn style less well.

## Consequences

- **Positive:** d100 roll-under is the simplest dice logic there is (roll d100, compare to
  target, SL = difference of the tens digits) — easy to get right and unit-test in
  `rules/imperium_maledictum.py`. The tone (patron rather than hero, investigation rather
  than battle) hits the request. The most modern and cleanest of the three systems.
- **Negative / binding:** the rule engine is tailored to IM mechanics (success levels,
  advantage/disadvantage, d10/d5 damage). A later system switch would touch `rules/` and
  parts of the Discord UI buttons. RAG ingestion should target the IM rulebook PDF.
