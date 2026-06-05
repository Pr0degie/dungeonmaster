# architecture.md — AI Dungeon Master (system-agnostic)

> Working name: **Cogitator** (just a codename — the DM is not tied to any one setting).

A local, **system-agnostic** AI game master for tabletop RPGs over Discord: voice-only
interaction, dice and turn mechanics as text buttons, German play language. You load a
ruleset/adventure as PDFs; the DM learns the setting (RAG) and the mechanics (a per-system
**profile** it proposes from the rulebook) and runs the game. Everything runs locally —
no cloud, no API costs.

**The first campaign** is Warhammer 40,000 with **Imperium Maledictum**, in the grimdark
tone of Dan Abnett's *Eisenhorn* — but that is just the first loaded system + tone layer,
not baked into the DM.

> Note: the docs and code are English for token efficiency. The *game content* (the DM
> persona prompt, tone overlays, anything the DM says) stays German — that is a separate path.

---

## 1. Overview & design principles

- **Two bots, clean separation.** The existing music bot stays untouched and only
  gains a thin output channel (`/speak`). All the "uncharted territory" (voice
  receive) lives isolated in the new bot — if it breaks, the music bot keeps running.
- **Every layer testable on its own.** Bridge, STT, LLM, TTS, RAG, memory can each
  be checked independently via CLI/curl before the full loop exists.
- **Separate determinism from the LLM.** Dice, success levels and turn order are
  computed by *code*, not the language model. The LLM narrates, the code rolls.
- **Latency is acceptable, not irrelevant.** A "thinking" DM may take a few seconds;
  the chain is still kept lean (LAN instead of cloud, streaming TTS later).

---

## 2. Hardware topology

**Important up front:** both bots talk to Discord's servers, not to each other or to
the players' home networks. Voice audio flows player → Discord → DMbot and
Bot A → Discord → player. **Where the bots run is irrelevant to Discord** — Tobi and
his colleague do *not* need to be on the same network. The only internal links are
DMbot → Ollama and DMbot → Bot A (the bridge).

**Bot A and DMbot run on the same machine by default** (the bridge passes a *file path* to the
WAV — a shared filesystem). They can also be **split across machines over Tailscale**: when
`DM_BRIDGE_HOST` is remote, DMbot sends the WAV *bytes* instead of a path and Bot A plays its own
copy (hybrid transport, ADR 010 — relaxes this co-location for the bridge). Ollama splits off the
same way (JSON over HTTP, no path).

### Development (MVP) — everything on one machine

| Machine | GPU | Tasks |
|---|---|---|
| **Tobi's PC** | RTX 4070 (12 GB) | **everything**: Bot A, DMbot, VAD, STT, TTS, RAG, **and Ollama locally** |

