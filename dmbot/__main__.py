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

import discord
from discord.ext import commands

from .config import Config
from .logsetup import setup_logging
from .voice.commands import VoiceReceiveCog

log = logging.getLogger("dmbot")


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
            VoiceReceiveCog(
                self,
                bot_a_user_id=self._config.bot_a_user_id,
                whisper_model=self._config.whisper_model,
                whisper_device=self._config.whisper_device,
                whisper_compute=self._config.whisper_compute,
                dump_utterances=self._config.dump_utterances,
                ollama_host=self._config.ollama_host,
                ollama_model=self._config.ollama_model,
                dm_num_predict=self._config.dm_num_predict,
                tts_engine=self._config.tts_engine,
                tts_voice=self._config.tts_voice,
                tts_speaker=self._config.tts_speaker,
                tts_device=self._config.tts_device,
                bridge_host=self._config.bridge_host,
                bridge_port=self._config.bridge_port,
                bridge_secret=self._config.bridge_secret,
            )
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
    setup_logging(config.log_level)
    _ensure_opus()
    DMBot(config).run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
