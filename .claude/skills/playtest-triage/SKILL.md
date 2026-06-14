---
name: playtest-triage
description: Use when the user pastes a live Discord session log, transcript, or annotated complaints from a play session and wants a fix round. Diagnoses the failure chain from the logs, extracts player improvement-wishes, applies deterministic fixes, runs the test suite, commits per round, and updates progress.md (and an ADR when a real trade-off was decided).
---

# Playtest triage — turn a live session into a fix round

This is the project's signature loop. A real round was played, something felt off, and the
user wants it fixed. The job is **diagnosis first, deterministic fix second** — never "the
model got worse".

## Golden rules that bind this work

- **#2** — dice rolling *and* resolution are code (`dmbot/rules/engine.py` + the active
  profile), never the LLM. A fix that lets the model invent results is wrong.
- **#3** — hard world state (HP, inventory, flags) is advanced by code, never written from
  LLM free text.
- **#4** — Bot A's user-ID filter in the sink stays. Never weaken feedback protection "for
  debugging".
- **#8** — anything the DM says stays German; code/logs/commits stay English.

## Procedure

1. **Read the evidence, not your priors.** Sources, in order:
   - the pasted log / annotations (the user's own complaints carry the most signal)
   - `logs/debug.log` (opt-in verbose), `logs/transcript.log` (STT → narration → TTS)
   - the live state under `data/sessions/<id>/state.json` (wounds, NPCs, scene, recap)
2. **Classify each complaint → root cause.** Past diagnoses to pattern-match against
   (`progress.md` decision log):
   - **D43 / ADR 018** — wrong channel → silent example-party fallback → echoed player line
     read aloud (a failure *chain*, not regression).
   - **D57 / ADR 027** — silent `num_ctx` truncation (8192 hardcoded) dropped persona +
     adventure from the prompt mid-session → "ignores the story", over-long answers, puppeting.
   - **D59 / ADR 028** — OCR/statblock junk leaking into the per-turn RAG block.
   Suspect the pipeline (sample rate, context budget, dedupe, channel) before the model.
3. **Fix deterministically.** Prefer a code guard over a prompt nudge. Prompt-only is allowed
   only when the failure is genuinely stylistic — and then note that a code guard is the
   fallback if nemo doesn't adhere.
4. **Run the suite:** `uv run --with pytest python -m pytest`. Add fixed-seed tests for any
   new deterministic logic.
5. **Commit per round** with a scoped imperative message
   (e.g. `dmbot(memory): cumulative auto-recap so wrap-up can't drop the session start`).
6. **Record the round** (end-of-session ritual): update `progress.md` `## Last session` and
   `## Current focus`, and **rotate** the previous `## Last session` entry to
   `docs/progress-archive.md` so the live file stays lean (per `session-ritual`); write the
   next-numbered ADR if a real trade-off was weighed. Mark the result **live-unverified** — the
   next real session is the gate. Name the concrete thing the next round should confirm.

## Notes

- Every log the user pastes is *pre-change*: your fixes are unproven until the next live run.
  Don't claim "fixed", claim "fix landed, live-unverified, gate = X".
- Cross-reference the `playtest-tuning-loop` memory and the relevant ADR before touching code
  in the area a complaint points at.
