# CLAUDE.md

Instructions for Claude Code in this repository. Read first, every session.

## Session ritual

This project runs over many sessions, across different models and effort levels. To
survive context clears and model switches, state lives on disk:

**At the start of every session, read in this order:**
1. This file (`CLAUDE.md`) — conventions
2. ONLY the `## State header` at the top of `progress.md`
3. The highest-numbered file in `docs/decisions/` — the most recent decision
4. `docs/lessons/README.md` — skim the one-line lesson summaries; open a full lesson only
   when its summary touches the task

Then state in two or three sentences: where we are, what we're about to do. Don't touch
files until that handshake is done. Full `progress.md`, the decision log, and older ADRs
are on-demand reads when the task touches them. When you have enough to act, act — don't
re-derive established facts or re-litigate decided ADRs.

**Before touching a subsystem or starting a phase:** the decision log and the
**phase → ADR map** in `progress.md` remain the routing mechanism — consult them to find
the governing ADR(s) and read those **before** implementing. On-demand, but mandatory for
that case. This is how the older ADRs (001–004) get used — not just the newest one.

**WIP limit: max 3 open live gates.** A round that would open a FOURTH doesn't start — the
next session is a live-verification session; say so in the handshake and propose the
shortest script to close the oldest gates. Exempt: rounds that open no new live gate (dev
tooling, refactors covered by suite + dm-eval). Tobi can explicitly override
("WIP-Override") when a live session isn't schedulable — note the override in the wrap-up.

**Other documents — read on demand, NOT every session:**

