# ADR 066 B — evaluation of the parity pass (2026-11-15)

Evaluation of the one parity pass of 2026-11-14 (`dmbot.tools.aux_parity`, Haiku, 35 turns,
140 calls, concurrency 3) as of commit `9a4f3e1`. **No new run:** no model call, no bot start.
Only what is on disk was read. Two offline checks ran with a fake chat and no model (named where
they are used). Nothing in `progress.md`, `docs/decision-log.md`, the code or the tests was
changed. This file is the proposal.

**Result.** Recommendation: **remove** the combined call and the parity tool, and set ADR 066 to
"rejected after the parity pass". The main reason is the measured balance:

- **What it would save:** two CLI starts and roughly a third of the classifier input per turn,
  all in the Haiku tier. On 2026-11-14 no usage limit was reached and no time was gained.
- **What it cost:**
  - The only hard failures of the pass were 2 timeouts in 35 turns. Both fell on the turns that
    matter, where someone new appears: 2 of the 7 sighting turns, none of the other 28.
  - Each timeout loses all three verdicts of the turn, because the combined call is one point of
    failure.
  - The 4 verdicts the two paths decided differently cannot be told apart from Haiku's
    run-to-run noise. On 2 of those 4 turns the separate path itself decided differently at the
    table than in the pass.

The individual cases were still on disk (section 0), so all ten differences are listed below,
one by one.

---

## 0. Where the raw output was

| what | where | status |
|---|---|---|
| Console output of the pass (progress lines, per-case table, verdict) | `C:\Users\tobo2\AppData\Local\Temp\claude\a10c544d097516d2\96a8a269-8d8e-4ffa-854b-2a01efd70f3f\scratchpad\parity_run.txt` (151 lines) | present; **temp directory, can be cleared** |
| Per-case results (`--out`): combined raw answer, separate/combined verdicts, labels | same folder, `parity_results.jsonl` (35 rows) | present; temp |
| The same report, verbatim | Claude Code session transcript `~/.claude/projects/C--Users-tobo2-repos-dungeonmaster/96a8a269-…/subagents/agent-a858f32da98f9c5ac.jsonl` (tool result of 2026-11-14T19:08:19Z) | present |
| Journal the 26 `history.debug#N` cases came from | `data/sessions/1343673766487654464/history.debug.jsonl` (the `--journal` path in that transcript) | **deleted** 2026-11-14 20:40 (`docs/phase-11-abend.md:324-325`); the turn texts of `#4` and `#22` were recovered from `logs/transcript-d1.log` / `logs/debug-d1.log` (journal `ts` = the `[latency]` line of that turn) |
| The 9 log-positive cases | `tests/aux_parity/log_positives.jsonl` | present (in the repo) |

The tool itself writes only to stdout and, with `--out`, to the given JSONL
(`dmbot/tools/aux_parity.py:455-466`). It keeps no file of its own.

Because the temp copy can vanish, the ten rows are reproduced verbatim here (from
`parity_run.txt` lines 47-115, report format `case | kind | recorded | separate | combined (labels)`):

```
≠ log-2056-scene-schrein | scene | schrein | ∅ | schrein
≠ log-0155-npc-fact | scene |      | ∅ | !timeout
≠ log-0155-npc-fact | fact | item | item | !timeout  (Zerknittertes Pergament (dem Laufburschen abgenommen) / —)
≠ log-0155-npc-fact | npc |    1 | * | !timeout  (Gestalt im Schatten / —)
≠ log-0159-npc-sichtklappe | npc |    1 | * | Bree Marlok  (Frau an der Sichtklappe / Bree Marlok)
≠ d1-1921-npc-kettenmann | npc |    1 | * | ∅  (Kettenmann / —)
≠ history.debug#4 | fact |      | quest | ∅  (Akte Schleusengrund 409: Schrein der Aschenheiligen untersuchen / —)
≠ history.debug#22 | scene |      | ∅ | !timeout
≠ history.debug#22 | fact |      | ∅ | !timeout
≠ history.debug#22 | npc |    1 | * | !timeout  (Mann mit Ketten / —)
[parity] 35 turns, 105 questions, 95/105 verdicts agree, 16 positives
[parity] positives with another combined verdict: log-2056-scene-schrein scene, log-0155-npc-fact fact, log-0155-npc-fact npc, log-0159-npc-sichtklappe npc, d1-1921-npc-kettenmann npc, history.debug#4 fact, history.debug#22 npc
[parity] new positives on empty turns: none
[parity] malformed combined answers: log-0155-npc-fact scene,fact,npc, history.debug#22 scene,fact,npc
[parity] DOES NOT HOLD (ADR 066 step 4)
```

