# Cogitator — a local, voice-only AI Game Master

**DMbot** is a self-hosted AI game master for tabletop RPGs that plays **by voice over
Discord**, in **German**. You talk; it listens, thinks, and answers aloud in character. It is
**system-agnostic** — load a ruleset/adventure as PDFs and it learns the setting (RAG) and the
mechanics (a per-system profile). Everything runs **locally** — no cloud, no API costs.

First campaign: **Warhammer 40,000 / Imperium Maledictum** in Dan Abnett's *Eisenhorn*
grimdark tone — but that's just the first profile + tone overlay, not baked into the DM.

> **Status:** the core voice loop is **playable** (Phases 0–6 done). You can speak and the DM
> answers aloud. Dice engine, persistent memory and RAG are the next phases. See
> [`progress.md`](progress.md) for the live status and [`roadmap.md`](roadmap.md) for the plan.

## How it works

Two Discord bots share one voice channel:

- **Bot A** — the existing music bot (a **separate repo**), used only as the *mouth*: a tiny
  `/speak` HTTP bridge that plays a WAV and blocks until done.
- **DMbot** — this repo, the *brain*: voice receive → VAD → STT → LLM → TTS → bridge.

```
You speak ─► DMbot receives per-user audio (discord-ext-voice-recv, DAVE/E2EE decrypt)
            │   (Bot A's voice is filtered out — no self-hearing)
            ▼
        resample 48k stereo → 16k mono (soxr)
            ▼
        silero-vad cuts utterances ──► faster-whisper → German transcript (buffered)
            ▼
        you trigger a DM turn:  !dm
            ▼
        Ollama (mistral-nemo) + layered German persona (GM core + Eisenhorn tone) → answer
            ▼
        TTS (Coqui XTTS v2 default, Piper fallback) → WAV  ──► POST /speak to Bot A ──► spoken aloud
```

**Signature principle:** *dice = code, narration = LLM.* Dice rolls and their resolution are
computed by a deterministic engine from the active system profile — never the language model
(coming in Phase 8).

## Quick start

```bash
uv sync                       # install deps (Python 3.12, managed by uv)
cp .env.example .env          # then fill in DISCORD_TOKEN_DMBOT (never commit .env)
uv run python -m dmbot        # or double-click start_dmbot.bat (Windows)
```

You also need, running alongside: **Ollama** (`mistral-nemo` pulled) and **Bot A** (the music
bot on its `dungeon_master` branch, in the same voice channel). Full step-by-step in
**[`SETUP.md`](SETUP.md)**; the external prerequisites the bot can't install itself are in
[`docs/SETUP.md`](docs/SETUP.md).

## Running on another machine (e.g. a second GPU box)

The project is two processes plus Ollama, all local. To bring it up on a fresh Windows + NVIDIA
machine:

1. **Clone both repos.** This one (DMbot) and the music bot, `Pr0degie/musicbot` on branch
   `dungeon_master` (Bot A — the `/speak` mouth). DMbot can't speak without Bot A running.
2. **Install per repo:** `uv sync` in each. DMbot pulls a **CUDA torch** build from the cu130
   index automatically (CUDA 13.0 — covers Ada *and* Blackwell, e.g. RTX 40xx/50xx; needs an
   NVIDIA GPU + recent driver; a box without a usable GPU degrades XTTS to CPU). Lock is Windows-only.
3. **Two Discord bot tokens.** A bot token allows only one live connection, so either (a) reuse
   the existing two tokens *while the other machine's instances are off*, or (b) create two new
   Discord bot applications (DMbot + Bot A) with voice intents and invite both to the server.
   DMbot's token → `DISCORD_TOKEN_DMBOT` in this repo's `.env`; Bot A's token → the music bot's
   own `.env`. Set `BOT_A_USER_ID` to Bot A's user-ID (feedback protection).
4. **Ollama:** install, then `ollama pull mistral-nemo` and `ollama pull nomic-embed-text`.
   Or point `OLLAMA_HOST` at a machine that already has them.
5. **Pick the GPU profile** in `.env` (see [`.env.example`](.env.example)):
   - **16 GB+ (e.g. RTX 5080) — everything on GPU:** `WHISPER_DEVICE=cuda` `WHISPER_COMPUTE=float16` `TTS_DEVICE=cuda`
   - **12 GB (e.g. RTX 4070):** `WHISPER_DEVICE=cpu` `WHISPER_COMPUTE=int8` `TTS_DEVICE=cuda` (whisper on CPU frees VRAM for XTTS)
6. **Start order:** Ollama (service) → Bot A (music bot) → DMbot (`uv run python -m dmbot` or
   `start_dmbot.bat`). Both bots `!join` the same voice channel, then `!dm` runs a turn.

XTTS downloads its model on first run; the Piper voice is optional (only if `TTS_ENGINE=piper`).

## Split hosting: the two bots on two machines (over Tailscale)

By default both bots run on one machine (path bridge over the shared disk). They can also be
**split across two machines** — e.g. **Bot A (the music bot) on machine A, DMbot on machine B** —
so the heavy AI (XTTS + Whisper) runs on the box with the better GPU while the other just plays
audio. DMbot then sends the WAV **bytes** to Bot A over the network instead of a file path
(hybrid bridge, ADR 010). Concrete example used here: **Bot A on the 4070 box, DMbot on the 5080
box.**

