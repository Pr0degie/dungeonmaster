# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
**Phases 0–6 complete — the loop is PLAYABLE** ⭐ (speak → German DM answer in **Dionisio's**
voice, heard aloud). **XTTS now runs on the GPU** (2026-06-05, ADR 009): CUDA torch installed,
verified live RTF **0.34** (≈3× realtime, vs ~1.9 on CPU). The remaining latency lever is no
longer TTS but the **LLM answer length** (a 24 s synth was a ~70 s monologue) + the ~8 s LLM turn.
Next: (a) trim DM answer length / persona meta-preamble; (b) **Phase 7** — feedback layer 2
(pause VAD while Bot A speaks). The fragile voice-receive stack stays hardened (ADR 006).

## Last session
**GPU XTTS via CUDA torch + portable per-machine GPU profiles (non-Phase work, ADR 009).** The
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
  Added it as a win32 dep + registered its bin dir in `transcriber.py`; **verified a real
  faster-whisper cuda transcription on the 4070**. Lesson: ctranslate2's CUDA-12 trio
  (cublas + cudnn + **cudart**) must be self-complete, independent of torch's CUDA version.
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

_(Prior session — voice-stack hardening, ADR 006 — and Phases 3–6 (the playable loop) are captured
in ADR 006 and each phase's VERIFY EVIDENCE below.)_

## Next concrete step
**Trim the DM answer length — the latency is now in the LLM, not TTS.** With XTTS on the GPU
(RTF 0.34, ADR 009) a long synth means a long *answer*: a 24 s synth was a ~70 s monologue.
Cap the DM turn (e.g. `num_predict` / prompt nudge for shorter turns) and trim nemo's meta-preamble
("Ich beschreibe…") + occasional role-inversion ("Was siehst du?"). The ~8 s LLM turn is the other
half — consider offloading Ollama to the 5080 via Tailscale (ADR 002). **Then Phase 7** — feedback
layer 2 (pause VAD while Bot A speaks; read ADR 003). Level: **opusplan / high**.

_5080 onboarding:_ the project is now portable — `uv sync` pulls CUDA torch (cu130), the 5080
runs the all-GPU `.env` profile (whisper `cuda`/`float16` + XTTS `cuda`). README "Running on
another machine" has the full flow; the only manual bits are the two Discord tokens + Ollama pull.

_Also open (not blocking):_ DM model/persona tuning (nemo vs `gemma3:12b`; trim the occasional
"Was siehst du?" role-inversion + meta-preamble); STT confidence-filter live check; the
requested toggleable edit/review-window (Part 2 backlog).

_Carry-overs:_ (1) **STT confidence filter** is live but only tested on clean speech — watch a
live run for whether the "Vielen Dank…" phantoms are gone and nothing real is dropped (tune
`_NO_SPEECH_MAX`/`_LOGPROB_MIN`). (2) **DM model/persona tuning** — try `gemma3:12b` vs
`mistral-nemo` with the real persona; trim nemo's occasional meta-preamble. (3) The **ms latency
display** + green console need a restart to show. (4) Live-test `!dm` (Tobi hasn't run it yet).

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
| D16 | Runtime environment | **Windows** (both bots + pipeline) | No `/tmp` (OS temp dir); Opus DLL for voice; cuDNN/cuBLAS DLLs on `PATH` for faster-whisper. _WSL considered but rejected — keeps both bots co-located so the file-path bridge works without path translation._ |
| D17 | Doc language | **Dev docs in English** (game content stays German) | Token efficiency on docs read every session; matches the schema precedent |
| D18 | System-agnostic engine | **Generic dice/resolution engine + per-system profile**; DM **proposes the profile from the PDF**, user confirms (MVP). Persona = generic GM + per-campaign tone overlay | Reusable across rulesets; "paste PDFs → DM knows what's played"; dice still code → ADR 005 |
| D19 | DAVE/E2EE on voice receive | **Decrypt the DAVE layer via discord.py's `dave_session`** (keep E2EE; sink takes `wants_opus=True`, decrypts each frame before Opus-decode) | Discord calls are end-to-end encrypted; voice-recv only undoes transport → garbage. Declining DAVE is rejected (voice close 4017) → ADR 006 |
| D20 | VAD segmentation stack | **silero-vad via `onnxruntime`** (no torch) + **`soxr`** streaming resampler; model vendored in-repo | Robust neural VAD without torch's ~GB weight; webrtcvad too noise-prone; soxr is the smallest correct resampler → ADR 007 |
| D21 | TTS engine | **XTTS v2 (`coqui-tts`) default + Piper fallback**, selectable via `TTS_ENGINE`; XTTS speaker **Dionisio Schuyler**. _(Default flipped Piper→XTTS 2026-06-05 once XTTS ran on GPU.)_ | Piper's German voices were rejected; XTTS gives 58 voices + cloning (local, no cloud); torch is a hard dep regardless + XTTS degrades to CPU, so it's a safe default → ADR 008 + 009 |
| D22 | GPU XTTS / portability | **CUDA torch from the `cu130` index** (`+cu130` builds; CUDA 13.0 covers Ada **and** Blackwell), device env-driven (`TTS_DEVICE`/`WHISPER_DEVICE`); same Windows-only lock for both boxes, XTTS auto-degrades to CPU | CPU-only torch made GPU XTTS impossible; cu130 gives the GPU build (RTF 0.34 verified) for both 4070 (sm_89) + 5080 (sm_120); win32-only lock dodges the cudnn pin clash; one repo runs 4070 dev + 5080 full-GPU → ADR 009 |

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | **ADR 006** (DAVE/E2EE decrypt on receive) + **ADR 007** (VAD stack, Phase 3) + `architecture.md` §4–§5 (feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) |
| 6 — TTS + full loop | **ADR 008** (TTS engine: Piper + XTTS) + ADR 002 (bridge, VRAM) + `architecture.md` §3 (bridge contract) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) |
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
  _Open tuning (noted, not blocking):_ nemo occasionally adds a meta-preamble ("Ich beschreibe…")
  and lets the setting drift with sparse context → re-run the Phase-0 **nemo vs gemma3:12b** taste
  test with this persona; consider it in Phase 6 once TTS gives a feel for tone aloud.

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

### ⬜ Phase 7 — Turn-taking & feedback protection layer 2
- [ ] VAD pauses while Bot A speaks
- [ ] Session state per channel
- **Gate:** two people speak → orderly reaction, no feedback loop.
- **VERIFY EVIDENCE:** _(empty)_

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
