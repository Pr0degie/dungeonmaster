# CLAUDE.md

Instructions for Claude Code in this repository. Read first, every session.

## Session ritual

This project runs over many sessions, across different models and effort levels. To
survive context clears and model switches, state lives on disk:

**At the start of every session, read in this order:**
1. This file (`CLAUDE.md`) — conventions
2. `progress.md` — where we are, what's next
3. The highest-numbered file in `docs/decisions/` — the most recent decision
   (if any; otherwise the decision log in `progress.md`)

Then state in two or three sentences: where we are, what we're about to do. Don't touch
files until that handshake is done.

**At a phase transition, additionally:**
- Read the ADR(s) that govern the new phase **before** implementing it. The decision log in
  `progress.md` links every decision to its ADR, and the **phase → ADR map** there shows
  which ADRs apply to which phase. This is how the older ADRs (001–004) get used — not just
  the newest one.
- Look at the model/effort table in `roadmap.md` and remind Tobi in the handshake of the
  level recommended for this phase (`/model` + `/effort`) before starting. The running
  instance cannot switch its own model — Tobi sets that on the dial.

**Other documents — read on demand, NOT every session:**

| File | When to read |
|---|---|
| `architecture.md` | Only when the task touches design. Skim the relevant section; don't re-read top to bottom. |
| `roadmap.md` | When transitioning into a new phase, or when the user asks "what's the goal of Phase X?" |
| `SETUP.md` | In Phase 0 or when a setup/install step comes up (Ollama, Discord tokens, cuDNN DLLs, PDFs, fresh-machine copy). Point Tobi at the open items there — the agent cannot do them itself. |
| Older ADRs in `docs/decisions/` | When working in the area they cover. Don't guess which — the decision log + phase→ADR map in `progress.md` tell you which ADR governs the current decision/phase (e.g. ADR 003 before touching turn-taking, ADR 005 before the dice engine). |
| `docs/conventions.md` | When working in a module (rules/memory/rag/tts/voice) or on testing/runtime/troubleshooting/commit-style details. Holds the per-module how-tos moved out of this file. |
| `docs/progress-archive.md` | Only when you need history — old `## Last session` logs, completed-phase `VERIFY EVIDENCE`, or resolved `## Open questions`. Never needed for normal work. |

Eagerly loading everything fills the context window before useful work starts. Be selective.

**At the end of every working session (before context clear or model switch), without
being asked:**
1. Update `progress.md`:
   - `## Current focus` if the phase changed
   - `## Last session` — what we actually did
   - `## Next concrete step` — the specific next action, not a vague goal
   - `## Open questions` — anything that came up but isn't actionable yet
   - Fill the `VERIFY EVIDENCE` field of the affected phase when a gate was met
   - **Keep it lean (rotation):** when you prepend a new `## Last session` entry, move the
     *previous* one to `docs/progress-archive.md` (`## Last session (Verlauf)`) — keep only the
     newest 1–2 live. Rotate ✅-resolved `## Open questions` and just-completed phases (full
     `VERIFY EVIDENCE`) there too, leaving a one-line summary live. `## Decision log` and the
     `### Phase → ADR map` stay fully live.
2. On a non-trivial decision (real trade-off, alternatives weighed), create the
   next-numbered ADR in `docs/decisions/` (format in the README there).

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
  voice/        recv, resample, VAD + the Discord cogs (voicecog / dicecog / dmcog) + delivery.py (the answer→audio turn-delivery pipeline, ADR 035)
  stt/          faster-whisper wrapper
  tts/          piper + xtts (Coqui XTTS v2) wrappers
  llm/          Ollama client, prompt building + orchestrator's extracted pure helpers (sanitize / echo_guard / director_msgs / stream_assembler, ADR 034)
  rag/          ingestion + retrieval + profile bootstrap
  memory/       JSON state + recaps
  rules/        engine.py (generic) + profile loader (+ tests)  ← deterministic core
  discord_ui/   buttons, turn-order view
  orchestrator.py   the DM brain (history + buffer → LLM)
  bridge.py     HTTP client to Bot A's /speak
  logsetup.py   console (green chat) + file logging
data/           committed seed/reference: systems/ (profiles), lore/ + rules_de/ (curated DE setting/rules), party/ (party JSONs), sessions/_example + the live channel's characters.json. Generated/local (git-ignored — see the .gitignore allowlist): pdfs/ (RAG sources), adventures/ (scene cards, bought-book derivatives), sessions/<id>/ state+recaps, vectordb/ (rag.db)
prompts/        dm_core_de.md (generic GM persona) + campaign_tone_de.md (campaign overlay)  — GERMAN, game content
docs/           decisions/ (ADRs), how-to-*.html + character-creation-prompt.md (player guides). SETUP.md lives in the repo root.
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
