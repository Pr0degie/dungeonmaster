# Snapshot shared state at event time, not after the await

**Shared mutable state read after an `await` is this repo's recurring race class — capture
the value when the triggering event happens and pass it explicitly through the async chain;
on/off state that can nest is a refcount, never a boolean.**

## What happened

- Routing had to reflect the gate state *while the words were spoken*, not whenever the
  async transcript returned — `for_dm` is tagged when the utterance is cut and carried
  through the STT worker (ADR 011).
- A dice click during playback overwrote `_last_turn` before the turn's autosave read it →
  wrong pairs persisted; fix: autosave snapshots `user_msg` at generation end and passes it
  explicitly (ADR 018).
- Auto-recap `clear_history` popped everything *after* `summarize` awaited for seconds — a
  turn appended during the await vanished from both recap and history (ADR 030 #4).
- Layer-2 mute as a shared boolean unmuted VAD mid-playback on an operator resume →
  `_mute_depth` refcount (ADR 030 #8); the mute is taken once around the whole answer, not
  flapped per sentence (ADR 017).

## The correction

At every `await` boundary, ask: what does the code re-read afterwards, and can a concurrent
event (dice click, gate flip, new turn) have changed it meanwhile? Snapshot at the event and
thread the value as a parameter. Nesting on/off state → depth counter. Sibling tasks sharing
bounded queues need explicit cancellation in `finally` (ADR 030 #3/#7).

## Why it matters

These races only fire under live-table timing (a click *during* playback), which the suite
rarely reproduces — `docs/conventions.md` lists concurrency as a review trigger for exactly
this reason; this is the fix recipe reviewers should check against.
