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
