"""Streaming voice-activity segmentation with silero-vad (Phase 3).

Turns a continuous 16 kHz mono stream into discrete **utterances** — the project's
"one sentence = one utterance". silero-vad is a tiny (~2 MB) neural VAD, far more robust to
noise than the older GMM-based webrtcvad; we run it through **onnxruntime** so it needs no
torch (ADR 007). The model is vendored at ``models/silero_vad.onnx``.

The v5 ONNX model advances in fixed **512-sample hops** at 16 kHz (32 ms); each hop is fed to
the model together with a 64-sample **context** from the previous hop (576 samples total — the
v5 contract; see ``_CONTEXT``) plus a recurrent state, and it emits a speech probability per
hop. :class:`UtteranceSegmenter` accumulates
windows while speech is active and, after enough trailing silence, emits the buffered audio
as one utterance — with a little pre/post padding so word onsets and tails aren't clipped.

Threading: one :class:`UtteranceSegmenter` per user (its own state + buffers), all sharing a
single :class:`SileroVad` (the loaded session is stateless across calls — the recurrent state
lives in the segmenter). ``feed`` runs on the voice-recv reader thread, so it stays
allocation-light and never raises out of itself; the on-utterance callback runs there too.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "models" / "silero_vad.onnx"

_SR = 16_000
_WINDOW = 512  # new samples per inference at 16 kHz (one 32 ms hop)
_WINDOW_MS = 1000.0 * _WINDOW / _SR  # 32 ms
# silero v5 prepends a context of the previous chunk's last samples to each window, so the
# tensor it actually consumes is _CONTEXT + _WINDOW = 576 samples. Feeding a bare 512 silently
# returns ~0 probability (the ONNX input shape is dynamic, so it doesn't error) — the lesson
# from CLAUDE.md's "check the foreign lib's real contract".
_CONTEXT = 64  # 64 for 16 kHz (would be 32 for 8 kHz)

# Segmentation tuning. The thresholds mirror silero's own VADIterator defaults; the silence
# window is widened a touch so a natural mid-sentence pause doesn't split one utterance.
_SPEECH_THRESHOLD = 0.5   # prob >= → speech
_SILENCE_THRESHOLD = 0.35  # prob <  → silence (the gap to _SPEECH_THRESHOLD is hysteresis)
_MIN_SILENCE_MS = 600.0   # trailing silence that closes an utterance
_MIN_SPEECH_MS = 250.0    # discard utterances with less actual speech than this (blips)
_SPEECH_PAD_MS = 200.0    # audio kept before the first / after the last speech window

_I16_PEAK = 32767.0


class SileroVad:
    """The loaded silero-vad onnx session. One instance is shared across all users."""

    def __init__(self, model_path: Path = _MODEL_PATH) -> None:
        if not model_path.exists():
            raise FileNotFoundError(
                f"silero-vad model not found at {model_path}. It is vendored in the repo; "
                "see SETUP.md if it is missing."
            )
        opts = ort.SessionOptions()
        # The model is tiny and runs per 32 ms window on the reader thread — single-threaded
        # keeps it predictable and avoids spawning a pool per session.
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._sr = np.array(_SR, dtype=np.int64)
        log.info("silero-vad loaded (onnxruntime, CPU) from %s", model_path.name)

    @staticmethod
    def new_state() -> np.ndarray:
        """Fresh zero recurrent state ([2, 1, 128], the v5 layout)."""
        return np.zeros((2, 1, 128), dtype=np.float32)

    @staticmethod
    def new_context() -> np.ndarray:
        """Fresh zero context ([_CONTEXT] samples) prepended to the first window."""
        return np.zeros(_CONTEXT, dtype=np.float32)

    def __call__(
        self, window: np.ndarray, state: np.ndarray, context: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray]:
        """Run one 512-sample window with its 64-sample context.

        Returns (speech_prob, new_state, new_context). The new context is the last
        ``_CONTEXT`` samples of *this* window, carried into the next call (silero v5 contract).
        """
        x = np.concatenate((context, window))  # 64 + 512 = 576, what the model was trained on
        out, new_state = self._session.run(
            ["output", "stateN"],
            {"input": x.reshape(1, -1), "state": state, "sr": self._sr},
        )
        return float(out[0, 0]), new_state, window[-_CONTEXT:].copy()


class UtteranceSegmenter:
    """Per-user streaming segmenter: feed 16 kHz mono float32, get utterances out.

    Invokes ``on_utterance(pcm_s16le_bytes, duration_s)`` once per completed utterance, on the
    reader thread. The emitted PCM is 16 kHz mono s16le — ready for faster-whisper (Phase 4).
    """

    def __init__(
        self, vad: SileroVad, on_utterance: Callable[[bytes, float], None]
    ) -> None:
        self._vad = vad
        self._on_utterance = on_utterance
        self._state = vad.new_state()
        self._context = vad.new_context()
        self._tail = np.empty(0, dtype=np.float32)  # leftover (<512) samples between feeds

        self._pad_windows = max(1, round(_SPEECH_PAD_MS / _WINDOW_MS))
        self._silence_windows_held = round(_MIN_SILENCE_MS / _WINDOW_MS)
        # Pre-speech padding: ring of the most recent windows kept while still silent.
        self._prebuf: deque[np.ndarray] = deque(maxlen=self._pad_windows)

        self._triggered = False
        self._collected: list[np.ndarray] = []
        self._silence_ms = 0.0
        self._speech_windows = 0

    def feed(self, samples: np.ndarray) -> None:
        """Feed 16 kHz mono float32 samples; runs whole 512-sample windows as they fill."""
        if samples.size:
            self._tail = (
                np.concatenate((self._tail, samples)) if self._tail.size else samples
            )
        while self._tail.size >= _WINDOW:
            window = self._tail[:_WINDOW].copy()  # copy: detach from the shared tail buffer
            self._tail = self._tail[_WINDOW:]
            self._process_window(window)

    def flush(self) -> None:
        """End of stream (e.g. on leave): emit any in-progress utterance, drop leftovers."""
        if self._triggered:
            self._finalize()
        self._tail = np.empty(0, dtype=np.float32)

    def _process_window(self, window: np.ndarray) -> None:
        prob, self._state, self._context = self._vad(window, self._state, self._context)

        if not self._triggered:
            self._prebuf.append(window)
            if prob >= _SPEECH_THRESHOLD:
                # Start an utterance, seeded with the pre-speech padding (incl. this window).
                self._triggered = True
                self._collected = list(self._prebuf)
                self._prebuf.clear()
                self._silence_ms = 0.0
                self._speech_windows = 1
            return

        # Triggered: keep collecting until we see enough trailing silence.
        self._collected.append(window)
        if prob < _SILENCE_THRESHOLD:
            self._silence_ms += _WINDOW_MS
            if self._silence_ms >= _MIN_SILENCE_MS:
                self._finalize()
        else:
            self._silence_ms = 0.0
            if prob >= _SPEECH_THRESHOLD:
                self._speech_windows += 1

    def _finalize(self) -> None:
        # Trim trailing silence down to the post-speech pad (we collected _MIN_SILENCE_MS of it
        # to decide the utterance ended; only _SPEECH_PAD_MS belongs in the clip).
        drop = max(0, self._silence_windows_held - self._pad_windows)
        windows = self._collected[: len(self._collected) - drop] if drop else self._collected
        audio = np.concatenate(windows) if windows else np.empty(0, dtype=np.float32)
        speech_ms = self._speech_windows * _WINDOW_MS

        self._triggered = False
        self._collected = []
        self._silence_ms = 0.0
        self._speech_windows = 0
        # Note: the recurrent state is intentionally NOT reset — silero is a streaming model
        # and carrying state across utterances within one stream is how it stays accurate.

        if speech_ms < _MIN_SPEECH_MS:
            return  # too little real speech — a cough/click, not an utterance
        pcm = (np.clip(audio, -1.0, 1.0) * _I16_PEAK).astype("<i2").tobytes()
        self._on_utterance(pcm, len(audio) / _SR)
