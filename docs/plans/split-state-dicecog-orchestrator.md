# Plan — split `memory/state.py`, `orchestrator.py` and `voice/dicecog.py`, no behaviour change

**Status:** approved by Tobi on 2026-11-27, decisions 1–6 as recommended; decision 7 of the same
day changes the order of round 3 (see *Decisions*).
Round 1 (`memory/state.py`) and round 2 (`orchestrator.py`) done on 2026-11-27 — see *Result*
under sections 1 and 2. Round 3 (`voice/dicecog.py`) done on 2026-11-27 as well, **before** the
next run — changed by Tobi the same day, decision 7; see *Result* under section 3. All three
rounds are done; nothing of them has been heard at the table yet.
**Date:** 2026-11-27 · **Base commit:** `676f78e` (all line numbers below refer to it)
**Pattern:** [runtime-split.md](runtime-split.md) · **Rules:** lesson
[byte-exact-moves-stepwise-gates](../lessons/byte-exact-moves-stepwise-gates.md)
**Governing:** ADR 034 (re-export shims), ADR 039 (sub-cogs for commands), ADR 065 (mixins, no
state, `self` stays the host), ADR 046 (`dm-eval` as the refactor gate), ADR 052 (testplan pin).

## Recommendation in short

1. **Start with `memory/state.py`.** Nothing in the tests pins its cut (no patch on its module
   namespace, no logger pin, no file-name pin, no metaclass), it is the quietest of the three
   (one commit since 15.11.), and `dm-eval` replays the goldens through `WorldState`, so the
   refactor gate actually guards it. Two plain moves with re-exports, the ADR 034 pattern.
2. **Then `orchestrator.py`.** The round of 27.11. changed only `_prepare_turn` there, and that
   method stays where it is. Five moves, the ADR 065 pattern. It does not have to wait for the
   run (decision 1).
3. **`voice/dicecog.py` only after the next run is evaluated and its fix round is committed.**
   The round of 27.11. (D151, D152, D153) changed 357 lines there, spread over every block this plan
   would move except the command block. Fixes from the run will land in exactly those blocks,
   and a move in between would put a second variable into the run that is meant to verify them.
   Its line numbers below are a sketch; the round re-measures at its own base commit.
   **Changed on 2026-11-27 — decision 7: the round runs before the run.**

Each file is its own round with its own closing report. This plan does not bundle them.

## Goal

| File | Lines now | Target | Expected | Moves |
| --- | --- | --- | --- | --- |
| `dmbot/memory/state.py` | 1457 | ≤ 900 | ≈ 860 | 2 |
| `dmbot/orchestrator.py` | 1421 | ≤ 800 | ≈ 630 | 5 |
| `dmbot/voice/dicecog.py` | 1442 | ≤ 800 | ≈ 730 | 4 + 1 seam commit |

About 2100 lines move. Method bodies move byte for byte by a line-slice script; nothing is
retyped. Baseline per the State header: 1647 tests green, 4 xfail, ruff (F) clean, `dm-eval`
exit 0 — step 0 of each round measures it again before the first move.

## What constrains the cut (measured at the base)

