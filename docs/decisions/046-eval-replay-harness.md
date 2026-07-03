# ADR 046 — Golden-transcript replay harness (`dm-eval`): regression, not quality

- **Status:** Accepted
- **Date:** 2026-07-03
- **Refs:** decision log **D93** in progress.md. Builds on **D41** (the `history.jsonl`
  autosave this extends), **ADR 014** (the roll router whose decisions it replays),
  **ADR 026/043** (the scene/flag validation it replays), **ADR 017** (batch/stream
  `finalize_answer` parity — why stream-recorded turns may be replayed through the batch
  path), and the **D89/D90** `dm-sync` pattern (report style + `[project.scripts]` entry
  point). Touches `dmbot/memory/history.py`, `dmbot/orchestrator.py`, `dmbot/runtime.py`,
  `dmbot/voice/delivery.py`, `dmbot/voice/dicecog.py`, new `dmbot/tools/eval_replay.py`,
  `pyproject.toml`, `tests/golden/`.

## Context

Refactor rounds (D70–D81, D87…) all claim "behaviour unchanged" — proven so far by unit
tests plus byte-identical moves. What's missing is an end-to-end check that a *recorded
real session*, played through today's pipeline, still produces the same deterministic
decisions: which dice test the router picked, which markers were parsed out of the DM's
raw answer, which scene moves / element flags the validators accepted. The LLM itself is
not the subject — its answers are frozen recordings; the machinery *around* it is.

Constraints:

