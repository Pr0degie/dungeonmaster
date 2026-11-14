# ADR 061 — A second LLM backend behind one client seam: Claude via the Agent SDK, Ollama kept byte-identical

- **Status:** Proposed (Phase 11 of the model round; Accepted when the live gate in
  `docs/plans/claude-backend.md` is met)
- **Date:** 2026-09-02 (amended 2026-10-06)
- **Refs:** decision log D116 in progress.md; `architecture.md` §3 (dependencies, LLM client);
  ADR 002 (LLM host is one env switch), ADR 014 (roll router), ADR 017 (streaming parity),
  ADR 027 (context budget), ADR 042 (client-instance sampling defaults), ADR 046 (replay eval),
  ADR 057 (scene advancement). Lessons: `sampling-defaults-leak-into-aux-calls`,
  `unwired-knobs-and-silent-fallbacks`, `incidents-become-preflights`, `parity-by-construction`,
  `isolation-must-enumerate-every-artifact`, `one-variable-per-live-run`.
  Plan: `docs/plans/claude-backend.md`. Target: `docs/plans/target-vision.md`.

## Context

The table's top complaint after two debug runs is prose quality — generic, repetitive, meta.
Every guard since ADR 016 is a code fence around a 12B model's tic, and ADR 060 names the
pattern. A competitor survey (2026-09-02) found feature parity or better on dice, scene state,
memory and panel; the gap is the narration model. VoxDungeon sells its 8B→70B step as the
premium tier; Friends & Fables and DungeonsDeep run frontier models.

Tobi's constraints: no API key (per-token pricing is a bad fit for a hobby table); a Claude Max
5x subscription he already pays for; a wish to keep every local piece so he can return to local
models at any time. Facts as of this ADR: the Anthropic Help Center (updated 2026-06-16) states
that the planned separate Agent SDK credit is paused and *"Claude Agent SDK, `claude -p`, and
third-party app usage still draw from your subscription's usage limits"*; the Claude Code
legal page says OAuth is for *ordinary individual use* and that products should use API keys.
DMbot is not a product and runs on Tobi's own machine, but friends' inputs pass through his
seat and the rule can change without notice.

Technically the brain already has a narrow client surface (`chat`, `chat_stream`,
`last_stats`, `model`, `aclose`) that the replay harness and every test double already
imitate, so a second implementation costs no call-site changes. The `claude-agent-sdk` (0.2.x)
provides everything needed: plain string system prompt (replacing the CLI's own), per-call
model, partial-message streaming, JSON-schema structured output, rate-limit events, usage
counters, and an isolation mode that keeps the CLI from loading this repo's `CLAUDE.md`.

## Decision

Add a **`ClaudeClient`** that implements the existing client surface through the Agent SDK on
the operator's own subscription login, wrap it with a **`FailoverClient`** that degrades loudly
to the unchanged **`OllamaClient`**, and select the primary with **`DM_LLM_BACKEND`**. Model
tier is chosen inside the client from the call's shape (schema-constrained call → aux model,
otherwise narration model). Nothing above the seam changes; Ollama keeps running for `bge-m3`
embeddings and as the fallback.

## Current state (2026-10-25) — read this first; the amendments below are the history

- Status **Proposed** until the Phase-11 live gate; `DM_LLM_BACKEND=ollama` (default) is the bot
  of before. On `claude`, Opus narrates and Haiku answers every JSON-schema call. Subscription
  login only, never an API key.
- Since 2026-11-13 (fourth amendment): when Claude fails **the game pauses** (`DM_LLM_ON_FAILURE=pause`,
  the default) — one ⏸ line and one spoken sentence, no call reaches Nemo, the unanswered turn's
  player lines are kept, a probe at a doubling interval finds the return. `fallback` is the old
  way (Nemo takes over, one ⚠ line); `!backend ollama` pins Nemo for the session in either position.
- Narration calls: `effort="low"`, per-request cap `num_predict` + 1024 thinking headroom, the
  spoken budget held on the text at Nemo's 3.4 chars/token, **streamed calls only**; batch prose
  (recap, `!rules`) is held only by the request cap.
- Since 2026-11-13: the recap call has its own cap on this backend (2000 tokens
  + headroom), the recap prompt names a hard length (1200 characters), and the `[ctx]` line
  says that nothing is truncated here.
- Since 2026-11-13 (second amendment): a turn that ends on a fragment is cut back to its last
  complete sentence in the turn core (one sentence-end rule for sanitizer, stream and TTS), and
  the turn's ✂ line names how many characters fell away.
- Stats: separate slots for prose and schema calls; the boot ping checks both models. Since
  2026-11-13 (third amendment) every schema call also logs one `[aux]` line with its own tokens.
- Since 2026-11-14 (fifth amendment): a DM turn sends only persona + recap as the system prompt;
  scene card, state, NPC memory, RAG and alias hint open the user prompt, same text and order —
  the prompt cache now hits on that head. `[latency]` carries `cache_w=` (tokens written).
- The live evening is isolated (17 old gates parked, optional layers off — one variable). Known
  gaps and the deliberately deferred review findings: the "review of the whole round" amendment.

## Alternatives

- **Anthropic API key (Messages API directly).** Cleanest technically (real `stop_sequences`,
  `temperature`, prompt caching control, no subprocess). Rejected by Tobi on price/performance;
  remains the correct path if the subscription policy ever closes — the seam makes that a
  third client, not a rewrite.
