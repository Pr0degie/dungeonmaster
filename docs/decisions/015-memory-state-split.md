# ADR 015 — Memory: split sheet/state, and auto-applied combat damage

- **Status:** Accepted (code-complete; live gate pending)
- **Date:** 2026-06-09
- **Refs:** decision log D32/D33 in `progress.md`; Phase 9; builds on **ADR 004** (character JSON,
  "sheets → JSON once") + ADR 012 (character store) + ADR 005 (generic engine + profile);
  `architecture.md` §7. Golden rule #3 (memory split: hard facts by code, recap by LLM).

## Context

Phase 9 is memory: the DM must remember **hard facts** (HP, conditions, NPCs, quests, location)
and the **narrative thread** (a recap), across restarts. Two design questions had real
alternatives and were put to the user:

1. **How does the mutable world state relate to the existing read-only `characters.json`?**
   `characters.json` (ADR 004/012) already holds the party sheet — characteristics, skills,
   `wounds`/`max_wounds`, aliases — transferred **once** from the player sheets. `architecture.md`
   §7 sketched a single world-state blob that also carries the live wounds. So: extend/rewrite that
   one file, or keep the sheet read-only and add a separate mutable layer?

2. **How does an HP change actually happen** (the deterministic-advancement path the gate needs)?
   A GM command (`!damage`), or wire the dice engine's damage into combat so a successful attack
   auto-applies wounds?

## Decision

**1. Split (chosen).** `characters.json` stays the **read-only source** (the once-only sheet
transfer + aliases). A new **code-owned** `data/sessions/<channel_id>/state.json` holds the
**mutable** layer: current wounds / conditions / inventory per character, the NPCs in play, quests,
location, in-game time, and the stored recap. On the first `!join` for a channel, `state.json` is
**seeded once** from the sheet (`WorldState.seed_from_store`); thereafter **code only ever writes
`state.json`** — the sheet is never rewritten. New module `dmbot/memory/state.py` (`WorldState` +
pure advancement functions + atomic save/load). State is saved on **every** change (atomic temp +
`os.replace`), so "an HP change survives a restart" holds even without a clean shutdown.

**2. Auto-applied combat damage (chosen).** On a **successful attack test** (skill ∈ the profile's
`combat.attack_skills`), the engine rolls the attacker's weapon damage, the cog computes wounds lost
= **weapon damage + SL − soak** (soak = Toughness Bonus + armour) and applies it to a target, then
feeds the result back so the DM narrates the consequence. The target is auto-chosen if there's one
candidate, else picked from a Discord dropdown (`discord_ui/target.py`) over the scene's NPCs + the
party. NPCs are registered with `!npc add`. `!damage`/`!heal` remain as GM overrides.

**Recap** (D14 trigger): `!wrap up` / `!wrapup` asks the LLM (via `DMBrain.summarize`) for a German
"Was bisher geschah" from the channel history, code stores it in `state.json` (+ a human-readable
`recap.md`), and `!join` re-injects it — plus a compact world-state block — into the prompt, in the
CLAUDE.md order (persona → recap → state → history).

**System-agnostic:** the combat model is profile-driven — a `combat` block declares
`attack_skills`, a `weapons` damage table, `default_damage`, and the `soak` source
(`{characteristic, mode}`). A profile without a `combat` block simply has no auto-damage (tests
still roll and report). IM fills it in; the weapon-damage values are **approximate** Core-Rulebook
figures for the example party's gear, to be tuned when real loadouts are entered.

## Alternatives

- **Single world-state blob, code rewrites `characters.json`** (literal §7): matches the schema
  sketch, but code overwriting the hand-authored source is risky (a bug corrupts the sheets), loses
  the file's comments/formatting, entangles the once-only transfer with runtime state, and makes a
  session reset awkward. Rejected for the split.
- **GM `!damage` command only, no auto-combat:** smaller, satisfies the gate, but the user wanted
  the engine's damage actually wired into play. Kept as an override, not the primary path.
- **Parse the target from narration / the player's words:** unreliable; a dropdown over known
  combatants is deterministic. `!npc add` is the explicit, testable enemy-registration path
  (auto-extraction of NPCs from narration is a later, LLM-extraction refinement).

## Consequences

- **Positive:** the sheet stays pristine and diffable; resetting a session = delete `state.json`;
  the gate is clean (save-on-change → HP survives a restart; recap re-injected on join). The dice
  engine's damage is now realised in play (the natural Phase-8 → Phase-9 hook). Memory math is pure
  and unit-tested (`tests/test_memory_state.py` + `test_memory_recap.py`), 102/102 green.
- **Binding:** `state.json` is generated, per-channel, and git-ignored (the `_example` party is the
  only checked-in session data). The `combat` block is now part of the profile contract.
- **Limits / to verify live:** weapon-damage numbers are approximate; NPC names are single-token for
  now (`Kult_Anführer`); the soak model is TB + armour (armour defaults to 0; no hit-location).
  The recap **quality** and the full "HP survives restart + recap on next session" loop are the
  live gate — pending a Discord run by Tobi.