`*` = a person the card-person code could not identify (an unnamed newcomer); `∅` = "nothing".

**Correction to ADR 066 (line 153) and the D143 row:**
- They say "5 positives decided differently" and name 4. The tool lists **7 positives with
  another combined verdict**:
  - **4 decided differently:** `log-2056` scene, `log-0159` npc, `d1-1921` npc,
    `history.debug#4` fact.
  - **3 lost to the timeouts:** `log-0155` fact and npc, `#22` npc.
- The other 3 of the 10 differences are the empty kinds of the two timed-out turns.
- Sum: **10 = 6 timeout rows (2 turns × 3 kinds) + 4 decided differently.**

---

## 1. The ten differences, one by one

"Separate" means the three calls of today; "combined" means the one call.

**Who is right** is judged against the narrated turn text. It is "unclear" where the text does
not decide.

**At the table** means what the combined verdict would change if the flag were on. Each case
answers whether it causes a wrong scene change, a wrong person present or a lost fact. A
timeout's effect is taken from the current code (section 3).

| # | turn (id) | classifier | separate | combined | right by the text | at the table with the flag on |
|---|---|---|---|---|---|---|
| 1 | `log-2056-scene-schrein` | scene | `nein` (stay) | `schrein` | **combined**: "Dann steht der Schrein der Aschenheiligen vor Fridolin und Rektalus … Bronzetür einen Spalt offen" — an arrival. The table's own separate call said `schrein` too (`debug-bis-2026-11-14.log:3068`) | **Better or neutral.** A separate miss leaves the pointer in `zollhaus`. That evening the marker path also proposed and confirmed the move (`:3056`, `:3104-3105`), so the miss would have been covered there |
| 2 | `log-0155-npc-fact` | scene | `nein` | timeout | both "no move" | **No change.** The scene verdict is lost, and the flag gate still runs |
| 3 | `log-0155-npc-fact` | fact | `item` (Zerknittertes Pergament → Rektalus) | timeout | **separate**: "drückt Rektalus hastig das Pergament gegen die Brust … das zerknitterte Pergament liegt jetzt in deinen Händen" | **Lost fact.** The parchment never enters Rektalus' inventory. At the table it did (`debug-bis-2026-11-14.log:11318`) |
| 4 | `log-0155-npc-fact` | npc | `*` "Gestalt im Schatten" | timeout | **neither verdict is a real newcomer.** The figure is Fridolin, a player character. The previous narration has him pressing into the shadows, and the answer ends "Fridolin, dein Versteck ist keines mehr". The separate verdict is a false positive | **Accidentally better.** The table registered a phantom NPC, "Gestalt im Schatten (neu, Standardwerte)" (`debug-bis-2026-11-14.log:11319`). The timeout avoids it only because everything is lost |
| 5 | `log-0159-npc-sichtklappe` | npc | `*` "Frau an der Sichtklappe" | **Bree Marlok** | **combined**: the woman says "Den Marlok gibt's nicht, Schätzchen, nur die Marlok", and the player asked for "der Marlok". This is what D138 wants | **Better.** The table registered "Frau hinter der Sichtklappe (neu, Standardwerte)" in `schrein` (`debug-bis-2026-11-14.log:12641-12642`), a second entry waiting to happen |
| 6 | `d1-1921-npc-kettenmann` | npc | `*` "Kettenmann" | `∅` (nobody new) | **combined**: the man with the chains was introduced in the previous turn (`#22`, see row 10) and is not new here | **Better.** At the table the separate path registered him a second time, "Kettenmann (neu, Kettenbund-Schläger)" (`debug-d1.log:768-769`). That happened after the turn before had already merged him, wrongly, into "Vosk der Haken" (`debug-d1.log:713`). The combined verdict avoids the duplicate but cannot repair that wrong merge |
| 7 | `history.debug#4` | fact | `quest` "Akte Schleusengrund 409: Schrein der Aschenheiligen untersuchen" | `nichts` | **unclear.** Kaad: "Drei Gassen bergab, der Schrein der Aschenheiligen, Akte Schleusengrund vier-null-neun … dort fangt ihr an" (`transcript-d1.log:2437`). That is a directive inside the mission the party already holds (`#2`: the sealed mission parchment). The bar "im Zweifel nichts" leans to `nichts`, which is also the table's verdict (`debug-d1.log:107`, `fact … → none`) | **Small.** One quest entry more or less, and no wrong state either way |
| 8 | `history.debug#22` | scene | `nein` | timeout | both "no move" | **No change** (flag gate as in row 2) |
| 9 | `history.debug#22` | fact | `nichts` | timeout | both "nothing" | **No change** |
| 10 | `history.debug#22` | npc | `*` "Mann mit Ketten" | timeout | **separate**: "Davor lehnt ein Mann mit schweren Ketten am Gürtel … ruft: ‚Wer da?‘" (`transcript-d1.log:2489`), a real newcomer | **Missing person.** The man is not registered that turn. At the table he was registered, though wrongly merged into Vosk (`debug-d1.log:712-713`). Row 6's verdict was computed on a state where that registration had happened, so with the flag on the two turns would chain differently than measured |