- **A bigger local model (Mistral Small 24B / Gemma 4 12B on the 5080).** Stays on the table as
  the local path's own upgrade (Carry-over #1) and needs nothing from this ADR; it does not reach
  frontier prose quality, which is the complaint.
- **Replace Ollama entirely.** Rejected: the retriever embeds through Ollama, the fallback needs
  it, and "back to local in one env line" is a hard requirement.
- **SDK session resume (`continue_conversation` / `resume`) instead of rendering history into
  the prompt.** Rejected: `DMBrain` owns history (redo, echo-guard pair removal, auto-recap
  compaction, crash restore). Two owners would desync (`parity-by-construction`).
- **Explicit `tier=` parameter on every call site.** Rejected for now: the JSON-schema `format`
  already marks exactly the classifier/extractor calls; zero churn wins. Can be added later
  without breaking anything.
- **Nominal `num_ctx` = the model's real 200k window.** Rejected: auto-recap and the `[ctx]`
  warning key on `prompt_eval / num_ctx`; a 200k budget would never compact history and would
  send the whole campaign every turn. Keeping 24576 preserves recap cadence and bounds usage.
- **Tool-calling in the same round.** Deferred to Phase 12: two unknowns at once (backend and
  turn flow) would make a failed evening undiagnosable.

## Consequences

- **"Everything local — no cloud" is no longer strictly true.** `CLAUDE.md` and
  `architecture.md` are amended: local by default, optional cloud backend via the operator's
  own subscription, never an API key. The Ollama path remains complete and is the documented way
  back.
- **Policy exposure, recorded once.** The subscription route is permitted today for individual
  use and may change. The failover means a policy change costs quality, not the evening. The bot
  must run on Tobi's machine when the Claude backend is on (no token on another machine).
- **Unmappable knobs become no-ops on Claude:** `temperature` (D83 intro temperature),
  `repeat_penalty`/`repeat_last_n` (ADR 042), `top_p`, and server-side `stop` sequences (D37).
  The client-side label cut (`_cut_at_labels`, `StreamAssembler.stopped`) remains the guard.
  Documented in the client and logged once at first use.
- **VRAM:** Nemo is no longer resident during play (Ollama lazy load / idle unload), so
  `TTS_DEVICE=cuda` on the 4070 becomes the recommended setting with `DM_LLM_BACKEND=claude`
  (closes the old Workstream A). Fallback pays a cold load (~10–15 s once).
- **Concurrency:** classifiers no longer serialise behind narration on one GPU;
  `OLLAMA_NUM_PARALLEL` is irrelevant on the Claude path. D40's timing rationale weakens — a
  flow change for Phase 12, not this one.
- **Two new modules and one dependency** (`claude-agent-sdk`, plus the `claude` CLI + Node on
  the Windows bot machine, installed and logged in outside the agent — `SETUP.md`). Lazily
  imported; the Ollama path never touches them.
- **Latency profile changes** (subprocess spawn + cloud roundtrip vs local inference). The
  `[latency]` line gains `spawn`/`cache`; the live gate pastes them. This is the input Phase 12
  needs.
- **Preflight grows** (`check_claude`): API-key refusal, CLI presence, login ping — every
  external-state incident becomes a boot check.
