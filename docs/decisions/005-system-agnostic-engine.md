# ADR 005 — System-agnostic ruleset engine + profile bootstrap

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** decision log D1, D7, D12, D18 in `progress.md`; `architecture.md` §7, §8, §9

## Context

The DM was originally scoped around Warhammer 40,000 / Imperium Maledictum, with a
hardcoded IM dice module (`rules/imperium_maledictum.py`, d100 roll-under). The actual goal
is a **reusable** DM: load any ruleset/adventure as PDFs, and the DM figures out what is
being played. A single hardcoded system contradicts that — different systems use entirely
different dice and resolution (d20 roll-over, d100 roll-under, d6 pools, 2d6+mod, …) and
different character stat schemas.

## Decision

Make the DM **system-agnostic**:

- **Generic engine** (`dmbot/rules/engine.py`): rolls dice (RNG is always code) and resolves
  them per the **active system profile**. Never the LLM.
- **System profile** (`data/systems/<system>.json`): a declarative description of one
  ruleset's core mechanic — dice, resolution (roll-under/over/pool/…), target source, degrees
  rule, optional damage, and the character stat/skill/resource schema.
- **Profile bootstrap (MVP):** on a new ruleset the DM reads the core-mechanics passages
  (RAG) and **proposes a draft profile**; the user confirms/edits it once; it is saved.
- **Persona is layered:** a generic GM core prompt (`prompts/dm_core_de.md`, German) + a
  per-campaign tone/setting overlay. IM + Eisenhorn grimdark is the first system + tone, not
  the DM's fixed identity.

## Alternatives

- **Keep IM hardcoded:** simplest, but a 40k one-off — defeats the reuse goal.
- **Generic dice roller + LLM interprets all rules from RAG:** simplest generic option, but
  the LLM would make rulings/degrees, which drifts and weakens the "dice = code" guarantee.
  Rejected as the primary path; the marker→engine flow keeps resolution deterministic.
- **Auto-detect the profile without confirmation:** LLM-proposed profiles can be wrong; a
  one-time human confirmation is cheap insurance.

## Consequences

- **Positive:** one DM across rulesets; "paste the PDFs and it knows what's played"; dice and
  resolution stay deterministic and unit-testable per profile.
- **Binding:** `rules/` is a generic engine + profile loader, not an IM module; the character
  JSON schema is dictated by the active profile (D12); the generic engine + golden rule #2
  now reads "rolling **and** resolution via engine + profile".
- **Sequencing:** the bootstrap depends on RAG, so it lands in **Phase 10** (after RAG), not
  Phase 8. In **Phase 8** the engine ships with a **hand-written** IM profile; auto-proposal
  from a PDF comes online in Phase 10.
- **Future pay-off (Part 2):** a library of saved system profiles + campaigns to switch between.