| File | When to read |
|---|---|
| `architecture.md` | Only when the task touches design. Skim the relevant section; don't re-read top to bottom. |
| `roadmap.md` | When transitioning into a new phase, or when the user asks "what's the goal of Phase X?" |
| `SETUP.md` | In Phase 0 or when a setup/install step comes up (Ollama, Discord tokens, cuDNN DLLs, PDFs, fresh-machine copy). Point Tobi at the open items there — the agent cannot do them itself. |
| Older ADRs in `docs/decisions/` | When working in the area they cover. Don't guess which — the decision log + phase→ADR map in `progress.md` tell you which ADR governs the current decision/phase (e.g. ADR 003 before touching turn-taking, ADR 005 before the dice engine). |
| `docs/conventions.md` | When working in a module (rules/memory/rag/tts/voice) or on testing/runtime/troubleshooting/commit-style details. Holds the per-module how-tos moved out of this file. |
| `docs/progress-archive.md` | Only when you need history — old `## Last session` logs, completed-phase `VERIFY EVIDENCE`, or resolved `## Open questions`. Never needed for normal work. |
| Individual files in `docs/lessons/` | When their one-line summary in the lessons README (session-start read #4) matches the task at hand. |

Eagerly loading everything fills the context window before useful work starts. Be selective.

**While working:**
- Ground every done-claim in a tool result from this session (pytest, ruff, dm-eval exit
  code). Anything not live-verified is labeled live-unverified.
- Before committing a round that touches orchestrator / llm helpers / marker / roll_router /
  delivery verdicts: dispatch a fresh-context verifier subagent that reads only the diff,
  the governing ADR, and the golden rules. Resolve or explicitly defer each finding before
  commit. Skip it when a /code-review round over the same commits is planned — one review
  layer, not two.
- Delegate independent subtasks to parallel subagents (progress rotation, doc-drift sweeps,
  golden regeneration, the verify above). ADR write-ups stay in the main thread.
- Effort is the primary dial (Fable 5): default high; xhigh for unknowns, integration
  debugging, subtle async/state bugs, and persona prose; medium for clearly specified
  deterministic modules and doc sweeps; step down only after seeing quality hold. The
  per-phase model table in `roadmap.md` is retired — don't remind Tobi of per-phase
  recommendations.
- When Tobi describes a problem or thinks out loud, the deliverable is your assessment —
  report and stop; don't build until asked. Pause only for: destructive actions, real
  scope changes, a live gate only a human can run, or a design fork worth an ADR — then
  ask and end the turn instead of ending on a promise.
- **Record lessons as they happen.** When a correction recurs or an approach is confirmed
  the hard way, write it to `docs/lessons/` (one file per lesson, one-line summary into the
  README index) in the same round. Update the existing lesson rather than creating a
  duplicate; delete lessons proven wrong. Don't record what CLAUDE.md, `docs/conventions.md`,
  or an ADR already holds — link there instead. Decisions stay ADRs; lessons are the
  recurring corrections around them.

**At the end of every working session (before context clear or model switch), without
being asked:**
1. Update `progress.md`:
   - `## Current focus` if the phase changed
   - `## Last session` — what we actually did
   - `## Next concrete step` — the specific next action, not a vague goal
   - `## Open questions` — anything that came up but isn't actionable yet
   - Fill the `VERIFY EVIDENCE` field of the affected phase when a gate was met
   - **Keep it lean (rotation + caps, enforced every wrap-up, not "eventually"):** when you
     prepend a new `## Last session` entry, move the *previous* one to
     `docs/progress-archive.md` (`## Last session (Verlauf)`) — keep only the newest 1–2
     live. Rotate ✅-resolved `## Open questions` and just-completed phases (full
     `VERIFY EVIDENCE`) there too, leaving a one-line summary live. Caps: State header max
     25 lines; `## Current focus` max 2 blocks live (rotate in the same edit that adds a
     new one); decision-log rows max 2 lines ("what + one-clause why + → ADR NNN" — the
     rationale lives in the ADR; rows without an ADR are exempt); `progress.md` over 400
     lines → rotate rotatable content (archived history, old Current-focus blocks) before
     committing — the exempt no-ADR decision-log rows don't count against this. `## Decision
     log` and the `### Phase → ADR map` stay fully live.
2. On a non-trivial decision (real trade-off, alternatives weighed), create the
   next-numbered ADR in `docs/decisions/` (format in the README there).

Current-focus blocks and wrap-up messages are for a fresh reader: one plain sentence on
what changed and why it matters for play, then evidence, then at most five lines of
mechanism — the rest goes in the ADR. No arrow chains, no hyphen-stacked compounds.

If the user types `wrap up` or `update progress`, that is the explicit trigger for the
end-of-session step. If a session ends without an explicit hint: do it anyway — silence
here is the failure mode that breaks continuity across sessions.

## What this project is

**Cogitator** (codename): a local, **system-agnostic** AI game master for tabletop RPGs,
voice-only over Discord, German play language. You load a ruleset/adventure as PDFs; the DM
learns the setting (RAG) and the mechanics (a per-system **profile** it proposes from the
rulebook, §9) and runs the game. Two discord.py bots: **Bot A** (existing music bot, output
via the `/speak` bridge — separate repo) and **DMbot** (this repo, the DM brain: voice
receive, VAD, STT, LLM orchestration, TTS, RAG, memory, rules engine, Discord UI).
Everything local — no cloud, no API costs.

**First campaign:** Warhammer 40,000 / Imperium Maledictum in the Eisenhorn grimdark tone —
but that's just the first system profile + tone overlay, *not* baked into the DM.

Full design in `architecture.md`; plan in `roadmap.md`. **If a design decision is
unclear, `architecture.md` wins — and if you change a decision, update `architecture.md`
in the same change.**

> Language convention: docs and code are **English**. Game content — the generic GM persona
> (`prompts/dm_core_de.md`), per-campaign tone overlays, and anything the DM says — stays
> **German**.

## Golden rules

1. **Read before write.** `grep`/read the relevant module before editing. Grep-first
   workflow to keep context lean.
2. **Dice = code, narration = LLM.** This is the project's signature. Dice rolling (RNG)
   *and* their resolution (success, degrees, damage) are computed by the generic engine
   `dmbot/rules/engine.py` applying the **active system profile** (`data/systems/<system>.json`)
   — **never** the language model. The LLM *requests* a test (via marker), the engine rolls
   and reports back. Never let the LLM invent dice results or rulings.
3. **Memory split.** JSON world state = hard facts (HP, inventory, NPCs, flags), advanced
   **deterministically by code**. Recaps = narrative thread, by the LLM. Never write hard
   state from LLM free text.
4. **Feedback protection is non-negotiable.** Bot A's user-ID filter in the sink (layer 1)
   must **always** be present — never remove it "for debugging", or DMbot transcribes its
   own DM voice. Pausing VAD while Bot A speaks is layer 2.
5. **Two-bot isolation.** Bot A stays minimal: only `/speak` + status. All complexity
   (voice receive, pipeline) lives in DMbot. The bridge is the **only** contact surface.
   Never let DMbot logic leak into the music bot.
6. **Layer by layer, with a gate.** Voice/VAD/STT/LLM/TTS/RAG/memory are verified one at
   a time (see the verification gates in `roadmap.md`) before the next phase begins. Don't
   couple what is separately testable.
7. **System-agnostic, learned from PDFs.** The DM isn't tied to one game. Setting/lore/
   adventure come from RAG; the mechanics come from a per-system **profile** the DM proposes
   from the rulebook and the user confirms (§9). Rule questions are answered from retrieved
   rulebook chunks, not from the model's gut. IM is just the first profile.
8. **German is the play language.** Generic GM persona (`prompts/dm_core_de.md`) and
   per-campaign tone overlays in German. Code/logs in English.
9. **No new heavy dependencies without a note.** If you add one, justify it in the
   commit/PR description and in `architecture.md` §3.

## Repo layout

This is the **DMbot repo**. Bot A is a separate repo (the music bot) — not here.

```
dmbot/          the DM bot
  runtime.py    SessionRuntime — shared session state/services, injected into every cog (ADR 029)
  voice/        recv, resample, VAD + the Discord cogs (voicecog / dicecog / dmcog + scenecog / lorecog / clockcog / timecog / chekhovcog, ADR 039/047/048/050) + delivery.py (the answer→audio turn-delivery pipeline, ADR 035)
  stt/          faster-whisper wrapper + segments.py (pure hallucination guard)
  tts/          piper + xtts (Coqui XTTS v2) wrappers
  llm/          Ollama client, prompt building + orchestrator's extracted pure helpers (sanitize / echo_guard / director_msgs / stream_assembler, ADR 034; prompt_assembly = system-prompt order owner, ADR 038; consistency = deterministic pre-delivery guard, ADR 045)
  rag/          ingestion + retrieval + profile bootstrap
  memory/       JSON state + recaps + gametime.py (pure in-game-time helpers, ADR 048) + chekhov.py (loose-thread list, ADR 050)
  rules/        engine.py (generic) + combat.py (attack/Warp resolution, ADR 037) + profile loader (+ tests)  ← deterministic core
  discord_ui/   buttons, turn-order view
  tools/        dev CLIs via [project.scripts]: sync_check (`uv run dm-sync`, D89/D90) + eval_replay (`uv run dm-eval`, golden-transcript regression replay, ADR 046 — goldens in tests/golden/)
  orchestrator.py   the DM brain (history + buffer → LLM)
  bridge.py     HTTP client to Bot A's /speak
  logsetup.py   console (green chat) + file logging
data/           committed seed/reference: systems/ (profiles), lore/ + rules_de/ (curated DE setting/rules), party/ (party JSONs), sessions/_example + the live channel's characters.json. Generated/local (git-ignored — see the .gitignore allowlist): pdfs/ (RAG sources), adventures/ (scene cards, bought-book derivatives), sessions/<id>/ state+recaps, vectordb/ (rag.db)
prompts/        dm_core_de.md (generic GM persona) + campaign_tone_de.md (campaign overlay)  — GERMAN, game content
docs/           decisions/ (ADRs), lessons/ (recurring corrections; README = the skimmed index), how-to-*.html + character-creation-prompt.md (player guides). SETUP.md lives in the repo root.
```

## Bot A — the bridge (separate repo)

Bot A is the existing music bot in its **own repo** (`Pr0degie/musicbot`) — **never edited from
here** (two-bot isolation, golden rule #5). DMbot calls its `POST /speak` (plays a WAV and
**blocks until playback ends** = the resume signal) and `GET /health`. Full contract + bridge
details: `architecture.md` §3 and **`docs/conventions.md`**.

## Key gotchas

Broad footguns. Module conventions (DMbot/rules/memory/rag), testing/runtime details,
troubleshooting and style live in **`docs/conventions.md`** — read it when you work in that area.

- **Windows runtime:** never hardcode POSIX paths — WAV temp via `tempfile.gettempdir()`, **never `/tmp`**.
- **Never hardcode `OLLAMA_HOST`** (env/config) — the 4070→5080 switch stays a one-liner.
- **Audio reality:** per-user PCM arrives 48 kHz **stereo** → resample to **16 kHz mono** before
  anything else, or you get a garbage transcript (not an error).
- **Commit messages:** imperative, scoped — `dmbot(stt): resample to 16k mono`, `rules(im): success-level calculation`.
- **Tests:** `uv run --with pytest python -m pytest` (pytest isn't in the venv). Python 3.12, uv (no direct `pip`; `uv add`).
- **Two processes, two tokens** — both bots must join the voice channel; tokens in `.env`, **never commit them**.