- **The output cap still cuts end-of-answer markers.** `num_predict` maps onto
  `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, so a long Opus answer loses its trailing `<<ERLEDIGT>>`,
  `<<UHR>>`, `<<ZEIT>>` or `<<ORT>>` exactly as Nemo's did (ADR 057's root cause). This round
  only measures it (`truncated` stat, WARNING, gate item 8); Phase 12 removes the dependency by
  moving those requests into tools.

## Amendment (2026-10-06) — the evening is isolated, the ERLEDIGT path is named

A fresh review of `main` against `docs/plans/target-vision.md` found that opportunity resolution
(`<<ERLEDIGT>>`, ADR 043) is the last mandatory decision still carried only by an inline
end-of-answer marker plus a default-on confirm click, and that the 2026-08-22 analysis did not
cover it. It explains the "the DM keeps reminding us and nothing moves" symptom better than the
model alone.

Decided, without widening this round's code scope:

- The live evening runs on Claude with the 17 WIP-override gates **parked** and the optional
  layers off, so the model is the only variable (`one-variable-per-live-run`). The parked gates
  are re-triaged after the evening.
- The marker probe covers `<<ERLEDIGT>>` (with `DM_FLAG_CONFIRM=0`) as well as `<<TEST>>`, and
  truncation is counted, so the probe result is interpretable.
- Fixing ERLEDIGT and dropping the persona's "remind the group" instructions belong to Phase 12,
  together with tools for every remaining inline marker and for damage to any combatant.

## Amendment (2026-10-06, build) — where the installed SDK differs from the plan

Found while building `dmbot/llm/claude_client.py` against the installed `claude-agent-sdk`
0.2.163 and the native CLI 2.1.291, by reading the SDK source and by a short live smoke on Haiku
(subscription login, this machine). Each point is commented at its spot in the client.

**The output cap is not a hard cut.** `CLAUDE_CODE_MAX_OUTPUT_TOKENS` caps one API request. When
it hits, the CLI injects "Output token limit hit. Resume directly…" and asks again, up to three
times, regardless of `max_turns=1`; if the answer still does not fit, the run ends with an
assistant error `max_output_tokens`. Left alone, a narration turn would talk for up to four times
`num_predict` and then fail over to Ollama. The client therefore cuts narration itself at the
first `max_tokens` stop reason in the stream frames and closes the stream. This restores the
PRD's premise (hard cut, `truncated`, the `✂` WARNING), so gate items 7 and 8 stay meaningful.
The CLI's first resume request may still run in the background until the process is ended.

**A stop reason exists.** `ResultMessage.stop_reason` is a real field, and every request's stop
reason is in the `message_delta` stream frame. The token comparison is only the fallback.
Partial messages are therefore switched on for batch calls too.

**Structured output is a tool call, not a constrained decode.** `output_format` makes the CLI
register a `StructuredOutput` tool. Three consequences: (1) with `max_turns=1` a model that
answers in prose first fails the run ("Reached maximum number of turns (1)", seen live), so
schema calls get three turns; (2) the callers' `num_predict` (80 for the roll router) is sized
for Ollama's grammar and made the CLI spend four requests on one verdict (5.4 s), so schema calls
get a floor of 1024 output tokens per request; (3) the client appends one German line to the
system prompt of schema calls asking for the tool call without preamble (1.5 s instead of 3 s on a
toy prompt). A schema call that still runs out of cap returns its text and logs a WARNING — the
callers fail open as they do on a bad verdict from Ollama; it is not a backend failure.
Classifier latency on Haiku was 1.5–5 s in the smoke. That is an input for the live gate and for
the router timing question of Phase 12.

**The system prompt goes through a file.** The SDK puts a string `system_prompt` on the command
line; persona + state + RAG outgrows Windows' 32,767-character limit. The client writes it to a
per-call file under the system temp dir and passes `{"type": "file", …}`.

**Early close ends the subprocess, about five seconds later.** `query()` does not close its inner
generator on an early exit; the event loop finalises it, and the SDK's transport then sends stdin
EOF, waits up to 5 s and terminates. Measured: closing returns at once, the CLI process is gone
after about 5 s. A per-call `ClaudeSDKClient` would end it deterministically but blocks the turn
for those 5 s, so `query()` stays. A test drives the real `query()` over a fake transport to pin
that the close arrives.

**Isolation needs two more switches than the PRD listed.** The SDK has no field for session
persistence, so every DM turn would be written to `~/.claude/projects` as a transcript; the
client passes the CLI flag `--no-session-persistence` through `extra_args`. `strict_mcp_config`
keeps the operator's own MCP servers out. With both, the init frame reports no tools and no MCP
servers; a one-line prompt costs about 520 input tokens of CLI overhead.

**On Windows the SDK refuses npm's `claude.cmd`.** It only spawns a native `claude.exe` (batch
files run through `cmd.exe`, which it treats as an injection risk), and this install bundles no
CLI. `SETUP.md` must therefore describe the native installer (`irm https://claude.ai/install.ps1 |
iex`), not `npm i -g @anthropic-ai/claude-code` as the PRD says. Done in `SETUP.md` B10.

**Smaller decisions taken in the client, beyond the PRD:**

- A call with exactly one user message is sent verbatim. The transcript header ("antworte nur als
  Spielleitung") would contradict the routers', extractors' and recap's own instruction.
- The API-key refusal is enforced per call, not only in the preflight — otherwise a failed
  preflight would still let the CLI bill the API.
- An `AssistantMessage.error` is a backend error; its text is the CLI's "API Error: …" prose and
  must never be spoken.
- A call that produces nothing for 120 s (streaming: before its first delta) is a backend error.

**Measured in the smoke, Haiku only:** spawn-to-first-message about 0.7 s per call. Not yet
measured: Opus, a full-size system prompt, cache reads.

**From the review of the stream and failover logic (same day):**

- The SDK raises bare `Exception` for a failed or timed-out initialize handshake. The client
  maps every exception of a call to `LLMBackendError`, otherwise such a turn would bypass the
  failover and simply be silent.
- A schema call that runs out of turns (`error_max_turns`) loses its verdict but is not a backend
  failure, for the same reason as a spent cap: it must not push the narration onto Ollama.
  A wrong or unavailable aux model still degrades the whole pair — loud, and intended.
- A retry that fails after the announced time has passed posts a corrected notice, once per
  cooldown.
- **Known and not fixed** *(closed for the Claude path later the same day — see the next amendment)***:** `last_stats` is one slot per client. When a classifier call overlaps
  an aborted narration stream, the turn's `[latency]` line and the auto-recap trigger can read
  the classifier's numbers. The same holds for `OllamaClient` today; a fix needs per-call stats
  across the seam and belongs to Phase 12, where the turn flow changes anyway.

## Amendment (2026-10-06, steps 4-6) — the stats slot, the boot ping

**The `last_stats` overwrite is closed on the Claude path.** The note above called it known and
not fixed. On closer reading the fix did not need per-call stats across the seam: `ClaudeClient`
now keeps two slots — `last_stats` for prose calls, `last_aux_stats` for schema calls — and
`FailoverClient.last_stats` follows the side that answered the last *prose* call. A classifier
that finishes, or fails over, while a narration stream is open can no longer feed the turn's
`[latency]` line or the auto-recap trigger. What remains: `OllamaClient` is deliberately
untouched and still has one slot, so the old overlap exists on the pure Ollama path and while the
pair is degraded; and two overlapping *prose* calls (a narration and an auto-recap) still share
the narration slot on both backends. Both stay with Phase 12.

**The boot ping covers both tiers.** `check_claude` pings the narration model and the aux model
side by side and names both outcomes in one line. A mistyped `CLAUDE_MODEL_NARRATION` used to
pass the aux-only ping and fail over on the first turn. Measured live on this machine: both pings
together 2.9 s; a nonsense narration model is reported as `model_not_found` with the knob named.
The cost is one eight-token Opus request per boot.

**The `[latency]` line carries `spawn`, `cache` and `cut`** when the stats have them; an Ollama
turn's line is unchanged.

## Amendment (2026-10-06, review of the whole round) — fixed, and deliberately left

An independent verifier read the diff since `01a8d14` against this ADR, the golden rules and the
installed SDK. It confirmed: `OllamaClient` untouched, zero edits to tests that existed before,
isolation complete, no path that spawns the CLI with an API key set. Seven findings were fixed
with tests:

- **A call that began before a degrade no longer undoes it.** A narration stream that was open
  when a classifier failed used to clear the cooldown when it ended, so the next call walked
  into the same error and announced it again. A primary success now ends only a degraded period
  that already existed when that call started.
- **The transcript labels are `Spieler:` / `Spielleitung:`,** not the bracketed form of the PRD.
  The speaker-label guards above the seam match `<label>:` only; with no server-side `stop` they
  are the sole anti-puppeting guard, and a bracketed label was invisible to them.
- **A failure while preparing a call is a backend error** (it bypassed the failover as a silent
  turn), and a vanished working directory is recreated.
- **A cut batch answer takes its text from the stream deltas** when no assistant message came
  first. Measured live on Haiku: a recap-style call cut at 30 tokens returns its 30 tokens.
- **The boot ping passes `CLAUDE_MODEL_FALLBACK`,** so a value the CLI rejects fails at boot.
- **The CLI search prefers the native exe** at the installer's default location over a shim on
  PATH, as the SDK does; the boot message no longer announces a fallback that does not happen.
- **Docs:** the troubleshooting text named a log prefix four of the six failure lines do not carry.

Left as they are, on purpose:

- **Timeouts and cancels run about 5 s long on Claude.** A timed-out or cancelled call waits for
  the SDK's shielded shutdown (stdin EOF, 5 s grace). The routers' 20 s limit is therefore about
  25 s here. No turn is lost; the number belongs to the router-timing question of Phase 12.
- **Only `error_max_turns` counts as a lost verdict.** Any other error result of a schema call
  degrades the pair. No such subtype exists in the installed SDK; revisit if one appears live.
- **A rejected rate limit fails over even when paid overage would have served the request.**
  Intended: no usage beyond the subscription. `overage_status` is ignored.
- **The table notice shows a time of day only.** A weekly limit that resets days ahead reads as
  "bis etwa 09:00". Cosmetic.
- **`spawn=` includes the SDK's own `claude -v` probe** that precedes every spawn. It can be
  switched off with `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` in the bot's environment; measure first.
- **The CLI inherits the bot's environment,** Discord token included (the SDK merges
  `os.environ`). No tool is enabled, so the model cannot read it.
- **Only `ANTHROPIC_API_KEY` is refused.** Other variables that redirect billing
  (`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, the Bedrock/Vertex switches) are not checked.
  Not set on this machine; a candidate for the preflight before anyone else runs the backend.
