# ADR 066 — Should the scene, fact and presence classifiers share one schema call?

- **Status:** Accepted 2026-11-14 — option **B**, built behind `DM_AUX_COMBINED` (default `0`
  until the parity holds); see "Decision". Live-unverified.
- **Date:** 2026-11-13 (draft), 2026-11-14 (decision)
- **Refs:** ADR 057 (scene classifier), ADR 058 (fact classifier), ADR 062 with its 2026-11-13
  amendment (presence classifier, D138), ADR 061 with all amendments (Claude backend, tier rule),
  ADR 046 (replay journal, `dm-eval`), ADR 014 (roll router — stays separate either way); lessons
  `mandatory-decisions-need-a-separate-classifier`, `one-variable-per-live-run`,
  `parity-by-construction`. Decision row **D143**.

## Context

After every narrated turn `_classify_turn` (`dmbot/session/scenes.py`) starts up to three aux
calls in one `gather`: did the group enter a place (ADR 057), did the narration commit to an
item, quest or promise (ADR 058), who newly appears in person (ADR 062). Each is a stateless
JSON-schema call with its own system prompt, and each sends the narrated answer again. On the
Claude backend each is its own CLI process (ADR 061). The roll router runs before the turn on
the player's line and is not part of this question.

The question: one call with one combined schema instead of three — on both backends, on Claude
only, or not at all.

### What the logs of 2026-11-13 show

Source: `logs/debug.log` from the 00:13:58 start on (three bot starts, all on the Claude
backend, Haiku as the aux model) and the journal `history.20261113-021634.debug.jsonl`.
25 turn boundaries, at 00:36–00:40 and 01:51–02:07.

**Measured:**

| | per turn boundary | over the 25 turns |
|---|---|---|
| Post-turn aux calls | 3 (every boundary ran all three) | 75, no failure |
| CLI spawns | 4.88 — 1 narration, 0.88 roll router, 3 post-turn | 122 |
| Time until the last of the three verdicts is in | median 4.75 s, max 6.14 s | |
| The three call times added up | median 12.3 s | |

- Call time by classifier (median, range): scene 3.81 s (3.44–5.99), presence 3.95 s
  (3.56–6.14), fact 4.74 s (4.03–5.52). For comparison the roll router: 4.21 s (3.56–7.16).
- Call time follows the output size. Scene and an empty presence verdict write 12–16 characters
  and take 3.8–3.95 s. The fact classifier takes 4.7 s because it fills `sache` with a sentence
  even when its verdict is "nichts" (median 118 characters). A presence verdict that names people
  took 5.3–6.1 s. The fact call was the slowest of the three in 19 of 25 boundaries.
- Verdicts: 1 scene move, 0 commitments, 3 turns with sightings (4 people — the four duplicates
  D138 was built for). Over the whole log since 2026-10-25, all on Haiku: 154 scene verdicts with
  3 moves, 154 fact verdicts with 2 commitments, 58 presence verdicts with 5 that name people,
  and no failed call among the 366.
- The narration call for scale: `spawn=` median 1.67 s, context median 17,748 tokens, `cache=0`
  on all 25 turns, spoken answer median 36.9 s. The verdicts arrive while the DM is still talking.
- No turn in the log failed over to Ollama.

**Not in the log:** tokens and spawn time of the aux calls. `spawn=` and `ctx=` in the
`[latency]` line belong to the narration call. An aux call logs one `[classifier]` line with its
total time and verdict; `ClaudeClient.last_aux_stats` holds its token counts and nothing reads
them. The token numbers below are therefore computed from the prompts, not read from the log.
(Closed the same day for the next run: every schema call on Claude now writes an `[aux]` line
with its own tokens, cache reads and spawn time — ADR 061, amendment 2026-11-13, third.)

**Computed** (the three prompts rebuilt for the 25 turns from the journal and the
`debug-kampagne` adventure with the real prompt builders; system prompt plus user message plus
schema, in characters; exits without their gates, so the scene prompt is an upper bound):

