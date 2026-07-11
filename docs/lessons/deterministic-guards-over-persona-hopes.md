# Deterministic guards over persona hopes

**A prompt/persona instruction is not a reliable lever on a 12B model — every recurring
misbehaviour was fixed by a deterministic code guard; the prompt only shapes, code owns removal.**

## What happened

The same shape, rediscovered in at least six independent rounds:

- Puppeting player characters survived three live sessions of persona fixes — the persona
  *already forbade it* (D37 → ADR 016; fix: speaker-label truncation + stop sequences).
- Echo loops ignored the soft rules under confusion (D43 → ADR 018; fix: `is_echo` guard).
- Live repetitions dodged the prompt rule (D45; fix: fuzzy `is_self_repetition`).
- The meta-preamble tic survived a hardened brief AND low temperature (D84/D86 → ADR 041
  addenda; fix: deterministic strip in `sanitize.py`).
- Scene-card contradictions were ignored often enough to break immersion (D92 → ADR 045;
  fix: pure-code consistency guard — explicitly *not* an LLM judge).

## The correction

Treat persona edits as hypotheses. First check whether the instruction already exists —
usually it does, and the model ignored it. When a tic survives one live session, move the
fix into code: sanitizer strip, Ollama stop sequence, pure predicate + one bounded retry,
marker suppression. Keep the prompt bullet only as best-effort shaping. ADR 041 states the
division: deterministic post-processing owns *removing* the tic (guaranteed); brief +
temperature own *shaping* the prose (best-effort).

## Why it matters

Each new failure looks like a wording problem ("just tell it not to"), so the cheap-looking
prompt edit is always the first instinct — and it fails the same way every time. Golden
rules #2/#3 in CLAUDE.md are the two hard-wired instances of this principle; this lesson is
the general case. See also [[mandatory-decisions-need-a-separate-classifier]].
