# Measure a persona change on replayed turns

**What a persona sentence does to the spoken text is not what its wording says. Before a change
to turn or sentence length goes to the table, send the same recorded turns through the narration
model with the old and the new text and read the numbers.**

## What happened

After the evening of 2026-11-14 the persona was changed to make turns shorter and denser (D141:
"long sentences are allowed", "at most about half a minute"). Replayed on six turns of that
evening, the changed persona produced the *longest* turns of all three states measured (656
characters on average against 565, up to 807), and the half-minute sentence had no effect. The
same replay showed that the persona of the earlier, better-liked run gave the same text as the
evening's — the persona had not been the cause at all
(`docs/plans/textvergleich-2026-11-14.md`).

A second measurement compared two wordings: dropping "long sentences are allowed" changed
nothing (153 characters per sentence); a limit per sentence ("no sentence over about twenty
words") brought 100 characters per sentence — and more sentences, so the turns did not get
shorter. Sentence length and turn length are two rules, not one.

## The correction

`uv run python -m dmbot.tools.text_replay run <label>=<persona file>`: six calls per variant,
numbers for characters per turn, per sentence and cuts. A persona change that is meant to alter
the shape of a turn is measured this way first; the live run then checks how it sounds.

## Why it matters

A live session is scarce (`one-variable-per-live-run`), and a table cannot tell a persona effect
from scatter. One sample per turn is scatter too: differences of a few dozen characters between
variants mean nothing.
