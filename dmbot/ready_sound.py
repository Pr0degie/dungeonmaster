"""A soft "pop" on the bot's own machine the moment it is logged in (2026-10-31, Tobi's wish).

It sounds with the "logged in as DungeonMaster" line — Tobi found waiting for the TTS voice as
well (~17 s more) far too late. Played once per process, never again on reconnects.
The pop is synthesised (a quiet sine sweeping up with a fast decay, like a bubble) — no sound file,
no new dependency. Windows only (``winsound``); elsewhere, and on any error, it stays silent: the
"logged in as" log line is the record either way.
"""

from __future__ import annotations

import logging
import math
import struct
import sys
import tempfile
import threading
import wave
from pathlib import Path

log = logging.getLogger(__name__)

RATE = 44_100
POP_SECONDS = 0.09
POP_VOLUME = 0.28            # of full scale — soft on purpose
POP_FROM_HZ, POP_TO_HZ = 380.0, 1150.0


def pop_samples() -> list[int]:
    """16-bit samples of the pop: a sine sweeping up, 3 ms attack, exponential decay."""
    count = int(RATE * POP_SECONDS)
    samples: list[int] = []
    phase = 0.0
    for i in range(count):
        t = i / RATE
        freq = POP_FROM_HZ + (POP_TO_HZ - POP_FROM_HZ) * min(1.0, t / 0.05)
        phase += 2 * math.pi * freq / RATE
        envelope = min(1.0, t / 0.003) * math.exp(-t / 0.018)
        samples.append(int(32767 * POP_VOLUME * envelope * math.sin(phase)))
    return samples


def write_pop(path: Path) -> Path:
    """The pop as a mono 16-bit WAV at ``path``."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        samples = pop_samples()
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def play_pop() -> None:
    """Play the pop (blocking until it is handed to the sound system). Silent off Windows."""
    if sys.platform != "win32":
        return
    import winsound  # Windows-only stdlib module

    path = write_pop(Path(tempfile.gettempdir()) / "dmbot_ready_pop.wav")
    winsound.PlaySound(str(path), winsound.SND_FILENAME)


class ReadySound:
    """Plays the pop once, when Discord is logged in."""

    def __init__(self, *, enabled: bool = True, play=play_pop) -> None:
        self._enabled = enabled
        self._play = play
        self._started = False
        self._lock = threading.Lock()

    def logged_in(self) -> threading.Thread | None:
        """Call from ``on_ready``. Plays the pop (in a thread) the first time only."""
        with self._lock:
            if not self._enabled or self._started:
                return None
            self._started = True
        thread = threading.Thread(target=self._play_once, name="ready-sound", daemon=True)
        thread.start()
        return thread

    def _play_once(self) -> None:
        try:
            self._play()
        except Exception:  # cosmetic: a broken sound device must never disturb the bot
            log.warning("could not play the ready sound", exc_info=True)
