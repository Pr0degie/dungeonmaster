# PRD — A second LLM backend: Claude (Opus) via the Agent SDK, Ollama kept intact

**Status:** built (steps 1–5), live gate open — where this text and ADR 061 disagree, the ADR's
"Amendment (2026-10-06, build)" wins · **Date:** 2026-09-02, amended 2026-10-06 · **Round:** D116 (Phase A of three)
**Source:** Tobi's competitor survey of 2026-09-02 (DungeonsDeep, Friends & Fables, AI Realm,
RoleForge, VoxDungeon, AI Dungeon) and five question rounds. The one finding that mattered: the
features are at parity or ahead; the quality gap at the table is the model. Story/answer quality is
Tobi's stated number-one pain.
**Amended 2026-10-06** after a fresh repo review against the target vision
(`docs/plans/target-vision.md`): the evening is isolated from the 17 parked gates, the marker
probe covers `<<ERLEDIGT>>`, and truncation by the output cap is measured. See *Amendment
2026-10-06* at the end; the changed places are marked inline.
**Governing ADRs:** 002 (LLM host is one env switch), 014 (roll router), 017 (streaming +
`finalize_answer` parity), 027 (context budget + auto-recap), 034 (pure `llm/` helpers), 042
(sampling defaults on the client instance), 046 (replay eval), 057/058 (scene + fact classifiers).
**Lessons that bind this round:** `sampling-defaults-leak-into-aux-calls`,
`unwired-knobs-and-silent-fallbacks`, `incidents-become-preflights`,
`optional-layers-fail-open-core-fails-loud`, `parity-by-construction`,
`mandatory-decisions-need-a-separate-classifier`, `one-variable-per-live-run`.
**New ADR from this round:** 061 (second backend behind one client seam).
**Follow-up phases (not this round):** 12 DM tools non-blocking, 13 blocking tool turn, 14 round
mode + enemy turns + zone combat — see Part 2a in `roadmap.md` and *Further Notes* below.

---

## Problem Statement

Two debug runs and every ADR since 016 tell the same story: the deterministic guards work, the
persona does not hold on a 12B model, and each round adds another code guard around a model
tic (ADR 060 says it in its own Context). The table's complaint is not a missing feature; it is
that the DM writes generic, repetitive, sometimes meta prose. Nemo is the ceiling.

Constraints that shape the fix:

- **No API key.** Tobi will not pay per token; price/performance is bad for a hobby table. He has
  a **Claude Max 5x** subscription and uses Claude Code daily.
- **The subscription can run the Agent SDK today.** Anthropic announced a separate SDK credit for
  2026-06-15, then paused it: as of the Help Center note of 2026-06-16, *"Claude Agent SDK,
  `claude -p`, and third-party app usage still draw from your subscription's usage limits."* The
  policy page says OAuth is for *ordinary individual use* and that products should use an API
  key. DMbot is a private bot on Tobi's own machine, not a product — but friends' inputs pass
  through his seat, and Anthropic reserves the right to change the rule. **Therefore the Claude
  path must never be the only path.** Ollama stays fully working; switching back is one env line.
- **The bot must run on Tobi's machine** when the Claude backend is on (an OAuth token on someone
  else's machine is credential sharing, which is the one clearly forbidden case). It only ever
  moved to Timo's box for VRAM; with the LLM in the cloud the reason is gone.
- **Ollama does not go away.** The retriever embeds with `bge-m3` through `config.ollama_host`,
  and Ollama is the fallback. What goes away is Nemo *resident in VRAM* during play — Ollama loads
  lazily and unloads on idle — which frees the 4070 for `TTS_DEVICE=cuda` (the old Workstream A).

## Solution

One seam, two clients. Extract the client surface the brain already uses into a `LLMClient`
protocol, keep `OllamaClient` byte-identical behind it, and add a `ClaudeClient` that speaks the
same surface through the `claude-agent-sdk` (which drives the installed `claude` CLI on Tobi's
OAuth login — no API key anywhere). A `FailoverClient` wraps both so a Claude failure or rate
limit degrades loudly to Ollama instead of killing a turn. `DM_LLM_BACKEND=ollama|claude` picks
the primary. Nothing above the seam changes: orchestrator, routers, extractors, delivery,
markers, sanitizer, tests and `dm-eval` see the same `chat` / `chat_stream` / `last_stats`.

