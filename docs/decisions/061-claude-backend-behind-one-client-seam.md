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
