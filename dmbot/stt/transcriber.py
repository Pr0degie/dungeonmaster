"""faster-whisper STT wrapper (Phase 4).

Turns a cut utterance (16 kHz mono s16le — exactly what ``VadSink`` emits) into German text.

Two things matter here:

1. **Off the audio thread.** ``_on_utterance`` fires on the voice-recv reader / silence-gen
   thread; running a whisper inference there (tens to hundreds of ms) would stall audio for
   *every* user. So transcription runs on a dedicated worker thread fed by a queue — submit is
   non-blocking, results come back via the ``on_transcript`` callback. A single worker also
   serialises calls, which is what faster-whisper wants (the model isn't for concurrent use).

2. **Windows CUDA DLLs.** faster-whisper → CTranslate2 needs cuDNN + cuBLAS + cudart DLLs that
   don't ship with it. We get them from the ``nvidia-cudnn-cu12`` / ``nvidia-cublas-cu12`` /
   ``nvidia-cuda-runtime-cu12`` wheels and **preload them by full path** (plus register their
   ``bin`` dirs) *before* importing faster-whisper — see ``_register_cuda_dll_dirs`` for why the
   preload is needed on a box without a system CUDA install. If the GPU still won't init, we fall
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


# CUDA-12 DLLs that CTranslate2 (faster-whisper) needs, in dependency order: each DLL's
# dependencies must be loaded before it (cudart ← cublasLt ← cublas; cudnn last). Globbed so the
# exact minor-version suffix doesn't matter (cudart64_12.dll, cublas64_12.dll, cudnn64_9.dll, …).
_CUDA_PRELOAD = (
    ("nvidia.cuda_runtime", "cudart64_*.dll"),
    ("nvidia.cublas", "cublasLt64_*.dll"),
    ("nvidia.cublas", "cublas64_*.dll"),
    ("nvidia.cudnn", "cudnn64_*.dll"),
)


def _register_cuda_dll_dirs() -> None:
    """Make the cuDNN/cuBLAS/cudart DLLs from the nvidia wheels loadable (Windows only).

    Two steps: register each wheel's ``bin`` dir (so a DLL's sibling deps resolve), then
    **explicitly preload** the key CUDA-12 DLLs by full path with ``ctypes.WinDLL``.

    The preload is the load-bearing part. ``os.add_dll_directory`` alone is not enough: on a box
    with no system-wide CUDA on PATH, CTranslate2's own loader does not reliably search the added
    user dirs, so ``cublas64_12.dll`` fails with "is not found or cannot be loaded" (hit on a
    fresh RTX 5080 box, 2026-06-05; the dev 4070 only worked because it had a system CUDA toolkit
    on PATH). Loading each DLL by full path up front puts it in the process, so CTranslate2's later
    load-by-name resolves to the already-loaded module — no system CUDA needed.

    No-op off Windows. Harmless if the wheels aren't installed — the GPU load simply fails and we
    fall back to CPU int8.
    """
    if not hasattr(os, "add_dll_directory"):
        return
    import ctypes
    import glob

    bin_dirs: dict[str, str] = {}
    for pkg in ("nvidia.cuda_runtime", "nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            spec = None
        if spec is None or not spec.submodule_search_locations:
            continue
        bin_dir = os.path.join(spec.submodule_search_locations[0], "bin")
        if os.path.isdir(bin_dir):
            os.add_dll_directory(bin_dir)
            bin_dirs[pkg] = bin_dir
            log.debug("registered CUDA DLL dir %s", bin_dir)

    for pkg, pattern in _CUDA_PRELOAD:
        bin_dir = bin_dirs.get(pkg)
        if not bin_dir:
            continue
        for dll in glob.glob(os.path.join(bin_dir, pattern)):
            try:
                ctypes.WinDLL(dll)
                log.debug("preloaded %s", os.path.basename(dll))
            except OSError as exc:
                log.warning("could not preload %s: %s", os.path.basename(dll), exc)


_register_cuda_dll_dirs()  # MUST run before faster_whisper pulls in ctranslate2

from faster_whisper import WhisperModel  # noqa: E402  (after the DLL-dir registration)

_I16_FULL_SCALE = 32768.0

# Hallucination guard. On short/quiet clips Whisper invents stock phrases ("Vielen Dank
# für's Zuhören", "Das war's für heute" …). Those segments fire when the model thinks the
# audio is mostly non-speech (high no_speech_prob) or is low-confidence (low avg_logprob).
# Drop them; thresholds tuned conservatively so real (even mumbled) speech is kept.
_NO_SPEECH_MAX = 0.7   # drop a segment whose no_speech_prob exceeds this
_LOGPROB_MIN = -1.0    # …or whose avg_logprob falls below this

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
        self._stop = threading.Event()  # set on shutdown so the worker exits promptly

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
        """Signal the worker to exit ASAP and wait briefly.

        Sets a flag so the worker abandons any queued backlog instead of transcribing it all
        first, and wakes its blocking ``get()`` with a sentinel. The join is short — the thread
        is a daemon, so a transcription still mid-flight after the timeout dies with the process.
        This keeps Ctrl+C shutdown prompt instead of blocking for the whole queue."""
        self._stop.set()
        self._queue.put(None)  # wake the blocking get()
        if self._thread is not None:
            self._thread.join(timeout=2)
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
            if item is None or self._stop.is_set():  # sentinel or shutdown → drop any backlog
                break
            name, pcm, clip_s = item
            try:
                self._transcribe_one(name, pcm, clip_s)
            except Exception:
                log.exception("transcription failed for %s", name)

    def _transcribe_one(self, name: str, pcm: bytes, clip_s: float) -> None:
        # s16le mono → float32 [-1, 1), what faster-whisper expects as a raw array.
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / _I16_FULL_SCALE
        # We already did VAD upstream, so don't run whisper's own VAD filter.
        # condition_on_previous_text=False: each utterance is independent, and it stops a
        # hallucination from priming the next. transcribe() returns a generator — the real
        # work happens as we consume it, so time the join.
        t0 = time.perf_counter()
        segments, _info = self._model.transcribe(  # type: ignore[union-attr]
            audio,
            language=self._language,
            vad_filter=False,
            beam_size=5,
            condition_on_previous_text=False,
        )
        kept, dropped = [], []
        for seg in segments:
            seg_text = seg.text.strip()
            if not seg_text:
                continue
            if seg.no_speech_prob > _NO_SPEECH_MAX or seg.avg_logprob < _LOGPROB_MIN:
                dropped.append((seg_text, seg.no_speech_prob, seg.avg_logprob))
                continue
            kept.append(seg_text)
        text = " ".join(kept).strip()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if dropped:
            log.debug(
                "dropped %d low-confidence seg(s) from %s: %s", len(dropped), name, dropped
            )
        if text:
            self._on_transcript(name, text, clip_s, latency_ms)
        else:
            log.debug("no confident speech in a %s utterance (%d samples)", name, audio.size)
