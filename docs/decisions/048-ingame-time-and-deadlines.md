# ADR 048 — In-game time: minutes counter, `<<ZEIT>>` marker, deadlines with day phases

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D95** in progress.md. Follows the **ADR 043/047** pattern
  (LLM proposes via marker, code validates + applies, confirm button under `DM_FLAG_CONFIRM`);
  bound by **ADR 015** (memory state split) and **golden rule #3** (world state is advanced by
  code, never by LLM free text). Marker seams mirror **ADR 026/043/047**; replay-journal
  extensions follow **ADR 046**; cog placement follows **ADR 039**; the expired-deadline
  injection reuses the **ADR 047** GM-note mechanism. Touches `dmbot/memory/state.py`, new
  `dmbot/memory/gametime.py`, `dmbot/rules/marker.py`, `dmbot/llm/stream_assembler.py`,
  `dmbot/orchestrator.py`, `dmbot/voice/delivery.py`, new `dmbot/voice/timecog.py`, new
  `dmbot/discord_ui/zeit.py`, `dmbot/runtime.py`, `dmbot/config.py`,
  `dmbot/tools/eval_replay.py`, `prompts/dm_core_de.md`, `dmbot/__main__.py`.

## Context

`WorldState.time_ingame` exists as a free-text string and does nothing: no caller ever sets
it (`set_time` is dead code), the prompt line is empty in practice, and the DM has no notion
of "the train leaves in a day" or "it's the middle of the night". Time is the cheapest source
of pressure a GM has — deadlines, closed shops at night, consequences that arrive on schedule
— but only if it is a *number the code owns*, not prose the model may or may not keep straight.
If the LLM owned the clock it would drift, jump backwards, or skip days mid-scene (the exact
failure golden rule #3 exists for). Clocks (ADR 047) solved this shape for progress meters;
time follows the same groove.

## Decision

1. **Internal model: one minutes counter.** `WorldState.time_minutes: int` = minutes since
   campaign start, where minute 0 is **day 1, 00:00**. Everything else is derived rendering:
   day = `time_minutes // 1440 + 1`, clock = `HH:MM` of the remainder. A single int is
   trivially clampable, comparable against deadlines, and serialises without a calendar.
   The default (fresh state) is **480 = day 1, 08:00** — campaigns start in the morning.
2. **`time_ingame` (string) survives as the rendered, human-readable mirror.** Whenever code
   advances the counter it re-renders `time_ingame` ("Tag 2, 14:30") so a hand-opened
   `state.json` stays legible and old tooling keeps seeing a string. It is never parsed back.
   **Migration:** a `state.json` without `time_minutes` starts the counter at 480 (day 1,
   08:00) and logs it — including when a legacy free-text `time_ingame` is present (we do not
   attempt to parse prose; the old string is overwritten on the first advance). `set_time`
   (the dead free-text setter) is removed.
3. **Day phases derived from the hour**, code-owned boundaries: **Morgen** 05:00–10:59,
   **Tag** 11:00–16:59, **Abend** 17:00–21:59, **Nacht** 22:00–04:59. Rendered next to the
   time everywhere ("Tag 2, 23:10 — Nacht") so the DM can play it (no innkeeper at night).
   The persona gets the phase as *narrative colour + plausibility*, not hard availability
   logic (that would be the NPC-agenda round — scope boundary).
4. **LLM proposes time advance via `<<ZEIT +30m>>` / `<<ZEIT +4h>>`** (grammar + glue
   tolerance like the other markers; units tolerant: `m|min|minuten`, `h|std|stunden`;
   ASCII `+` optional). Code validates and applies — the model never writes the counter.
   **Only the first valid marker per turn is honoured** (ORT precedent, ≤1 move per turn):
   time advance is *not* idempotent, so processing duplicates would double-advance — the
   opposite call from flags/ticks (ADR 043/047), where all valid markers apply because they
   are idempotent. **Hard clamp: max +12h (720 min) per marker turn** — a larger proposal is
   clamped to 720 and logged, not rejected (the model's *intent* "much later" is preserved;
   the magnitude is the code's call). Zero/negative/unparseable proposals are rejected +
   logged: time never runs backwards on the marker path; corrections are command territory.
5. **Confirm mechanics identical to `<<ERLEDIGT>>`/`<<UHR>>`** (ADR 043/047): a valid
   proposal posts a `ZeitView` confirm button; the existing **`DM_FLAG_CONFIRM`** knob
   governs it (=0 auto-applies). Same argument as ADR 047: one knob, one mental model for
   the whole low-stakes marker-confirm class.
6. **`<<ZEIT>>` is exempt from the results-only marker suppression** (the UHR precedent,
   ADR 047 #7): the consequence narration after a roll is a canonical time-advance moment
   ("die Reparatur kostet euch zwei Stunden"), and a time advance can never trigger a new
   roll/turn — no loop to guard against.
7. **Deadlines:** `WorldState.deadlines: list[Deadline]` with `Deadline{id, label,
   due_minutes, notified: bool = False}` — `due_minutes` on the same absolute axis as the
   counter. Created/removed **by humans only** (`!frist neu "<Label>" <+Dauer>` /
   `!frist weg <id>` / `!fristen`) — same authority argument as clock creation (ADR 047 #5):
   what pressure exists is GM-table framing, not model output. Ids are slugified from the
   label (the clock-id machinery, marker-safe as a habit even though no marker takes them).
   Open deadlines render in the prompt with **coarse remaining time** ("noch ~2 Std",
   "noch ~1 Tag") — coarse on purpose, the DM should speak in fiction units, not minutes.
8. **Expiry fires exactly once, via the ADR-047 GM note.** The single time mutator scans
   deadlines after every advance; a deadline crossing `due_minutes` queues the one-shot
   `[Regie]` line („Die Frist ‚X' ist verstrichen — spiele die Konsequenz jetzt ein") and
   sets `notified=True` so it can never re-fire (persisted — a restart doesn't re-notify).
   The expired deadline stays visible as **ABGELAUFEN** until `!frist weg` — the ADR-047
   full-clock semantics: the GM decides when the consequence is spent.
9. **Commands in a new thin `TimeCog`** (ADR-039 style): `!zeit` (show), `!zeit +6h`
   (advance, unclamped — the human IS the authority, like `!uhr tick`), `!zeit tag` (jump
   to the next morning 08:00), `!frist …`. Weighed against putting them on ClockCog: clocks
   and time are both pressure, but distinct state with distinct commands — two ~120-line
   cogs stay individually loadable (the D81 goal) instead of one mixed 250-line cog.
10. **Default advance on scene change: +30 min**, applied inside the single scene-move
    mutator (`runtime._set_scene`) — so `!ort` and the confirmed `<<ORT>>` both get it —
    but **only on a real move** (old pointer non-empty and different): the initial
    `start_scene` seed on `!join`/`!start` must not advance the clock. Rationale for 30:
    a scene change in play is travel/regrouping on the order of half an hour; big jumps
    (overnight, a journey) are narrative beats the marker or `!zeit` should carry
    explicitly. Env-tunable: **`DM_SCENE_TIME_ADVANCE`** (minutes, default 30, 0 = off).
11. **Display: the clock panel becomes the time panel too.** The existing edit-in-place
    clock panel (ADR 047) gains a header line (current time + day phase) and a deadline
    section (next the clocks), and shows whenever clocks **or** deadlines exist — no new
    panel, no scene-card change (the ADR-043 scene card is a *prompt* artefact, not a
    Discord panel; the clock panel is the pressure display and time is pressure).
12. **Replay journal (ADR 046) extended compatibly:** the markers dict gains `"zeit"`
    (recorded even under suppression, like `uhr`), the pipeline notes `"zeit_verdicts"`,
    and dm-eval re-runs the pure `zeit_verdict` against `state_before`. Old goldens keep
    replaying (missing keys default empty).

## Alternatives

- **LLM writes the time as free text (status quo `time_ingame`):** rejected — golden rule #3;
  it is also exactly what the dead field already proved doesn't happen by itself.
- **Absolute-time markers (`<<ZEIT 14:30>>` / "next morning"):** rejected — absolute forms
  need a parser over fuzzy prose and can move time *backwards* on a model slip. Durations
  are one token pair, always forward, trivially clampable. `!zeit tag` covers the one
  common absolute jump (next morning) as a human command.
- **Rejecting (not clamping) an oversized proposal:** rejected — a 24h proposal on a rest
  scene is *directionally right*; dropping it entirely loses signal a clamp preserves.
  (Zero/negative stays rejected: there is no salvageable intent.)
- **Processing all `<<ZEIT>>` markers in a turn (flag/tick parity):** rejected — advances
  are not idempotent; duplicates double-advance. First-only is the ORT rule, and the clamp
  then genuinely means "max 12h per turn".
- **A real calendar (imperial dating, months, weekdays):** rejected for this round — no
  play evidence it earns its complexity; "Tag N" carries every current use case (deadlines,
  phases). A follow-up could render the counter through a per-system calendar profile.
  Scope boundary, explicitly deferred.
- **Hard NPC availability from the day phase (shop closed = code-rejected):** rejected —
  that is the NPC-agenda round; today the phase rides in the prompt as narrative guidance.
- **`Deadline` as a special clock (reuse `Clock`):** rejected — clocks fill by discrete
  *events* (ticks), deadlines by the *passage of time*; conflating them would give deadlines
  a fake segment count and clocks a fake due-time. They share the panel instead.
- **A separate confirm knob (`DM_ZEIT_CONFIRM`):** rejected — ADR 047's one-knob argument
  holds; split only if the table ever wants the flows to differ.

## Consequences

- **+** Time becomes a tool: the DM sees "Tag 2, 23:10 — Nacht" + "Der Zug nach Hive
  Sibellus: noch ~1 Tag" every prompt, players see the same pressure on the panel, and an
  expired deadline *injects* its consequence instead of hoping the model remembers.
- **+** `time_ingame` finally has one writer (code) and stays human-readable in state.json.
- **−** One more marker in the persona (prompt bytes), one more pending queue in the brain
  (redo/reset/consistency-snapshot seams each gain a line — mechanical but wide), and
  `finalize_answer` grows to a 7-tuple (every unpack site changes in one sweep, again).
- **−** The `"zeit"` journal field means goldens recorded from today can't be replayed by
  yesterday's code (forward-compat only — same as every ADR-046 extension).
- **−** Day-phase boundaries are hardcoded (not profile data); a system on a non-24h world
  would need them profile-driven — accepted until a second system actually wants it.
- **Bound for later work:** calendar/imperial dating rendering, NPC agendas / hard
  availability from the phase, travel-time tables — all explicitly deferred.

## Addendum — detail preserved from decision log D95 (2026-07-11)

- Live gate for this round: set a deadline, let it lapse, watch the DM play the consequence.
- Replay compatibility verified in the round: old goldens replayed green after the journal
  extension.
- Test evidence from the round: suite **635 green** (+62 new tests).
