# ADR 003 — Conversational control, registration & turn-taking

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** decision log D10 & D13 in `progress.md`; `architecture.md` §6

## Context

A voice DM with 2–5 players cannot tell on its own whether it is being addressed or
whether the players are just talking among themselves. If it reacts to every utterance it
talks over people, processes table talk as game action, and provokes feedback. It also
needs to know which Discord user plays which character, in order to address someone and to
use the right stats on a roll.

## Decision

- **When the DM speaks:** Bot B transcribes continuously (with the user-ID filter) and
  buffers utterances per player, but **only generates an answer on a button press**
  ("End turn" / "DM, respond"). VAD serves **only for segmentation**, not as a trigger.
- **Registration:** guided and sequential — the bot walks through the loaded characters
  ("Who plays Brother Castor? Press the button"), each click maps a user-ID to a character,
  until all are assigned. The mapping goes into the session JSON.
- **Turn-taking:** in the MVP only a lightweight turn indicator, advanced manually.

## Alternatives

- **React to every utterance:** chaotic, feedback-prone, no table talk possible.
- **Wake word from the start:** more natural UX, but an extra unreliable building block
  (false triggers, German recognition) before the first playable loop.
- **Full combat initiative in the MVP:** builds combat rules before a free scene even runs.

## Consequences

- **Positive:** robust, semi-turn-based flow without talking over each other; table talk
  stays out; clearly defined DM turn; simple to build.
- **Binding:** the orchestrator needs a per-player utterance buffer and a button layer
  (`discord_ui/`). Registration assumes characters exist as JSON (ADR 004).
- **Later goal (Part 2):** a wake word ("Magos, …") triggers the DM turn instead of the
  button. The button is the robust path there.
- **Combat initiative** (rolled order, rounds) is a separate later mode.
