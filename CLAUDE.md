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
| `docs/SETUP.md` | In Phase 0 or when a setup/install step comes up (Ollama, Discord tokens, cuDNN DLLs, PDFs). Point Tobi at the open items there — the agent cannot do them itself. |
| Older ADRs in `docs/decisions/` | When working in the area they cover. Don't guess which — the decision log + phase→ADR map in `progress.md` tell you which ADR governs the current decision/phase (e.g. ADR 003 before touching turn-taking, ADR 005 before the dice engine). |

Eagerly loading everything fills the context window before useful work starts. Be selective.

**At the end of every working session (before context clear or model switch), without
being asked:**
1. Update `progress.md`:
   - `## Current focus` if the phase changed
   - `## Last session` — what we actually did
   - `## Next concrete step` — the specific next action, not a vague goal
   - `## Open questions` — anything that came up but isn't actionable yet
   - Fill the `VERIFY EVIDENCE` field of the affected phase when a gate was met
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
  voice/        recv, resample, VAD
  stt/          faster-whisper wrapper
  tts/          piper + xtts (Coqui XTTS v2) wrappers
  llm/          Ollama client, prompt building
  rag/          ingestion + retrieval + profile bootstrap
  memory/       JSON state + recaps
  rules/        engine.py (generic) + profile loader (+ tests)  ← deterministic core
  discord_ui/   buttons, turn-order view
  orchestrator.py   the DM brain (history + buffer → LLM)
  bridge.py     HTTP client to Bot A's /speak
  logsetup.py   console (green chat) + file logging
