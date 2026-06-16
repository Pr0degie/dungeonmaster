# ADR 037 — Extract attack & warp resolution into a pure rules module (`rules/combat.py`)

- **Status:** Accepted
- **Date:** 2026-06-16
- **Refs:** decision log **D79** in progress.md; from the `/improve-architecture` candidate set
  (candidate #2). Builds on **ADR 029** (SessionRuntime + cog split), **ADR 022** (psyker/Warp),
  **ADR 023** (augmetics → soak), **ADR 015** (auto-combat damage), **ADR 005** (system-agnostic
  engine + per-system profile). Governed by **golden rule #2** (dice rolling *and* resolution are
  deterministic code, never the LLM). Continues the testability/deepening line but is a **rules-layer**
  move, distinct from the context-leanness moves of ADR 034/035.

## Context
After ADR 029 split the voice god-cog, the *request → target* half of combat was already pure and
tested (`resolve_target`, `resolve_manifest_request`, `engine.resolve_test/resolve_damage/
resolve_perils`). What stayed end-to-end **untested** lived as methods on `DiceCog`, reachable only
through a live Discord cog:

- the **soak montage** in `_apply_attack_damage` — the PC/NPC branch + Toughness Bonus + armour +
  augmetic armour (ADR 023);
- the `roll_damage → resolve_damage → apply_damage` chain and the downed detection;
- the **Warp containment → Perils** sequence in `_resolve_warp_consequences` (ADR 022).

The smell that this was stuck in the cog: `tests/test_augmetics.py` already had to do
`DiceCog.__new__(DiceCog)` + a `SimpleNamespace` just to reach `_toughness_bonus`. The project's
signature ("dice = code") had a deterministic core with no fixed-seed test surface for *resolution*.

## Decision
Extract the pure arithmetic into a new module **`dmbot/rules/combat.py`** — `toughness_bonus()`,
`resolve_attack() → AttackOutcome`, `resolve_warp_consequences() → WarpConsequence` — with **no
Discord and no WorldState mutation**, the RNG injected. The cog **delegates** and keeps the state
mutations (`state.apply_damage` / `state.reset_warp_charge`) and the post-mutation narration
(`engine.describe_damage_de`, which reads the *updated* wounds).

**The seam (the real trade-off): the pure function stops *before* the WorldState mutation.**
`resolve_attack` returns the soak breakdown + the `DamageResult`; `resolve_warp_consequences` returns
the Perils/containment `lines` + a `reset_charge` flag. The cog applies the wounds, then calls the
already-pure `engine.describe_damage_de` with the post-mutation wounds, and resets Warp Charge iff
`reset_charge`.

`_toughness_bonus` stays on the cog (its existing test calls `cog._toughness_bonus(...)`) but its body
is now a one-liner delegating to `combat.toughness_bonus` — **zero test edits**, new tests hit the
pure functions directly. Suite **343 green** (+7 `test_segments` from the parallel candidate #1, +12
`test_combat`), ruff clean, no existing test touched.

## Alternatives
- **"Full outcome"** — also reproduce the wound arithmetic (`current − applied`, clamped) inside the
  pure function so it can emit the `downed` flag + the finished narration line in one object.
  **Rejected:** that duplicates `WorldState.apply_damage`'s clamp in a second place; any future drift
  between the two silently desyncs the narrated number from the actual state — exactly the
  behaviour-drift hazard the "behaviour-neutral" discipline forbids. The narration genuinely depends on
  post-mutation wounds, so the **mutation is the natural cut**, and `describe_damage_de` is already a
  pure engine function on the cog side.
- **Leave it on the cog / mixin:** rejected — a cog method reachable only via Discord gives the
  deterministic core no fixed-seed test surface; the resolution arithmetic is the signature worth
  hardening.
- **Move `_toughness_bonus` wholesale (drop the cog method):** rejected — it would force a
  `test_augmetics` rewrite. Keeping the cog method as a thin delegator yields zero test edits (the
  strongest "no behaviour change" signal).
- **Hand-retype the German Perils/Overt strings:** rejected — copied byte-for-byte from `dicecog.py`
  (🜏 / em-dash / → verified identical) to eliminate glyph drift.

## Consequences
- **+** The soak montage and the Warp containment→Perils chain are now **fixed-seed unit-testable**
  (`tests/test_combat.py`) with plain duck-typed inputs — same seed → exact soak breakdown, applied
  wounds, and Perils lines — without a cog or Discord.
- **+** Behaviour provably unchanged: byte-equivalent move, full suite 343 green with **zero**
  existing-test edits, ruff clean. No number, string, flag-default, or log-message changed.
- **+** `combat.py` is engine-adjacent and system-agnostic (numbers still come from the profile, ADR
  005) → reusable by a second system profile later.
- **−** The cog keeps a thin seam: it resolves `target_sheet` and passes it in, and applies
  `reset_charge` itself. One greppable indirection, caught instantly by the suite.
- **−** The `downed` flag + final narration line stay on the cog (they need post-mutation wounds);
  trivial and built from the already-pure `describe_damage_de`, so little is lost.

_Companion mechanical change this round (no ADR — it only finishes an already-started extraction):
candidate #1 wired the pre-existing pure `stt/segments.py::confident_text` (Whisper hallucination
guard) into `transcriber.py`, dropping the inline duplicate + dead constants, and added
`tests/test_segments.py` (the boundary `==0.7`/`==-1.0` are kept — strict `>`/`<`)._
