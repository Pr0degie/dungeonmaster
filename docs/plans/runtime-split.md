# Plan — split `dmbot/runtime.py` into session modules, no behaviour change

**Status:** approved by Tobi 2026-11-12 with changes — this round is the **seven move commits
only**. The cog interface is deferred (see *Deferred*).
**Date:** 2026-11-12 · **Base commit:** `87c5997` (all line numbers below refer to it)
**Governing:** ADR 029 (runtime + cogs), ADR 035 (delivery extraction — the precedent),
ADR 046 (`dm-eval` as the refactor gate), lessons `byte-exact-moves-stepwise-gates` and
`complete-fakes-not-production-guards`.
**New ADR from this round:** 065 (mixins instead of separate objects; the 21 attributes cogs
rebind, listed for a later round).

## Goal

`SessionRuntime` (1949 lines, a 303-line `__init__` plus 74 methods) mixes seven concerns. Move
each into its own module without changing behaviour. The cogs keep reaching the private names
exactly as today.

**Done when:** `runtime.py` is **≤ 800 lines** (expected ≈ 780), the suite is green, ruff (F) is
clean, and the byte check passed for every move.

## What constrains the cut

| Fact | Value |
| --- | --- |
| `runtime.py` | 1949 lines: 141 header, 303 `__init__` (95 attributes), 1505 methods |
| Baseline (step 0, measured) | 1365 tests green in 29 s, `dm-eval` exit 0, ruff (F) clean |

Three things in the tests decide the shape:

1. **Unbound calls with a stub `self`** — `SessionRuntime._session_ingest_source(stub, 42)`,
   `SessionRuntime.speech_transform(SimpleNamespace(...))`, `SessionRuntime.update_debug_overlay(rt)`
   (≈ 26 call sites in `test_session_ingest`, `test_speech_mode`, `test_debug_overlay`,
   `test_dice_animation`). Every method must stay reachable as `SessionRuntime.<name>` and must
   reach its siblings through `self`.
2. **Instance overrides** — `rt._persist_and_refresh = recorder`, `make_runtime(_brain_channel=...)`.
   Every internal call has to keep going through the instance.
3. **Patches on the module namespace `dmbot.runtime`** — `tests/fakes.py` patches seven names
   that only `__init__` uses, plus `SessionRuntime._load_characters`; two files patch
   `dmbot.runtime._DATA_DIR`; `test_seed_session` reaches `runtime_mod.history_store`. So
   `__init__`, `_load_characters` and `session_file` stay in `runtime.py`, and an import a test
   reaches through this module stays as a re-export.

## Shape (decided)

New package `dmbot/session/`, one module per concern, each holding one mixin class with the
moved methods. `SessionRuntime` inherits from them:

```python
class SessionRuntime(SceneFlowMixin, PanelsMixin, PersistenceMixin, SessionIngestMixin,
                     NpcMemoryMixin, ClocksMixin, SeedingMixin):
```

The mixins have no `__init__` and no state; all state stays in `SessionRuntime.__init__`. The
method bodies move byte for byte, same indentation, comments and section headers included.
Because `self` is still the runtime, the three constraints hold by construction and the round
needs **zero test edits**. Why mixins and not delegators or collaborator objects: ADR 065.

Moved code logs under its new module name (`session.scenes` instead of `runtime` in the console
and `debug.log`), as `voice/delivery.py` does since ADR 035. Checked before the first move:
`logsetup.py` filters on the prefix `dmbot` only, and nothing in `tools/`, `dmbot/tools/` or the
tests pins the name `dmbot.runtime`. This is the one visible difference.

## Target modules and method assignment

| # | Module (class) | Methods | Lines at base |
| --- | --- | --- | --- |
| 1 | `session/ingest.py` (`SessionIngestMixin`) — campaign memory, ADR 054 | `schedule_session_ingest` `schedule_session_catchup` `_ingest_one` `_spawn_session_ingest` `_spawn_session_task` | 991–1048 |
| 2 | `session/clocks.py` (`ClocksMixin`) — clocks + in-game time, ADR 047/048 | `clocks_enabled` `_tick_clock` `_untick_clock` · `_advance_time` `advance_scene_time` `advance_turn_time` | 1069–1108, 1302–1339 |
| 3 | `session/npcs.py` (`NpcMemoryMixin`) — ADR 044 | `_scene_npcs` `schedule_npc_memory_extraction` `extract_npc_memories` | 1691–1799 |
| 4 | `session/panels.py` (`PanelsMixin`) — player panel, 🧪 overlay, clock panel | `update_clock_panel` `_sweep_pressure_panels` · `_operator_channel` `_debug_overlay_channel` · `update_player_panel` `_adopt_old_panel` · constants `PANEL_MARK` `PANEL_SWEEP_LIMIT` | 96–98, 1109–1192, 1245–1301 |
| 5 | `session/persistence.py` (`PersistenceMixin`) — world state + prompt context | `chekhov_list` `save_chekhov` `_load_or_seed_state` `_persist_and_refresh` `_guidance_due` `_psyker_block` `_augmetic_block` | 746–882 |
| 6 | `session/seeding.py` (`SeedingMixin`) — `!join` | `_build_turn_order` `_seed_adventure_state` `seed_session` | 1800–1936 |
| 7 | `session/scenes.py` (`SceneFlowMixin`) — scene pointer + post-turn boundary, ADR 057/058/059 | `_set_scene` `_register_scene_npcs` `_journal_scene_event` `_set_scene_flag` · `close_turn` `_scene_context` `_classify_turn` `_apply_npc_sightings` `_exit_labels` `_apply_commitment` `_apply_scene_verdict` `request_scene_move` `report_rejected_move` `_scene_title` `move_scene` `_announce_scene_change` `_make_scene_undo` | 883–967, 1049–1068, 1340–1669 |

