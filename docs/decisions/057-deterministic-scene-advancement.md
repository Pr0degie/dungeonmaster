# ADR 057 — Scene advancement belongs to code, not to an inline marker

- **Status:** Accepted (specified; the build and the next debug run are the verification)
- **Date:** 2026-08-23
- **Refs:** supersedes the *primary* mechanism of **ADR 019/026** (the `<<ORT>>` scene pointer),
  which stays as a fallback; applies the classifier pattern of **ADR 014** / `roll_router`;
  unblocks **ADR 043** (opportunity flags), **ADR 047/048** (clocks, in-game time),
  **ADR 049** (NPC agendas), **ADR 050** (Chekhov threads) and **ADR 052** (debug overlay),
  all of which are downstream of a scene change. Lesson:
  `docs/lessons/mandatory-decisions-need-a-separate-classifier.md`.
  Plan: `docs/plans/coherent-campaign-run.md`.

## Context

The debug campaign was played live on 2026-08-22 with four players. In 22 turns the scene
pointer never moved once. The group left the starting room twice and said so explicitly; the DM
narrated a harbour while the world state stayed in the customs sacristy, and an NPC who had
walked out in turn 4 was leading the group through that same sacristy in turn 21.

The scene pointer has exactly three movers: the operator typing `!ort <id>`, an inline `<<ORT
id>>` marker from the model, and the confirmation button that marker raises. Nobody at the table
knew the command existed — it appears in no join message and in no test hint. So in practice the
model was the only mover, and it emitted zero markers in 22 turns.

That is not bad luck. The marker is specified to sit at the end of the answer, which is precisely
where the 220-token ceiling truncates and where the stop-label cut fires. Two independent
analyses reached this from opposite directions. The scene card compounds it: the starting scene's
only concrete destination in its own prose is the pawn hall, which is two edges away, while the
one reachable neighbour — the shrine — is never mentioned in the fiction. Had the model emitted
the marker the fiction suggested, the resolver would have discarded it silently. And "silently"
is literal: a rejected move produces one log line, nothing that reaches the table or the model.

The cost is not one missing feature. The test overlay, the in-game clock, the deadlines, the NPC
agendas, the recap, the NPC memory, the Chekhov threads, five of six scenes and seven of eight
NPCs all hang downstream of a scene change. One dead link disabled the evening.

`docs/lessons/mandatory-decisions-need-a-separate-classifier.md` already states the rule this
violates: inline markers are fine for optional proposals and fail model-size-independently for
mandatory decisions. Scene advancement was classified as optional ("nice when it fires, free when
it doesn't"). In a six-scene campaign it is mandatory.

## Decision

1. **A dedicated post-turn classifier decides movement.** After each turn, a stateless
   constrained-JSON call — the shape that demonstrably works for the roll router — answers one
   question: did the group actually enter one of these places? Its answer space is exactly the
   current scene's reachable exits plus "no". The inline `<<ORT>>` marker is demoted to an
   opportunistic fallback; it is still honoured when it appears.
2. **A flag gate is the second, model-free trigger.** When every opportunity of the current scene
   is resolved, code advances the scene with no LLM involvement at all.
3. **Opportunity ids become mandatory campaign data, enforced at load.** The flag gate needs
   something to count, and today exactly one of the campaign's seventeen opportunities carries an
   id. An opportunity without an id is a load-time content error, so this cannot half-work
   silently the way the marker did.
4. **Advancement is automatic, with a one-minute undo.** The scene changes immediately, the
   channel announces it, and an undo control restores the previous pointer, scene time and
   overlay state for about a minute. No pre-confirmation: the evening proved that a control
   nobody knows about is the same as no control.
5. **A rejected move is loud.** An unreachable or unknown target produces a director note for the
   next turn naming the reachable exits, plus an operator-visible line — never a log-only path.
6. **Exits render with their titles.** The scene block names each exit as `id — title` instead of
   a bare id, so a fictional direction can be mapped onto a real destination.

## Alternatives

- **Keep the inline marker and just prompt harder:** rejected. The persona already asks for it,
  the model already ignores it, and the marker sits where truncation destroys it. This is the
  exact shape the lesson file was written about.
- **Move the marker to the start of the answer:** rejected. It survives truncation but forces the
  model to decide movement before narrating it, and it leaks marker syntax into the first spoken
  words if sanitising ever misses.
- **Keep human confirmation (propose + button):** rejected as the default. It is what existed on
  2026-08-22 and it never fired, because the mechanism assumed an operator watching for a
  control that was never announced. Undo-after is strictly better than confirm-before when the
  failure is *inaction*.
- **Flag gate only, no classifier:** rejected. It advances a scene that has been played out, but
  a group that simply walks away without exhausting a room is not followed — which is exactly
  what happened twice.
- **Add a stall detector that pushes the group after N quiet turns:** deferred, not rejected. It
  addresses a different failure (sticking) than the one observed (walking away unnoticed), and
  three overlapping movers would make a misfire hard to attribute on the first run.
- **Let the classifier write the pointer without any undo:** rejected. A misclassification would
  tear the table out of a conversation with no recovery.

## Consequences

- **+** The campaign can be played through. Overlay, clock, deadlines, agendas, recap, NPC memory
  and Chekhov threads all get their trigger back, none of which have ever run in a live session.
- **+** The decision that must be right is made by a call type with a live track record, and the
  decision that can be made without a model is not given to one.
- **+** An invalid move now teaches both the model and the operator instead of vanishing.
- **−** One additional short LLM call per turn. It runs on the same turn boundary as the fact
  classifier (ADR 058), so the two share one latency window.
- **−** Every campaign must now carry opportunity ids; the existing debug campaign needs a content
  pass over seventeen entries, and `chemical_burn` will need one before it is played.
- **−** Three mechanisms can now move the pointer (classifier, flag gate, fallback marker). Their
  interaction is the first thing to watch on the next run; each is individually switchable.
- **−** A wrong automatic change is felt at the table before it can be undone. Accepted: the
  observed failure was never moving at all.
