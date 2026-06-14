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


def concat_wavs(parts: list[str], out_path: str, gap_s: float = 0.15) -> None:
    """Concatenate same-format WAV files into ``out_path`` with ``gap_s`` of silence between each.

    Torch-free (only ``wave``), so non-TTS callers (e.g. the cog that joins per-sentence synth WAVs
    into one seamless playback) can reuse it without importing the heavy XTTS stack. The output
    inherits the first part's format; all parts must share it (they do — same backend/speaker).
    """
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
