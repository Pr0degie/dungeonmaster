# Setup & Run

The single source of truth for getting **DMbot** running: install, configure, run, the
external prerequisites the agent can't provide for you, and what to copy when moving to
another machine.

Runtime is **Windows**, Python **3.12**, managed with **uv** (no direct `pip`).

## Quick order (TL;DR)

1. Repo + docs + `.gitignore` + `.env` (§A)
2. Git / Python 3.12 / uv / NVIDIA driver (§B1)
3. Ollama + pull models + curl test (§B2) ← **Phase 0 gate**
4. cuDNN/cuBLAS DLLs — handled **in code**, no manual PATH (§B3)
5. Discord apps + tokens + intents + invite (§B4)
6. XTTS (default, self-downloads) / Piper voice + Opus DLL (§B5/§B6)
7. Rulebook & story PDF into `data/pdfs/` (§B7)
8. RAG store + adventure: copy or rebuild `rag.db`, set `DM_ADVENTURE` (§B9)

Then **Install → Configure → Run** below. Tailscale & the character JSON schema come later
(§C). Moving to a fresh machine? See **Running on another machine**.

---

## Install

**Automated (recommended).** One-shot installer from the repo root — installs `uv`, runs
`uv sync`, creates `.env`, pulls/warms the local Ollama models, then prints what only *you*
can finish (token, Bot A, PDFs). Safe to re-run.

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
# .\setup.ps1 -StartBot     # also launch the bot when setup succeeds
# .\setup.ps1 -SkipOllama   # skip the LLM steps (e.g. remote Ollama host)
# .\setup.ps1 -Prefetch     # pre-download the STT + XTTS models (several GB) so the
#                           # first DM turn doesn't wait; otherwise they fetch on first use
```

**Manual** (what the script automates):

```bash
uv sync                  # creates the venv and installs all dependencies
```

## Configure (`.env`)

```bash
cp .env.example .env     # never commit .env (gitignored)
```

This repo's `.env` holds **only DMbot's** token + config — **Bot A's token lives in the music
bot's own repo** (two-bot isolation). Fill in at least `DISCORD_TOKEN_DMBOT`. Knobs (all
optional, sensible defaults):

| Var | Default | Notes |
|---|---|---|
| `DISCORD_TOKEN_DMBOT` | — | **required** |
| `BOT_A_USER_ID` | — | Bot A's user-ID; filtered from voice (feedback layer 1) |
| `OLLAMA_HOST` / `OLLAMA_MODEL` | `127.0.0.1:11434` / `mistral-nemo` | LLM host + model |
| `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE` | `medium` / `cuda` / `float16` | STT; use `cpu`/`int8` to free GPU VRAM |
| `TTS_ENGINE` | `xtts` | Coqui XTTS v2 (58 voices + cloning) — the default; set `piper` for the fast, lean fallback voice |
| `TTS_SPEAKER` / `TTS_DEVICE` | *Dionisio Schuyler* / `cpu` | XTTS speaker + device (`cuda` for GPU; auto-falls back to CPU) |
| `DM_BRIDGE_HOST` / `DM_BRIDGE_PORT` | `127.0.0.1` / `8765` | Bot A's `/speak` bridge |
| `DM_ADVENTURE` | — | scene-card adventure to load (e.g. `chemical_burn`); unset → no adventure |
| `DM_LOG_FILE` | off | `1` records a run to `logs/terminal.log` + `logs/debug.log` |

## Run

1. Start **Ollama** and **Bot A** (on its **`dungeon_master`** branch — that branch has the
   `cogs/dm_bridge.py` `/speak` server; `main` does **not**). Get **both** bots into the
   **same voice channel**.
2. Start DMbot:
   ```bash
   uv run python -m dmbot      # or start_dmbot.bat on Windows
   ```
3. In Discord: `!j` → speak → `!dm` (or `!say <text>`). The DM answers **aloud**.

Logs go to the console — kept lean (DMbot's own lines + any warnings/errors, timestamped).
File logging is **off by default**; set `DM_LOG_FILE=1` to record a run as two pasteable
files: `logs/terminal.log` (plain console mirror) and `logs/debug.log` (fuller detail +
tracebacks, heartbeat flood collapsed).

## Troubleshooting (gotchas we actually hit)

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
  `uv sync` pins these (CUDA build from the cu130 index for GPU — covers Ada + Blackwell). On
  CUDA-less boxes or an OOM it auto-degrades to CPU (logged). If it still won't run, fall back to
  the lean voice with `TTS_ENGINE=piper`.

## Tests

```bash
uv run --with pytest python -m pytest     # the deterministic core (rules/, memory)
```

Voice/VAD/STT/TTS/full-loop are verified manually per phase gate (see `progress.md`); real-time
audio can't be meaningfully unit-tested.

---

## External prerequisites — what *you* must provide (the agent can't)

The agent knows from the Phase 0 checklist *that* these things are needed, but installing
software, creating tokens and getting the PDFs is on you. Runtime is **Windows** (decision log
D16). Check the items off.

### A. Before you even write to the agent

- [ ] **Create the repo** and place the planning docs into the working directory, otherwise the
      agent can't see them:
  - `CLAUDE.md`, `roadmap.md`, `progress.md`, `architecture.md` in the repo root
  - `docs/decisions/` with `README.md` + `001`–`004`
  - this `SETUP.md`
- [ ] **`.gitignore`** with at least: `.env`, `data/`, `__pycache__/`, `.venv/`, `*.wav`,
      model/voice files.
- [ ] **`.env`** (do NOT commit) — copy `.env.example`. Holds **only DMbot's** token + config:
      `DISCORD_TOKEN_DMBOT=…`, `BOT_A_USER_ID=…`, `OLLAMA_HOST=http://localhost:11434`.
      **Bot A's token lives in the music bot's own repo** (two-bot isolation).

