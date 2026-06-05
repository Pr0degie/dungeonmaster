# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
**Phases 0–7 complete — PLAYABLE and turn-managed** ⭐. Phase 7 (turn-taking + feedback) is
**live-validated** over four real multi-player sessions (2026-06-05/06): push-to-talk routing,
feedback layer 1, GPU whisper, transcription during DM speech — all working. Most of this session
was **playtest-driven quality tuning** from the players' wishes (read off `transcript.log`): killed
the "Als Spielleitung beschreibe ich" preamble, fixed POV (ihr/euch, not wir/uns), named action
attribution, no auto-advance, no read-aloud disclaimers, varied hooks, `!redo`, mic button anchored
to the bottom, and an XTTS chunking fix for the mid-sentence audio cut-off. **Next: Phase 8** — dice
engine + IM profile + turn buttons (read ADR 005 + 004 + 001). Recommended dial: **Opus 4.8 / xhigh**.
The remaining persona drift is **model-limited** (nemo) — the gemma3:12b taste test is the quality
lever to try alongside.

## Last session
**Phase 7 (feedback layer 2) implemented + a music-bot bridge race fixed (2026-06-05, later).**
- **Bridge race (music-bot repo, own commit `82393da`).** A `!dm` turn ran fully (STT→LLM→TTS) but
  Bot A returned `HTTP 500 'playback failed'` (`ClientException: Already playing audio.`). Root
  cause: the music cog's `after_playing` auto-advances the queue on **any** track end — including
  the bridge's own `vc.stop()` — so two `play()` owners fought over the voice client. Fix: a shared
  `bot.dm_speaking` flag — `dm_bridge._play_file` sets it (finally-cleared) around playback, and
  `music.play_next` bails while it's set (at the top + again right before `vc.play()`, re-queuing the
  popped track). Diagnosis came straight from `logs/dmbot.log` (now opt-in `DM_LOG_FILE=1`) + the
  music bot's `bot.log`. _Tobi must restart the music bot to load it._
