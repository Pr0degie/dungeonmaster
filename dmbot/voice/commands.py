"""Discord commands to drive Phase 2 voice receive.

`!join`  — join the caller's voice channel and start the per-user PCM sink.
`!leave` — stop listening, print per-user totals, disconnect.
`!vstatus` — connection / listening / Opus state.

Foreign voice-recv wiring stays inside ``voice/`` (CLAUDE.md). Bot replies are German
(seen in Discord); logs are English.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, voice_recv

from .recv import PcmLogSink

log = logging.getLogger(__name__)


class VoiceReceiveCog(commands.Cog):
    def __init__(self, bot: commands.Bot, *, bot_a_user_id: int | None = None) -> None:
        self.bot = bot
        self._bot_a_user_id = bot_a_user_id

    @commands.command(name="join", aliases=["j"])
    async def join(self, ctx: commands.Context) -> None:
        """Join the caller's voice channel and start logging per-user PCM. Alias: !j"""
        voice_state = ctx.author.voice
        if voice_state is None or voice_state.channel is None:
            await ctx.send("Du bist in keinem Voice-Channel — tritt erst einem bei.")
            return

        if ctx.voice_client is not None:
            await ctx.send("Ich bin schon in einem Voice-Channel. Nutze zuerst `!leave`.")
            return

        channel = voice_state.channel
        vc: voice_recv.VoiceRecvClient = await channel.connect(
            cls=voice_recv.VoiceRecvClient
        )
        sink = PcmLogSink(bot_a_user_id=self._bot_a_user_id)
        vc.listen(sink, after=self._on_listen_done)

        log.info("joined voice '%s' (id=%s) and started PCM sink", channel.name, channel.id)
        await ctx.send(
            f"Beigetreten: **{channel.name}** — höre zu, PCM-Log läuft. "
            f"(Opus geladen: {discord.opus.is_loaded()})"
        )

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context) -> None:
        """Stop listening and leave the voice channel."""
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("Ich bin in keinem Voice-Channel.")
            return
        if isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening():
            vc.stop_listening()
        await vc.disconnect()
        await ctx.send("Voice-Channel verlassen.")

    @commands.command(name="vstatus")
    async def vstatus(self, ctx: commands.Context) -> None:
        """Report connection / listening / Opus state."""
        vc = ctx.voice_client
        connected = vc is not None and vc.is_connected()
        listening = isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening()
        await ctx.send(
            f"connected={connected} listening={listening} "
            f"opus={discord.opus.is_loaded()}"
        )

    @staticmethod
    def _on_listen_done(exc: Exception | None) -> None:
        # Called from the reader thread when listening stops.
        if exc is not None:
            log.error("voice reader stopped with error: %r", exc)
        else:
            log.info("voice reader stopped cleanly")
