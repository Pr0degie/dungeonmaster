# ADR 062 — Improvised NPCs join the scene through a post-turn classifier

- **Status:** Accepted (built 2026-10-25; the next run at the table is the verification)
- **Date:** 2026-10-25
- **Refs:** third post-turn classifier on the boundary of **ADR 057** (scene) and **ADR 058**
  (facts), same call pattern and failure posture; scene presence from **D107** (`npcs_here`);
  auto-damage from Phase 9 (**ADR 015**); golden rule #3. Decision row **D124**.

## Context

In the fourth Opus run (2026-10-25) Opus invented the opposition on the spot: a "Kettenmann" at
the shrine door, later named Brenna, a "Hakenmann", two and then four more chain-gang thugs. None
of them existed in the world state — only the adventure's scene NPCs are registered, on entering
a scene. When Fridolin's shot hit, the target picker offered every living registered NPC plus the
party: Seneschal Kaad (two scenes away), Rektalus, Sister Vall. Tobi had to pick someone, picked
Kaad, and two hits later the quest-giver stood in the state at 0/8 — "kampfunfähig", and therefore
gone from the prompt — while the narration said Brenna fell.

Two faults stack: the picker is not scoped to the scene, and the people the DM improvises never
become state. Tobi chose to have the bot register new opponents itself as the DM introduces them,
over a manual "other target" button.

## Decision

1. **A post-turn classifier reports who is physically present.** After each narrated turn a
   stateless constrained-JSON call (aux tier, in the same `gather` as the scene and fact
   classifiers) lists at most four people who appear *in person* at the group's location and act
   or speak, and who are not yet listed as present. Mentioned or absent people, player
   characters and crowds without individuals are excluded. Each entry is a short label (the name
   the narration uses, or a noun like "Hakenmann") plus an optional statblock from the
   adventure's roster when the person clearly is that statblock.
2. **Code validates and writes.** Labels pass a shape gate (length, no quotes/markup, not a
   player name or a first-name variant of one); the statblock must be one of the offered roster
   names or empty. A known NPC is moved into the current scene; a new one is registered with the
   statblock's numbers, otherwise with the profile's `combat.improvised_npc` defaults (IM: 10
   wounds, TB 3), attitude neutral.
3. **Presence is state, not only the scene card.** A `Combatant.scene` field records where an NPC
   was last seen. "Present" means living and either on the current card's `npcs_here` or seen in
   the current scene. The prompt's "NSCs in der Szene" line, the NPC-memory block and the attack
   target picker all read this one definition.
4. **The target picker offers present NPCs only** (then the party, for friendly fire). NPCs
   elsewhere are never targets; with nobody present it says so instead of offering strangers.
5. **Switchable and fail-open** like its siblings: `DM_NPC_ROUTER` (default on) and
   `!automatik nscs`. A failed or malformed verdict registers nothing and logs one line.

## Alternatives

- **"Anderes Ziel" button with a typed name** — cheapest, no model call, but the table types a
  name mid-fight and the prompt still never learns who is there. Rejected by Tobi.
- **Classify at hit time** ("whom did the shot hit?") — one call only when needed, but the NPCs
  stay unknown to the prompt and the presence line until someone fires.
- **An `<<NSC>>` marker from the narration model** — the house rule is that the narration model's
  markers are the weak path (D43); a separate classifier is the established remedy.

## Consequences

- One more aux call per turn (~3–5 s, hidden behind playback like the other two).
- Duplicates are possible when the narration renames someone ("Kettenmann" → "Brenna"); the
  classifier sees the present list and is told not to re-register, but the guard is soft. A
  duplicate costs a wrong entry in the picker, not a wrong fact about the plot.
- Improvised NPCs persist in `state.json` like any registered NPC.
