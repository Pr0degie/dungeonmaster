"""Discord commands for voice receive: !join / !leave / !vstatus, the mic button, pause control.

Foreign voice-recv wiring stays inside voice/ (CLAUDE.md). Shared state lives on SessionRuntime
(dmbot/runtime.py); cross-cog flow goes through its hooks (ADR 029). Bot replies are German; logs English.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands, voice_recv

from .recv import VadSink
from .preflight import check_dave_session
from ..discord_ui.mic import MicToggleView
from ..discord_ui.pause import PauseToggleView, pause_embed
from ..memory import history as history_store
from ..shutdown import progress
from ..runtime import SessionRuntime

log = logging.getLogger(__name__)


class VoiceCog(commands.Cog):
    # Number of progress.step() calls in cog_unload — DMBot.close() sums this across cogs to
    # announce the total shutdown step count up front. Keep in sync with cog_unload.
    TEARDOWN_STEPS = 4

    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime
        self._esc_task: asyncio.Task | None = None    # terminal Esc listener (Windows)
        self._anim_task: asyncio.Task | None = None   # the animated "paused" box (rich)
        runtime.reanchor_mic = self._post_mic_button  # hook: DMCog re-anchors the mic after a turn

    async def cog_load(self) -> None:
        # Terminal Esc → pause/resume (Variante A). Windows-only (msvcrt); on other platforms the
        # listener no-ops and the Discord ⏸ button still works. Runs for the whole bot lifetime.
        self._esc_task = asyncio.create_task(self._esc_key_listener())

    async def cog_unload(self) -> None:
        with progress.step("STT-Transcriber stoppen (Backlog wird verworfen, max 2s)"):
            for task in (self._esc_task, self._anim_task):
                if task is not None:
                    task.cancel()
            # stop() does a (short) thread.join — run it off the event loop so the gateway
            # heartbeat keeps beating during shutdown (otherwise "voice heartbeat blocked").
            await asyncio.to_thread(self._rt._transcriber.stop)
        with progress.step("LLM-Client (Ollama) schließen"):
            await self._rt._brain.aclose()
        with progress.step("RAG-Retriever schließen"):
            await self._rt._retriever.aclose()
        with progress.step("Bridge zu Bot A schließen"):
            await self._rt._bridge.aclose()

    async def _on_mic_stop(self, interaction: discord.Interaction) -> None:
        """Mic button released → optionally run the DM turn automatically (players asked for this)."""
        if not self._rt._button_autosend:
            return
        try:
            await self._rt.auto_dm_turn(interaction.channel, interaction.guild_id)
        except Exception:
            log.exception("auto DM turn after mic release failed")

    # ----- Pause control: Esc (terminal) + ⏸ button (Discord), one shared state ----------

    async def toggle_pause(self) -> bool:
        """Flip the shared game-pause state; return the new flag. Called by Esc and the ⏸ button."""
        await self.set_paused(not self._rt._paused)
        return self._rt._paused

    async def set_paused(self, value: bool) -> None:
        """Freeze/resume the game. Pause mutes the VAD/STT pipeline (no transcription) and the DM
        turn guards block any answer; resume reverses both. Idempotent. Both surfaces (the terminal
        box and the Discord embed) are re-rendered from this one flag."""
        if value == self._rt._paused:
            return
        self._rt._paused = value
        if value:
            if self._rt._sink is not None:
                self._rt._sink.mute()  # freeze transcription (also flushes the open utterance)
            log.warning("⏸ Spiel pausiert — keine Transkription, der Spielleiter wartet.")
            if self._anim_task is not None and not self._anim_task.done():
                self._anim_task.cancel()
            self._anim_task = asyncio.create_task(self._run_pause_animation())
        else:
            if self._rt._sink is not None:
                self._rt._sink.unmute()  # (no DM turn runs while paused, so this can't fight layer 2)
            log.warning("▶ Spiel fortgesetzt.")
        await self._refresh_pause_panel()

    async def _esc_key_listener(self) -> None:
        """Variante A: poll the DMbot terminal for the Esc key and toggle pause. Non-blocking — it
        only reads a key when one is ready, so it never stalls the discord.py event loop. Windows
        only (``msvcrt``); elsewhere it no-ops (the Discord ⏸ button still works)."""
        try:
            import msvcrt  # Windows console key polling (D16: the runtime is Windows)
        except ImportError:
            return
        log.info("Esc-Taste im Terminal pausiert/setzt das Spiel fort.")
        try:
            while not self.bot.is_closed():
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch == "\x1b":  # Esc
                        await self.toggle_pause()
                    elif ch in ("\x00", "\xe0") and msvcrt.kbhit():
                        msvcrt.getwch()  # swallow the 2nd byte of arrow/function keys
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def _run_pause_animation(self) -> None:
        """Variante A's animated box: a spinning 'PAUSIERT' panel in the DMbot terminal while the
        game is frozen. Best-effort — if rich is missing or the console can't host a live region,
        it just skips (the Discord embed still shows the state). The pipeline is muted while paused,
        so the console is quiet and the box owns the screen cleanly."""
        try:
            from rich.align import Align
            from rich.live import Live
            from rich.panel import Panel
            from rich.spinner import Spinner
        except Exception:
            return
        spinner = Spinner(
            "dots12",
            text="  ⏸  PAUSIERT  —  Esc oder der ⏸-Knopf setzt fort  ",
            style="bold yellow",
        )
        panel = Panel(
            Align.center(spinner), title="[bold]DMbot[/]", border_style="yellow", padding=(1, 6)
        )
        try:
            with Live(panel, refresh_per_second=12, transient=True):
                while self._rt._paused and not self.bot.is_closed():
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.debug("pause animation unavailable", exc_info=True)

    async def _refresh_pause_panel(self) -> None:
        """(Re)render the Discord pause panel (embed + button) to the current state. Posts it if a
        text channel is known and none exists yet, so an Esc-driven pause is also visible in Discord."""
        if self._rt._text_channel is None:
            return
        view = PauseToggleView(self.toggle_pause, paused=self._rt._paused)
        embed = pause_embed(self._rt._paused)
        if self._rt._pause_message is not None:
            try:
                await self._rt._pause_message.edit(embed=embed, view=view)
                return
            except discord.HTTPException:
                self._rt._pause_message = None  # message gone — fall through and re-post
        try:
            self._rt._pause_message = await self._rt._text_channel.send(embed=embed, view=view)
        except discord.HTTPException:
            log.warning("could not post the pause panel", exc_info=True)

    @commands.command(name="pausebutton")
    async def pausebutton(self, ctx: commands.Context) -> None:
        """(Re)post the pause control panel (embed + ⏸ button) at the bottom of the text channel."""
        self._rt._text_channel = ctx.channel
        await self._rt.clear_panel("_pause_message")
        await self._refresh_pause_panel()

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
            bot_a_user_id=self._rt._bot_a_user_id, on_utterance=self._rt._on_utterance
        )
        self._rt._sink = vad_sink  # keep the handle so _speak can mute it while Bot A talks (layer 2)
        self._rt._dm_listening = not self._rt._push_to_talk  # fresh session: gate closed if push-to-talk
        sink = voice_recv.SilenceGeneratorSink(vad_sink)
        vc.listen(sink, after=self._on_listen_done)
        char_fallback = self._rt.seed_session(channel, ctx.channel)

        log.info(
            "joined voice '%s' (id=%s) and started VAD pipeline (16k mono + silero, push_to_talk=%s)",
            channel.name, channel.id, self._rt._push_to_talk,
        )
        if self._rt._push_to_talk:
            close = (
                "wenn ihr fertig seid – **dann antwortet die Spielleitung automatisch** (kein `!dm` nötig)"
                if self._rt._button_autosend
                else "wenn ihr fertig seid (ein Tipp gilt für alle), dann `!dm`"
            )
            await ctx.send(
                f"Beigetreten: **{channel.name}**. Ich schreibe **alles** mit (Protokoll im Log), "
                f"aber nur was im **Knopf-Fenster** gesagt wird, geht an die Spielleitung: tippt den "
                f"Knopf *bevor* ihr mit ihr redet und nochmal, {close}. "
                f"(Opus: {discord.opus.is_loaded()})"
            )
            await self._rt.post_turn_order(ctx.channel)  # before the mic button so mic stays at bottom
            await self._refresh_pause_panel()
            await self._post_mic_button(ctx.channel)
        else:
            await ctx.send(
                f"Beigetreten: **{channel.name}** — ich höre durchgehend zu, alles geht an die "
                f"Spielleitung. Sprecht, dann `!dm` (oder `!dm <Text>`). (Opus: {discord.opus.is_loaded()})"
            )
            await self._rt.post_turn_order(ctx.channel)
            await self._refresh_pause_panel()

        # Name the loaded party — and warn loudly on the example-party fallback (D43): a session
        # in the wrong channel once silently ran Mortn/Seskin/Vask with wrong sheet values, and it
        # only surfaced as "the DM feels broken". Better one loud line than a quiet wrong game.
        party = ", ".join(c.name for c in self._rt._characters.characters())
        if char_fallback:
            log.warning("no characters.json for channel %s — example party loaded (%s)",
                        channel.id, party or "leer")
            await ctx.send(
                f"⚠ **Keine `characters.json` für diesen Channel** — Beispiel-Party geladen "
                f"({party or '—'}). Würfe nutzen die falschen Werte! Lege "
                f"`data/sessions/{channel.id}/characters.json` an (oder spielt im Stamm-Channel)."
            )
        elif party:
            await ctx.send(f"👥 **Party:** {party}")

        # TTS readiness (the backend loads in the background off the boot path): tell the table once
        # if speech is unavailable or still warming up, rather than letting them wonder about silence.
        if not self._rt._tts_enabled:
            await ctx.send("⚠ **Keine Sprachausgabe** — TTS konnte nicht geladen werden; der DM "
                           "antwortet vorerst nur als Text (Details im Log).")
        elif not self._rt._tts_ready.is_set():
            await ctx.send("⏳ Stimme lädt noch — der erste gesprochene Satz kann ein paar "
                           "Sekunden warten.")

        # Announce the loaded adventure + current scene, so the table knows the plot is on rails.
        if self._rt._adventure is not None:
            scene = self._rt._adventure.get_scene(self._rt._state[channel.id].scene_id)
            where = f" — Szene: **{scene.title_de}**" if scene is not None else ""
            await ctx.send(f"📖 **Abenteuer:** {self._rt._adventure.title}{where} "
                           f"(`!szenen` zeigt alle, `!ort <id>` wechselt)")

        # If a recap was stored from a previous session, show it so the table picks up the thread.
        state = self._rt._state.get(channel.id)
        if state is not None and state.recap:
            await ctx.send(f"📜 **Was bisher geschah:** {state.recap}")

    async def toggle_listening(self) -> bool:
        """Flip the push-to-talk DM-routing gate; return the new state. Called by the mic button.

        Flushes the open utterance **before** flipping, so the trailing thing said right at the
        press is cut now and tagged with the current gate state (on press-off it still counts as
        DM; on press-on the pre-press fragment stays out of the DM). Transcription itself keeps
        running either way — only DM routing toggles."""
        if self._rt._sink is not None:
            self._rt._sink.flush_open()  # cut + tag the trailing utterance under the OLD gate state
        self._rt._dm_listening = not self._rt._dm_listening
        log.info("push-to-talk → %s", "🎙 an die Spielleitung" if self._rt._dm_listening else "⏸ nur Protokoll")
        return self._rt._dm_listening

    async def _post_mic_button(self, channel) -> None:
        """(Re)post the push-to-talk button at the bottom of the text channel, deleting the previous
        one so it doesn't scroll out of reach as the DM talks (players asked for this). Best-effort —
        a failed delete/post never breaks a turn."""
        await self._rt.clear_panel("_mic_message")
        view = MicToggleView(
            self.toggle_listening, listening=self._rt._dm_listening, on_stop=self._on_mic_stop
        )
        try:
            self._rt._mic_message = await channel.send("🎙 Push-to-talk:", view=view)
        except discord.HTTPException:
            log.warning("could not post the mic button", exc_info=True)

    @commands.command(name="mic")
    async def mic(self, ctx: commands.Context) -> None:
        """Re-post the push-to-talk button at the bottom (handy if it scrolled out of view)."""
        if self._rt._sink is None:
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
        if self._rt._active_vc_id is not None:
            # Persist the world state one last time (it's saved on every change too) so HP/recap
            # survive into the next session, then drop the in-memory handle for this channel.
            state = self._rt._state.pop(self._rt._active_vc_id, None)
            if state is not None:
                try:
                    state.save(self._rt._state_path(self._rt._active_vc_id))
                except OSError:
                    log.exception("could not persist world state on leave")
            # Rotate the conversation autosave (D41) so the record survives but the next session
            # starts fresh (the in-memory history is cleared by reset() just below).
            if self._rt._autosave:
                try:
                    history_store.rotate(
                        self._rt._history_path(self._rt._active_vc_id),
                        stamp=datetime.now().strftime("%Y%m%d-%H%M%S"),
                    )
                except OSError:
                    log.exception("could not rotate the history autosave on leave")
            self._rt._brain.reset(self._rt._active_vc_id)
            self._rt._turn_order.pop(self._rt._active_vc_id, None)
            self._rt._turn_index.pop(self._rt._active_vc_id, None)
        self._rt._active_vc_id = None
        self._rt._sink = None
        self._rt._utterance_counts.clear()
        self._rt._dm_listening = not self._rt._push_to_talk  # reset the routing gate for the next session
        # Clear any pause: stop the animation, drop the flag (the sink is being dropped anyway).
        self._rt._paused = False
        if self._anim_task is not None and not self._anim_task.done():
            self._anim_task.cancel()
        self._rt._text_channel = None
        for msg_attr in ("_mic_message", "_turn_message", "_pause_message"):
            await self._rt.clear_panel(msg_attr)
        await ctx.send("Voice-Channel verlassen.")

    @commands.command(name="vstatus")
    async def vstatus(self, ctx: commands.Context) -> None:
        """Report connection / listening / Opus state."""
        vc = ctx.voice_client
        connected = vc is not None and vc.is_connected()
        listening = isinstance(vc, voice_recv.VoiceRecvClient) and vc.is_listening()
        await ctx.send(
            f"connected={connected} listening={listening} "
            f"opus={discord.opus.is_loaded()} paused={self._rt._paused}"
        )

    @staticmethod
    def _on_listen_done(exc: Exception | None) -> None:
        # Called from the reader thread when listening stops.
        if exc is not None:
            log.error("voice reader stopped with error: %r", exc)
        else:
            log.info("voice reader stopped cleanly")
