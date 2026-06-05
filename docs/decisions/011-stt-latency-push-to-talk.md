# ADR 011 — STT latency: GPU whisper + push-to-talk listen gate

- **Status:** Accepted
- **Date:** 2026-06-05
- **Refs:** decision log D24 in `progress.md`; ADR 003 (conversational control); ADR 002/009 (GPU/VRAM); supersedes the "whisper on CPU" choice of the 4070 dev profile

## Context

First real multi-player session (4 speakers, ~15 min) exposed the dominant playability bug: the
DM reacted to player input **~1.5 minutes late**. Two causes, both confirmed in the log + code:

1. **CPU whisper can't keep up.** `medium`/int8 on CPU takes 4–7 s per clip (one 1.7 s clip took
   22.7 s). The 4070 dev profile put whisper on CPU on purpose, to free VRAM so XTTS fits next to
   nemo (ADR 009).
2. **Continuous transcription of everything.** Per ADR 003 the bot transcribes the whole table
   continuously and buffers; with 3–4 people talking nonstop, the **unbounded** STT queue
   (`transcriber.py`, single worker) grows without bound → minutes of lag, and the narrative goes
   incoherent ("where were we? suddenly there was a rover"). The players themselves asked for a
   start/stop button so only DM-directed speech is transcribed.

## Decision

Cut STT latency two ways: **(a) move whisper back to the GPU** (`WHISPER_DEVICE=cuda`/float16), and
**(b) add a push-to-talk listen gate** — a single shared Discord button (`discord_ui/mic.py`) that,
when disengaged, makes `VadSink` drop all audio so nothing is transcribed until the table taps it
on; tap again to stop (one tap for everyone). On by default (`DM_PUSH_TO_TALK=1`).

## Alternatives

- **Bound/drop the STT backlog + greedy decode** (beam_size=1): cheap relief, keeps the DM current,
  but still transcribes (and discards) table talk and loses utterances — treats the symptom.
- **Smaller whisper model** (small/base): 2–4× faster on CPU but less accurate; small mis-heard the
  quiet speaker in the Phase-4 gate.
- **Wake word** ("Magos, …"): the natural long-term UX (ADR 003, Part 2), but an extra unreliable
  building block (false triggers, German recognition) — the button is the robust path there.
- Keep continuous transcription, just faster hardware: doesn't fix the table-talk noise or the
  coherence problem, and GPU whisper alone is VRAM-tight on the 4070 if it runs constantly.

## Consequences

- **Positive:** push-to-talk eliminates the backlog *at the source* — whisper rarely runs, so GPU
  whisper fits even the 4070 next to nemo+XTTS, and the buffer only holds DM-directed speech (less
  noise → more coherent, more responsive turns). The gate reuses the layer-2 drop path in `_on_pcm`
  (`_muted or not _listening`); layer-2 mute still wins while Bot A speaks.
- **Negative / binding:** play is now button-paced — forget to tap and the bot hears nothing
  (the join message + `!mic` re-post mitigate). GPU whisper can OOM the 4070 if it does run under
  full VRAM; the transcriber falls back to CPU int8, and `DM_PUSH_TO_TALK=0` restores the legacy
  always-on mode. This is the first `discord_ui/` View — the pattern (a View calling back into the
  cog) is the template for the Phase-8 dice/turn buttons.
- **Later:** a wake word can replace the button without touching the gate (it just flips
  `set_listening`); stopping the gate could optionally auto-trigger the `!dm` turn.
