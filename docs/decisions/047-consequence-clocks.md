# ADR 047 — Consequence clocks: code-owned progress clocks, `<<UHR>>` marker, visible panel

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D94** in progress.md. Follows the **ADR 043** pattern exactly
  (code-owned flags, marker with confirm button, stateful render); bound by **ADR 015**
  (memory state split) and **golden rule #3** (world state is advanced by code, never by LLM
  free text). Marker seams mirror **ADR 026/043**; replay-journal extensions follow **ADR 046**;
  cog placement follows **ADR 039**. Touches `dmbot/memory/state.py`, `dmbot/rules/marker.py`,
  `dmbot/llm/stream_assembler.py`, `dmbot/orchestrator.py`, `dmbot/voice/delivery.py`, new
  `dmbot/voice/clockcog.py`, new `dmbot/discord_ui/clock.py`, `dmbot/runtime.py`,
  `dmbot/tools/eval_replay.py`, `prompts/dm_core_de.md`, `dmbot/__main__.py`.

## Context

The world has no pressure: nothing moves unless the party pokes it. Blades-in-the-Dark-style
progress clocks („Arbites-Ermittlung 3/6") give consequences a visible fuse — but if the LLM
owned them they would drift, double-tick, or be forgotten (the exact failure golden rule #3
exists for). The scene-flag machinery (ADR 043) already solved this shape once: the model
*requests*, code validates and applies, a Discord confirm button keeps a 12B model's misfires
harmless. Clocks follow that groove instead of inventing a new one.

## Decision

1. **LLM proposes, code disposes.** A new marker `<<UHR <id>>>` (grammar + glue tolerance
   identical to `<<ERLEDIGT>>`) *requests* one tick on a clock. Code validates the id against
   `WorldState.clocks` and applies the tick — the model never writes clock state. An unknown
   id is dropped + logged, never guessed.
2. **Hard clamp: max +1 tick per clock per turn** on the marker path — duplicate `<<UHR x>>`
   requests within one turn are rejected like duplicate flags (pure `uhr_verdict`, shared with
   dm-eval). The manual `!uhr tick` is not clamped: the human at the table IS the authority.
3. **Schema:** `WorldState.clocks: list[Clock]` with `Clock{id, name, size (4|6|8), filled,
   visible: bool = True}`. Omit-when-empty, backward compatible (an old `state.json` without
   `clocks` loads unchanged), roundtrip like `scene_flags`. `filled` clamps to `0..size`.
4. **Visible-to-all is the deliberate first cut.** Clocks render in a Discord panel (name +
   ◉◉◉○○○ segments, edit-in-place like the pause panel, no spam) and in the system prompt.
   The `visible` field already exists in the schema for hidden GM clocks — the UI **ignores it
   for now**; hidden clocks are the documented follow-up option, not scope creep today.
5. **Humans create clocks, never the LLM.** `!uhr neu "<Name>" <4|6|8>` / `!uhr tick` /
   `!uhr zurück` / `!uhr weg` / `!uhren`, in a new thin **ClockCog** (ADR-039 style).
   Weighed against attaching to SceneCog (clocks are not adventure-scoped — they live in the
   WorldState and work without any adventure loaded) and DiceCog (no dice involved): a
   separate ~100-line sub-cog keeps both existing cogs lean and the feature loadable alone.
   Adventure-schema clock definitions (loader) are out of scope — a scope boundary, revisit
   when an authored adventure actually wants pre-defined clocks.
6. **Confirm mechanics identical to `<<ERLEDIGT>>`.** A valid tick request posts a
   `ClockView` confirm button (mirror of `FlagView`); the existing `DM_FLAG_CONFIRM` knob
   governs both flows (=0 auto-applies). One knob, one mental model — ticks are the same
   low-stakes, code-validated, idempotent-per-turn shape as element flags.
7. **`<<UHR>>` is exempt from the results-only marker suppression.** `<<TEST>>`/`<<ORT>>`/
   `<<ERLEDIGT>>` are suppressed on results-only (post-roll consequence) turns to break
   request loops. But the consequence narration after a **failed roll is the canonical tick
   moment** — suppressing UHR there would kill the feature's primary use case. A tick never
   triggers a new roll/turn, so there is no loop to guard against. Documented divergence.
8. **Full clock = injected consequence.** When a tick fills a clock, code queues a one-shot
   GM note; the next DM turn's user message carries a `[Regie]`-prefixed line („Die Uhr ‚X'
   ist voll — die Konsequenz tritt jetzt ein"). The full clock stays visible (rendered VOLL
   in panel + prompt) until `!uhr weg` — the GM decides when the consequence is spent.
   `!uhr zurück` from full discards a still-queued note (an accidental fill must not fire).
