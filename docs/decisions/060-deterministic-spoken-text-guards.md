# ADR 060 — Deterministic guards on the spoken text: two signals, negative cases first

- **Status:** Accepted (implemented in D112/D113/D114; the next debug run is the live verification)
- **Date:** 2026-08-23
- **Refs:** generalises three rounds that each hit the same wall — **D112** (assistant register and
  handover stage directions), **D113** (the DM speaking for player characters, reversing the
  deferral in **D110**), **D114** (Whisper's outro hallucinations). Sits beside **ADR 045** (the
  consistency guard) and **ADR 034** (the pure `llm/` helpers the filters live in). Lessons:
  `deterministic-guards-over-persona-hopes`, `spoken-audio-cannot-be-retracted`,
  `optional-layers-fail-open-core-fails-loud`. Plan: `docs/plans/coherent-campaign-run.md`.

## Context

The live run of 2026-08-22 spoke four kinds of non-fiction to the table: an assistant apologising
in the formal register, a director frame read aloud, a handover stage direction closing almost
every answer, and the players' own characters given lines they never said. A fifth arrived from the
other direction — Whisper transcribed YouTube outro boilerplate as player speech, six times, twice
routed straight at the DM where it became the group's next declared action.

All five were already forbidden or guarded in the obvious place. The persona forbids the first
four in plain German. The STT guard drops low-confidence segments. Neither held: a 12B model does
not obey a prose prohibition reliably, and a *fluently generated* stock phrase scores **high**
confidence, so the threshold never sees it.

The first instinct each time was the cheap one — sharpen the wording, raise the threshold. It
failed each time, which is what `deterministic-guards-over-persona-hopes` already says. What the
three rounds added is the harder half: *how* to write a deterministic guard on natural-language
text without it eating the game. A filter that removes real narration or real player speech costs
far more than the tic it removes, and the damage is invisible — nobody can tell what was silently
deleted from a sentence they never heard.

## Decision

Guards on the spoken text follow one shape, applied identically in `llm/sanitize.py` and
`stt/segments.py`:

1. **Two independent signals must coincide.** Never act on one. Puppeting needs quoted speech *and*
   an attribution to a player. A handover needs a handover verb *and* a handover object, so "Damit
   endet die Schicht im Hafenbecken" survives while "Damit endet dein Zug" does not. A hallucination
   needs the phrase to match *and* nothing else to remain in the utterance.
2. **Whole units only, never part of a sentence.** A guard removes an entire sentence (or the whole
   utterance) or nothing. Cutting inside a sentence leaves dangling quotes and half-thoughts, and
   makes the damage unreadable after the fact.
3. **A quote is sanctuary.** A sentence carrying a quote character is skipped by the register
   filters: an NSC may apologise, ask formally or say it is waiting, and that is the fiction.
4. **Never strip a turn to nothing** — with one deliberate exception. Silence after someone pressed
   the mic reads as a broken bot. The meta filter is the exception, because an answer that is
   *entirely* assistant register has nothing worth keeping; it collapses to one neutral GM line that
   preserves the model's intent and drops only the register.
5. **The negative cases are written first.** Roughly half of every guard's tests exist to prove what
   it must *not* touch, drawn from real table talk. A guard without them is a liability.
6. **Guard on the seam the table actually hears.** Live sessions run streamed, so a filter applied
   only to the batch path is decorative — spoken audio cannot be retracted. Filters run on the
   incremental view too, where they may only judge *complete* sentences, and where a sentence that
   is dropped must stay dropped (the assembler tracks spoken sentences by index).
7. **A block that fires is visible.** A content-blocked hallucination logs at INFO. A guard nobody
   can see fire cannot be verified at the table, and an unverifiable guard rots.

## Alternatives

- **Prompt-only, keep measuring:** what D110 chose and D113 reversed on Tobi's instruction. Still
  the right *first* move — the D107 prompt fix removed a genuine self-contradiction — but a rule the
  table cares about cannot rest on a 12B model's compliance.
- **Regenerate the turn instead of cutting** (what ADR 045 does for the consistency guard): rejected
  as the primary mechanism here. It is strictly better for quality, but in streaming mode the
  opening sentences are already spoken, and these tics are frequent enough that regenerating each
  time would add a second generation to a large share of turns.
- **An LLM judge over the answer:** rejected. It adds a call per turn to police the output of the
  same model, and it fails in exactly the situations where the model is already failing.
- **Configurable blocklists in `.env`:** rejected for D114. A curated in-code list is reviewable in
  the diff and cannot silently rot in an operator's environment file, which is the failure
  `unwired-knobs-and-silent-fallbacks` describes.
- **Substring matching anywhere in the text** (instead of whole units): rejected — it is what makes
  a filter eat legitimate speech, and it cannot be reasoned about from the outside.

## Consequences

- **+** Four recurring tics that reached the table on 2026-08-22 cannot reach it again, and the
  fifth (hallucinated player speech) cannot enter the DM's buffer.
- **+** A shape for the next one. The next tic found live gets a filter of the same form rather than
  a fresh invention, and the review knows what to check.
- **−** German-language regexes are a maintenance surface. They are dialect- and wording-specific
  and will need entries added as new tics appear; the tests double as the documentation of what is
  covered.
- **−** Each guard can, in principle, still eat something real. The two-signal rule and the negative
  tests make it unlikely, not impossible, and the failure is silent by nature. The mitigation is
  cheap and must stay: whenever the table says "it swallowed something", the sentence goes into the
  test file as a negative case.
- **−** Streaming and batch can disagree on a sentence at the moment it completes. That divergence
  already has machinery (the assembler speaks the canonical remainder) and is logged.