**Tally:**

| | count | rows |
|---|---|---|
| Combined right where the two paths decided differently | 3 | 1, 5, 6 |
| Unclear | 1 | 7 |
| Timeouts that cost something real | 2 | 3: lost item fact; 10: missing person |
| Timeout that was a lucky loss | 1 | 4: phantom NPC avoided |
| Timeouts that changed nothing | 3 | 2, 8, 9 |

**Why the three "combined right" rows do not carry the decision (this is inference):**
- **Noise.** In two of the four decided differences the *separate* path itself disagrees with
  its own table verdict:
  - `log-2056`: `schrein` at the table, `nein` in the pass.
  - `#4`: `none` at the table, `quest` in the pass.
  - One pass cannot separate Haiku's run-to-run spread from the merge (ADR 066:161-162).
- **Mechanism.** Where the combined call was better on presence (rows 5 and 6), it had
  something the separate presence call never gets: the scene question's context, meaning the
  previous narration and the player lines (`dmbot/llm/post_turn.py:185-196`; the separate
  presence question has no context, `dmbot/session/scenes.py:303-310`).
  - Row 5: the player line "ist der Marlok hier".
  - Row 6: the previous narration that introduces the man.
  - This is the "context leak" ADR 066 named as the main risk (lines 231-237). Here it helped.
  - If that help is wanted, the single-variable experiment is to give the *separate* presence
    classifier the same context, as a question for ADR 062. It does not need the merge.

**Agreements that are still misses (for completeness, not counted above):**
- `log-0201-npc-d138`: recorded 2 people (the D138 pair), both paths `∅`.
- `history.debug#11`: recorded 1, both paths `∅`.
- `history.debug#13`: both paths `*`, recorded 0. The recording is unreliable there because of
  the note-overwrite bug, ADR 066:269-275.
- The parity counts all three as agreements. They say something about the presence classifier,
  nothing about the merge.

---

## 2. The two timeouts

**What the two turns share (seen):**
- Both are sighting turns where the separate presence verdict is an **unnamed newcomer** (`*`):
  - `log-0155`: "Gestalt im Schatten", with an item fact on top.
  - `#22`: "Mann mit Ketten".
- In this pass the separate path saw a person on 7 turns: `log-1946`, `log-0155`, `log-0040`,
  `log-0159`, `d1-1921`, `#13`, `#22`. **Both timeouts fall among these 7; none among the
  other 28.**
  - If the 2 timeouts were spread at random over the 35 turns, the chance that both land among
    those 7 is C(7,2)/C(35,2) = 21/595 ≈ 3.5 %.
  - The link to sighting turns is therefore likely, but not proven with n = 2.
- The separate calls of both turns answered: the parity runs them first, then the combined
  call (`dmbot/tools/aux_parity.py:296-297`).
- In the bot's evening log the separate presence call of `#22` took **4.6 s with `out=585`
  tokens** (`debug-d1.log:711`).

**Candidate causes, evidence against assumption:**