| Fact | Consequence |
| --- | --- |
| `test_dice_animation`, `test_dice_assets`, `test_dice_images` patch seven names on the namespace `dmbot.voice.dicecog`: `get_dice_image_async`, `get_dice_gif_async`, `get_target_image_async`, `prepare_throw_async`, `flight_seconds`, `resolve_target`, `REVEAL_GRACE_S` | A method that reads one of them stays in `dicecog.py`: `_send_dice_button`, `_animate_result`, `_animate_stored`, `_result_edit`, `_make_fate_decision`, `!roll`. Two manifest methods read `prepare_throw_async` too — decision 4. **Since D0 (`921a55c`) `DiceCog._prepare_throw` is the only reader of `prepare_throw_async`;** the other six names are read as listed. |
| `dmbot/tools/text_replay.py:273` rebinds `orchestrator.load_system_prompt` for a persona comparison | `DMBrain._build_request` (the only reader, line 701) stays in `orchestrator.py`. |
| `test_classifier_latency` captures the `[classifier]` line on the logger `dmbot.orchestrator` (three places) | `DMBrain._log_classifier` (7 lines) stays in `orchestrator.py`; the classifier methods move and keep calling it through `self`. |
| Tests reach names through `dmbot.orchestrator` (`_ROLE_LABELS`, `finalize_answer`, `StreamAssembler`, …) and through `dmbot.memory.state` (26 names) | Every name stays importable from the old module. An import that becomes unused there is deleted only if a grep over `dmbot/`, `tests/` and `tools/` finds no reader; otherwise it stays with `# noqa: F401`. |
| Unbound and stub calls: `WorldState.seed_from_store(...)` (28), `WorldState.record_commitment(...)`, `DiceCog.__new__(DiceCog)` (6 files), `DiceCog.agenda.callback(...)` (7), `brain._session(...)` (31), `brain._prepare_turn(...)` (7); subclasses `FakeBrain(DMBrain)` in `tests/fakes.py` and `_Brain(DMBrain)` in `test_autorecap` | Mixins satisfy all of them by construction (ADR 065). The exception is the command block of `DiceCog` — decision 3. |
| ADR 052 pin: `test_testplan_is_only_reachable_from_the_runtime` walks every file under `dmbot/` and exempts by file name (`testplan.py`, `runtime.py`, `config.py`) | None of the three files mentions the testplan, so nothing is held back. No new module may be named `runtime.py` or `config.py`. `test_prompt_paths_never_touch_the_testplan` reads only the source of `orchestrator.py`; the moved methods stay covered by the walk. |
| Log names: nothing in `dmbot/tools/`, `tools/`, the skills or the Beipackzettel filters on `orchestrator`, `dicecog` or `memory.state`; the check items grep message text | Moved code may log under its new module name (decision 5). |
| `dm-eval` drives `DMBrain` and `WorldState`, not `DiceCog` | A real gate for the first two rounds; for `dicecog` it only proves that the package imports. |
| No pickling and no `__module__`/`get_type_hints` use on the state classes | The dataclasses may change their home module. |

## 1 — `dmbot/memory/state.py` (first)

**Shape:** two plain moves into sibling modules, `state.py` re-exports every moved name
(ADR 034). `WorldState` itself stays whole in `state.py`. No importer is edited.

| # | Module | What moves | Lines at base |
| --- | --- | --- | --- |
| S1 | `memory/state_text.py` — the German lines for prompt and panels | `_combatant_line_de` `_agenda_line_de` `mission_line_de` `fact_line_de` `clock_segments` `clock_line_de` `clock_full_note_de` `clocks_panel_de` `pressure_panel_de` `world_state_summary_de` | 1271–1457 (187) |
| S2 | `memory/records.py` — the records `WorldState` is made of | constants `DOWNED_CONDITION` `ATTITUDE_SCALE` `NPC_MEMORY_CAP` `AGENDA_LOG_CAP` `GROUP_HOLDER` `FACT_KINDS` `FACT_STATUSES` `FACT_TEXT_MAX` `FACT_CAP` `CLOCK_SIZES` · `_validated_fact_text` · `AgendaStep` `NpcMemory` `Combatant` `step_attitude` `Clock` `slugify_clock_id` `Deadline` `Fact` `Quest` | 48–84, 143–539 (434) |

**Stays in `state.py` (≈ 860):** docstring and imports, the in-game-time section
(`TURN_ADVANCE_MINUTES`, `SCENE_CHANGE_ADVANCE_MINUTES`, the two regexes, `parse_time_of_day`,
`parse_campaign_time_de`, `absolute_minutes`; lines 86–141), `WorldState` (542–1268, 727 lines),
the re-export block.

**Import direction:** `records` imports only `gametime` and the standard library. `state`
imports `records`. `state_text` imports `records` and `gametime`, and `WorldState` only under
`TYPE_CHECKING` (the block names the state types in annotations only — expected, and the suite
decides at the step). `state` imports `state_text` for the re-export. No cycle.

**Order:** S1 first — a leaf nobody inside `state.py` calls, so it proves the re-export shape
on the smaller slice. S2 second.

### Result — `state.py` (2026-11-27, done)

| Step | Commit | `state.py` | New module | Suite | Byte check | `state.json` check |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | base `d3914c5` | 1457 | — | 1647 passed, 4 xfail; ruff clean; `dm-eval` 0 | snapshot: 187 names | 2163 bytes, sha `725262287117…` |
| S1 | `2907fd2` | 1279 | `state_text.py` 212 | 1647 / 4 / clean / 0 | slice 1269–1457 verbatim; rest = imports + re-export block | identical bytes, prompt block, panel |
| S2 | `81bfbbc` | **868** | `records.py` 451 | 1647 / 4 / clean / 0 | slices 59–95 and 154–549 verbatim; rest = re-export block + dropped blank lines | identical bytes, prompt block, panel |

