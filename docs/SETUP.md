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

### B3 — faster-whisper on GPU (the Windows stumbling block)
- [ ] Provide **cuDNN/cuBLAS DLLs** matching your CUDA version — GPU inference won't start
      otherwise. Two ways:
  - convenient: the NVIDIA wheels into the venv (`uv add nvidia-cublas-cu12 nvidia-cudnn-cu12`)
    and make sure their `bin`/DLLs are findable, **or**
  - manual: put the DLLs on the `PATH` (or next to the running .exe / in the working dir).
- [ ] **Budget time here** — this is empirically the most stubborn setup point.

### B4 — Discord (two bots)
- [ ] **DMbot** new in the Discord Developer Portal: Application → Bot → copy the **token**.
- [ ] **Bot A** (music bot) already exists — keep the token handy.
- [ ] Enable the **Privileged Gateway Intents** as needed (at least the voice/server ones;
      Message Content only if you read text commands — buttons go through interactions).
- [ ] **OAuth2 invite** for both bots with permissions: **Connect**, **Speak**,
      **Send Messages**, **Use Application Commands**.
- [ ] Add both bots to the **same server** and, for testing, the **same voice channel**.

### B5 — TTS voice (Piper)
- [ ] **piper-tts** installed (`uv add piper-tts`).
- [ ] Download a German voice (`.onnx` **and** `.onnx.json`), e.g. `de_DE-thorsten-medium`,
      into a `voices/` folder. Optionally `thorsten_emotional` for comparison (listen test
      in Phase 0).

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
