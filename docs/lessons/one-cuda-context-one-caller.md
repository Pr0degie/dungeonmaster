# One CUDA model, one caller at a time — and a CUDA fault kills the whole process

**XTTS and faster-whisper share one CUDA context in DMbot. Running the same XTTS model from two
threads at once ends in a sticky `device-side assert`, and after that every CUDA call in the
process fails — Whisper included. Serialise every GPU model behind a lock, and make the first
CUDA fault loud at the table, because nothing recovers short of a restart.**

## What happened

- 2026-06-13: a device-side assert from VRAM coexistence on the 4070 poisoned the process and
  killed STT live (the reason `TTS_DEVICE=cpu` was the default for a long time).
- 2026-10-25 (fourth Opus run): one psi action was rolled twice, each result started its own
  streamed narration, and two XTTS syntheses ran concurrently. `CUDA error: device-side assert
  triggered` in `layer_norm`; from then on every transcription failed (80+ tracebacks) and the
  table only noticed that the bot had gone deaf.

## What to do

- Any model that runs on the GPU gets one lock around inference (`XttsTTS._lock`). Overlapping
  callers are normal here — two dice results, a `!lore` read, a seamless pre-buffer.
- Worker threads report failures through `dmbot.gpu_health` (`log_failure`): the first CUDA
  fault logs a critical line and posts one channel notice ("Bot neu starten"); later ones are a
  short line, not another traceback.
- When a device-side assert shows up, look for concurrency first, VRAM second.
