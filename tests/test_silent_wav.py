"""Tests for the shared silent-WAV writer (dmbot.tts.wavio.write_silent_wav).

The two TTS backends (Piper 22050 Hz, XTTS 24000 Hz) emit a short silent mono WAV for
the "nothing speakable" case. This guards that the centralized writer produces a valid
mono 16-bit WAV at the requested framerate with 0.2 s worth of frames.
"""

from __future__ import annotations

import wave

import pytest

from dmbot.tts.wavio import write_silent_wav


@pytest.mark.parametrize("framerate", [22050, 24000])
def test_write_silent_wav_format_and_frames(tmp_path, framerate):
    path = str(tmp_path / f"silent_{framerate}.wav")
    write_silent_wav(path, framerate)

    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == framerate
        assert w.getnframes() == int(framerate * 0.2)


@pytest.mark.parametrize("framerate", [22050, 24000])
def test_write_silent_wav_is_silence(tmp_path, framerate):
    path = str(tmp_path / f"silent_{framerate}.wav")
    write_silent_wav(path, framerate)

    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
    assert frames == b"\x00" * (int(framerate * 0.2) * 2)