- Every name of the snapshot is still reachable as `dmbot.memory.state.<name>` with the same kind,
  signature and source, except four gametime imports (`day_phase_de`, `deadline_line_de`,
  `remaining_de`, `render_time_phase_de`) that only the S1 functions used: dropped from
  `state.py`, no reader under `dmbot/`, `tests/`, `tools/`. Zero test edits; goldens untouched.
- Logger names (decision 5): `records.py` has its own logger, so the two NPC lines (memory prune,
  ignored attitude proposal) log under `dmbot.memory.records`. `state_text.py` logs nothing.
- `state_text.py` imports the record types from `records` at runtime and `WorldState` only under
  `TYPE_CHECKING` (in S1, before `records` existed, all of them came from `state` under
  `TYPE_CHECKING`).
- Slice B ended at base line 538, not 539 (539 is the blank line before `WorldState`).

## 2 — `dmbot/orchestrator.py` (second)

**Shape:** new package `dmbot/brain/`. The turn records move as a plain module with re-exports;
four concerns move as mixins without `__init__` and without state (ADR 065):

```python
class DMBrain(GenerationMixin, SideCallsMixin, OpeningMixin, PendingMixin):
```

| # | Module (class) | What moves | Lines at base |
| --- | --- | --- | --- |
| O1 | `brain/channel.py` — per-channel and per-turn records | `TurnAnswer` `turn_user_msg` `_Turn` `_markers_dict` `ChannelSession` `_Sink` `_Attempt` | 76–235 (160) |
| O2 | `brain/pending.py` (`PendingMixin`) — what the cogs take out of the brain and put into it | `take_pending` `_drop_pending` `take_pending_tests` `tests_narrator` `take_pending_manifests` `take_pending_scenes` `take_pending_erledigt` `take_pending_uhr` `take_pending_zeit` · `add_gm_note` `discard_gm_notes` `last_action` `last_actions` `take_replay_turn` `last_user_msg` `restore_history` | 1005–1116 (112) |
| O3 | `brain/opening.py` (`OpeningMixin`) — `!start` / `!intro` | `_prepare_opening` `_opening` `respond_opening` `respond_opening_streaming` | 607–682 (76) |
| O4 | `brain/side_calls.py` (`SideCallsMixin`) — every model call that is not a narrated turn | `classify_test` `classify_scene_move` `_scene_outcome` `_fact_outcome` `_npc_outcome` `_note_scene` `_note_fact` `_note_npc` `classify_commitment` `classify_present_npcs` · `summarize` · `answer_rules` | 1126–1246, 1284–1320, 1374–1393 (178) |
| O5 | `brain/generation.py` (`GenerationMixin`) — one answer through the guards | `_apply_consistency` · `_chat_once` `_answer_problem` `_prev_answer` `_stream_once` `_log_cut` `_guarded_answer` `_run_turn` | 554–605, 715–944 (282) |

**Stays in `orchestrator.py` (≈ 630):** docstring, imports and the ADR 034 re-export block;
`__init__`; the buffer (`_session`, `add_player_line`, `pending_count`, `waiting_turn`,
`turn_held`, `_drain`); `_prepare_turn`, `_hold_turn`, `_refresh_rag`; `_respond`/`respond`,
`_redo`/`redo`, `respond_streaming`, `redo_streaming`; `_build_request` (pinned by
`text_replay`); `_queue_markers`, `_append_turn`; `_log_classifier` (pinned by the logger);
`add_test_result`, `_drain_test_results`, the context setters; `current_recap`, `history_len`,
`history_messages`, `client`; `clear_history`, `reset`, `aclose`.

**Order:** O1 first — it is a precondition: the mixin modules need `_Attempt`, `_Sink`,
`TurnAnswer` and `_markers_dict`, and importing them from `orchestrator` would be a cycle.
Then small and self-contained (`pending` has no model call and no log line), and `generation`,
the turn's hot path, last.

**Left alone on purpose:** the open `DMBrain` findings (Nr. 5–8, 10, 13, 14 in `progress.md`)
sit in `_prepare_turn`, `_queue_markers` and the retry paths. This round moves code and fixes
none of them; the four xfails stay xfail.

### Result — `orchestrator.py` (2026-11-27, done)

