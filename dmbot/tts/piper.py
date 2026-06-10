"""Piper text-to-speech wrapper (Phase 6).

Synthesises the DM's German answer to a WAV file that Bot A then plays via the `/speak`
bridge. The WAV goes to the **OS temp dir** (`tempfile.gettempdir()`), never `/tmp` — this is
Windows (CLAUDE.md). piper-tts 1.x bundles its espeak-ng data, so no separate phonemiser
install is needed.

Synthesis is CPU-bound and blocking; callers run it off the event loop (``asyncio.to_thread``)
so the bot stays responsive. The voice model is loaded once and reused.
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from pathlib import Path

from piper import PiperVoice

from .textsplit import normalize_for_tts

log = logging.getLogger(__name__)

# Default voice (downloaded per SETUP B5 into voices/). Overridable via config.
_DEFAULT_VOICE = Path(__file__).resolve().parent.parent.parent / "voices" / "de_DE-thorsten-medium.onnx"


class PiperTTS:
    """A loaded Piper voice. One per bot; call :meth:`synthesize` per DM answer."""

    def __init__(self, voice_path: str | os.PathLike = _DEFAULT_VOICE) -> None:
        model = Path(voice_path)
        if not model.exists():
            raise FileNotFoundError(
                f"Piper voice not found at {model}. Download de_DE-thorsten-medium.onnx "
                "(+ .onnx.json) into voices/ — see docs/SETUP.md B5."
            )
        config = model.with_suffix(model.suffix + ".json")  # de_DE-…onnx → …onnx.json
        # CPU: the GPU is busy with whisper + the LLM, and Piper is real-time on CPU.
        self._voice = PiperVoice.load(
            str(model), config_path=str(config) if config.exists() else None, use_cuda=False
        )
        log.info("Piper voice loaded: %s", model.name)

    def synthesize(self, text: str) -> str:
        """Render ``text`` to a fresh WAV in the OS temp dir; return its absolute path.

        The caller is responsible for deleting the file once Bot A has played it.
        """
        fd, path = tempfile.mkstemp(prefix="dm_tts_", suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wav_file:
            self._voice.synthesize_wav(normalize_for_tts(text), wav_file)  # speech-only punctuation cleanup
        return path
