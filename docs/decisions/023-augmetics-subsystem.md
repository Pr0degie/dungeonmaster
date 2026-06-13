# ADR 023 — Augmetik / Implantate subsystem (+ psyker creation-file backfill)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** decision log D52 in progress.md; builds on ADR 022 (psyker/Warp), ADR 005 (system-agnostic engine), ADR 004 (dice/character data); golden rule #2 (dice = code)

## Context

After the psyker subsystem (ADR 022), Tobi asked to also add **augmetics (implants)** in the same
profile-driven style and to **integrate them into the creation pipeline** — the
`docs/how-to-create-a-character.html` form and the `tools/fill_character_sheet.py` sheet filler.

Exploring those two files surfaced a second gap: the just-built **psyker fields**
(`psyker`/`disciplines`/`known_powers`) had never been wired into the creator HTML or the sheet
filler either — so a psyker couldn't be *entered* by a player or *printed* on a sheet, even though
the engine fully supported them. The sheet PDF already has a laid-out psychic-powers table + Warp
boxes (`tools/fill_character_sheet.py` `_PSY_ROWS`/`_PSY_COLS`, `warp_*`) that were simply fed empty
data.

Unlike psykers, augmetics have **no active roll** — they're passive, permanent modifiers.

## Decision

Add a **profile-driven augmetics subsystem** mirroring the psyker pattern (engine stays
system-agnostic, ADR 005): a new optional `augmetics` block in
`data/systems/imperium_maledictum.json` holds the catalog (each implant's body location,
availability, cost, structured `effects`, and a German effect text) and the soft limit
(= Toughness Bonus). `Character` gains an `augmetics: tuple[str,...]` of catalog names.

Effects are split by what the engine can apply deterministically (golden rule #2: dice = code):
- **`armour`** → added to a PC's soak in the damage flow (`augmetic_armour`, used in
  `_apply_attack_damage`).
- **`characteristic`** (e.g. Augur-Array +5 Perception) → added to the test target in
  `resolve_target` via `augmetic_bonus`, matched by the characteristic name **or** an optional
  `skills` list on the effect (so the bonus reaches the governed skill, e.g. Wahrnehmung).
- **`skill_sl`** / **`special`** (situational +SL, Auspex, Mechadendrites, Combat Gland, …) →
  **narrative**: surfaced to the DM in a state-summary block + the persona prompt, with full prose
  from the rulebook RAG. Not auto-applied.

Augmetics are passive, so there is **no marker/button flow** (the psyker `<<MANIFEST>>` analogue is
deliberately absent).

In the same pass, **backfill the creation pipeline** for both augmetics and psyker:
- `docs/how-to-create-a-character.html`: an Augmetik checkbox-grid (with a soft Toughness-Bonus
  limit hint) and a Psioniker section (checkbox + disciplines + known powers), emitting
  `augmetics` / `psyker` / `disciplines` / `known_powers` into the JSON block. Catalog names are
  hardcoded to match the profile exactly (the static handout can't read the profile JSON).
- `tools/fill_character_sheet.py`: fill the existing-but-empty psychic-powers grid from
  `known_powers` × the profile catalog and set Warp Threshold = Willpower Bonus; render augmetics
  into the middle equipment column (the sheet has no dedicated augmetics box).

## Alternatives

- **Narrative-only augmetics (no engine application).** Rejected by Tobi — for the dice to reflect
  armour/characteristic bonuses they must be code (golden rule #2), as with psykers.
- **Encode every augmetic effect mechanically (SL bonuses, Auspex, Mechadendrites).** Rejected —
  these are conditional/contextual; auto-applying them reliably needs context the marker lacks.
  Armour + characteristic are the clean, fully-correct cases; the rest stay DM-adjudicated from RAG.
- **A full skill→characteristic governance map in the profile** (so any characteristic bonus flows
  to all governed skills). Rejected as scope creep; the per-effect optional `skills` list covers the
  headline cases (Augur-Array→Wahrnehmung, Calculus-Logi→Wissen/Logik) precisely and extensibly.
- **Leave psyker out of the creation files.** Rejected — they were unenterable/unprintable; the same
  files were already open, so backfilling now closes the loop.

## Consequences

- **Positive:** implants are enterable (HTML), printable (sheet), and mechanically live (armour to
  soak, characteristic to test target) while staying system-agnostic and data-driven; psykers are
  now fully usable end-to-end too. +10 augmetics tests (suite 230 green). New implants = more JSON
  catalog rows; another system = its own `augmetics` block.
- **Negative / open:** the creator HTML hardcodes the catalog names, so it must be kept in sync with
  the profile (a name mismatch means the engine won't find the implant/power — noted in the file).
  Situational augmetic effects rely on the DM applying them. The standard sheet has no augmetics
  box, so implants print in the equipment column. German skill names (`Psi-Meisterschaft`, the
  augmetics' `skills` lists) must match the sheet's skill keys — verify against the German edition.
