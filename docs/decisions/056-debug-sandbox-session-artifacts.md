# ADR 056 — Finish the debug-run sandbox: own state, thread, recap and scene pointer

- **Status:** Accepted (code-complete; the next debug-campaign run is the verification)
- **Date:** 2026-08-15
- **Refs:** completes **ADR 055** (which sandboxed only the rotated archives and the RAG
  source) at the same `SessionRuntime.is_debug_run` seam; the artifacts it splits come from
  **ADR 015** (`state.json`), **D41** (`history.jsonl`), **ADR 050** (`chekhov.json`) and
  **D56** (`recap.md`); the scene pointer is **ADR 019/026**. Touches `dmbot/runtime.py`,
  `dmbot/voice/dmcog.py`. Runbook: `docs/debug-campaign-runbook.md`.

## Context

ADR 055 promised that a debug run leaves the live campaign untouched "in both directions".
It delivered that for the *rotated* archives (`history.<stamp>.debug.jsonl`) and the RAG
source (`session_debug_<id>`) — but not for the four **live** per-session artifacts, which
still resolved to one path per channel regardless of mode.

The live run on 2026-08-15 showed what that costs. `DM_ADVENTURE` was switched to the debug
campaign; the bot loaded it correctly (`loaded adventure 'Die Mitternachtsfracht'`) and then
loaded the live campaign's `state.json` and restored 20 turns of the live campaign's thread.
Two failures followed from that one fact:

- The DM kept narrating the *previous* campaign for the whole evening — the restored recap
  and history described it, and nothing in the prompt contradicted them.
- The stored `scene_id` belonged to the previous adventure, so every `get_scene()` returned
  `None`: no scene card in the prompt, no start scene, and no 🧪 overlay — the overlay is
  rendered from the scene, and no scene transition ever happened.

Both directions of the promised isolation were open: the debug run also wrote its own turns,
recap and Chekhov threads into the live campaign's files.

## Decision

1. **One seam for all per-session artifacts.** `SessionRuntime.session_file(channel_id,
   stem, ext)` builds every path under `data/sessions/<channel_id>/`, inserting `.debug`
   before the extension on a debug run. `state.json`, `history.jsonl`, `chekhov.json` and
   `recap.md` all route through it, so a debug evening reads and writes `state.debug.json`,
   `history.debug.jsonl`, `chekhov.debug.json`, `recap.debug.md` and nothing else. The
   naming mirrors the archive split from ADR 055 rather than inventing a second convention,
   and `rotate()` already produces `history.<stamp>.debug.jsonl` from the debug twin.
2. **Same directory, split filenames — not a separate directory.** The channel's session
   folder stays one folder. The committed, read-only `characters.json` (the party sheet) is
   therefore shared by both modes, which is exactly right: the debug campaign is played by
   the real party, and a second folder would fork the sheet, the aliases and the
   `_default`-party fallback for no gain.
3. **Mode from the same path check.** `is_debug_run` (testplan sidecar next to the loaded
   adventure, ADR 055 decision 1) stays the single source of truth. No new env var, no
   second switch that could desync from the archive/RAG routing.
4. **A foreign scene pointer re-seeds, loudly.** At the `seed_session` bootstrap, a stored
   `scene_id` the loaded adventure doesn't know is replaced by `start_scene` and logged at
   WARNING. This is defence in depth, not a duplicate of decision 1: it also covers a scene
   renamed or removed *within* one adventure, and any hand-edited or restored-from-backup
   state — cases the sandbox split cannot reach.

## Alternatives

- **Only the scene-pointer guard (the five-line fix):** rejected — it restores the entry
  point but leaves the recap, the 20 restored turns and the Chekhov list of the live
  campaign bleeding into the debug run, which is most of what went wrong live.
- **A separate `data/sessions/<id>-debug/` directory:** rejected — it forks
  `characters.json` and the party/alias resolution, and it would leave the ADR 055 archives
  (which live in the shared folder, keyed by filename) split across two conventions.
- **Stamp the adventure id into `WorldState` and refuse a mismatched state:** rejected as
  the primary mechanism — it needs a state-format migration, and refusing to load is worse
  at the table than starting the debug campaign cleanly. The pointer guard gets the same
  protection where it matters without touching the format.
- **Route by `DM_ADVENTURE` value instead of the sidecar:** rejected for the reason ADR 055
  already gives — the mode must not depend on a value a user edits between sessions while
  archives keyed the other way already exist on disk.

## Consequences

- **+** A debug evening can no longer read or write a byte of the live campaign's session
  files, in either direction; the ADR 055 promise now holds for the whole session store.
- **+** Switching `DM_ADVENTURE` back and forth is safe and reversible: each mode keeps its
  own position, thread and recap, and resuming the live campaign needs no cleanup.
- **+** A stale or foreign scene pointer now fails loudly at `!join` instead of silently
  degrading a whole session to "no scene card, no overlay".
- **−** Four more filename shapes in the session directory; a human reading the folder must
  know that `.debug` files are test records (the runbook says so).
- **−** State written by a debug run *before* this change still sits in the live
  `state.json` / `history.jsonl` of the channel that ran it — those files need a manual
  look, the split only protects from here on.
- **Live-unverified:** the next debug-campaign run. Gate: the boot log shows the start scene
  `zollhaus`, the 🧪 panel appears at `!join`, and `state.debug.json` is created while the
  live `state.json` keeps its modification time.