| Step | Commit | `orchestrator.py` | New module | Suite | Byte check | Pins and `text_replay` |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | base `c7c09f9` | 1421 | — | 1647 passed, 4 xfail; ruff clean; `dm-eval` 0 | snapshot: 70 module names, 74 `DMBrain` attributes | hold; `--help` starts |
| O1 | `bb24158` | 1274 | `brain/channel.py` 177 | 1647 / 4 / clean / 0 | slice 76–235 verbatim; rest = docstring pointer, re-export block, 2 dropped imports | hold; starts |
| O2 | `506072d` | 1158 | `brain/pending.py` 138 | 1647 / 4 / clean / 0 | slice 858–969 (base 1005–1116) verbatim; rest = pointer, mixin import, base-class line, 5 dropped imports | hold; starts |
| O3 | `79b0b2f` | 1083 | `brain/opening.py` 96 | 1647 / 4 / clean / 0 | slice 457–532 (base 607–682) verbatim; rest = pointer, mixin import, base-class line | hold; starts |
| O4 | `1a9689b` | 895 | `brain/side_calls.py` 215 | 1647 / 4 / clean / 0 | slices 788–908, 946–982, 1036–1055 (base 1126–1246, 1284–1320, 1374–1393) verbatim; rest = pointer, mixin import, base-class line, 16 dropped imports | hold; starts |
| O5 | `03349e8` | **608** | `brain/generation.py` 318 | 1647 / 4 / clean / 0 | slices 399–450, 483–712 (base 554–605, 715–944) verbatim; rest = pointer, mixin import, base-class line, 4 dropped imports | hold; starts |

Slice numbers are measured at each step's parent commit, by symbol name with `ast`; the base numbers
in brackets are the ones of this plan. `orchestrator.py` had not changed between the plan's base
`676f78e` and the round's base `c7c09f9`, so they still held.

- 808 lines moved (160 + 112 + 76 + 178 + 282): seven records and 40 methods. `dmbot/brain/` holds
  946 lines in six files. Target ≤ 800, expected ≈ 630, reached **608**.
- All 74 attributes of `DMBrain` at the base are still reachable as `DMBrain.<name>` with the same
  kind, signature and source. Of the 70 module-level names, 43 likewise; the other 27 are imports
  that only the moved code used (`json`, `asdict`, `dataclass`, `field`, `empty_markers`, six marker
  request types, the three router functions and their verdict types, the roll-router and recap
  helpers, `retry_nudge_de`, `INTRO_RETRY_NUDGE`, `caller_reports_cut`): dropped from
  `orchestrator.py`, no reader under `dmbot/`, `tests/`, `tools/`. Zero test edits; goldens untouched.
