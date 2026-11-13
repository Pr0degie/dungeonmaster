# Snapshot shared state at event time, not after the await

**Shared mutable state read after an `await` is this repo's recurring race class — capture
the value when the triggering event happens and pass it explicitly through the async chain;
on/off state that can nest is a refcount, never a boolean.**

## What happened

- Routing had to reflect the gate state *while the words were spoken*, not whenever the
  async transcript returned — `for_dm` is tagged when the utterance is cut and carried
  through the STT worker (ADR 011).
- A dice click during playback overwrote the last turn (`ChannelSession.last_turn`) before the turn's autosave read it →
  wrong pairs persisted; fix: autosave snapshots `user_msg` at generation end and passes it
  explicitly (ADR 018).
- Auto-recap `clear_history` popped everything *after* `summarize` awaited for seconds — a
  turn appended during the await vanished from both recap and history (ADR 030 #4).
- Its fix — a head *count* of the summarized messages — broke again on every other mutation
  during the await (cap trim, `!redo`, a concurrent `!wrap up`), and `!redo` recognising its pair
  by *text* hit two identical player lines (review 2026-11-13). Fix: `summarize` keeps the
  message objects it folded in, `last_turn` a reference to its stored pair, and the turn answer
  carries its own player line to the autosave.
- The opposite mistake: `close_turn` filed NPC sightings under its pointer snapshot. The snapshot
  was right for the scene verdict (built against the old scene's exits) and wrong for the
  people of an arrival narration, who belong where the group ends up. And one live case was no
  race inside the `await` at all: the `<<ORT>>` button came 22 s after the function had
  returned, which none of the three reproduction tests covered (ADR 062, amendment 2026-11-13).
- Layer-2 mute as a shared boolean unmuted VAD mid-playback on an operator resume →
  `_mute_depth` refcount (ADR 030 #8); the mute is taken once around the whole answer, not
  flapped per sentence (ADR 017).

## The correction

At every `await` boundary, ask: what does the code re-read afterwards, and can a concurrent
event (dice click, gate flip, new turn) have changed it meanwhile? Snapshot at the event and
thread the value as a parameter. An index, count or text match into a list that others mutate is shared state too — mark the element by object identity. Nesting on/off state → depth counter. Sibling tasks sharing
bounded queues need explicit cancellation in `finally` (ADR 030 #3/#7).

A snapshot is not automatically the right value. Ask per result which moment it belongs to:
what a decision was *computed against* is the snapshot; where its result is *filed* can be the
state after the await, or after an event that arrives once the function is done. And check
each live case's timestamps against the reproduction tests before calling the fix complete.

## Why it matters

These races only fire under live-table timing (a click *during* playback), which the suite
rarely reproduces — `docs/conventions.md` lists concurrency as a review trigger for exactly
this reason; this is the fix recipe reviewers should check against.
