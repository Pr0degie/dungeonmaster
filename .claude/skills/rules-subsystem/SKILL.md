---
name: rules-subsystem
description: Use when adding a new profile-driven rules subsystem to a system profile (in the style of the psyker or augmetics subsystems) — e.g. a new test type, resource, combat mechanic, or character-data block. Scaffolds the profile data block, pure engine functions, fixed-seed tests, state-summary integration, an optional in-band marker + button, and a persona hint.
---

# Add a profile-driven rules subsystem

The engine is **system-agnostic** (golden rule #7) and **deterministic** (golden rule #2):
the rules live in the active profile (`data/systems/<system>.json`), the engine just applies
them. A new subsystem follows the exact shape of psyker (ADR 022) and augmetics (ADR 023).
**Read ADR 005, 022, and 023 before starting.**

## The pattern (psyker / augmetics)

1. **Data goes in the profile, never in the engine.** Add a new top-level block to
   `data/systems/<system>.json` (catalog + any banded d100 tables). Example blocks already
   there: `psyker` (power catalog + Warp threshold + Perils/Phenomena tables), `augmetics`
   (catalog with `effects`). Other systems are just other profiles — never hardcode IM.
2. **Pure functions in `dmbot/rules/engine.py`.** Style to mirror: `resolve_manifest`,
   `resolve_perils`, `resolve_phenomena`, helpers like `reverse_d100`. Keep them pure and
   fixed-seed-testable; read the profile block as data.
3. **Roll vs passive.**
   - Needs a roll → add an extractor + `Request` dataclass in `dmbot/rules/marker.py` **plus a
     row in its `MARKER_SPECS` registry** (ADR 051 — the row alone wires strip, streaming
     withholding, pending queue, replay journal and dm-eval), and a confirm button in the
     **Dice cog**, mirroring the `<<TEST>>` / `<<MANIFEST>>` flow (marker → Request → button →
     engine rolls + bookkeeps → fed back to narrate). Reuse the `<<…>>` delimiter so the
     existing strip/withhold-from-TTS guards apply for free.
   - Passive (no roll, e.g. augmetics) → **no marker**; apply the effect where it's consumed
     (e.g. soak / characteristic / skill bonus in attack/target resolution).
4. **Stateful resource → code-owned.** If the subsystem tracks a mutable resource (Warp Charge
   is the example), put it on `Combatant`, persist it with the rest of world state, and show
   it in the state summary. The model never writes it (golden rule #3).
5. **Fixed-seed tests** in a new `tests/test_<subsystem>.py`, modelled on `tests/test_psyker.py`
   and `tests/test_augmetics.py` (seeded RNG, asserted exact outcomes incl. crit/fumble/edge
   bands).
6. **Surface it to the DM.** Add a block to the state summary so the value reaches the prompt
   as structured data, and a short persona line in `prompts/dm_core_de.md` (German). Per-entry
   prose (full power/implant descriptions) comes from **RAG**, not the profile (golden rule #7).
7. **Run the suite** (`uv run --with pytest python -m pytest`) and **write an ADR** — a new
   subsystem is a real decision.

## Gotchas

- German skill/characteristic names must match the German edition — flag any you can't confirm
  as "verify against the book" (this bit psyker and augmetics).
- If a player-facing tool encodes the catalog (e.g. `tools/fill_character_sheet.py`,
  `docs/how-to-create-a-character.html`), the catalog names there must stay in sync with the
  profile.
- Banded d100 tables from OCR'd books often have merged boundaries — verify band edges against
  the source.