Model tiers are decided **inside** `ClaudeClient` from a signal the calls already carry:
a call with a JSON-schema `format` is a classifier or extractor → aux model (Haiku); every other
call is prose → narration model (Opus). Zero call-site churn, and the tiers are two env knobs.

**What A must measure for B.** The `[latency]` line gains the SDK's spawn-to-first-delta gap and
the usage counters; the live gate below pastes them. Those numbers, plus the marker probe and the
truncation count, decide how Phases 12/13 are shaped (see *Further Notes*).

---

## User Stories

**Operator (Tobi)**

1. As the operator, I flip `DM_LLM_BACKEND=claude` in `.env`, start the bot as usual, and the boot
   log tells me in one line whether the Claude CLI is found, logged in, and which two models will
   be used — or exactly what to fix.
2. As the operator, I flip the same line back to `ollama` and get the pre-round bot back, bit for
   bit — same tests, same goldens, same knobs.
3. As the operator, if I accidentally have `ANTHROPIC_API_KEY` in my environment, the bot refuses
   to start the Claude backend and tells me why (the CLI would silently bill the API instead of
   the subscription).
4. As the operator, I see one `[latency]` line per turn with the Claude token counts and the SDK
   spawn overhead, so I can compare it against the Nemo baseline.
5. As the operator, I can type `!backend` to see which backend answered the last turn and whether
   failover is active, and `!backend ollama` / `!backend claude` to force one for this session.
6. *(amended)* As the operator, I see a WARNING whenever a narration answer was cut off by the
   output cap, so I can tell "the model ignored the marker" apart from "the cap cut the marker".

**Table**

7. As a player, when Claude is unreachable or rate-limited mid-session, the DM keeps answering
   (from Nemo) and the chat shows **one** ⚠ line saying so and until when — not one per turn, not
   silence.
8. As a player, nothing about the buttons, panel, dice or scene flow changes this round.

**Developer (Claude Code)**

9. As the next agent, I find the backend choice in `config.py`, the seam in `llm/client.py`, the
   Claude specifics in one file `llm/claude_client.py`, and the failover in one file
   `llm/failover.py`; the CLAUDE.md module map lists all three.
10. As the next agent, every test that existed before this round passes unchanged (0 test edits),
    and `uv run dm-eval` exits 0 on both goldens.

---

## Implementation Decisions

### The seam (`dmbot/llm/client.py`)

- Add a `typing.Protocol` **`LLMClient`** with exactly today's surface: `model: str` (property),
  `last_stats: dict | None`, `async chat(system, messages, *, options=None, format=None) -> str`,
  `async chat_stream(system, messages, *, options=None) -> AsyncIterator[str]`,
  `async aclose()`. Structural typing only — `OllamaClient`, `PlaybackClient` (eval replay) and
  every `_Fake*Client` in `tests/` already satisfy it without inheriting anything.
- `OllamaClient` is **not edited** beyond the type annotation on the seam consumers. Zero
  behaviour change; the test-edit count is the signal (`byte-exact-moves-stepwise-gates`).
- Consumers annotate the parameter as `LLMClient`: `DMBrain.__init__`, `npc_memory`, `chekhov`,
  `fact_router`, `scene_router` call sites. Annotation only.

### `ClaudeClient` (`dmbot/llm/claude_client.py`, new)

Built on `claude_agent_sdk` (PyPI `claude-agent-sdk`, verified 0.2.151 exposes everything named
here). Justify the dependency per golden rule #9 in `architecture.md` §3: it is the only way to
use the subscription without an API key, and it is optional at import (imported lazily inside the
backend factory, like `xtts`, so the Ollama path never pulls it).

**Statelessness.** Every call is one `claude_agent_sdk.query(prompt, options)` with
`max_turns=1` *(schema calls: 3, see the table)*. `DMBrain` remains the sole owner of history (redo, echo-guard pair removal,
auto-recap compaction, crash restore, D41). `resume`/`continue_conversation` are **not** used.

**Mapping of the `chat` contract onto `ClaudeAgentOptions`:**