9. **Replay journal (ADR 046) extended compatibly:** the markers dict gains `"uhr"`, turn
   records gain `"notes"` (the drained GM notes — dm-eval re-feeds them so the composed
   user_msg matches), and the pipeline notes `"uhr_verdicts"`. Old goldens keep replaying
   (missing keys default empty); dm-eval re-runs `uhr_verdict` against `state_before`.

## Alternatives

- **LLM writes clock state (free text / tool call):** rejected — golden rule #3, same as ADR 043.
- **LLM creates clocks (`<<UHR NEU …>>`):** rejected — clock creation frames the fiction
  (what pressure exists, how long the fuse is); that is GM-table authority, and a marker that
  can mint state objects is a much bigger misfire surface than one that ticks existing ones.
- **A separate `DM_UHR_CONFIRM` knob:** rejected for now — the confirm semantics are identical
  to flags; two knobs for one behaviour class invites config drift. Split later if the table
  ever wants flags auto but ticks confirmed.
- **Keeping UHR under the results-only suppression (strict marker parity):** rejected — the
  post-roll consequence turn is where ticks belong (fail → the world advances); parity would
  make the feature fire mainly in the wrong turns.
- **Hidden clocks in the UI now:** rejected — visibility is the point of the first cut
  (players see pressure mounting); the schema field keeps the door open without UI work.
- **Chained/linked clocks (one fills → another starts):** rejected — no play evidence yet
  that the bookkeeping earns its complexity. Scope boundary.

## Consequences

- **+** The world gains visible, deterministic pressure the model can lean on but not corrupt;
  players watch the fuse burn (panel), the DM is reminded every prompt (state block).
- **+** Full-clock consequences are *injected*, not hoped for — the model gets an explicit
  directive line, the same mechanism dice results already use.
- **−** One more marker in the persona (prompt bytes) and one more pending-queue in the
  brain (redo/reset/consistency-snapshot seams all gained a line — mechanical but wide).
- **−** `finalize_answer` returns a 6-tuple now; every unpack site changed in one sweep.
- **−** The `"uhr"`/`"notes"` journal fields mean goldens recorded from today on can't be
  replayed by yesterday's code (forward-compat only — same as every ADR-046 extension).
- **Bound for later work:** hidden clocks (UI honours `visible=False`), adventure-authored
  clock definitions, chained clocks — all explicitly deferred, schema-ready where cheap.

## Addendum — detail preserved from decision log D94 (2026-07-11)

- Seam detail: `<<UHR>>` mirrors `<<ERLEDIGT>>` also at strip-before-TTS, streaming
  withholding of partial markers, the per-channel pending queue, and the delivery drain
  (added as a fourth proposal task in the delivery paths).
- Prompt surface: a `Uhren:` line in the state summary plus a persona bullet (when to tick,
  marker syntax).
- Replay compatibility verified in the round: old goldens replayed green (`dm-eval` exit 0)
  after the journal extension.
- Test evidence from the round: suite **573 green** (+38: schema/slug/GM-notes, marker,
  delivery/clamp/panel, commands).
- Live gate (open at the time of writing): create a clock, provoke the DM into a tick, watch
  the panel update — see the live-test checklist.
