"""Run DMbot (Phase 2).

A Discord bot that, on ``!join``, enters the caller's voice channel and logs per-user
PCM while filtering Bot A's voice (feedback protection layer 1). This is the voice-receive
scaffold only — VAD/STT/LLM/TTS come in later phases.

    uv run python -m dmbot

Requires (one-time, in the Discord Developer Portal): the **Message Content** and
**Server Members** privileged intents enabled for DMbot. Needs the Opus library/DLL on
Windows (SETUP B6) so incoming Opus can be decoded to PCM.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import discord
from discord.ext import commands

from .config import Config
from .voice.commands import VoiceReceiveCog

log = logging.getLogger("dmbot")

# Console logs vanish when the bot window is closed; mirror everything to a file so the
# Phase-3 gate evidence (the "🗣 utterance" lines) survives a restart. Gitignored (*.log).
_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "dmbot.log"


def _setup_logging(level: str) -> None:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s", datefmt="%H:%M:%S"
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    handlers: list[logging.Handler] = [console]

    # File handler: UTF-8 so the glyphs/Umlauts don't blow up on Windows cp1252; append, with
    # a per-run banner so successive runs stay separable in one file.
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_h = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
        file_h.setFormatter(fmt)
        handlers.append(file_h)
    except OSError:
        log.warning("could not open log file %s — console only", _LOG_FILE, exc_info=True)

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO), handlers=handlers, force=True
    )
    log.info("=== DMbot starting (%s) — logging to %s ===", time.strftime("%Y-%m-%d %H:%M:%S"), _LOG_FILE)

    # discord.py gateway/voice logs are noisy at DEBUG; keep them civil.
    logging.getLogger("discord").setLevel(logging.WARNING)
    # voice-recv warns per single lost/late RTP packet ("lost being flushed") — benign jitter
    # (a sender's voice-activation cutting in/out). Quiet it so it doesn't drown the PCM log.
    logging.getLogger("discord.ext.voice_recv.opus").setLevel(logging.ERROR)


def _ensure_opus() -> None:
    if discord.opus.is_loaded():
        log.info("Opus is loaded.")
        return
    # discord.py auto-loads the bundled Opus on import for supported platforms; nudge it
    # once more, then report clearly. Without Opus, wants_opus=False decoding yields no PCM.
    try:
        discord.opus._load_default()  # type: ignore[attr-defined]
    except Exception:
        pass
    if discord.opus.is_loaded():
        log.info("Opus loaded (default).")
    else:
        log.error(
            "Opus is NOT loaded — voice receive cannot decode PCM. On Windows the Opus "
            "DLL must be available (SETUP B6); see CLAUDE.md 'No sound despite correct code'."
        )


class DMBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged: prefix commands need the text
        intents.members = True          # privileged: resolve members to filter Bot A
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self._config = config

    async def setup_hook(self) -> None:
        await self.add_cog(
            VoiceReceiveCog(self, bot_a_user_id=self._config.bot_a_user_id)
        )

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user and self.user.id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # DMbot shares the "!" prefix with the music bot; silently ignore commands it doesn't
        # own (e.g. !play) instead of spamming CommandNotFound.
        if isinstance(error, commands.CommandNotFound):
            return
        log.error("command error in %r: %r", getattr(ctx, "command", None), error)


def main() -> None:
    config = Config.load()
    _setup_logging(config.log_level)
    _ensure_opus()
    DMBot(config).run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