Mistral Nemo 12B (Q4, ~8 GB) fits alongside Whisper-small and Piper in 12 GB. No
internal network, no Tailscale setup — and the separate networks are a non-issue for
the whole MVP. Tobi develops and debugs locally (you do not want to debug real-time
audio on someone else's hardware).

> **Runtime environment: Windows.** Both bots and the whole pipeline run on Windows.
> A few consequences must be respected in code (see §11): no `/tmp` (use the OS temp
> dir via `tempfile.gettempdir()`), the Opus DLL for discord.py voice, and
> cuDNN/cuBLAS DLLs on the `PATH` for faster-whisper on the GPU. uv, Ollama, Piper and
> faster-whisper all run natively on Windows.

### Later upgrade — LLM onto the stronger card

| Machine | GPU | Tasks |
|---|---|---|
| **Tobi's PC** | RTX 4070 (12 GB) | Bot A, DMbot, VAD, STT, TTS, RAG |
| **Colleague** | RTX 5080 (16 GB) | Ollama only (+ embeddings) — bigger model possible |

If Nemo 12B feels too weak, **only the LLM** moves to the 5080. Switching = one line of
`OLLAMA_HOST` (the host is deliberately not hardcoded). Reachable via
**Tailscale/WireGuard** (free Personal plan, P2P latency negligible against token
generation). Then the LLM has the 16 GB card to itself; STT/TTS stay on the 4070.

---

## 3. Components

### Bot A — Output / DMBridge (existing music bot)
- **Stack:** discord.py
- **Status: IMPLEMENTED.** Lives in a **separate repo** (`Pr0degie/musicbot`, branch
  `dungeon_master`, as of commit `249cc38`) as the cog `cogs/dm_bridge.py` (DMBridge).
  Music/queue/autoplay/radio logic is untouched (two-bot isolation).
- **Why reuse the music bot?** It is already in the voice channel and can play audio —
  the playback logic already exists.

#### Bridge contract (what DMbot builds against)
An `aiohttp` server on `DM_BRIDGE_HOST`:`DM_BRIDGE_PORT` (defaults `127.0.0.1:8765`, via the music
bot's `config.py` / `.env`). Localhost by default; bind a Tailscale/LAN IP for the split topology.

- `GET /health` → `{"status":"ok","bot":"<name>"}` — liveness check.
- `POST /speak` — **two transports** (ADR 010), both blocking until playback finishes:
  - **path mode** (loopback): JSON `{"path": "<abs WAV path>", "guild_id": <optional int>}`
    → plays from the shared disk, responds `{"status":"played","path":...}`.
  - **bytes mode** (remote): raw body, `Content-Type: audio/wav`, headers `X-DM-Guild-Id` +
    `X-DM-Secret` → Bot A writes the bytes to its own temp dir, plays, deletes; responds
    `{"status":"played"}`.
  Errors: `400` invalid/empty/unsupported, `401` secret mismatch (off-loopback), `404` file not
  found (path mode), `409` not connected to voice, `413` too large, `500` write/playback failed.
  Calls are serialized by a lock; any running music is stopped first. Playback uses
  `discord.FFmpegOpusAudio` (ffmpeg already a music-bot dependency).
- `!dm` — Discord command, shows bridge status (server, voice connection).

**Signalling:** the blocking return is the *only* "done" signal — no callback, no shared
state (matches D15; an earlier Bot-A→DMbot callback was removed as redundant).

**DMbot's side of the contract:** write the TTS WAV to a real file (OS temp dir, Windows), then
`POST` to `http://DM_BRIDGE_HOST:DM_BRIDGE_PORT/speak` — its *path* when the host is loopback
(shared disk), or its *bytes* when the host is remote (ADR 010). DMbot deletes its WAV after the
call returns. DMbot pauses its own VAD before the
`await` and resumes after the response returns (it owns the loop, so it needs no push
from Bot A; layer-1 user-ID filtering protects regardless).

### DMbot — Receiver / DM brain (new)
- **Stack:** discord.py + `discord-ext-voice-recv` (the only real research part)
- **Responsibility:** voice receive, VAD, STT, orchestration (LLM + RAG + memory),
  TTS, bridge call, text-channel mechanics (buttons). Pure *outbound* HTTP client toward
  the bridge — needs no inbound HTTP server of its own.

### Inference & pipeline building blocks

| Step | Component | Note |
|---|---|---|
| Receive voice | `discord-ext-voice-recv` (+ `davey`) | real-time streaming sinks, per-user audio (48 kHz stereo). `davey` decrypts Discord's **DAVE/E2EE** layer on receive — calls are end-to-end encrypted (ADR 006) |
| Resampling | `soxr` (streaming) | 48 kHz stereo → 16 kHz mono for VAD/STT, one `ResampleStream` per user (ADR 007) |
| VAD/segmentation | `silero-vad` via `onnxruntime` | neural VAD run through onnxruntime (no torch), model vendored in-repo; cuts utterances on silence (ADR 007) |
| STT | `faster-whisper` (CTranslate2) | small/medium on the 4070 (GPU float16, CPU int8 fallback). cuDNN/cuBLAS via the `nvidia-*-cu12` wheels; DLLs registered in-code (`stt/transcriber.py`), no manual `PATH`. Runs on a worker thread off the audio path |
| LLM | **Ollama** (local/5080) + `httpx` | DM system prompt + history + RAG context + JSON state |
| Embeddings | `nomic-embed-text` via Ollama | for RAG (tiny, runs anywhere) |
| RAG store | SQLite + vector (e.g. `sqlite-vec`) or ChromaDB | searchable PDF chunks |
| TTS | `coqui-tts` (XTTS v2) **default**, `piper-tts` fallback | XTTS (default): ~58 built-in speakers + voice cloning, rich but heavy (**pulls torch/torchaudio/torchcodec — from the CUDA `cu130` index** (covers Ada + Blackwell) so it runs on the GPU, not the CPU-only build; transformers pinned <5); device per `TTS_DEVICE` (cuda/cpu), auto-degrades to CPU if CUDA is absent or OOMs. Piper: fast, lean, fixed German voice (`de_DE-thorsten`) → WAV — the fallback when XTTS won't load. Selectable per `TTS_ENGINE` (golden rule #9: the CUDA torch stack is the cost of GPU XTTS → ADR 009) |
| Bridge client | `httpx`/`aiohttp` | `POST` to Bot A `/speak` |

---

## 4. Data flow (per utterance)

```
Player speaks (freely, among themselves)
   │
   ▼
[DMbot] sink yields per-user PCM ──► resample 48k/stereo → 16k/mono
   │                                 (Bot A's user-ID is filtered out!)
   ▼
silero-vad cuts utterances ──► faster-whisper ──► transcript
   │
   ▼
transcripts are BUFFERED per player (DM does NOT answer yet)
   │
   ▼
Button "End turn" / "DM, respond"  ◄── triggers the DM turn
   │
   ▼
Orchestrator builds the prompt:
   GM core persona + campaign tone overlay (e.g. Eisenhorn)
   + active system profile (dice/resolution rules)
   + session recap (memory narrative)
   + JSON world state (characters, HP, inventory, NPCs, flags)
   + RAG hits (relevant rulebook/lore chunks)
   + buffered player utterances since the last DM turn
   │
   ▼
Ollama ──► answer text, possibly with a test marker  <<TEST Perception +10>>
   │            │
   │            └─► orchestrator detects the marker ──► shows a dice button to the
   │                right player ──► rules/ rolls d100 + SL ──► result feeds back
   │                into the next prompt
   ▼
piper-tts ──► <TEMP>/dm_<id>.wav   (OS temp dir, NOT /tmp — Windows!)
   │
   ▼
httpx POST {wav_path} to Bot A /speak   (DMbot pauses VAD)
   │
   ▼
[Bot A] plays the WAV ── and only responds when finished (blocking)
   │
   ▼
[DMbot] return = "done" ──► VAD active again, buffer cleared, next turn
```

---

## 5. Feedback-loop protection (mandatory)

DMbot also hears Bot A in the same channel — without protection it transcribes its own
DM voice. Two layers:

1. **The sink filters out Bot A's user-ID entirely** (cleanest solution, primary).
2. **DMbot pauses the VAD during the `/speak` call** — and because `/speak` blocks
   until playback is finished, DMbot knows exactly when it may listen again
   (belt and braces).

---

## 6. Conversational control, registration & turn-taking

### When does the DM speak?
Core problem: with 2–5 people in voice, the bot does not know whether it is being
addressed or whether you are just talking among yourselves. Solution in the MVP: DMbot
**transcribes continuously** (with the user-ID filter) and **buffers** utterances per
player, but **only answers on a button press** ("End turn" / "DM, respond"). That way
the DM never talks over anyone, table talk stays out of the game, and it is naturally
semi-turn-based. **VAD only segments clean utterances — the button triggers the DM
turn, not the VAD.**

> **Later goal:** a wake word ("Magos, …") that triggers the DM turn instead of the
> button. The button is the robust path to get there (see ADR 003 / Part 2 of the roadmap).

### Character registration (session start)
DMbot gets the Discord user-ID via `voice-recv`, but it must know who plays which
character — otherwise it cannot address anyone and cannot know whose stats a roll uses.
Flow: **guided and sequential.** The bot walks through the loaded characters ("Who
plays **Brother Castor**? Press the button.") — the first click maps that user-ID to
the character, then the next, until everyone is mapped. The user-ID → character mapping
goes into the session JSON.

### Turn-taking
- **Session scope:** one history **per voice channel**; the orchestrator keeps state per channel.
- **MVP:** a lightweight turn indicator in the text channel ("whose turn it is"),
  advanced manually via "End turn". Buttons (`View`/`Button`) for: roll, declare action,
  end turn.
- **Real combat initiative** (rolled order, rounds, per-character declarations) is a
  separate mode and comes **later** (late Phase 8 / Part 2) — otherwise you build combat
  rules before a free scene even runs.

---

## 7. Memory (two-part)

The LLM has a finite context window — a whole campaign does not fit. Hence two separate
stores:

**a) Structured world state (JSON / SQLite) — the "hard facts"**
```jsonc
{
  "session_id": "...",
  "system": "imperium_maledictum",   // which system profile is active (see §9)
  "characters": [
    // stat/skill fields follow the ACTIVE system profile's character schema,
    // not a fixed set. IM example shown:
    { "name": "...", "wounds": 8, "max_wounds": 12,
      "characteristics": {...}, "skills": {...}, "inventory": ["..."], "conditions": ["..."] }
  ],
  "npcs":   [ { "name": "...", "attitude": "hostile", "known_since": "..." } ],
  "quests": [ { "title": "...", "status": "open", "flags": {...} } ],
  "location": "...",
  "time_ingame": "..."
}
```
Advanced deterministically by code (e.g. HP after damage). Goes into the prompt as
structured data.

> **Character sheets are the source of this JSON, not RAG.** You transfer each sheet
> **once** into the `characters` block. The *shape* of a character (which characteristics,
> skills, resource tracks exist) is dictated by the active **system profile** (§9) — so it
> differs between D&D, IM, etc. That lets the engine roll stat-aware and track the right
> resource (HP/wounds/stress/…). Only the *rulebook/lore/adventure* lives in RAG.

**b) Session recaps (free text) — the "narrative thread"**
On session end (the `wrap up` command) — or on context overflow — the LLM produces a
"story so far" summary. These recaps are stored and placed at the front of the prompt
next time as narrative memory. The story stays coherent without dragging the whole raw
history along. (A rolling mid-session summary is a later refinement; with Nemo's 128k
context there is plenty of headroom.)

> Interplay: JSON = state (what *is*), recap = story (what *was*).

---

## 8. RAG over PDFs

- **Ingestion:** **rulebook, setting/lore and adventure PDFs** are read in
  (PDF → text → chunks), embedded (`nomic-embed-text`) and placed in the vector store.
  **Character sheets do NOT go into RAG** — they become structured JSON (§7).
- **Two jobs:** (1) per request, retrieve the most relevant chunks into the prompt (a rule
  passage, a lore detail, an adventure beat); (2) **bootstrap the system profile** — on
  first load of a new ruleset, the DM reads the core-mechanics passages and proposes the
  profile (§9).
- **Source discipline:** rule questions are answered from the rulebook chunk, not from the
  model's gut — reduces hallucination. This matters more now: the DM learns *unfamiliar*
  systems from the PDF, so it must lean on retrieval rather than half-remembered rules.

---

## 9. Dice & resolution: generic engine + system profiles (code, not LLM)

The DM is system-agnostic, so dice logic is **not** hardcoded for one game. It is split in
two: a generic engine (code) and a per-system **profile** (data).

### System profile (data, per ruleset)
A small declarative file (`data/systems/<system>.json`) describing the core mechanic:
```jsonc
{
  "name": "imperium_maledictum",
  "dice": "1d100",
  "resolution": "roll_under",        // roll_under | roll_over | pool | sum_vs_target | ...
  "target_source": "skill_value",    // where the target number comes from
  "degrees": "tens_difference",      // how degrees/levels of success are computed
  "advantage": "flip_d100",          // optional, system-specific
  "damage": "d10/d5 + modifiers",    // free-text or structured, optional
  "character_schema": {              // which stat/skill/resource fields a character has
    "characteristics": ["WS","BS","Str","Tgh","Ag","Int","Per","Wil","Fel"],
    "resource": "wounds",
    "skills": "list"
  }
}
```
Other systems are just other profiles (d20 roll-over vs DC; 2d6+mod PbtA; d6 success pool; …).

### Generic engine (`dmbot/rules/engine.py`)
Pure Python, fully decoupled from the LLM. Rolls dice (RNG **is always code**) and applies
the active profile to produce success/degrees. Unit-tested against each profile (IM first).
**Golden rule generalized:** dice *and* their resolution are code-driven via engine +
profile — never invented by the LLM.

### Profile bootstrap (MVP — proposed from the PDF, confirmed by the user)
On first load of a new ruleset, the DM reads the core-mechanics passages (RAG) and
**proposes a draft profile**; the user reviews/confirms/edits it once in the text channel;
the confirmed profile is saved to `data/systems/`. This is what realizes "paste the PDFs
and the DM knows what's played" for the *mechanics*. IM is simply the first profile
produced (or seeded) this way.

### How a test is requested
The LLM emits a machine-readable **marker**, e.g. `<<TEST Perception +10>>`. The
orchestrator detects it, shows a dice button to the right player, the engine rolls per the
active profile and computes the result, which feeds back into the next prompt (the DM
narrates the consequence). A bracketed marker is more reliable for a 12B model than strict
JSON. **Fallback:** if parsing fails, the DM states the test in plain text and you roll
manually via button — no break in flow. See ADR 004 + ADR 005.

---

## 10. Model choice (German, fits in 12 GB)

Starting recommendation (runs on the 4070, later also on the 5080):

- **Primary: Mistral Nemo 12B (instruct).** Strong German, 128k context (good for long
  sessions + RAG), ~7–9 GB at Q4 — lots of headroom, runs on the 4070 too.
- **More quality: Mistral Small 24B (Q4 ~14 GB)** or **Qwen2.5 14B** — stronger, but tighter.
- **Embeddings:** `nomic-embed-text` (tiny).
- **TTS voice:** `de_DE-thorsten-medium` as a start; test `thorsten_emotional` for more
  expression.

Final choice via taste test (Phase 0): the same German Eisenhorn prompt to several
models, compare tone & speed.

---

## 11. Risks & sticking points (honest)

- **Latency chain:** hear → VAD → STT → LLM → TTS → bridge → playback adds up.
  Mitigation: LAN/Tailscale instead of cloud, smaller Whisper model, later
  sentence-by-sentence streaming TTS.
- **Feedback loop:** without the user-ID filter, DMbot transcribes its own DM voice →
  mandatory mitigation.
- **`discord-ext-voice-recv`:** less well-trodden than plain discord.py — the only real
  research part, but isolated in DMbot.
- **Two tokens/processes:** two bot applications, both must join the channel.
- **VAD false triggers with 2–5 people:** push-to-talk as an emergency exit if needed.
- **Remote Ollama reachability:** the colleague must be online & reachable; Tailscale
  recommended.
- **Rule hallucination:** contained by RAG + code-side dice/success logic.
- **Windows specifics:** (a) **no `/tmp`** — build WAV paths via `tempfile.gettempdir()`,
  never hardcoded. (b) **Opus DLL** — discord.py voice (send *and* receive) needs libopus;
  on Windows you may have to ship the DLL and call `discord.opus.load_opus(...)`
  explicitly. (c) **faster-whisper on GPU** — cuDNN/cuBLAS DLLs must be on the `PATH`
  (or next to the .exe / in the working dir), otherwise CTranslate2 will not start;
  classic Windows stumbling block.

---

## 12. Project structure (proposal)

This is the **DMbot repo**. Bot A is **not** part of it — it lives in the separate music
bot repo (`Pr0degie/musicbot`, branch `dungeon_master`); DMbot talks to it over HTTP per
the contract in §3. Do not create a `bot_a_bridge/` folder here.

```
cogitator/                 # = the DMbot repo
├── dmbot/                 # the DM bot
│   ├── voice/             # recv, resample, VAD
│   ├── stt/               # faster-whisper wrapper
│   ├── tts/               # piper wrapper
│   ├── llm/               # Ollama client, prompt building
│   ├── rag/               # ingestion + retrieval + profile bootstrap
│   ├── memory/            # JSON state + recaps
│   ├── rules/             # engine.py (generic) + profile loader (+ tests)  ← deterministic core
│   ├── discord_ui/        # buttons, turn-order view
│   └── orchestrator.py    # wires everything together
├── data/
│   ├── systems/           # system profiles, e.g. imperium_maledictum.json (§9)
│   ├── pdfs/              # loaded rulebook/lore/adventure PDFs (for RAG)
│   ├── sessions/          # JSON world state + recaps (per voice channel)
│   └── vectordb/          # vector store
├── prompts/
│   ├── dm_core_de.md      # generic GM persona (GERMAN — game content)
│   └── campaign_tone_de.md # current campaign's tone/setting overlay (GERMAN)
├── docs/
│   ├── SETUP.md
│   └── decisions/         # ADRs
├── CLAUDE.md
├── roadmap.md
├── progress.md
└── architecture.md
```

> Bot A (the music bot) is a separate repo: the `cogs/dm_bridge.py` cog providing
> `GET /health` + blocking `POST /speak` (see §3).
>
> **Persona is layered:** `prompts/dm_core_de.md` is the generic, system- and
> setting-agnostic GM core. The *tone/setting* (e.g. Eisenhorn grimdark) is the campaign
> overlay `prompts/campaign_tone_de.md`, combined with the active system profile (§9) at
> runtime. Swapping campaign = swap overlay + profile, same DM.
>
> **MVP = one campaign**, so the layout above is flat. Multiple saved campaigns (a
> `data/campaigns/<name>/` library bundling its own pdfs/sessions/tone) is a Part-2 item.
