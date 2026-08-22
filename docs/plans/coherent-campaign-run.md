# PRD — A coherent debug-campaign run

**Status:** specified, not built · **Date:** 2026-08-23 · **Round:** D107
**Source:** the live debug-campaign run of 2026-08-22 (4 players, 22 turns, ~33 min),
root-caused into 76 findings across seven code areas, then narrowed to 20 decisions in five
question rounds with Tobi.
**Governing ADRs:** 019/026 (scene pointer), 034 (extracted LLM helpers), 035 (delivery),
038 (prompt assembly order), 043 (stateful scene cards), 044 (NPC memory), 045 (consistency
guard), 046 (replay eval), 047 (clocks), 048 (in-game time), 049 (NPC agendas), 050 (Chekhov),
051 (marker registry), 052 (debug overlay), 055/056 (debug sandbox).
**New ADRs from this round:** 057 (deterministic scene advancement), 058 (post-turn fact
classifier), 059 (adventure-seeded time, deadlines and clocks).

---

## Problem Statement

The debug campaign exists so that a play session can *prove* the DM works. On 2026-08-22 it
proved the opposite, and the evening cost four people 33 minutes.

**From the players' side.** Nobody knew what the mission object was after 25 minutes — asked
directly, the DM answered "das Ossarium ist ein heiliger Schrein", a tautology. One NPC did
almost all the talking and repeated the same clock-checking line in eight of ten answers. The
DM spoke *for* the player characters, gave them dialogue and motives nobody had declared, and
addressed everyone as if they were one person — by Discord name, not character name. A customs
warrant handed over in turn 7 did not exist in turn 16. The NPC who left in turn 4 was leading
the group through the same room in turn 21. The opening two paragraphs were unintelligible to
anyone without Warhammer 40,000 knowledge, so a *human player* had to stop the game and lecture
the table on the setting for two minutes. And the speech itself hacked at the seams instead of
reading sentence by sentence.

**From the operator's side.** The evening was supposed to walk the table through six scenes
while the chat displayed what was being tested. Neither happened. The run never left scene one.

**The single mechanical cause.** Everything that would have carried the evening hangs off one
link — the scene change — and that link can only be pulled by an inline `<<ORT>>` marker the
model must emit at the end of its answer. In 22 turns it fired zero times, and it structurally
almost cannot: the marker belongs at the end of the text, which is exactly where the 220-token
ceiling and the stop-label cut destroy it. Downstream of that dead link sit the test overlay,
the in-game clock, the deadlines, the NPC agendas, the recap, the NPC memory, the Chekhov
threads, five of six scenes and seven of eight NPCs. This is the failure mode
`docs/lessons/mandatory-decisions-need-a-separate-classifier.md` already describes: a mandatory
decision was left to an inline marker.

**A second cause, independent of the model.** The bot ran in its default speech mode, `stream`
+ `flach`. That default is documented as the sensible choice *on CPU*: fast first audio, and
all punctuation stripped so XTTS cannot babble. This run had XTTS on **cuda**, synthesising
2–3.5× faster than realtime. So the table paid the CPU default's price — seams between streamed
chunks, and no punctuation for XTTS to derive sentence-final intonation from — on hardware that
no longer needs it.

---

## Solution

Move every decision that the campaign depends on out of the model's optional inline markers and
into code, keep the model doing what it is good at (prose), and put the campaign's own facts
where they are visible: in the prompt, in the world state, and on a panel the table can read.

Four blocks, in the order the table experiences them:

1. **Speech and entry.** Compare the three speech modes at the table and settle a default that
   fits GPU synthesis. Give the campaign a spoken plain-language opening before the atmosphere
   prose, so a newcomer knows who they are and what they want.
2. **Scene advancement and the player panel.** A dedicated constrained-JSON classifier after
   each turn decides whether the group actually entered one of the current scene's real exits;
   a flag gate advances the scene once its opportunities are all resolved. Advancement is
   automatic with a one-minute undo. A persistent, self-updating panel shows the table the
   scene, the goal, the time, the deadline and what is still open here.
3. **NPC life.** The roleplaying notes the campaign already carries reach the prompt, and the
   NPCs present in a scene get registered in the world state — which switches on NPC memory,
   agendas and the consistency guard for the first time. The scene's standing GM guidance stops
   being repeated every single turn.
4. **Identity and hard facts.** A player's line reaches the prompt under their *character* name,
   resolved from the Discord user id. A second post-turn classifier turns narrated commitments —
   an item handed over, a quest accepted, a promise made — into hard world-state facts.

The load-bearing principle stays the one from golden rule #2, extended from dice to plot: **the
model requests, code decides and records.** No new mechanism asks the model to remember
something across turns.

---

