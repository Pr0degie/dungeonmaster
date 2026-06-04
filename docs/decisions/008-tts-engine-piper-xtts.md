# ADR 008 — TTS engine: Piper default + XTTS v2 optional

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** decision log D21 in `progress.md`; `architecture.md` §3 (TTS row), §4; ADR 002
  (local-only topology, VRAM); Phase 6 in `roadmap.md`/`progress.md`

## Context

Phase 6 shipped TTS with **Piper** (`de_DE-thorsten-medium`): fast (~130 ms/sentence), light,
fixed voice. Once the full loop was audible, the voice itself was the problem — Tobi found
*all* of Piper's German voices unsatisfying (Thorsten included), and Piper's German catalogue
has nothing better. He wanted a richer voice and ideally a **specific cloned voice** (e.g. a
Drachenlord-like timbre). The project is **local-only, no cloud / no API cost** (ADR 002), so
ElevenLabs and other hosted TTS are out.

## Decision

Keep **Piper as the default** TTS (fast, lean, reliable fallback) and add **Coqui XTTS v2**
(`coqui-tts`) as a **selectable** backend via `TTS_ENGINE` (`piper` | `xtts`). XTTS brings ~58
built-in speaker timbres that all speak German, plus zero-shot **voice cloning** from a short
reference clip. After auditioning all 58 built-ins (pitch-ranked samples in `voices/samples/`),
Tobi chose **Dionisio Schuyler** (deep male, ~99 Hz) as the default XTTS speaker. XTTS is wired
**in-process** for now and defaults to **CPU**; the heavy `TTS.api` import is lazy so Piper
users don't pull torch.

## Alternatives

- **Piper only:** simplest/leanest, but the voices were rejected — the whole reason for this ADR.
- **Replace Piper with XTTS:** XTTS is heavy and slow on CPU; Piper stays as the fast, dependency-
  light default and a fallback if the torch stack ever breaks. Rejected dropping it.
- **Cloud TTS (ElevenLabs, etc.):** best quality/expressiveness, but violates the local-only,
  no-cost principle (ADR 002). Rejected.
- **F5-TTS / StyleTTS 2:** strong cloning alternatives. XTTS chosen for maturity, easy German +
  built-in speakers (audition without a clip), and straightforward cloning. F5 stays a fallback
  if XTTS quality disappoints.
- **XTTS as a separate process/service now:** the clean end-state (isolates the torch stack,
  enables GPU), but more work — deferred to the backlog; in-process unblocked auditioning today.

## Consequences

- **Positive:** 58 selectable voices + cloning, switchable live (`!voice` / `!voices`); Piper
  untouched as the default; engine chosen by one env var.
- **Heavy deps (golden rule #9):** pulls **torch + torchaudio + torchcodec + coqui-tts**;
  `transformers` pinned **<5** (XTTS imports `isin_mps_friendly`, removed in 5.x) and `tokenizers`
  got pulled back 0.23→0.22 — **verified faster-whisper still transcribes** after the changes.
  torchcodec is required for torch≥2.9 audio IO and needs ffmpeg libs (present via Bot A).
- **Latency / VRAM:** XTTS on **CPU is ~1.5× realtime** (slow for long answers, on top of the
  LLM); on **GPU it is near-realtime**, but the 12 GB 4070 has no spare VRAM next to nemo
  (~9.5 GB) + whisper (~2.5 GB). Going fast means freeing VRAM — whisper→CPU and/or the LLM onto
  the 5080 via Tailscale (ADR 002).
- **Binding / follow-up:** keep the XTTS import lazy; **move XTTS to its own local service**
  (own venv, GPU) to keep the bot venv lean and get realtime synthesis (backlog).