| Ours | SDK | Note |
|---|---|---|
| `system` | `system_prompt={"type": "file", "path": …}` | *(corrected 2026-10-06)* Written to a per-call file under the system temp dir: a plain string goes on the command line and outgrows Windows' 32,767-character limit. Still **replaces** the CLI's own coding system prompt; never the preset. → ADR 061 build amendment, "The system prompt goes through a file". |
| `messages` (history + user) | rendered into the single `prompt` string | One labelled transcript block (*corrected 2026-10-06:* `Spieler: …` / `Spielleitung: …`, not the bracketed form — the label guards above the seam only know `<label>:`; last user line last), preceded by a one-line German instruction "Setze die Sitzung fort; antworte nur als Spielleitung." A pure `render_transcript(messages) -> str` helper, unit-tested. |
| `options["num_predict"]` | `env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(n)}` **plus a cut in the client** | *(corrected 2026-10-06)* The env var caps one API request, it is **not** a hard cut: the CLI then asks the model to resume, up to three times, and finally fails the run. The client therefore ends a narration call itself at the first `max_tokens` stop reason. Schema calls get a floor of 1024 tokens. The cut still removes end-of-answer markers — see *Truncation detection*. → ADR 061 build amendment, "The output cap is not a hard cut". |
| `options["temperature"]` | **not available** | Log once at WARNING on first use and ignore. D83's intro temperature is a no-op on Claude; its retry guard (`intro_guard`, D86) still applies. |
| `options["stop"]` | **not available** | The anti-puppeting label cut already exists client-side (`_cut_at_labels`, `StreamAssembler.stopped`); the server-side stop was belt-and-braces. Document in ADR 061. |
| `repeat_penalty`, `repeat_last_n`, `top_p`, `num_ctx` | ignored | Nemo-specific (ADR 042). Silently dropped — they are instance defaults the caller never asked for. |
| `format=<schema>` | `output_format={"type": "json_schema", "schema": schema}` → `ResultMessage.structured_output` | Return `json.dumps(structured_output)` so callers' `json.loads` + validators run unchanged. If `structured_output` is `None`, fall back to the `result` text. *(corrected 2026-10-06)* This is a **tool call**, not a constrained decode: schema calls run with `max_turns=3` (not 1), a 1024-token floor and one appended German system line asking for the call without preamble; a verdict that does not arrive is lost, not a backend error. → ADR 061 build amendment, "Structured output is a tool call". |
| — | `tools=[]`, `allowed_tools=[]`, `permission_mode="dontAsk"` | No tools this round. |
| — | `thinking={"type": "disabled"}` | Latency. Phase 12 may revisit. |
| — | `cwd=<empty temp dir>`, `setting_sources=[]`, `skills=None`, `plugins=[]` | **Isolation.** Otherwise the CLI loads *this repo's* `CLAUDE.md`, `.claude/skills` and settings into the DM's context. Enumerate every source (`isolation-must-enumerate-every-artifact`); assert in a test that the options carry all four. |
| — | `env` also sets `CLAUDE_AGENT_SDK_CLIENT_APP="cogitator-dmbot/<version>"` | Identifies the app in the User-Agent. |
| — | `model=` per tier, `fallback_model=` optional (`CLAUDE_MODEL_FALLBACK`, default unset) | Anthropic-side fallback (e.g. opus → sonnet on outage) is separate from our Ollama failover. |

**Model tiers.** `format is not None` → `config.claude_model_aux` (default `haiku`); otherwise
`config.claude_model_narration` (default `opus`). This routes roll/scene/fact routers, the NPC
memory extractor and the Chekhov extractor to Haiku, and narration, `!intro`, recap/summarise,
`!rules <frage>`/`!lore <frage>` answers to Opus. Documented as the tier rule in the module
docstring; a later explicit `tier=` kwarg is allowed but not needed now.

**Streaming.** `chat_stream` uses `query(..., include_partial_messages=True)` and yields the
`text_delta` strings from `StreamEvent.event` (`content_block_delta` with `delta.type ==
"text_delta"`). Early close by the consumer (`agen.aclose()`, the pause/stop-label abort) must
terminate the subprocess — use the async generator's `finally` to close the SDK stream; test with
a fake transport that records the close. `ThinkingBlock`/`tool_use` events are ignored.

