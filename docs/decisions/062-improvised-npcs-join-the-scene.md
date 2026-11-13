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

## Amendment (2026-11-13) — a sighting follows the turn's scene; card NPCs are recognised

- **Status:** built 2026-11-13, **live-unverified** — suite and `dm-eval` only; the next run at
  the table is the verification. Decision row **D138**.
- **Evidence:** [npc-sighting-stale-scene-2026-11-13.md](../plans/npc-sighting-stale-scene-2026-11-13.md)
  (00:40, "Schreinschwester" filed under `zollhaus`) and the run of 2026-11-13, 01:59–02:01.

**What the table showed.** Four sightings, four second entries. "Schreinschwester" is Schwester
Cassia Vall, filed under the scene just left because the pointer moved while the classifier was
thinking. "Frau hinter der Sichtklappe" is Bree Marlok at the pawn hall's door, filed under
`schrein` at 01:59:57 — the `<<ORT>>` button was confirmed at 02:00:19, after the turn boundary
had finished. "Blinder Greis" is Alter Fenk and "Türwächter" is Bree Marlok again (the eye behind
the flap; the narration names no guard): the pointer already stood on `pfandhalle` and both stood
in the "already present" list, but the classifier only ever saw their names, never their roles.

6. **A sighting belongs to the scene the pointer stands on when the turn is over, not the one
   it began in.** `close_turn` files the sightings under the pointer as it stands when the
   verdict comes back. Until the next turn boundary begins, the NPCs filed in this turn follow
   every pointer move: the classifier's own move in the same turn, the `<<ORT>>` button
   confirmed late, `!ort`, the ↩ undo (which takes them back).
7. **Candidates carry their role.** The classifier is given the scene-card people of the current
   scene and of every exit reachable right now (the set the scene classifier gets) as
   "name — role", and is told that a person who fits one of them is that figure. The roster is
   otherwise unchanged; the verdict still only names people.
8. **Code decides identity**, over the same candidate set taken from the scene the sighting
   lands in. In order: the label is a known NPC's name → that NPC moves (unchanged). The
   statblock or the label names a candidate → the sighting is that person, under their own name
   and with their statblock. The label equals a candidate's role or its leading words
   ("Schreinschwester" for "Schreinschwester der Aschenheiligen") and fits no second candidate →
   the same. Otherwise #2 applies.
   **Who is a single person is read from the data, never from the name:** a figure that a scene
   card lists in `npcs_here` is one person. A statblock no scene card lists stays a template
   that lends its numbers to as many improvised people as the narration shows. One exception,
   also data: a statblock the adventure flags `generic` stays a template even on a card —
   "Kettenbund-Schläger" stands on a card of the debug campaign, and merging every thug of that
   fight into one entry would undo #1.
   Outside the candidate set a statblock is a template as before: a misjudged verdict must not
   pull a plot NPC from across the adventure into the room.

**Behaviour change.** Until now a sighting with a card NPC's statblock became a second NPC with
that statblock's numbers; now it is that NPC.

**What gets worse.** Someone seen in the old scene before the group leaves — the runner who
hands over a letter in the Zoll-Sakristei in the answer that then walks the group to the
shrine — was filed correctly until now and lands in the shrine: in the prompt's scene line and
in the target picker. The verdict cannot tell the two apart without naming a scene, and that is
code's call (golden rule #3). Accepted because every live case was an arrival and an answer
that narrates a move ends at the destination.
Also: a second person with a card NPC's role (another Schreinschwester in the shrine) gets no
entry of their own, and a wrong candidate statblock now merges instead of duplicating.

**Not covered.**
- A sighting with no statblock whose label is not the role stays a second entry, as "Blinder
  Greis", "Türwächter" and "Frau hinter der Sichtklappe" did. #7 is the only lever there, and it
  is a prompt: **whether it works is shown only by a live run.** Check scene: the pawn hall —
  Alter Fenk at the entrance, Bree Marlok behind the flap. Passed when neither comes back as a
  new entry and `state.json` holds one Bree Marlok and one Alter Fenk.
- The entries the run left behind ("Schreinschwester", "Frau hinter der Sichtklappe",
  "Türwächter", "Blinder Greis" in `state.debug.json`) are not cleaned up by this change.
