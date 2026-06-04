# progress.md — AI Dungeon Master (Cogitator), system-agnostic

Living status document. A phase counts as done only when its **verification gate** is
met and the proof is recorded here.

## Current focus
Phase 2 — Bot B scaffold: voice receive. **Phase 0 is complete** (gate met, primary model
chosen — see below). Phase 1's Bot A bridge is done; its formal gate tick (`curl /speak` →
audible) is a formality pending both bots in one voice channel.

## Last session
Set up the **Bot B repo**: project skeleton (`architecture.md` §12) — `bot_b/` subpackages
(incl. the **generic** `rules/`), the `data/` tree (systems/pdfs/sessions/vectordb, `.gitkeep`
markers, content gitignored), German prompt placeholders; `uv`/Python-3.12 `pyproject.toml`,
`.gitignore`, `.env.example` (Bot B token, `OLLAMA_HOST`, `DM_BRIDGE_*`). No `bot_a_bridge/`
(two-bot isolation). Verified tooling and ran the **Phase 0 gate** (curl → grimdark German).
Did a **model taste test** (scene + NSC dialogue) across mistral-nemo / gemma3:12b / qwen3.5:9b /
glm-4.7-flash → chose **mistral-nemo** as primary (best idiomatic German + dialogue; glm 19 GB
doesn't fit the 4070's 12 GB). Committed and pushed the whole Phase 0 scaffold + docs to
`origin/main` (`f17f134`); hardened `.gitignore` (voices/, tool caches, IDE/OS cruft, `.env.*`);
`uv.lock` tracked. _Earlier:_ reframed to a system-agnostic DM (D1/D7/D12/D18, ADR 005);
built/reviewed the Bot A bridge (musicbot `dungeon_master`, commit `249cc38`).

## Next concrete step
Begin **Phase 2 — Bot B voice receive**: join a voice channel, wire a `discord-ext-voice-recv`
sink, log per-user PCM, and filter Bot A's user-ID (feedback protection **layer 1**). Check the
sink callback signature against the *installed* voice-recv version; ensure the Opus DLL loads on
Windows (B6). Recommended level (`roadmap.md`): **Opus 4.8 / xhigh** — this is the research part.
Open prerequisites for the gate: both bots in the same voice channel, a working mic (B6).

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

### Phase → ADR map (read these when you enter the phase)

| Phase | ADRs to read first |
|---|---|
| 0 — Foundation & setup | ADR 002 (topology, `OLLAMA_HOST`, localhost bridge) |
| 1 — Bridge (done) | ADR 002 + `architecture.md` §3 (bridge contract) |
| 2–4 — Voice / VAD / STT | _no ADR_ — see `architecture.md` §4–§5 (incl. feedback protection) |
| 5 — LLM wiring + persona | ADR 002 + ADR 005 (persona = generic core + campaign overlay) |
| 6–7 — Full loop, turn-taking, registration | ADR 003 (conversational control, registration, turn-taking) |
| 8 — Dice engine, IM profile, marker flow | ADR 005 (engine + profile) + ADR 004 (test marker, character data) + ADR 001 (IM specifics) |
| 9 — Memory (JSON + recaps) | ADR 004 (character/state JSON) |
| 10 — RAG + profile bootstrap | ADR 005 (profile bootstrap) |

---

## Phase status (Part 1 — MVP)

Legend: ⬜ open · 🔄 in progress · ✅ done (with proof)

### ✅ Phase 0 — Foundation & setup
- [x] Repo + project structure (skeleton per `architecture.md` §12; uv/Python-3.12, `.gitignore`, `.env.example`)
- [x] Discord Bot B app + token (in `.env`). _(Bot A token already exists in the music bot repo.)_
- [x] Ollama installed locally on the 4070 + models pulled (`mistral-nemo`, `nomic-embed-text`) + reachable
- [x] Model taste test → primary model chosen: **mistral-nemo**
- **Manual setup (outside the agent): see `docs/SETUP.md`.**
- **Gate:** `curl` to Ollama from Tobi's machine → German answer.
- **VERIFY EVIDENCE:** Gate met 2026-06-04 — `curl http://localhost:11434/api/generate` with
  `mistral-nemo` returned a plausible grimdark German answer ("Die Finsternis hat sich über die
  Welt gelegt wie ein Grabtuch aus Eisen…"). Tooling: git 2.42, Python 3.12.10, uv 0.11.19,
  Ollama 0.30.4 on `:11434`, models `mistral-nemo` + `nomic-embed-text` pulled, NVIDIA 596.49
  (RTX 4070). Discord Bot B created, token in `.env`. **Primary model: `mistral-nemo`**, chosen
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
  _(Run the `curl /speak` → audible check once both bots share a voice channel to formally tick the gate.)_

### ⬜ Phase 2 — Bot B scaffold: voice receive
- [ ] Voice join + `discord-ext-voice-recv` sink
- [ ] per-user PCM log
- [ ] Bot A's user-ID filtered (protection layer 1)
- [ ] Windows: Opus DLL for voice available
- **Gate:** PCM frames in the log; Bot A's own voice absent.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 3 — VAD segmentation
- [ ] Resample 48k/stereo → 16k/mono
- [ ] silero-vad → cut utterances
- **Gate:** one sentence = one utterance, start/end correct.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 4 — STT (faster-whisper)
- [ ] faster-whisper wrapper, transcript log
- [ ] Windows: cuDNN/cuBLAS DLLs on the `PATH`
- **Gate:** German sentence transcribed correctly.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 5 — LLM wiring + DM persona
- [ ] Ollama client (httpx)
- [ ] `prompts/dm_core_de.md` (generic GM persona, German) + first campaign tone overlay (Eisenhorn)
- [ ] History per channel (in-memory)
- **Gate:** text prompt → German DM answer in the campaign's tone.
- **VERIFY EVIDENCE:** _(empty)_

### ⬜ Phase 6 — TTS + first full loop ⭐
- [ ] Piper (`de_DE-thorsten`) → WAV (OS temp dir)
- [ ] httpx `POST` to `/speak`
- **Gate:** speak → DM answers audibly; latency measured; no self-hearing.
- **VERIFY EVIDENCE:** _(empty)_

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
  then Bot B layer by layer.
- **Principle:** dice/success = code, narration = LLM. Do not mix.
- Verify each phase in isolation before the next begins.
