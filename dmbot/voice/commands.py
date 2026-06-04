"""Discord commands to drive Phase 2 voice receive.

`!join`  — join the caller's voice channel and start the per-user VAD pipeline.
`!leave` — stop listening, print per-user totals, disconnect.
`!vstatus` — connection / listening / Opus state.

Foreign voice-recv wiring stays inside ``voice/`` (CLAUDE.md). Bot replies are German
(seen in Discord); logs are English.
"""

from __future__ import annotations

import logging
import os
import tempfile
import wave

import discord
from discord.ext import commands, voice_recv

from .recv import VadSink
from ..stt import Transcriber

log = logging.getLogger(__name__)

_SR_16K = 16_000


def _write_utterance_wav(name: str, index: int, pcm_s16le_mono_16k: bytes) -> str:
    """Write one utterance to a 16 kHz mono WAV in the OS temp dir (Phase-3 inspection).

    Uses ``tempfile.gettempdir()`` — never ``/tmp`` (Windows runtime, CLAUDE.md).
    """
    safe = "".join(c if c.isalnum() else "_" for c in name) or "user"
    path = os.path.join(tempfile.gettempdir(), f"dm_utt_{safe}_{index:03d}.wav")
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # s16le
        wav.setframerate(_SR_16K)
        wav.writeframes(pcm_s16le_mono_16k)
    return path


class VoiceReceiveCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        bot_a_user_id: int | None = None,
        whisper_model: str = "small",
        whisper_device: str = "cuda",
        whisper_compute: str = "float16",
    ) -> None:
        self.bot = bot
        self._bot_a_user_id = bot_a_user_id
        self._utterance_counts: dict[int, int] = {}
        # STT worker (Phase 4): loads faster-whisper in its own thread, transcribes off the
        # audio path. Started here so a broken cuDNN surfaces at boot, not on first utterance.
        self._transcriber = Transcriber(
            self._on_transcript,
            model=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute,
        )
        self._transcriber.start()

    def _on_utterance(self, user_id: int, name: str, pcm: bytes, duration_s: float) -> None:
        """Per cut utterance (voice-recv reader / silence-gen thread): dump a WAV for
        inspection and hand the PCM to the STT worker. Keep it light, never raise.
        """
        n = self._utterance_counts.get(user_id, 0) + 1
        self._utterance_counts[user_id] = n
        try:
            path = _write_utterance_wav(name, n, pcm)
        except Exception:
            log.exception("failed to write utterance WAV")
            path = "<unwritten>"
        log.info(
            "🗣 utterance #%d from %s — %.2fs (%d KiB) → %s",
            n, name, duration_s, len(pcm) // 1024, path,
        )
        self._transcriber.submit(name, pcm)  # transcription happens on the STT worker thread

    def _on_transcript(self, name: str, text: str) -> None:
        """STT result (on the STT worker thread). Phase-4 gate: surface the German text."""
        log.info("📝 %s: %s", name, text)

    async def cog_unload(self) -> None:
        self._transcriber.stop()

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
        # Wrap the VAD sink in voice-recv's SilenceGeneratorSink: Discord clients send no
        # packets at all while a user is silent (voice activation), so without injected silence
        # the segmenter never sees an utterance's trailing gap and can't close it. The wrapper
        # feeds synthetic silence frames during transmission downtime (cleanup propagates to the
        # child automatically — reader walks the sink tree).
        vad_sink = VadSink(
            bot_a_user_id=self._bot_a_user_id, on_utterance=self._on_utterance
        )
        sink = voice_recv.SilenceGeneratorSink(vad_sink)
        vc.listen(sink, after=self._on_listen_done)

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero)",
            channel.name, channel.id,
        )
        await ctx.send(
            f"Beigetreten: **{channel.name}** — höre zu, VAD segmentiert Utterances "
            f"(WAVs im Temp-Ordner). (Opus geladen: {discord.opus.is_loaded()})"
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