| candidate | evidence | verdict |
|---|---|---|
| Input length | `#22`: answer 741 chars (top 3 of the 34 evening turns, `[latency] … chars=` in `debug-d1.log`), previous narration 740. `log-0155`: answer 657, previous 436, mid-range. `log-1946` (706 + 585) and `d1-1921` (600 + 741) answered | **Does not separate the cases.** Ruled out as the sole cause |
| Output length | The two combined answers are **not recorded**: the timeout leaves `combined_raw` empty and cancels the call before its `[aux]` line. The tool ran at log level WARNING anyway (`aux_parity.py:422`), so no combined call wrote token counts. Indirect: the separate presence call writes far more output on sighting turns. On 2026-11-14 its median was 158 tokens, `#22` 585, max 934 (19:12:54), still under 8 s. The combined call's output cap per API request is `max(320, 1024)` = 1024 tokens (`post_turn.py:205`, `claude_client.py:66` and `:286-288`), the same cap one separate call has alone. On a sighting turn, scene + fact + presence output can come close to or exceed it. The CLI then resumes or takes another turn (`_AUX_MAX_TURNS = 3`, `claude_client.py:72`; resume note at `:383-388`), and each extra request costs seconds | **Most plausible mechanism, unverified.** It fits "only sighting turns", and no recorded number shows it |
| CLI start | Spawn 0.56-0.78 s per call on 2026-11-14 (`[aux] … spawn=`), plus the `claude -v` probe | **Ruled out** as the cause of 20 s |
| Concurrency 3 | Up to 3 cases in flight, so up to 9 CLI processes at once. The other 33 combined calls ran under the same concurrency and answered. The two timeouts are not clustered (case 8-9 and case ~29 of 35 in completion order). The bot was running during the pass, but between 20:00 and 20:09 it logged only speech recognition and made no Claude calls (`debug-2026-11-14-nach-abend.log:1323-1388`) | **Not supported, not ruled out.** The pass recorded no per-call timings |
| Something else (API-side slowness, a hung CLI) | Nothing on disk speaks for or against it | **Open** |

**Conclusion.** The cause cannot be determined from what is on disk. What is seen: both
timeouts are sighting turns with an unnamed newcomer. What is inferred: an output-heavy
combined answer running into the shared 1024-token request cap. Settling it needs one
instrumented run (combined `[aux]` lines with `out=` / `turns=` / `total=`, and a deadline long
enough to see the real duration). That is a new run, out of scope here.

---

## 3. What a timeout costs at the table with the flag on (from the code)

The path, step by step:

1. **`classify_post_turn`** (`dmbot/llm/post_turn.py:287-293`):
   - `asyncio.wait_for(…, 20.0)` raises `TimeoutError`.
   - The result is `verdicts={}`, `retry=()` and `failure=TIMEOUT`.
   - **Nothing is asked separately.** The review amendment of 2026-11-14 (ADR 066:326) removed
     the separate retry.
2. **`DMBrain.classify_post_turn`** (`dmbot/orchestrator.py:1251-1286`):
   - It logs `[classifier] post-turn … timeout (scene=separate fact=separate npc=separate)`
     (`:1258-1266`). The label "separate" is misleading, because nothing is asked separately.
   - It writes no note (`:1267-1268` loops over an empty dict) and returns `{}`.
3. **`_classify_turn`** (`dmbot/session/scenes.py:282`) returns `(None, None, None)`.
4. **`close_turn`** (`dmbot/session/scenes.py:204-220`):
   - `_apply_commitment(None)`: no fact is written.
   - `_apply_npc_sightings(None)`: nobody is placed or registered.
   - `_apply_scene_verdict(None)`: only the model-free flag gate can still move the pointer
     (`:476-482`).
   - **Net effect: the turn's scene move, fact and sightings are all gone.** A separate call that
     times out loses only itself (for example `scene_router.py:261-264`).
5. **Time:** `close_turn` runs alongside playback (`scenes.py:183-184`) but waits the full 20 s
   instead of about 3-5 s before the player panel update (`:221`).
   - On 2026-11-14 several answers were shorter than that (`wav=10.6s`, `19.5s`). The next turn
     can then start while `close_turn` is still waiting.
   - That overlap is what overwrites replay notes (ADR 066:269-275). This consequence is
     inferred, not observed.
6. **Journal (a bug, verified offline):**
   - The brain's `last_scene_router` / `last_facts` / `last_npcs` keep the **previous** turn's
     verdicts after a combined timeout.
   - `_classify_turn` then journals them as this turn's notes (`scenes.py:275-279`). Only the
     `post_turn` note says `failure: timeout`.
   - Checked with a fake client and no model: after a combined timeout `last_facts` and
     `last_npcs` still held the values set before the call.
   - The separate path always rewrites its note (`orchestrator.py:1188-1189`), so it does not
     have this gap.