| Call | Characters, median | Of that fixed (instructions + schema) |
|---|---|---|
| Scene (carries the previous narration and the player lines, ADR 057 amendment) | 2053 | 802 |
| Fact | 1950 | 1346 |
| Presence (roster, candidates with role and aliases) | 2675 | 2071 |
| **All three** | **6678** | 4219 |

The narrated answer (median 578 characters) is in there three times.

**Estimated in tokens.** ADR 061 measured about 520 input tokens of CLI overhead per call, on a
one-line Haiku prompt and an older CLI. German text is taken at 2 to 3 characters per token (2 is
Opus' measured output rate; Haiku's input rate is unmeasured).

| | Today, 3 calls | One call | Saved |
|---|---|---|---|
| CLI overhead | 1560 | 520 | 1040 |
| Prompt text | 2230–3340 | 1850–2770 | 380–570 |
| **Input tokens per turn boundary** | **3800–4900** | **2400–3300** | **1400–1600 (33–37 %)** |

"One call" keeps all three instruction blocks at full length and sends answer and context once.
Two thirds of the saving is the two CLI overheads, the rest the answer sent twice less. Against
the whole turn (about 23,000–24,000 input tokens with the narration call) that is 6–7 %, and all
of it in the Haiku tier. Output does not shrink: the same verdict text is written either way.

**Process starts:** 4.88 to 2.88 CLI spawns per turn (−41 %). The SDK runs a `claude -v` probe
before each spawn (ADR 061), so in processes it is about 9.8 to 5.8.

**Time:** no gain. The three calls already run side by side and behind the DM's voice. One call
carries all three outputs, so by the output pattern above it lands near 5 s in the median and at
6–7 s on a turn with sightings, against 4.75 s and 6.14 s today. Estimated, not measured.

**On Ollama there is no data.** All 23 bot starts in `debug.log` ran on Claude; the archive ends
before the classifiers existed. How Nemo answers even the three separate schemas at the table is
not in any log at hand. Ollama has no process start and no token bill, so the only possible gain
there is prompt-evaluation time, unmeasured.

## Decision

**Option B, 2026-11-14 (D143).** The draft's trigger for B was "measured aux tokens that are a
larger share of the turn than estimated here". The Phase-11 evening of 2026-11-14 measured them
(33 turns, `[aux]` lines in `logs/debug-d1.log`):

| call (`fields=`) | calls | input tokens per call | of it cache | spawn |
|---|---|---|---|---|
| scene `ziel` | 33 | 2189 | 740 | 719 ms |
| fact `art,sache,an,von` | 33 | 2079 | 985 | 720 ms |
| presence `npcs` | 33 | 2451 | 1317 | 718 ms |
| roll router `needs_test,skill,difficulty` | 29 | 2020 | 1197 | 680 ms |

All 128 aux calls: about 8500 input tokens per turn; scene + fact + presence about 6700 per
turn — well above the 3800–4900 estimated above. No usage limit was reached that evening.

What was built (as option B describes; the roll router stays its own call):

- **`dmbot/llm/post_turn.py`** — one prompt with the three questions under their own headings,
  built from the separate classifiers' own question builders (`scene_question`,
  `fact_question`, `npc_question`, split out of the existing system prompts, which stay
  byte-identical); one schema with the three schemas side by side, so the `[aux]` line reads
  `fields=ziel,art,sache,an,von,npcs` (fewer when a layer sits out); each part through its own
  validator. The context (previous narration, player lines) rides only when the scene is asked
  and is marked as Frage 1's alone. Sampling pinned, output cap = the three caps added up,
  one 20 s timeout. A combined call needs at least two questions.