**`last_stats` parity.** From `ResultMessage.usage` / `model_usage`: `prompt_eval_count =
input_tokens + cache_read_input_tokens + cache_creation_input_tokens`, `eval_count =
output_tokens`, `num_ctx = config.claude_num_ctx`. Extra keys, ignored by Ollama consumers:
`cache_read`, `spawn_ms` (time from `query()` call to the first `SystemMessage`/first delta),
`api_ms` (`duration_api_ms`), `model`, *(amended)* `truncated` (bool, see below).
`turn_timing.py` appends `spawn=…ms cache=…` when present, and `cut` when `truncated` is true.

**Truncation detection *(amended 2026-10-06)*.** Every end-of-answer marker (`<<ERLEDIGT>>`,
`<<UHR>>`, `<<ZEIT>>`, `<<ORT>>`) sits exactly where `CLAUDE_CODE_MAX_OUTPUT_TOKENS` cuts — the
same failure ADR 057 found for `<<ORT>>` on Nemo. Set `last_stats["truncated"]` from the result's
stop reason if the SDK exposes one (check the installed `ResultMessage` fields; do not guess a
name), otherwise from `output_tokens >= the cap`. Log one WARNING per truncated narration turn
(`✂ Antwort an der Ausgabegrenze abgeschnitten (N/N Tokens)`). Logging only; no retry, no
behaviour change. If the SDK gives neither signal, say so in the ADR-061 amendment.

**`claude_num_ctx` is a nominal budget, default 24576 — the same as Ollama.** The auto-recap
(ADR 027) and the `[ctx]` warning (D36) fire on `prompt_eval / num_ctx`; on a 200k window they
would never fire, history would grow unbounded, and every turn would cost the whole campaign in
tokens. Keeping the nominal budget equal keeps recap cadence and the context diet identical across
backends (parity by construction) and bounds subscription usage. Tunable via `CLAUDE_NUM_CTX`.

**Errors.** Raise a single `LLMBackendError` (new, in `client.py`) wrapping
`CLINotFoundError`, `CLIConnectionError`, `ProcessError`, `ResultMessage.is_error`, and a
`RateLimitEvent` with `status == "rejected"`. A `RateLimitEvent` with `allowed_warning` is logged
at WARNING with `utilization` and `resets_at` — the operator's early signal.

### `FailoverClient` (`dmbot/llm/failover.py`, new)

- Wraps `primary` and `fallback` (both `LLMClient`). On `LLMBackendError` from the primary:
  log ERROR with the cause, set `degraded_until = now + config.llm_failover_cooldown_s`
  (default 600), re-issue the **same** call on the fallback, and set `self.degraded_event`
  (an `asyncio.Event` the DMCog awaits to post the one ⚠ line). While degraded, calls go straight
  to the fallback; after the cooldown the next call tries the primary again (and a recovery is
  logged + posted once). `last_stats` and `model` proxy to whichever client answered; the stats
  dict gains `backend: "claude"|"ollama"`.
- Streaming failover only **before the first delta** (nothing spoken yet). After the first delta
  the existing mid-stream degradation in `_stream_and_store` applies unchanged — spoken audio
  cannot be retracted.
- The fallback is not optional infrastructure: it announces itself (lesson
  `unwired-knobs-and-silent-fallbacks`) and never swallows the error silently.
- `!backend` (DMCog): shows primary/fallback names, degraded state and until-when, the backend of
  the last turn; `!backend claude|ollama|auto` forces or restores. Session-scoped, not persisted.

### Config (`dmbot/config.py`, `.env.example`)

```
DM_LLM_BACKEND=ollama            # ollama | claude   (primary; the other is the fallback when claude)
CLAUDE_MODEL_NARRATION=opus      # prose: DM turns, !intro, recap, rules/lore answers
CLAUDE_MODEL_AUX=haiku           # constrained-JSON side calls: routers + extractors
CLAUDE_MODEL_FALLBACK=           # optional Anthropic-side fallback model (SDK fallback_model)
CLAUDE_NUM_CTX=24576             # nominal budget for auto-recap / [ctx] warning (parity with Ollama)
CLAUDE_CLI_PATH=                 # optional; default = `claude` on PATH
CLAUDE_ALLOW_API_KEY=0           # 1 = permit a set ANTHROPIC_API_KEY (bills the API!)
DM_LLM_FAILOVER_COOLDOWN_S=600
```