**Prerequisites**
- Pull both repos on their machines (DMbot `main`, music bot `dungeon_master`) and `uv sync` each.
- Each bot runs as a **single instance** of its own Discord app: machine A runs **only** Bot A,
  machine B runs **only** DMbot (one live connection per token — don't run a second copy of either).
- Both bots invited to the **same server**; both join the **same voice channel** (each from its
  own machine — Discord is in the cloud).

**1. Network — Tailscale (or LAN)**
- *Same home network?* Skip Tailscale: use the host's LAN IP (`ipconfig` → `192.168.x.x`).
- *Different networks?* Install **Tailscale** (https://tailscale.com/download/windows, free
  Personal plan) on **both** machines and **sign both into the same tailnet**. Get the host's IP
  with `tailscale ip -4` (a `100.x.y.z`); verify with `tailscale ping <ip>` from the other machine.

**2. `.env` on the Bot A machine** (the music bot repo) — bind off-localhost + set a secret:
```
DM_BRIDGE_HOST=0.0.0.0          # listen on the Tailscale/LAN interface, not just localhost
DM_BRIDGE_PORT=8765
DM_BRIDGE_SECRET=<choose-a-token>
```
Restart Bot A; its log must show `[DMBridge] HTTP-Server läuft auf 0.0.0.0:8765`. Allow `python`
through the Windows firewall (private network) if prompted.

**3. `.env` on the DMbot machine** (this repo) — point at Bot A + the same secret:
```
DM_BRIDGE_HOST=<Bot A machine's Tailscale/LAN IP>
DM_BRIDGE_PORT=8765
DM_BRIDGE_SECRET=<same-token-as-above>
```
Plus the GPU profile for that box (see above) and `BOT_A_USER_ID` = Bot A's user-ID.

**4. Verify** from the DMbot machine:
```
curl http://<Bot A IP>:8765/health     # → {"status":"ok","bot":"..."}
```
Then both bots join the voice channel and `!dm` / `!say <text>` should speak. Failure hints in
DMbot's log: `401` = secret mismatch · `unreachable` = Bot A not bound off-localhost or
Tailscale/firewall blocking · `409` = Bot A not in the voice channel.

> Localhost is unchanged: leave `DM_BRIDGE_HOST=127.0.0.1` and `DM_BRIDGE_SECRET=` empty to run
> both bots on one machine (path mode, no secret).

## Discord commands

Prefix is `!`. Type them in any text channel the bot can read.

| Command | Does |
|---|---|
| `!join` / `!j` | DMbot joins your voice channel and starts listening (the whole table is transcribed to the log) |
| `!leave` | leave the voice channel and end the session (clears its buffer + history) |
| `!dm [text]` | run a DM turn — answers the speech routed to the DM (or the given `text`) — and speaks it aloud |
| `!redo` / `!r` | re-run the **last** DM turn with the same input — for when the DM misunderstood |
| `!mic` | re-post the push-to-talk button at the bottom of the chat (if it scrolled away) |
| `!roll <dice>` | roll raw dice through the engine (`!roll 1d100`, `!roll 2d10+3`) — a smoke test |
| `!test <skill> [difficulty] [für name]` | request a test → posts a 🎲 button; the engine rolls + resolves it (`!test Wahrnehmung Schwer für Tobi`) |
| `!turn` / `!order` | show / rotate the turn order ("whose turn"), seeded from the voice channel |
| `!say <text>` | speak arbitrary text aloud — a TTS + bridge smoke test |
| `!voice [name]` | switch the XTTS speaker (no name → show current); only with `TTS_ENGINE=xtts` |
| `!voices` | list the XTTS built-in speakers; only with `TTS_ENGINE=xtts` |
| `!vstatus` | show connection / listening / Opus state |

> **Push-to-talk** (default `DM_PUSH_TO_TALK=1`): tap the **🎙 button** posted on `!join` *before*
> you speak to the DM and again when you're done — only that speech reaches the DM, while the whole
> table is still transcribed to `logs/transcript.log`. One tap counts for everyone. Releasing the
> button **auto-runs the DM turn** (no `!dm` needed; `DM_BUTTON_AUTOSEND=0` to disable) — it waits
> for the just-said speech to transcribe first. `!mic` brings the button back if it scrolled away.

> **Dice (Phase 8):** when a roll is due, the DM writes a marker `<<TEST <skill> <difficulty> für
> <name>>>` and DMbot posts a 🎲 button. Clicking it rolls **in code** (never the LLM): the target is
> the character's skill value (from `data/sessions/<channel>/characters.json`) plus the difficulty
> modifier from the active system profile (`data/systems/<DM_SYSTEM>.json`, default
> `imperium_maledictum`), and the result feeds back so the DM narrates the consequence. You can also
> trigger one by hand with `!test`. Put your party's stats + a display-name→character alias map in the
> characters JSON (an example ships under `data/sessions/_example/`).

## Configuration (`.env`)

Everything is env-driven (never hardcoded). Highlights — see [`.env.example`](.env.example):

- `OLLAMA_HOST` / `OLLAMA_MODEL` — LLM host + model (default local `mistral-nemo`)
- `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE` — STT (default `medium` / `cuda` / `float16`)
- `TTS_ENGINE` — `xtts` (Coqui XTTS v2, 58 voices + cloning — **default**) or `piper` (fast, lean fallback voice)
- `TTS_SPEAKER` / `TTS_DEVICE` — XTTS speaker (default *Dionisio Schuyler*) and device
- `BOT_A_USER_ID` — Bot A's user-ID, filtered from voice (feedback protection layer 1)

## Documentation

| File | What |
|---|---|
| [`architecture.md`](architecture.md) | full design — pipeline, components, memory, RAG, rules engine |
| [`roadmap.md`](roadmap.md) | phased plan + model/effort recommendations |
| [`progress.md`](progress.md) | live status, decision log, what's next |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records (ADRs) |
| [`SETUP.md`](SETUP.md) · [`docs/SETUP.md`](docs/SETUP.md) | install & run · external prerequisites |

> Convention: code and docs are **English**; game content (the GM persona, tone overlays, and
> anything the DM says) is **German**.