- **The hook `dmbot.llm.post_turn_combined`** (the `recap_cap` pattern), asked by the brain per
  turn: `True` only on `DM_LLM_BACKEND=claude` with `DM_AUX_COMBINED=1` while the failover pair
  would try Claude. Ollama, a pause and `!backend ollama` keep the three separate calls,
  unchanged. Known gap, as with the recap cap: the one call during which Claude fails reaches
  the fallback as issued (combined).
- **Fallback in the same turn, logged:** a failed, timed-out, empty or unparseable combined
  answer asks every question separately; a missing or wrong-shaped part asks that part. A
  validator's own discard (an exit not offered, prose instead of a label) is a verdict, not a
  malformed part.
- **Journal shape as above:** the three notes keep their shape, their `raw` is each question's
  own part; one `post_turn` note holds the whole answer, the questions it carried, its failure
  and the questions asked separately after it. Notes are now copied only for the layers asked
  that turn.
- **Replay parity tool** (step 4): `python -m dmbot.tools.aux_parity --journal … --cases
  tests/aux_parity/log_positives.jsonl [--live]`. Questions come from the runtime's own
  builder; verdicts are compared as scene target, commitment kind and the people named (as the
  card person code identifies them, else `*`).

**Parity pass, 2026-11-14 — one pass on Haiku, not the three of step 4.** 35 turns (26 journal
turns of 2026-11-14 with post-turn notes + 9 log positives: 3 moves, 2 commitments, 5 turns
with sightings incl. the D138 people, and the 2026-11-14 sighting whose note was overwritten),
140 calls, concurrency 3. Result: **95 of 105 verdicts agree, no new positive on an empty turn,
but the parity does not hold:**

- 2 combined calls hit the 20 s timeout (`log-0155`, `history.debug#22`) — both turns with
  sightings; the separate calls of the same turns answered. In the bot the fallback would have
  asked separately, 20 s late.
- 5 positives decided differently: `log-2056` scene — combined `schrein` (= the recorded move),
  separate `nein`; `log-0159` presence — combined names the newcomer as Bree Marlok (what D138
  wants), separate an unidentified person; `d1-1921` presence — combined "nobody new" for a
  man already registered the turn before, separate an unidentified newcomer; `history.debug#4`
  fact — separate `quest` (a file to look into), combined and the recording `nichts`.
- Combined answers left `sache` empty on `nichts` (the shorter output the draft named as a
  lever).

Several differences go the combined call's way, but Haiku's verdicts vary between runs and one
pass cannot separate that from the merge. **So `DM_AUX_COMBINED` defaults to `0`:** the code is
in, Ollama and the default Claude evening are unchanged. Before the flag goes to `1`: the timeout
(a larger budget for the combined call, or a look at why those two took longer than 20 s),
then the three-run replay of step 4, then the live run of step 5.

*Superseded:* the draft's recommendation ("C now, B when a run shows the cost") — the run showed
the cost. The original text stays below.

## Alternatives

In every option the validators stay what they are: `to_scene_verdict`, `to_fact_verdict` and
`to_npc_verdict` are pure and take parsed data, so a combined call would hand each its own part
of the answer. A combined call exists only when at least two of the three layers have something
to ask; with one layer on (`!automatik`, a scene without exits) the single call of today runs.

### A — one call on both backends

One prompt with three questions, one schema with three parts (`ziel`, the commitment fields, the
`npcs` list), one 20 s timeout.

- Gain on Claude as in the tables. Gain on Ollama unknown and at best small.
- **Nemo and the larger schema.** The lesson this pattern rests on
  (`mandatory-decisions-need-a-separate-classifier`) scored 8/8 for one question in one call. A
  combined prompt asks a 12B model three questions with three different bars ("im Zweifel nein",
  "im Zweifel nichts", "nur wer NEU dazukommt"). There is no measurement that Nemo keeps them
  apart, and no baseline for Nemo on the separate calls either.
- On Ollama `num_predict` is a hard cut inside a grammar-constrained answer (40, 120 and 160
  tokens today). A combined answer cut short is unparseable JSON and loses all three verdicts;
  today a cut presence verdict loses only itself.