**Second finding, verified offline (it matters only for "switch on"):**
- With the current code, a combined timeout is no longer counted as "malformed" by the parity
  tool:
  - `run_case` sets `malformed = combined.retry`, and `retry` is now `()` after a timeout
    (`aux_parity.py:306-311`).
  - The timed-out kinds become `!missing`.
- On a turn whose separate answers are all empty, `judge` therefore flags nothing.
- A fake-chat run of one such turn printed `0/3 verdicts agree` **and** `HOLDS (ADR 066 step 4)`.
- The 2026-11-14 pass ran on the pre-amendment code and still counted the two timeouts as
  malformed. A rerun today would no longer do so.

---

## 4. Recommendation: remove

**Why remove and not "switch on after one step":**
- **The gain is small, and it lands where nothing hurts:**
  - Haiku input only, with no usage limit reached (ADR 066:114).
  - No latency gain, because the three calls already run side by side behind the DM's voice.
  - Two CLI starts per turn.
- **The cost lands where it hurts:**
  - The only failures of the pass hit sighting turns, which are the turns D138 and ADR 062 work
    on.
  - Each failure costs all three verdicts at once.
- **The upside is unproven.** The "combined is better" signal is three single-run differences.
  Their likely mechanism, the context, can be tested on the separate presence call alone.
- **Switching on is not one step but a chain:**
  1. Fix the parity tool's timeout judging (section 3).
  2. Fix the stale-note journalling.
  3. Explain or budget the timeout (one instrumented run).
  4. Run the three-run replay (ADR 066 step 4).
  5. Do one live run with the flag as the only change (step 5). That is a live gate under the
     WIP limit.
- **Every link in that chain buys only the small gain above.**
- **The cheaper levers from ADR 066 option C couple nothing and are still open:**
  - `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` removes the `claude -v` probe before *every* spawn,
    including the roll router and the narration (about half of all process starts, ADR 066:217-218).
  - The parity pass already showed that a shorter `sache` on `nichts` works.
- **Keeping the code off is not free either.** It is a second prompt path, a tool and three
  docs that already disagree with the code (section 4.2).

### 4.1 Removal list: every file and every spot

Line numbers are as of `9a4f3e1`.

**Code**

