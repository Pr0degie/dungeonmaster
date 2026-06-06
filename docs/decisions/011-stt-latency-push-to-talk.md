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

Cut STT latency two ways: **(a) move whisper back to the GPU** (`WHISPER_DEVICE=cuda`/float16, ~5–8×
faster per clip), and **(b) add a push-to-talk gate** — a single shared Discord button
(`discord_ui/mic.py`). **The whole table is always transcribed and logged** (Tobi wanted the full
conversation record — useful for recaps/memory, Phase 9); the button gates only **what reaches the
DM**: utterances captured while it is engaged are buffered for `!dm`, the rest are log-only. Tap
before talking to the DM, tap to stop (one tap for everyone). On by default (`DM_PUSH_TO_TALK=1`;
`0` routes everything to the DM).

The gate lives in the cog (`commands._on_transcript` buffers only `for_dm` lines), not in `VadSink`.
Each utterance is tagged `for_dm` **when it is cut** (carried through the STT worker), and the button
flushes the open utterance before flipping, so the routing reflects the gate state *while the words
were spoken*, not whenever the async transcript returns.

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

- **Positive:** the full table transcript is preserved in the log (recaps/memory groundwork), while
  the DM buffer only holds button-routed speech — less table-talk noise → more coherent, responsive
  turns. The `→DM` marker on `📝` lines shows which were routed. GPU whisper is what makes
  always-on transcription viable again (CPU was the bottleneck). Layer-2 mute still wins (Bot A's own
  voice is never transcribed).
- **Negative / binding:** because transcription is continuous again, the STT-backlog risk returns if
  GPU whisper can't keep up with a busy table — GPU is 5–8× faster so it should, and **dropping a
  stale backlog is the next lever** if it doesn't. GPU whisper can OOM the 4070 under full VRAM (nemo
  + XTTS); the transcriber falls back to CPU int8. Play is button-paced for the DM — forget to tap
  and nothing reaches the DM (the join message + `→DM` marker + `!mic` re-post mitigate);
  `DM_PUSH_TO_TALK=0` routes everything. First `discord_ui/` View — the View→cog callback pattern is
  the template for the Phase-8 dice/turn buttons.
- **Later / done:** pressing the gate off auto-triggers the DM turn — **now implemented**
  (`DM_BUTTON_AUTOSEND=1`, waits on `Transcriber.wait_idle` so the last utterance is included). A wake
  word can still replace the button later (it just flips `self._dm_listening`); a stale-backlog drop
  covers the busy-table case if continuous transcription ever falls behind.
