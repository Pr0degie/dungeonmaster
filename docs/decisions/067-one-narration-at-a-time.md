# ADR 067 — One narration at a time

- **Status:** Accepted (built 2026-11-27, live-unverified — check item F11)
- **Date:** 2026-11-27
- **Refs:** decision log D152 (docs/decision-log.md); ADR 017 (streaming pipeline), D40 (dice
  button during playback), ADR 063 (Fate), `architecture.md` §9 (timing note)

## Context

Nothing serialised DM turns. A turn starts on a mic release, on a finished roll, on a typed
command, on the backend's return — and each start ran its own narration call and its own
sentence-by-sentence delivery. The bridge plays WAVs in arrival order. The run of 2026-11-27
(three players, Claude) showed three faces of that:

- 16:17:06 — two push-to-talk windows a second apart: two narration calls side by side, the second
  describing the same moment again, both spoken into each other.
- 16:11:06 — a roll narration generated while the previous answer still played (wanted since
  D40): its first sentence was spoken in the middle of that answer.
- 16:22:19 / 16:22:21 — two players with a test each in one turn: every finished roll started its
  own narration, and the two contradicted each other. Tobi at the table: wait for both results,
  then narrate once.

## Decision

Three separate guards: one narration call at a time, every answer spoken whole in the order it
was generated, and one narration for all rolls of a turn.

1. **Narration lock** (`DeliveryPipeline._narration`): held around the LLM call of every
   delivery path. A second trigger waits, then answers with the first answer in its history.
2. **Speaking order** (`_SpeakingOrder`): an answer takes its place when its generation starts and
   speaks only after the answer before it has finished. Generation of the next answer still runs
   while the previous one plays.
3. **Roll batch** (`OpenRolls`, `DiceCog._narrate_rolls`): the dice buttons of one answer are a
   batch; a finished roll is narrated when no other button of the batch is open, at the latest
   after `DM_ROLL_BATCH_WAIT_SECONDS` (30; 0 = every roll on its own).

## Alternatives

- **One lock over the whole turn, playback included.** Simplest, and it would also order speech.
  Rejected: it gives up D40's head start — a roll narration could only start generating after the
  previous answer's last word, eight to ten silent seconds after every roll.
- **Merge the second trigger into the running call**, or cancel and restart the first. A call in
  flight cannot take a new line, and restarting throws away Opus tokens for an answer whose
  first sentences are already being spoken. Rejected; the second answer follows the first.
- **Rolls: wait without a limit** until every button is pressed. A button nobody presses would
  silence the DM until someone speaks. **Narrate each roll on its own** is the old behaviour and
  the finding. The bounded wait is the middle; its length is a setting.
- **A list of open buttons instead of a count.** Exact, but the token would have to travel
  through every roll, Fate and damage callback. The count's known inexactness — a stale button
  pressed late ends the wait one roll early — loses no result.

## Consequences

- `[latency]` shows the two waits as `queued=` and `spoke_after=`; `⏱ LLM` stays the pure
  generation time. `first_audio` of a queued turn includes the previous answer's playback.
- A hit whose target picker nobody uses keeps its roll open: the turn's other roll is narrated
  only when the wait runs out.
- Speech outside the narration answers (`!say`, `!intro test`, backend notices, lore read-aloud)
  does not take a place in the speaking order and can still be spoken into an answer.
- Any new path that calls the narration model takes `DeliveryPipeline.narrating()`; any new path
  that speaks an answer goes through the speaking order
  (lesson `answers-interleave-without-a-speaking-order`).
