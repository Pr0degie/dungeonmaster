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
from ..discord_ui.mic import MicToggleView

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
        dm_max_lines: int = 8,
        push_to_talk: bool = True,
        pause_vad_while_speaking: bool = False,
        tts_engine: str = "piper",
        tts_voice: str = "",
        tts_speaker: str = "",
        tts_device: str = "cpu",
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 8765,
        bridge_secret: str = "",
    ) -> None:
        self.bot = bot
        # Preflight the version-sensitive voice stack at boot, so a drift surfaces as a loud
        # warning here instead of as a silent garbage transcript mid-session (ADR 006).
        check_static()
        self._bot_a_user_id = bot_a_user_id
        self._dump_utterances = dump_utterances
        self._utterance_counts: dict[int, int] = {}
        self._active_vc_id: int | None = None  # the voice channel we buffer/answer for
        self._sink: VadSink | None = None  # set on join; muted while Bot A speaks (layer 2)
        self._mic_message: discord.Message | None = None  # the live mic button msg (kept at bottom)
        self._push_to_talk = push_to_talk
        # Push-to-talk DM-routing gate: the whole table is always transcribed + logged, but only
        # utterances captured while this is True are buffered for the DM. The mic button flips it.
        # With push-to-talk off it's always True (legacy: everything reaches the DM).
        self._dm_listening = not push_to_talk
        # Layer-2 feedback pause (opt-in, off by default): pause the VAD while Bot A speaks. Off so
        # the table keeps being transcribed during narration; layer 1 still blocks self-hearing.
        self._pause_vad_while_speaking = pause_vad_while_speaking
        self._brain = DMBrain(
            OllamaClient(ollama_host, ollama_model),
            num_predict=dm_num_predict,
            max_buffer_lines=dm_max_lines,
        )
        self._bridge = BridgeClient(bridge_host, bridge_port, secret=bridge_secret)
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
        # Tag the utterance with the DM-routing gate state NOW (when it was cut), so the routing
        # decision reflects whether the button was engaged while it was spoken — not whenever the
        # async transcript happens to come back. The metric (clip · transcribe ms) is logged with
        # the transcript once STT returns (see _on_transcript).
        self._transcriber.submit(name, pcm, duration_s, for_dm=self._dm_listening)

    def _on_transcript(
        self, name: str, text: str, clip_s: float, latency_ms: float, for_dm: bool
    ) -> None:
        """STT result (on the STT worker thread). The German text with clip length + transcribe ms.

        The whole table is logged (full transcript record); only ``for_dm`` lines are buffered for
        the next DM turn — that is the push-to-talk gate (everything recorded, button picks what
        the DM hears). A ``→DM`` marker on the metric shows which lines were routed.
        """
        # "📝 name | clip·ms[ →DM] | text" — the console formatter renders the metric dim inline;
        # the file log keeps the same one-line, greppable form.
        marker = " →DM" if for_dm else ""
        log.info("📝 %s | %.1fs·%dms%s | %s", name, clip_s, round(latency_ms), marker, text)
        # Buffer the line for the next DM turn (triggered by !dm) only when routed. Runs on the STT
        # thread; the brain's buffer is lock-guarded.
        if for_dm and self._active_vc_id is not None:
            self._brain.add_player_line(self._active_vc_id, name, text)

    async def cog_unload(self) -> None:
        # stop() does a (short) thread.join — run it off the event loop so the gateway heartbeat
        # keeps beating during shutdown (otherwise Ctrl+C logs "voice heartbeat blocked").
        await asyncio.to_thread(self._transcriber.stop)
        await self._brain.aclose()
        await self._bridge.aclose()

    async def _speak(self, text: str, guild_id: int | None) -> bool:
        """Synthesise ``text`` and play it via Bot A's /speak bridge. Returns True if it played.

        Synthesis is blocking, so it runs in a thread. The WAV is deleted after playback so the
        temp dir doesn't fill up. Bot A's audio is filtered by user-ID (feedback layer 1), so
        DMbot does not transcribe its own DM voice even without pausing the VAD.
        """
        if self._tts is None:
            return False
        try:
            t0 = time.perf_counter()
            wav = await asyncio.to_thread(self._tts.synthesize, text)
            log.info("🔊 TTS %d ms → speaking", round((time.perf_counter() - t0) * 1000))
        except Exception:
            log.exception("TTS synthesis failed")
            return False
        # Feedback protection layer 2 (ADR 003), now OPT-IN and off by default: pause the VAD while
        # Bot A speaks. It's redundant in normal use — layer 1 (the Bot-A user-ID filter, golden
        # rule #4, always on) already keeps the DM from transcribing its own voice, and the
        # push-to-talk routing gate keeps narration-time table talk out of the DM. We default it off
        # so the table keeps being transcribed (full transcript record) while the DM talks. Enable
        # DM_PAUSE_VAD_WHILE_SPEAKING=1 to restore the pause. /speak blocks until playback ends
        # (D15), so unmuting in finally reopens exactly when Bot A goes quiet; snapshot the sink so
        # a !leave mid-playback still unmutes the one we muted.
        sink = self._sink if self._pause_vad_while_speaking else None
        if sink is not None:
            sink.mute()
        try:
            played = await self._bridge.speak(wav, guild_id=guild_id)
            if not played:
                log.warning("playback did not succeed — is Bot A in the voice channel?")
            return played
        finally:
            if sink is not None:
                sink.unmute()
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
        # Keep the mic button reachable: move it back to the bottom after the DM's message + speech
        # pushed it up (players asked for this).
        if self._push_to_talk and self._sink is not None:
            await self._post_mic_button(ctx.channel)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Speak arbitrary text through Piper + Bot A — a TTS/bridge smoke test."""
        if self._tts is None:
            await ctx.send("Keine TTS-Stimme geladen (siehe SETUP B5).")
            return
        if await self._speak(text, ctx.guild.id if ctx.guild else None):
            await ctx.send("🔊")
        else:
            await ctx.send(
                "Konnte nicht abspielen — läuft **Bot A** und ist es im selben Voice-Channel? "
                "Prüfe `!vstatus`; Details im Log (`logs/dmbot.log`)."
            )

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
        self._sink = vad_sink  # keep the handle so _speak can mute it while Bot A talks (layer 2)
        self._dm_listening = not self._push_to_talk  # fresh session: gate closed if push-to-talk
        sink = voice_recv.SilenceGeneratorSink(vad_sink)
        vc.listen(sink, after=self._on_listen_done)
        self._active_vc_id = channel.id  # buffer transcripts + answer for this channel

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero, push_to_talk=%s)",
            channel.name, channel.id, self._push_to_talk,
        )
        if self._push_to_talk:
            await ctx.send(
                f"Beigetreten: **{channel.name}**. Ich schreibe **alles** mit (Protokoll im Log), "
                f"aber nur was im **Knopf-Fenster** gesagt wird, geht an die Spielleitung: tippt den "
                f"Knopf *bevor* ihr mit ihr redet und nochmal, wenn ihr fertig seid (ein Tipp gilt "
                f"für alle), dann `!dm`. (Opus: {discord.opus.is_loaded()})"
            )
            await self._post_mic_button(ctx.channel)
        else:
            await ctx.send(
                f"Beigetreten: **{channel.name}** — ich höre durchgehend zu, alles geht an die "
                f"Spielleitung. Sprecht, dann `!dm` (oder `!dm <Text>`). (Opus: {discord.opus.is_loaded()})"
            )

    async def toggle_listening(self) -> bool:
        """Flip the push-to-talk DM-routing gate; return the new state. Called by the mic button.

        Flushes the open utterance **before** flipping, so the trailing thing said right at the
        press is cut now and tagged with the current gate state (on press-off it still counts as
        DM; on press-on the pre-press fragment stays out of the DM). Transcription itself keeps
        running either way — only DM routing toggles."""
        if self._sink is not None:
            self._sink.flush_open()  # cut + tag the trailing utterance under the OLD gate state
        self._dm_listening = not self._dm_listening
        log.info("push-to-talk → %s", "🎙 an die Spielleitung" if self._dm_listening else "⏸ nur Protokoll")
        return self._dm_listening

    async def _post_mic_button(self, channel) -> None:
        """(Re)post the push-to-talk button at the bottom of the text channel, deleting the previous
        one so it doesn't scroll out of reach as the DM talks (players asked for this). Best-effort —
        a failed delete/post never breaks a turn."""
        if self._mic_message is not None:
            try:
                await self._mic_message.delete()
            except discord.HTTPException:
                pass
            self._mic_message = None
        view = MicToggleView(self.toggle_listening, listening=self._dm_listening)
        try:
            self._mic_message = await channel.send("🎙 Push-to-talk:", view=view)
        except discord.HTTPException:
            log.warning("could not post the mic button", exc_info=True)

    @commands.command(name="mic")
    async def mic(self, ctx: commands.Context) -> None:
        """Re-post the push-to-talk button at the bottom (handy if it scrolled out of view)."""
        if self._sink is None:
            await ctx.send("Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        await self._post_mic_button(ctx.channel)

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
        # End the session cleanly: forget this channel's buffered lines + history, drop the sink
        # handle and the per-user counters, so a later !join starts a fresh session (session
        # state is per channel, ADR 003).
        if self._active_vc_id is not None:
            self._brain.reset(self._active_vc_id)
        self._active_vc_id = None
        self._sink = None
        self._utterance_counts.clear()
        self._dm_listening = not self._push_to_talk  # reset the routing gate for the next session
        if self._mic_message is not None:
            try:
                await self._mic_message.delete()
            except discord.HTTPException:
                pass
            self._mic_message = None
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