## User Stories

**Speech and comprehension**

1. As a player, I want the DM to read sentence by sentence without audible seams, so that I can
   follow a long answer instead of losing the thread at every join.
2. As a player, I want punctuation to survive into the speech, so that questions sound like
   questions and sentences end instead of running together.
3. As the operator, I want to compare the three speech modes on the same answer at the table, so
   that the default is chosen with ears and not from a config comment written for other hardware.
4. As a player new to the setting, I want the DM to tell me in plain language who we are, what we
   want and what happens at midnight *before* the atmosphere prose starts, so that I do not need
   another player to explain the universe to me.
5. As a player, I want the mission object described concretely at least once, so that "get the
   Ossarium back" means something I can picture.
6. As the operator, I want the DM voice to be the one I configured, so that a stray environment
   value cannot silently substitute a random speaker.

**Scene advancement**

7. As a player, I want the world to move when we leave a place, so that the DM stops narrating a
   harbour while insisting we are still in the customs sacristy.
8. As a player, I want the DM to know which places we can actually reach from here, so that going
   "to the harbour" leads somewhere real instead of into improvisation.
9. As a player, I want a scene we have exhausted to hand us onward, so that we do not keep
   squeezing a room that has nothing left in it.
10. As a player, I want a wrong scene change to be undoable within a minute, so that a
    misjudgement costs one click and not the evening.
11. As the operator, I want a rejected scene change to be visible and to reach the model as a
    correction, so that an invalid move is not silently swallowed by a log line.
12. As the operator, I want the scene's exits rendered with their titles, not bare ids, so that
    the model can connect "the harbour" to an actual destination.
13. As the author of a campaign, I want the first scene to point at the place the players can
    actually go next, so that the only permitted move is also the one the fiction suggests.

**The player panel**

14. As a player, I want a panel that always shows where we are, what we want, whose turn it is,
    what time it is in the fiction and how long we have, so that I never have to ask "what is our
    mission again?".
15. As a player, I want to see what is still open in this scene, so that the group has something
    to aim at.
16. As the operator, I want the test points shown in players' language, so that the table takes
    part in the test instead of me reading a command cheat sheet to myself.
17. As the operator, I want the panel to update itself in place and stay reachable, so that it
    does not scroll out of the channel after the first post.

**NPC life**

18. As a player, I want NPCs to have a manner of speaking, so that the customs seneschal is a
    character and not a clock-checking phrase generator.
19. As a player, I want to meet more than one NPC, so that a scene with three named people is not
    played as a monologue.
20. As a player, I want an NPC to remember what we told them, so that lying to one and meeting
    their contact later means something.
21. As the operator, I want the NPCs present in a scene registered as world-state facts, so that
    NPC memory, agendas and the consistency guard finally have data to work on.
22. As the operator, I want the scene's standing guidance injected as an impulse rather than a
    standing order, so that "keep the deadline in view" does not become the same sentence in
    every answer.

**Identity and hard facts**

23. As a player, I want the DM to address me by my character's name, so that four players are not
    treated as one.
24. As the operator, I want the player's identity resolved from the Discord user id rather than
    from a display name the model has to map itself, so that a nickname change cannot break it.
25. As a player, I want an item the DM handed me to stay handed over, so that a won social test is
    not silently reversed nine turns later.
26. As a player, I want our accepted mission to be a fact the DM cannot forget, so that the
    campaign has a spine.
27. As the operator, I want the consistency guard to actually run, so that contradictions are
    caught before they are spoken.

**Time and pressure**

28. As a player, I want the in-game clock to match the fiction, so that a night before midnight
    does not read as eight in the morning.
29. As a player, I want the deadline to come closer as we play, so that the pressure is real
    instead of an NPC repeating that time is short.
30. As the author of a campaign, I want to ship the start time, the deadlines and the clocks with
    the adventure, so that the operator does not have to type them in from memory.

**The test evening itself**

31. As the operator, I want the run to leave a replayable record, so that a bad evening becomes a
    regression test instead of an anecdote.
32. As the operator, I want each new mechanism individually switchable, so that one misfiring
    feature does not end the session.
33. As a player, I want the DM to stop speaking my character's lines, so that my character stays
    mine.

---

## Implementation Decisions

### Scene advancement (ADR 057)

- **A dedicated post-turn classifier, not an inline marker.** After each turn a stateless
  constrained-JSON call — same shape as the roll router, which is the one LLM-driven decision
  that demonstrably works — is asked a single question: did the group actually enter one of
  these places? Its answer space is exactly the current scene's reachable exits plus "no". The
  inline `<<ORT>>` marker stays as a fallback, demoted from primary mechanism to opportunistic
  hint.
