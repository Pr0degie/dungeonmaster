# ADR 022 — Psyker / Warp subsystem (Imperium Maledictum psychic powers)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D51 in progress.md; ADR 005 (system-agnostic engine), ADR 004 (dice/markers/character data), ADR 015 (memory state split); golden rules #2 (dice = code) and #7 (rules from the rulebook)

## Context

The party wants to play psykers, the signature (and most dangerous) part of Imperium Maledictum:
manifesting psychic powers builds **Warp Charge**, and exceeding your **Warp Threshold** risks the
**Perils of the Warp**. None of this existed in code — psykers, like augmetic implants, lived only
as lore in the extracted rulebook. Tobi asked for the **fully rules-faithful** version, not a
narrative-only stand-in, and pointed at the Inquisition Player's Guide for additional powers.

Constraints that shaped the design:
- **The engine must stay system-agnostic (ADR 005).** IM is one profile among future ones; no IM
  psyker rule may be hardcoded in `engine.py`.
- **Dice = code, narration = LLM (golden rule #2).** The Manifest Test, Warp Charge math and the
  Perils/Phenomena table rolls are deterministic and must run in the engine, never the model.
- **The full power catalog is huge and the rulebook prose is what RAG already serves (golden rule
  #7).** Re-encoding every power's bespoke effect as code would duplicate the rulebook badly (and
  the PDF OCR is lossy).

## Decision

Add a **profile-driven psyker subsystem**: all IM-specific data (the power catalog with each
power's Warp Rating + Difficulty, the Warp Threshold formula, and the d100 Perils-of-the-Warp and
Psychic Phenomena tables) lives in `data/systems/imperium_maledictum.json` under a new optional
`psyker` block. The engine gains generic, pure functions that read that data:
`resolve_manifest` (Manifest Test via the existing `resolve_test`, Warp Charge per p.163,
Critical/Fumble/Push), `resolve_perils` and `resolve_phenomena` (banded d100 lookups), plus
`reverse_d100` + an `advantage` parameter on the roll-under resolver for IM's reverse-the-digits
Advantage (Pushing). A profile with no `psyker` block simply has no Warp flow — exactly like the
optional `combat` block.

The **mechanical spine is fully faithful**; each power's narrative **effect** is served by the
rulebook RAG (Core Rulebook + Inquisition Player's Guide), with a short German effect gist in the
catalog for the prompt. The catalog is seeded with every Core minor power, the core Biomancy
powers, and representative Player's Guide Inquisition powers, and is extensible in the same shape.

Plumbing mirrors the existing dice flow (ADR 004): a new `<<MANIFEST power [für name] [push]>>`
marker → `ManifestRequest` → the cog posts a button → the engine rolls and bookkeeps → the result
is fed back so the DM narrates. Warp Charge is a **code-owned mutable resource** on `Combatant`
(ADR 015), persisted in `state.json` and shown in the world-state summary.

## Alternatives

- **Narrative-only (Variant A/B):** treat powers as skill-like tests, no Warp/Perils. Rejected —
  Tobi explicitly chose full fidelity; Warp Charge/Perils is the point of playing a psyker.
- **Hardcode IM psyker rules in the engine.** Rejected — violates ADR 005; the tables/threshold
  belong in the profile as data so other systems can declare their own (or none).
- **Encode every power's full mechanical effect in code.** Rejected — enormous, duplicates the
  rulebook, and fights golden rule #2's companion ("narration = LLM"); the bespoke per-power
  resolution (opposed tests, conditions) is what the DM adjudicates from the RAG'd rule text.

## Consequences

- **Positive:** psykers are playable end-to-end and rules-faithful on the parts that matter
  mechanically (Manifest, Warp Charge, Threshold, Perils, Pushing, Sustained). The engine stays
  generic and unit-tested (29 new fixed-seed tests; suite 220 green). Adding more powers = more JSON
  rows; adding psykers to other systems = another profile's `psyker` block.
- **Timing simplification (documented):** IM runs the end-of-turn containment Test at the psyker's
  turn end. The conversational loop has no hard turn boundary, so the cog resolves the containment
  Test (and any Perils) at the **end of the manifesting action** — deterministic and visible rather
  than relying on the LLM to remember to trigger it later. Strict per-round timing is out of scope.
- **Negative / open:** the Psychic Phenomena table was reconstructed from lossy PDF OCR — a few band
  boundaries (≈59–64, 68–73, 80–85) were merged and should be verified against the physical book
  (the Perils table is complete). The play-language skill names `Psi-Meisterschaft` /
  `Disziplin (Psi)` must match the sheet's skill keys (verify against the German edition's terms).
  Force-weapon Warp-Charge bonus damage and Null-Rod/Familiar interactions are flagged in the
  profile but not yet wired into the combat engine. The Inquisition Player's Guide is extracted to
  Markdown but **not yet embedded** into the rules RAG (Ollama was down) — run the ingest command in
  progress.md when Ollama is up so the DM retrieves the full Inquisition catalog.

## Addendum — detail preserved from decision log D51 (2026-07-11)

- Concrete profile values: **Warp Threshold = Willpower Bonus**; each catalog power carries its
  **Warp Rating + Difficulty**. The subsystem implements IM **ch. VI**.
- IM's reverse-the-digits Advantage (served by `reverse_d100` + the `advantage` kwarg on the
  roll-under resolver) is per rulebook **p.189**.

