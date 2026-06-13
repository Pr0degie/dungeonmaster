"""Shared WAV helpers for the TTS backends.

Both Piper and XTTS need to emit a short silent mono WAV for the "nothing speakable"
case (emoji-/punctuation-only answers) so the caller still gets a valid, playable path
instead of feeding a bare-punctuation chunk to the synthesiser. The two backends differ
only in sample rate, so the writer lives here and each passes its own framerate.
"""

from __future__ import annotations

import wave


def write_silent_wav(path: str, framerate: int, duration_s: float = 0.2) -> None:
    """Write a silent mono 16-bit PCM WAV of ``duration_s`` seconds to ``path``.

    The sample count is ``int(framerate * duration_s)`` zero frames — at the default
    0.2 s this matches the previous inline writers (Piper 22050 Hz → 4410 frames,
    XTTS 24000 Hz → 4800 frames) byte-for-byte.
    """
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00" * (int(framerate * duration_s) * 2))