- Nemo is also the fallback: while the pair is degraded, Nemo answers the aux calls.

### B — one call on Claude only

The combined call while Claude would answer, the three separate calls on Ollama and while the
pair is degraded or pinned.

- The whole measurable gain, without touching what Nemo sees.
- The call site must not name a backend (ADR 061, tier rule). The existing pattern is
  `dmbot.llm.recap_cap`: a hook next to `build_llm_client` that the runtime asks before the call.
  It has the same known gap as the recap cap — the one call during which Claude fails is
  re-issued to Ollama as it was, combined.
- Two prompt paths for the same three decisions. The validators are shared; the instruction text
  must be too (one builder per question, used by both paths), or the paths drift
  (`parity-by-construction`).
- A parity result on Haiku says nothing about Nemo, and the reverse.

### C — leave it

Three calls, as built. No saving; nothing new to verify. Cheaper levers that couple nothing
remain open, each a small decision of its own:

- Log the aux stats (input tokens, cache reads, spawn) per call. Without it no option can be
  judged on measured tokens. **Built 2026-11-13** as the `[aux]` line, written by the client from
  the call's own numbers; the shared `last_aux_stats` slot cannot say which of three parallel
  calls it holds.
- `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` removes the `claude -v` probe before every spawn — about
  half of all process starts, on every call, with no prompt change (ADR 061: "measure first").
- Tell the fact classifier to leave `sache` empty on "nichts". It is the slowest of the three
  because of that sentence; this shortens the wait for all three more than a merge does.
- The narration call sends about 17,700 input tokens per turn with `cache=0`. That is four times
  the three classifiers together, in the expensive tier.

## Consequences

### Risks of a combined call, on both backends

- **One failure domain.** A timeout, a spent turn limit (`error_max_turns`) or a malformed answer
  costs the scene move, the fact and the sightings of that turn together. Today they fail one by
  one. No call failed in the log, so the size of this is unknown, not zero.
- **The scene context reaches the other two questions.** Only the scene call carries the previous
  narration and the player lines; ADR 057's amendment added them because Haiku could not place a
  turn without them. In one user message the fact and presence questions see them too. A
  commitment or a person from the previous turn can then be reported a second time. The prompt
  can mark the context as "nur zur Einordnung"; whether both models hold that is the main thing a
  replay has to show. Whether the state writers reject a repeated label was not checked for this
  draft.
- **The presence prompt changed on 2026-11-13 (D138) and is live-unverified.** A merge before
  D138 is verified at the table makes a wrong sighting unattributable: candidate handling or
  merge.
- **The Claude evening is one-variable** (ADR 061, `one-variable-per-live-run`). A merged call
  changes all three post-turn decisions at once and would be a second variable.
- **The lesson needs an amendment.** It says a mandatory decision gets its own call. "One call
  per turn boundary, several decisions" is a different rule and would have to be written there
  with its evidence. ADR 057 #1, 058 #1 and 062 #1 each need a line, and `architecture.md`.

### `dm-eval` and the goldens

- `dm-eval` replays the narration and the roll router. It does not replay any of the three
  post-turn classifiers, and the two goldens (`dice_flow.jsonl`, `scene_flags.jsonl`) carry no
  `scene_router`, `facts` or `npcs` notes. Exit 0 therefore holds under every option — and says
  nothing about a merge. The suite covers the prompt builders and validators against a fake
  chat, not a model's answer.
- A merge is a prompt change to three mandatory decisions with no regression gate. If B or A is
  built, a classifier category in `dm-eval` (recorded raw answer through today's validators,
  compared with the recorded verdict) belongs to the same round.

### Replay journal

- Today each turn record gets three notes, `scene_router`, `facts` and `npcs`, each
  `{raw, verdict, failure}`. Nothing reads them yet.