Invalid `DM_LLM_BACKEND` → config error at boot, not a silent default. All new knobs are read
in `Config.from_env()` and **proven wired** by a test that constructs the client from config.

### Wiring (`dmbot/runtime.py`)

A small factory `build_llm_client(config) -> LLMClient` in `llm/__init__.py` (or `client.py`):
`ollama` → `OllamaClient(...)` exactly as today; `claude` → `FailoverClient(ClaudeClient(...),
OllamaClient(...))`. `SessionRuntime` calls the factory instead of constructing `OllamaClient`
inline. The retriever's `host=config.ollama_host` is untouched (embeddings stay on Ollama).

### Preflight (`dmbot/llm/preflight.py`)

`check_claude(config) -> bool`, mirroring `check_ollama`: (1) `ANTHROPIC_API_KEY` set and
`CLAUDE_ALLOW_API_KEY != 1` → ERROR and `False` (refuse; the CLI's credential precedence puts the
key above the OAuth login); (2) CLI found (`cli_path` or PATH) and `--version` runs; (3) a
minimal `query("ping", model=aux, max output 8, tools=[])` completes without `is_error` →
INFO with both model names *(built 2026-10-06: the narration model is pinged too, and the line
names both outcomes)*. Never raises. When `check_claude` fails at boot with backend
`claude`, the factory still builds the failover pair — the table gets Nemo, the log says why.
`check_ollama` keeps running on both backends (embedder + fallback).

### Ops and docs

