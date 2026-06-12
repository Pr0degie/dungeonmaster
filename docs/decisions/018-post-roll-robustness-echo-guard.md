# ADR 018 — Post-roll robustness: echo guard, router-wins dedupe, autosave race fix

- **Status:** Accepted (code-complete; live verification pending)
- **Date:** 2026-06-12
- **Refs:** decision log D43 in `progress.md`; flips the dedupe detail of **D40**; builds on
  **ADR 014** (roll-detection router), **ADR 015/D41** (state split + history autosave),
  **ADR 016** (anti-puppeting backstops — partially rolled back here), **ADR 017** (streaming).
  `architecture.md` §4 (data flow) + §9 (how a test is requested). Suite 142 → 157.

## Context

The 2026-06-12 live session collapsed — "der Bot fühlt sich nicht mehr wie ein Gamemaster an."
The logs (`debug.log`, `history.jsonl`) showed a failure chain, not model regression:

1. **Echo degeneration.** On a post-roll turn the model answered with the *next player line*
   (`Pr0degie: Ich greife den Kultisten an.`) instead of narrating the consequence. The
   leading-label strip (`_strip_leading_label`) silently turned that into a clean-looking echo,
   which was spoken **and stored** — and history-poisoned the session: three consecutive turns the
   DM answered every input with the same parroted sentence, including an elaborate sword attack.
2. **The trigger was a nonsense roll.** The model's inline marker requested
   `<<TEST Heimlichkeit für Pr0degie>>` for an *attack*; under D40 the (unreliable) marker won the
   dedupe over the (validated, nemo 8/8) constrained router. The model then had to narrate a
   stealth result it couldn't make sense of and degenerated. The bare `[Würfel] …` feedback line —
   with no instruction what to do with it — invited line-prediction instead of narration.
3. **D40×D41 race.** A dice click *during playback* (the button is concurrent since D40) starts
   the next turn and overwrites the brain's mutable `_last_turn` before the still-running turn's
   autosave reads it → `history.jsonl` recorded wrong `(user_msg, answer)` pairs, which a later
   restore would re-teach.
4. (Same session, adjacent: the run was in the wrong channel and silently fell back to the
   example party; the cold-start stream died on a 120 s ReadTimeout — both fixed alongside,
   no trade-off worth an ADR section: a loud `!join` warning + party announcement, and a
   generous 300 s read timeout for `chat_stream` only.)

## Decision

**Echo guard (deterministic, in the brain — both paths).** A pure `is_echo(answer, user_msg)`
compares the finalized answer against each player line of the turn (normalized; exact, fragment,
or ≥90%-coverage match; lines under 10 chars never count). On an echo: **retry once** with a
corrective German nudge appended to the prompt (`_ECHO_NUDGE`); if the retry parrots again,
**suppress the turn** — nothing spoken, nothing posted, and the pair **stays out of history**
(an echo in history self-reinforces; that's the poison loop seen live). In the streaming path the
guard runs at `finish()` and only when no sentence was spoken yet (an echo is a short, held-back
single sentence — a half-spoken turn is never retried); the retry is a plain batch call.
`restore_history` additionally skips empty-answer turns, so persisted junk (marker-only or
suppressed turns) isn't re-taught after a crash.

**Roll-feedback directive.** A results-only turn no longer hands the model a bare `[Würfel] …`
line: `_prepare_turn` appends `_ROLL_DIRECTIVE` ("Beschreibe als Spielleitung kurz die Folgen
dieses Würfelergebnisses in der Szene.") — the cheapest fix for the line-prediction failure,
attacking its cause rather than just catching the symptom.

**Router wins the dedupe (flips D40's marker-wins).** When `DM_ROLL_ROUTER=1` (default), inline
`<<TEST>>` requests are still stripped from the text but their buttons are **discarded**
(`roll_button_source` replaces `should_post_router`); the constrained classifier decides. ADR 014
established exactly this reliability gap — letting the marker win contradicted it. Markers remain
the only trigger when the router is off.

**Autosave race fix.** The cog snapshots the turn's `user_msg` at **generation end** (before any
playback await) and passes it to `_autosave_turn(user_msg=…)` explicitly, instead of reading the
brain's mutable `_last_turn` after playback.

**ADR 016 partial rollback.** `DM_NUM_PREDICT` default 160 → **220** and the persona back to
"zwei bis vier Sätze": the squeeze was justified by pre-streaming latency (the table waited
through the whole synth); with streaming (ADR 017) first audio plays after the first sentence
regardless of turn length. The praised sessions ran at 220. ADR 016's *deterministic* backstops
(speaker-label stops, label cuts) stay — they, not the brevity, were the real anti-puppeting fix.

## Alternatives

- **Catch echoes purely via prompt/persona:** the persona already forbids speaking for players;
  nemo ignores soft rules under confusion (the whole ADR 016 lesson). A deterministic detector
  with a retry is model-independent.
- **Suppress without retrying:** cheaper, but a silent DM on a normal action feels broken at the
  table; one nudged retry usually lands (and costs ~2 s on a warm GPU).
- **Always store the turn and filter at restore only:** leaves the live session poisoned — the
  self-reinforcement happened *within* a session, so the pair must stay out of in-memory history.
- **Validate the marker's skill instead of discarding markers:** the engine can't know which
  skill fits an action without exactly the classification the router already does. Router-wins is
  the simpler, already-validated path.

## Consequences

- **Positive:** an echo can no longer reach the table or the history; post-roll turns get an
  explicit narration directive; dice buttons carry router-grade skill choices; `history.jsonl`
  pairs are correct under concurrent dice clicks; richer narration headroom again.
- **Binding:** `roll_button_source` is the dedupe contract (router > marker > none); echo handling
  lives in `DMBrain._generate` / `_stream_and_store` — `respond`/`redo` interpret `None` from
  `_generate` as "suppress, don't store". `_autosave_turn` callers must pass the snapshotted
  `user_msg`.
- **Risk:** a false-positive echo (a legitimate answer that quotes the player nearly verbatim)
  costs one retry; if the retry also matches, a turn goes silent — logged as WARNING both times.
  The ≥90%-coverage rule plus the 10-char floor keeps this rare.
- **To verify live:** post-roll turns narrate consequences (no parroting); an attack action gets a
  combat-skill button (not Heimlichkeit); `history.jsonl` pairs line up after dice clicks during
  playback; `!join` names the party and warns on the example fallback; a cold-start greeting
  survives past 120 s.
