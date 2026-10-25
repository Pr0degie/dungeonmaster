"""A process-wide latch for CUDA faults (2026-10-25, fourth Opus run).

XTTS and faster-whisper share one CUDA context in this process. A ``device-side assert`` (seen
live when two XTTS syntheses ran at once) is sticky: every later CUDA call in the process fails
too, so the bot goes deaf and mute until it is restarted. Before this module the only trace was
80+ identical tracebacks in the log while the table wondered why nobody was answering.

The workers (STT thread, TTS threads) hand their exceptions to :meth:`GpuHealth.report`. The first
CUDA fault trips the latch, logs one critical line and calls the listener exactly once; the cog
turns that into a single channel notice. Later faults return ``True`` too, so callers can log a
short line instead of another full traceback. Nothing here tries to recover — after a sticky CUDA
error only a restart helps.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

# Messages torch / ctranslate2 use for a broken CUDA context.
_FAULT_MARKERS = (
    "device-side assert",
    "cudaerrorassert",
    "illegal memory access",
    "cuda error",
    "cuda failed with error",
)


def is_cuda_fault(exc: BaseException) -> bool:
    """Does ``exc`` say the CUDA context is broken?"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _FAULT_MARKERS)


class GpuHealth:
    """Thread-safe one-shot latch. ``broken`` stays True for the rest of the process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.broken = False
        self.source = ""
        self._listener: Callable[[str], None] | None = None

    def set_listener(self, listener: Callable[[str], None] | None) -> None:
        """``listener(source)`` is called once, from whichever thread hit the first fault."""
        self._listener = listener

    def report(self, exc: BaseException, source: str) -> bool:
        """Record ``exc`` from ``source`` ("Sprachausgabe", "Spracherkennung"). Returns True when
        it is a CUDA fault (the first or a later one), False for any other error."""
        if not is_cuda_fault(exc):
            return False
        with self._lock:
            first = not self.broken
            if first:
                self.broken = True
                self.source = source
        if first:
            log.critical("💥 CUDA-Fehler in %s — GPU-Kontext kaputt, Sprache und Spracherkennung "
                         "sind bis zum Neustart des Bots tot: %s", source, exc)
            listener = self._listener
            if listener is not None:
                try:
                    listener(source)
                except Exception:
                    log.exception("could not hand the GPU fault to its listener")
        return True

    def log_failure(self, logger: logging.Logger, exc: BaseException, source: str, message: str) -> None:
        """Log a worker failure: the full traceback normally and for the first CUDA fault, then
        one short line per failure — instead of the 80 identical tracebacks of 2026-10-25."""
        already = self.broken
        if self.report(exc, source) and already:
            logger.error("%s — GPU-Kontext seit dem ersten CUDA-Fehler kaputt, Bot neu starten",
                         message)
        else:
            logger.error(message, exc_info=exc)

    def notice_de(self) -> str:
        """The one channel line for the table."""
        return (f"⚠ **GPU-Fehler** in der {self.source or 'Sprachverarbeitung'}: Sprachausgabe und "
                "Spracherkennung funktionieren bis zum Neustart nicht mehr. Bitte den Bot neu "
                "starten (der Spielstand ist gespeichert).")


#: The process-wide instance the workers report into.
health = GpuHealth()
