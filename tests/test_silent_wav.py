"""Tests for the shared WAV helpers (dmbot.tts.wavio): the silent-WAV writer and concat_wavs.

The two TTS backends (Piper 22050 Hz, XTTS 24000 Hz) emit a short silent mono WAV for
the "nothing speakable" case. This guards that the centralized writer produces a valid
mono 16-bit WAV at the requested framerate with 0.2 s worth of frames. concat_wavs joins
per-sentence synth WAVs into one continuous track (used by the !intro test seamless delivery).
"""

from __future__ import annotations

import wave

import pytest

from dmbot.tts.wavio import concat_wavs, write_silent_wav


def _write_pcm(path: str, data: bytes, framerate: int = 24000) -> None:
    """Write raw 16-bit mono PCM ``data`` to a WAV at ``path`` (data length must be even)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(data)


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


def test_concat_wavs_joins_in_order_with_gap(tmp_path):
    # two distinct WAVs joined with a 0.1 s silence between → order preserved, gap inserted once,
    # format inherited from the first part. This is the !intro seamless-track join.
    a, b, out = (str(tmp_path / n) for n in ("a.wav", "b.wav", "out.wav"))
    _write_pcm(a, b"\x01\x02" * 100)   # 100 frames
    _write_pcm(b, b"\x03\x04" * 50)    # 50 frames
    concat_wavs([a, b], out, gap_s=0.1)

    gap_frames = int(24000 * 0.1)
    with wave.open(out, "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 100 + gap_frames + 50
        frames = w.readframes(w.getnframes())
    assert frames == (b"\x01\x02" * 100) + (b"\x00" * (gap_frames * 2)) + (b"\x03\x04" * 50)


def test_concat_wavs_zero_gap_is_pure_concatenation(tmp_path):
    a, b, out = (str(tmp_path / n) for n in ("a.wav", "b.wav", "out.wav"))
    _write_pcm(a, b"\x01\x02" * 10)
    _write_pcm(b, b"\x03\x04" * 20)
    concat_wavs([a, b], out, gap_s=0.0)
    with wave.open(out, "rb") as w:
        assert w.getnframes() == 30
        assert w.readframes(30) == (b"\x01\x02" * 10) + (b"\x03\x04" * 20)


def test_concat_wavs_single_part_has_no_trailing_gap(tmp_path):
    a, out = str(tmp_path / "a.wav"), str(tmp_path / "out.wav")
    _write_pcm(a, b"\x07\x08" * 30)
    concat_wavs([a], out, gap_s=0.1)   # a lone part is copied verbatim — no gap appended
    with wave.open(out, "rb") as w:
        assert w.getnframes() == 30
        assert w.readframes(30) == b"\x07\x08" * 30
