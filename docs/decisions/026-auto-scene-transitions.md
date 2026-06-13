# ADR 026 — Automatic scene transitions (`<<ORT …>>` marker + confirm button)

- **Status:** Accepted
- **Date:** 2026-06-13
- **Refs:** supersedes the "moved by humans only" binding of **ADR 020** (filename
  `020-adventure-scene-tracker-hybrid.md`; note its internal title still reads "ADR 019" — an
  off-by-one between filename and header); builds on **ADR 004** (dice/marker pattern) and **ADR 022**
  (the `<<MANIFEST>>` precedent — a second code-validated marker); golden rules #2 (dice = code) and
  #3 (no hard state from LLM free text).

## Context

The scene pointer (`state.scene_id`, ADR 015) is moved by `!ort <id>`: a manual, human-only command.
ADR 020 (the scene-tracker hybrid) made that binding explicit — "the scene pointer is moved by humans
only" — to keep the narrator LLM clear of hard state (golden rule #3: the LLM never writes hard state).

In live voice play, typing `!ort` mid-scene is friction: it pulls a player out of the conversation to
type a command the moment the party walks somewhere. ADR 020 anticipated this and **explicitly
deferred** the next step — "a director LLM moves the scene pointer … re-evaluate once live play shows
`!ort` friction." Live play has now shown it. This ADR takes that step.

The constraint is the same one ADR 020 protected: the LLM must not become an authority on hard state.

## Decision

Add a **third LLM marker `<<ORT <scene-id>>>`**, mirroring `<<TEST>>` (ADR 004) and `<<MANIFEST>>`
(ADR 022). The model **requests** a move; code does the rest:

- **Parse + strip.** Code parses the marker and strips it from the text before TTS — it is never
  spoken, inherited from the shared `<<…>>` strip/withhold guards (same protection as the other two
  markers).
- **Validate.** The target id is checked against the adventure. Two switchable **target modes**:
  - **`verbunden` (DEFAULT):** only the current scene's `leads_to` neighbours are accepted. Illegal or
    unknown ids are **ignored and logged**, never moved.
  - **`frei`:** any known scene id is accepted.
  The default comes from `DM_SCENE_MODE`; switchable at runtime via `!ortmodus [verbunden|frei]`.
- **Confirm, then move.** A valid request posts a `SceneChangeView` button in the channel. On a **human
  confirm**, code runs the **same deterministic move `!ort` already does** (`_set_scene`: set
  `state.scene_id`, sync the location, persist, rebuild the prompt scene card). The human stays in the
  loop; the DM just keeps narrating.
- **Manual `!ort` remains** as the override / undo.

**This upholds golden rule #3, it does not break it.** The LLM still never *writes* hard state — it
emits a *validated request*, exactly as it *requests* a die roll (golden rule #2) rather than rolling
it. The engine, not the model, performs the move. The only thing reversed is ADR 020's "moved by
humans only" binding: the pointer is now moved **by code, on a validated, human-confirmed model
request** — not by free LLM text.

## Alternatives

- **Keep `!ort` manual-only (ADR 020 as-is).** Lowest risk, but the friction ADR 020 itself flagged
  for re-evaluation is now real. Rejected for that reason.
- **Auto-apply the move without a confirm button.** Removes friction entirely but hands the pointer to
  the model with no human gate — too close to letting the LLM write hard state. Rejected; the confirm
  button is the human-in-the-loop guarantee.
- **A separate director LLM call to decide moves.** Heavier (extra latency, a second model pass) than
  reusing the narration the model already produces; the in-band marker rides the existing turn. Rejected
  for the MVP — the marker is the cheap form of ADR 020's "director LLM" idea.
- **`frei` mode as the default.** Drops the `leads_to` authorisation boundary and invites teleport
  jumps from a stray id. `verbunden` is the safe default; `frei` stays available for GM convenience.

## Consequences

- **Positive:** the party can walk somewhere and the DM offers the move inline — no `!ort` typing
  mid-scene — while a human still confirms every pointer change and the engine still owns the move.
- **Binding:**
  - `leads_to` is the **authorisation boundary** in the default mode; illegal/unknown ids are
    **ignored + logged**, never moved.
  - A move is queued only under the existing **post-roll loop-guard** — a results-only consequence turn
    (the `_last_action` guard) must not trigger a move.
  - `DM_SCENE_MODE` defaults to **`verbunden`**; `!ortmodus` switches it at runtime.
  - Manual `!ort` is the **override**.
  - The marker must keep the shared `<<…>>` delimiter so the strip/withhold TTS guard applies — do
    **not** use a different delimiter.
- **Risk register:**
  - **(a) Spurious markers** when players merely mention a location — bounded by the persona wording
    ("nur wenn die Gruppe ihn wirklich betritt"), the `leads_to` gate, and the confirm button.
  - **(b) Move-loops** — bounded by reusing the `_last_action` post-roll guard (a results-only turn
    can't move the pointer).
  - **(c) TTS leakage of the marker** — inherited from the `<<…>>` strip/withhold guards; **do not**
    use a different delimiter or that protection is lost.
- **To verify live:** the party enters a connected location, the DM ends the turn with `<<ORT …>>`
  (not spoken), a confirm button appears, and confirming moves the pointer exactly as `!ort` would; an
  invented or non-neighbour id in `verbunden` mode is ignored and logged, not moved.