- **A flag gate as the second trigger.** When every opportunity of the current scene is
  resolved, code advances the scene without consulting the model at all.
- **Opportunity ids become mandatory campaign data.** The flag gate needs something to count.
  Every opportunity in every scene gets a stable id; today exactly one of seventeen has one.
  The loader treats an opportunity without an id as a content error, so this cannot silently
  half-work again.
- **Automatic with undo.** The scene changes immediately and the channel says so; an undo
  control stays live for about a minute and restores the previous pointer, scene time and
  overlay state. No pre-confirmation.
- **A rejected move is loud.** An invalid or unreachable target produces a director note for the
  following turn naming the reachable exits, plus an operator-visible line. It never disappears
  into a log-only path.
- **Exits render with titles.** The scene block names each exit as `id — title`, so the model can
  map a fictional direction onto a real destination.

### Speech delivery

- **No new mechanism first.** The existing speech-mode axis (`stream` / `puffer` / `nahtlos`)
  and punctuation axis (`flach` / `intoniert`) already cover the complaint. The deliverable is a
  short table-side comparison procedure — the same answer spoken in three modes — after which the
  default is set from what was heard. The measured GPU synthesis rate (2–3.5× realtime) is what
  makes the gapless mode affordable at all; it is recorded here so the decision is not re-derived.
- **Answer length is explicitly not a problem.** No seconds budget, no barge-in, no shortening.
  The table wants to hear what is going on. This closes the "156-second monologue" finding as
  *working as intended*.
- **The speaker configuration must fail loudly.** An unknown speaker value currently degrades to a
  random voice behind a warning line; it becomes a startup preflight failure like the other
  external-state checks.

### NPC presence

- **The roleplaying notes reach the prompt.** Each campaign NPC already carries a role and
  roleplaying notes; today nothing in the codebase reads them. The scene block renders, for each
  NPC present, name, role and manner. This is a rendering change: no new state, no extra call.
- **NPCs present are registered as world-state facts on scene entry.** This is what switches on
  NPC memory, agendas and the consistency guard, none of which have ever run.
- **Known trap:** the consistency guard treats speech by an NPC not registered as present as a
  violation. Registering only the scene's listed NPCs would therefore cement the cast and make
  every incidental figure — a runner, a bystander — a violation. Registration must mark scene
  NPCs as *present* while leaving room for unnamed incidental figures, or the guard's presence
  check must be scoped to named campaign NPCs only. This is a correctness precondition, not a
  refinement.
- **Standing guidance becomes an impulse.** The scene's GM guidance is injected periodically or
  on a stalled scene rather than in every turn's prompt.

### Identity

- **Character name at the source.** A player utterance enters the prompt under the character
  name, resolved from the Discord user id through the existing alias mapping. The prompt-level
  hint that asks the model to do this mapping itself is removed once the resolution is real.
  This is ADR 003's turn-taking identity, finally implemented.
- **Deliberately out of this round:** the dice button stays identity-agnostic and the roll router
  keeps classifying the last buffered line. Consequence, accepted knowingly: a test can still be
  rolled for the wrong character when several players speak in one turn.

### Hard facts (ADR 058)

- **A second post-turn classifier** extracts commitments from the turn just narrated: an item
  handed over, a quest accepted, a promise given. Its output is validated against the world-state
  schema and written as hard facts, which then appear in every subsequent prompt. It runs
  alongside the scene classifier on the same turn boundary.
- **The mission becomes a hard fact.** The adventure's objective is seeded as a quest at session
  start rather than living only in narration, and it is what the player panel displays as the
  goal.
- **Golden rule #3 is preserved by shape, not by trust:** the classifier's output is a constrained
  enumeration validated by code, not free text parsed into state.

### Time, deadlines and clocks (ADR 059)

- **The adventure ships its own clock.** Start time, deadlines and consequence clocks are campaign
  data, seeded at session start.
- **Time advances per turn.** Each turn costs a small fixed amount of in-game time, a scene change
  more. The `<<ZEIT>>` marker remains for deliberate jumps.
- **The deadline is visible** on the player panel, not only in an NPC's dialogue.

### Prompt and persona

- **Resolve the self-contradiction first.** The intro director currently asks for a moment per
  player character — exactly what the persona forbids three blocks earlier. That contradiction is
  removed and the prohibition sharpened with an example.
- **Then measure, do not filter.** No puppeting filter this round. The next run counts how often
  it still happens; a filter is only justified if the sharpened prompt fails. This is a
  deliberate, evidence-first exception to
  `docs/lessons/deterministic-guards-over-persona-hopes.md`, taken with the lesson in view.
