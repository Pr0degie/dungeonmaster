# Routine steps move, they never delete

**A prep or reset step that deletes, renames or truncates run artefacts by hand will
eventually destroy the one record you need. Make the step a command that moves the files
into a timestamped archive, with a limit that prunes old ones — and let the code do it, not
the checklist.**

## What happened

- 2026-11-14: the evening's session journal (`history.debug.jsonl`) was deleted by the
  "Sandbox leer" prep step for the next run, and `terminal.log` was overwritten on every
  start. The text comparison with 25.10. had to rebuild the journal from `debug-d1.log`
  (`dmbot/tools/text_replay.py`).
- Measurements ran on hand-made copies (`Copy-Item logs\debug.log logs\debug-d1.log`
  between two passes); a forgotten copy would have mixed two bot starts into one number.

## The correction

D149: one run per log file; the next start moves the previous run to
`logs/archive/runs/<start-stamp>/`, `ingest_session --wipe-debug` moves the `.debug` files
before it wipes the store, `dmbot.tools.logruns` finds and pins runs. A failed move never
blocks the start — it is logged at ERROR.

## How to apply

When a checklist says "delete", "rename" or "copy before restarting", replace the step with
code that archives. Measurements read a run folder (`$d`), never a hand-made copy.
