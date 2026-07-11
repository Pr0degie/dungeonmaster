# roadmap.md — AI Dungeon Master (Cogitator), system-agnostic

Goal of this roadmap: **the smallest version that is already fun**, in clearly testable
phases — followed by a few big rocks for the future.

**"Fun version" =** you sit in the voice channel, you speak, the DM narrates back in the
campaign's tone, you roll tests via button, and the DM remembers the session and knows the
rules — from a per-system profile it proposed from your PDFs. The **first campaign** is
WH40K / Imperium Maledictum in the Eisenhorn grimdark tone, but the DM is not tied to it.

Every phase has a **verification gate**: only when the proof is delivered does it
continue. (Order follows the "bridge first, then DMbot layer by layer" principle —
lowest risk first.)

---

## Claude effort (for Claude Code)

Effort-first (Fable 5): effort is the primary dial, set via `/effort` (persists across
sessions). The old per-phase model table is retired — the project is past those phases.

- Default **high**.
- **xhigh** for unknowns, integration debugging, subtle async/state bugs, and persona prose.
- **medium** for clearly specified deterministic modules and doc sweeps.
- Step down only after seeing quality hold.

---

## Part 1 — MVP: the smallest fun version

### Phase 0 — Foundation & setup
**Goal:** tools in place, model speaks German.
- Create repo + project structure (see `architecture.md` §12).
- Two Discord applications + tokens (Bot A exists, DMbot is new).
- Install Ollama locally on the 4070, pull models (`mistral-nemo`, `nomic-embed-text`).
- Model taste test: Mistral Nemo 12B vs. alternatives with the same German Eisenhorn
  prompt; compare tone & speed → pick the primary model.
- **Manual setup outside the agent:** see `SETUP.md`.
- **Verification:** `curl http://localhost:11434/api/generate …` returns a plausible
  German answer.

### Phase 1 — Bridge: Bot A `/speak`
**Goal:** Bot A plays a WAV on request. Zero risk to the music bot.
- Add `POST /speak` (aiohttp) to the music bot: takes a WAV path, plays in the voice channel.
- **`/speak` blocks until playback ends** — the return is the resume signal (no separate status).
- **Verification:** `curl -X POST localhost:<PORT>/speak` with a test WAV → audible in the channel.
  *(Proves Part 1 completely without DMbot.)*

### Phase 2 — DMbot scaffold: voice receive
**Goal:** raw audio arrives, Bot A's voice is filtered.
- DMbot joins voice, `discord-ext-voice-recv` sink, log per-user PCM.
- **Hard-filter Bot A's user-ID** (feedback protection layer 1).
- **Windows:** provide the Opus DLL for voice / `discord.opus.load_opus(...)` if needed.
- **Verification:** PCM frames appear in the log when speaking; Bot A's own audio output
  does **not** appear.

### Phase 3 — VAD segmentation
**Goal:** the audio stream becomes clean utterances.
- Resample 48k/stereo → 16k/mono; `silero-vad` accumulates until silence → one utterance.
- **Verification:** a spoken sentence is recognized as **one** utterance, start/end correct.

### Phase 4 — STT (faster-whisper)
**Goal:** utterance → text.
- Wire in faster-whisper (small/medium), log the transcript.
- **Windows:** put cuDNN/cuBLAS DLLs on the `PATH`, otherwise GPU inference won't start.
- **Verification:** a spoken German sentence appears correctly as text in the log.

### Phase 5 — LLM wiring + DM persona
**Goal:** text in, in-tone answer out.
- Ollama client (`httpx`); generic GM core prompt `prompts/dm_core_de.md` (German) +
  the first campaign's tone overlay (Eisenhorn grimdark, Inquisition) layered on top.
- History per channel (in-memory for now).
- **Verification:** a text prompt to Ollama → an atmospheric German DM answer in the campaign's tone.

### Phase 6 — TTS + first full loop  ⭐ HEART
**Goal:** **speak → the DM answers audibly.** From here it is playable.
- Piper (`de_DE-thorsten`) → WAV into the OS temp dir (`tempfile.gettempdir()`, **not** `/tmp`).
- httpx `POST` to Bot A `/speak`.
- **Verification:** both bots in a test channel, someone speaks → the DM answers audibly.
  Measure latency. Check the feedback loop (the DM must **not** hear itself).