- **Phase 7 — turn-taking & feedback protection layer 2 (this repo).** `VadSink.mute()/unmute()`
  pause the whole segmentation pipeline while Bot A speaks; `voice/commands._speak` mutes around the
  blocking `/speak` and unmutes in `finally`. `mute()` flushes open utterances so pre-DM speech is
  buffered, not glued across the gap. `!leave` now resets per-channel session state
  (`DMBrain.reset` + sink/counters). New `tests/test_feedback_layer2.py`. _(No new ADR — this
  implements ADR 003's existing layer-2 mandate, no fresh trade-off.)_ **Live-tested by Tobi: layer 2
  works (no feedback).**
- **Playability tuning — players' input now drives the narration more (Phase-5 open tuning).** Live
  play showed nemo drifting: it set atmosphere and continued its own thread instead of resolving the
  stated action, and opened every turn with a "Als Spielleitung beschreibe ich:" preamble. Two
  levers (Tobi picked both): (1) **persona sharpened** — new top section "Worauf du reagierst"
  makes resolving the latest action the primary directive + forbids the preamble; (2) **buffer
  noise cut** — `DMBrain` now forwards only the most recent `DM_MAX_LINES` (default 8) so table
  talk between !dm presses doesn't drown the action. Plus `_sanitize` strips the preamble as a net.
  _Still open: the nemo-vs-gemma3:12b taste test._
- **First live session → the criticism-driven fixes (D24/ADR 011).** Read `logs/dmbot.log` of a real
  4-player run. Findings + fixes: **(1) STT ~1.5 min behind** (unbounded queue + CPU whisper + all
  table talk) → **GPU whisper** + **push-to-talk button** so only DM-directed speech is transcribed;
  **(2) the DM answered AS a player** ("SezBoss69: …") → `_strip_leading_label` (the `\n<label>:` stop
  misses a leading label; `_cut_at_labels` skips position 0); **(3) preamble** → sanitized.
- **Second live session → playability polish (the players' requests).** Push-to-talk + GPU whisper
  confirmed working live (`→DM` markers, ~100–1000 ms transcribe). Five fixes from their feedback:
  **(1)** persona forbids the read-aloud meta-disclaimer + `_sanitize` strips a trailing meta
  parenthetical ("(Bitte beachte…)"); **(2)** new persona section: NPCs in **third person**, no
  "Tech-Priester:" script, never address a player AS the NPC; **(3)** vary the closing hook (not
  always "Was tut ihr?"); **(4)** the mic button is **re-posted to the bottom** after each DM turn
  (`_post_mic_button`, delete+resend) so it stops scrolling away; **(5)** a clean **session
  transcript** `logs/transcript.log` (`DM_TRANSCRIPT_FILE=1`) — just the conversation (player lines
  incl. table talk + DM answers) with timestamps, separate from the debug log. Suite **22/22**.
  _Live-tested: layer 2 + push-to-talk + GPU whisper work; the persona/UI polish is NOT yet live-tested._
- **Feedback layer 2 → opt-in, off by default (D25).** Tobi wanted the table to keep being
  transcribed *while the DM speaks* (full record). Layer 1 (Bot-A user-ID filter) already blocks
  self-transcription and the routing gate keeps narration table talk out of the DM, so the VAD pause
  was redundant. Now `DM_PAUSE_VAD_WHILE_SPEAKING=0` by default; mechanism kept for mic-bleed cases.
  `architecture.md` §5 updated; golden rule #4 (layer 1) unchanged.
- **Third live session → more persona/quality fixes.** From the transcript: **(A)** the
  "Als Spielleitung beschreibe ich …" preamble was *still* there — my `_META_PREAMBLE` only matched
  the colon form; rewrote it to strip the colon-less shapes too ("… beschreibe ich die Szene, wie …",
  "… eine dunkle Gasse …") and re-capitalise. **(B)** persona: the DM is **not** in the party — say
  "ihr/euch", never "wir/uns/ich" inside the scene (it kept writing "auf uns zu", "sehen wir").
  **(C)** ask "Was tut ihr?" only when something open is presented, never every turn, never with
  action suggestions. **(D)** no content warnings / lectures / setting commentary (turn 1 produced an
  LGBTQ disclaimer). **(E)** new **`!redo`/`!r`** — re-run the last DM turn with the same input
  (DMBrain.redo, replaces the last history pair) for when the DM misunderstood. Suite **25/25**.
  _Open (F): player→character name mapping_ — the LLM confuses "SezBoss69" vs the character "Seskin"
  and mixes up who did what. Belongs to character registration (D13/ADR 003, Phase 8); a light alias
  map could help sooner.
- **Fourth live session → audio bug + more persona.** **(J)** real bug: XTTS truncates a single
  chunk >253 chars for German (the "bricht mitten im Satz ab" reports) — the wrapper now splits a
  long answer into <240-char chunks (`tts/textsplit.py`, unit-tested) and concatenates the WAVs.
  Persona: **(G)** attribute each action to the *named* player when several acted, not a vague
  "du/dein"; **(H)** don't auto-advance — answer the immediate thing (esp. a perception question),
  NPCs wait until the group reacts; **(I)** engage with *every* player action incl. provocative
  ones, don't dodge/sanitise (model-dependent). Suite **29/29**.
  _Open (K) — Phase-8 dice design input from the players:_ a real GM rolls **for** the player
  ("ich würfle für Tobi auf Spurenlesen, Wert 6, Ziel 12 — nicht geschafft"); skill-check
  **difficulty** must come from the system profile / rulebook, the LLM can't balance it on the fly.
  Confirms "dice = code" (golden rule #2) — fold into ADR 005 / the engine when building Phase 8.

**(Earlier same day) GPU XTTS via CUDA torch + portable per-machine GPU profiles (non-Phase work, ADR 009).** The
GPU rebalance (whisper→CPU, XTTS→cuda) crashed at first: the venv's torch was the **CPU-only**
build, so `TTS_DEVICE=cuda` raised `Torch not compiled with CUDA enabled` and left the DM mute.
Fixed end to end:

- **CUDA torch:** `torch`/`torchaudio`/`torchcodec` now pulled from the PyTorch **cu130** index
  (CUDA 13.0; `[tool.uv.sources]` + `[[tool.uv.index]]`). Verified live: `torch 2.12.0+cu130`,
  `cuda available: True`, XTTS `loaded on cuda`, RTF **0.34** (≈3× realtime; CPU was ~1.9).
  _(Started on cu126, but that tops out at sm_90 and failed on a colleague's **RTX 5080**
  (Blackwell, sm_120) — moved to cu130, which covers Ada (4070) + Blackwell (5080); re-verified
  on the 4070.)_ Then GPU whisper on the 5080 died at `encode()` with **`cublas64_12.dll cannot
  be loaded`**: `nvidia-cuda-runtime-cu12` (cudart64_12.dll, a cuBLAS dependency) was missing.
  Added it as a win32 dep. **But that alone still failed on the 5080** — root cause: `os.add_dll_directory`
  is not enough, CTranslate2's loader doesn't reliably search the added user dirs, so it only worked
  on the 4070 because that box has a **system CUDA toolkit (v12.3) on PATH**; the fresh 5080 box has
  none. Fix: `transcriber._register_cuda_dll_dirs` now **preloads the CUDA-12 DLLs by full path**
  (`ctypes.WinDLL`, in dep order cudart→cublasLt→cublas→cudnn). **Verified on the 4070 with the system
  CUDA stripped from PATH** (simulating the 5080) — GPU whisper runs. Lesson: ctranslate2's CUDA-12
  trio (cublas + cudnn + **cudart**) must be self-complete *and explicitly preloaded*, independent of
  torch's CUDA version and of any system CUDA install. **Result: the 5080 runs everything on GPU**
  (XTTS cuda + whisper cuda), full voice receive + transcription confirmed by the colleague.
- **Log noise tamed:** voice-recv's benign `Error unpacking packet` RTP-parse flood (alpha lib,
  drops the odd packet, audio keeps flowing) is now throttled in `logsetup.py` — first occurrence
  logged, then a running count every 500th, tracebacks suppressed (console + file).
- **Diagnostic tool:** `tools/diag_stt.py` — one-shot CUDA/STT check (commit, wheels, DLL preload,
  torch GPU, a real cuda transcription) for debugging a fresh box remotely.
- **Resolver fix:** CUDA torch pins `nvidia-cudnn-cu12==9.10.2.21` on linux, clashing with
  faster-whisper's `>=9.23`. Resolved by locking **win32-only** (`environments = ["sys_platform
  == 'win32'"]`, legit per D16) + `requires-python` pinned to the 3.12 line + win32 markers on
  the cudnn/cublas wheels. Lock is now Windows-only.
- **Robust device:** `dmbot/tts/xtts.py` `_resolve_device` + load-time fallback → XTTS degrades to
  CPU (warns, never crashes) when CUDA is absent or the GPU OOMs. Same `.env` is portable.
- **httpx bug:** found `httpx` was an **undeclared direct dep** (used by `llm/client.py` +
  `bridge.py`); the dep churn dropped it. Now declared `httpx>=0.28.1`.
- **Profiles + docs:** `.env` = 4070 dev profile; `.env.example` documents both (4070 dev / 5080
  full-GPU); `architecture.md` §3 updated; **ADR 009** written; README gained a "Running on
  another machine" section; `docs/SETUP.md` token-var line corrected (`DISCORD_TOKEN_DMBOT`, Bot A
  token lives in the music bot repo). Voice-stack smoke test re-run after the dep change: **5/5**.

**Then (same session) — playability + ops polish:**
- **XTTS is now the default engine** (Piper = fallback); D21 flipped once XTTS ran on GPU.
- **Answer length capped** (`DM_NUM_PREDICT`, env, default 220) + sentence-trim on a cut turn +
  persona tightened ("2–4 Sätze, keine Monologe") — XTTS-GPU made monologues the latency, not TTS.
- **Prompt shutdown:** transcriber `stop()` drops its backlog + short join (daemon), run off the
  loop in `cog_unload` → one Ctrl+C, no "heartbeat blocked" hang.
- **Bridge debuggability:** `!say` reports playback failure instead of a false 🔊; `bridge.speak`
  surfaces the bridge's real reason (401/404/409/unreachable). This pinned the colleague's issue to
  Bot A not reachable / not in voice (not a WAV/path bug).
- **Network bridge (ADR 010, D23):** hybrid `/speak` — loopback sends the WAV *path* (unchanged),
  remote sends the WAV *bytes* + shared secret (`DM_BRIDGE_SECRET`) over Tailscale; Bot A plays its
  own copy. **Both repos changed** (DMbot + the music bot's `cogs/dm_bridge.py`, its own commit).
  Localhost path mode verified unchanged; the remote/Tailscale path is **implemented but not yet
  live-tested** (they run both bots on one machine for now). Split-hosting documented in the README.
- **Lean logging:** console shows only `dmbot.*` lines + WARN/ERROR (timestamps kept); the
  full file log `logs/dmbot.log` is **off by default**, opt-in via `DM_LOG_FILE=1`; the benign
  voice-recv unpack notice is kept off the console (file-only).

_(Prior session — voice-stack hardening, ADR 006 — and Phases 3–6 (the playable loop) are captured
in ADR 006 and each phase's VERIFY EVIDENCE below.)_

## Next concrete step
**Phase 8 — dice engine, system profile & turn-order buttons.** Phase 7 is live-validated; this is
the next phase. Phase-transition ritual: read **ADR 005** (generic engine + profile) + **ADR 004**
(test marker, character JSON) + **ADR 001** (IM specifics) before implementing. Build the
deterministic core (`rules/engine.py` + the first profile `data/systems/imperium_maledictum.json`,
**pytest, fixed seed**) — golden rule #2: dice = code, never the LLM. The players already sketched
the contract (open item K): a real GM rolls **for** the player and the **difficulty comes from the
profile/rulebook**, not the LLM. The `discord_ui/mic.py` View→cog pattern is the template for the
dice/turn buttons. Dial: **Opus 4.8 / xhigh**.

**In parallel — the gemma3:12b taste test** (quick, high-leverage): set `OLLAMA_MODEL=gemma3:12b`
(pull it first) and replay a scene. Most of the residual persona drift (action attribution, not
dodging provocative input, POV) is nemo's weakness, not the prompt — gemma3 may follow the sharpened
persona better. If it does, flip the default; if not, the persona is already as tight as it gets.

_Carry-overs (verify in a live run, not code) — Tobi said he'll test these during development:_
1. **Dialogue loop** end-to-end on the 5080 host: `!j` → speak → `!dm` answers aloud, and a 2nd
   `!dm` keeps the per-channel history. (Fill Phase-6 evidence once confirmed on that box.)
2. **Answer length** by ear — tune `DM_NUM_PREDICT` if turns feel long/clipped.
3. **Prompt Ctrl+C shutdown** — confirm one Ctrl+C exits cleanly.
4. **Remote/Tailscale bridge (ADR 010)** — implemented, **never live-tested**; do the two-machine
   check in the README "Split hosting" section when they want it (currently both bots on one box).
5. Older: STT confidence filter on noisy speech; `gemma3:12b` vs `mistral-nemo` persona taste test;
   the toggleable edit/review window (Part 2 backlog). **Input bleed:** a player's stream audio
   leaking into the mic gets transcribed — an input-discipline / future wake-word concern, not a bug.

---

## Decision log

**This log is the index to the ADRs.** Each row with a real trade-off links its decision to
a full ADR under `docs/decisions/` (the `→ ADR NNN` at the end of the rationale). The
session-start read covers only the *newest* ADR for recency; the **older ADRs are read on
demand** — when you start a phase or touch a subsystem, follow the `→ ADR` links of the
decisions that govern it (see the phase → ADR map below). A new non-trivial decision →
create the next-numbered ADR.

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Ruleset approach | **System-agnostic** — generic engine + per-system profile; **Imperium Maledictum is the first** profile (1d100 roll-under, SL) | Reusable DM, not a 40k one-off; IM only the first loaded system → ADR 005 |
| D2 | Mechanic depth v1 | Voice narration **+ dice & turn buttons** in the text channel | Playable without the bot having to manage all the rules |
| D3 | Memory | **JSON world state + session recaps** | JSON = hard facts, recap = narrative thread; together coherent without context overflow |
| D4 | Knowledge source | **RAG over rulebook & story PDFs** (NOT character sheets) | Rule knowledge ingestible; reduces rule hallucination. Sheets → JSON (D12) |
| D5 | Bot language | **Python (discord.py)** for both bots | Music bot is discord.py; the voice-recv ecosystem is Python |
| D6 | LLM host | **Dev: everything local on Tobi's 4070** (Nemo 12B); later optionally only Ollama on the 5080 via Tailscale | Develop/debug locally; separate networks are a non-issue for the MVP; upgrade = one `OLLAMA_HOST` switch → ADR 002 |
| D7 | Language/tone | **German play language**; generic GM persona + **per-campaign tone overlay** (first: Eisenhorn / Dan Abnett grimdark) | Tone is campaign-specific, not the DM's fixed identity → ADR 005 |
| D8 | Player count | 2–5, semi-turn-based | — |
| D9 | Output bot | **Reuse the music bot** + `/speak` bridge | Already in the voice channel, can play audio |
| D10 | Conversational control | **Transcribe continuously + buffer, DM turn triggered by button**; VAD only for segmentation. Wake word is a later goal | DM doesn't talk over anyone, no table talk in the game, semi-turn-based → ADR 003 |
| D11 | Dice test trigger | **LLM emits a test marker** (`<<TEST …>>`), code rolls; manual button fallback | Loop mostly automatic but robust against parse errors → ADR 004 |
| D12 | Character data | **Lean structured JSON**; the stat/skill/resource shape follows the **active system profile**; sheets transferred once, NOT RAG | Enables stat-aware rolls + resource tracking per system; Phases 8/9 one piece → ADR 004 + 005 |
| D13 | Registration | **Guided & sequential** — bot asks character by character, a click maps user-ID → character | Bot must know who plays whom (addressing + rolls) → ADR 003 |
| D14 | Recap trigger | **`wrap up` command** ends the session & generates the recap; rolling mid-summary later | Clear trigger; 128k context has headroom |
| D15 | Bot A signal | **`/speak` blocks until playback ends** | Return moment = resume signal; no status/shared state needed. _Confirmed in implementation (commit `249cc38`); a redundant callback was removed._ |
| D16 | Runtime environment | **Windows** (both bots + pipeline) | No `/tmp` (OS temp dir); Opus DLL for voice; cuDNN/cuBLAS DLLs on `PATH` for faster-whisper. _WSL considered but rejected — keeps both bots co-located so the file-path bridge works without path translation. Co-location is no longer mandatory: the bridge now also runs split across machines via bytes-over-Tailscale (D23 / ADR 010)._ |
| D17 | Doc language | **Dev docs in English** (game content stays German) | Token efficiency on docs read every session; matches the schema precedent |
| D18 | System-agnostic engine | **Generic dice/resolution engine + per-system profile**; DM **proposes the profile from the PDF**, user confirms (MVP). Persona = generic GM + per-campaign tone overlay | Reusable across rulesets; "paste PDFs → DM knows what's played"; dice still code → ADR 005 |
| D19 | DAVE/E2EE on voice receive | **Decrypt the DAVE layer via discord.py's `dave_session`** (keep E2EE; sink takes `wants_opus=True`, decrypts each frame before Opus-decode) | Discord calls are end-to-end encrypted; voice-recv only undoes transport → garbage. Declining DAVE is rejected (voice close 4017) → ADR 006 |
| D20 | VAD segmentation stack | **silero-vad via `onnxruntime`** (no torch) + **`soxr`** streaming resampler; model vendored in-repo | Robust neural VAD without torch's ~GB weight; webrtcvad too noise-prone; soxr is the smallest correct resampler → ADR 007 |
| D21 | TTS engine | **XTTS v2 (`coqui-tts`) default + Piper fallback**, selectable via `TTS_ENGINE`; XTTS speaker **Dionisio Schuyler**. _(Default flipped Piper→XTTS 2026-06-05 once XTTS ran on GPU.)_ | Piper's German voices were rejected; XTTS gives 58 voices + cloning (local, no cloud); torch is a hard dep regardless + XTTS degrades to CPU, so it's a safe default → ADR 008 + 009 |
| D22 | GPU XTTS / portability | **CUDA torch from the `cu130` index** (`+cu130` builds; CUDA 13.0 covers Ada **and** Blackwell), device env-driven (`TTS_DEVICE`/`WHISPER_DEVICE`); same Windows-only lock for both boxes, XTTS auto-degrades to CPU | CPU-only torch made GPU XTTS impossible; cu130 gives the GPU build (RTF 0.34 verified) for both 4070 (sm_89) + 5080 (sm_120); win32-only lock dodges the cudnn pin clash; one repo runs 4070 dev + 5080 full-GPU → ADR 009 |
| D23 | Bridge transport | **Hybrid `/speak`**: loopback → WAV path (unchanged); remote → WAV bytes + shared secret over Tailscale; Bot A plays its own copy | Lets DMbot + Bot A run on different machines without breaking the proven localhost path; partially relaxes D16/ADR 002 co-location for the bridge → ADR 010 |
| D24 | STT latency | **GPU whisper** (`WHISPER_DEVICE=cuda`) **+ push-to-talk DM-routing gate** (shared Discord mic button; whole table always transcribed + logged, button gates only what reaches the DM, `DM_PUSH_TO_TALK=1`) | CPU whisper fell ~1.5 min behind; GPU + routing only the button-window speech to the DM keeps the full transcript record (Tobi's call) while cutting DM noise. Supersedes the 4070 "whisper on CPU" profile → ADR 011 |
| D25 | Feedback layer 2 | **Pausing the VAD while Bot A speaks is now opt-in, off by default** (`DM_PAUSE_VAD_WHILE_SPEAKING=0`). Layer 1 (Bot-A user-ID filter) stays mandatory | Layer 1 already stops self-transcription and the push-to-talk routing gate keeps narration table talk out of the DM, so layer 2 was redundant and blocked transcription during the DM's narration — players wanted the table kept in the record. golden rule #4 (layer 1) unchanged; updates `architecture.md` §5 |

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM) + `architecture.md` §3 (bridge contract) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) + **ADR 011** (STT latency: push-to-talk gate) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) |

---

## Phase status (Part 1 — MVP)

Legend: ⬜ open · 🔄 in progress · ✅ done (with proof)

### ✅ Phase 0 — Foundation & setup
- [x] Repo + project structure (skeleton per `architecture.md` §12; uv/Python-3.12, `.gitignore`, `.env.example`)
- [x] Discord DMbot app + token (in `.env`). _(Bot A token already exists in the music bot repo.)_
- [x] Ollama installed locally on the 4070 + models pulled (`mistral-nemo`, `nomic-embed-text`) + reachable
- [x] Model taste test → primary model chosen: **mistral-nemo**
- **Manual setup (outside the agent): see `docs/SETUP.md`.**
- **Gate:** `curl` to Ollama from Tobi's machine → German answer.
- **VERIFY EVIDENCE:** Gate met 2026-06-04 — `curl http://localhost:11434/api/generate` with
  `mistral-nemo` returned a plausible grimdark German answer ("Die Finsternis hat sich über die
  Welt gelegt wie ein Grabtuch aus Eisen…"). Tooling: git 2.42, Python 3.12.10, uv 0.11.19,
  Ollama 0.30.4 on `:11434`, models `mistral-nemo` + `nomic-embed-text` pulled, NVIDIA 596.49
  (RTX 4070). Discord DMbot created, token in `.env`. **Primary model: `mistral-nemo`**, chosen
  via taste test (scene description + NSC dialogue) over gemma3:12b / qwen3.5:9b / glm-4.7-flash
  (glm 19 GB doesn't fit 12 GB; nemo gave the most idiomatic German + dialogue). Deferred to
  later phases (flagged, not blocking): cuDNN/cuBLAS DLLs (B3→Phase 4), Piper voice (B5→Phase 6),
  Opus DLL + mic (B6→Phase 2), rulebook/adventure PDFs (B7→Phase 10).

### ✅ Phase 1 — Bridge: Bot A `/speak`  (Bot A side done, out of order)
- [x] `POST /speak` (aiohttp) in the music bot
- [x] `/speak` blocks until playback ends (return = resume signal)
- [x] `/health` + `!dm` status command; localhost only; serialized by lock; music stopped first
- **Gate:** `curl -X POST .../speak` with a test WAV → audible.
- **VERIFY EVIDENCE:** Implemented & code-reviewed — `Pr0degie/musicbot` branch
  `dungeon_master`, commit `249cc38`. Contract in `architecture.md` §3. Music cogs untouched.
  **Gate met 2026-06-04:** `GET /health` → `{"status":"ok","bot":"EarRape#8961"}`;
  `curl -X POST :8765/speak` with a 2 s test WAV (both bots in voice channel `circlejerk`) →
  `HTTP 200 {"status":"played"}`, the call **blocked 2.09 s** (= the WAV's full length,
  confirming the blocking-return contract D15), and Tobi confirmed the tone was **audible**.

### ✅ Phase 2 — DMbot scaffold: voice receive
- [x] Voice join + `discord-ext-voice-recv` sink (`!join`/`!j`/`!leave`/`!vstatus`)
- [x] per-user PCM log (decoded 48 kHz stereo s16le; heartbeat every 2 s)
- [x] Bot A's user-ID filtered (protection layer 1) — explicit `BOT_A_USER_ID` + `.bot` flag
- [x] Windows: Opus loaded via discord.py's bundled DLL (B6 satisfied, no manual install)
- [x] _(unforeseen)_ DAVE/E2EE layer decrypted on receive → clean Opus (ADR 006)
- **Gate:** PCM frames in the log; Bot A's own voice absent.
- **VERIFY EVIDENCE:** Gate met 2026-06-04. Live test in voice channel `circlejerk`: two human
  speakers (`Pr0degie`, `Timo`) logged with `▶ receiving audio` + `PCM ⟳` heartbeats; **Bot A
  ("EarRape", id 1361375360784273409) filtered** — `layer-1: filtering out …`, never tallied.
  After wiring the DAVE/E2EE decrypt (ADR 006): consistent Opus TOC `0x78…`, **~100 % decode,
  0 dropped**; a captured WAV analysed as real speech (ZCR 0.061, 13 % silent frames). Stack:
  `discord.py 2.7.1`, `discord-ext-voice-recv 0.5.2a179`, `davey 0.1.4`, Opus bundled DLL.
  Remaining `lost being flushed` jitter (sender voice-activation) is benign, quieted in logs.

### ✅ Phase 3 — VAD segmentation
- [x] Resample 48k/stereo → 16k/mono (`voice/resample.py`, `soxr.ResampleStream` per user)
- [x] silero-vad → cut utterances (`voice/vad.py`; onnx via onnxruntime, ADR 007; wired as `VadSink`)
- [x] **Live gate met** — clean per-speaker utterances; Tobi confirmed the WAVs sound right
- **Gate:** one sentence = one utterance, start/end correct.
- **VERIFY EVIDENCE:** _Offline (2026-06-04):_ resample ratio ≈ 16000 samples/s; pure silence →
  **0 utterances** (no false trigger); `UtteranceSegmenter` state machine verified with a
  scripted fake model — clean utterance cut=1, sub-250 ms blip dropped, mid-sentence pause
  <600 ms not split, real >600 ms gap splits into 2, flush mid-speech emits. Stack:
  `onnxruntime 1.26.0`, `soxr 1.1.0`, `numpy 2.4.6`, vendored silero v5 onnx (~2 MB).
  _Live (2026-06-04):_ first live run surfaced **two bugs, both fixed + offline-reproduced:**
  (1) silero v5 needs a **64-sample context** prepended (576-sample input, not bare 512) — bare
  512 scored prob≈0 on clear speech (0/1874 frames), fixed → 1451/1874 voiced; (2) **voice
  activation** means clients send no RTP while silent, so utterances never closed — fixed by
  wrapping in `SilenceGeneratorSink` (injects silence; lock-guarded sink). After the fixes a
  live utterance + WAV was produced. _Final gate met (2026-06-04):_ clean run (bot start
  18:56:56) segmented **both** speakers per sentence — Pr0degie 9 utterances (0.99–5.06 s),
  Timo 4 (1.06–8.51 s), each dumped as a 16 kHz mono WAV; **Tobi listened to the WAVs and
  confirmed they sound clean/correct**. Utterances also close now while a speaker is silent
  (silence injection), so separate sentences no longer merge. Stack live: `discord.py 2.7.1`,
  `discord-ext-voice-recv 0.5.2a179`, `onnxruntime 1.26.0`, `soxr 1.1.0`.

### ✅ Phase 4 — STT (faster-whisper)
- [x] faster-whisper wrapper (`dmbot/stt/transcriber.py`): worker thread + queue (off the audio
      path), 16k mono s16le → German text via `WhisperModel`, CPU-int8 fallback
- [x] Windows cuDNN/cuBLAS: `os.add_dll_directory()` for the `nvidia-*-cu12` wheel `bin` dirs in
      `stt/transcriber.py` — no manual `PATH` (SETUP B3 done)
- [x] Wired into `VoiceReceiveCog`: `_on_utterance` → `transcriber.submit`; transcript logged
      as `📝 <name> | <clip>·<ms> | <text>`; model via `WHISPER_MODEL/DEVICE/COMPUTE` env
- [x] **`medium` is the default** (beat `small` clearly in the live German test)
- [x] Hallucination guard: drop segments with high `no_speech_prob` / low `avg_logprob`
      (kills the "Vielen Dank für's Zuhören" phantoms on short/quiet clips)
- **Gate:** German sentence transcribed correctly.
- **VERIFY EVIDENCE:** _Live (2026-06-04):_ a ~16-min two-speaker session transcribed German
  correctly throughout — long, complex, well-punctuated sentences (e.g. *"Nichtsdestotrotz steht
  mir der Christoph, Markos Vater im Wege."*; a 60-word run captured verbatim). Players confirmed
  in-channel: *"ihr habt's perfekt transkribiert"* + *"ging echt schnell"*. `medium` clearly beat
  `small` (small mis-heard the quieter speaker; medium got him). GPU: `faster-whisper 'medium'
  loaded on cuda (float16)` via in-code DLL registration; ~0.77 s to transcribe 8 s audio.
  Remaining: rare stock-phrase hallucinations on short/near-silent clips → now filtered by
  confidence. Stack: `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `nvidia-cudnn-cu12 9.23`.

### ✅ Phase 5 — LLM wiring + DM persona
- [x] Ollama client (`llm/client.py`, async httpx, `/api/chat`; host+model from config — ADR 002)
- [x] `prompts/dm_core_de.md` (generic GM persona, German) + `campaign_tone_de.md` (Eisenhorn overlay) — layered loader `llm/persona.py` (ADR 005)
- [x] `DMBrain` (`orchestrator.py`): per-channel history (in-memory) + lock-guarded player-line buffer
- [x] Wired: voice transcripts buffer per channel; `!dm` / `!dm <Text>` triggers a turn → answer logged `🎭` + posted to the text channel
- [x] Output hygiene for TTS: strip role labels/markdown; `stop` sequences + truncation so the model plays **one** DM turn and never fabricates player replies
- **Gate:** text prompt → German DM answer in the campaign's tone.
- **VERIFY EVIDENCE:** _Offline (2026-06-04), real Ollama + `mistral-nemo` + the real persona:_ a
  German player line ("Ich öffne die schwere Eisentür…") yields an atmospheric grimdark DM answer
  in Eisenhorn tone (flackernde Lumen, Rost/Weihrauch, ein Adept-NSC mit Stimme), addresses players
  by name, ends with "Was tut ihr?"; a follow-up turn correctly uses the history. After hardening:
  exactly one DM turn, no fabricated player lines, no "Spielleitung:"/markdown leakage.
  _Tuning (2026-06-05, after live play):_ nemo added a "Als Spielleitung beschreibe ich:" preamble
  and drifted off the players' actions → **mitigated** — persona sharpened (top "Worauf du
  reagierst" directive), buffer capped to the recent `DM_MAX_LINES`, `_sanitize` strips the
  preamble (`tests/test_orchestrator.py`). _Still open:_ the **nemo vs gemma3:12b** taste test with
  this persona, if the tone/responsiveness still needs more.

### ✅ Phase 6 — TTS + first full loop ⭐  (PLAYABLE)
- [x] Piper wrapper (`tts/piper.py`): `de_DE-thorsten-medium` → WAV in the OS temp dir
      (`tempfile.gettempdir()`, not `/tmp`); loaded once, synth off the event loop
- [x] Bridge client (`bridge.py`): async httpx `GET /health` + blocking `POST /speak`
      (architecture §3 contract); WAV deleted after playback so temp doesn't fill
- [x] Wired: `!dm` answer → Piper → `/speak` (spoken); `!say <Text>` smoke test; LLM + TTS
      times logged (`⏱`, `🔊`). Piper missing → text-only, bot still runs
- [x] **Live full loop confirmed** (2026-06-04, 21:37): `!dm` → German DM answer → spoken aloud,
      Tobi heard it; no self-hearing (layer-1 filters Bot A)
- **Gate:** speak → DM answers audibly; latency measured; no self-hearing.
- **VERIFY EVIDENCE:** Live full loop works end to end and is **audible** (player line → nemo →
  Piper → Bot A `/speak`). Piper: voice loads ~1.3 s, synth ~130–1250 ms (length-dependent).
  **Latency caveat (the Phase-6 tuning target):** `⏱ LLM = 15.2 s` on the first turn. Root cause
  is **VRAM pressure** — `ollama ps` shows nemo at **9.5 GB / 100% GPU with a 16384 context**, and
  total VRAM sat at **11.8/12.3 GB** (nemo + whisper-medium 2.5 GB + desktop apps), so nemo
  cold-loads/runs under near-full memory. _Mitigations applied in code:_ `num_ctx=8192` (smaller
  KV cache) + `keep_alive=30m` (no cold reload between turns). _Biggest remaining lever (Tobi):_
  run whisper on CPU or `small` to free ~2.5 GB, and/or offload Ollama to the 5080 via Tailscale
  (ADR 002). Bridge fix this session: Bot A had to be on the `dungeon_master` branch (the `main`
  branch has no DMBridge → "All connection attempts failed").

### ✅ Phase 7 — Turn-taking & feedback protection layer 2  (live-validated)
- [x] VAD pause while Bot A speaks — `VadSink.mute()/unmute()` (`voice/recv.py`); `_speak()` mutes
      around the **blocking** `/speak` and unmutes in `finally` (D15: blocking return = Bot A quiet).
      `mute()` flushes in-progress utterances first. **Now opt-in, off by default** (D25,
      `DM_PAUSE_VAD_WHILE_SPEAKING=0`): redundant beside layer 1 + the routing gate, and it blocked
      transcribing the table during narration — which players wanted recorded. Mechanism kept for
      mic-bleed cases. Layer 1 (Bot-A user-ID filter) stays mandatory (golden rule #4).
- [x] Session state per channel — cog keeps the `self._sink` handle (set on `!join`); `!leave`
      now `self._brain.reset(channel)` + drops the sink + clears the per-user counters, so a
      re-join starts a fresh session.
- [x] **Push-to-talk DM-routing gate (D24/ADR 011)** — a shared Discord mic button (`discord_ui/mic.py`,
      the project's first View). The whole table is **always transcribed + logged** (full record,
      Tobi wanted it — recap/memory groundwork); the button gates only **what reaches the DM**:
      utterances are tagged `for_dm` when cut (carried through the STT worker) and only those are
      buffered. `→DM` marks routed lines in the log. `!mic` re-posts; `DM_PUSH_TO_TALK=0` routes all.
- [x] **Latency + quality fixes from the first live session** — GPU whisper (`WHISPER_DEVICE=cuda`,
      D24); buffer capped to recent `DM_MAX_LINES` (default 8) so table talk doesn't drown the action;
      persona sharpened (action-resolution as the top directive); `_sanitize`/`_strip_leading_label`
      kill the "Als Spielleitung beschreibe ich:" preamble and a leaked leading "Name:" (the DM was
      answering **as** a player — `tests/test_orchestrator.py`).
- [x] **Unit tests** (deterministic parts): `tests/test_feedback_layer2.py` (mute + listen gate)
      + `tests/test_orchestrator.py` (sanitize, label strip, buffer cap). **20/20 green.**
- **Gate:** two people speak → orderly reaction, no feedback loop.
- **VERIFY EVIDENCE:** _Live, four real multi-player sessions (2026-06-05/06, 3 players: Timo,
  Sezgin/SezBoss69, Pr0degie)._ Confirmed in the transcripts: multiple speakers captured per-user;
  **push-to-talk routing works** — only button-window speech carries the `→DM` marker and reaches
  the DM, the rest is log-only (`push-to-talk → 🎙 an die Spielleitung` / `⏸ nur Protokoll`);
  **no feedback loop** — Bot A filtered every turn (`layer-1: filtering out EarRape`), the DM never
  re-transcribed its own voice; the DM answers the routed lines **in order**; players confirmed
  "transkribiert er unsre Zeug trotzdem noch" while the DM spoke (layer-2 opt-out working). GPU
  whisper kept up (~100–1000 ms/clip). Quality tuning (preamble, POV, no-advance, TTS chunking) was
  done from these transcripts and is in the unit suite (**29/29**) — but is **persona/model-limited**
  (nemo); residual drift is the gemma3 lever, not a Phase-7 gate failure.

### ⬜ Phase 8 — Dice engine, system profile & turn-order buttons
- [ ] `rules/engine.py` — generic dice + resolution engine (profile-driven) **+ unit tests**
- [ ] `data/systems/imperium_maledictum.json` — first profile, hand-written (1d100, roll-under, SL, d10/d5)
- [ ] Text-channel view with buttons + "whose turn it is"
- [ ] LLM requests a test via marker → engine rolls per active profile → back into context
- **Gate:** button roll correct (result + degrees for the profile); turn order rotates; tests green.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 9 — Memory (JSON + recaps)
- [ ] JSON world state + deterministic advancement
- [ ] Recap generation + re-injection
- **Gate:** HP change survives a restart; next session starts with a correct recap.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 10 — RAG over PDFs + system-profile bootstrap
- [ ] Ingestion (PDF → chunks → embeddings → store) for rulebook/lore/adventure
- [ ] Retrieval into the prompt
- [ ] Profile bootstrap: DM proposes a draft system profile from the rulebook → user confirms → saved
- **Gate:** a concrete rule question answered correctly from the PDF; a fresh ruleset yields a working profile.
- **VERIFY EVIDENCE:** _(empty)_

---

## Part 2 — Beyond the MVP (backlog)
- [ ] **XTTS as its own process/service** — XTTS v2 (`coqui-tts`) is wired in-process as an
      alternative TTS (`TTS_ENGINE=xtts`, picked speaker **Dionisio Schuyler**), but it drags the
      torch/torchaudio/torchcodec stack into the bot venv and is slow on CPU (~1.5× realtime).
      Move it behind a small local service (own venv, GPU once VRAM is freed) to keep DMbot lean
      and get near-realtime synthesis. Until then it runs on CPU. _Tobi chose Dionisio 2026-06-04
      after auditioning all 58 built-in speakers (samples in `voices/samples/`, pitch-ranked)._
- [ ] **Edit/review window before the DM speaks** — a toggleable human-in-the-loop step that
      briefly intercepts the DM response (and optionally the transcript) so a player can read /
      correct it before TTS. Off once trusted, so play flows. _Requested live by Pr0degie + Timo,
      2026-06-04; fits Phase 7 (turn-taking) — keep it switchable, not a permanent gate._
- [ ] GUI for the bot (session/turn/dice/sheets)
- [ ] LLM finetuning (LoRA on session logs)
- [ ] Streaming TTS (latency)
- [ ] Wake word / push-to-talk
- [ ] Per-NPC voices
- [ ] Automatic character progression
- [ ] Long-term vector memory

---

## Open questions / to clarify

**From the Phase-7 playtests (2026-06-06) — carry into Phase 8 / quality work:**
- **(gemma3) Persona drift is model-limited.** nemo still mis-attributes who did what, dodges
  provocative in-fiction input, and occasionally slips POV — despite a sharpened persona. **Try
  `gemma3:12b`** (taste test, see Next step) before assuming the prompt is at fault.
- **(F) Player → character name mapping.** The LLM confuses the Discord name ("SezBoss69") with the
  character ("Seskin") and muddles who acted. Belongs to character registration (D13/ADR 003,
  Phase 8); a light alias map (display-name → character) injected into the prompt could help sooner.
- **(K) Dice/skill-check design (Phase 8).** Players want the GM to roll **for** them and the
  **difficulty to come from the system profile/rulebook**, not be improvised by the LLM — exactly
  "dice = code". Fold into ADR 005 / `rules/engine.py` when building Phase 8.
- **Latency grows with context** as history accumulates; the 20-turn cap helps but recaps (Phase 9)
  are the real fix. Watch; don't act yet.

**Only empirical, to decide in Phase 0 (try it, not design):**
- ✅ **Model:** decided — **mistral-nemo** as primary (taste test 2026-06-04 vs gemma3:12b /
  qwen3.5:9b / glm-4.7-flash: best idiomatic German + NSC dialogue; glm too big for 12 GB).
  `gemma3:12b` is the atmospheric runner-up — worth re-checking against nemo in Phase 5 with the
  real persona prompt if the tone needs more richness.
- **TTS voice:** `de_DE-thorsten-medium` vs. `thorsten_emotional` — listen. _(Phase 6.)_

**Loose ends / housekeeping (from the Phase 3 session):**
- **Intermittent voice-connect `TimeoutError` on `!join`** (seen once, ~18:45): the discord.py
  voice handshake occasionally times out; the command errored but a retry joined fine. Benign
  so far — watch it; if it recurs, look at the connect timeout / a clean error message in
  `voice/commands.py` rather than the raw traceback.
- Logging now also writes `logs/dmbot.log` (UTF-8, gitignored) — handy for inspecting a run
  after the window closes.
- Continuous silence injection runs silero on every silent user ~50×/s (cheap, ~1–2 %/core
  each); fine for a small table, revisit only if many idle users ever cost CPU.

**Loose ends / housekeeping (from the Phase 2 session):**
- ✅ `docs/pipeline-diagram.*` removed (Tobi, 2026-06-05) — no longer a loose end.
- ✅ **Voice stack now safeguarded against silent breakage (2026-06-05).** The version
  sensitivity (DAVE decrypt into `_connection.dave_session`; voice-recv alpha) is now caught,
  not just documented: the three voice dists are pinned `==` in `pyproject.toml`;
  `voice/preflight.py` checks versions + attribute paths at boot and the live `dave_session`
  at join (loud warnings on drift); `recv.py` warns+skips a DAVE frame (magic `0xFAFA`) when no
  session is reachable instead of decoding garbage; `tests/test_voice_stack.py` is the offline
  canary (5/5 green). Verified-stack table added to ADR 006. **Still required on any upgrade:**
  run the smoke test + a live re-verify, then bump `KNOWN_GOOD` + the pins + the ADR table.
- DAVE decrypt skips frames received before the MLS group is `ready` (brief startup gap), and
  single-packet RTP jitter ("lost being flushed", sender voice-activation) is benign for STT.

**Resolved design questions (now in the decision log / ADRs):**
- ✅ Ollama host → D6 / ADR 002
- ✅ Conversational control (when the DM speaks) → D10 / ADR 003
- ✅ VAD vs. push-to-talk → resolved: VAD segments, button triggers the DM turn (D10)
- ✅ Dice test trigger → D11 / ADR 004
- ✅ Character stats in the JSON state → D12 / ADR 004
- ✅ Character registration → D13 / ADR 003
- ✅ Recap trigger → D14
- ✅ Bot A status signal → D15

---

## Notes
- Order deliberately risk-minimal: bridge first (curl-testable, no risk to the music bot),
  then DMbot layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
