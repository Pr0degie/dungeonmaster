# Setup & Run

How to install and run **DMbot** and get the full voice loop working. For the *external*
prerequisites the agent can't provide for you (Ollama models, Discord apps/tokens, GPU DLLs,
voice files, rulebook PDFs), see the granular checklist in [`docs/SETUP.md`](docs/SETUP.md).

Runtime is **Windows**, Python **3.12**, managed with **uv**.

## 1. Prerequisites (running alongside DMbot)

- **uv** installed, and Python 3.12.
- **Ollama** running locally with the DM model pulled:
  `ollama pull mistral-nemo` (and `nomic-embed-text` for later RAG).
- **Bot A** — the music bot from its **own repo** (`Pr0degie/musicbot`), checked out on the
  **`dungeon_master`** branch (that branch has the `cogs/dm_bridge.py` `/speak` server; `main`
  does **not**). ffmpeg comes with the music bot.
- A **Discord app + token** for DMbot (privileged intents: Message Content + Server Members),
  and both bots invited to the **same server / voice channel**.

Details and one-time GPU/voice setup: [`docs/SETUP.md`](docs/SETUP.md) (cuDNN for faster-whisper
is handled **in code** — no manual PATH; the default **XTTS** voice model downloads itself on
first run, the optional Piper fallback voice lives in `voices/`, gitignored).

## 2. Install

```bash
uv sync                  # creates the venv and installs all dependencies
```

## 3. Configure

```bash
cp .env.example .env     # never commit .env (gitignored)
```

Fill in at least `DISCORD_TOKEN_DMBOT`. Useful knobs (all optional, sensible defaults):

| Var | Default | Notes |
|---|---|---|
| `DISCORD_TOKEN_DMBOT` | — | **required** |
| `BOT_A_USER_ID` | — | Bot A's user-ID; filtered from voice (feedback layer 1) |
| `OLLAMA_HOST` / `OLLAMA_MODEL` | `127.0.0.1:11434` / `mistral-nemo` | LLM host + model |
| `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE` | `medium` / `cuda` / `float16` | STT; use `cpu`/`int8` to free GPU VRAM |
| `TTS_ENGINE` | `xtts` | Coqui XTTS v2 (58 voices + cloning) — the default; set `piper` for the fast, lean fallback voice |
| `TTS_SPEAKER` / `TTS_DEVICE` | *Dionisio Schuyler* / `cpu` | XTTS speaker + device (`cuda` for GPU; auto-falls back to CPU) |
| `DM_BRIDGE_HOST` / `DM_BRIDGE_PORT` | `127.0.0.1` / `8765` | Bot A's `/speak` bridge |

## 4. Run

1. Start **Ollama** and **Bot A** (on `dungeon_master`); get both bots into one voice channel.
2. Start DMbot:
   ```bash
   uv run python -m dmbot      # or start_dmbot.bat on Windows
   ```
3. In Discord: `!j` → speak → `!dm` (or `!say <text>`). The DM answers **aloud**.

Logs go to the console (green chat layout) **and** `logs/dmbot.log` (full detail, gitignored).

## 5. Troubleshooting (gotchas we actually hit)

- **`/speak` → "All connection attempts failed":** Bot A isn't serving the bridge. It must run
  on its **`dungeon_master`** branch (not `main`); on start its log says
  `[DMBridge] HTTP-Server läuft auf 127.0.0.1:8765`.
- **Slow DM turn (latency):** the 12 GB GPU fills up (nemo ~9.5 GB + whisper ~2.5 GB). Free VRAM
  with `WHISPER_DEVICE=cpu` (+ `WHISPER_COMPUTE=int8`), and/or run XTTS on GPU
  (`TTS_DEVICE=cuda`); check `ollama ps` (nemo should be 100 % GPU) and `nvidia-smi`. Long-term:
  Ollama on a second GPU via Tailscale (ADR 002).
- **No sound:** are **both** bots in the voice channel? Is ffmpeg available to Bot A?
- **Garbage transcript:** suspect the sample rate (must be 16 kHz mono) before the model.
- **XTTS won't load (it's the default):** it needs torch/torchaudio/torchcodec + `transformers<5`;
  `uv sync` pins these (CUDA build from the cu126 index for GPU). On CUDA-less boxes or an OOM it
  auto-degrades to CPU (logged). If it still won't run, fall back to the lean voice with
  `TTS_ENGINE=piper`.

## 6. Tests

```bash
uv run pytest             # the deterministic core (rules/, memory) — when those land
```

Voice/VAD/STT/TTS/full-loop are verified manually per phase gate (see `progress.md`); real-time
audio can't be meaningfully unit-tested.
