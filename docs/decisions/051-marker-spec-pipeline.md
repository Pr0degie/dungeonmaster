# ADR 051 — Marker pipeline consolidation: declarative `MarkerSpec` table, one generic seam

- **Status:** Accepted
- **Date:** 2026-07-04
- **Refs:** decision log **D98** in progress.md. Redeems the D61/ADR-030 altitude debt
  ("per-marker pipeline grows linearly", re-flagged at D94). Consolidates the seams built by
  **ADR 004** (`<<TEST>>`), **ADR 022** (`<<MANIFEST>>`), **ADR 026** (`<<ORT>>`),
  **ADR 043** (`<<ERLEDIGT>>`), **ADR 047** (`<<UHR>>`), **ADR 048** (`<<ZEIT>>`); gated by
  **ADR 046** (`dm-eval` replay — the journal contract this must not move). Touches
  `dmbot/rules/marker.py`, `dmbot/llm/stream_assembler.py`, `dmbot/orchestrator.py`,
  `dmbot/tools/eval_replay.py` (`dmbot/voice/delivery.py` only marginally — see "not
  generalised").

## Context

Six director markers ride the same mechanical pipeline: parse out of the raw LLM answer,
strip before TTS, withhold a partial `<<…` while streaming, queue per channel under the
results-only suppression rule, drain into a validator that confirms or applies. Every seam
was hand-copied per marker: six regex+dataclass+extractor triples in `marker.py`,
`finalize_answer` grown to a 7-tuple (every unpack site changes per marker — twice noted in
ADR 047/048's consequences), a 6-field `StreamResult`, six parallel `_pending_*` dicts in the
brain with six hand-written pop lines at each of four lifecycle seams (redo, streaming redo,
consistency snapshot, reset), six `take_pending_*` methods, and a hand-built journal dict.
D94's open-questions entry says it plainly: consolidate **before** a sixth marker lands,
with `dm-eval` (ADR 046) as the regression gate. That harness now exists; this round uses it.

The per-marker *behaviours* are features, not accidents, and must survive exactly:

| Marker | Suppressed on results-only turn? | Confirm | Per-turn clamp / verdict |
|---|---|---|---|
| `<<TEST>>` | yes (ADR 018 — no roll loops) | dice button (dicecog) | all parsed; profile-driven parse |
| `<<MANIFEST>>` | yes | manifest button (dicecog) | all parsed; profile-driven parse |
| `<<ORT>>` | yes (ADR 026) | `SceneChangeView` under `DM_FLAG_CONFIRM`-independent flow | first request only; `resolve_move` validation |
| `<<ERLEDIGT>>` | yes (ADR 043) | `FlagView` under `DM_FLAG_CONFIRM` | all valid (idempotent); `erledigt_verdict` |
| `<<UHR>>` | **no** (ADR 047 #7) | `ClockView` under `DM_FLAG_CONFIRM` | +1 per clock per turn; `uhr_verdict` |
| `<<ZEIT>>` | **no** (ADR 048 #6) | `ZeitView` under `DM_FLAG_CONFIRM` | first valid only, +12h clamp; `zeit_verdict` |

## Decision

1. **A declarative `MarkerSpec` table in `marker.py`.** `MarkerSpec{kind, keyword, extract,
   needs_profile, suppressible}` — one frozen row per marker, in **canonical order = extraction
   order = journal key order** (`tests`, `manifests`, `scenes`, `erledigt`, `uhr`, `zeit`).
   `kind` doubles as the `history.jsonl` `markers.*` key and the `_pending_<kind>` attribute
   suffix; `extract` is the *existing* per-marker extractor behind a normalised
   `(text, profile) → (clean, requests)` signature; `suppressible=False` encodes the
   UHR/ZEIT exemption from the results-only suppression. The table deliberately does **not**
   carry verdict functions or confirm views (see #5) — those columns live in this ADR as the
   behavioural registry, in code they stay where their authority is.
2. **One generic extraction seam.** `extract_all(text, profile)` runs the specs in table
   order, each exactly as today (same regex sub + `_clean` per marker — byte-identical by
   construction, not by luck), returning `(clean, {kind: [requests]})`.
   `finalize_answer_markers(raw, labels, profile) → (answer, markers)` becomes the canonical
   post-processing seam; the public `finalize_answer` 7-tuple survives as a thin wrapper
   (tests and callers pin it). `StreamAssembler._body` strips via the same spec loop;
   `StreamResult` carries the keyed `markers` dict with `tests`/`manifests`/… as
   back-compat properties.
3. **One keyed pending store in the brain.** `DMBrain._pending: dict[kind, dict[channel,
   list]]` replaces the six parallel dicts; queueing (`_generate` / `_stream_and_store`),
   the four lifecycle drops (redo ×2, consistency snapshot/restore, reset) and the journal's
   `_markers_dict` become single loops over the specs, with the suppression rule read from
   `spec.suppressible` — the exact per-marker semantics of today. The legacy attributes
   (`_pending_uhr` …) remain as live aliases of the inner dicts (a test pokes one directly;
   they also keep debugger views familiar). The six `take_pending_*` methods stay as public
   wrappers over a generic `take_pending(kind, channel)` — dicecog, the delivery handlers
   (whose getattr-guards against stub brains are test-pinned) and dm-eval keep their surface.
4. **Journal contract untouched (ADR 046).** `markers.*` keys, order and per-request dict
   shapes, `*_verdicts`, `lines`/`results`/`notes` are byte-compatible; the committed goldens
   replay green without edits — `uv run dm-eval` is the gate after every migration step.
5. **Deliberately NOT generalised:**
   - **The delivery handlers' bodies** (`_handle_scene`/`_handle_erledigt`/`_handle_uhr`/
     `_handle_zeit`) and the dice/manifest button flow in dicecog. Their differences *are*
     the features: ORT's first-request-only + `resolve_move`, ERLEDIGT's load-bearing
     adventure-guard-before-drain order, UHR's race-recheck + panel update, ZEIT's
     first-valid-only + async apply, four different confirm views and verdict-dict shapes.
     A generic handler would need ~7 injected callbacks per marker — more surface than the
     four explicit methods it replaces. A sixth marker's handler is feature work, not seam tax.
   - **The verdict functions** (`erledigt_verdict`/`uhr_verdict`/`zeit_verdict`) stay pure in
     `delivery.py`, the single source shared by the handlers and dm-eval (ADR 046) — moving
     them into the table would invert the dependency direction (`rules/` must not import
     `voice/`).
   - **TEST/MANIFEST parsing** stays profile-driven and bespoke (difficulty ladder, push);
     the table only normalises the call signature.
6. **Migration order (executed, gated):** table + `extract_all` built beside the existing
   code first; then the finalize/stream seam switched in one step (dense marker unit tests +
   dm-eval's `answer`/`marker` categories cover it); then the pending seams moved one marker
   at a time — ZEIT, UHR, ERLEDIGT, MANIFEST, TEST, ORT last (oldest, most-wired) — with the
   full suite, `ruff --select F` and `dm-eval` green after every step. No big-bang diff.

## Alternatives

- **A `Marker` base class / per-marker strategy objects instead of a table:** rejected — the
  variation between markers is *data* (keyword, profile-need, suppressibility), not
  polymorphic behaviour; the behavioural variety that does exist (validation, confirm, apply)
  lives downstream in the handlers, which this round deliberately keeps concrete. A class
  hierarchy would add indirection at the parse layer without removing a single handler.
- **Generalising the confirm-view dispatch too (one handler, per-spec callbacks):** rejected,
  see Decision #5 — measured against "a sixth marker touches fewer places", the handler is
  the one place that *should* be written by hand, because it is the feature.
- **Changing `finalize_answer` to return the keyed dict directly (drop the 7-tuple):**
  rejected for this round — it would force assertion-preserving churn through ~10 test files
  for zero behaviour gain; the wrapper costs three lines. Revisit if the wrapper ever
  misleads.
- **Keeping the status quo until the sixth marker:** rejected — that is exactly the D94
  entry's failure mode; the seam price was "mechanical but growing" twice in a row, and the
  gate (dm-eval) exists now.

## Consequences

- **+** A sixth marker is: one dataclass + one extractor + one `MarkerSpec` row, plus its
  actual feature (handler/view/verdict) and persona text. `finalize_answer`'s tuple,
  `StreamResult`, the pending store, the four lifecycle seams, the journal dict and dm-eval's
  key list no longer change at all.
- **+** The suppression rule (which markers a results-only turn silences) is now declared in
  one visible place instead of encoded in duplicated `if` blocks in two methods.
- **−** The 7-tuple wrapper and the `_pending_*` alias attributes are permanent back-compat
  surface — small, documented, and cheaper than touching ~10 test files' import/unpack sites.
- **−** Table order is load-bearing (extraction order and journal key order both read from
  it); a careless re-sort would be a byte-level behaviour change. Noted at the table.
- **Behaviour-neutral, verified:** suite green (unchanged assertions), `ruff --select F`
  clean, `uv run dm-eval` exit 0 against the pre-refactor goldens after every step and at the
  end. **No new live gate** — nothing player-visible changed.

## Addendum — detail preserved from decision log D98 (2026-07-11)

- Both delivery paths dispatch the proposal handlers via one labelled
  `_marker_proposal_tasks` list.
- `StreamResult`'s back-compat marker access is implemented via `__getattr__` over the keyed
  dict.
- Test evidence from the round: suite **689 green** (+6 registry tests, 0 changes to existing
  tests).