- **Meta-sentence removal stays open.** "Es tut mir leid, aber ich kann Ihre Frage nicht
  verstehen" and "In diesem Fall würde ich als Spielleitung antworten:" were read aloud; no
  deterministic filter covers them. Not decided this round.
- **The scene description must not read as finished narration.** Today the card's description sits
  unlabelled in the prompt as ready-made prose and was recited verbatim; it is labelled as
  reference material.

### Kill switches

Each of the four blocks is individually switchable at the table, so a misbehaving mechanism costs
a command and not the session.

---

## Testing Decisions

**The seam is the pure function.** Every new decision is expressed as a pure function taking
explicit inputs and returning a verdict, tested with fixed seeds and exact expected values — the
established pattern of the rules and game-time tests. Concretely:

- **Exit resolution:** given a scene, a set of resolved flags and a proposed target, return
  permitted / rejected-with-reason. Table-driven: unknown id, non-neighbour, locked gate whose
  requirement is unmet, locked gate whose requirement is met, valid neighbour.
- **Flag gate:** given a scene and the resolved flags, return whether the scene is exhausted.
  Requires the opportunity ids, so the loader's id validation is tested alongside — including the
  negative case that a campaign missing ids fails to load rather than loading half-broken.
- **Fact extraction:** given a classifier verdict, return the world-state mutation. The LLM call
  itself is not under test; its *output contract* is. Malformed, out-of-enum and empty verdicts
  must all degrade without touching state.
- **Panel rendering:** given a world state, scene and testplan, return the panel text. Pure and
  fully assertable, including the "nothing open here" and "no deadline" cases.
- **Time advancement:** per-turn increment, scene-change increment, deadline crossing, and the
  seeded start time — extending the existing game-time tests.
- **Chunking and speech text:** whatever changes in the spoken-text path gets asserted on exact
  output strings, since this is where a silent regression is inaudible until the table hears it.

**Regression at the evening level.** The next debug run is recorded and becomes a golden replay
for the existing eval harness, so "the DM never left scene one" is a failing test rather than a
memory. The 2026-08-22 run itself cannot serve as one — it happened on another machine and left
no session artifacts here.

**Not covered by tests, explicitly.** Whether the speech sounds better, whether the opening is
comprehensible, and whether the model still speaks for player characters are live-verification
gates. They are named as such rather than approximated in the suite.

**Live gates opened by this round.** Scene advancement, the player panel, adventure-seeded time,
NPC registration, character-name identity, fact extraction, and the speech-mode comparison. The
repository's WIP limit of three open gates is explicitly overridden for this round, on Tobi's
instruction: the ten pre-existing gates are already stacked onto the same next evening, and
without these fixes that evening would be unusable again.

---

## Out of Scope

- **Shortening answers, seconds budgets, barge-in.** Length is wanted. Barge-in would additionally
  require a stop endpoint in Bot A's repository, which two-bot isolation puts off limits from here.
- **Dice-button identity and per-speaker test routing.** Consciously deferred; the consequence
  (the wrong character may roll) is recorded above.
- **One DM answer per speaker.** Considered and not chosen.
- **A puppeting filter.** Prompt repair first, measurement after.
- **A neutral, non-40k debug campaign.** The setting stays; the entry point is what gets built.
- **A deterministic meta-sentence filter.** Open, undecided.
- **Profile bootstrap (phase 10b).** Unchanged, still deferred until play runs smoothly.

---

## Further Notes

- **What the run got right, and should not be "fixed".** The campaign content is good: six scenes
  as a clean chain, named NPCs per scene, opportunities with skill and difficulty, secrets, GM
  guidance, and a real gate — Pier Nine is reachable only with the loading manifest. The dice
  engine behaved: three tests, correctly routed to skill and difficulty, correctly resolved. The
  feedback protection worked; Bot A's voice was filtered at layer 1 as designed. None of the
  evening's failures were dice or audio-loop failures.
- **A convergence worth recording.** Two independent analyses reached the trailing-marker problem
  from opposite directions — one from the marker registry, one from the token ceiling. Agreement
  from independent paths is the reason the classifier decision is not treated as a preference.
- **One finding was withdrawn.** "The run left no debug session artifacts" is an artefact of where
  the analysis ran, not of the code: the evening happened on another machine.
- **The hallucination guard is a threshold, not a blocklist.** "Das war's für heute, tschüss" was
  transcribed as player speech because the segment filter only weighs probabilities, and a fluent
  stock phrase scores high. Recorded here because the operator asked for a blocklist and there is
  none to extend — building one is a separate decision.
- **The persona's share of the context.** Persona plus overlay occupied roughly two thirds of the
  prompt, and about 38 % of that was marker instructions which produced a single marker all
  evening. Moving decisions to classifiers should shrink that block; whether it does is worth
  measuring after block 2.
