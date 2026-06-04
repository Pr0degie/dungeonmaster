# ADR 004 — Dice tests & character data

- **Status:** Accepted (refined by ADR 005)
- **Date:** 2026-06-04
- **Refs:** decision log D11 & D12 in `progress.md`; `architecture.md` §7 & §9

> **Update (ADR 005):** the system is now system-agnostic. `rules/imperium_maledictum.py`
> below became the generic `rules/engine.py` + an IM **profile**, and the character JSON
> schema is dictated by the active profile rather than fixed IM fields. The marker→engine
> flow and "sheets → JSON, not RAG" decisions still hold.

## Context

Dice and successes are computed by code, not the LLM (golden rule). What was open was
*how* the DM requests a test and how the result flows back into the narrative — and
whether the bot needs to know the character stats in order to compute success and success
level.

## Decision

- **Test trigger:** the LLM emits a machine-readable marker in its answer text, e.g.
  `<<TEST Perception +10>>`. The orchestrator detects it, shows a dice button to the right
  player, `rules/imperium_maledictum.py` rolls d100 and computes the SL, the result feeds
  back into the next prompt. **Fallback:** if parsing fails, the DM states the test in
  plain text and you roll manually.
- **Character data:** characters live as **lean structured JSON** (name, characteristics,
  relevant skills, wounds, inventory) in the world state. The PDF sheets are only the
  human-readable source, transferred **once** into the JSON. This lets the code roll
  stat-aware (target + SL automatically) and track HP. **Character sheets do not go into
  RAG.**

## Alternatives

- **Strict JSON instead of a bracketed marker:** less reliable to produce for a 12B model;
  the marker is more forgiving and easier to parse.
- **Neutral roll (bot knows no stats):** the player compares against their own sheet.
  Simpler, but no automatic SL, no HP tracking — and HP tracking we wanted for the memory
  anyway (D3).
- **Sheets into RAG:** mixes mutable player stats with static rule knowledge; stats change
  (HP, inventory) and belong in the deterministically maintained state.

## Consequences

- **Positive:** the loop stays mostly automatic but robust; Phase 8 (dice) and Phase 9
  (memory/HP) become one connected piece instead of two sites.
- **Binding:** `rules/` must process test-marker inputs (skill + modifier); the
  orchestrator needs a marker parser with a tolerant fallback. The character JSON schema
  must exist before Phase 8, because registration (ADR 003) and stat-aware rolls build on it.
- **Prerequisite:** transfer each character's relevant IM stats from the sheet into the
  JSON once.
