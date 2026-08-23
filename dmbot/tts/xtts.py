"""Coqui XTTS v2 text-to-speech wrapper (Phase 6, alternative to Piper).

XTTS v2 is a multilingual neural TTS with ~58 built-in speaker timbres that can all speak
German (pick a speaker + ``language="de"``), and it can also clone a voice from a short
reference clip. It is far heavier than Piper (pulls torch) and slower — on CPU a sentence
takes a few seconds — so it runs only when ``TTS_ENGINE=xtts``. On GPU it is near real-time,
but the 12 GB 4070 has no spare VRAM next to nemo+whisper, so default device is CPU until that
is freed (whisper→CPU, or the LLM offloaded to the 5080, ADR 002).

Output is 24 kHz mono WAV in the OS temp dir; Bot A's ffmpeg plays it. Same ``synthesize(text)
-> path`` interface as :class:`~dmbot.tts.piper.PiperTTS`, so the cog treats them alike.
"""

from __future__ import annotations

import logging
import os
import tempfile

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # accept the model licence non-interactively

from TTS.api import TTS  # noqa: E402 — heavy (torch); only imported when XTTS is selected

from ..voice.preflight import (  # noqa: E402 — torch-free; the shared speaker-config helpers
    DEFAULT_XTTS_SPEAKER,
    resolve_speaker,
    speaker_problem,
)
from .textsplit import chunk_text, normalize_for_tts  # noqa: E402
from .wavio import concat_wavs, write_silent_wav  # noqa: E402

log = logging.getLogger(__name__)

_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

_CHUNK_GAP_S = 0.15  # a little silence between re-joined chunks so they don't run together

# XTTS sampling overrides, passed straight to ``tts_to_file`` (ADR 016 follow-up, D55). Two levers
# D53 deferred until a live test proved them needed — it did ("Psychosen bei Satzzeichen"):
#   * ``split_sentences=False`` — we already split into <240-char, sentence-grouped chunks
#     (``textsplit``), so XTTS's own pysbd splitter only re-tokenises them, and on the tiny
#     punctuation fragments it produces the autoregressive GPT loops/babbles at sentence ends.
#   * ``repetition_penalty=10.0`` — the model config ships 5.0; XTTS's own inference default is the
#     stronger anti-loop 10.0. Lift it back to that (tunable via ``XTTS_REPETITION_PENALTY``).
try:
    _REPETITION_PENALTY = float(os.environ.get("XTTS_REPETITION_PENALTY", "10.0"))
except ValueError:
    _REPETITION_PENALTY = 10.0
_SYNTH_KWARGS = {"split_sentences": False, "repetition_penalty": _REPETITION_PENALTY}


def _concat_wavs(parts: list[str], out_path: str, gap_s: float = _CHUNK_GAP_S) -> None:
    """Concatenate same-format WAV files into ``out_path`` with a short silence between each.

    Thin wrapper over the shared, torch-free :func:`dmbot.tts.wavio.concat_wavs` (so non-TTS
    callers can reuse the join logic without importing this XTTS module); only the default gap
    differs (XTTS's ``_CHUNK_GAP_S`` for re-joined sub-240-char chunks)."""
    concat_wavs(parts, out_path, gap_s=gap_s)


def _resolve_device(requested: str) -> str:
    """Honour ``requested`` but degrade to CPU if CUDA is unusable, never crash.

    Mirrors the STT transcriber's degrade-don't-die policy. A ``cuda`` request on a
    CPU-only torch build (or a machine with no GPU) otherwise raises "Torch not compiled
    with CUDA enabled" and takes the whole TTS path down — the DM goes mute. Falling back
    means the SAME ``.env`` (``TTS_DEVICE=cuda``) is safe on the GPU box and the dev box.
    """
    if requested == "cuda":
        import torch  # already loaded via TTS.api above; cheap here

        if not torch.cuda.is_available():
            log.warning(
                "TTS_DEVICE=cuda requested but torch has no CUDA (build=%s) — falling back "
                "to CPU. Install a CUDA torch build for GPU synthesis (see architecture.md §3).",
                torch.version.cuda,
            )
            return "cpu"
    return requested