- Each mixin has only methods, no `__init__`, and no name is defined twice across `DMBrain` and the
  four mixins (checked at every step, beyond the plan's list).
- Whole round against the base: of the 1303 non-blank lines of `orchestrator.py`, ten import lines
  and the line `class DMBrain:` are the only ones found in neither `orchestrator.py` nor `brain/`.
- Logger names (decision 5): `side_calls.py` and `generation.py` have their own loggers. Under
  `dmbot.brain.generation` now: `🪵 LLM roh`, the echo-guard, intro-guard and `[consistency]` lines,
  the `✂` cut line, "streaming turn failed mid-generation". Under `dmbot.brain.side_calls`:
  "roll-router classification failed" and the over-long-recap warning. The `[classifier]` line
  keeps `dmbot.orchestrator`. `channel.py`, `pending.py` and `opening.py` log nothing.
- Deviation from *Steps and gates*: the byte check, `dm-check` and the three extra checks ran on the
  working tree **before** each commit (against `HEAD`), not after it — the pre-commit hook wants the
  green stamp anyway, and a red check then leaves no commit to take back. After the round the
  slices were compared once more on the committed objects (`<commit>` against `<commit>~1`): same
  result.
- Docs moved with the code: the repo-layout rows in `architecture.md` and `docs/conventions.md`
  (new `brain/` row) and the "likely spots" line in the `improve-architecture` skill.

## 3 — `dmbot/voice/dicecog.py` (third — before the next run, decision 7)

The tables below are the sketch at the plan's base `676f78e`; the round measured again at its own
base — see *Result* at the end of this section.

**Shape:** the NPC commands become a sub-cog (ADR 039); three concerns of `DiceCog` move as
mixins into a new package `dmbot/voice/dice/` (ADR 065):

```python
class DiceCog(RollRoutingMixin, DamageMixin, ManifestMixin, commands.Cog):
```

| # | Module (class) | What moves | Lines at base |
| --- | --- | --- | --- |
| D0 | — (seam commit, new logic, reviewed) | one helper in `dicecog.py` for "prepare the throw in the background", used by the four call sites of `prepare_throw_async` (decision 4) | 339, 585, 708, 926 |
| D1 | `voice/npccog.py` (`NpcCog`) — the human GM's NPC commands | `npc` `npcmem` `agenda` `agenden` (they reach only `self._rt`) | 1290–1442 (153) |
| D2 | `voice/dice/routing.py` (`RollRoutingMixin`) — which roll does this turn ask for | `_spoken` `_said` `_check_marker` `_difficulty_label` `_markers_decide` `_router_decides` `_manifesting` `_toughness_bonus` `_post_router_dice` | 139–305 (167) |
| D3 | `voice/dice/damage.py` (`DamageMixin`) — a hit becomes booked wounds | `_choose_weapon` `_target_phrases` `_begin_attack_damage` `_apply_attack_damage` `_book_damage` | 970–1086 (117) |
| D4 | `voice/dice/manifest.py` (`ManifestMixin`) — psychic powers, ADR 022 | `_post_manifest_button` `_send_manifest_button` `_make_manifest_roll` `_manifest_once` `_book_manifest` `_present_manifest` `_feed_manifest` `_finish_manifest` `_begin_power_damage` `_apply_power_damage` `_make_manifest_fate` `_edit_manifest_text` `_resolve_warp_consequences` · constant `_NO_TARGET` | 57, 678–968 (291) |

**Stays in `dicecog.py` (≈ 730):** header and the two timing constants; `__init__` (it sets the
three runtime hooks) and `on_ready`; `_handle_dice`; the dice button and the roll
(`_post_dice_button` … `_roll_test_face`); the whole presentation block (`_dice_images_on` …
`_result_edit`) — four of the seven patched names live there; fate (`_fate_holder`,
`_make_fate_decision`); `_finish_roll` and the one-narration wait of D152 (`_cancel_roll_wait` …
`_log_roll_wait`); the turn order; the commands `!roll`, `!test`, `!turn`, `!rules`, `!damage`,
`!heal`.

**Order:** D0, then D1 (commands, no shared helper), D2, D3, and `manifest` last — the largest
block and the one D153 rewrote.

### Result — `dicecog.py` (2026-11-27, done)

| Step | Commit | `dicecog.py` | New module | Suite | Byte check | Commands and listeners |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | base `c96218d` | 1442 | — | 1647 passed, 4 xfail; ruff clean; `dm-eval` 0 | snapshot: 68 `DiceCog` attributes, 49 module names | 10 commands, 1 listener |
| D0 | `921a55c` | 1449 | — (seam, new logic) | 1650 / 4 / clean / 0 (three new tests) | not a move: `_prepare_throw` added (7 lines), four call-site lines changed; reviewed | equal to the base |
| D1 | `4b97606` | 1297 | `voice/npccog.py` 172 | 1650 / 4 / clean / 0 | slice 1296–1449 verbatim; rest = docstring pointer | `DiceCog` 6 + `NpcCog` 4, 1 listener — equal |
| D2 | `f29464b` | 1131 | `voice/dice/routing.py` 192 | 1650 / 4 / clean / 0 | slice 140–307 verbatim; rest = pointer, mixin import, base-class line, 3 dropped imports | equal |
| D3 | `d535b2c` | 1014 | `voice/dice/damage.py` 143 | 1650 / 4 / clean / 0 | slice 812–929 verbatim; rest = pointer, mixin import, base-class line, 1 dropped import | equal |
| D4 | `fb1d6ed` | **720** | `voice/dice/manifest.py` 325 | 1650 / 4 / clean / 0 | slices 61–64 and 521–812 verbatim; rest = pointer, mixin import, base-class line, 4 dropped imports | equal |

Slice numbers are measured at each step's parent commit, by symbol name with `ast`. Between D0 and
D1 sits one docs commit (`e1e0809`, the doc findings of the D0 review).

- 736 lines moved (154 + 168 + 118 + 296): four commands, 27 methods and one constant. Target
  ≤ 800, expected ≈ 730, reached **720**. `dmbot/voice/dice/` holds 661 lines in four files.
- **The cut is the sketch's:** the same methods went to the same modules. `dicecog.py` had not
  changed between the plan's base `676f78e` and the round's base `c96218d`; no moved method reads
  one of the seven replaced names after D0 (checked at every step over `co_names`, nested functions
  included, for all 32 functions now defined outside `dicecog.py`).
- **Differences from the sketch:**
  - Each slice starts at the blank line before its first method, so it is one line longer than
    the sketch (154 / 168 / 118 / 292). `_NO_TARGET` moved with its comment and two blank lines.
  - **Test edits in three files, not one.** D0 got three tests in `tests/test_dice_animation.py`
    instead of one: the seam itself, the manifest button, and both Fate rerolls — neither reroll
    call site had ever run in a test with the animation on. D1 edited `tests/test_agenda.py` as
    decision 3 says (ten lines name `NpcCog`) **and `tests/test_command_errors.py`, which this plan
    had not counted**: `test_the_name_taking_commands_document_the_quoted_form` took `npcmem` and
    `agenda` from `DiceCog.__cog_commands__` and went red (`KeyError`). The round stopped there;
    Tobi approved on 2026-11-27 that the test reads both cogs and that the walk in
    `test_all_registered_commands_yield_a_usable_usage_line` includes `npccog` (it would have
    stayed green at 56 of 60 commands and silently dropped the four). Goldens untouched.
  - The re-check of the test pins found the seven names unchanged. Also reached on the namespace:
    `dicecog.asyncio.sleep` (the shared module object, so the replacement reaches the mixins too)
    and `dicecog.CLIENT_START_S` (read only; stays).
  - Gates, as in round 2: `dm-check` ran on the working tree before each commit. After each
    commit: the stamp still matches the committed tree (`dm_check --fresh`) and the tree is clean,
    then the byte check on the committed objects (`HEAD~1` → `HEAD`) and the command check.
- Snapshot: all 69 attributes after D0 (68 of the base plus `_prepare_throw`) are reachable with the
  same kind, signature and source — 65 as `DiceCog.<name>`, the four commands as `NpcCog.<name>`.
  Against the base only the four D0 call sites differ. Nine of the 49 module-level names are gone
  from `dicecog.py`: eight imports that only moved code used (`is_continuation_fragment`,
  `marker_key`, `superseded_by_manifest`, `Character`, `TargetSelectView`, `combat`,
  `resolve_manifest_request`, `ManifestRequest`) and `_NO_TARGET`; no reader under `dmbot/`,
  `tests/`, `tools/`.
- Each mixin has only methods, no `__init__`, and no name is defined twice across `DiceCog` and the
  three mixins. Registered on a real `commands.Bot` (offline): ten commands with their five aliases
  resolve, `on_ready` is the one listener, the three runtime hooks point at `DiceCog` methods.
- Whole round against the base: of the 1343 non-blank lines of `dicecog.py`, twelve are found in
  none of the files — one docstring line, six import lines, the line `class DiceCog(commands.Cog):`
  and the four call sites D0 rewrote.
- Review of D0 (`/code-review`, medium): no correctness finding. One finding that was there before
  (see *Noticed while measuring*), two doc findings fixed in `e1e0809`.
- Logger names (decision 5): under `dmbot.voice.dice.routing` now the `🎲 Marker …`,
  `🎲 Sicherheitsnetz`, `🎲 … Inline-Marker verworfen` and `🎲 router: …` lines; under
  `dmbot.voice.dice.damage` the `🎯 Ziel aus der Ansage` line of an attack and the booked-damage
  line; under `dmbot.voice.dice.manifest` the `🌀` result lines, the Fate line of a manifest, the
  `🎯` line of a power and "Warp charge not tracked". `npccog.py` logs nothing. The `🎲` result
  line of a test and everything about the throw keep `dmbot.voice.dicecog`.
- Visible at the table: the default `!help` lists `!npc`, `!npcmem`, `!agenda`, `!agenden` under
  the heading `NpcCog`.
- Docs moved with the code: the repo-layout rows in `architecture.md` and `docs/conventions.md`,
  the module docstring of `dicecog.py`.

## Steps and gates (every round)

One module per commit, on `main`, staged by explicit path. A red gate stops the round at that
step; the commit before it stays.

**Step 0, once per round:** run `uv run dm-check` and note the numbers; take the snapshot the
byte check compares against (for every attribute of the host class and every module-level
name: kind, `inspect.signature`, source text); grep the tests once more for patches, `rglob`
and file allow-lists that appeared since this plan was written.

**After every move commit:**

- **Byte check** (slice script in the scratchpad, as in the runtime split):
  1. the moved text equals the same lines of `git show HEAD~1:<file>` byte for byte;
  2. the shrunk file is the old one minus the slices; every other difference is printed and
     limited to imports, the base-class line, the re-export block and the docstring pointer;
  3. every name of the snapshot is still reachable under its old path
     (`dmbot.memory.state.<name>`, `DMBrain.<name>`, `DiceCog.<name>`) with the same kind,
     signature and source;
  4. `git diff --stat -- tests/` is empty (one planned exception: step D1, decision 3);
  5. no moved function reads a name that tests or tools patch on the old module's namespace —
     checked over `__code__.co_names`, nested functions included, against the seven `dicecog`
     names and `load_system_prompt`.
- **`uv run dm-check`** — ruff (F) catches a missing import in the new module and a dead one
  left behind; the suite must show the baseline count; `dm-eval` exit 0 with untouched goldens.
- **Docs in the same commit:** grep `CLAUDE.md`, `architecture.md`, `docs/conventions.md`,
  `.claude/skills/` and `docs/lessons/` for the file and the moved symbols; fix only the hits.
  Known: the repo-layout rows `architecture.md:759` and `docs/conventions.md:310`,
  `architecture.md:342`, `.claude/skills/improve-architecture/SKILL.md:42`.

**Extra checks per file:**

| Round | Check | Why |
| --- | --- | --- |
| `state.py` | a `WorldState` built by `seed_from_store`, written with `save` and read with `load`, produces the same `state.json` bytes as at the base | the records change their home module; the file on disk must not notice |
| `orchestrator.py` | `DMBrain._build_request.__globals__` is the namespace of `dmbot.orchestrator`; `DMBrain._log_classifier.__module__` is `dmbot.orchestrator` | the two pins from the table above |
| `orchestrator.py` | `uv run python -m dmbot.tools.text_replay --help` still starts | the tool rebinds a name in the module this round shrinks |
| `dicecog.py` | names and aliases of all commands and listeners of `DiceCog` plus `NpcCog` equal those of `DiceCog` at the base | the cog metaclass collects commands; nothing may get lost or doubled |
| `dicecog.py` | D0 gets a `/code-review`; the move commits do not need one | review belongs on new logic (lesson) |

**Last commit of each round:** final numbers into this plan (a *Result* table per file), a
dated amendment with those numbers in the ADR the round followed (034 for `state.py`, 065 for
`orchestrator.py`, 039 and 065 for `dicecog.py`), and the `progress.md` entry. No new ADR is
needed: every shape here is one an ADR already decided.

## Decisions

All six were decided by Tobi on 2026-11-27 as recommended. The alternatives stay written down for
whoever asks why.

1. **May `orchestrator.py` go before the next run?**
   **Decided: yes, but never in between — either the round is finished and green before
   the bot is restarted for the run, or it starts after the run is evaluated.** For: the 27.11.
   round touched only `_prepare_turn`, which does not move; the suite and `dm-eval` both drive
   `DMBrain`; a short test run is a better place to meet a wiring mistake than the Claude
   evening. Against: the fixed `DMBrain` findings Nr. 1–4, 9 and 12 have never been heard at
   the table, and their code would move before they are.
2. **`state.py`: stop at ≈ 860 lines, or cut into `WorldState` as well?**
   **Decided: stop.** `WorldState` is one class with one job — the only writers of the
   hard state (golden rule #3) — and its 727 lines already carry section headers per ADR. A
   third move would take the fact and mission writers (lines 1097–1265, 169 lines) into
   `memory/facts.py` as a mixin and bring the file to ≈ 690; it buys a shorter file, not a
   clearer one. After all three rounds `state.py` would be the third-largest file, behind
   `delivery.py` (974) and `runtime.py` (894).
3. **`!npc`, `!npcmem`, `!agenda`, `!agenden`: sub-cog or mixin?**
   **Decided: sub-cog `NpcCog`, as ADR 039 decided for scene and lore commands.** The
   price is the round's only test edit: `tests/test_agenda.py` names the class in ten lines
   (`DiceCog.agenda.callback(...)`, the `_cog` helper), and the default `!help` lists the four
   commands under a new heading. A mixin would need no test edit, but ADR 039 ruled commands on
   mixins out, and the four commands have nothing to do with dice.
   *Correction from the round (2026-11-27):* it was not the only test edit —
   `tests/test_command_errors.py` reads two of the four commands from `DiceCog` as well; see
   *Result* under section 3.
4. **The two manifest methods that read `prepare_throw_async`** (`_send_manifest_button`,
   `_make_manifest_fate`).
   **Decided: the seam commit D0** — one small method in `dicecog.py`, the four call sites
   use it, and the manifest block moves whole. Alternatives: leave the two methods behind (the
   concern is then split over two files), or move them as they are (works today because no
   test that patches the name reaches a manifest, and breaks silently for the first one that
   does).
5. **Log names of moved code.**
   **Decided: the new module name, as in the runtime split** — `brain.generation` instead
   of `orchestrator` in front of the `🪵 LLM roh` and echo-guard lines, `voice.dice.manifest`
   instead of `voice.dicecog`. The `[classifier]` line keeps `orchestrator` because of the pin.
   Nothing filters on these names today. The alternative is to give every new module the old
   logger name; then `debug.log` reads the same across the split, at the cost of a logger name
   that no longer says where the line comes from.
6. **Names.** `memory/records.py`, `memory/state_text.py`, `dmbot/brain/` (`channel`,
   `pending`, `opening`, `side_calls`, `generation`), `dmbot/voice/dice/` (`routing`, `damage`,
   `manifest`), `voice/npccog.py`. **Decided: as written;** they are cheap to change now
   and expensive after the first commit.
7. **Changed on 2026-11-27 (Tobi): `voice/dicecog.py` goes before the next run, not after it.**
   Recommendation 3 said to wait until the run is evaluated and its fix round is committed.
   **Decided instead: the round runs now, and one run afterwards checks everything together** —
   D151–D155 and all three splits. **The price, as this plan named it:** the round of 27.11.
   (D151, D152, D153) changed 357 lines in exactly the blocks that move, and none of them has
   been heard at the table; the run that is meant to verify them now carries the move as a
   second variable. If the dice flow misbehaves in that run, the fix and the move are both
   suspects, and fixes from the run land in the new modules. What speaks for the fix in that
   case is the byte check (moved text identical to the parent commit, same kind, signature and
   source for every attribute). The rule of decision 1 holds here too: the round is finished and
   green before the bot is restarted. Decisions 1–6 stand as decided.

## Out of scope

- Pointing importers at the new modules (`from .records import Combatant` in
  `npc_memory.py`, …). The old modules stay the public face, as `orchestrator.py` has been for
  the ADR 034 helpers.
- The cog interface (446 reaches into runtime privates, 109 of them from `dicecog`) — still
  deferred as in [runtime-split.md](runtime-split.md).
- Any fix: the open `DMBrain` findings, whatever the next run shows in the dice flow.
- `voice/delivery.py` (974 lines) and `runtime.py` (894), the next two by size.
- Moving the time parsers from `state.py` into `memory/gametime.py`.

## Noticed while measuring

- `DiceCog._toughness_bonus` (`dicecog.py:251`) has no caller left under `dmbot/`; only two
  tests in `tests/test_augmetics.py` call it. Probably orphaned by D155. Not touched here.
- `DiceCog.cog_unload` ends the roll waits but not the running presentation tasks in
  `self._presentations` (throw preparation, `_animate_result` with its reveal sleep): a task still
  running when the cog unloads edits its dice message afterwards or is destroyed while pending.
  Found by the review of D0 (2026-11-27), there before D0. Not touched here.

## Live-unverified after each round

All of it — the suite and `dm-eval` do not join a voice channel. What the first session after
a round should exercise:

- **`state.py`:** `!join` on an existing `state.json`, one booked hit, one narrated handover
  (fact), the player panel.
- **`orchestrator.py`:** one narrated turn with a roll, `!redo`, `!start` or `!intro`, `!wrap`
  (recap), `!rules` with a question.
- **`dicecog.py`:** a skill test with a fate re-roll, a manifest with damage, an attack with
  the target picker, `!npc`, `!agenda`, `!help`. With the throw animation on, both Fate rerolls
  (test and manifest) show a second throw — D0 changed those two call sites, and before D0 no
  test had run them.

None of this opens a new live gate; it rides on the Phase 11 runs.
