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
import signal

import discord
from discord.ext import commands

from .config import Config
from .llm.preflight import check_ollama
from .logsetup import setup_logging
from .runtime import SessionRuntime
from .shutdown import disconnect_voice, progress
from .voice.voicecog import VoiceCog
from .voice.dicecog import DiceCog
from .voice.dmcog import DMCog
from .voice.scenecog import SceneCog
from .voice.lorecog import LoreCog

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
            "DLL must be available (SETUP B6); see docs/conventions.md 'No sound despite correct code'."
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
        # Build the shared session state/services once from the config, then register the cogs that
        # share it (VoiceCog/DiceCog/DMCog + the thin SceneCog/LoreCog split off in ADR 039). The
        # kwarg avalanche moved into SessionRuntime (ADR 029); cross-cog flow goes through the
        # runtime's hooks, not bot.get_cog. VoiceCog is added first so its cog_unload (which closes
        # the shared services) runs first on shutdown. DMCog is added before LoreCog so the
        # runtime.speak hook LoreCog uses is wired (hooks fire only after !join anyway).
        runtime = SessionRuntime(self._config)
        await self.add_cog(VoiceCog(self, runtime))
        await self.add_cog(DiceCog(self, runtime))
        await self.add_cog(DMCog(self, runtime))
        await self.add_cog(SceneCog(self, runtime))
        await self.add_cog(LoreCog(self, runtime))

    async def on_ready(self) -> None:
        log.info("logged in as %s (id=%s)", self.user, self.user and self.user.id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # DMbot shares the "!" prefix with the music bot; silently ignore commands it doesn't
        # own (e.g. !play) instead of spamming CommandNotFound.
        if isinstance(error, commands.CommandNotFound):
            return
        log.error("command error in %r: %r", getattr(ctx, "command", None), error)

    async def close(self) -> None:
        """Step-wise teardown with an `[i/n]` console display (dmbot.shutdown.progress), so the
        operator sees what is being shut down, how many steps remain, and which one is slow —
        the bare dots animation hid all of that. Voice disconnects + cog teardown are pulled in
        front of ``super().close()`` so each gets its own counted step; the cogs report their
        own substeps (``TEARDOWN_STEPS``)."""
        if self.is_closed():
            return
        voice = list(self.voice_clients)
        cog_steps = sum(getattr(c, "TEARDOWN_STEPS", 0) for c in self.cogs.values())
        progress.begin(len(voice) + cog_steps + 1)
        for vc in voice:
            with progress.step(f"Voice-Channel verlassen ({getattr(vc, 'channel', '?')})"):
                try:
                    # disconnect_voice bounds discord.py's post-leave confirmation wait (up to
                    # VoiceClient.timeout=30s) — moot at exit, and the cause of the slow leave.
                    if not await disconnect_voice(vc):
                        log.warning("voice confirm wait abandoned at shutdown (already left)")
                except Exception:
                    log.exception("voice disconnect failed (continuing shutdown)")
        for name in list(self.cogs):
            try:
                await self.remove_cog(name)  # runs the cog's cog_unload → its progress steps
            except Exception:
                log.exception("cog teardown failed (continuing shutdown)")
        with progress.step("Discord-Verbindung schließen (Gateway + HTTP)"):
            await super().close()
        progress.finish()


_YELLOW = "\033[93m"
_RED = "\033[91m"
_RESET = "\033[0m"


def _install_sigint_guard() -> None:
    """Two-stage Ctrl+C: the **first** press asks ("Quit?") and keeps running, the **second**
    shuts down. discord.py 2.7.1's ``run()`` installs no SIGINT handler (verified), so ours stays
    in effect; the second press raises ``KeyboardInterrupt``, which ``run()`` catches and tears
    down cleanly (``DMBot.close()`` → per-step progress display → cog teardown). Avoids killing
    a session on a single fat-fingered Ctrl+C.
    """
    armed = {"v": False}

    def _handler(signum, frame) -> None:
        if not armed["v"]:
            armed["v"] = True
            print(f"\n{_YELLOW}Quit? Nochmal Strg+C zum Beenden.{_RESET}", flush=True)
            return
        print(f"\n{_RED}Shutting down …{_RESET}", flush=True)  # instant; close() lists the steps
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