## Amendment (2026-11-27) — a power's flat damage is data, resolved by code

Live run 2026-11-27: a successful Smite was narrated as a hit while the target's wounds stayed
untouched — nothing applied damage for a manifested power. The rejection above of "every power's
full effect in code" stands; the narrow exception is **damage a power deals the moment it
manifests**, which is hard state (golden rule #3) and must not be left to the narration.

- A damaging power carries a structured `damage` block in the catalog:
  `{"base": "<dice notation>", "bonus": {"characteristic", "mode"}, "add_sl": bool,
  "ignores": ["armour" | "toughness_bonus"], "targets": "one" | "area"}`. Read through
  `SystemProfile.power_damage`; the German `effect` text is never parsed.
- `combat.resolve_power_damage` (pure, injected RNG, mirrors `resolve_attack`) rolls the base, adds
  the psyker's characteristic bonus and the Manifest SL, and subtracts the target's soak minus the
  ignored parts. "armour" covers worn and augmetic armour.
- IM seeding: Smite (2 + WilB + SL, ignores armour), Force Bolt (6 + WilB + SL), Nova and
  Bio-Lightning (4 + WilB + SL, area). Left narrative on purpose: Haemorrhage and Life Leech (an
  opposed test or a per-turn link decides), Sear (on touch), Spectral Hands, Stimulating Jolt.
- **Reading of "ignores Armour":** the engine's soak is Toughness Bonus + armour (Phase 9), while
  IM p.214 reduces damage by armour only. Within the engine's soak, "ignores Armour" drops the
  armour and keeps the Toughness Bonus — the conservative reading; Life Leech's "ignores Armour and
  can't be reduced in any way" is what `ignores: ["armour", "toughness_bonus"]` expresses.
- Wired the same day (D153): `DiceCog._finish_manifest` feeds the result that stands and, for a
  successful power whose block says `"targets": "one"`, starts the damage flow of a weapon hit — the
  target from the psyker's own line or the picker (`combat.choose_attack_target`, D151), the wounds
  through `_book_damage`. There is no shortcut for a lone NPC (a power may be aimed at a door), the
  picker offers "nobody", and without an NPC in the scene the result is narrated only. Bio-Lightning
  is booked on its primary target (`"targets": "one"`; the creatures next to it are the GM's call),
  Nova keeps its block but stays narrative: who stands in the zone is the GM's call. Live-unverified.
