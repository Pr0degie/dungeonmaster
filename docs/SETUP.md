# SETUP.md — Preparation outside the agent

Everything **you** must set up before/while Claude Code builds — in order. The agent
knows from the Phase 0 checklist *that* these things are needed, but installing, creating
tokens and getting PDFs is on you.

Runtime is **Windows** (see decision log D16). Check the items off.

---

## A. Before you even write to the agent

- [ ] **Create the repo** and place the planning docs into the working directory,
      otherwise the agent can't see them:
  - `CLAUDE.md`, `roadmap.md`, `progress.md`, `architecture.md` in the repo root
  - `docs/decisions/` with `README.md` + `001`–`004`
  - this `docs/SETUP.md`
- [ ] **`.gitignore`** with at least: `.env`, `data/`, `__pycache__/`, `.venv/`, `*.wav`,
      model/voice files.
- [ ] **`.env`** (do NOT commit) for the two bot tokens + config:
      `DMBOT_TOKEN=…`, `BOT_A_TOKEN=…`, `OLLAMA_HOST=http://localhost:11434`.

> From here the session ritual applies: the agent reads `CLAUDE.md` → `progress.md` →
> the latest ADR and does the handshake.

---

## B. Phase 0 setup (the actual install work)

### B1 — Base tooling (Windows)
- [ ] **Git** installed.
- [ ] **Python 3.12** installed.
- [ ] **uv** installed (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`),
      project managed with `uv` — no direct `pip`.
- [ ] Current **NVIDIA driver** for the 4070.

### B2 — Ollama + models (local on the 4070)
- [ ] **Ollama for Windows** installed (runs as a service on `localhost:11434`).
- [ ] Pull model(s):
  - `ollama pull mistral-nemo` (starting recommendation, ~12B)
  - `ollama pull qwen2.5:14b` (optional, for the taste test)
  - `ollama pull nomic-embed-text` (embeddings for RAG)
- [ ] **Verification (= Phase 0 gate):**
      `curl http://localhost:11434/api/generate -d "{\"model\":\"mistral-nemo\",\"prompt\":\"Say something grim in German.\",\"stream\":false}"`
      → plausible German answer.

### B3 — faster-whisper on GPU (the Windows stumbling block) — ✅ DONE (2026-06-04)
- [x] cuDNN/cuBLAS DLLs provided via the NVIDIA wheels
      (`uv add faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12`). Installed:
      `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `nvidia-cudnn-cu12 9.23` (cuDNN 9, matches
      ct2 4.7), `nvidia-cublas-cu12 12.9`.
- [x] **No manual `PATH` editing needed.** `dmbot/stt/transcriber.py` registers the wheels'
      `bin` dirs with `os.add_dll_directory()` *before* importing faster-whisper, so Windows
      finds the DLLs. Verified: `faster-whisper 'small' loaded on cuda (float16)`,
      ~1.25 s to transcribe 4 s of audio (model cached). If GPU init ever fails it auto-falls
      back to CPU int8 (logged), so STT degrades instead of dying.
- Tunable via env (no code change): `WHISPER_MODEL` (default `small`), `WHISPER_DEVICE`
  (`cuda`), `WHISPER_COMPUTE` (`float16`). Bump to `medium` if German accuracy needs it.

### B4 — Discord (two bots)
- [ ] **DMbot** new in the Discord Developer Portal: Application → Bot → copy the **token**.
- [ ] **Bot A** (music bot) already exists — keep the token handy.
- [ ] Enable the **Privileged Gateway Intents** as needed (at least the voice/server ones;
      Message Content only if you read text commands — buttons go through interactions).
- [ ] **OAuth2 invite** for both bots with permissions: **Connect**, **Speak**,
      **Send Messages**, **Use Application Commands**.
- [ ] Add both bots to the **same server** and, for testing, the **same voice channel**.

### B5 — TTS voice (Piper) — ✅ DONE (2026-06-04)
- [x] **piper-tts** installed (`uv add piper-tts`, v1.4.2) — installs cleanly on Windows/py3.12
      and **bundles its espeak-ng data**, so no separate phonemiser is needed.
- [x] German voice `de_DE-thorsten-medium` (`.onnx` + `.onnx.json`) downloaded into `voices/`
      (gitignored). Piper outputs **22050 Hz mono 16-bit** WAV; Bot A's ffmpeg plays it fine.
      Verified: voice loads ~1.3 s, ~224 ms to synthesise a 6 s German sentence.
- Swap the voice via `PIPER_VOICE=<path to .onnx>`; `thorsten_emotional` is worth a listen test.
- **Still needs Tobi for the full loop:** Bot A (the music bot, `dungeon_master` branch) must be
  **running with both bots in the same voice channel** so DMbot's `/speak` POST has somewhere to
  play. The agent cannot start Bot A (separate repo/process).

### B6 — Audio/Opus (Windows)
- [ ] **Opus DLL** ready for discord.py voice (send *and* receive need libopus); possibly
      `discord.opus.load_opus(...)` in code — the agent does that, but you must have the DLL
      available.
- [ ] A working **microphone**, test people in the voice channel.

### B7 — Game content (PDFs)
- [ ] **Your first system's rulebook as a PDF** (legally owned) into `data/pdfs/` — for the
      first campaign that's **Imperium Maledictum**. Basis for RAG and for the system profile
      the DM proposes (Phase 8/10).
- [ ] **Adventure/story PDF** you want to run, also into `data/pdfs/`.
- [ ] **Character sheets** ready — you transfer these later (Phase 8/9) once into the
      character JSON (shape follows the system profile); they do **not** go into RAG.

---

## C. Only needed later (not for the MVP)

- [ ] **Tailscale** (Personal plan, free) — only if Ollama later moves to the colleague's
      5080 (ADR 002). Unnecessary for local development on the 4070.
- [ ] **Finalize the character JSON schema** — prerequisite for Phase 8 (ADR 004), but not
      a Phase 0 concern yet.

---

## Quick order (TL;DR)
1. Repo + docs + `.gitignore` + `.env` (section A)
2. Git / Python 3.12 / uv / NVIDIA driver (B1)
3. Ollama + pull models + curl test (B2) ← **Phase 0 gate**
4. cuDNN/cuBLAS DLLs (B3) ← budget time
5. Discord apps + tokens + intents + invite (B4)
6. Piper voice + Opus DLL (B5/B6)
7. Rulebook & story PDF into `data/pdfs/` (B7)

Tailscale & character JSON come later (C).
