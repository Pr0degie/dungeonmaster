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
- [ ] **`.env`** (do NOT commit) — copy `.env.example`. This repo's `.env` holds **only
      DMbot's** token + config: `DISCORD_TOKEN_DMBOT=…`, `BOT_A_USER_ID=…`,
      `OLLAMA_HOST=http://localhost:11434`. **Bot A's token lives in the music bot's own repo**,
      not here (two-bot isolation).

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
  - `ollama pull bge-m3` (embeddings for RAG — multilingual; replaced the original
    `nomic-embed-text` plan, which failed German→English retrieval, ADR 019/D45)
- [ ] **Verification (= Phase 0 gate):**
      `curl http://localhost:11434/api/generate -d "{\"model\":\"mistral-nemo\",\"prompt\":\"Say something grim in German.\",\"stream\":false}"`
      → plausible German answer.

### B3 — faster-whisper on GPU (the Windows stumbling block) — ✅ DONE (2026-06-04)
- [x] cuDNN/cuBLAS/cudart DLLs provided via the NVIDIA wheels
      (`uv add faster-whisper nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12`).
      Installed: `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `nvidia-cudnn-cu12 9.23` (cuDNN 9,
      matches ct2 4.7), `nvidia-cublas-cu12 12.9`, **`nvidia-cuda-runtime-cu12 12.9`**. The
      **cudart** wheel is required: `cublas64_12.dll` depends on `cudart64_12.dll`, so without it
      GPU whisper dies at `encode()` with "cublas64_12.dll cannot be loaded" (hit on the 5080 box,
      2026-06-05, once torch moved to CUDA 13 / cu130 — the CUDA-12 trio must be self-complete).
- [x] **No manual `PATH` editing needed.** `dmbot/stt/transcriber.py` registers the wheels'
      `bin` dirs with `os.add_dll_directory()` *before* importing faster-whisper, so Windows
      finds the DLLs. Verified: `faster-whisper 'small' loaded on cuda (float16)`,
      ~1.25 s to transcribe 4 s of audio (model cached). If GPU init ever fails it auto-falls
      back to CPU int8 (logged), so STT degrades instead of dying.
- Tunable via env (no code change): `WHISPER_MODEL` (default `medium`), `WHISPER_DEVICE`
  (`cuda`), `WHISPER_COMPUTE` (`float16`). Drop to `small` to free VRAM if needed.

### B4 — Discord (two bots) — ✅ DONE (2026-06-04)
- [x] **DMbot** created, token in `.env`; **Bot A** (music bot) token in its own repo.
- [x] Privileged intents enabled (Message Content + Server Members + voice); OAuth2 invites with
      Connect/Speak/Send Messages. Both bots verified live in the **same voice channel** — the
      full loop (speak → DM answers aloud) worked. **Bot A must run on its `dungeon_master`
      branch** (the bridge cog `cogs/dm_bridge.py` is only there; `main` → "connection refused").

### B5 — TTS: XTTS (default) + Piper (fallback) — ✅ DONE (2026-06-04 / GPU 2026-06-05)
- [x] **XTTS v2 is the default** (`TTS_ENGINE=xtts`, `coqui-tts`): ~58 German-capable speakers +
      voice cloning, speaker **Dionisio Schuyler**. The model **downloads itself on first run**
      (no manual file). Runs on GPU with the CUDA torch build (ADR 009, RTF ~0.34) and
      **auto-degrades to CPU** if CUDA is absent or the GPU OOMs — never blocks startup.
- [x] **Piper is the lean fallback** (`TTS_ENGINE=piper`, `piper-tts` v1.4.2): fast (~224 ms/
      sentence), fixed German voice `de_DE-thorsten-medium` (`.onnx` + `.onnx.json`) in `voices/`
      (gitignored), **bundles espeak-ng data** (no separate phonemiser). Outputs 22050 Hz mono
      16-bit WAV; Bot A's ffmpeg plays it. Swap via `PIPER_VOICE=<path to .onnx>`.
- **Still needs Tobi for the full loop:** Bot A (the music bot, `dungeon_master` branch) must be
  **running with both bots in the same voice channel** so DMbot's `/speak` POST has somewhere to
  play. The agent cannot start Bot A (separate repo/process).

### B6 — Audio/Opus (Windows) — ✅ DONE (2026-06-04)
- [x] **Opus** loads via discord.py's **bundled DLL** (no manual install needed) — confirmed in
      Phase 2 (`discord.opus.is_loaded()` true; receive decodes PCM).
- [x] **Microphone** works — live tests with two human speakers transcribed correctly (Phase 3/4).

### B7 — Game content (PDFs)
- [ ] **Your first system's rulebook as a PDF** (legally owned) into `data/pdfs/` — for the
      first campaign that's **Imperium Maledictum**. Basis for RAG and for the system profile
      the DM proposes (Phase 8/10).
- [ ] **Adventure/story PDF** you want to run, also into `data/pdfs/`.
- [ ] **Character sheets** ready — you transfer these later (Phase 8/9) once into the
      character JSON (shape follows the system profile); they do **not** go into RAG.

### B8 — Phase 8: real party stats + verify the IM rules (human-only steps)
The dice engine, `!test` and the unit tests already run against an **example party**
(`data/sessions/_example/characters.json`). To play with your real characters and correct rolls:
- [ ] **Transfer the real sheets once into JSON.** Copy the example to
      `data/sessions/<voice-channel-id>/characters.json` (the cog prefers the channel-specific file
      at `!join`, else falls back to the example) and fill in each character's `characteristics`,
      `skills` (the values the engine rolls against), `wounds`/`max_wounds`, and the
      `aliases` map (Discord display name → character name, e.g. `"SezBoss69": "Seskin"` — this is
      what fixes the model confusing player/character names). The channel id is the **voice** channel's
      id (right-click → Copy ID with Developer Mode on).
- [x] **IM difficulty ladder + SL/auto-band numbers verified** against the Core Rulebook (2026-06-07,
      via `tools/pdf_to_md.py` on the bought PDF) and corrected in
      `data/systems/imperium_maledictum.json` (see its `_note`). Nothing more to do here unless you want
      to tweak labels. (Phase 10's RAG profile bootstrap will later propose such profiles from the PDF
      automatically.)

### B9 — Phase 10: RAG store + adventure (one-time per machine)

On Tobi's box this is all ✅ done — these steps matter on a **fresh machine**. What git does
NOT carry (PDFs, the adventure compendium, optionally the prebuilt `rag.db`) is listed in
[`CHECKLIST.md`](CHECKLIST.md); copy that over first. The curated lore (`data/lore/*.md`,
ADR 021) IS in the repo and comes with the clone.

- [ ] **Vector store** — either copy `data/vectordb/rag.db` from a built machine, **or**
      rebuild it (Ollama with `bge-m3` running; from the repo root):
      ```
      uv run python tools/pdf_to_md.py "data/pdfs/Imperium Maledictum Core Rulebook.pdf"
      uv run python tools/pdf_to_md.py "data/pdfs/Starter Set/IM_SS_Setting_Guide_Book_240722.pdf" --pages 1-57
      uv run python tools/pdf_to_md.py "data/pdfs/Imperium_Maledictum_Inqusition_Player's_Guide.pdf"
      uv run python tools/pdf_to_md.py "data/pdfs/Imperium Maledictum Inquisition GM-Guide.pdf" --pages 4-61,74-83,172-174 -o "data/pdfs/md/Imperium Maledictum Inquisition GM-Guide.md"
      uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Core Rulebook.md" --source rulebook
      uv run python -m dmbot.rag.ingest "data/pdfs/md/IM_SS_Setting_Guide_Book_240722.md" --source setting
      uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium_Maledictum_Inqusition_Player's_Guide.md" --source player_guide
      uv run python -m dmbot.rag.ingest "data/pdfs/md/Imperium Maledictum Inquisition GM-Guide.md" --source gm_guide
      uv run python -m dmbot.rag.ingest "data/lore/imperium.md" --source lore_imperium
      uv run python -m dmbot.rag.ingest "data/lore/chaos.md" --source lore_chaos
      ```
      Deliberate spoiler cuts: the Setting Guide pages 1–57 only ("Villains on Voll" stays out,
      D46); the Inquisition GM-Guide only its safe reference half (pages 4–61, 74–83, 172–174) —
      the Heresies Macharia campaign, Sector-Threat villains, Open Case Files, the patron sheets
      (incl. Halikarn) and the index stay out. The Player's Guide is whole. Idempotent per source.
- [ ] **Adventure** — `data/adventures/chemical_burn/` in place (from CHECKLIST.md) and
      `DM_ADVENTURE=chemical_burn` set in `.env`, otherwise the DM loads no adventure.
- [ ] **Sanity check:** ask a Chaos or lore question in a live session — a `📚 lore_…:` line
      must appear in `debug.log`; a rule question shows `📚 rulebook:…`.

---

## C. Only needed later (not for the MVP)

- [ ] **Tailscale** (Personal plan, free) — needed for the **split-hosting** setup (Bot A on one
      machine, DMbot on another; the bridge then sends WAV bytes over the tailnet, ADR 010) and/or
      if Ollama moves to the 5080 (ADR 002). Both machines sign into the **same tailnet**; set
      `DM_BRIDGE_HOST`/`DM_BRIDGE_SECRET` per the README "Split hosting" section. Unnecessary when
      both bots run on one machine (localhost path mode).
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
8. RAG store + adventure: copy or rebuild `rag.db`, set `DM_ADVENTURE` (B9)

Tailscale & character JSON come later (C).
