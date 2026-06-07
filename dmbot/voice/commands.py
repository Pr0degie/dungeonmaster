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
import random
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
from ..discord_ui.dice import DiceTestView
from ..discord_ui.turnorder import TurnOrderView
from ..rules import engine, profile as profile_mod
from ..rules.profile import ProfileError, SystemProfile
from ..rules.characters import CharacterStore, resolve_target
from ..rules.marker import TestRequest, extract_tests

# Repo data dir (data/systems is the profile root; sessions/ sits beside it).
_DATA_DIR = profile_mod.systems_dir().parent

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
        system: str = "imperium_maledictum",
        push_to_talk: bool = True,
        pause_vad_while_speaking: bool = False,
        button_autosend: bool = True,
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
        # Release the mic button → auto-run the DM turn (no separate !dm). On by default; the turn
        # waits for the just-said utterances to transcribe first. DM_BUTTON_AUTOSEND=0 disables it.
        self._button_autosend = push_to_talk and button_autosend
        # Rules engine (Phase 8): load the active system profile (data/systems/<system>.json). A
        # missing/broken profile must not down the bot — log loudly and run rules-less (no dice).
        self._profile: SystemProfile | None = None
        try:
            self._profile = profile_mod.load(system)
            log.info("loaded system profile %r (%s, %s)", self._profile.name,
                     self._profile.dice, self._profile.resolution)
        except ProfileError:
            log.exception("no usable system profile %r — running without the dice engine", system)
        # Characters: start from the example party so !test/!roll work out of the box; !join prefers
        # a channel-specific data/sessions/<id>/characters.json if present. Engine rolls (RNG) here.
        self._characters: CharacterStore | None = self._load_characters(None)
        self._rng = random.Random()  # production RNG (tests pass their own seeded Random)
        # Turn order ("whose turn"), seeded from the voice-channel members at !join (keyed by the
        # active voice-channel id, like the brain's buffers). The view rotates the index.
        self._turn_order: dict[int, list[str]] = {}
        self._turn_index: dict[int, int] = {}
        self._turn_message: discord.Message | None = None
        self._brain = DMBrain(
            OllamaClient(ollama_host, ollama_model),
            profile=self._profile,
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

    async def _send_with_retry(self, channel, content: str, *, view: discord.ui.View | None = None):
        """Send a message, retrying once on a transient Discord 5xx (e.g. the 503 seen mid-session)."""
        kwargs = {"view": view} if view is not None else {}
        try:
            return await channel.send(content, **kwargs)
        except discord.HTTPException as exc:
            if (getattr(exc, "status", 0) or 0) < 500:
                raise
            log.warning("Discord send failed (HTTP %s) — retrying once", getattr(exc, "status", "?"))
            await asyncio.sleep(1.0)
            try:
                return await channel.send(content, **kwargs)
            except discord.HTTPException:
                log.warning("Discord send retry also failed — dropping the message", exc_info=True)
                return None

    async def _deliver_answer(self, channel, guild_id: int | None, answer: str, llm_ms: int,
                              *, redo: bool = False) -> None:
        """Log, post (5xx-resilient), speak, and re-anchor the mic button — shared by all turns."""
        log.info("🎭 %s", answer)  # rendered prominently in the console
        log.info("⏱ LLM %d ms%s", llm_ms, " (redo)" if redo else "")
        await self._send_with_retry(channel, answer)
        await self._speak(answer, guild_id)
        # A test the DM requested via <<TEST …>> → post its dice button (before the mic re-anchor
        # so the mic button stays at the very bottom).
        await self._post_pending_dice(channel)
        # Keep the mic button reachable: move it back to the bottom after the message + speech.
        if self._push_to_talk and self._sink is not None:
            await self._post_mic_button(channel)

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
        await self._deliver_answer(ctx.channel, ctx.guild.id if ctx.guild else None, answer, llm_ms)

    @commands.command(name="redo", aliases=["r"])
    async def redo(self, ctx: commands.Context) -> None:
        """Re-run the last DM turn with the same input — for when the DM misunderstood. Alias: !r"""
        channel_id = self._active_vc_id if self._active_vc_id is not None else ctx.channel.id
        try:
            async with ctx.typing():
                t0 = time.perf_counter()
                answer = await self._brain.redo(channel_id)
                llm_ms = round((time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("DM redo failed")
            await ctx.send("(Fehler beim Neu-Erzählen, siehe Log.)")
            return
        if not answer:
            await ctx.send("Nichts zum Wiederholen — erst eine Runde mit `!dm` spielen.")
            return
        await self._deliver_answer(
            ctx.channel, ctx.guild.id if ctx.guild else None, answer, llm_ms, redo=True
        )

    async def _auto_dm_turn(self, channel, guild_id: int | None) -> None:
        """Auto-trigger a DM turn when the mic button is released (push-to-talk). Waits for the
        just-said utterances to finish transcribing (so the last thing said is included), then
        answers if anything was routed to the DM. Silent no-op when nothing was — no nagging."""
        channel_id = self._active_vc_id if self._active_vc_id is not None else channel.id
        await asyncio.to_thread(self._transcriber.wait_idle, 4.0)  # let the final utterance land
        if self._brain.pending_count(channel_id) == 0:
            return
        try:
            t0 = time.perf_counter()
            answer = await self._brain.respond(channel_id)
            llm_ms = round((time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("DM turn failed (auto)")
            await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer:
            await self._deliver_answer(channel, guild_id, answer, llm_ms)

    async def _on_mic_stop(self, interaction: discord.Interaction) -> None:
        """Mic button released → optionally run the DM turn automatically (players asked for this)."""
        if not self._button_autosend:
            return
        try:
            await self._auto_dm_turn(interaction.channel, interaction.guild_id)
        except Exception:
            log.exception("auto DM turn after mic release failed")

    # ----- Phase 8: dice engine, marker flow & turn order --------------------------------

    def _brain_channel(self, channel) -> int:
        """The id the brain/turn-state are keyed by — the active voice channel, text channel as
        fallback (matches the existing !dm/!redo convention)."""
        return self._active_vc_id if self._active_vc_id is not None else channel.id

    def _load_characters(self, channel_id: int | None) -> CharacterStore:
        """Load the party JSON: a channel-specific sheet if present, else the example party.
        A missing file yields an empty store (the engine then rolls without a target)."""
        sessions = _DATA_DIR / "sessions"
        if channel_id is not None:
            specific = sessions / str(channel_id) / "characters.json"
            if specific.is_file():
                log.info("loaded characters from %s", specific)
                return CharacterStore.load(specific)
        return CharacterStore.load(sessions / "_example" / "characters.json")

    async def _run_and_deliver(self, channel, guild_id: int | None) -> None:
        """Run a DM turn and deliver it — used after a dice roll feeds its result back in so the
        DM narrates the consequence (architecture §9)."""
        try:
            t0 = time.perf_counter()
            answer = await self._brain.respond(self._brain_channel(channel))
            llm_ms = round((time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("DM turn failed (after roll)")
            await self._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer:
            await self._deliver_answer(channel, guild_id, answer, llm_ms)

    async def _post_pending_dice(self, channel) -> None:
        """Post a dice button for each test the last DM turn requested via a <<TEST …>> marker."""
        if self._profile is None:
            return
        for req in self._brain.take_pending_tests(self._brain_channel(channel)):
            await self._post_dice_button(channel, req)

    async def _post_dice_button(self, channel, req: TestRequest) -> None:
        """Resolve a test request (skill value + difficulty → target, all in code) and post its button."""
        skill = req.skill or "Probe"
        resolved = resolve_target(
            self._profile, self._characters, skill=skill,
            target_name=req.target_name, difficulty=req.difficulty, modifier=req.modifier,
        )
        who = (resolved.character.name if resolved.character else req.target_name) or "Gruppe"
        if resolved.difficulty:
            diff = resolved.difficulty
        elif req.modifier is not None:
            diff = f"{req.modifier:+d}"
        else:
            diff = ""
        label = f"{who} würfelt: {skill}" + (f" ({diff})" if diff else "")
        note = "" if req.parsed else " (unklarer Marker — manuell prüfen)"
        await self._send_with_retry(
            channel, f"🎲 Probe angefordert{note}:",
            view=DiceTestView(label, self._make_dice_roll(channel, req, resolved)),
        )

    def _make_dice_roll(self, channel, req: TestRequest, resolved):
        """Build the roll callback for a dice button: the engine rolls + resolves, the message is
        replaced with the result, and it's fed back so the DM narrates the consequence."""
        skill = req.skill or "Probe"
        who = resolved.character.name if resolved.character else req.target_name

        async def _roll(interaction: discord.Interaction) -> None:
            if resolved.target is None:  # no character/skill value — roll, ask them to compare
                d = engine.roll(self._profile.dice, self._rng)
                line = f"🎲 {skill}: {d.total} — kein hinterlegter Wert, vergleicht mit eurem Bogen."
            else:
                result = engine.resolve_test(self._profile, resolved.target, self._rng)
                line = engine.describe_result_de(
                    result, skill=skill, character=who, difficulty=resolved.difficulty
                )
            log.info("🎲 %s", line)
            try:
                await interaction.message.edit(content=line, view=None)  # show result, drop button
            except discord.HTTPException:
                await self._send_with_retry(channel, line)
            self._brain.add_test_result(self._brain_channel(channel), line)
            await self._run_and_deliver(channel, channel.guild.id if channel.guild else None)

        return _roll

    def _build_turn_order(self, voice_channel) -> list[str]:
        """Seed the turn order from a voice channel's human members (Bot A + bots filtered),
        preferring each player's character name via the alias map (open item F)."""
        names: list[str] = []
        for m in voice_channel.members:
            if m.bot or (self._bot_a_user_id and m.id == self._bot_a_user_id):
                continue
            char = self._characters.get(m.display_name) if self._characters else None
            names.append(char.name if char else m.display_name)
        return names

    def _render_turn(self, key: int) -> str:
        order = self._turn_order.get(key, [])
        if not order:
            return "Keine Teilnehmer erfasst — tretet dem Voice-Channel bei und nutzt `!turn`."
        i = self._turn_index.get(key, 0) % len(order)
        seq = " → ".join(f"**{n}**" if j == i else n for j, n in enumerate(order))
        return f"🗡 Dran: **{order[i]}**\n{seq}"

    def _turn_step(self, key: int, step: int) -> None:
        order = self._turn_order.get(key, [])
        if order:
            self._turn_index[key] = (self._turn_index.get(key, 0) + step) % len(order)

    async def _post_turn_order(self, channel) -> None:
        """(Re)post the turn-order panel, deleting the previous one so it doesn't duplicate."""
        key = self._active_vc_id
        if key is None:
            await self._send_with_retry(channel, "Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        if self._turn_message is not None:
            try:
                await self._turn_message.delete()
            except discord.HTTPException:
                pass
            self._turn_message = None

        async def advance() -> None:
            self._turn_step(key, +1)

        async def back() -> None:
            self._turn_step(key, -1)

        view = TurnOrderView(advance, back, lambda: self._render_turn(key))
        self._turn_message = await self._send_with_retry(channel, self._render_turn(key), view=view)

    @commands.command(name="roll")
    async def roll(self, ctx: commands.Context, *, dice: str = "1d100") -> None:
        """Roll raw dice through the engine: `!roll 1d100`, `!roll 2d10+3`. A smoke test."""
        try:
            result = engine.roll(dice, self._rng)
        except engine.DiceError:
            await ctx.send(f"Unverständlicher Würfelausdruck `{dice}` — z. B. `1d100`, `2d10+3`.")
            return
        detail = ""
        if result.dice:
            parts = "+".join(str(d) for d in result.dice)
            if result.modifier:
                parts += f"{result.modifier:+d}"
            detail = f" ({parts})"
        await ctx.send(f"🎲 `{dice}` → **{result.total}**{detail}")

    @commands.command(name="test")
    async def test(self, ctx: commands.Context, *, spec: str = "") -> None:
        """Manually request a test: `!test Wahrnehmung Schwer für Tobi`. Posts a dice button."""
        if self._profile is None:
            await ctx.send("Keine Würfel-Engine geladen (Systemprofil fehlt) — siehe Log.")
            return
        if not spec.strip():
            await ctx.send("Nutzung: `!test <Fertigkeit> [Schwierigkeit] [für <Name>]`.")
            return
        _, reqs = extract_tests(f"<<TEST {spec}>>", self._profile)
        if not reqs:
            await ctx.send("Konnte daraus keine Probe lesen.")
            return
        await self._post_dice_button(ctx.channel, reqs[0])

    @commands.command(name="turn", aliases=["order"])
    async def turn(self, ctx: commands.Context) -> None:
        """Show / rotate the turn order ('whose turn'). Rebuilds it from the voice channel. Alias: !order"""
        if self._active_vc_id is None:
            await ctx.send("Ich bin in keinem Voice-Channel — erst `!j`.")
            return
        vc = ctx.voice_client
        if vc is not None and getattr(vc, "channel", None) is not None:
            self._turn_order[self._active_vc_id] = self._build_turn_order(vc.channel)
            self._turn_index.setdefault(self._active_vc_id, 0)
        await self._post_turn_order(ctx.channel)

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
        # Phase 8: load this channel's party (else the example), wire the "who plays whom" alias
        # hint into the prompt (open item F), and seed the turn order from the voice members.
        self._characters = self._load_characters(channel.id)
        self._brain.set_alias_hint(channel.id, self._characters.alias_hint_de())
        self._turn_order[channel.id] = self._build_turn_order(channel)
        self._turn_index[channel.id] = 0

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero, push_to_talk=%s)",
            channel.name, channel.id, self._push_to_talk,
        )
        if self._push_to_talk:
            close = (
                "wenn ihr fertig seid – **dann antwortet die Spielleitung automatisch** (kein `!dm` nötig)"
                if self._button_autosend
                else "wenn ihr fertig seid (ein Tipp gilt für alle), dann `!dm`"
            )
            await ctx.send(
                f"Beigetreten: **{channel.name}**. Ich schreibe **alles** mit (Protokoll im Log), "
                f"aber nur was im **Knopf-Fenster** gesagt wird, geht an die Spielleitung: tippt den "
                f"Knopf *bevor* ihr mit ihr redet und nochmal, {close}. "
                f"(Opus: {discord.opus.is_loaded()})"
            )
            await self._post_turn_order(ctx.channel)  # before the mic button so mic stays at bottom
            await self._post_mic_button(ctx.channel)
        else:
            await ctx.send(
                f"Beigetreten: **{channel.name}** — ich höre durchgehend zu, alles geht an die "
                f"Spielleitung. Sprecht, dann `!dm` (oder `!dm <Text>`). (Opus: {discord.opus.is_loaded()})"
            )
            await self._post_turn_order(ctx.channel)

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
        view = MicToggleView(
            self.toggle_listening, listening=self._dm_listening, on_stop=self._on_mic_stop
        )
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
            self._turn_order.pop(self._active_vc_id, None)
            self._turn_index.pop(self._active_vc_id, None)
        self._active_vc_id = None
        self._sink = None
        self._utterance_counts.clear()
        self._dm_listening = not self._push_to_talk  # reset the routing gate for the next session
        for msg_attr in ("_mic_message", "_turn_message"):
            msg = getattr(self, msg_attr)
            if msg is not None:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass
                setattr(self, msg_attr, None)
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