data/           systems/ (profiles), pdfs/ (RAG), adventures/ (scene cards — local-only, derivative of bought books), sessions/ (state+recaps), vectordb/  ← generated/local, not hand-edited
prompts/        dm_core_de.md (generic GM persona) + campaign_tone_de.md (campaign overlay)  — GERMAN, game content
docs/           SETUP.md, decisions/ (ADRs)
```

## Bot A — the bridge (separate repo, already done)

Bot A is the existing music bot in its **own repo** (`Pr0degie/musicbot`, branch
`dungeon_master`, commit `249cc38`). It is **not** edited from this repo. What matters
here is its contract, which DMbot calls:

- `GET /health` → liveness. `POST /speak` with JSON `{"path","guild_id?"}` plays the WAV
  and **blocks until playback ends** — the return is the resume signal (no callback, no
  shared state). Localhost only, default `127.0.0.1:8765`. Full contract in `architecture.md` §3.
- **Two-bot isolation:** never propose changes to the music bot from here. If the bridge
  ever genuinely needs a change, that's a separate task in the music bot repo — keep it
  minimal there (the music/queue logic stays untouched).

## DMbot — DM conventions (`dmbot/`)

- **`discord-ext-voice-recv` is the only research part.** Less well-trodden than plain
  discord.py. Check against the *installed* version (the sink callback signature may
  differ), keep it isolated in `voice/`.
- **Audio reality:** per-user PCM arrives as 48 kHz **stereo**. VAD/STT need 16 kHz
  **mono** → resample before anything else. Wrong sample rate = garbage transcript,
  **not** an error — it won't surface on its own.
- **LLM wiring:** Ollama runs as its own process — in development **locally** (Tobi's
  4070, Nemo 12B), later optionally on the 5080 via Tailscale. **Never hardcode the
  host** — use env/config (`OLLAMA_HOST`), so the switch is a one-liner. Before blaming
  the client: `ollama list` — is the model even pulled?
- **Prompt building (`llm/`):** order = generic GM core → campaign tone overlay → recap →
  **adventure summary + current scene card** (code-owned pointer `state.scene_id`, ADR 019) →
  JSON state → Regelwerk hits (threshold-gated rulebook RAG) → recent history. Pass state and
  RAG as structured data, don't boil them into prose.
- **TTS:** Piper outputs a specific WAV format — confirm Bot A can play it.
- **Discord UI (`discord_ui/`):** buttons via `View`/`Button`. Dice buttons call the rules
  engine, never inline their own dice logic.

## Rules engine (`dmbot/rules/`)

- Pure Python, **fully decoupled** from the LLM. A **generic** engine: it rolls dice (RNG)
  and resolves them per the **active system profile** (`data/systems/<system>.json`) — it
  does not hardcode any one game. Profiles declare dice type, resolution (roll-under/over/
  pool/…), target source, degrees rule, and the character schema.
- IM is the first profile: `1d100`, roll-under, success level = tens-difference, damage
  d10/d5. Other systems are just other profiles.
- **Profile bootstrap:** on a new ruleset the DM proposes a draft profile from the rulebook
  (RAG) and the user confirms it; then the engine applies it. See `architecture.md` §9 + ADR 005.
- Pure functions, fixed seed in tests. The engine is unit-tested against each profile (IM
  first). This is the only part that is deterministically testable — use that.

## Memory (`dmbot/memory/`)

- JSON world state per voice channel in `data/sessions/`. Schema in `architecture.md` §7.
- Advancement is **deterministic in code** (e.g. HP after damage), never from LLM free text.
- Recaps: the LLM summarizes, code stores & re-injects at the front next time.

## RAG (`dmbot/rag/`)

- Ingestion: PDF → chunks → `bge-m3` → vector store. **40k rulebooks are
  multi-column/table-heavy** — extracted text comes out scrambled. Inspect a real chunk
  before trusting retrieval.
- Answer rule questions from rulebook chunks; attach the source to the context.

## Testing

- **`rules/`:** pytest, deterministic — mandatory (see above).
- **Voice/VAD/STT/TTS/full loop:** verified manually per phase gate, proof in the
  `VERIFY EVIDENCE` field of the phase in `progress.md`. (Real-time audio can't be
  meaningfully unit-tested.)
- **Memory:** persistence test — a state change survives a restart.
- **RAG:** sanity check — a concrete IM rule question answered correctly from a PDF.

## Runtime / operations

- Python 3.12, managed with **uv**. No direct `pip`; `uv add`.
- **Runtime: Windows.** Both bots + pipeline run on Windows. Never hardcode POSIX paths —
  WAV temp via `tempfile.gettempdir()`, **never `/tmp`**.
- **Two processes, two tokens** — both bots must join the voice channel. Tokens in
  env/`.env`, **never commit them**.
- Ollama runs as its own process, not bundled with DMbot — in development locally on the
  4070, later optionally on the 5080 (Tailscale). Switchable via `OLLAMA_HOST`.
- Keep the latency chain lean (LAN/Tailscale). Streaming TTS is a later optimization, not
  an MVP must.

## When you're stuck on reality

The pipeline doesn't lie about itself — but real-time audio and foreign libs do:
- **`discord-ext-voice-recv`:** check the sink callback signature against the installed version.
- **No sound?** First check: are *both* bots actually connected to the voice channel?
- **Garbage transcript?** Suspect the sample rate (16 kHz mono?) before the model.
- **LLM not answering?** `ollama list` + reachability of the host (ping/curl) before the client.
- **RAG hallucinating?** Look at a real extracted PDF chunk — probably layout garbage.
- **No sound despite correct code (Windows)?** Is the Opus DLL loaded for discord.py voice?
- **faster-whisper won't start (Windows)?** Are the cuDNN/cuBLAS DLLs on the `PATH`?
- **`FileNotFoundError` for the WAV?** `/tmp` hardcoded instead of `tempfile.gettempdir()` — Windows has no `/tmp`.

## Style

- Commit messages: imperative, scoped (`dmbot(stt): resample to 16k mono`,
  `rules(im): success-level calculation`).
- Small functions; prefer pure functions in `rules/` and `memory/` so they stay testable.
- Comments explain *why*, not *what*.
- For small manual edits, use an editor (nano/vim) rather than clever sed/awk one-liners.