class XttsTTS:
    """A loaded XTTS v2 model fixed to one built-in speaker. ``synthesize`` per DM answer."""

    def __init__(
        self,
        speaker: str = "",
        *,
        device: str = "cpu",
        language: str = "de",
    ) -> None:
        self._language = language
        device = _resolve_device(device)
        try:
            self._tts = TTS(_MODEL).to(device)
        except Exception:
            # GPU load can still fail past the CUDA check — most often VRAM/OOM next to nemo.
            # Degrade to CPU rather than leaving the DM mute.
            if device == "cpu":
                raise
            log.warning(
                "XTTS load on %s failed (likely VRAM/OOM) — retrying on CPU", device,
                exc_info=True,
            )
            device = "cpu"
            self._tts = TTS(_MODEL).to(device)
        # Speaker resolution, checked against the model's REAL speaker list (the boot preflight
        # `voice.preflight.check_tts_speaker` runs the same check earlier against the baked list,
        # before torch is even loaded). An unknown name still degrades rather than crashing — TTS
        # is an optional layer, it fails open (docs/lessons/optional-layers-fail-open-core-fails-
        # loud.md) — but it degrades LOUDLY: B13 (2026-08-22) had TTS_SPEAKER=cuda and one WARNING
        # line was enough to lose a whole evening to a random voice.
        available = list(self._tts.speakers)
        problem = speaker_problem(speaker, available)
        if problem is not None:
            log.error("XTTS speaker misconfigured: %s", problem)
        self._speaker = resolve_speaker(speaker, available)
        if problem is None and self._speaker != (speaker.strip() or DEFAULT_XTTS_SPEAKER):
            # Only reachable if the model itself no longer ships the default voice.
            log.error(
                "XTTS default speaker %r is missing from this model — speaking as %r instead. "
                "Set TTS_SPEAKER in .env explicitly (`!voices` lists what the model has).",
                DEFAULT_XTTS_SPEAKER, self._speaker,
            )
        log.info("XTTS v2 loaded on %s — speaker: %s", device, self._speaker)

    @property
    def speaker(self) -> str:
        return self._speaker

    def speakers(self) -> list[str]:
        return list(self._tts.speakers)

    def set_speaker(self, name: str) -> bool:
        """Switch the active speaker; returns False if the name is unknown."""
        if name not in self._tts.speakers:
            return False
        self._speaker = name
        return True

    def synthesize(self, text: str) -> str:
        """Render ``text`` in the active speaker's voice to a fresh WAV; return its path.

        Long answers are split into <240-char chunks (XTTS truncates a longer single chunk for
        German) — each chunk is synthesised separately and the WAVs are concatenated. XTTS's own
        sentence splitter is disabled (``_SYNTH_KWARGS``) so it renders our clean chunks as-is
        instead of re-tokenising them into punctuation fragments it then babbles on."""
        fd, path = tempfile.mkstemp(prefix="dm_tts_", suffix=".wav")
        os.close(fd)
        chunks = chunk_text(normalize_for_tts(text))  # speech-only cleanup, then split for XTTS's char limit
        if not chunks:  # nothing speakable (emoji-/punctuation-only) → silence, never feed XTTS junk
            write_silent_wav(path, 24000)  # XTTS's 24 kHz mono output format
            return path
        if len(chunks) <= 1:
            self._tts.tts_to_file(
                text=chunks[0], speaker=self._speaker, language=self._language, file_path=path,
                **_SYNTH_KWARGS,
            )
            return path
        parts: list[str] = []
        try:
            for chunk in chunks:
                cfd, cpath = tempfile.mkstemp(prefix="dm_tts_part_", suffix=".wav")
                os.close(cfd)
                self._tts.tts_to_file(
                    text=chunk, speaker=self._speaker, language=self._language, file_path=cpath,
                    **_SYNTH_KWARGS,
                )
                parts.append(cpath)
            _concat_wavs(parts, path)
        finally:
            for part in parts:
                try:
                    os.remove(part)
                except OSError:
                    pass
        return path
