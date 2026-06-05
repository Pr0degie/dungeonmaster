# Cogitator — a local, voice-only AI Game Master

**DMbot** is a self-hosted AI game master for tabletop RPGs that plays **by voice over
Discord**, in **German**. You talk; it listens, thinks, and answers aloud in character. It is
**system-agnostic** — load a ruleset/adventure as PDFs and it learns the setting (RAG) and the
mechanics (a per-system profile). Everything runs **locally** — no cloud, no API costs.

First campaign: **Warhammer 40,000 / Imperium Maledictum** in Dan Abnett's *Eisenhorn*
grimdark tone — but that's just the first profile + tone overlay, not baked into the DM.

> **Status:** the core voice loop is **playable** (Phases 0–6 done). You can speak and the DM
> answers aloud. Dice engine, persistent memory and RAG are the next phases. See
> [`progress.md`](progress.md) for the live status and [`roadmap.md`](roadmap.md) for the plan.

## How it works

Two Discord bots share one voice channel:

- **Bot A** — the existing music bot (a **separate repo**), used only as the *mouth*: a tiny
  `/speak` HTTP bridge that plays a WAV and blocks until done.
- **DMbot** — this repo, the *brain*: voice receive → VAD → STT → LLM → TTS → bridge.

```
You speak ─► DMbot receives per-user audio (discord-ext-voice-recv, DAVE/E2EE decrypt)
            │   (Bot A's voice is filtered out — no self-hearing)
            ▼
        resample 48k stereo → 16k mono (soxr)
            ▼
        silero-vad cuts utterances ──► faster-whisper → German transcript (buffered)
            ▼
        you trigger a DM turn:  !dm
            ▼
        Ollama (mistral-nemo) + layered German persona (GM core + Eisenhorn tone) → answer
            ▼
        TTS (Piper or Coqui XTTS v2) → WAV  ──► POST /speak to Bot A ──► spoken aloud
```

**Signature principle:** *dice = code, narration = LLM.* Dice rolls and their resolution are
computed by a deterministic engine from the active system profile — never the language model
(coming in Phase 8).

## Quick start

```bash
uv sync                       # install deps (Python 3.12, managed by uv)
cp .env.example .env          # then fill in DISCORD_TOKEN_DMBOT (never commit .env)
uv run python -m dmbot        # or double-click start_dmbot.bat (Windows)
```

You also need, running alongside: **Ollama** (`mistral-nemo` pulled) and **Bot A** (the music
bot on its `dungeon_master` branch, in the same voice channel). Full step-by-step in
**[`SETUP.md`](SETUP.md)**; the external prerequisites the bot can't install itself are in
[`docs/SETUP.md`](docs/SETUP.md).

## Running on another machine (e.g. a second GPU box)

The project is two processes plus Ollama, all local. To bring it up on a fresh Windows + NVIDIA
machine:

1. **Clone both repos.** This one (DMbot) and the music bot, `Pr0degie/musicbot` on branch
   `dungeon_master` (Bot A — the `/speak` mouth). DMbot can't speak without Bot A running.
2. **Install per repo:** `uv sync` in each. DMbot pulls a **CUDA torch** build from the cu126
   index automatically (needs an NVIDIA GPU + recent driver; a box without a usable GPU degrades
   XTTS to CPU). The lock is Windows-only.
3. **Two Discord bot tokens.** A bot token allows only one live connection, so either (a) reuse
   the existing two tokens *while the other machine's instances are off*, or (b) create two new
   Discord bot applications (DMbot + Bot A) with voice intents and invite both to the server.
   DMbot's token → `DISCORD_TOKEN_DMBOT` in this repo's `.env`; Bot A's token → the music bot's
   own `.env`. Set `BOT_A_USER_ID` to Bot A's user-ID (feedback protection).
4. **Ollama:** install, then `ollama pull mistral-nemo` and `ollama pull nomic-embed-text`.
   Or point `OLLAMA_HOST` at a machine that already has them.
5. **Pick the GPU profile** in `.env` (see [`.env.example`](.env.example)):
   - **16 GB+ (e.g. RTX 5080) — everything on GPU:** `WHISPER_DEVICE=cuda` `WHISPER_COMPUTE=float16` `TTS_DEVICE=cuda`
   - **12 GB (e.g. RTX 4070):** `WHISPER_DEVICE=cpu` `WHISPER_COMPUTE=int8` `TTS_DEVICE=cuda` (whisper on CPU frees VRAM for XTTS)
6. **Start order:** Ollama (service) → Bot A (music bot) → DMbot (`uv run python -m dmbot` or
   `start_dmbot.bat`). Both bots `!join` the same voice channel, then `!dm` runs a turn.

XTTS downloads its model on first run; the Piper voice is optional (only if `TTS_ENGINE=piper`).

## Discord commands

| Command | Does |
|---|---|
| `!join` / `!j` | DMbot joins your voice channel and starts listening |
| `!leave` | leave the voice channel |
| `!dm [text]` | run a DM turn — answers the buffered speech, or the given text — and speaks it |
| `!say <text>` | speak arbitrary text (TTS/bridge smoke test) |
| `!voice <name>` / `!voices` | switch / list XTTS speakers (only with `TTS_ENGINE=xtts`) |
| `!vstatus` | connection / listening / Opus state |

## Configuration (`.env`)

Everything is env-driven (never hardcoded). Highlights — see [`.env.example`](.env.example):

- `OLLAMA_HOST` / `OLLAMA_MODEL` — LLM host + model (default local `mistral-nemo`)
- `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE` — STT (default `medium` / `cuda` / `float16`)
- `TTS_ENGINE` — `piper` (fast, fixed voice) or `xtts` (Coqui XTTS v2, 58 voices + cloning)
- `TTS_SPEAKER` / `TTS_DEVICE` — XTTS speaker (default *Dionisio Schuyler*) and device
- `BOT_A_USER_ID` — Bot A's user-ID, filtered from voice (feedback protection layer 1)

## Documentation

| File | What |
|---|---|
| [`architecture.md`](architecture.md) | full design — pipeline, components, memory, RAG, rules engine |
| [`roadmap.md`](roadmap.md) | phased plan + model/effort recommendations |
| [`progress.md`](progress.md) | live status, decision log, what's next |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (ADRs) |
| [`SETUP.md`](SETUP.md) · [`docs/SETUP.md`](docs/SETUP.md) | install & run · external prerequisites |

> Convention: code and docs are **English**; game content (the GM persona, tone overlays, and
> anything the DM says) is **German**.
