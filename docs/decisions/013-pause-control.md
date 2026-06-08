# ADR 013 — Pause control: Esc (terminal) + ⏸ button (Discord), one shared freeze

- **Status:** Accepted
- **Date:** 2026-06-08
- **Refs:** decision log D27 in progress.md; architecture.md §3 (dependency: `rich`); builds on
  the layer-2 mute mechanism (ADR 003, `voice/recv.py mute()/unmute()`)

## Context
During play the table needs a way to **pause the game** — step out, settle a rule, take a break —
without the bot transcribing the room or the DM answering into the void. Tobi asked for two
controls: the **Esc key** in the DMbot terminal *and* a **Discord button**, each showing a clear
"paused" state (an animated box in the terminal, a status box in Discord). The pause must **freeze
everything** (his explicit choice over "keep transcribing, only hold the DM").

Constraints: the runtime is Windows (D16); a real keystroke has no natural docking point in a
voice/Discord-only bot; CLAUDE.md rule #9 requires justifying any new dependency. The pause *logic*
was already mostly present — `VadSink.mute()/unmute()` (feedback layer 2) freeze the VAD/STT
pipeline — so only DM-turn blocking and the two UIs were new.

## Decision
A single shared `_paused` flag in the cog, flipped by **both** the terminal **Esc key** (Variante A,
`msvcrt` polled in a non-blocking asyncio task) and a **Discord ⏸ button** (Variante C,
`discord_ui/pause.py`). Pause calls `sink.mute()` and DM-turn guards (`!dm`, `!redo`, the mic-release
auto-send, and the post-roll narration) short-circuit while paused; resume calls `sink.unmute()`.
Both surfaces re-render from the one flag: an animated **`rich`** `Live` spinner panel in the
terminal, and a colour-coded **embed** in Discord. New dependency: **`rich`** (pure-Python, light).

## Alternatives
- **Global OS hotkey** (Esc even when Discord has focus) — needs `keyboard`/Windows hooks, often
  admin rights, fragile and intrusive. Rejected.
- **Discord button only** (no Esc) — simplest, but Tobi wants the terminal key too (he sits at the
  DMbot console). Done as well, not instead.
- **"Hold the DM only", keep transcribing** — matches the "always record the table" principle
  (D24/D25). Rejected by Tobi for *this* control: pause should mean a real freeze. The full-record
  behaviour still exists when *not* paused.
- **No `rich`** (hand-rolled ANSI spinner) — avoids the dep but reinvents `Live`/`Panel`; `rich` is
  small and pure-Python, so the cost is low and the result much cleaner.

## Consequences
- One source of truth: Esc and the button can't disagree; `!vstatus` shows `paused=`.
- The animated box is **terminal-only** (Variante A); Discord shows a static embed — animation there
  would mean GIFs or rate-limited embed edits, deliberately avoided.
- `rich` enters the venv. Light and pure-Python, but it is a new dep (rule #9) — noted in
  architecture.md §3. The Esc listener is Windows-only (`msvcrt`); elsewhere it no-ops and the button
  still works, keeping the bot importable/testable cross-platform.
- This is the first half of the backlog "Edit/Review window before the DM speaks" — same
  human-in-the-loop freeze point; a future review step can hook the same `_paused` gate.
- Live-tested by Tobi (terminal Esc + Discord button + the freeze); unit tests cover the pure UI
  (embed states, button label/style). The cog wiring is not unit-tested (heavy `__init__`).
