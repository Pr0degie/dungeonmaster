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
import wave

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # accept the model licence non-interactively

from TTS.api import TTS  # noqa: E402 — heavy (torch); only imported when XTTS is selected

from .textsplit import chunk_text, normalize_for_tts  # noqa: E402

log = logging.getLogger(__name__)

_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
_DEFAULT_SPEAKER = "Dionisio Schuyler"

_CHUNK_GAP_S = 0.15  # a little silence between re-joined chunks so they don't run together


def _concat_wavs(parts: list[str], out_path: str, gap_s: float = _CHUNK_GAP_S) -> None:
    """Concatenate same-format WAV files into ``out_path`` with a short silence between each."""
    with wave.open(parts[0], "rb") as first:
        params = first.getparams()
    gap = b"\x00" * (int(params.framerate * gap_s) * params.sampwidth * params.nchannels)
    with wave.open(out_path, "wb") as out:
        out.setparams(params)
        for i, part in enumerate(parts):
            with wave.open(part, "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if i < len(parts) - 1:
                out.writeframes(gap)


def _silent_wav(path: str, *, seconds: float = 0.2, framerate: int = 24000) -> None:
    """Write a short silent 24 kHz mono WAV (XTTS's output format). Used when an answer has nothing
    speakable after cleanup, so the caller still gets a valid, playable path instead of XTTS being
    handed a bare-punctuation chunk (which it reads for ~15 s or turns into gibberish)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00" * (int(framerate * seconds) * 2))


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
        available = list(self._tts.speakers)
        self._speaker = speaker if speaker in available else _DEFAULT_SPEAKER
        if speaker and speaker not in available:
            log.warning("XTTS speaker %r unknown — using %s", speaker, self._speaker)
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
        German) — each chunk is synthesised separately and the WAVs are concatenated."""
        fd, path = tempfile.mkstemp(prefix="dm_tts_", suffix=".wav")
        os.close(fd)
        chunks = chunk_text(normalize_for_tts(text))  # speech-only cleanup, then split for XTTS's char limit
        if not chunks:  # nothing speakable (emoji-/punctuation-only) → silence, never feed XTTS junk
            _silent_wav(path)
            return path
        if len(chunks) <= 1:
            self._tts.tts_to_file(
                text=chunks[0], speaker=self._speaker, language=self._language, file_path=path
            )
            return path
        parts: list[str] = []
        try:
            for chunk in chunks:
                cfd, cpath = tempfile.mkstemp(prefix="dm_tts_part_", suffix=".wav")
                os.close(cfd)
                self._tts.tts_to_file(
                    text=chunk, speaker=self._speaker, language=self._language, file_path=cpath
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