- **The stderr tail is one list per client,** so with concurrent calls an error message can carry
  another call's stderr. It only feeds the error text shown by `!backend`.

## Amendment (2026-10-25, first Opus turns at the table) — thinking ate the spoken budget

Found on the first live run with Opus and the full DM prompt (CLI 2.1.310): the intro was
spoken, every player turn after it came out empty (`🪵 LLM roh (stream):` with nothing after it,
`chars=0`, `220/220 Tokens`). Cause, reproduced with the persona alone: **Opus thinks although
the client passes `thinking={"type": "disabled"}`** (the SDK correctly sends `--thinking
disabled`), and the thinking tokens count against `CLAUDE_CODE_MAX_OUTPUT_TOKENS`. The first
request spent all 220 tokens on thinking; the client cut at that first `max_tokens` stop, before
any text. `MAX_THINKING_TOKENS=0` does not stop it; `effort="low"` shortens it (persona alone: 93
thinking tokens in one request instead of 640+ over four).

Decided, narration calls only (schema calls unchanged):

- **`effort="low"`.** Shorter thinking is also the latency fix: first delta ~3.7 s live, against
  10–27 s for the empty turns before.
- **The per-request cap is `num_predict` + 1024** (`_THINKING_HEADROOM`), so the thinking
  fits beside the text.
- **The spoken budget is held on the text by the client:** the overflowing delta is trimmed
  and the stream ends there. It is held as characters because the stream has no per-delta
  token count. *(Revised the same night, second run — see below: 3.4 characters per token, and
  streamed turns only.)*
- **A `max_tokens` stop cuts only after text has begun.** A request that ended in thinking is
  read on — the CLI's resume brings the text. The stop reason is reset at each `message_start`,
  so a resumed request's first delta is not taken for text arriving at the cut.
- **`think=` in the `[latency]` line** (`thinking` in the stats). `gen=` still counts thinking
  in, as billed.

