"""Resample decoded voice PCM to the rate the VAD/STT need (Phase 3).

``discord-ext-voice-recv`` hands us per-user PCM at 48 kHz **stereo** s16le (20 ms = 960
frames per channel). silero-vad and faster-whisper both want 16 kHz **mono** float32.
Getting this wrong is *silent*: a wrong sample rate is not an error, it just yields garbage
downstream (CLAUDE.md — "wrong sample rate = garbage transcript, not an error").

One :class:`StereoResampler` per user (the sink owns them). soxr's *streaming* resampler
keeps filter state across chunks, so 20 ms frames fed back-to-back don't pick up the boundary
artefacts a per-chunk one-shot resample would introduce. The HQ filter has a small constant
startup delay (the very first chunk may yield 0 output samples); that only shifts the timeline
by a fixed offset, which is irrelevant for utterance segmentation.
"""

from __future__ import annotations

import numpy as np
import soxr

_IN_RATE = 48_000
_OUT_RATE = 16_000
_I16_FULL_SCALE = 32768.0  # |min int16|; maps s16le → [-1, 1)


class StereoResampler:
    """Per-user 48 kHz stereo s16le → 16 kHz mono float32 streaming resampler."""

    def __init__(self) -> None:
        # num_channels=1: we downmix to mono *before* resampling (cheaper, and the VAD/STT
        # only want mono anyway).
        self._stream = soxr.ResampleStream(
            _IN_RATE, _OUT_RATE, 1, dtype="float32", quality="HQ"
        )

    def feed(self, pcm_stereo_48k: bytes) -> np.ndarray:
        """Downmix one stereo frame to mono and resample it to 16 kHz.

        Returns float32 mono samples in [-1, 1) at 16 kHz. May be empty for the first frame
        while the filter primes, or whenever soxr buffers across the chunk boundary.
        """
        # s16le interleaved L,R,L,R… → (n, 2) int16 → averaged mono float32 in [-1, 1).
        stereo = np.frombuffer(pcm_stereo_48k, dtype=np.int16).reshape(-1, 2)
        mono = stereo.astype(np.float32).mean(axis=1) / _I16_FULL_SCALE
        return self._stream.resample_chunk(mono)