### Phase 7 — Turn-taking & feedback protection layer 2
**Goal:** clean coexistence with several people.
- While Bot A speaks: pause VAD / accept no new utterance.
- Keep session state per channel clean.
- **Verification:** two people speak → the DM reacts in order and does not talk into its own audio.

### Phase 8 — Dice engine, system profile & turn-order buttons   ✅ DONE (2026-06-08, live-validated)
**Goal:** system-agnostic mechanics at the press of a button — IM as the first profile.
- `rules/engine.py`: **generic** dice + resolution engine driven by a system profile
  (roll-under/over/pool, target source, degrees, damage). **With unit tests.**
- First profile `data/systems/imperium_maledictum.json` — **hand-written for now**
  (1d100, roll-under, SL = tens-difference, d10/d5 damage); engine tested against it.
  (Auto-proposing a profile from a PDF comes with RAG in Phase 10.)
- Text-channel `View` with buttons: roll, declare action, end turn; display "whose turn it is".
- A test is detected by the **roll-detection router** (a separate classifier after narration, ADR 014;
  default on) — or, as a fallback, the LLM's inline `<<TEST>>` marker; the engine rolls per the active
  profile and feeds the result back. _(The inline-only marker proved unreliable live → ADR 014.)_
- **Verification:** a button roll shows the correct result + degrees for the active profile; turn order rotates; unit tests green.

### Phase 9 — Memory (JSON + recaps)
**Goal:** the DM remembers.
- JSON world state (characters, HP, inventory, NPCs, quests, flags); code advances it deterministically.
- Session recap generation (LLM summarizes) + re-injection next time.
- **Verification:** an HP change survives a restart; the next session begins with a correct "story so far".

### Phase 10 — RAG over PDFs + system-profile bootstrap
**Goal:** the DM knows setting & rules from your PDFs — and can learn a new system from them.
- Ingestion (PDF → chunks → `nomic-embed-text` → vector store) for rulebook/lore/adventure.
- Retrieval into the prompt; answer rule questions from rulebook chunks.
- **Profile bootstrap:** the DM reads the core-mechanics passages and **proposes a draft
  system profile**; the user confirms/edits it; it's saved to `data/systems/`. This realizes
  "paste the PDFs and the DM knows what's played" for the mechanics.
- **Verification:** a concrete rule question answered correctly from the PDF; and a fresh
  ruleset's PDF yields a confirmed, working profile the engine can roll against.

> ✅ **End of Part 1 = complete fun version.** A playable voice session with dice
> buttons, memory and rule knowledge.

---

## Part 2 — Beyond the MVP (big rocks)

Roughly prioritized, deliberately not fully planned yet:

- **GUI for the bot.** A dedicated interface for session control, turn order, dice and
  character-sheet management — could replace the text-button layer. (Fits your
  Flutter/web stack.)
- **Finetuning the LLM.** LoRA on collected session logs for a more consistent Eisenhorn
  style and IM rule knowledge in German. Requires enough play material.
- **Latency optimization.** Sentence-by-sentence streaming TTS so the DM starts speaking
  before the whole answer is finished.
- **Wake word / push-to-talk.** If VAD is too noisy with the full group.
- **Per-NPC voices.** Multiple Piper voices or voice cloning for character flavor.
- **Automatic character progression.** XP, advances, injury tables from the JSON state.
- **Long-term vector memory.** Semantically searchable across many sessions.
- **System/campaign library.** Multiple saved system profiles + campaigns (tone overlay +
  PDFs + characters) to switch between — the pay-off of the system-agnostic design.

---

## Cross-cutting: conventions
- German as the play language; code/logs in English.
- **Dice = code, narration = LLM.** Rolling + resolution run through the generic engine
  applying the active system profile; never invented by the LLM.
- **System-agnostic:** mechanics live in per-system profiles (`data/systems/`), tone in
  per-campaign overlays. IM/Eisenhorn is the first of each, not baked in.
- A phase is only "done" once its verification gate is met (status & evidence in `progress.md`).
