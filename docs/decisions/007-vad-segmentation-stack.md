# ADR 007 — VAD segmentation stack: silero-vad via onnxruntime + soxr

- **Status:** Accepted
- **Date:** 2026-06-04
- **Refs:** Phase 3 in `roadmap.md`/`progress.md`; `architecture.md` §4 (data flow);
  golden rule #9 (no heavy deps without a note); follows ADR 006 (the PCM this consumes)

## Context

Phase 3 turns the continuous per-user PCM the sink decodes (48 kHz **stereo** s16le, after
DAVE-decrypt + Opus-decode — ADR 006) into discrete **utterances** ("one sentence = one
utterance") for STT in Phase 4. Two pieces are needed and both were left open at phase start
(`progress.md`): a **resampler** (48 kHz stereo → 16 kHz mono, what VAD and faster-whisper
both want) and a **voice-activity detector** to segment the stream on silence.

Wrong sample rate is *silent garbage*, not an error (CLAUDE.md), so the resampler must be
correct and continuous across 20 ms chunk boundaries. The VAD must be reliable in a real,
possibly noisy Discord channel with several speakers — a false split mid-sentence or a missed
onset directly corrupts the transcript downstream.

## Decision

**VAD: silero-vad, run via `onnxruntime` (CPU), model vendored in-repo.**
silero is a tiny (~2 MB) neural VAD and the de-facto standard — markedly more robust to noise
than the older GMM-based webrtcvad. We run the v5 ONNX model through `onnxruntime` rather than
the official `silero-vad` pip package, which would pull **torch** (~GB) just for VAD. The
model file (`dmbot/voice/models/silero_vad.onnx`, from the upstream repo) is committed so the
bot needs no runtime download. A small streaming segmenter (`voice/vad.py`,
`UtteranceSegmenter`) feeds the model fixed 512-sample/32 ms windows, tracks speech with
hysteresis, and emits an utterance after trailing silence — its pure state machine is
deterministically tested with a scripted fake model (the real model on real speech is the
manual live gate).

**Resample: `python-soxr` (streaming).**
High quality, small, purpose-built for rate conversion. One `soxr.ResampleStream` per user
(`voice/resample.py`) keeps filter state across the 20 ms frames so there are no per-chunk
boundary artefacts; we downmix stereo→mono first, then resample mono (cheaper).

Both sit behind the existing sink via a new `_on_pcm` seam; `VadSink` subclasses `PcmLogSink`
so the **layer-1 Bot A filter, DAVE-decrypt and Opus-decode are inherited unchanged** (golden
rule #4 — the filter is never re-implemented or bypassed).

## Alternatives

- **silero-vad official pip package (torch backend):** fastest to wire (ready-made
  `VADIterator`), identical model quality — but drags in torch/torchaudio (~GB) solely for
  VAD. faster-whisper (Phase 4) uses CTranslate2, **not** torch, so torch would be net-new
  weight for one tiny model. Rejected on golden rule #9; the onnxruntime path gives the same
  accuracy and real-time speed without it (and onnxruntime is reusable later).
- **webrtcvad:** the lightest runtime (pure-C, no model), naturally streaming. But it is
  GMM-based and crude — many false positives on noise/music/overlapping speech, needing
  aggressive tuning, and still less reliable than silero. The efficiency win is imperceptible
  for this tiny audio load, so it is a bad trade against reliability. Rejected.
- **torchaudio / scipy / ffmpeg for resampling:** torchaudio implies torch (see above);
  scipy/av are heavier than the one job needs. soxr is the smallest correct fit.
- **One-shot `soxr.resample` per 20 ms chunk:** simpler, but discards filter state between
  chunks → boundary artefacts on a continuous stream. The streaming resampler avoids this.

## Consequences

- **Positive:** robust neural segmentation with a light footprint — no torch; new deps are
  `onnxruntime`, `soxr`, `numpy` (CPU-only). onnxruntime is reusable in later phases.
  Segmentation logic is unit-verified (state machine) and isolated from the foreign voice-recv
  code in `voice/`.
- **Heavy-dep note (golden rule #9):** `onnxruntime` (~12 MB wheel) + `numpy` are the only
  non-trivial additions; this ADR is their justification. They are far lighter than the torch
  path they replace. The silero `.onnx` is a committed ~2 MB binary asset (provenance: silero
  upstream) — re-verify the 512-sample/32 ms window + `[2,1,128]` state contract if the model
  is ever updated (the v4 ONNX had a different state layout).
- **Tuning is empirical:** `_MIN_SILENCE_MS` (600), `_MIN_SPEECH_MS` (250), `_SPEECH_PAD_MS`
  (200) and the 0.5/0.35 thresholds are starting points; the live gate (a real spoken sentence
  → exactly one utterance, correct start/end) may move them. They live as constants in
  `voice/vad.py`.
- **Per-user, single-threaded:** segmentation runs on the voice-recv reader thread, one
  resampler + segmenter per user, all sharing one loaded model. The HQ resampler's constant
  startup delay (first chunk may yield 0 samples) only shifts the timeline by a fixed offset —
  irrelevant for segmentation.
- **Voice activation → silence must be injected (learned live).** Discord clients send *no*
  RTP at all while a user is silent, so the segmenter never receives the trailing-silence
  frames it needs to close an utterance — it hangs open until the next speech, merging
  sentences. Fix: wrap `VadSink` in voice-recv's `SilenceGeneratorSink`, which fills
  transmission gaps with synthetic silence frames (decoded PCM, no opus/DAVE); `write()`
  routes those straight to the segmenter, bypassing decrypt/decode. Chosen over a self-managed
  wall-clock close-timer because the library already solves it. The wrapper drives `write()`
  from its own thread, so the sink is lock-guarded.
