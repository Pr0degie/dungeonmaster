# CLAUDE.md

Instructions for Claude Code in this repository. Read first, every session.

## Session ritual

This project runs over many sessions and models; state lives on disk. The procedure is in the
`session-ritual` skill — this is the short form.

**Start, scaled to the task:**
- **Always:** this file + ONLY the `## State header` of `progress.md` (`sed -n '/^## State header/,/^## Current focus/p' progress.md`).
  Then say in two or three sentences where we are and what's next; don't touch files before that.
- **Small task** (one feature, a fix, a doc edit, a question): that's all.
- **Subsystem or phase work:** also the governing ADR(s) from the **phase → ADR map** in
  `progress.md` (mandatory there), and skim `docs/lessons/README.md`. Read an ADR's
  `## Decision` and its newest amendment first (grep the headings), the rest only if needed.
- Don't re-derive established facts or re-litigate decided ADRs.

**WIP limit: max 3 open live gates.** A round that would open a fourth doesn't start; the next
session is a live-verification session. "WIP-Override" exception: see the skill.

**Read on demand, never eagerly:** `architecture.md` (design), `roadmap.md` (phase goals),
`SETUP.md` (install steps; point Tobi at its open items), `docs/conventions.md` (module how-tos,
repo layout, testing/runtime/commit-style), `docs/decision-log.md` (grep one `| D## |` row),
older ADRs, single lessons, `docs/progress-archive.md` (history only).

**While working:**
- Label anything not live-verified as live-unverified; a done-claim rests on a tool result from
  this session (pytest, ruff, dm-eval exit code).
- When Tobi describes a problem or thinks out loud, the deliverable is your assessment — report
  and stop. Pause only for destructive actions, real scope changes, a human-only live gate, or a
  design fork worth an ADR.
- **Test-first only where it pays:** deterministic-core rules with real logic get tests first;
  trivial additions get a test alongside; persona/prompts/recaps/RAG/Discord glue are verified by
  the suite, dm-eval and a live run. Details in the `tdd` skill.
- **Search at the data's origin, narrowly.** Grep the specific symbol (`_on_transcript`,
  `_send_with_retry`), not a broad pattern like `.send(` across the package.
- **Record lessons as they happen** in `docs/lessons/` (one file each, one-line summary in the
  README). Update rather than duplicate; don't repeat what this file, conventions or an ADR hold.

**End of every working session, without being asked** (and on `wrap up`): keep `progress.md`
current. A small round updates it **in the same commit as the change** (one `Last session`
bullet + the State header line) — then `wrap up` is only a check. Bigger rounds run the `session-ritual` skill
(rotation, size caps, WIP check, ADR scaffold). Silence here breaks continuity.

## What this project is

**Cogitator** (codename): a local, **system-agnostic** AI game master for tabletop RPGs,
voice-only over Discord, German play language. You load a ruleset/adventure as PDFs; the DM
learns the setting (RAG) and the mechanics (a per-system **profile** it proposes from the
rulebook, §9) and runs the game. Two discord.py bots: **Bot A** (existing music bot, output
via the `/speak` bridge — separate repo) and **DMbot** (this repo, the DM brain: voice
receive, VAD, STT, LLM orchestration, TTS, RAG, memory, rules engine, Discord UI).
Local by default; an optional Claude backend runs over the operator's own subscription
(ADR 061), never an API key — `DM_LLM_BACKEND=ollama` is the way back at any time.

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
- **LLM backends sit behind one seam (ADR 061).** `llm/client.py` holds the `LLMClient` protocol
  and `OllamaClient` (do not edit it for Claude's sake); `llm/claude_client.py` is everything
  Claude-specific; `llm/failover.py` degrades loudly to Ollama. **Tier rule:** a call with a
  JSON-schema `format` goes to the aux model (Haiku), every other call to the narration model
  (Opus) — call sites never name a model. Read ADR 061 with both amendments before touching
  either file; the SDK differs from the PRD and the ADR wins.
- **Audio reality:** per-user PCM arrives 48 kHz **stereo** → resample to **16 kHz mono** before
  anything else, or you get a garbage transcript (not an error).
- **Commit messages:** imperative, scoped — `dmbot(stt): resample to 16k mono`, `rules(im): success-level calculation`.
- **Tests:** `uv run --with pytest python -m pytest` (pytest isn't in the venv). Python 3.12, uv (no direct `pip`; `uv add`).
- **Two processes, two tokens** — both bots must join the voice channel; tokens in `.env`, **never commit them**.
