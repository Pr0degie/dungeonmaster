"""Discord commands for the DM turn pipeline: !dm/!redo/!start, streaming+batch delivery, TTS speak,
auto-recap, !wrap, !say/!voice/!voices, scenes (!ort/!szenen/!ortmodus + the <<ORT>> marker), !lore.
Shared state lives on SessionRuntime (dmbot/runtime.py); cross-cog flow goes through its hooks (ADR 029).
Bot replies are German; logs English.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime

import discord
from discord.ext import commands

from ..orchestrator import build_opening_director_msg
from ..tts.textsplit import has_speakable_content
from ..shutdown import to_daemon_thread
from ..discord_ui.scene import SceneChangeView
from ..discord_ui.rules import RulesView
from ..discord_ui.lore_read import LoreReadView
from ..memory import history as history_store
from ..rag.adventure import Scene
from ..rag.lore import available_topics, lore_pages
from ..runtime import (
    SessionRuntime, _TurnTiming, _wav_duration_s, _safe_remove, _TTS_LOAD_TIMEOUT_S, _DATA_DIR,
)

log = logging.getLogger(__name__)


class DMCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime
        runtime.run_and_deliver = self._run_and_deliver  # hook: DiceCog roll callbacks narrate consequence
        runtime.auto_dm_turn = self._auto_dm_turn        # hook: VoiceCog mic release runs a DM turn

    def _synthesize(self, text: str) -> str | None:
        """Synthesise ``text`` to a WAV path, first waiting on the boot-time TTS preload
        (``_tts_ready``) so the very first spoken line waits for the model if it's still loading.
        Runs in a worker thread (``to_daemon_thread``), so the wait never blocks the event loop.
        ``None`` when no backend is available (load failed/timed out)."""
        # Wait for the background load, but with a ceiling: a hung load must degrade to text-only,
        # not freeze every spoken line forever. A normal XTTS load is a few seconds.
        if not self._rt._tts_ready.wait(timeout=_TTS_LOAD_TIMEOUT_S):
            self._rt._tts_enabled = False  # stop trying — later turns skip synth via the guard
            log.error("TTS not ready after %ss — disabling speech (text-only).", _TTS_LOAD_TIMEOUT_S)
            return None
        tts = self._rt._tts
        return tts.synthesize(text) if tts is not None else None

    async def _speak(self, text: str, guild_id: int | None,
                     timing: _TurnTiming | None = None) -> bool:
        """Synthesise ``text`` and play it via Bot A's /speak bridge. Returns True if it played.

        Synthesis is blocking, so it runs in a thread. The WAV is deleted after playback so the
        temp dir doesn't fill up. Bot A's audio is filtered by user-ID (feedback layer 1), so
        DMbot does not transcribe its own DM voice even without pausing the VAD. ``timing`` (when
        a DM turn passes one) collects the tts / wav / bridge_wait stages for the [latency] line.
        """
        if not self._rt._tts_enabled:
            return False
        try:
            t0 = time.perf_counter()
            # Daemon thread, not asyncio.to_thread: a GPU synth in flight at Ctrl+C must not
            # join-block shutdown (the WAV is moot once we're quitting). See dmbot/shutdown.py.
            # _synthesize waits for the boot-time TTS preload inside the thread (never the loop).
            wav = await to_daemon_thread(self._synthesize, text)
            if wav is None:
                return False
            tts_ms = round((time.perf_counter() - t0) * 1000)
            log.info("🔊 TTS %d ms → speaking", tts_ms)
        except Exception:
            log.exception("TTS synthesis failed")
            return False
        if timing is not None:
            timing.tts_ms = tts_ms
            timing.wav_s = _wav_duration_s(wav)
        # Feedback protection layer 2 (ADR 003), now OPT-IN and off by default: pause the VAD while
        # Bot A speaks. It's redundant in normal use — layer 1 (the Bot-A user-ID filter, golden
        # rule #4, always on) already keeps the DM from transcribing its own voice, and the
        # push-to-talk routing gate keeps narration-time table talk out of the DM. We default it off
        # so the table keeps being transcribed (full transcript record) while the DM talks. Enable
        # DM_PAUSE_VAD_WHILE_SPEAKING=1 to restore the pause. /speak blocks until playback ends
        # (D15), so unmuting in finally reopens exactly when Bot A goes quiet; snapshot the sink so
        # a !leave mid-playback still unmutes the one we muted.
        sink = self._rt._sink if self._rt._pause_vad_while_speaking else None
        if sink is not None:
            sink.mute()
        try:
            tb = time.monotonic()
            played = await self._rt._bridge.speak(wav, guild_id=guild_id)
            if timing is not None:
                timing.bridge_ms = round((time.monotonic() - tb) * 1000)
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

    def _begin_turn(self, channel_id: int, *, kind: str = "") -> _TurnTiming:
        """Open a per-turn timing record: bump the turn counter, stamp the trigger, and claim the
        last DM-routed utterance's transcribe ms (the stt stage; None for typed/redo/dice turns)."""
        self._rt._turn_seq += 1
        return _TurnTiming(
            turn=self._rt._turn_seq,
            trigger=time.monotonic(),
            kind=kind,
            stt_ms=self._rt._last_stt_ms.pop(channel_id, None),
        )

    def _use_streaming(self) -> bool:
        """Stream the answer (ADR 017) only when streaming is on AND a TTS backend loaded — a
        text-only run has nothing to stream audio for, so it takes the byte-identical batch path."""
        return self._rt._streaming and self._rt._tts_enabled

    async def _handle_scene(self, channel) -> None:
        """Apply the DM turn's ``<<ORT id>>`` scene marker (auto scene transition, ADR 026): validate
        the target against the adventure and — if it survives — post a confirm button. The move is
        deterministic and human-confirmed (golden rule #3): the model never writes ``scene_id``, it
        only *requests* the move. In ``verbunden`` mode only the current scene's ``leads_to``
        neighbours are accepted; ``frei`` accepts any known scene. An illegal/unknown id is ignored
        and logged, never moved. At most one move per turn (the first request wins). Runs
        concurrently with playback like the dice button."""
        cid = self._rt._brain_channel(channel)
        reqs = self._rt._brain.take_pending_scenes(cid)
        if not reqs or self._rt._adventure is None:
            return
        state = self._rt._state.get(cid)
        if state is None:
            return
        req = reqs[0]  # ≤1 move per turn; ignore any extras the model emitted
        target = self._rt._adventure.resolve_move(state.scene_id, req.scene_id, self._rt._scene_mode)
        if target is None:  # no-op, unknown id, or (in verbunden mode) not a leads_to neighbour
            log.info("🚫 Auto-Szenenwechsel '%s' abgelehnt (Modus '%s', aktuelle Szene '%s')",
                     req.scene_id, self._rt._scene_mode, state.scene_id)
            return
        log.info("📖 Auto-Szenenwechsel vorgeschlagen → %s (%s)", target.id, target.title_de)
        await channel.send(
            f"📖 Szenenwechsel vorgeschlagen: **{target.title_de}** (Teil {target.part}). Wechseln?",
            view=SceneChangeView(target.title_de, target.part, self._make_scene_confirm(channel, target)),
        )

    def _make_scene_confirm(self, channel, scene: Scene):
        """Build the confirm callback for a proposed move to ``scene``: on click, perform the same
        deterministic pointer move ``!ort`` does (``_set_scene`` + persist + prompt refresh) and edit
        the proposal message to reflect it."""
        async def _confirm(interaction: discord.Interaction) -> None:
            cid = self._rt._brain_channel(channel)
            state = self._rt._state.get(cid)
            if state is None:
                return
            moved = self._rt._set_scene(state, scene.id)
            if moved is None:  # the scene vanished between proposal and click — shouldn't happen
                return
            self._rt._persist_and_refresh(channel)
            log.info("scene → %s (%s) [auto, bestätigt]", moved.id, moved.title_de)
            await interaction.edit_original_response(
                content=f"📖 Szene gewechselt: **{moved.title_de}** (Teil {moved.part})."
            )
        return _confirm

    async def _autosave_turn(self, channel, answer: str, *, user_msg: str | None = None,
                             redo: bool = False) -> None:
        """Append the just-completed turn to ``data/sessions/<id>/history.jsonl`` (D41) off the
        event loop, best-effort. World state persists separately (ADR 015); this is the narrative
        thread so a crash doesn't lose the evening's conversation.

        ``user_msg`` must be the value snapshotted at **generation end** (D43): this runs after
        playback, and a dice click during playback starts the next turn, which overwrites the
        brain's mutable ``_last_turn`` — reading it here pairs the wrong user_msg with the answer
        (seen live 2026-06-12 in history.jsonl). The read-now fallback covers legacy callers."""
        if not self._rt._autosave:
            return
        cid = self._rt._brain_channel(channel)
        if user_msg is None:
            user_msg = self._rt._brain.last_user_msg(cid)
        if user_msg is None:
            return
        try:
            await asyncio.to_thread(
                history_store.append_turn, self._rt._history_path(cid),
                ts=datetime.now().isoformat(timespec="seconds"),
                user_msg=user_msg, answer=answer, redo=redo,
            )
        except OSError:
            log.exception("could not autosave the turn history for channel %s", cid)

    async def _deliver_answer(self, channel, guild_id: int | None, answer: str,
                              timing: _TurnTiming) -> None:
        """Batch delivery: log, post (5xx-resilient), then speak and post the dice button
        **concurrently** so the 🎲 appears while the DM speaks (Task 2 / D40), and re-anchor the
        mic button. Closes out the per-turn ``timing`` (tts/bridge via ``_speak``) and emits the
        single ``[latency]`` line once ``/speak`` returned."""
        timing.answer_chars = len(answer)
        # Snapshot the turn's user_msg NOW (generation just ended): a dice click during the
        # playback below starts the next turn and overwrites the brain's _last_turn (D43 race fix).
        saved_user_msg = self._rt._brain.last_user_msg(self._rt._brain_channel(channel))
        if answer:
            log.info("🎭 %s", answer)  # rendered prominently in the console
        log.info("⏱ LLM %d ms%s", timing.respond_ms(), " (redo)" if timing.kind == "redo" else "")
        # A content-less answer (a marker-only turn the model wrapped in a code fence, etc.) must not
        # be posted or spoken — XTTS would read a lone quote for ~15 s. The dice button still posts.
        speakable = has_speakable_content(answer)
        speak_task = None
        if speakable:
            await self._rt._send_with_retry(channel, answer)
            speak_task = asyncio.create_task(self._speak(answer, guild_id, timing))
        else:
            log.info("(inhaltslose Antwort — nichts gepostet/gesprochen; nur ggf. Würfel)")
        dice_task = asyncio.create_task(self._rt.handle_dice(channel))
        scene_task = asyncio.create_task(self._handle_scene(channel))  # ADR 026: propose a scene move
        if speak_task is not None:
            await speak_task
        timing.end = time.monotonic()  # /speak returned → total stops here (mic re-anchor excluded)
        timing.log_line()
        await dice_task  # the dice button must land before the mic button re-anchors at the bottom
        await scene_task  # likewise the scene-change proposal lands before the mic re-anchors
        await self._autosave_turn(channel, answer, user_msg=saved_user_msg,
                                  redo=timing.kind == "redo")
        # Keep the mic button reachable: move it back to the bottom after the message + speech.
        if self._rt._push_to_talk and self._rt._sink is not None:
            await self._rt.reanchor_mic(channel)
        # Rolling auto-recap (D56): if this turn's prompt neared the num_ctx cap, compact the history
        # now — off the hot path (the turn is fully delivered above), so it never adds turn latency.
        await self._maybe_compact(channel, timing)

    async def _deliver_streaming(self, channel, guild_id: int | None, timing: _TurnTiming, *,
                                 redo: bool = False, extra_text: str | None = None,
                                 opening: str | None = None) -> str | None:
        """Streaming delivery (ADR 017): the producer drives the brain's streaming turn while a
        synth→playback pipeline speaks each sentence (synth N+1 while N plays); the Discord text
        post + 🎲 dice button happen at generation-end (mid-playback). Layer-2 mute spans the whole
        answer (not per sentence); pause stops emission cleanly. Returns the stored answer or None."""
        channel_id = self._rt._brain_channel(channel)
        sentence_q: asyncio.Queue = asyncio.Queue()
        wav_q: asyncio.Queue = asyncio.Queue(maxsize=1)  # bounds synth to ~1 ahead of playback
        sink = self._rt._sink if self._rt._pause_vad_while_speaking else None
        holder: dict = {"answer": None}

        async def on_sentence(s: str) -> None:
            await sentence_q.put(s)

        async def producer() -> None:
            try:
                if opening is not None:
                    # !start opening briefing: a GM-side director turn (dice suppressed) — same
                    # stream→speak pipeline, just a different brain entry point.
                    holder["answer"] = await self._rt._brain.respond_opening_streaming(
                        channel_id, opening, on_sentence=on_sentence,
                        should_abort=lambda: self._rt._paused,
                    )
                elif redo:
                    holder["answer"] = await self._rt._brain.redo_streaming(
                        channel_id, on_sentence=on_sentence, should_abort=lambda: self._rt._paused,
                    )
                else:
                    holder["answer"] = await self._rt._brain.respond_streaming(
                        channel_id, extra_text=extra_text, on_sentence=on_sentence,
                        should_abort=lambda: self._rt._paused,
                    )
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
            finally:
                await sentence_q.put(None)  # sentinel: generation finished

        async def synth_worker() -> None:
            while True:
                s = await sentence_q.get()
                if s is None:
                    await wav_q.put(None)
                    return
                if self._rt._paused or not self._rt._tts_enabled:
                    continue
                try:
                    t0 = time.perf_counter()
                    # Daemon thread (see dmbot/shutdown.py): a streamed-sentence synth in flight
                    # at Ctrl+C is abandoned, never join-blocking the shutdown. _synthesize waits
                    # for the boot-time TTS preload inside the thread (never the event loop).
                    wav = await to_daemon_thread(self._synthesize, s)
                    if wav is None:
                        continue
                except Exception:
                    log.exception("TTS synthesis failed (streamed sentence) — skipping it")
                    continue
                timing.tts_ms = (timing.tts_ms or 0) + round((time.perf_counter() - t0) * 1000)
                dur = _wav_duration_s(wav)
                if dur is not None:
                    timing.wav_s = (timing.wav_s or 0.0) + dur
                await wav_q.put(wav)

        async def play_worker() -> None:
            while True:
                wav = await wav_q.get()
                if wav is None:
                    return
                if self._rt._paused:
                    _safe_remove(wav)
                    continue
                if timing.first_audio is None:
                    timing.first_audio = time.monotonic()
                tb = time.monotonic()
                try:
                    await self._rt._bridge.speak(wav, guild_id=guild_id)
                finally:
                    timing.bridge_ms = (timing.bridge_ms or 0) + round((time.monotonic() - tb) * 1000)
                    _safe_remove(wav)

        if sink is not None:
            sink.mute()  # layer 2: stay muted across the WHOLE answer, no flapping between sentences
        prod = asyncio.create_task(producer())
        sw = asyncio.create_task(synth_worker())
        pw = asyncio.create_task(play_worker())
        dice_task: asyncio.Task | None = None
        scene_task: asyncio.Task | None = None
        saved_user_msg: str | None = None
        try:
            try:
                await prod  # generation finished (mid-playback) — the full answer is known now
            except Exception:
                log.exception("streaming producer failed")
            # Snapshot the turn's user_msg NOW: the dice button below can be clicked while the
            # tail still plays, and that next turn overwrites _last_turn (D43 race fix).
            saved_user_msg = self._rt._brain.last_user_msg(channel_id)
            answer = holder["answer"]
            if answer is not None:  # a turn happened ("" = a marker-only/content-less turn)
                timing.answer_chars = len(answer)
                if answer:
                    log.info("🎭 %s", answer)
                log.info("⏱ LLM %d ms%s", timing.respond_ms(),
                         " (redo)" if timing.kind == "redo" else "")
                # Post the text only if there's something to read; the sentences were already
                # filtered for speakability before synthesis. A marker-only turn posts no text but
                # still posts its dice button below.
                if has_speakable_content(answer):
                    await self._rt._send_with_retry(channel, answer)
                dice_task = asyncio.create_task(self._rt.handle_dice(channel))
                scene_task = asyncio.create_task(self._handle_scene(channel))  # ADR 026
            await asyncio.gather(sw, pw)  # wait for the last sentence to finish playing
        finally:
            if sink is not None:
                sink.unmute()
        if holder["answer"] is not None:
            timing.end = time.monotonic()  # last /speak returned
            timing.log_line()
            if dice_task is not None:
                await dice_task
            if scene_task is not None:
                await scene_task
            await self._autosave_turn(channel, holder["answer"], user_msg=saved_user_msg, redo=redo)
            if self._rt._push_to_talk and self._rt._sink is not None:
                await self._rt.reanchor_mic(channel)
            # Rolling auto-recap (D56): same off-hot-path compaction as the batch path — the answer is
            # already spoken (gather(sw, pw) above awaited the last sentence), so no added latency.
            await self._maybe_compact(channel, timing)
        return holder["answer"]

    @commands.command(name="dm")
    async def dm(self, ctx: commands.Context, *, text: str = "") -> None:
        """Run a DM turn. `!dm` answers the buffered voice lines; `!dm <Text>` answers text."""
        if self._rt._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        channel_id = self._rt._active_vc_id if self._rt._active_vc_id is not None else ctx.channel.id
        if not text and self._rt._brain.pending_count(channel_id) == 0:
            await ctx.send(
                "Nichts zu beantworten — sprecht etwas (nach `!j`) oder nutzt `!dm <Text>`."
            )
            return
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._begin_turn(channel_id)
        if self._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._deliver_streaming(
                        ctx.channel, guild_id, timing, extra_text=text or None
                    )
            except Exception:
                log.exception("DM turn failed (stream)")
                await ctx.send("(Der Spielleiter schweigt — Fehler bei der Antwort, siehe Log.)")
                return
            if answer is None:  # None = nothing to respond to; "" = a marker-only turn (dice posted)
                await ctx.send("(Nichts zu beantworten.)")
            return
        try:
            async with ctx.typing():
                answer = await self._rt._brain.respond(channel_id, extra_text=text or None)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed")
            await ctx.send("(Der Spielleiter schweigt — Fehler bei der Antwort, siehe Log.)")
            return
        if answer is None:
            await ctx.send("(Nichts zu beantworten.)")
            return
        await self._deliver_answer(ctx.channel, guild_id, answer, timing)

    @commands.command(name="redo", aliases=["r"])
    async def redo(self, ctx: commands.Context) -> None:
        """Re-run the last DM turn with the same input — for when the DM misunderstood. Alias: !r"""
        if self._rt._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        channel_id = self._rt._active_vc_id if self._rt._active_vc_id is not None else ctx.channel.id
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._begin_turn(channel_id, kind="redo")
        if self._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._deliver_streaming(ctx.channel, guild_id, timing, redo=True)
            except Exception:
                log.exception("DM redo failed (stream)")
                await ctx.send("(Fehler beim Neu-Erzählen, siehe Log.)")
                return
            if answer is None:
                await ctx.send("Nichts zum Wiederholen — erst eine Runde mit `!dm` spielen.")
            return
        try:
            async with ctx.typing():
                answer = await self._rt._brain.redo(channel_id)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("DM redo failed")
            await ctx.send("(Fehler beim Neu-Erzählen, siehe Log.)")
            return
        if answer is None:
            await ctx.send("Nichts zum Wiederholen — erst eine Runde mit `!dm` spielen.")
            return
        await self._deliver_answer(ctx.channel, guild_id, answer, timing)

    @commands.command(name="start", aliases=["briefing", "auftrag"])
    async def start(self, ctx: commands.Context) -> None:
        """`!start` — the DM speaks the opening briefing so the table knows who they are and what
        their mission is. First-session complaint: `!join` only prints status lines and never
        narrates the hook ("hat am Anfang nicht gesagt, was abgeht"). This runs a normal DM turn
        through the existing generate → stream/speak path (so it's spoken like any other line),
        driven by a GM-side *director* instruction (orchestrator.build_opening_director_msg) that
        points the model at the start scene's card. Dice are suppressed for the briefing (the
        opening turn never queues a <<TEST>>, see DMBrain._prepare_opening)."""
        if self._rt._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        cid = self._rt._brain_channel(ctx.channel)
        # Mirror the turn-producing guards: a session must be active (state seeded on !join).
        if self._rt._active_vc_id is None or cid not in self._rt._state:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        # Point the scene pointer at the start scene if it isn't set yet, so the prompt's
        # "## Aktuelle Szene" is the opening scene the briefing should play (deterministic, golden
        # rule #3 — code moves the pointer, not the model). A loaded session keeps its saved pointer.
        if self._rt._adventure is not None and not self._rt._state[cid].scene_id:
            moved = self._rt._set_scene(self._rt._state[cid], self._rt._adventure.start_scene)
            if moved is not None:
                self._rt._persist_and_refresh(ctx.channel)
        director_msg = build_opening_director_msg()
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._begin_turn(cid)
        if self._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._deliver_streaming(
                        ctx.channel, guild_id, timing, opening=director_msg
                    )
            except Exception:
                log.exception("opening briefing failed (stream)")
                await ctx.send("(Der Spielleiter schweigt — Fehler beim Auftakt, siehe Log.)")
                return
            if answer is None:
                await ctx.send("(Kein Auftakt — siehe Log.)")
            return
        try:
            async with ctx.typing():
                answer = await self._rt._brain.respond_opening(cid, director_msg)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("opening briefing failed")
            await ctx.send("(Der Spielleiter schweigt — Fehler beim Auftakt, siehe Log.)")
            return
        if answer is None:
            await ctx.send("(Kein Auftakt — siehe Log.)")
            return
        await self._deliver_answer(ctx.channel, guild_id, answer, timing)

    async def _auto_dm_turn(self, channel, guild_id: int | None) -> None:
        """Auto-trigger a DM turn when the mic button is released (push-to-talk). Waits for the
        just-said utterances to finish transcribing (so the last thing said is included), then
        answers if anything was routed to the DM. Silent no-op when nothing was — no nagging."""
        if self._rt._paused:
            return
        channel_id = self._rt._active_vc_id if self._rt._active_vc_id is not None else channel.id
        # Trigger = mic release, before wait_idle, so trigger→llm_done covers the whole turn and the
        # wait_idle portion is broken out (wait=…ms).
        timing = self._begin_turn(channel_id, kind="auto")
        tw = time.monotonic()
        await asyncio.to_thread(self._rt._transcriber.wait_idle, 4.0)  # let the final utterance land
        timing.wait_ms = round((time.monotonic() - tw) * 1000)
        # The triggering utterance is usually still transcribing during wait_idle, so re-claim the
        # stt stage now that it has landed (keep _begin_turn's value if nothing new arrived).
        timing.stt_ms = self._rt._last_stt_ms.pop(channel_id, timing.stt_ms)
        if self._rt._brain.pending_count(channel_id) == 0:
            return
        if self._use_streaming():
            timing.streamed = True
            try:
                await self._deliver_streaming(channel, guild_id, timing)
            except Exception:
                log.exception("DM turn failed (auto, stream)")
                await self._rt._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        try:
            answer = await self._rt._brain.respond(channel_id)
            timing.llm_done = time.monotonic()
            timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed (auto)")
            await self._rt._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer is not None:  # "" = a marker-only turn → still deliver (posts the dice button)
            await self._deliver_answer(channel, guild_id, answer, timing)

    async def _run_and_deliver(self, channel, guild_id: int | None) -> None:
        """Run a DM turn and deliver it — used after a dice roll feeds its result back in so the
        DM narrates the consequence (architecture §9)."""
        if self._rt._paused:  # frozen — the roll result is already posted; narration waits for resume
            return
        timing = self._begin_turn(self._rt._brain_channel(channel), kind="roll")
        if self._use_streaming():
            timing.streamed = True
            try:
                await self._deliver_streaming(channel, guild_id, timing)
            except Exception:
                log.exception("DM turn failed (after roll, stream)")
                await self._rt._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        try:
            answer = await self._rt._brain.respond(self._rt._brain_channel(channel))
            timing.llm_done = time.monotonic()
            timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("DM turn failed (after roll)")
            await self._rt._send_with_retry(channel, "(Der Spielleiter schweigt — Fehler, siehe Log.)")
            return
        if answer is not None:  # "" = the consequence narration was empty; nothing to deliver/speak
            await self._deliver_answer(channel, guild_id, answer, timing)

    # Display names for the curated lore topics (data/lore/<topic>.md, ADR 021); unknown
    # (future) files fall back to topic.title().
    _LORE_TITLES = {"imperium": "Weltwissen: Imperium", "chaos": "Weltwissen: Chaos"}
    # !lore questions search the Weltwissen sources only — rule questions belong to the DM
    # turn / !rules, and raw rulebook chunks are English layout soup, not player reading.
    _LORE_SOURCES = ("lore_imperium", "lore_chaos", "setting")
    _LORE_SOURCE_NAMES = {"lore_imperium": "Imperium", "lore_chaos": "Chaos", "setting": "Hive Rokarth"}

    @commands.command(name="lore", aliases=["hintergrund"])
    async def lore(self, ctx: commands.Context, *, arg: str = "") -> None:
        """Weltwissen: `!lore` / `!lore chaos` blättert den Rundown (◀/▶); `!lore <frage>`
        schlägt die passenden Kompendiums-Abschnitte nach (`!lore wer ist der Imperator?`).
        `!lore tts [thema]` liest das Kompendium über Bot A vor. Sonst Lese-Material, kein
        DM-Turn — wird nicht gesprochen. Alias: !hintergrund"""
        lore_dir = _DATA_DIR / "lore"
        topic = arg.lower().strip()
        head, _, rest = topic.partition(" ")
        if head == "tts":
            await self._lore_speak(ctx, lore_dir, rest.strip() or "imperium")
            return
        if not topic or (lore_dir / f"{topic}.md").is_file():
            await self._lore_rundown(ctx, lore_dir, topic or "imperium")
            return
        await self._lore_question(ctx, arg)

    async def _lore_rundown(self, ctx: commands.Context, lore_dir, topic: str) -> None:
        """The paged ◀/▶ view over data/lore/<topic>.md (the original !lore mode)."""
        path = lore_dir / f"{topic}.md"
        if not path.is_file():
            topics = available_topics(lore_dir)
            hint = ", ".join(f"`{t}`" for t in topics) if topics else "—"
            await ctx.send(f"Kein Lore-Thema `{topic}`. Verfügbar: {hint}")
            return
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        pages = lore_pages(text)
        if not pages:
            await ctx.send(f"`{path.name}` enthält keine lesbaren Abschnitte.")
            return
        view = RulesView(pages, self._LORE_TITLES.get(topic, topic.title()))
        await self._rt._send_with_retry(ctx.channel, view=view, embed=view.embed())

    async def _lore_speak(self, ctx: commands.Context, lore_dir, topic: str) -> None:
        """`!lore tts [thema]` — read the data/lore/<topic>.md compendium aloud via Piper +
        Bot A, section by section. Lese-Material that *is* spoken on demand (opposite of the
        silent rundown); reuses ``_speak`` so the feedback guard + WAV cleanup are identical to
        a DM turn. Pages are spoken one at a time so /speak blocks per section, not the whole
        file at once."""
        if not self._rt._tts_enabled:
            await ctx.send("Keine TTS-Stimme geladen (siehe SETUP B5).")
            return
        path = lore_dir / f"{topic}.md"
        if not path.is_file():
            topics = available_topics(lore_dir)
            hint = ", ".join(f"`{t}`" for t in topics) if topics else "—"
            await ctx.send(f"Kein Lore-Thema `{topic}`. Verfügbar: {hint}")
            return
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        pages = lore_pages(text)
        if not pages:
            await ctx.send(f"`{path.name}` enthält keine lesbaren Abschnitte.")
            return
        title = self._LORE_TITLES.get(topic, topic.title())
        guild_id = ctx.guild.id if ctx.guild else None
        log.info("📚 !lore tts %r → interactive reader, %d sections", topic, len(pages))
        # Interactive reader: shows each block's text in chat + reads it; ⏭ Weiter advances to the
        # next block (a fast click-through skips intermediate audio), ⏹ Stopp ends it. Bot A's
        # /speak blocks per WAV with no stop, so a running block can't be cut mid-playback.
        view = LoreReadView(pages, title, speak_fn=self._speak, guild_id=guild_id)
        await self._rt._send_with_retry(ctx.channel, view=view, embed=view.embed())
        view.begin_speaking()  # speak block 0 now

    async def _lore_question(self, ctx: commands.Context, question: str) -> None:
        """`!lore <frage>` — show the best-matching Weltwissen sections (deterministic chunk
        display, no LLM: the compendium text IS the answer; the DM narrates in-game)."""
        if not self._rt._retriever.available():
            await ctx.send("Kein RAG-Store vorhanden — `!lore <frage>` braucht `data/vectordb/rag.db`.")
            return
        hits = await self._rt._retriever.lookup(question, sources=self._LORE_SOURCES)
        if not hits:
            await ctx.send(
                f"Dazu steht nichts im Weltwissen: *{question}*\n"
                f"(Rundown: `!lore` / `!lore chaos` — Regelfragen: `!rules`)"
            )
            return
        parts = []
        for source, heading, text, dist in hits:
            label = self._LORE_SOURCE_NAMES.get(source, source)
            parts.append(f"**{heading}** · _{label}_\n{text}")
            log.info("📚 !lore %r → %s:%r (d=%.2f)", question, source, heading, dist)
        description = "\n\n".join(parts)
        if len(description) > 4000:  # embed description cap; two lore chunks normally fit
            description = description[:4000].rsplit(" ", 1)[0] + " …"
        embed = discord.Embed(
            title="📚 Weltwissen", description=description, color=discord.Color.dark_gold()
        )
        await self._rt._send_with_retry(ctx.channel, embed=embed)

    @commands.command(name="ort", aliases=["szene"])
    async def ort(self, ctx: commands.Context, scene_id: str = "") -> None:
        """`!ort <szenen-id>` — set the adventure's scene pointer (Phase 10a): the DM's prompt then
        carries that scene's card. Deterministic by design (golden rule #3) — the human at the
        table moves the plot pointer, the model never does."""
        if self._rt._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._rt._brain_channel(ctx.channel)
        state = self._rt._state.get(cid)
        if state is None:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        if not scene_id:
            scene = self._rt._adventure.get_scene(state.scene_id)
            current = f"**{scene.title_de}** (`{scene.id}`)" if scene else "—"
            await ctx.send(f"Aktuelle Szene: {current}. Wechsel: `!ort <id>` (`!szenen` zeigt alle).")
            return
        scene = self._rt._set_scene(state, scene_id)
        if scene is None:
            await ctx.send(f"Unbekannte Szene `{scene_id}` — `!szenen` zeigt alle Ids.")
            return
        self._rt._persist_and_refresh(ctx.channel)
        log.info("scene → %s (%s)", scene.id, scene.title_de)
        await ctx.send(f"📖 Szene gewechselt: **{scene.title_de}** (Teil {scene.part}).")

    @commands.command(name="szenen")
    async def szenen(self, ctx: commands.Context) -> None:
        """List the loaded adventure's scenes by part — the ids `!ort` accepts."""
        if self._rt._adventure is None:
            await ctx.send("Kein Abenteuer geladen (`DM_ADVENTURE` in `.env`).")
            return
        cid = self._rt._brain_channel(ctx.channel)
        current = self._rt._state[cid].scene_id if cid in self._rt._state else ""
        by_part: dict[int, list[str]] = {}
        for part, sid, title in self._rt._adventure.scene_overview():
            marker = " ◀" if sid == current else ""
            by_part.setdefault(part, []).append(f"`{sid}` {title}{marker}")
        lines = [f"**Teil {part}:** " + " · ".join(entries)
                 for part, entries in sorted(by_part.items())]
        await ctx.send(f"📖 **{self._rt._adventure.title}**\n" + "\n".join(lines))

    @commands.command(name="ortmodus", aliases=["szenenmodus"])
    async def ortmodus(self, ctx: commands.Context, mode: str = "") -> None:
        """`!ortmodus [verbunden|frei]` — how far an automatic scene change (ADR 026) may jump.
        `verbunden` (default): only the current scene's `leads_to` neighbours. `frei`: any scene.
        No argument shows the current mode."""
        mode = mode.strip().lower()
        if not mode:
            await ctx.send(
                f"Automatischer Szenenwechsel: **{self._rt._scene_mode}** "
                f"(`verbunden` = nur Nachbarorte, `frei` = jede Szene). Wechsel: `!ortmodus <modus>`."
            )
            return
        if mode not in ("verbunden", "frei"):
            await ctx.send(f"Unbekannter Modus `{mode}` — erlaubt: `verbunden`, `frei`.")
            return
        self._rt._scene_mode = mode
        log.info("scene mode → %s", mode)
        await ctx.send(f"📖 Szenenmodus: **{mode}**.")

    @commands.command(name="wrap", aliases=["wrapup"])
    async def wrap(self, ctx: commands.Context, *, _arg: str = "") -> None:
        """`!wrap up` / `!wrapup` — generate & store the session recap (D14). It's re-injected at the
        front of the next session so the story carries over. Non-destructive: play can continue."""
        cid = self._rt._brain_channel(ctx.channel)
        await ctx.send("📜 Ich fasse die Sitzung zusammen …")
        try:
            # Cumulative, like the rolling auto-recap (D57): fold the recap already in the prompt into
            # the new one. The auto-recap may have cleared the running history mid-session, so the
            # visible history alone no longer covers the start — without this the manual wrap-up would
            # overwrite the stored recap with only the recent tail and lose the earlier part.
            recap = await self._rt._brain.summarize(cid, prior_recap=self._rt._brain.current_recap(cid))
        except Exception:
            log.exception("recap generation failed")
            await ctx.send("Konnte keine Zusammenfassung erstellen (siehe Log).")
            return
        if not recap:
            await ctx.send("Noch nichts passiert, das sich zusammenfassen ließe.")
            return
        self._persist_recap(ctx.channel, recap)
        await ctx.send(f"📜 **Was bisher geschah:**\n{recap}")

    def _persist_recap(self, channel, recap: str) -> None:
        """Store a freshly generated recap exactly like ``!wrap up``: write it into the world state
        (state.json via _persist_and_refresh, which also re-injects it into the brain's prompt as
        ``## Was bisher geschah``) and mirror it to a human-readable recap.md. Shared by ``!wrap up``
        and the rolling auto-recap (D56) so both persist it identically and it survives a restart."""
        cid = self._rt._brain_channel(channel)
        state = self._rt._state.get(cid)
        if state is None:
            return
        state.set_recap(recap)
        self._rt._persist_and_refresh(channel)
        try:  # mirror to a human-readable recap.md beside state.json
            (self._rt._state_path(cid).parent / "recap.md").write_text(recap + "\n", encoding="utf-8")
        except OSError:
            log.exception("could not write recap.md")

    async def _maybe_compact(self, channel, timing: _TurnTiming) -> None:
        """Rolling auto-recap / context handoff (D56). Called AFTER a turn has been delivered/spoken
        (off the hot path, modelled on _autosave_turn) — never adds latency to the current turn.

        When the just-finished turn's prompt neared the num_ctx cap, fold the running history into a
        **cumulative** recap (prior recap + recent history → one new recap that supersedes it),
        persist it like ``!wrap up`` (so it survives a restart and is injected next turn), then clear
        the in-memory history. The next prompt = persona + adventure + (longer) recap + state + empty
        history — safely under budget, so the persona/adventure head is never truncated again.

        A per-channel guard stops two quick turns both compacting and stops the next player turn from
        reading half-cleared history. After compaction the history is small, so it won't re-trigger."""
        if not self._rt._autorecap or not timing.ctx_over_budget():
            return
        cid = self._rt._brain_channel(channel)
        if cid in self._rt._compacting or self._rt._state.get(cid) is None:
            return
        if self._rt._brain.history_len(cid) == 0:  # nothing to fold in (e.g. fresh after a prior compaction)
            return
        self._rt._compacting.add(cid)
        try:
            log.info(
                "🧵 Kontext bei %s/%s — Auto-Recap: history wird kompaktiert (Persona/Abenteuer "
                "bleiben so ungekürzt).", timing.prompt_eval, timing.num_ctx,
            )
            # Cumulative: fold the recap currently in the prompt into the new one so nothing already
            # summarised is lost (the older recap covers what scrolled out of the running history).
            prior = self._rt._brain.current_recap(cid)
            recap = await self._rt._brain.summarize(cid, prior_recap=prior)
            if not recap:
                log.warning("🧵 Auto-Recap: leere Zusammenfassung — history NICHT geleert.")
                return
            self._persist_recap(channel, recap)
            # Reset the rolling history only now that the recap is safely persisted (clear_history
            # keeps recap/state/buffer — only the turn-by-turn thread goes).
            self._rt._brain.clear_history(cid)
            log.info("🧵 Auto-Recap fertig — history kompaktiert, Recap aktualisiert.")
            if self._rt._text_channel is not None:  # a brief, lightweight Discord note (matches status posts)
                await self._rt._send_with_retry(
                    self._rt._text_channel,
                    "🧵 Kontext wurde eng — ich habe das Bisherige zusammengefasst und mache nahtlos "
                    "weiter (Persona & Abenteuer bleiben erhalten).",
                )
        except Exception:
            log.exception("🧵 Auto-Recap failed — keeping the running history (no truncation safety lost)")
        finally:
            self._rt._compacting.discard(cid)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *, text: str) -> None:
        """Speak arbitrary text through Piper + Bot A — a TTS/bridge smoke test."""
        if not self._rt._tts_enabled:
            await ctx.send("Keine TTS-Stimme geladen (siehe SETUP B5).")
            return
        if await self._speak(text, ctx.guild.id if ctx.guild else None):
            await ctx.send("🔊")
        else:
            await ctx.send(
                "Konnte nicht abspielen — läuft **Bot A** und ist es im selben Voice-Channel? "
                "Prüfe `!vstatus`; Details im Log (`logs/debug.log`)."
            )

    @commands.command(name="voice")
    async def voice(self, ctx: commands.Context, *, name: str = "") -> None:
        """Switch the XTTS speaker live: `!voice Dionisio Schuyler`. No arg → show current."""
        if not hasattr(self._rt._tts, "set_speaker"):
            await ctx.send("Sprecher-Wechsel geht nur mit `TTS_ENGINE=xtts`.")
            return
        if not name:
            await ctx.send(f"Aktueller Sprecher: **{self._rt._tts.speaker}**")
            return
        if self._rt._tts.set_speaker(name):
            await ctx.send(f"Sprecher → **{name}**. Teste mit `!say …`.")
        else:
            await ctx.send(f"Unbekannter Sprecher `{name}`. Liste: `!voices`.")

    @commands.command(name="voices")
    async def voices(self, ctx: commands.Context) -> None:
        """List the XTTS built-in speakers."""
        if not hasattr(self._rt._tts, "speakers"):
            await ctx.send("Nur mit `TTS_ENGINE=xtts` verfügbar.")
            return
        names = ", ".join(self._rt._tts.speakers())
        await ctx.send(f"**XTTS-Sprecher:**\n{names[:1900]}")