- `start_dmbot.bat`: Ollama warm-up unchanged (bge-m3 must be resident; Nemo may be).
- `SETUP.md`: new section *Claude backend* — *(corrected 2026-10-06: the **native** installer
  `irm https://claude.ai/install.ps1 | iex`; the SDK refuses npm's `claude.cmd` on Windows)* ~~Node.js + `npm i -g @anthropic-ai/claude-code`~~,
  `claude` login once **on the Windows bot machine** (browser OAuth; a login inside WSL does not
  count, the bot runs on Windows, D16), verify with `claude -p "hi"` from the same shell that
  starts the bot; the API-key warning; `TTS_DEVICE=cuda` now recommended on the 4070 when
  `DM_LLM_BACKEND=claude`.
- `CLAUDE.md`: "Everything local — no cloud, no API costs" becomes "Local by default; an optional
  Claude backend via the operator's own subscription (ADR 061), never an API key"; module map
  gains `claude_client.py`, `failover.py`, the `LLMClient` protocol, and the tier rule.
- `architecture.md` §3: dependency note (golden rule #9) + the backend seam; §LLM: the tier rule
  and what is unmappable (temperature, stop).
- `docs/conventions.md` *Runtime* + *When you're stuck on reality*: "LLM not answering?" gets the
  Claude variant (`claude -p "hi"` from the bot's shell, `claude auth status`, check for a stray
  `ANTHROPIC_API_KEY`).
- `.env.example`: the block above, commented.
- Roadmap: Part 2a (Phases 11–14) is already committed with this PRD.

### Kill switches

`DM_LLM_BACKEND=ollama` restores the pre-round bot. `!backend ollama` does it live for the session.
`CLAUDE_ALLOW_API_KEY` defaults to refusing a set API key.

---

## Testing Decisions

- **0 edits to existing tests** and the suite stays green — the signal that the seam is
  behaviour-neutral for Ollama. Currently 1090.
- **`uv run dm-eval`** exits 0 on both goldens before and after (PlaybackClient satisfies the
  protocol as-is).
- **New unit tests, all with a fake SDK** (monkeypatch `claude_agent_sdk.query` to an async
  generator that yields scripted `SystemMessage` / `StreamEvent` / `AssistantMessage` /
  `ResultMessage` objects — real SDK dataclasses, no subprocess):
  - option mapping: `num_predict` → env var; `format` → `output_format`; tier selection by
    `format`; isolation set (`cwd` temp, `setting_sources=[]`, `tools=[]`, thinking disabled) —
    asserted on the captured `ClaudeAgentOptions`;
  - `render_transcript`: order, labels, last user line last, empty history;
  - `chat` with structured output returns `json.dumps(structured_output)`; with `None` returns
    `result`;
  - `chat_stream` yields only `text_delta` strings, ignores thinking/tool events, sets
    `last_stats` from `ResultMessage`, and closes the stream on early `aclose()`;
  - `last_stats` arithmetic (prompt_eval = input + cache read + cache creation);
  - *(amended)* truncation: a result at the cap sets `truncated=True` and logs one WARNING; a
    result below the cap sets `False` and logs nothing;
  - errors: `is_error`, `CLIConnectionError`, rejected `RateLimitEvent` → `LLMBackendError`;
    `allowed_warning` → WARNING log, no error;
  - failover: primary raises → fallback answers, `degraded_until` set, event set once; during
    cooldown primary not called; after cooldown primary retried; streaming failover only before
    the first delta; `backend` key in stats;
  - preflight: API key set → `False` + ERROR unless allowed; CLI missing → `False`; ping ok →
    `True`;
  - config: backend enum validation, every knob read (`unwired-knobs` — construct from env and
    assert on the client).
- **Lint gates** as usual (`ruff --select F`, pre-commit). Verifier subagent per CLAUDE.md for the
  orchestrator-adjacent diff (annotations only, but it touches the seam).
- **Live gate (one evening, isolated — amended, see *Further Notes*):**
  0. *(amended)* Evening setup: debug campaign, Claude backend; the optional layers are **off**
     for this evening (`DM_CONSISTENCY_GUARD=0`, `DM_NPC_MEMORY=0`, clocks/agendas/Chekhov/overlay
     off via their switches or `!automatik`); `DM_FLAG_CONFIRM=0`. Everything else default.
  1. Boot with `DM_LLM_BACKEND=claude`: log shows `Claude preflight OK — opus / haiku` and
     `Ollama preflight OK` (bge-m3). `nvidia-smi` during play: XTTS on cuda, no Nemo resident.
  2. `!join` → `!start` → five spoken player turns. Paste five `[latency]` lines (`first_audio`,
     `spawn`, `ctx`, `cache`). Compare against the Nemo baseline lines from 2026-08-22.
  3. One dice button from the Haiku router, one auto scene change (ADR 057), one fact extraction
     (ADR 058) — i.e. the classifiers work on the aux tier.
  4. `!wrap up` → recap in German, stored.
  5. Failover: set `CLAUDE_MODEL_NARRATION` to a nonsense name (or pull the network), run a
     turn → one ⚠ line, Nemo answers (cold load accepted); `!backend claude` → Opus again.
  6. Subscription usage: note the claude.ai usage meter before and after the evening.
  7. *(amended)* Marker probe for Phase 12, two parts, a few turns each:
     a. `DM_ROLL_ROUTER=0` → does Opus place a correct `<<TEST …>>` marker where a test is due?
     b. With `DM_FLAG_CONFIRM=0` (already set): when the group visibly completes an opportunity
        of the scene card, does a correct `<<ERLEDIGT id>>` arrive and get applied?
     Record yes/no + the raw marker for each.
  8. *(amended)* Truncation count: how many narration turns logged `✂` out of all turns. Paste the
     number. If it is more than a rare exception, the marker probe in 7 is not conclusive.
  9. The table's verdict on prose quality — three sentences from each player, verbatim, into the
     findings doc. That is the actual gate.

---

## Out of Scope

- SDK tools / MCP — Phase 12/13 (tool list in `roadmap.md` Part 2a).
- Revisiting D40's router timing. With Claude the classifiers no longer serialise behind the
  narration on one GPU, so the router could fire at turn start; that is a flow change, Phase 12.
- A persistent `ClaudeSDKClient` session per DM turn to avoid per-call spawn — only if A's
  `spawn` numbers say the overhead matters.
- Prompt-caching tuning (stable prefix ordering in `assemble_system_prompt`) — measure first.
- The Mistral Small 24B taste test on the 5080 (Carry-over #1) — independent; still worth doing
  as the local path's own upgrade.
- Any change to markers, sanitizer, delivery modes, dice, panel, memory. Nothing above the seam.
- Removing Nemo-specific knobs or guards. They stay wired for the Ollama path.
- *(amended)* Fixing the `<<ERLEDIGT>>` path and removing the persona's "remind the group"
  instructions. Both are real defects found in the 2026-10-06 review (`target-vision.md`), and
  both are deliberately **not** in this round: one variable per live run. They are the core of
  Phase 12.

## Further Notes

- **On the WIP override *(amended 2026-10-06, replaces the open question of 2026-09-02)*.**
  Decided: the evening runs on Claude and is **isolated**. The seventeen gates stacked under the
  2026-08-23 WIP override are **parked**, not carried into this evening — they were specified
  against Nemo, and verifying them on a different model in the same evening would make every
  failure unattributable (`one-variable-per-live-run`). The optional layers they cover are
  switched off for the evening (live gate item 0). After the evening, each parked gate is
  re-triaged against the findings: kept, rewritten for the tool path, or dropped. `progress.md`
  records the parking.
- **On `mandatory-decisions-need-a-separate-classifier`.** This round keeps every classifier a
  separate call, now on Haiku. The lesson was learned on 12B/gemma3; whether Opus obeys inline
  markers is exactly what gate item 7 probes — but only if gate item 8 shows the cap did not cut
  them.
- **The `<<ERLEDIGT>>` defect *(amended)*.** Opportunity resolution is the one mandatory decision
  still carried only by an inline end-of-answer marker plus, by default, a confirm click nobody at
  the table knows. ADR 057's flag gate depends on those flags, and an unresolved opportunity stays
  under „Möglichkeiten hier" where the persona tells the model to steer toward it — the "reminds
  us and nothing moves" symptom. Phase 12 replaces it with a tool.
- **Sketch Phase 12 — DM tools, non-blocking.** Register in-process SDK tools
  (`claude_agent_sdk.tool` + `create_sdk_mcp_server`, schema enums from the active profile and the
  current scene card so an off-list id is impossible): `request_test`, `manifest_power`,
  `move_scene`, *(amended)* `resolve_opportunity`, `apply_damage` (any combatant, so enemy hits
  on PCs get a mechanical path), `tick_clock`, `advance_time`. Tool returns "angefordert"
  immediately; code validates and applies; turn ends. On the Claude path with `DM_DICE_MODE=tool`
  the corresponding markers and the router are off. Ollama path unchanged. Same round: drop the
  persona's "remind the group" instructions so pressure comes only from clock/deadline events.
- **Sketch Phase 13 — blocking tool turn.** Same tools, but `request_test` awaits the button click
  (asyncio Future, timeout e.g. 120 s → "keine Probe"), the engine result returns as the tool
  result and Opus continues narrating the consequence in the same turn. Delivery learns "stream
  stalls, waits, resumes"; end-of-turn hooks wait for the true end; pause/`!redo` cancel the
  pending future. Open until A: whether cloud latency leaves room for a mid-turn wait.
- **Model choice is a policy exposure, recorded once.** ADR 061 carries the exact Help-Center
  wording and date so the next reader knows what the assumption was when it was made.

## Amendment 2026-10-06

A fresh review of `main` (01a8d14) against the new target vision found the architecture already
matches it closely and isolated two problems this round must not hide. Changes to this PRD:

1. The live evening is isolated: the 17 WIP-override gates are parked, optional layers are off,
   `DM_FLAG_CONFIRM=0` (gate item 0, *Further Notes*).
2. The marker probe covers `<<ERLEDIGT>>` as well as `<<TEST>>` (gate item 7).
3. Truncation by `CLAUDE_CODE_MAX_OUTPUT_TOKENS` is detected and counted (`truncated` stat,
   WARNING, gate item 8), because every end-of-answer marker sits where the cap cuts.
4. SETUP.md must say the `claude` login happens on the Windows bot machine, not in WSL.
5. Phase 12's tool list grows to cover every inline marker plus damage to any combatant; a new
   Phase 14 (round mode, enemy turns, zone combat) closes the remaining vision gaps.

Not changed: the seam, the client mapping, tiers, failover, config, the 0-test-edit gate.
