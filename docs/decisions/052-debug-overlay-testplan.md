# ADR 052 — Deterministic 🧪 debug overlay from a `testplan.json` sidecar

- **Status:** Accepted
- **Date:** 2026-07-11
- **Refs:** decision log **D99** in progress.md. Rides the scene-change seam of **ADR 026**
  (`<<ORT>>` / `!ort`) and reuses the edit-in-place panel pattern of **ADR 047** (clock
  panel). Sidecar sits next to the **ADR 019/043** adventure compendium but is deliberately
  NOT part of it. Dev tooling — no new live gate; its verification is a side effect of the
  debug-campaign run it exists for.

## Context

Eight live gates are stacked into one scripted live run (`docs/live-run-script.md`). A
dedicated **debug campaign** should let testers walk scene by scene and trigger each gate —
but testers at the table need to know *what to trigger where*, without anyone alt-tabbing
into the gate register. The obvious hazard: any test guidance that reaches the DM's prompt
breaks immersion (the DM would narrate around "tests") and burns tokens. Constraints, in
priority order: (1) **immersion is sacred** — the LLM must never learn a test run is
happening; (2) a compact per-scene hint in Discord; (3) fail-open + kill-switch; (4) zero
LLM calls, zero prompt bytes.

## Decision

A deterministic OOC overlay driven by an optional sidecar, invisible to the LLM **by
construction**:

1. **Sidecar contract.** `testplan.json` next to `adventure.json`:
   `{"scenes": {"<scene-id>": {"gates": ["G4 Gated Exit", …], "hint_de": "one line"}}}`.
   Parsed by the new pure module `dmbot/rag/testplan.py` (`Testplan.load`, fail-open:
   missing → silently dormant; malformed → ONE loud log line, then dormant).
2. **LLM-invisibility by construction.** The sidecar is loaded in `SessionRuntime.__init__`
   next to — but never into — the `Adventure` object, so no prompt/persona/RAG path can
   even reach it. Pinned by a source-inspection test: no prompt-building module
   (orchestrator, prompt_assembly, director_msgs, adventure loader) may mention the
   testplan (`tests/test_debug_overlay.py`).
3. **Rendering.** `SessionRuntime.update_debug_overlay()` posts/edits ONE compact
   🧪-prefixed message (current scene, gates under test, hint) — edit-in-place per the
   clock-panel pattern, so a session is one message, not a scroll of spam. Scenes absent
   from the plan render "keine Gates in dieser Szene" so testers know to move on.
   Refreshed by every scene-change path: `!ort`, the confirmed `<<ORT>>` click, the
   `!start`/`!intro` start-scene seed, and `!join` (a loaded session may already sit in a
   scene). `!leave` clears the panel like the other panels.
4. **Fail-open + kill-switch.** `DM_DEBUG_OVERLAY=0` skips even the sidecar load (existing
   kill-switch conventions). Optional `DM_DEBUG_CHANNEL=<id>` posts the overlay to a
   separate channel (keeps OOC chatter out of play); an unresolvable id logs once and falls
   back to the game channel. Send/edit failures log and never break a turn. Stub runtimes
   in tests stay dormant via the pinned getattr-guard pattern.
5. **Token economy — the whole point.** Zero LLM calls, zero prompt bytes, zero latency on
   the turn path. The DM narrates a completely normal game; only the humans see the 🧪 line.

## Alternatives

- **Gates/hints inside `adventure.json`:** rejected — the adventure object feeds
  `adventure_block_de` into every prompt; test metadata one field away from the prompt path
  is exactly the leak invariant (1) forbids. A separate file a separate loader reads makes
  the leak structurally impossible, not just avoided.
- **A `!testplan` command instead of automatic posts:** rejected — testers would have to
  remember to ask after every move; the value is the hint arriving *with* the scene change.
  (The panel is idempotent; a manual command can be added later if live use wants it.)
- **One new message per scene change instead of edit-in-place:** workable, but ADR 047's
  panel pattern was cheap to reuse (same handle + fallback logic) and keeps the channel
  readable over a multi-hour test run.
- **Log-file-only guidance:** rejected — testers at the table are in Discord, not tailing
  logs; the Discord line is the feature.

## Consequences

- **+** The debug campaign becomes self-guiding: walk the scenes, do what the 🧪 line says,
  tick gates off. Normal adventures pay nothing (no sidecar → one `is_file()` check).
- **+** The invisibility invariant is test-pinned, not convention-pinned — a future change
  that imports the testplan into a prompt module fails the suite.
- **−** One more panel handle on the runtime (`_debug_panel`) and a fifth entry in the
  `!leave` clear list.
- **Next:** a content round authors the debug campaign (adventure + `testplan.json` filling
  this contract); the overlay's live verification rides that run — deliberately NOT a new
  entry in the live-gate register.