Rejected: a larger context window — the context was not full (`ctx=17617/24576`) and the budget
is nominal on purpose (recap cadence equal to Ollama's); the variable of the evening stays the
model. A thinking budget (`{"type": "enabled", "budget_tokens": N}`) — the API minimum is 1024,
more than the spoken budget itself.

Live-verified this session: the boot preflight with the new options (`narration opus: OK · aux
haiku: OK` — Haiku accepts `effort`), and two streamed persona turns at `num_predict=220` (250 and
365 chars, `think=70`/`68`, not truncated). A turn with the full table prompt and voice is
live-unverified.

**Revised after the second run the same night (02:25–02:38).** Every turn had text, 5.5–8.6 s to
the end of generation. Two consequences of the first version showed:

- **The cap cut 16 of 17 turns.** At 2 characters per token (Opus' real rate), 220 tokens are
  ~440 characters; Nemo's 220 tokens were ~750 (its 2026-06-15 turns: median 224, p90 741
  characters). The same token number was a much shorter leash, and the last thought of a turn —
  often the hook — went unspoken. Tobi's verdict: a GM talks sometimes a lot, sometimes little;
  no sentence quota. So `_CHARS_PER_TOKEN` is **3.4, Nemo's rate**: the budget is parity in
  *spoken length*, and the cap is again a brake on monologues that rarely engages. The persona's
  "zwei bis vier Sätze" stays untouched tonight (it is shared with Nemo; changing it would be a
  second variable).
- **The auto-recap was cut at the spoken budget.** It is a batch call with `num_predict` 400;
  cut at 800 characters mid-sentence, it lost its newest events (a docker had just named
  "Dockmeister Kessel"; the next turn denied anyone had). The spoken budget now applies to
  **streamed calls only** — the only ones spoken as they arrive. Batch prose (recap, `!rules`,
  a batch-mode turn with `DM_STREAMING=0`) is held only by the per-request cap with its
  headroom and the `max_tokens` cut. Live: the recap over the same 15 turns came out at 1275
  characters, uncut, ending with Kessel. Known gap: with `DM_STREAMING=0` a Claude turn has no
  spoken budget below ~1244 tokens; not the evening's configuration.

## Amendment (2026-11-13) — the recap gets its own cap on Claude and a hard length

Found in the logs of 2026-10-31 and 2026-11-12: `✂ … (1102/400 Tokens)` on six of the last seven
auto-recaps. The stored recap was 2344 characters and ended mid-sentence ("Kurz darauf brachte
ein"). The 2026-10-25 revision had taken the spoken budget off batch prose, which left the recap
held by the request cap of 400 + 1024 tokens. That was enough for the 1275-character recap
measured then; it is not enough once the recap is cumulative. Each auto-recap folds the previous
one in, the prompt asked for "4–8 Sätze" and told the model that nothing of the earlier recap
may be lost, and Opus obeyed the second instruction: the recap grew until the cap cut it — at its
end, where the newest events are.

Decided:

- **The recap call has its own output cap on Claude, and only while Claude answers.**
  `DMBrain` takes a hook (`recap_num_predict`) that it asks before each recap call;
  `dmbot.llm.recap_cap(config, client)` — next to `build_llm_client`, so no call site names a
  model — supplies it. On Ollama there is no hook and the 400 stands. On Claude the hook
  answers `claude_client.RECAP_OUTPUT_TOKENS` = **2000** while the failover pair would try
  Claude, and nothing while the pair is degraded or pinned with `!backend ollama`, so Nemo
  keeps its 400. With the thinking headroom 2000 is a request cap of 3024 tokens, room for
  more than three times the prompted length: the cap is a brake on a runaway answer, not what
  ends a recap. A cut still raises the ✂ WARNING. Known gap: the one recap call during which
  Claude fails is re-issued to Ollama as it was, with 2000.
- **The recap prompt names a hard length:** at most 8 sentences and 1200 characters
  (`RECAP_MAX_CHARS`), also when an earlier recap is folded in. The cumulative instruction now
  reads "condense the earlier part so the length holds; open threads and the latest events
  must not be lost, then names and decisions before older detail" instead of "nothing may be
  lost". This prompt is shared with Ollama. The length is prompted, not enforced — code cannot
  shorten a recap without losing facts; a recap over 1.5 times the length logs a WARNING.

Rejected: a higher floor for all batch prose in the client — it would also lift the cap of a
batch-mode turn (`DM_STREAMING=0`), and the narration budget is not to change before the Claude
evening. Raising the 400 at the call site — it would change the Ollama path. A fixed number
chosen at boot from `DM_LLM_BACKEND` (the first version of this round) — a degraded or pinned
session would have sent Nemo 2000, and Nemo does not hold a prompted length.

Fixed in the same round, outside the client: the auto-recap now writes a `{"kind": "compact"}`
event into the autosave journal and the crash restore loads only what follows it (D136). Before,
every restart put the last 20 turns back on top of the recap that already held them, so the first
turn after a restart was at 23,200–24,000 of 24,576 tokens and triggered another recap — eight of
the last ten auto-recaps in the log. The event is written only once the new recap is really in
`state.json` (a failed save or a `!leave` during the summary leaves the turns to the journal),
and not at all when the journal was rotated meanwhile. The `[ctx]` WARNING of a Claude turn
(the stats' `backend` key) now says that nothing is truncated and that the budget only paces
the auto-recap.

Not changed: the spoken budget of a streamed turn. It engaged on all three turns of 2026-11-12
(raw text exactly 748 characters each). The cut fragment is neither spoken nor posted —
`_trim_to_last_sentence` drops it from the answer that chat, speech and history share. One gap
found while checking: `_SENTENCE_END` does not accept the German closing quote `“` after the
full stop, so a complete sentence ending in `.“` right before the cut is dropped with the
fragment (seen once that evening). Left for the round that decides the spoken budget.

Live-unverified: the recap under the new cap and prompt, and a restart after an auto-recap.


## Amendment (2026-11-13, second) — a cut turn ends on its last complete sentence

Found in the run of 2026-11-13 (01:48–02:16): 7 of 22 turns logged `✂ … (220/220 Tokens)`. All
seven were cuts at the **spoken budget of 748 characters** (3.4 × 220), not at the output cap —
for a budget cut the line shows the cap itself as the count. The fragment after the cut was
already neither spoken nor stored: `_trim_to_last_sentence` in `finalize_answer_markers`, the
seam the batch turn and `StreamAssembler.finish` share, drops it on both backends. What the table
lost were **complete sentences**: the sentence-end rule did not accept `“` after `?`/`!`, so the
NSC line right before the cut counted as part of the fragment and went with it (02:01:01:
„Bevor wir über Ware reden, Schätzchen: In wessen Auftrag kommst du?“; 01:52:46: the sister's
shout ending in `!“`). `86ccdc0` (02:40, after the run) fixed that rule in the sanitizer;
`tts/textsplit.py` still had its own, which disagreed.

Decided:

- **The cut stays in the turn core**, in `finalize_answer_trimmed` (formerly
  `finalize_answer_markers`, which remains as its two-value view). Not in the client: it cuts at a
  character count, knows no sentences, and in a stream the deltas have already been passed on. Not
  in the `StreamAssembler` alone: the batch path does not go through it. Recap, `!rules` and schema
  calls do not go through `finalize` and are untouched.
- **Every answer that ends on a fragment is trimmed**, not only one the backend reports as cut
  (Tobi, 13.11.). That also covers a stop-label abort and Ollama's `num_predict` cut, and the
  `dm-eval` replay needs no cut flag. An answer that is one unfinished sentence stays as it is —
  no silent turn. Sentences already spoken are safe by construction: the assembler holds back the
  latest completed sentence, so the fragment is never spoken, and history, journal and chat get
  the same trimmed answer.
- **One sentence-end rule** (`af5056e`): `textsplit.SENTENCE_END` and `split_sentences` —
  terminator, any closing quotes or brackets (`“` and `«` included), then whitespace or the end.
  `llm/sanitize.py` imports both; `split_completed` (stream), `chunk_text` (TTS) and the Discord
  splitter use them. `rag/retrieve.py` keeps its own chunk-boundary set (it also counts `:` and `;`).
- **The ✂ line of a DM turn comes from the turn core** and names the dropped characters:
  `✂ Antwort an der Ausgabegrenze abgeschnitten (220/220 Tokens), 37 Zeichen am Ende weggefallen`
  (0: the cut happened to fall on a sentence end, or the answer was one unfinished sentence). The
  turn core wraps its call in `caller_reports_cut()` (`dmbot/llm/cut_report.py`, a context
  variable, so neither the `LLMClient` protocol nor `OllamaClient` changes). Inside it
  `ClaudeClient` writes no narration ✂ line and hands `cut_tokens`/`cap` over in `last_stats`;
  outside it (recap, `!rules`, NSC memory) the client writes its line as before.

Not changed: the budget (`DM_NUM_PREDICT`, Tobi's to set) and the persona. Known gaps: Ollama
reports no cut (`done_reason` is not read), so a turn there gets no ✂ line (open point in
`progress.md`); a budget cut still shows the cap as its token count.

Live-unverified.

## Amendment (2026-11-13, third) — every schema call logs its own numbers

ADR 066 (draft) asked what the classifiers cost per turn, and the log could not say: an aux
call's tokens went into `last_aux_stats`, which nothing read. Reading that slot from
`DMBrain`'s `[classifier]` line would not have worked either — the three post-turn classifiers
run side by side and share it.

So `ClaudeClient` writes one INFO line when a schema call completes, from that call's own record:

`[aux] haiku fields=ziel in=1234 cache=0 out=12 turns=1 spawn=700ms api=2100ms total=3800ms`

`fields` are the schema's top-level names and identify the call (`ziel` scene, `art,sache,an,von`
fact, `npcs` presence, `needs_test,skill,difficulty` roll router). `in` counts cache reads in,
like `ctx=` in the `[latency]` line; `turns` above 1 means the model answered in prose before the
tool call; ` cut` is appended when the call ran out of cap. Logging only: no stats key, no return
value and no call path changed. A schema call answered by Ollama writes no such line.

Live-unverified.

## Amendment (2026-11-13, fourth) — a failed Claude pauses the game instead of handing it to Nemo

The table's verdict after the Claude evenings is unanimous: Nemo is unusable as a narrator. The
failover of this ADR made a failed backend "cost quality, not the evening" — but a Nemo turn in
the middle of an Opus scene costs more than a pause does, and it writes itself into history and
recap. Ollama stays for the embeddings (`bge-m3`) and as the operator's deliberate way out.

Decided:

- **One switch, two positions: `DM_LLM_ON_FAILURE=pause|fallback`, default `pause`.** `fallback`
  is everything this ADR described before, unchanged, and stays so a better local model can step
  in later. The constructor of `FailoverClient` defaults to `fallback` (the existing tests are
  untouched); the config defaults to `pause`; an unknown value is a boot error; the boot log and
  `!backend` name the position, and the preflight's failure lines say which consequence applies.
- **In `pause` no call reaches the fallback.** The failing call and every call until the next
  attempt raise `LLMPausedError` (a subclass of `LLMBackendError`, raised only while no text of
  the call has been handed out; calls during the pause do not start the CLI). The decision lives
  in `llm/failover.py`; no call site names a backend. What each caller makes of it:

  | Call | Caller's handling | Changed? |
  |---|---|---|
  | narration, streamed | `_stream_once` used to swallow it: an empty answer went into history and the lines were spent | **yes** — re-raised, the turn core keeps the turn |
  | narration, batch (`!dm`, after a roll) | rose to the delivery layer: "(Der Spielleiter schweigt …)", lines spent | **yes** — the turn core keeps the turn, no chat line |
  | roll router | `classify_test` catches, no dice button | no |
  | scene / fact / presence classifier | each catches, verdict `call_failed` | no |
  | recap | auto-recap catches and keeps the history; `!wrap` says it could not summarise | no |
  | NPC memory | the extraction wrapper catches; the window mark is not advanced, so the turns are mined at the next extraction | no |
  | `!rules` | the cog catches; its line no longer asks "läuft Ollama?" | text only |

- **The unanswered turn is kept, not lost.** When a turn fails before anything was said, the turn
  core (`DMBrain._hold_turn`) puts its input back: the player lines into `held_lines`, dice
  results and GM notes to the head of their own queues, and the session's last-turn / last-action
  / replay fields back to what they were — nothing reaches history, the roll router or the
  classifiers. The kept lines lead the next turn **outside the 8-line cap**; everything said
  after them goes through the buffer and the cap as always. Only one turn is kept that way: a
  second attempt during the pause leaves it as it was and returns its own new lines to the head
  of the buffer. Two turns that were both in flight when the backend failed (a network outage
  can take the client two minutes to report) are both kept and answered in the order they were
  said, whichever failed first; if the later one still gets its answer, the session's
  last-turn fields describe that one. A `!redo` during the pause leaves the previous answer and its marker requests
  in place. An echo-guard retry that meets the pause keeps the turn (nothing was spoken); an
  intro-guard or consistency retry keeps the first answer.
- **The return is found by a probe, at a doubling interval.** `DM_LLM_PAUSE_RETRY_S` (30) is the
  first wait; each failed attempt doubles it up to 300 s; a reported rate-limit reset beats the
  interval. The existing watcher in `DMCog` sleeps for `FailoverClient.retry_in()` and calls
  `probe()`: one call of the shape that failed — prose or schema, so it reaches the tier that was
  out without naming a model — with the eight-token "ping" of the boot preflight and a 30 s
  timeout. A call that arrives after the wait is an attempt of its own — **if it has the shape
  that failed.** Only that shape is tried and only its answer ends the pause; the other tier's
  calls are refused meanwhile (Haiku out, Opus fine: a narration that got through would
  announce ▶ and its classifiers ⏸ again, every turn). A failure counts only if nothing changed
  since the call began: the other two post-turn classifiers do not double the wait, and a probe
  that fails after a call has already ended the pause announces no second outage.
  `DM_LLM_PAUSE_RETRY_S` below 1 is a boot error (0 would never back off).
- **The bot answers the kept turn itself only after a short pause.** `DM_LLM_PAUSE_AUTO_TURN_S`
  (180): when a pause shorter than that ends — by a probe or by a call that got through — and
  the brain still holds a waiting turn (`DMBrain.waiting_turn`: kept lines or unnarrated dice
  results), the watcher starts one DM turn, which answers the kept lines and what was said
  since in one answer. A turn that ended the pause itself has taken its lines along and is not
  waiting, so nothing is started on top of it; a side call (`!rules`, a recap) that ended it
  leaves the turn waiting, and it is answered. The turn runs as its own task, so the watcher
  keeps posting and probing while it plays. After a longer pause the bot only announces the
  return and waits for the next player line; the kept lines stay where they are.
- **Exactly one notice each way, in chat and by voice.** Failed probes and kept turns say
  nothing; `!dm` / `!redo` during the pause get a ⏸ reaction instead of a line.
  - Out: `⏸ Claude antwortet nicht — das Spiel pausiert. Eure Zeilen bleiben vorgemerkt, ich
    melde mich, sobald Claude wieder da ist.` (with ` (Limit bis etwa HH:MM)` after "pausiert"
    when a rate-limit reset was reported) — spoken: „Die Spielleitung ist gerade nicht
    erreichbar, das Spiel pausiert.“
  - Back, short pause or a call got through: `▶ Claude antwortet wieder — es geht weiter.` —
    spoken: „Die Spielleitung ist wieder da, es geht weiter.“
  - Back, long pause: `▶ Claude antwortet wieder. Die Pause war lang, darum warte ich auf eure
    nächste Zeile — das Vorgemerkte beantworte ich dann mit.` — spoken: „Die Spielleitung ist
    wieder da und wartet auf eure nächste Ansage.“ When a call that got through ended the long
    pause, this text is used only if a turn is still waiting (the pair hands both texts to the
    cog, which asks the brain); otherwise that call is the turn and the short text is right.

  The spoken sentences go through the existing no-LLM path (`runtime.speak`, the one `!lore tts`
  uses) and do not say "Claude" (a guess that XTTS would mispronounce it; not tried). The chat
  line says "bleiben vorgemerkt", not "eure letzten Zeilen sind vorgemerkt": when the outage hits
  a side call, no turn is waiting.
- **A failure in the middle of a streamed turn is handled as before.** After the first delta the
  backend's own error is re-raised, what was spoken stays, history notes "… [Antwort
  unterbrochen]", and the turn counts as answered (lesson `spoken-audio-cannot-be-retracted`).
  New is only that the pair then pauses instead of degrading, with the one notice.
- **`!backend ollama` stays the emergency grip.** It pins Nemo for the session in either
  position, also during a pause (no probing while pinned); `!backend auto` follows the switch
  again and clears a running pause without a ▶ line.

Rejected: a pause that only a player turn can end (how the cooldown works) — the table would
have to poke the bot to learn that Claude is back. A probe on the cheaper tier regardless of
what failed — a Haiku probe reports a return while Opus is still rate-limited, and the next turn
announces a second outage. A fixed 30 s interval — a two-hour outage would cost 240 CLI starts
for nothing. Building a new voice path for the notices — one existed.

Open points, left as they are:

- **A router or classifier verdict lost in the outage is not fetched again** — as with a timeout
  today. An action narrated just before the outage gets no dice button from the router.
- **Kept lines live in memory only.** A restart during the pause loses them (the crash restore
  loads answered turns).
- **A `!start` / `!intro` that fails in the pause is not run again.** The command answers with
  its existing error line; issuing it again after ▶ works.
- **How long until ⏸ on a network outage is unmeasured.** A rejected rate limit or a dead login
  fails at once; a CLI that cannot reach the API may only hit the client's 120 s no-output
  timeout. Durchgang 3 of the Phase-11 sheet measures it.
- **The spoken notice is not queued behind a turn that is still playing.** After a mid-stream
  failure the last sentences of the broken turn and the pause sentence can reach Bot A close
  together; what Bot A does with two `/speak` calls at once is its own behaviour.
- **The probe overwrites the Claude client's prose stats slot.** Harmless today — a turn copies
  its stats right after its own call, and no turn completes during a pause.
- **From the review of this round (2026-11-14), not fixed:** a turn attempted during a pause
  still drains the queues and runs the RAG refresh before the client refuses it (one embedding
  per mic release; a pre-check would change a line count an existing test asserts). A return
  while the game is frozen (Esc) starts no turn — the kept lines wait for the next player
  line, as dice results do. "The turn was kept" reaches the cog as a session flag, not in
  the turn's return value. Dice results and GM notes of two turns in flight can swap order.
  A turn whose call began during a pause and fails after it ended is kept without a new ⏸.
  `ON_FAILURE` exists in `config.py` and in `failover.py` (a test holds them equal).

Live-unverified.

## Amendment (2026-11-14, fifth) — the narration prompt reaches the prompt cache

The live run of 2026-11-14 logged `cache=0` on all 33 narration turns (prompt 14–21k tokens,
`first_audio` 8–13 s) while the Haiku calls of the same turns showed cache reads (D142).

**Diagnosis.** The stat was right; the cache was really missed. Two pieces of evidence:

- *The request the CLI builds* (CLI 2.1.325, captured by pointing `ANTHROPIC_BASE_URL` at a
  local endpoint that records the body and answers 400, so no model call was made): `system` is
  three blocks — a billing header, the SDK identity line, and **our whole system prompt as one
  block** — and the CLI puts a 1-hour cache breakpoint on the identity line, on our block and on
  a closing environment message after the user prompt. A cache entry therefore exists only for
  "everything up to the end of our system prompt"; one changed byte in it is a miss. A DM turn's
  system prompt changes every turn after persona and recap (the scene card with its guidance
  cadence, state, NPC memory, RAG). The Haiku hits were inside one call: a schema call takes two
  requests (prose, then the tool call), and the second reads what the first wrote.
- *Four short Opus calls through this client* (two consecutive turns per layout, 60-token cap):
  old layout `cache_read=0 cache_write=12941` on both turns — the whole prompt was written to the
  cache every turn and never read; new layout, second turn `cache_read=10877 cache_write=2063`.

**Decided.**

- `assemble_system_prompt` returns a `SystemPrompt` — a `str` subclass that also carries its
  `stable` head (persona + recap). Every reader, Ollama included, sees the same string as before.
- `ClaudeClient` (`split_system`) writes only that head into the system-prompt file and puts the
  rest, verbatim and in the same order, in front of the prompt (before the transcript header).
  The model reads the same text in the same sequence; what moved is the boundary between the
  system block and the user message. Any other string — classifiers, recap, `!rules` — goes
  through unchanged, and str operations drop the head, so a suffixed prompt is sent whole.
- Order-sensitive wording checked: the persona refers only to the campaign overlay "unten",
  which stays in the system part. Nothing refers to the state or RAG as "im Systemprompt".
- The system-prompt file is written with LF line endings; text mode on Windows had written CRLF
  into what the model reads, while the prompt over stdin was plain LF.
- The stats carry `cache_write` and the `[latency]` line shows `cache_w=` after `cache=`: a
  `cache=0` alone could not tell "nothing cached" from "written every turn, never read". The
  `[aux]` line is unchanged (the evening's measurement reads its format).

**Not changed, noted.** The recap invalidates the head once per auto-recap (one full write).
The static character sheets ride inside the state block, so they are re-sent fresh every turn;
moving them into the head would cache another few thousand tokens but changes the slice order
of `docs/conventions.md` — a separate decision. The capture also showed what the CLI adds on its
own: a `<system-reminder>` with the account's e-mail address in front of the prompt, the
environment message (temp working dir, date), and a separate small session-naming request on
the narration model before the turn's request. None of them breaks the cache of our head.

Live-unverified: the latency effect (`first_audio`) is not measured yet; the expectation is the
head's ~10k tokens read from the cache instead of processed, from the second turn on.
