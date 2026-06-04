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

log = logging.getLogger(__name__)

_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
_DEFAULT_SPEAKER = "Dionisio Schuyler"


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
        """Render ``text`` in the active speaker's voice to a fresh WAV; return its path."""
        fd, path = tempfile.mkstemp(prefix="dm_tts_", suffix=".wav")
        os.close(fd)
        self._tts.tts_to_file(
            text=text, speaker=self._speaker, language=self._language, file_path=path
        )
        return path