- With a combined call there is one raw answer. To keep one journal shape under every option and
  across a mid-session degrade (option B): keep the three notes, put each validator's own part of
  the answer in its `raw`, and add the full answer once under a new key. Older journals stay
  readable as they are.
- Seen while reading the journal: 4 of the 25 turn records of 2026-11-13 carry none of the three
  notes, though the log shows three verdicts for every boundary. Cause not examined here. A
  replay category built on these notes inherits that gap.
- *Cause seen 2026-11-14 while building the parity tool (not fixed):* replay notes are kept per
  channel until the turn's autosave drains them. When the next turn starts before that (a roll
  turn right behind a narrated one), its notes — `state_before` and the post-turn verdicts —
  overwrite the first turn's, and the record after gets none. Journal record 24 of 2026-11-14
  carries the next turn's `state_before` and an empty presence note, while the log shows
  `npcs → Kettenmann` for it. The parity tool therefore treats the recorded column as
  information only; that case is written into the case file from the log.

## Recommendation (draft of 2026-11-13 — superseded by the Decision above)

**C now.** The saving is real but small where it counts: 1400–1600 Haiku input tokens per turn
(6–7 % of the turn), two of five spawns, no time. Nothing in the logs shows the cost it would
remove hurting: no rate-limit failover, no failed aux call, verdicts in while the DM talks.
Against that stand a coupling of three mandatory decisions, an unmeasured leak of the scene
context, and two open verifications (the Phase-11 evening, D138) that a merge would blur.

**B is the next step if a run shows the cost.** Triggers: a failover caused by a usage limit
during a session, or measured aux tokens that are a larger share of the turn than estimated here.
Build it through the `dmbot.llm` hook, with shared question builders and the journal shape above.

**A only on evidence.** Nemo gains least and risks most. A needs a Nemo replay that does not
exist yet, for the separate calls as much as for the combined one.

Worth doing regardless of this ADR: the aux stats in the log (done), and the two small levers
under C.

## What a live run has to show

Before any merge, on the code as it is (the next run; the read-along sheet
`docs/phase-11-abend.md` carries these as measurement D and point N1):

1. Aux input tokens, cache reads and spawn time per classifier call — the measured version of
   the estimate table, read from the `[aux]` lines.
2. Whether a usage limit is reached in an evening, and how many turns in.
3. D138 at the table: Alter Fenk and Bree Marlok in the pawn hall come back as themselves.

To adopt B, first offline, then live:

4. **Replay parity on Haiku.** The recorded turns of the journal (54 with post-turn notes) plus
   every positive in the logs (3 moves, 2 commitments, 5 turns with sightings, among them the
   four D138 people), each through the three separate calls and the combined call. Required: the same
   verdict on every positive, no new positive on a turn that was empty, none that comes from the
   context instead of the narrated turn, no malformed answer. Three runs per turn, as in ADR 057's
   amendment — Haiku's verdicts are not deterministic.
5. **One live run with the merge as the only change:** no failed combined call; the last verdict
   in no later than about 6 s in the median (today 4.75 s, max 6.14 s); input tokens per
   boundary at or below two thirds of the number measured in step 1; and one scripted case of
   each kind decided correctly — the group enters a place, takes an item, meets someone new.

To adopt A, additionally:

6. **The same replay on Nemo, separate calls first** — the baseline that is missing — then
   combined. Same requirements as step 4, plus no answer cut at `num_predict`.
7. A live turn sequence on `DM_LLM_BACKEND=ollama` with the three scripted cases of step 5.

## Amendment 2026-11-14 (code review of the round)

A combined call that **times out or fails** is no longer retried through the separate calls. The retry put the verdicts about 40 s behind the narration (20 s + 20 s), or sent three more calls to the backend that had just failed (a paused client, or a cold Nemo under `fallback`). The turn loses those verdicts, as a separate call that times out loses its own. Only a usable call with an unusable answer (empty, unparseable, a part missing) is still asked again separately.