> From here the session ritual applies: the agent reads `CLAUDE.md` → `progress.md` →
> the latest ADR and does the handshake.

### B. Phase 0 setup (the actual install work)

#### B1 — Base tooling (Windows)
- [ ] **Git** installed.
- [ ] **Python 3.12** installed.
- [ ] **uv** installed (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`),
      project managed with `uv` — no direct `pip`.
- [ ] Current **NVIDIA driver** for the 4070.

#### B2 — Ollama + models (local on the 4070)
- [ ] **Ollama for Windows** installed (runs as a service on `localhost:11434`).
- [ ] Pull model(s):
  - `ollama pull mistral-nemo` (starting recommendation, ~12B)
  - `ollama pull qwen2.5:14b` (optional, for the taste test)
  - `ollama pull bge-m3` (embeddings for RAG — multilingual; replaced the original
    `nomic-embed-text` plan, which failed German→English retrieval, ADR 019/D45)
- [ ] **Verification (= Phase 0 gate):**
      `curl http://localhost:11434/api/generate -d "{\"model\":\"mistral-nemo\",\"prompt\":\"Say something grim in German.\",\"stream\":false}"`
      → plausible German answer.

#### B3 — faster-whisper on GPU (the Windows stumbling block) — ✅ DONE (2026-06-04)
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

#### B4 — Discord (two bots) — ✅ DONE (2026-06-04)
- [x] **DMbot** created, token in `.env`; **Bot A** (music bot) token in its own repo.
- [x] Privileged intents enabled (Message Content + Server Members + voice); OAuth2 invites with
      Connect/Speak/Send Messages. Both bots verified live in the **same voice channel** — the
      full loop (speak → DM answers aloud) worked. **Bot A must run on its `dungeon_master`
      branch** (the bridge cog `cogs/dm_bridge.py` is only there; `main` → "connection refused").

#### B5 — TTS: XTTS (default) + Piper (fallback) — ✅ DONE (2026-06-04 / GPU 2026-06-05)
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

#### B6 — Audio/Opus (Windows) — ✅ DONE (2026-06-04)
- [x] **Opus** loads via discord.py's **bundled DLL** (no manual install needed) — confirmed in
      Phase 2 (`discord.opus.is_loaded()` true; receive decodes PCM).
- [x] **Microphone** works — live tests with two human speakers transcribed correctly (Phase 3/4).

#### B7 — Game content (PDFs)
- [ ] **Your first system's rulebook as a PDF** (legally owned) into `data/pdfs/` — for the
      first campaign that's **Imperium Maledictum**. Basis for RAG and for the system profile
      the DM proposes (Phase 8/10).
- [ ] **Adventure/story PDF** you want to run, also into `data/pdfs/`.
- [ ] **Character sheets** ready — you transfer these later (Phase 8/9) once into the
      character JSON (shape follows the system profile); they do **not** go into RAG.

#### B8 — Phase 8: real party stats + verify the IM rules
The dice engine, `!test` and the unit tests run against an **example party**
(`data/sessions/_example/characters.json`). To play with real characters and correct rolls:
- [x] **The live circlejerk party is in the repo** — `data/sessions/1343673766487654464/characters.json`
      (Fridolin / Gellicus / Rektalus), tracked, comes with the clone. Playing that channel →
      nothing to do. **Different channel id?** Copy the file into the folder with *your* voice
      channel's id (`data/sessions/<id>/characters.json`), else the example fallback applies. Fill
      each character's `characteristics`, `skills` (the values the engine rolls against),
      `wounds`/`max_wounds`, and the `aliases` map (Discord display name → character name, e.g.
      `"SezBoss69": "Seskin"` — this fixes the model confusing player/character names). The channel
      id is the **voice** channel's id (right-click → Copy ID with Developer Mode on).
- [x] **IM difficulty ladder + SL/auto-band numbers verified** against the Core Rulebook (2026-06-07,
      via `tools/pdf_to_md.py` on the bought PDF) and corrected in
      `data/systems/imperium_maledictum.json` (see its `_note`). Nothing more to do here unless you
      want to tweak labels. (Phase 10's RAG profile bootstrap will later propose such profiles from
      the PDF automatically.)

#### B9 — Phase 10: RAG store + adventure (one-time per machine)
On Tobi's box this is all ✅ done — these steps matter on a **fresh machine** (see **Running on
another machine** for what to copy first). What git carries with the clone: the curated lore
(`data/lore/*.md`, ADR 021) and the German condition values (`data/rules_de/conditions.md`).

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
      uv run python -m dmbot.rag.ingest "data/rules_de/conditions.md" --source conditions
      ```
      `data/rules_de/conditions.md` (German condition game-values) and `data/lore/*.md` are
      hand-written and come **with the clone** (no PDF/`pdf_to_md` needed) — just embed them.
      Idempotent per source. **Deliberate spoiler cuts:** the Setting Guide pages 1–57 only
      ("Villains on Voll" stays out, D46); the Inquisition GM-Guide only its safe reference half
      (pages 4–61, 74–83, 172–174 = Ordos/philosophies, Lex Imperialis, Signs of Chaos/Xenos,
      rosettes, radical methods, bestiary) — the Heresies Macharia campaign (84–121), the
      Sector-Threat villains, the Open Case Files, the inquisitor/patron sheets (incl. Halikarn,
      62–73) and the index (175) stay out. The Player's Guide goes in whole (player-side). Source
      order/labels live in `dmbot/rag/retrieve.py` (`_SOURCES`).
- [ ] **Adventure** — `data/adventures/chemical_burn/` in place (`adventure.json` + `npcs.json`,
      see **Running on another machine**) and `DM_ADVENTURE=chemical_burn` set in `.env`,
      otherwise the DM loads no adventure.
- [ ] **Sanity check:** ask a Chaos or lore question in a live session — a `📚 lore_…:` line
      must appear in `debug.log`; a rule question shows `📚 rulebook:…`.

### C. Only needed later (not for the MVP)

- [ ] **Tailscale** (Personal plan, free) — needed for the **split-hosting** setup (Bot A on one
      machine, DMbot on another; the bridge then sends WAV bytes over the tailnet, ADR 010) and/or
      if Ollama moves to the 5080 (ADR 002). Both machines sign into the **same tailnet**; set
      `DM_BRIDGE_HOST`/`DM_BRIDGE_SECRET` per the README "Split hosting" section. Unnecessary when
      both bots run on one machine (localhost path mode).
- [ ] **Finalize the character JSON schema** — prerequisite for Phase 8 (ADR 004), but not
      a Phase 0 concern yet.

---

## Running on another machine (what git doesn't carry)

A short checklist for a fresh machine (e.g. the 5080 box). The general install is above; here is
only **what git doesn't bring** and what you must get from Tobi.

### 1. Copy from Tobi (not in the repo — bought books / derivatives)

| Path | Content | For |
|---|---|---|
| `data/pdfs/` | bought PDFs **+ the `md/` subfolder** (conversions) | RAG source texts, character-sheet filler |
| `data/adventures/chemical_burn/` | `adventure.json` + `npcs.json` — scene cards + statblocks | the adventure in the DM (ADR 019) |
| `data/vectordb/rag.db` | prebuilt vector DB (rulebook 1505 / player_guide 502 / gm_guide 226 / conditions 13 / setting 201 / lore_imperium 18 / lore_chaos 17 chunks, bge-m3) | retrieval — copying saves the rebuild |

All of this is deliberately **not** in the (public) repo — derivatives of bought books. Sharing
privately is fine, uploading is not. (The lore compendium `data/lore/` *is* in the repo — own
wording of freely available 40k knowledge, comes with the clone.)

**Do not copy** Tobi's `.env` (tokens!). Build your own from `.env.example` — your own Discord
tokens (one token = one live connection), `OLLAMA_HOST`, GPU profile. Important: set
`DM_ADVENTURE=chemical_burn`, otherwise the DM loads no adventure.

### 2. Install yourself
1. Clone both repos: this one (`main`) + `Pr0degie/musicbot` branch `dungeon_master` (Bot A).
   `uv sync` in both.
2. Install Ollama, then **`ollama pull mistral-nemo`** and **`ollama pull bge-m3`** (bge-m3 is
   the vector DB's embedder — without it retrieval stays silent, the rest still runs).
3. The rest (tokens, GPU profile, start order, Tailscale split): see **Install / Configure / Run**
   above and §C.

### 3. Rebuild `rag.db` (only if not copied)
Same command block as **§B9** above — Ollama with `bge-m3` must be running and the PDFs present
(`data/lore/` + `data/rules_de/` come with the clone). The same spoiler cuts apply.

### 4. Playing a session
- Each voice channel needs a party: `data/sessions/<channel-id>/characters.json`. The current
  circlejerk party (channel `1343673766487654464`: Fridolin / Gellicus / Rektalus) is **already
  in the repo** and comes with the clone — same channel, nothing to do. **Different channel id?**
  Copy the file into the folder with *your* id, else the example fallback applies. Only this
  `characters.json` is tracked; runtime state (`state.json`/history/recap) and the sheet PDFs
  under `sheets/` stay local.
- New characters: `docs/how-to-create-a-character.html` (form → JSON) **or** the one-prompt path
  `docs/character-creation-prompt.md` (the player self-interviews → finished JSON). Player rules
  primer: `docs/how-to-play.html`; setting background: `docs/lore.html` (or `!lore` / `!lore chaos`
  in Discord).
- Get both bots into the same voice channel (`!j`), then the session runs. Quick lore check: ask a
  Chaos question — a `📚 lore_chaos:` line must show up in the log.
