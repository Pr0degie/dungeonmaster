# ADR 065 — `SessionRuntime` split into mixins, not into separate objects

- **Status:** Accepted (built 2026-11-12; live-unverified — no behaviour change intended)
- **Date:** 2026-11-12
- **Refs:** decision row **D135** in `docs/decision-log.md`; plan `docs/plans/runtime-split.md`;
  ADR 029 (the runtime), ADR 035 (delivery extraction), lesson `byte-exact-moves-stepwise-gates`.

## Context

`dmbot/runtime.py` had grown to 1949 lines: a 303-line `__init__` and 74 methods covering scene
flow, panels, persistence and prompt context, session ingest, NPC memory, clocks and time, and
session seeding. Working on one of them meant loading all of them.

Three facts about the tests limit how it can be cut without editing them: about 26 call sites
invoke a method unbound with a stub as `self` (`SessionRuntime._ingest_one(stub, …)`); tests
replace methods on the instance (`rt._persist_and_refresh = recorder`) and expect every
internal call to see that; and `tests/fakes.py` patches names in the `dmbot.runtime` namespace
that `__init__` uses.

## Decision

Each concern moves into a module under `dmbot/session/` as a **mixin class**, and
`SessionRuntime` inherits from all of them. The mixins have no `__init__` and no state; `self`
is the runtime and all state stays in `SessionRuntime.__init__`. Method bodies move byte for
byte by a line-slice script. The cogs and the tests are not touched.

Result: seven modules — `ingest` (82 lines), `clocks` (99), `npcs` (132), `panels` (167),
`persistence` (161), `seeding` (158), `scenes` (477); 1097 lines moved in seven commits.
`runtime.py` went from 1949 to **844** lines. After each move: moved text byte-identical to
`HEAD`, kind/signature/source of all 75 class attributes identical to the base, 1365 tests
green with zero test edits, ruff (F) clean, `dm-eval` exit 0.

## Alternatives

- **Collaborator objects** (`rt.scenes.move(…)`, the shape ADR 035 used for the delivery
  pipeline). The only option that lowers coupling. Rejected for this round: every `self._x` in
  the moved code would be rewritten, the unbound-call tests break, and instance overrides stop
  reaching calls between collaborators — a redesign, not a move.
- **Free functions with one delegator per method.** Keeps the tests working, but leaves about
  60 hand-written pass-throughs in `runtime.py` (≈ 1000 lines instead of ≈ 800), each a place
  to drop a keyword argument. The glue is where refactor bugs live.

## Consequences

- Navigability improves; coupling does not. `SessionRuntime` is still one object with 95
  attributes, and a mixin reads attributes it does not define — look them up in
  `SessionRuntime.__init__`.
- Moved code logs under its module name (`session.ingest`, not `runtime`). Nothing in
  `logsetup.py`, `tools/` or the tests pins the old name.
- **The ADR 052 pin shapes the cut.** `test_testplan_is_only_reachable_from_the_runtime` allows
  only `runtime.py` to name the debug sidecar. The three methods outside `__init__` that do —
  `_session_ingest_source`, `update_debug_overlay`, `_panel_text` — therefore stay in
  `runtime.py` (63 lines), which is why the file ended at 844 lines instead of the planned
  ≤ 800. Moving them needs that allow-list extended by `ingest.py` and `panels.py` — Tobi's
  call, open at the end of the round.
- `history_store` stays imported in `runtime.py` even where unused, because `test_seed_session`
  reaches it as `runtime_mod.history_store`.

### For a later round: the attributes cogs rebind

The cogs reach 68 runtime privates (446 accesses at `87c5997`); a public interface was planned
and deferred. Most names are only read or called. These 21 are **rebound** by a cog, so any
interface has to make them writable:

| Attribute | Written in | How |
| --- | --- | --- |
| `_tts_enabled` | `voice/delivery.py` | assignment (synth failure → text-only) |
| `_turn_seq` | `voice/delivery.py` | `+= 1` per turn |
| `_turn_message` | `voice/dicecog.py` | assignment; `clear_panel("_turn_message")` |
| `_speech_mode` | `voice/dmcog.py` | assignment (`!sprechmodus`) |
| `_speech_punct` | `voice/dmcog.py` | assignment (`!sprechmodus`) |
| `_speech_prebuffer` | `voice/dmcog.py` | assignment (`!sprechmodus`) |
| `_scene_mode` | `voice/scenecog.py` | assignment (`!ortmodus`) |
| `_turn_time_advance` | `voice/scenecog.py` | assignment (`!automatik zeit`) |
| `_scene_router` | `voice/scenecog.py` | `setattr` through the `_SWITCHES` table (`!automatik`) |
| `_scene_flag_gate` | `voice/scenecog.py` | `setattr` through `_SWITCHES` |
| `_fact_router` | `voice/scenecog.py` | `setattr` through `_SWITCHES` |
| `_npc_router` | `voice/scenecog.py` | `setattr` through `_SWITCHES` |
| `_player_panel_enabled` | `voice/scenecog.py` | `setattr` through `_SWITCHES` |
| `_paused` | `voice/voicecog.py` | assignment (pause control, `!leave`) |
| `_pause_message` | `voice/voicecog.py` | assignment; `clear_panel("_pause_message")` |
| `_text_channel` | `voice/voicecog.py` | assignment (pause panel, `!leave`) |
| `_sink` | `voice/voicecog.py` | assignment (`!join`, `!leave`) |
| `_dm_listening` | `voice/voicecog.py` | assignment (`!join`, mic button, `!leave`) |
| `_mic_message` | `voice/voicecog.py` | assignment; `clear_panel("_mic_message")` |
| `_active_vc_id` | `voice/voicecog.py` | assignment (`!leave`) |
| `_clock_panel` | `voice/clockcog.py`, `voice/timecog.py` | only through `clear_panel("_clock_panel")` |

The six names that travel as strings (`_SWITCHES`, `clear_panel`) would pass a grep for
`_rt._`. Seven stub runtimes in six test files carry only the private names, so a cog-side
rename cannot be done with zero test edits.
