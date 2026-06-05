"""Discord commands to drive Phase 2 voice receive.

`!join`  — join the caller's voice channel and start the per-user VAD pipeline.
`!leave` — stop listening, print per-user totals, disconnect.
`!vstatus` — connection / listening / Opus state.

Foreign voice-recv wiring stays inside ``voice/`` (CLAUDE.md). Bot replies are German
(seen in Discord); logs are English.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import wave

import discord
from discord.ext import commands, voice_recv

from .recv import VadSink
from .preflight import check_dave_session, check_static
from ..stt import Transcriber
from ..llm.client import OllamaClient
from ..orchestrator import DMBrain
from ..tts.piper import PiperTTS
from ..bridge import BridgeClient

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
        whisper_model: str = "medium",
        whisper_device: str = "cuda",
        whisper_compute: str = "float16",
        dump_utterances: bool = False,
        ollama_host: str = "http://127.0.0.1:11434",
        ollama_model: str = "mistral-nemo",
        dm_num_predict: int = 220,
        tts_engine: str = "piper",
        tts_voice: str = "",
        tts_speaker: str = "",
        tts_device: str = "cpu",
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 8765,
    ) -> None:
        self.bot = bot
        # Preflight the version-sensitive voice stack at boot, so a drift surfaces as a loud
        # warning here instead of as a silent garbage transcript mid-session (ADR 006).
        check_static()
        self._bot_a_user_id = bot_a_user_id
        self._dump_utterances = dump_utterances
        self._utterance_counts: dict[int, int] = {}
        self._active_vc_id: int | None = None  # the voice channel we buffer/answer for
        self._brain = DMBrain(OllamaClient(ollama_host, ollama_model), num_predict=dm_num_predict)
        self._bridge = BridgeClient(bridge_host, bridge_port)
        # Load the TTS backend once. xtts is imported lazily so Piper users don't pull torch.
        # If loading fails, keep running text-only (answers still post, just aren't spoken).
        self._tts = None
        try:
            if tts_engine == "xtts":
                from ..tts.xtts import XttsTTS  # heavy import (torch) — only when selected

                self._tts = XttsTTS(tts_speaker, device=tts_device)
            else:
                self._tts = PiperTTS(tts_voice) if tts_voice else PiperTTS()
        except Exception:
            log.exception("TTS unavailable (%s) — DM answers won't be spoken", tts_engine)
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
        """Per cut utterance (voice-recv reader / silence-gen thread): hand the PCM to the STT
        worker (and optionally dump a WAV for debugging). Keep it light, never raise.
        """
        n = self._utterance_counts.get(user_id, 0) + 1
        self._utterance_counts[user_id] = n
        if self._dump_utterances:  # debug only — off by default so temp doesn't fill up
            try:
                path = _write_utterance_wav(name, n, pcm)
                log.debug("dumped %s utterance #%d (%.2fs) → %s", name, n, duration_s, path)
            except Exception:
                log.exception("failed to write utterance WAV")
        # The metric (clip length · transcribe ms) is logged with the transcript once STT
        # returns — see _on_transcript. clip length is passed through for that line.
        self._transcriber.submit(name, pcm, duration_s)

    def _on_transcript(
        self, name: str, text: str, clip_s: float, latency_ms: float
    ) -> None:
        """STT result (on the STT worker thread). Phase-4 gate: the German text, with the
        clip length and the transcription response time (ms) right next to it.
        """
        # "📝 name | clip·ms | text" — the console formatter renders the metric dim inline;
        # the file log keeps the same one-line, greppable form.
        log.info("📝 %s | %.1fs·%dms | %s", name, clip_s, round(latency_ms), text)
        # Buffer the line for the next DM turn (triggered by !dm). Runs on the STT thread;
        # the brain's buffer is lock-guarded.
        if self._active_vc_id is not None:
            self._brain.add_player_line(self._active_vc_id, name, text)

    async def cog_unload(self) -> None:
        self._transcriber.stop()
        await self._brain.aclose()
        await self._bridge.aclose()

    async def _speak(self, text: str, guild_id: int | None) -> None:
        """Synthesise ``text`` with Piper and play it via Bot A's /speak bridge.

        Synthesis is blocking, so it runs in a thread. The WAV is deleted after playback so the
        temp dir doesn't fill up. Bot A's audio is filtered by user-ID (feedback layer 1), so
        DMbot does not transcribe its own DM voice even without pausing the VAD.
        """
        if self._tts is None:
            return
        try:
            t0 = time.perf_counter()
            wav = await asyncio.to_thread(self._tts.synthesize, text)
            log.info("🔊 TTS %d ms → speaking", round((time.perf_counter() - t0) * 1000))
        except Exception:
            log.exception("TTS synthesis failed")
            return
        try:
            if not await self._bridge.speak(wav, guild_id=guild_id):
                log.warning("playback did not succeed — is Bot A in the voice channel?")
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass

    @commands.command(name="dm")
    async def dm(self, ctx: commands.Context, *, text: str = "") -> None:
        """Run a DM turn. `!dm` answers the buffered voice lines; `!dm <Text>` answers text."""
        channel_id = self._active_vc_id if self._active_vc_id is not None else ctx.channel.id
        if not text and self._brain.pending_count(channel_id) == 0:
            await ctx.send(
                "Nichts zu beantworten — sprecht etwas (nach `!j`) oder nutzt `!dm <Text>`."
            )
            return
        try:
            async with ctx.typing():
                t0 = time.perf_counter()
                answer = await self._brain.respond(channel_id, extra_text=text or None)
                llm_ms = round((time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("DM turn failed")
            await ctx.send("(Der Spielleiter schweigt — Fehler bei der Antwort, siehe Log.)")
            return
        if not answer:
            await ctx.send("(Nichts zu beantworten.)")
            return
        log.info("🎭 %s", answer)  # rendered prominently in the console
        log.info("⏱ LLM %d ms", llm_ms)
        await ctx.send(answer)
        await self._speak(answer, ctx.guild.id if ctx.guild else None)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Speak arbitrary text through Piper + Bot A — a TTS/bridge smoke test."""
        if self._tts is None:
            await ctx.send("Keine Piper-Stimme geladen (siehe SETUP B5).")
            return
        await self._speak(text, ctx.guild.id if ctx.guild else None)
        await ctx.send("🔊")

    @commands.command(name="voice")
    async def voice(self, ctx: commands.Context, *, name: str = "") -> None:
        """Switch the XTTS speaker live: `!voice Dionisio Schuyler`. No arg → show current."""
        if not hasattr(self._tts, "set_speaker"):
            await ctx.send("Sprecher-Wechsel geht nur mit `TTS_ENGINE=xtts`.")
            return
        if not name:
            await ctx.send(f"Aktueller Sprecher: **{self._tts.speaker}**")
            return
        if self._tts.set_speaker(name):
            await ctx.send(f"Sprecher → **{name}**. Teste mit `!say …`.")
        else:
            await ctx.send(f"Unbekannter Sprecher `{name}`. Liste: `!voices`.")

    @commands.command(name="voices")
    async def voices(self, ctx: commands.Context) -> None:
        """List the XTTS built-in speakers."""
        if not hasattr(self._tts, "speakers"):
            await ctx.send("Nur mit `TTS_ENGINE=xtts` verfügbar.")
            return
        names = ", ".join(self._tts.speakers())
        await ctx.send(f"**XTTS-Sprecher:**\n{names[:1900]}")

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
        # Confirm the live DAVE-decrypt path (ADR 006) is reachable on this client before we
        # start listening — an early, explicit signal if a discord.py upgrade moved the internal.
        check_dave_session(vc)
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
        self._active_vc_id = channel.id  # buffer transcripts + answer for this channel

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero)",
            channel.name, channel.id,
        )
        await ctx.send(
            f"Beigetreten: **{channel.name}** — ich höre zu. Sprecht, dann `!dm` für die "
            f"Antwort der Spielleitung (oder `!dm <Text>`). (Opus: {discord.opus.is_loaded()})"
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
        self._active_vc_id = None
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
