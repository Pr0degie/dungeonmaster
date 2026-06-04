"""Console + file logging for DMbot.

The **console** is curated for reading during play: transcripts (``📝``) render as a
per-speaker, colourised chat layout, and the high-frequency pipeline chatter (the ``PCM ⟳``
heartbeats, faster-whisper's per-utterance ``Processing audio`` lines) is hidden from the
console. The **file** (``logs/dmbot.log``) still gets *everything*, plain (no ANSI), UTF-8 —
so it survives the window closing and stays greppable for debugging.

ANSI colours are enabled on the Windows console via ``colorama.just_fix_windows_console()``
(turns on virtual-terminal processing for the conhost that ``start_dmbot.bat`` opens).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

try:  # enable ANSI on the Windows console; harmless elsewhere / if missing
    import colorama

    colorama.just_fix_windows_console()
except Exception:  # pragma: no cover
    pass

_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "dmbot.log"

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_GREY = "\033[90m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_WHITE = "\033[97m"
# Distinct, readable-on-black accents cycled per speaker.
_SPEAKER_COLORS = (
    "\033[96m",  # bright cyan
    "\033[95m",  # bright magenta
    "\033[94m",  # bright blue
    "\033[92m",  # bright green
    "\033[93m",  # bright yellow
)


def _speaker_color(name: str) -> str:
    return _SPEAKER_COLORS[sum(map(ord, name)) % len(_SPEAKER_COLORS)]


class _ConsoleFormatter(logging.Formatter):
    """Colourise the console: transcripts as chat, warnings/errors highlighted, rest dim."""

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()

        if msg.startswith("📝"):  # "📝 Name: text" → a chat line
            body = msg.split(" ", 1)[1] if " " in msg else msg
            name, _, text = body.partition(": ")
            col = _speaker_color(name)
            return f"{_DIM}{ts}{_RESET}  {col}{_BOLD}{name:>12}{_RESET}  {_WHITE}{text}{_RESET}"

        if msg.startswith("🗣"):  # utterance cut — secondary, dim
            return f"{_DIM}{ts}  {msg}{_RESET}"

        if record.levelno >= logging.WARNING:
            col = _RED if record.levelno >= logging.ERROR else _YELLOW
            return f"{_DIM}{ts}{_RESET} {col}{record.levelname:<7} {record.name}{_RESET} | {col}{msg}{_RESET}"

        return f"{_DIM}{ts}  {_GREY}{record.name}{_RESET} | {msg}"


class _ConsoleNoiseFilter(logging.Filter):
    """Drop high-frequency chatter from the CONSOLE only (the file still records it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "faster_whisper":
            return False  # the per-utterance "Processing audio ..." line
        return "PCM ⟳" not in record.getMessage()  # the 2 s heartbeat


def setup_logging(level: str) -> Path:
    """Install the console + file handlers on the root logger. Returns the log-file path."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    for handler in list(root.handlers):  # idempotent across restarts/tests
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(_ConsoleFormatter())
    console.addFilter(_ConsoleNoiseFilter())
    root.addHandler(console)

    plain = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S"
    )
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_h = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
        file_h.setFormatter(plain)
        root.addHandler(file_h)
    except OSError:
        logging.getLogger("dmbot").warning(
            "could not open log file %s — console only", _LOG_FILE, exc_info=True
        )

    # discord.py gateway/voice logs are noisy; keep them civil (console + file).
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.ext.voice_recv.opus").setLevel(logging.ERROR)

    logging.getLogger("dmbot").info(
        "=== DMbot starting (%s) — log file %s ===",
        time.strftime("%Y-%m-%d %H:%M:%S"), _LOG_FILE,
    )
    return _LOG_FILE