| file:line | function / section | action |
|---|---|---|
| `dmbot/llm/post_turn.py` (whole file, 317 lines) | combined prompt, schema, `classify_post_turn` | **delete** |
| `dmbot/tools/aux_parity.py` (whole file, 472 lines) | the parity tool | **delete** |
| `dmbot/llm/__init__.py:86-101` | `post_turn_combined` (hook) plus the blank line before it | **delete** |
| `dmbot/orchestrator.py:13` | `import asyncio` | **delete**. Its only use is `:1279`, inside `classify_post_turn` |
| `dmbot/orchestrator.py:65-66` | `from .llm.post_turn import CombinedFailure` and `… classify_post_turn as classify_post_turn_combined` | **delete** both lines |
| `dmbot/orchestrator.py:254` | `DMBrain.__init__` parameter `combine_post_turn` | **delete** the line |
| `dmbot/orchestrator.py:257-261` | the comment plus `self._combine_post_turn = combine_post_turn` | **delete** |
| `dmbot/orchestrator.py:306-309` | the `last_post_turn` comment plus the attribute | **delete** |
| `dmbot/orchestrator.py:1227-1236` | `combines_post_turn` | **delete** |
| `dmbot/orchestrator.py:1238-1286` | `classify_post_turn` (the brain's combined path and its separate fallback) | **delete** |
| `dmbot/orchestrator.py:1192-1225` | `_scene_outcome` / `_fact_outcome` / `_npc_outcome` / `_note_scene` / `_note_fact` / `_note_npc` | **keep.** Added by `d9704c6`, but the separate methods use them (for example `:1188-1189`) |
| `dmbot/runtime.py:45` | `from .llm import build_llm_client, post_turn_combined, recap_cap` | **edit the line**: drop `post_turn_combined` |
| `dmbot/runtime.py:398-399` | comment plus `combine_post_turn=post_turn_combined(config, llm_client),` | **delete** both lines |
| `dmbot/config.py:92-93` | `# One combined post-turn …` plus `aux_combined: bool = False` | **delete** |
| `dmbot/config.py:422-426` | the ADR 066 B comment (3 lines) plus `aux_combined=os.environ.get("DM_AUX_COMBINED", …)` (2 lines) | **delete** |
| `dmbot/llm/scene_router.py:157-161` | docstring of `scene_question` ("… and the combined post-turn call on Claude (`dmbot.llm.post_turn`, ADR 066 B) ask …") | **edit the text**: the function stays (the separate prompt is byte-identical with it, `scene_system` at `:177`); drop the combined-call clause |
| `dmbot/llm/fact_router.py:175-178` | docstring of `fact_question` | **edit the text** as above, keep the function |
| `dmbot/llm/npc_router.py:123-129` | docstring of `npc_question` | **edit the text** as above, keep the function |
| `.env.example:71-75` | the `DM_AUX_COMBINED` comment (4 lines) plus `DM_AUX_COMBINED=0` | **delete** |
| `pyproject.toml`, `.claude/` | — | nothing to change (grep: no `aux_parity`, `post_turn`, `AUX_COMBINED`) |

**`dmbot/session/scenes.py`, done precisely, because another change is editing this file in
parallel.** Inside `_classify_turn` (`:241-282`), which `d9704c6` rewrote:

| lines | belongs to | action |
|---|---|---|
| `:246-249`, the docstring sentence "With two or more layers asking and the brain's hook saying so (Claude answering, `DM_AUX_COMBINED=1`), the questions go out as ONE schema call (ADR 066 B); otherwise each is its own call, as on Ollama. Both paths get the same question sets." | combined | **edit the text**: delete the sentence, keep "All are optional layers … Returns" and the return-shape line |
| `:251-253`, `questions = self._post_turn_questions(…)` / `if not questions: return None, None, None` | **not combined**: the shared builder, also the separate path's input | **keep** |
| `:254`, `out: dict[str, object] = {}` | separate path | **keep** |
| `:255`, `combined = len(questions) >= 2 and self._brain.combines_post_turn()` | combined | **delete** |
| `:256-260`, `if combined:` … `log.exception("combined post-turn classifier raised …")` | combined | **delete** |
| `:261`, `else:` | combined (the branch) | **delete**, then **de-indent `:262-272`** by one level. Their content (`methods`, `jobs`, `asyncio.gather`, the fail-open loop) is the separate path and stays unchanged |
| `:273-279`, the replay-journal loop "for the layers asked this turn" (`if kind in questions …`) | **not combined**: an independent fix from the same commit (an off layer no longer repeats an old note) | **keep** |
| `:280-281`, `if combined and isinstance(self._brain.last_post_turn, dict): self.replay_note(channel, "post_turn", …)` | combined | **delete** |
| `:282`, `return out.get("scene"), …` | separate path | **keep** |
| `:284-311`, `_post_turn_questions` | **not combined** (builder) | **keep**. Only the docstring at `:287-288`, "so the separate calls and the combined one (ADR 066 B) are asked the same thing", becomes **edit the text** (for example "one keyword set per classifier") |
| everything else in the file (`close_turn`, `_scene_context`, `_npc_candidates`, the D144 code from `d327fe1`, …) | not combined | **do not touch** |

**Tests and test data**

| file:line | action |
|---|---|
| `tests/test_post_turn.py` (whole file) | **delete.** Optionally first move `test_the_separate_prompts_are_role_plus_the_shared_question_plus_the_json_line` (`:68-77`) into a router test file: it pins that the separate prompts are role + shared question + JSON line, which stays true while the builders stay |
| `tests/test_aux_parity.py` (whole file) | **delete** |
| `tests/aux_parity/log_positives.jsonl` plus the folder `tests/aux_parity/` | **delete.** Alternative: keep it as seed data for the classifier category in `dm-eval` that ADR 066 asks for (lines 254-256). It is recoverable from git (`9028661`) either way |
| `tests/test_turn_boundary.py:1563-1591` | **delete** the section header and `test_with_the_hook_on_the_three_questions_go_out_as_one_call_and_journal_as_before` |
| `tests/test_turn_boundary.py:1593-1609` | **keep** `test_without_the_hook_the_three_questions_stay_three_calls`. It uses no hook parameter and still holds, including the assert at `:1609` (there is never a `post_turn` note). Optionally rename it (for example "the three questions are three calls") and drop `:1609` |
| `tests/fakes.py` | nothing to change (`make_config` drops unknown keys, `:98-101`; nothing else names `aux_combined`) |

**Documentation**

| file:line | section | action |
|---|---|---|
| `docs/decisions/066-one-post-turn-classifier-call.md:3-4` | Status | **edit the text**: "Rejected after the parity pass, 2026-11-xx (Dxxx): option B was built and removed; see the amendment." |
| `docs/decisions/066-…md` (end) | new amendment | **append**: the result of this evaluation. Include the 10 differences, the corrected count (4 decided differently plus 3 positives lost, not "5"), the timeout cost, and why it was rejected. The "Decision" section (`:100-168`) stays as history, with a one-line note that it is superseded |
| `docs/decisions/066-…md:150-152` | "In the bot the fallback would have asked separately, 20 s late" | stays as history. The amendment at `:326` already supersedes it, so at most a pointer |
| `docs/decision-log.md:129` | row `D143` | **leave the row** (history). **Append a new row** with the next free number (currently D148): "ADR 066 B removed after the parity pass → ADR 066". Optionally add "(removed, D148)" at the end of the D143 row |
| `architecture.md:412-414` | "Who is here (ADR 062)", the parenthetical "— one `gather` of three calls, or one combined call on Claude with `DM_AUX_COMBINED=1` (ADR 066 B, see §10) —" | **edit the text**: delete the parenthetical, keep "`DM_NPC_ROUTER=1`, `!automatik nscs`" |
| `architecture.md:684-695` | §10 bullet "The post-turn classifiers can share one call (ADR 066 B)." | **delete the bullet.** Optionally replace it with one line: "The three post-turn classifiers stay three calls; a merged call was rejected after a parity pass (ADR 066)." |
| `docs/conventions.md:292` | repo layout `llm/` | **edit the line**: delete "; post_turn = the three as one combined call on Claude (ADR 066 B, `DM_AUX_COMBINED`)" |
| `docs/conventions.md:297` | repo layout `tools/` | **edit the line**: delete "; aux_parity (`python -m dmbot.tools.aux_parity`, separate vs combined post-turn classifiers on recorded turns, ADR 066 — log positives in tests/aux_parity/)" |
| `docs/phase-11-abend.md:322-325` | paragraph "ADR 066 B … ist gebaut, aber `DM_AUX_COMBINED=0` …" | **edit the text**: replace it with "verworfen und entfernt (ADR 066)". Keep the sentence about the deleted journal if it is still needed elsewhere |
| `docs/phase-11-abend.md:161, 200-221, 251, 272` | measurement D (classifier cost) | **leave.** That is the measurement, still valid |
| `docs/lessons/parity-by-construction.md` | — | **nothing to change.** It does not mention ADR 066; the question builders it motivated stay |
| `docs/lessons/mandatory-decisions-need-a-separate-classifier.md` | — | nothing to remove (the open item asked for an amendment that was never written). Optionally add one evidence line: the merged call was tried and rejected |
| `docs/decisions/061-…md:455`, `tests/test_claude_client.py:461` | mention ADR 066 as the reason for the `[aux]` line | **leave.** The `[aux]` line stays |
| `docs/progress-archive.md:31-33` | D143 entry | **leave** (history) |

**`progress.md` (only the spots are named; Tobi edits them)**

| line | content | action |
|---|---|---|
| `:17` and `:58-59` | "ADR 066 B gebaut, Schalter aus (D143)" in "Newest round" / "Last session" | history. Leave it, or add "(später verworfen)" |
| `:82-83` | "**ADR 066 B einschalten?** Erst drei Abgleich-Läufe … `DM_AUX_COMBINED=1` …" | **delete** (the question is decided) |
| `:238` | "… neben `post_turn_combined` / `recap_cap` …" in the `marker_decides` item | **edit the text**: name only `recap_cap` |
| `:239-240` | "**Doppelter Code (D143):** der „getrennt fragen“-Pfad steht in `session/scenes.py` und `orchestrator.classify_post_turn` …" | **edit the text**: the duplicated path goes away. What is left is "chat → wait_for → JSON three times (the three routers)", or delete the item |
| `:241-242` | "**ADR 066 vor `DM_AUX_COMBINED=1`:** …" | **delete** |
| `:243-245` | replay notes overwritten (found during D143) | **leave.** An independent bug, still open |

### 4.2 For comparison: what "switch on" would need, and the drift either path has to clean up

If the decision goes the other way, the named step before anything else is this. **Make the
parity tool and the bot honest about timeouts, then measure the timeout once.**
- **Build:**
  - `judge` counts every `failure=timeout|call_failed` as a failed case
    (`aux_parity.py:311`, `:361-362`).
  - `DMBrain.classify_post_turn` notes a failure verdict for each asked kind on timeout, so no
    stale note is journalled (`orchestrator.py:1267-1268`).
  - The parity tool logs `dmbot.llm.claude_client` at INFO, so each combined call writes its
    `[aux]` line.
- **Measure:** one replay of the 7 sighting turns, 3 runs each, with the combined deadline
  raised to 60 s for the measurement only.
- **Passed when:**
  - every combined call finishes in under 10 s;
  - no combined call shows `turns=3` or a resume;
  - the tool reports a deliberately injected timeout as DOES NOT HOLD.
- **Only then** come ADR 066 steps 4 and 5.

Docs that already disagree with the code. Fix them on "switch on"; on "remove" they disappear
with the list above:
- `dmbot/llm/post_turn.py:26-29` (the module docstring says a timed-out or failed call hands
  every question back; the code at `:283-297` does not).
- `dmbot/config.py:423-424` and `.env.example:72-74` ("A failed … combined answer falls back to
  the separate calls").
- `architecture.md:691-692` ("A failed, empty or unparseable combined answer asks every question
  separately").
- The log label `…=separate` on a timeout (`orchestrator.py:1261`).

---

## 5. The numbers behind the recommendation

**What the combined call saves:**

| | value | source |
|---|---|---|
| CLI starts per turn | 3 → 1 post-turn; 4.88 → 2.88 per turn including narration and roll router, about 9.8 → 5.8 with the `claude -v` probe | ADR 066:88-89 (2026-11-13 data) |
| Input tokens, the three separate calls | 2189 + 2079 + 2451 = **6,719 per turn**, of which 740 + 985 + 1317 = 3,042 cache reads | ADR 066:106-110 (33 turns, 2026-11-14) |
| Input tokens, one combined call | **not measured.** The pass logged at WARNING, so it wrote no `[aux]` line. The draft estimated a saving of 33-37 %. Applied to the measured 6,719, that would be about 2,200-2,500 Haiku tokens per turn (extrapolation, not a measurement) | ADR 066:81; `aux_parity.py:422` |
| For scale | narration context 14,300-21,600 tokens per turn on Opus (`[latency] ctx=`, `debug-d1.log`); no usage limit that evening | ADR 066:114 |
| Seconds | **none expected.** The three calls run in parallel behind the voice. On 2026-11-14 the per-call medians were scene 2.8 s, fact 3.6 s, presence 3.0 s (presence max 7.7 s). The combined call's own duration was **not recorded** in the pass | `[aux] total=` in `debug-d1.log` |

**What it costs:**

| | value | source |
|---|---|---|
| Differences | 10 of 105 verdicts: 6 from 2 timeouts, 4 decided differently (3 lean to combined by the text, 1 unclear) | section 1 |
| Timeouts | 2 of 35 combined calls (5.7 %); **2 of 7 sighting turns (29 %)**, 0 of 28 others | `parity_run.txt:10-11, 32-33` |
| Timeouts of separate calls for comparison | none found. 366 aux calls without failure up to 2026-11-13 (ADR 066:46-48), and no timeout line in `debug-d1.log` / `debug-2026-11-14-nach-abend.log` | grep |
| Positives lost to timeouts | 3 of 16 (19 %): one real item fact, one real newcomer, one false newcomer | section 1, rows 3, 4, 10 |
| Single point of failure | a timeout or failure loses scene + fact + presence of that turn together; a separate failure loses one | `post_turn.py:287-297` against `scene_router.py:261-264` |
| Code kept alive while off | `post_turn.py` (317 lines), `aux_parity.py` (472), two test files plus fixture, hook / config / env / three doc spots; two found bugs (stale notes, the tool's timeout judging); four stale doc spots | sections 3 and 4 |

**Not determinable from the disk:**
- The combined call's token count and duration per turn.
- The cause of the two timeouts.
- Whether the combined call's three better verdicts repeat over three runs.
