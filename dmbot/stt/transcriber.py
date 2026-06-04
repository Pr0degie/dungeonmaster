"""faster-whisper STT wrapper (Phase 4).

Turns a cut utterance (16 kHz mono s16le — exactly what ``VadSink`` emits) into German text.

Two things matter here:

1. **Off the audio thread.** ``_on_utterance`` fires on the voice-recv reader / silence-gen
   thread; running a whisper inference there (tens to hundreds of ms) would stall audio for
   *every* user. So transcription runs on a dedicated worker thread fed by a queue — submit is
   non-blocking, results come back via the ``on_transcript`` callback. A single worker also
   serialises calls, which is what faster-whisper wants (the model isn't for concurrent use).

2. **Windows CUDA DLLs.** faster-whisper → CTranslate2 needs cuDNN + cuBLAS DLLs that don't
   ship with it. We get them from the ``nvidia-cudnn-cu12`` / ``nvidia-cublas-cu12`` wheels and
   register their ``bin`` dirs with ``os.add_dll_directory`` *before* importing faster-whisper
   (SETUP B3 — "are the cuDNN/cuBLAS DLLs on the PATH?"). If the GPU still won't init, we fall
   back to CPU int8 so STT degrades instead of dying.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import queue
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


def _register_cuda_dll_dirs() -> None:
    """Make the cuDNN/cuBLAS DLLs from the nvidia wheels findable (Windows only).

    No-op off Windows (``os.add_dll_directory`` doesn't exist there) and harmless if the
    wheels aren't installed — the GPU load simply fails and we fall back to CPU.
    """
    if not hasattr(os, "add_dll_directory"):
        return
    for pkg in ("nvidia.cudnn", "nvidia.cublas"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            spec = None
        if spec is None or not spec.submodule_search_locations:
            continue
        bin_dir = os.path.join(spec.submodule_search_locations[0], "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            log.debug("registered CUDA DLL dir %s", bin_dir)


_register_cuda_dll_dirs()  # MUST run before faster_whisper pulls in ctranslate2

from faster_whisper import WhisperModel  # noqa: E402  (after the DLL-dir registration)

_I16_FULL_SCALE = 32768.0

# Callback shape: (speaker_name, transcript_text, clip_seconds, transcribe_ms).
OnTranscript = Callable[[str, str, float, float], None]


class Transcriber:
    """Background faster-whisper worker. Submit utterances, get transcripts via a callback."""

    def __init__(
        self,
        on_transcript: OnTranscript,
        *,
        model: str = "small",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "de",
    ) -> None:
        self._on_transcript = on_transcript
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._language = language

        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._model: WhisperModel | None = None

    def start(self) -> None:
        """Start the worker thread (it loads the model in the background)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="stt-worker", daemon=True
        )
        self._thread.start()

    def submit(self, name: str, pcm_s16le_mono_16k: bytes, clip_s: float) -> None:
        """Hand one utterance to the worker (non-blocking). ``clip_s`` is its audio length."""
        self._queue.put((name, pcm_s16le_mono_16k, clip_s))

    def stop(self) -> None:
        """Signal the worker to drain and exit."""
        self._queue.put(None)  # sentinel
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def _load_model(self) -> WhisperModel:
        try:
            model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
            log.info(
                "faster-whisper '%s' loaded on %s (%s)",
                self._model_name, self._device, self._compute_type,
            )
            return model
        except Exception:
            # Most often the cuDNN/cuBLAS DLLs or a CTranslate2/cuDNN version mismatch (SETUP
            # B3). Degrade to CPU int8 — slower but no CUDA deps — rather than disabling STT.
            log.exception(
                "faster-whisper GPU init failed (%s/%s) — falling back to CPU int8",
                self._device, self._compute_type,
            )
            model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
            log.info("faster-whisper '%s' loaded on CPU (int8 fallback)", self._model_name)
            return model

    def _run(self) -> None:
        try:
            self._model = self._load_model()
        except Exception:
            log.exception("could not load faster-whisper at all — STT disabled this session")
            return

        while True:
            item = self._queue.get()
            if item is None:
                break
            name, pcm, clip_s = item
            try:
                self._transcribe_one(name, pcm, clip_s)
            except Exception:
                log.exception("transcription failed for %s", name)

    def _transcribe_one(self, name: str, pcm: bytes, clip_s: float) -> None:
        # s16le mono → float32 [-1, 1), what faster-whisper expects as a raw array.
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / _I16_FULL_SCALE
        # We already did VAD upstream, so don't run whisper's own VAD filter. transcribe()
        # returns a generator — the real work happens as we consume it, so time the join.
        t0 = time.perf_counter()
        segments, _info = self._model.transcribe(  # type: ignore[union-attr]
            audio, language=self._language, vad_filter=False, beam_size=5
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if text:
            self._on_transcript(name, text, clip_s, latency_ms)
        else:
            log.debug("empty transcript for a %s utterance (%d samples)", name, audio.size)