About 1100 lines move. The cuts follow the section headers that already exist in the file.

**Changed at move 1 — the ADR 052 pin.** `test_testplan_is_only_reachable_from_the_runtime`
allows only `runtime.py` (plus the loader and `config.py`) to contain the word "testplan".
Three methods outside `__init__` do: `_session_ingest_source`, `update_debug_overlay` and
`_panel_text` (63 lines). They stay in `runtime.py`, so the pin and the tests are untouched.
The price is the size target: `runtime.py` is now expected at ≈ 835 lines, not ≈ 780. Reaching
≤ 800 needs either that allow-list extended by `ingest.py` and `panels.py` (then the three
methods move in one small follow-up commit) or more methods reassigned — Tobi's decision,
reported after move 7.

**Stays in `runtime.py` on purpose (≈ 835 lines):**

- header, imports, `_DATA_DIR`, the WAV helpers, the `_TurnTiming` re-export shim (≈ 120)
- `__init__` (303) — tests patch its collaborators in this module's namespace
- STT/VAD callbacks and the kick phrase (125) — thread boundary, wired by `__init__`, not one
  of the seven concerns
- send util `clear_panel` / `_send_with_retry` / `_send_once` (53), speech mode (19)
- `_brain_channel`, `_load_characters`, identity (`character_name_for`, `prompt_speaker_name`,
  `_seed_speaker_identities`) (70)
- session paths `session_file` / `_state_path` / `_history_path` / `_chekhov_path` and
  `is_debug_run` (30) — bound to `_DATA_DIR`
- `consistency_checker` (21), replay notes (13)
- `_session_ingest_source`, `update_debug_overlay`, `_panel_text` (63) — the ADR 052 pin above

## Steps and gates

One module per commit, on `main`, staged by explicit path (the modified
`data/sessions/…/characters.json` in the working tree is not part of this round). The order is
the table above: small and self-contained first — `ingest` leads because its tests use the
unbound-call style, so it proves the mixin shape on the hardest test pattern — and `scenes`,
the largest and most connected, last. A red gate stops the round at that step.

After every commit:

- **Byte check.** A slice script cuts line ranges; nothing is retyped. It asserts (a) the moved
  text equals the same lines of `git show HEAD:dmbot/runtime.py` byte for byte, (b) the new
  `runtime.py` is the old one minus the slices, with every other difference printed and limited
  to imports, the base-class line and the docstring pointer, (c) for every attribute of
  `SessionRuntime` the kind, `inspect.signature` and source text equal the snapshot taken at
  the base commit, (d) `git diff --stat -- tests/` is empty.
- **Suite:** `uv run --with pytest python -m pytest -q` — 1365 green.
- **Eval:** `uv run dm-eval` exit 0, goldens untouched. It does not import the runtime's
  methods, so here it proves little beyond "the package still imports"; byte check and suite
  are the real guards.
- **Lint:** `uv run --with ruff ruff check --select F dmbot tests` — catches a missing import in
  a new module and a dead one left in `runtime.py`.
- **Docs:** grep `CLAUDE.md`, `architecture.md`, `docs/conventions.md` for the module and the
  moved symbols; fix only the hits, in the same commit. Known hits: the repo-layout rows
  (`architecture.md:723`, `conventions.md:273`).

The seventh commit also carries the final numbers in ADR 065 and the `progress.md` entry. Then
the round stops with a report.

## Deferred — the cog interface (not this round)

Measured at the base, for whoever picks it up:

- The cogs reach runtime privates **446** times in nine files under `dmbot/voice/` (`dicecog`
  109, `delivery` 87, `dmcog` 79, `voicecog` 60, `scenecog` 22, `lorecog` 6, `chekhovcog` 5,
  `clockcog` 4, `timecog` 4): 61 distinct names, plus `runtime._dice_asset_channel` in
  `dicecog`. Nothing outside `dmbot/voice/` reaches a private.
- Six more names travel as strings and would pass a `_rt._` grep: the `_SWITCHES` table of
  `!automatik` in `scenecog`, and `clear_panel("_clock_panel")`.
- 13 of the 68 names are methods, 34 are read only, **21 are rebound by cogs** — listed in
  ADR 065.
- Seven stub runtimes in six test files (`test_augmetics`, `test_flag_commands`,
  `test_gpu_health`, `test_llm_backend`, `test_subcogs` ×2, `test_autorecap._StubRuntime`)
  carry only the private names, so a cog-side rename cannot be done with zero test edits.
- The proposal that was on the table: a table of late-bound aliases (`brain` → `_brain`) over
  unchanged storage, cogs migrated file by file, a guard test at the end.

## Out of scope

- An intent-level API (`rt.world(channel)` instead of the pair `cid = rt._brain_channel(channel)` /
  `rt._state.get(cid)`, which appears about 30 times).
- Splitting `__init__`; moving the STT/VAD callbacks.
- `.claude/skills/improve-architecture/SKILL.md` and two lessons mention the runtime; they are
  outside the three docs named for this round and are only reported if they go stale.

## Live-unverified after the round

All of it: the suite and `dm-eval` do not join a voice channel. The first live session after the
round should exercise `!join` (seeding), one narrated turn with a scene change (post-turn
boundary, panels) and `!leave` (session ingest). This opens no new live gate; it rides on the
Phase 11 evening.
