"""Console + file logging for DMbot.

The **console** is curated for reading during play: a green theme (dark "diff added-line"
green) where transcripts (``📝``) render as a chat layout — speaker name in bright green, the
line in green — and the high-frequency pipeline chatter (the ``PCM ⟳``
heartbeats, faster-whisper's per-utterance ``Processing audio`` lines) is hidden from the
console. The **file** (``logs/dmbot.log``) still gets *everything*, plain (no ANSI), UTF-8 —
so it survives the window closing and stays greppable for debugging.

ANSI colours are enabled on the Windows console via ``colorama.just_fix_windows_console()``
(turns on virtual-terminal processing for the conhost that ``start_dmbot.bat`` opens).
"""

from __future__ import annotations

import logging
import shutil
import textwrap
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
_GREEN = "\033[32m"   # the darker "diff added-line" green — the ambient theme colour
_BGREEN = "\033[92m"  # bright green, for emphasis (speaker names)
_RED = "\033[91m"
_YELLOW = "\033[93m"

# Chat layout: timestamp + a 12-wide name + a dim metric, then the text. The hanging indent
# for wrapped lines is computed per line from the actual prefix width.
_NAME_W = 12
_GAP = "  "


class _ConsoleFormatter(logging.Formatter):
    """Green-themed console: transcripts as chat (green), warnings/errors highlighted."""

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        msg = record.getMessage()

        if msg.startswith("🎭"):  # the DM's answer — prominent, bright, hanging indent
            text = msg.split(" ", 1)[1] if " " in msg else msg
            label = "Spielleiter"[:_NAME_W]
            prefix = f"{ts}{_GAP}{label:>{_NAME_W}}{_GAP}"
            indent = len(prefix)
            cols = shutil.get_terminal_size((100, 24)).columns
            lines = textwrap.wrap(text, width=max(20, cols - indent - 1)) or [""]
            head = (
                f"{_DIM}{_GREEN}{ts}{_RESET}{_GAP}"
                f"{_BGREEN}{_BOLD}{label:>{_NAME_W}}{_RESET}{_GAP}{_BGREEN}{_BOLD}{lines[0]}{_RESET}"
            )
            rest = [f"{' ' * indent}{_BGREEN}{ln}{_RESET}" for ln in lines[1:]]
            return "\n".join([head, *rest])

        if msg.startswith("📝"):  # "📝 Name | clip·ms | text" → a chat line, hanging indent
            body = msg.split(" ", 1)[1] if " " in msg else msg
            name, metric, text = (body.split(" | ", 2) + ["", ""])[:3]
            name = name[:_NAME_W]
            # The text column sits after ts + name + the dim metric, so continuation lines
            # hang under the first word (indented to that column) rather than at the margin.
            prefix = f"{ts}{_GAP}{name:>{_NAME_W}}{_GAP}{metric}{_GAP}"
            indent = len(prefix)
            cols = shutil.get_terminal_size((100, 24)).columns
            lines = textwrap.wrap(text, width=max(20, cols - indent - 1)) or [""]
            head = (
                f"{_DIM}{_GREEN}{ts}{_RESET}{_GAP}"
                f"{_BGREEN}{_BOLD}{name:>{_NAME_W}}{_RESET}{_GAP}"
                f"{_DIM}{_GREEN}{metric}{_RESET}{_GAP}{_GREEN}{lines[0]}{_RESET}"
            )
            rest = [f"{' ' * indent}{_GREEN}{ln}{_RESET}" for ln in lines[1:]]
            return "\n".join([head, *rest])

        if msg.startswith("🗣"):  # utterance cut — secondary, dim green
            return f"{_DIM}{_GREEN}{ts}  {msg}{_RESET}"

        if record.levelno >= logging.WARNING:  # keep these loud, not green
            col = _RED if record.levelno >= logging.ERROR else _YELLOW
            return f"{_DIM}{ts}{_RESET} {col}{record.levelname:<7} {record.name}{_RESET} | {col}{msg}{_RESET}"

        return f"{_DIM}{_GREEN}{ts}  {record.name} | {msg}{_RESET}"


class _ConsoleNoiseFilter(logging.Filter):
    """Keep the CONSOLE lean: only DMbot's own lines, plus any WARNING/ERROR from anywhere.

    Third-party INFO chatter (TTS/coqui synthesizer, httpx requests, faster_whisper, discord) and
    the 2 s PCM heartbeat are dropped from the console. The file handler (when enabled) has no
    filter, so a debug run still records the full detail."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "PCM ⟳" in record.getMessage():
            return False  # the 2 s per-user heartbeat
        return record.levelno >= logging.WARNING or record.name.startswith("dmbot")


class _UnpackErrorThrottle(logging.Filter):
    """Collapse discord-ext-voice-recv's "Error unpacking packet" flood (console + file).

    The alpha voice-recv library can't parse some RTP one-byte extension headers
    (``_parse_bede_header`` → ``struct.error``) and logs one ERROR *with traceback* per bad
    packet. It is **benign** — that packet is dropped, audio keeps flowing — but it can torrent
    hundreds of identical tracebacks in a second and bury everything else. We let the first one
    through (so it's on record), then suppress the rest, emitting a running count every Nth so a
    genuine escalation is still visible. Attached to the logger, so it covers all handlers."""

    _N = 500

    def __init__(self) -> None:
        super().__init__()
        self._count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if "Error unpacking packet" not in record.getMessage():
            return True
        self._count += 1
        record.exc_info = None  # drop the (identical, noisy) traceback
        record.args = None
        if self._count == 1:
            record.msg = (
                "voice-recv could not unpack an RTP packet (benign alpha jitter — the packet is "
                "dropped, audio keeps flowing; further occurrences summarised, tracebacks hidden)"
            )
            return True
        if self._count % self._N == 0:
            record.msg = f"voice-recv has dropped {self._count} unparseable RTP packets (benign)"
            return True
        return False


def setup_logging(level: str, *, to_file: bool = False) -> Path | None:
    """Install the console handler (always) and the file handler (only when ``to_file``).

    The console is kept lean (see :class:`_ConsoleNoiseFilter`). The full-detail file log is
    **off by default** — enable it with ``DM_LOG_FILE=1`` when you need to inspect a run after the
    window closes. Returns the log-file path when file logging is on, else ``None``."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    for handler in list(root.handlers):  # idempotent across restarts/tests
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(_ConsoleFormatter())
    console.addFilter(_ConsoleNoiseFilter())
    root.addHandler(console)

    log_file: Path | None = None
    if to_file:
        plain = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S"
        )
        try:
            _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            file_h = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
            file_h.setFormatter(plain)
            root.addHandler(file_h)
            log_file = _LOG_FILE
        except OSError:
            logging.getLogger("dmbot").warning(
                "could not open log file %s — console only", _LOG_FILE, exc_info=True
            )

    # discord.py gateway/voice logs are noisy; keep them civil (console + file).
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.ext.voice_recv.opus").setLevel(logging.ERROR)
    # Collapse the benign "Error unpacking packet" RTP-parse flood (alpha voice-recv bug).
    logging.getLogger("discord.ext.voice_recv.reader").addFilter(_UnpackErrorThrottle())

    where = f"log file {log_file}" if log_file else "file logging off (set DM_LOG_FILE=1)"
    logging.getLogger("dmbot").info(
        "=== DMbot starting (%s) — %s ===", time.strftime("%Y-%m-%d %H:%M:%S"), where
    )
    return log_file