- **No real model.** A golden run must be deterministic, offline, and fast enough to be a
  pre-merge gate. Judging *quality* of live model output is the explicit follow-up round
  (Nemo vs. Mistral Small on Timo's box) and out of scope here.
- **`history.jsonl` today** stores only `{ts, user_msg, answer, redo}` — and `answer` is
  the *sanitised* text (markers already stripped). Raw LLM output, structured turn inputs,
  the router's constrained-JSON verdict and the scene/flag verdicts are not recorded.
  Old files must keep loading (crash-restore, D41).
- **Not everything is replayable.** Dice buttons roll real RNG and mutate state on a
  *click* that lands asynchronously (often after the turn's autosave); GM commands
  (`!damage`, `!ort`) and the NPC-memory extraction (its own LLM call, ADR 044) mutate
  state between turns. A naive full-state-snapshot diff would flag all of that as
  regression noise.

## Decision

1. **Golden = playback, no real model.** The harness replaces `OllamaClient` with a
   playback mock that returns the *recorded* raw response for each call (narration turn,
   router classification). This measures **regression of the deterministic machinery**,
   never answer quality. Same input + same recorded LLM text ⇒ the pipeline's decisions
   must be identical; a diff is a behaviour change to either fix or bless.
2. **The autosave becomes a replay journal — backward-compatibly.** `history.jsonl` stays
   append-only JSONL; `load_recent` (crash restore) already ignores unknown fields and
   skips records without `user_msg`+`answer`, so both extensions are compatible:
   - a **session header** record `{"kind": "session", ts, profile, adventure, scene_mode}`
     written once on session seed;
   - **turn records** gain optional fields captured at generation/delivery time:
     `lines` (structured player lines after buffer capping), `results` (dice-result lines
     drained into the turn), `raw` (the kept answer's raw LLM text, markers intact),
     `markers` (the parsed requests the turn queued — tests/manifests/scenes/erledigt as
     dicts), `router` (action, character, skills, the constrained-JSON raw + the parsed
     decision), `scene_verdict` + `flag_verdicts` (what the validators decided), and
     `state_before` (compact `WorldState.to_dict()` at delivery start — the validation
     context).
   Old transcripts (no `raw`/header) are refused by `dm-eval` with a clear message, never
   a crash; they keep working for crash restore.
3. **What is compared, per turn** (one line per deviation, `dm-sync`-style; exit ≠ 0):
   - **turn** — the replayed `_prepare_turn` composition (player lines + `[Würfel]` lines
     + roll directive) against the recorded `user_msg`;
   - **answer** — the sanitised text `finalize_answer` produces from the recorded raw
     against the recorded `answer` (sanitizer/echo-guard regressions);
   - **marker** — the queued Test/Manifest/Scene/Erledigt requests against the recorded
     ones (marker grammar + profile parsing + results-only suppression);
   - **router** — `classify_test` replayed with the recorded constrained-JSON response
     against the recorded decision (schema/parse regressions, ADR 014/042);
   - **state** — the scene-move verdict (`Adventure.resolve_move` against `state_before`,
     the header's `scene_mode`, gated exits) and the per-flag Erledigt verdicts against
     the recorded verdicts;
   - **llm** — playback bookkeeping: a turn consuming more/fewer LLM calls than recorded
     (e.g. an echo-guard retry that didn't fire live) is itself a reported deviation.
4. **What is deliberately NOT compared:** timing/latency, audio/TTS, prompt content
   (recap/RAG/persona blocks — inputs to the frozen LLM, invisible to playback),
   consistency-guard regeneration (replay runs `check=None`; the guard has its own unit
   suite), NPC-memory extraction, and **numeric state mutations** (wounds/warp from dice
   clicks). Verdicts are the deterministic decision surface; full mutation replay would
   need recorded dice values re-fed through the engine — a follow-up if live refactors
   ever touch that path (the engine already has dense fixed-seed unit tests).
5. **Tool shape (D90 pattern):** `dmbot/tools/eval_replay.py`, run as `uv run dm-eval
   [files…]` (default: `tests/golden/*.jsonl`) via `[project.scripts]`. Compact `[eval]`
   report block; exit 0 = green, 1 = deviations, 2 = unusable transcript. Golden stock
   lives in `tests/golden/` — short, committable, synthetic-or-trimmed transcripts plus a
   README describing how to pull a fresh golden from a live session (copy the rotated
   journal, trim, run `dm-eval`, commit). Redo records are folded by the loader exactly
   like `load_recent` (replace the prior turn) before replay.
6. **Blessing a wanted change:** when a behaviour change is intentional, the golden is
   re-recorded (live or by editing the expected fields), not silenced — documented in
   `docs/conventions.md`.

## Alternatives

- **Live model comparison / quality eval:** explicitly the *next* round (needs exactly
  this harness as substrate). Playback keeps the gate deterministic and free.
- **Full WorldState snapshot diff per turn:** rejected for the first cut — dice-click
  RNG, GM commands and NPC-memory writes land asynchronously between snapshots, so the
  diff would be dominated by unreplayable noise (false positives). Verdict comparison
  captures the deterministic decisions with none of that.
- **Recording dice values and re-running the engine:** deferred — real coverage gain is
  small (fixed-seed engine tests are dense), recording surface is wide (every roll
  callback). Reconsider when a refactor actually touches the roll→damage path.
- **Deriving expectations at replay time ("bless on first run") instead of recording
  them live:** rejected — recorded-live expectations pin the behaviour the table actually
  saw; a bless-only golden would pin whatever the current (possibly already broken) code
  does.
- **A separate recording file next to `history.jsonl`:** rejected — one journal per
  session keeps the "pull a golden from last night's session" workflow a single copy, and
  the loader tolerance makes the extension free.

## Consequences

- **+** Refactor rounds get a real end-to-end gate: `uv run dm-eval` before merge, with
  turn-level, category-labelled diffs instead of "the suite is green, trust me".
- **+** Every future live session automatically produces golden-able material (the
  journal records replay fields as it plays).
- **−** The autosave records more per turn (raw text + state_before snapshot); journals
  grow a few hundred KB per evening. They rotate per session and are git-ignored — fine.
- **−** The replay drives the **batch** path only; stream-recorded turns replay through
  `respond()` relying on ADR-017 `finalize_answer` parity (unit-tested). A parity break
  would surface as an `answer` diff — that's a feature, but read the diff before blaming
  the golden.
- **−** Verdict-level state comparison means numeric-mutation regressions (soak
  arithmetic, warp bookkeeping) are *not* covered here — they stay unit-test territory.
- **Bound for later work:** goldens are a contract. A wanted behaviour change now has an
  explicit extra step (re-record/bless the goldens) — that friction is the point.
