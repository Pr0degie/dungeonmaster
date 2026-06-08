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

import itertools
import logging
import signal
import sys
import threading
import time

import discord
from discord.ext import commands

from .config import Config
from .llm.preflight import check_ollama
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
                dm_max_lines=self._config.dm_max_lines,
                system=self._config.system,
                push_to_talk=self._config.push_to_talk,
                pause_vad_while_speaking=self._config.pause_vad_while_speaking,
                button_autosend=self._config.button_autosend,
                roll_router=self._config.roll_router,
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


_YELLOW = "\033[93m"
_RED = "\033[91m"
_RESET = "\033[0m"


def _animate_shutdown() -> None:
    """Animate 'Shutting down' with cycling dots on one line (carriage-return) so the operator sees
    the teardown is progressing, not hung. Runs in a daemon thread → killed when the process exits."""
    for dots in itertools.cycle(("   ", ".  ", ".. ", "...")):
        sys.stdout.write(f"\r{_RED}Shutting down{dots}{_RESET}")
        sys.stdout.flush()
        time.sleep(0.3)


def _install_sigint_guard() -> None:
    """Two-stage Ctrl+C: the **first** press asks ("Quit?") and keeps running, the **second**
    shuts down. discord.py 2.7.1's ``run()`` installs no SIGINT handler (verified), so ours stays
    in effect; the second press raises ``KeyboardInterrupt``, which ``run()`` catches and tears
    down cleanly (``cog_unload`` → transcriber/brain/bridge close). Avoids killing a session on a
    single fat-fingered Ctrl+C. The second press also starts an animated 'Shutting down…' line so
    the (sometimes second-long) teardown visibly does something rather than looking frozen.
    """
    armed = {"v": False}

    def _handler(signum, frame) -> None:
        if not armed["v"]:
            armed["v"] = True
            print(f"\n{_YELLOW}Quit? Nochmal Strg+C zum Beenden.{_RESET}", flush=True)
            return
        sys.stdout.write(f"\n{_RED}Shutting down{_RESET}")  # instant paint; the thread animates the dots
        sys.stdout.flush()
        threading.Thread(target=_animate_shutdown, daemon=True).start()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handler)


def main() -> None:
    config = Config.load()
    setup_logging(
        config.log_level, to_file=config.log_to_file, transcript_file=config.transcript_file
    )
    _ensure_opus()
    # Surface a down/misconfigured LLM host at boot (clear log line) instead of a cryptic
    # httpx.ConnectError mid-game. Best-effort: the bot still starts either way.
    check_ollama(config.ollama_host, config.ollama_model)
    _install_sigint_guard()  # first Ctrl+C asks, second shuts down
    DMBot(config).run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
