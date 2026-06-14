# ADR 031 — `!intro` opening monologue that involves the player characters

- **Status:** Accepted
- **Date:** 2026-06-14
- **Refs:** decision log D62 in progress.md; builds on ADR 027 (`!start` opening turn /
  auto-recap), ADR 019 (prompt order), ADR 017 (streaming delivery); honours ADR 030's
  "don't duplicate / don't over-generalize" discipline

## Context

The first live round's loudest remaining complaint was that the bot "sagt am Anfang nicht, was
abgeht, und führt nicht durch die Geschichte." ADR 027 already added `!start`: a short (2–4 sentence)
GM-side *director* turn that narrates the mission hook through the existing generate→stream→speak
path. Tobi wants more for *Chemical Burn* — a real **intro sequence** that explains **what's going
on, where the party is, and how they got here, and that involves the player characters**.

Two concrete gaps in the existing opening path blocked that:

1. **The characters never reach the opening prompt.** At `!start`, the only character signal in the
   prompt is the names-as-stop-sequences and the "who plays whom" alias hint. The rich flavour the
   party JSONs carry (`concept`, `origin`, `faction`, `distinguishing`, `goals`, `connections`,
   `arc`, …) lands in `Character.raw` but is never surfaced — so the DM has nothing to involve each
   figure with.
2. **Length is capped for a briefing, not a monologue.** `OPENING_DIRECTOR_MSG` says "2–4 Sätze"
   and the turn runs at the normal `num_predict=220`. An opening that covers place + arrival +
   mission **and** gives every PC a beat does not fit.

## Decision

Add a new **`!intro`** command (aliases `!einleitung`/`!eroeffnung`) that produces **one long
opening monologue** which weaves in **each** player character at **full depth**, by **reusing and
parameterising the existing opening machinery** rather than building a second delivery path:

- A new `CharacterStore.intro_roster_de()` builds a compact German party roster from each
  character's `raw` flavour fields (full depth, tolerant of lean sheets).
- A new pure `build_intro_director_msg(roster_de)` wraps that roster in a `[Regie]` instruction:
  one coherent monologue (place → arrival → mission, from the scene card/summary already in the
  prompt), then a personal beat per named figure — **weave it in, never read private goals/arc
  aloud, only hint** (the same discipline `secrets_de` already uses). The roster rides **inside the
  director (user) message**, so the ADR-019 prompt order is untouched.
- An optional `num_predict` override is threaded through `_build_request`/`_chat_once`/`_generate`/
  `_stream_and_store`/`respond_opening`/`respond_opening_streaming` (default `None` → the brain's
  normal cap, so every existing caller is unchanged). `!intro` passes a larger budget,
  `DM_INTRO_NUM_PREDICT` (default **800**).
- `!intro` mirrors `!start`'s safe scaffolding: deterministic scene-pointer move to `start_scene`
  *only if unset* (golden rule #3 — never resets running progress), dice suppressed (the opening
  path leaves `_last_action` `None`), streamed/spoken via the same pipeline. **`!start` is left
  exactly as the short briefing.**

The three user-facing choices (Tobi, in plan mode): **monologue** over a scripted multi-beat
sequence; a **separate `!intro`** over extending `!start`; **full** figure depth (incl.
goals/connections/arc) over role-only.

## Alternatives

- **Scripted multi-beat sequence** (arrival → mission → per-character spotlights, each a short turn).
  More reliable against nemo-12B's documented rambling/dropping-at-length, and literally a
  "sequence" — but more code (a beat loop + sequencing) and several LLM calls. Rejected per Tobi's
  preference for a single monologue; the risk is mitigated by the existing W4 self-repetition guard
  and is acceptable for a one-time, re-runnable opener.
- **Extend `!start` instead of a new command.** Rejected: Tobi wants to keep the quick briefing as a
  re-runnable option alongside the full intro.
- **Inject the roster as a new system-prompt block** (a parallel to the alias hint). Rejected:
  it would change the shared `_build_request` for *every* turn (prompt bloat, ADR-019 order churn)
  for a one-off need. Embedding it in the one-off director message keeps the change local.
- **A parallel `respond_intro*` + an `intro=` branch in `_deliver_streaming`.** Rejected as
  duplication (ADR 030 discipline): the opening path already carries a director message; adding a
  `num_predict` parameter is the smaller, general change.

## Consequences

- **Positive:** the campaign opener now has a dedicated command that the DM speaks as a coherent
  monologue grounding place/arrival/mission and addressing each PC by name with their own flavour —
  closing the "involve the characters" + "say what's going on at the start" gaps. The character
  flavour is now reachable for opening narration without touching per-turn prompts. Suite **300
  green** (293 → 300; +7 fixed/unit tests in `tests/test_intro.py`). Existing behaviour is untouched
  (`num_predict` defaults to `None` everywhere; `!start` unchanged).
- **Negative / to watch:** a single long turn leans into nemo-12B's weak spots (rambling,
  repetition, possibly skipping a figure with a large party). Watch the live run; if it frays, the
  fallback is the rejected multi-beat sequence or a lower `DM_INTRO_NUM_PREDICT`. Large parties make
  the embedded roster (full depth) sizeable — fine under `num_ctx=24576`, but a very large table
  could pressure the budget (cap fields or depth then).
- **Live-unverified:** `!join` → `!intro` in Discord must confirm the DM speaks one monologue that
  names place/mission/arrival and involves each PC, with no dice prompt and no verbatim private
  goals — recorded as the open gate in `progress.md`.
- **Experimental B-variant (2026-06-14, same session):** `!intro test` keeps the *same* generated
  monologue but changes the **delivery** — batch-generate the whole text, then `chunk_text` it and
  speak the chunks **sequentially with a short pause** (`_INTRO_CHUNK_PAUSE_S`) instead of the
  seamless streamed read. It is **not** the rejected multi-beat sequence (still one generation, one
  director turn); it's a delivery-feel A/B (`_deliver_intro_chunked`). Kept behind the `test` arg so
  the default `!intro` is unchanged; if it doesn't earn its keep after the live test, delete the arg
  + helper.
- **Binds:** the `num_predict`-override parameter is now the way to vary a single turn's length cap;
  future opening/length work should reuse it rather than add per-call length state. The intro roster
  reads `Character.raw` flavour keys — keep `intro_roster_de`'s key list in step if the character
  schema's flavour fields change.
