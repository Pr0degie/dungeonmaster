"""The DM turn delivery pipeline: turn an answer (or a streaming generation) into spoken audio (via
Bot A's /speak bridge), the posted Discord text, the 🎲 dice button + scene-change proposal, and the
per-turn ``[latency]`` line. Split out of dmbot/voice/dmcog.py for context-leanness (ADR 035): it is
the most-edited block (every TTS-tuning fix lands here) yet a cohesive unit, so an agent working on
delivery loads only this module, not the whole 1100-line cog.

Composition, not inheritance: DMCog owns a ``DeliveryPipeline(runtime, post_deliver=...)`` and calls
into it. The pipeline holds the shared SessionRuntime and reaches everything shared through it (TTS,
bridge, brain, sink, speech-mode flags) exactly as the cog did — every moved body is byte-identical.
The one thing it calls back into the cog for is the post-turn tail (autosave history -> re-anchor mic
-> rolling auto-recap), injected as ``post_deliver``: that stays a cog/session concern (and keeps the
auto-recap tests on the cog). Cross-cog flow (dice button, mic re-anchor) still goes through the
runtime hooks (ADR 029); the two turn-running hooks ``_run_and_deliver`` / ``_auto_dm_turn`` live
here and are registered on the runtime by the cog.

Bot replies are German; logs English.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from collections.abc import Callable

import discord

from ..tts.textsplit import has_speakable_content, split_completed
from ..tts.wavio import concat_wavs
from ..shutdown import to_daemon_thread
from ..discord_ui.flag import FlagView
from ..discord_ui.scene import SceneChangeView
from ..rag.adventure import Scene
from ..runtime import (
    SessionRuntime, _TurnTiming, _wav_duration_s, _safe_remove, _TTS_LOAD_TIMEOUT_S,
)

log = logging.getLogger(__name__)

# `!intro test` / `nahtlos` (ADR 031/033): the silence inserted between sentences when their
# separately-synthesised WAVs are joined into ONE continuous track (so a chunked monologue sounds
# like one read-aloud text, with natural sentence pacing). Tune by ear.
_INTRO_SENTENCE_PAUSE_S = 0.2


class DeliveryPipeline:
    """The answer->audio delivery pipeline (ADR 035). Owns TTS synth/speak, the batch + streaming
    delivery paths, the seamless (`nahtlos`) one-track speak, the `<<ORT>>` scene-marker drain, the
    per-turn timing record, and the two turn-running hooks (`_run_and_deliver` after a dice roll,
    `_auto_dm_turn` on mic release). Constructed once by DMCog with the shared runtime; the post-turn
    tail (autosave/mic re-anchor/auto-recap) is injected as `post_deliver` and runs on the cog."""

    def __init__(self, runtime: SessionRuntime, post_deliver: Callable) -> None:
        self._rt = runtime
        # The shared end-of-turn tail (autosave -> mic re-anchor -> auto-recap) lives on DMCog so the
        # recap/session concern — and its tests — stay there; both delivery paths call it via this.
        self._post_deliver = post_deliver

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
                     timing: _TurnTiming | None = None, *,
                     speech_transform: Callable[[str], str] | None = None) -> bool:
        """Synthesise ``text`` and play it via Bot A's /speak bridge. Returns True if it played.

        Synthesis is blocking, so it runs in a thread. The WAV is deleted after playback so the
        temp dir doesn't fill up. Bot A's audio is filtered by user-ID (feedback layer 1), so
        DMbot does not transcribe its own DM voice even without pausing the VAD. ``timing`` (when
        a DM turn passes one) collects the tts / wav / bridge_wait stages for the [latency] line.
        ``speech_transform`` (optional): applied to ``text`` before synthesis only (e.g. the intro's
        punctuation strip) — the chat text the caller posted is unaffected.
        """
        if not self._rt._tts_enabled:
            return False
        if speech_transform is not None:
            text = speech_transform(text)
            if not has_speakable_content(text):
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
        target = self._rt._adventure.resolve_move(
            state.scene_id, req.scene_id, self._rt._scene_mode,
            resolved_ids=state.resolved_ids(state.scene_id),  # gated exits, ADR 043
        )
        if target is None:  # no-op, unknown id, not a leads_to neighbour, or a locked gate
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

    async def _handle_erledigt(self, channel) -> None:
        """Apply the DM turn's ``<<ERLEDIGT id>>`` scene-element flags (ADR 043): validate each id
        against the CURRENT scene card and either post a confirm button per element
        (``DM_FLAG_CONFIRM=1``, default) or apply them immediately. The flag is deterministic
        (golden rule #3): the model never writes ``scene_flags``, it only *requests* the flag.
        Unlike ``<<ORT>>`` every valid request in the turn is processed — flags are idempotent and
        low-stakes. Unknown/foreign/duplicate ids are ignored + logged, never applied.

        Guard order is load-bearing: the adventure check comes BEFORE the brain drain, so a stub
        brain without ``take_pending_erledigt`` (tests/test_delivery.py) is never touched when no
        adventure is loaded. Pending requests then simply expire on redo/reset — harmless, they
        are never queued in practice without a scene card in the prompt."""
        if self._rt._adventure is None:
            return
        cid = self._rt._brain_channel(channel)
        reqs = self._rt._brain.take_pending_erledigt(cid)
        if not reqs:
            return
        state = self._rt._state.get(cid)
        if state is None:
            return
        scene = self._rt._adventure.get_scene(state.scene_id)
        if scene is None:
            return
        valid = set(scene.element_ids())
        already = set(state.resolved_ids(scene.id))
        seen_this_turn: set[str] = set()
        applied_any = False
        for req in reqs:
            eid = req.element_id
            if not req.parsed or eid not in valid or eid in seen_this_turn or eid in already:
                log.info("🚫 ERLEDIGT '%s' abgelehnt (Szene '%s')", eid or req.raw, scene.id)
                continue
            seen_this_turn.add(eid)
            text = scene.element_text(eid) or eid
            if self._rt._flag_confirm:
                log.info("✅ Erledigt vorgeschlagen: %s (%s)", eid, scene.id)
                await channel.send(
                    f"✅ Erledigt vorgeschlagen: **{text}** (`{eid}`). Abhaken?",
                    view=FlagView(eid, text, self._make_flag_confirm(channel, eid)),
                )
            else:
                self._rt._set_scene_flag(state, eid, resolved=True)
                applied_any = True
                log.info("✅ erledigt (auto): %s — %s (Szene '%s')", eid, text, scene.id)
        if applied_any:
            self._rt._persist_and_refresh(channel)

    def _make_flag_confirm(self, channel, element_id: str):
        """Build the confirm callback for a proposed element flag: on click, perform the same
        deterministic flag ``!erledigt`` does (``_set_scene_flag`` + persist + prompt refresh) and
        edit the proposal message. A click after a scene change degrades cleanly — the id no longer
        validates against the (new) current scene."""
        async def _confirm(interaction: discord.Interaction) -> None:
            cid = self._rt._brain_channel(channel)
            state = self._rt._state.get(cid)
            if state is None:
                return
            text = self._rt._set_scene_flag(state, element_id, resolved=True)
            if text is None:  # the scene changed between proposal and click
                await interaction.edit_original_response(
                    content="Nicht mehr aktuell — die Szene hat gewechselt."
                )
                return
            self._rt._persist_and_refresh(channel)
            log.info("✅ erledigt: %s [auto, bestätigt]", element_id)
            await interaction.edit_original_response(
                content=f"✅ Abgehakt: **{text}** (`{element_id}`)."
            )
        return _confirm

    async def _deliver_answer(self, channel, guild_id: int | None, answer: str,
                              timing: _TurnTiming) -> None:
        """Batch delivery: log, post (5xx-resilient), then speak and post the dice button
        **concurrently** so the 🎲 appears while the DM speaks (Task 2 / D40), and re-anchor the
        mic button. Closes out the per-turn ``timing`` (tts/bridge via the speak step) and emits the
        single ``[latency]`` line once ``/speak`` returned. Spoken delivery follows the global
        `!sprechmodus` (ADR 033): the intonation transform comes from ``self._rt.speech_transform()``
        (applied to the spoken text only, chat text untouched, D38), and ``nahtlos`` speaks the whole
        answer as ONE continuous track (`_speak_seamless`) while ``stream``/default speaks it as one
        `_speak`. (This batch path runs for `nahtlos` OR when streaming is off.)"""
        timing.answer_chars = len(answer)
        # Snapshot the turn's user_msg NOW (generation just ended): a dice click during the
        # playback below starts the next turn and overwrites the brain's _last_turn (D43 race fix).
        saved_user_msg = self._rt._brain.last_user_msg(self._rt._brain_channel(channel))
        if answer:
            log.info("🎭 %s", answer)  # rendered prominently in the console
        log.info("⏱ LLM %d ms%s", timing.respond_ms(), " (redo)" if timing.kind == "redo" else "")
        # A content-less answer (a marker-only turn the model wrapped in a code fence, etc.) must not
        # be posted or spoken — XTTS would read a lone quote for ~15 s. The dice button still posts.
        transform = self._rt.speech_transform()
        speakable = has_speakable_content(answer)
        speak_task = None
        if speakable:
            await self._rt._send_with_retry(channel, answer)
            if self._rt.deliver_seamless():
                speak_task = asyncio.create_task(
                    self._speak_seamless(answer, guild_id, timing, transform=transform)
                )
            else:
                speak_task = asyncio.create_task(
                    self._speak(answer, guild_id, timing, speech_transform=transform)
                )
        else:
            log.info("(inhaltslose Antwort — nichts gepostet/gesprochen; nur ggf. Würfel)")
        dice_task = asyncio.create_task(self._rt.handle_dice(channel))
        scene_task = asyncio.create_task(self._handle_scene(channel))  # ADR 026: propose a scene move
        flag_task = asyncio.create_task(self._handle_erledigt(channel))  # ADR 043: element flags
        # dice_task/scene_task must ALWAYS be awaited — even if _speak raises a bridge-side error.
        # Otherwise the dice button is never posted and the orphaned tasks log "Task exception was
        # never retrieved". The finally awaits them (logging, not dropping, their own exceptions) and
        # lets a speak_task error propagate to the caller's handler afterwards.
        try:
            if speak_task is not None:
                await speak_task
            timing.end = time.monotonic()  # /speak returned → total stops here (mic re-anchor excluded)
            timing.log_line()
        finally:
            # The dice button must land before the mic button re-anchors at the bottom; likewise the
            # scene-change proposal. await_dice_scene awaits all and logs (never drops) their errors.
            await self._await_dice_scene(dice_task, scene_task, flag_task)
        await self._post_deliver(channel, answer, timing,
                                 saved_user_msg=saved_user_msg, redo=timing.kind == "redo")

    @staticmethod
    async def _await_dice_scene(dice_task: asyncio.Task | None,
                                scene_task: asyncio.Task | None,
                                flag_task: asyncio.Task | None = None) -> None:
        """Await the concurrent dice-button, scene-proposal and element-flag tasks, retrieving (and
        logging, never dropping) any exception each raised. Used by both delivery paths so a failing
        task can't leave a 'Task exception was never retrieved' warning. Order matters: dice first,
        then scene, then flags, so all land before the mic button re-anchors at the bottom."""
        for task, what in ((dice_task, "dice button"), (scene_task, "scene proposal"),
                           (flag_task, "flag proposal")):
            if task is None:
                continue
            try:
                await task
            except Exception:
                log.exception("%s task failed", what)

    async def _deliver_streaming(self, channel, guild_id: int | None, timing: _TurnTiming, *,
                                 redo: bool = False, extra_text: str | None = None,
                                 opening: str | None = None,
                                 opening_num_predict: int | None = None,
                                 opening_temperature: float | None = None) -> str | None:
        """Streaming delivery (ADR 017): the producer drives the brain's streaming turn while a
        synth→playback pipeline speaks each sentence (synth N+1 while N plays); the Discord text
        post + 🎲 dice button happen at generation-end (mid-playback). Layer-2 mute spans the whole
        answer (not per sentence); pause stops emission cleanly. Returns the stored answer or None.

        Each sentence is run through the global intonation transform (`self._rt.speech_transform()`,
        ADR 033) **before synthesis only** — `flach` strips all punctuation (no XTTS babble, D55),
        `intoniert` keeps it; the posted chat text is untouched (D38). This is the `stream` delivery
        mode (fast start, small gaps); `nahtlos` takes the batch path instead."""
        channel_id = self._rt._brain_channel(channel)
        transform = self._rt.speech_transform()         # global intonation axis, fixed for this turn
        prebuffer = self._rt.prebuffer_count()           # 1 = plain stream; >1 = puffer head-start
        sentence_q: asyncio.Queue = asyncio.Queue()
        # Bounds how far synth runs ahead of playback. In puffer mode this == the head-start depth,
        # so the cushion is kept ~prebuffer sentences deep during playback.
        wav_q: asyncio.Queue = asyncio.Queue(maxsize=max(1, prebuffer))
        sink = self._rt._sink if self._rt._pause_vad_while_speaking else None
        holder: dict = {"answer": None}

        async def on_sentence(s: str) -> None:
            await sentence_q.put(s)

        async def producer() -> None:
            try:
                if opening is not None:
                    # A GM-side director turn (dice suppressed): the short !start briefing or the
                    # longer !intro monologue (ADR 031) — same stream→speak pipeline, just a
                    # different brain entry point + an optional larger length budget for !intro.
                    holder["answer"] = await self._rt._brain.respond_opening_streaming(
                        channel_id, opening, on_sentence=on_sentence,
                        should_abort=lambda: self._rt._paused,
                        num_predict=opening_num_predict, temperature=opening_temperature,
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
                text = s
                if transform is not None:
                    text = transform(s)                # speech-only transform (e.g. strip punctuation)
                    if not has_speakable_content(text):
                        continue                       # a sentence that strips to nothing → no synth
                try:
                    t0 = time.perf_counter()
                    # Daemon thread (see dmbot/shutdown.py): a streamed-sentence synth in flight
                    # at Ctrl+C is abandoned, never join-blocking the shutdown. _synthesize waits
                    # for the boot-time TTS preload inside the thread (never the event loop).
                    wav = await to_daemon_thread(self._synthesize, text)
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

        async def _play_one(wav: str) -> None:
            if self._rt._paused:
                _safe_remove(wav)
                return
            if timing.first_audio is None:
                timing.first_audio = time.monotonic()
            tb = time.monotonic()
            try:
                await self._rt._bridge.speak(wav, guild_id=guild_id)
            finally:
                timing.bridge_ms = (timing.bridge_ms or 0) + round((time.monotonic() - tb) * 1000)
                _safe_remove(wav)

        async def play_worker() -> None:
            # Head-start (ADR 033 'puffer', D69): accumulate up to `prebuffer` synthesised WAVs
            # before the first plays, so the buffer cushions CPU synth falling behind realtime and
            # the inter-sentence gaps appear later (or not at all, for short turns). prebuffer == 1
            # is the plain 'stream' behaviour (play as soon as the first sentence is ready). Any WAVs
            # still buffered when the turn aborts (pause/cancel) are removed in `finally` — no leak.
            buffered: list[str] = []
            try:
                done = False
                while len(buffered) < prebuffer:
                    wav = await wav_q.get()
                    if wav is None:
                        done = True
                        break
                    buffered.append(wav)
                if prebuffer > 1 and buffered:
                    log.info("🔊 Puffer gefüllt (%d Satz/Sätze) — Wiedergabe startet", len(buffered))
                while buffered:
                    await _play_one(buffered.pop(0))
                if done:
                    return
                while True:
                    wav = await wav_q.get()
                    if wav is None:
                        return
                    await _play_one(wav)
            finally:
                for wav in buffered:
                    _safe_remove(wav)

        if sink is not None:
            sink.mute()  # layer 2: stay muted across the WHOLE answer, no flapping between sentences
        prod = asyncio.create_task(producer())
        sw = asyncio.create_task(synth_worker())
        pw = asyncio.create_task(play_worker())
        dice_task: asyncio.Task | None = None
        scene_task: asyncio.Task | None = None
        flag_task: asyncio.Task | None = None
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
                flag_task = asyncio.create_task(self._handle_erledigt(channel))  # ADR 043
            # gather() re-raises the FIRST worker exception WITHOUT cancelling its siblings — so if
            # play_worker dies on a mid-stream bridge 5xx, synth_worker would hang forever on the
            # bounded wav_q.put and leak its temp WAV. Log a worker failure here; the finally then
            # cancels any still-running pipeline task and drains the queue (no orphan task / WAV leak).
            try:
                await asyncio.gather(sw, pw)  # wait for the last sentence to finish playing
            except Exception:
                log.exception("streaming synth/play worker failed mid-stream")
        finally:
            if sink is not None:
                sink.unmute()
            # Cancel any pipeline task still pending (producer/synth/play) after a mid-stream failure
            # and await its cancellation, then drain any temp WAVs the synth worker had queued so a
            # failed turn doesn't leave a hung task or leaked file behind. A clean run finds them all
            # done and the queue empty — this is a no-op then.
            for task in (prod, sw, pw):
                if not task.done():
                    task.cancel()
            for task in (prod, sw, pw):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    log.exception("streaming pipeline task failed during cleanup")
            while not wav_q.empty():
                leftover = wav_q.get_nowait()
                if leftover is not None:
                    _safe_remove(leftover)
        if holder["answer"] is not None:
            timing.end = time.monotonic()  # last /speak returned
            timing.log_line()
            await self._await_dice_scene(dice_task, scene_task, flag_task)
            await self._post_deliver(channel, holder["answer"], timing,
                                     saved_user_msg=saved_user_msg, redo=redo)
        return holder["answer"]

    async def _speak_seamless(self, text: str, guild_id: int | None, timing: _TurnTiming, *,
                              transform: Callable[[str], str] | None = None) -> bool:
        """Speak ``text`` as ONE continuous track (the `nahtlos` delivery, ADR 033): split into
        sentences, synthesise each separately (optionally ``transform``-ed, e.g. punctuation-stripped
        so XTTS doesn't babble, D55), `concat_wavs` them with a short `_INTRO_SENTENCE_PAUSE_S` silence
        between, and play the single track in one layer-2-muted bridge call — gapless, naturally
        paced. Trade-off: nothing is heard until the WHOLE text is synthesised (XTTS is slower than
        realtime; only snappy on a GPU). A pause aborts before/while synthesising; every temp WAV (the
        per-sentence parts and the merged track) is removed in `finally`, so an aborted/failed turn
        leaks nothing. Returns True if a track played."""
        completed, tail = split_completed(text)              # split on punctuation FIRST (then transform)
        sentences = completed + ([tail] if tail else [])
        parts: list[str] = []
        try:
            for i, sentence in enumerate(sentences, 1):
                if self._rt._paused:
                    log.info("🧩 nahtlos: pausiert — Synthese abgebrochen")
                    return False
                speech = transform(sentence) if transform is not None else sentence
                if not has_speakable_content(speech):
                    continue
                log.info("🧩 Satz %d/%d: %s", i, len(sentences), speech)
                try:
                    t0 = time.perf_counter()
                    wav = await to_daemon_thread(self._synthesize, speech)
                except Exception:
                    log.exception("TTS synthesis failed (seamless sentence) — skipping it")
                    continue
                if wav is None:
                    continue
                timing.tts_ms = (timing.tts_ms or 0) + round((time.perf_counter() - t0) * 1000)
                parts.append(wav)
            if not parts or self._rt._paused:
                return False
            fd, merged = tempfile.mkstemp(prefix="dm_seamless_", suffix=".wav")
            os.close(fd)
            try:
                concat_wavs(parts, merged, gap_s=_INTRO_SENTENCE_PAUSE_S)
                timing.wav_s = _wav_duration_s(merged)
                # One continuous playback. Layer-2 mute spans it (ADR 003); /speak blocks until the
                # whole track finished, mirroring the streaming play_worker's bookkeeping.
                sink = self._rt._sink if self._rt._pause_vad_while_speaking else None
                if sink is not None:
                    sink.mute()
                if timing.first_audio is None:
                    timing.first_audio = time.monotonic()
                tb = time.monotonic()
                try:
                    played = await self._rt._bridge.speak(merged, guild_id=guild_id)
                finally:
                    timing.bridge_ms = (timing.bridge_ms or 0) + round((time.monotonic() - tb) * 1000)
                    if sink is not None:
                        sink.unmute()
                return bool(played)
            finally:
                _safe_remove(merged)
        finally:
            for wav in parts:
                _safe_remove(wav)

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
        if not self._rt.deliver_seamless() and self._use_streaming():
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
        if not self._rt.deliver_seamless() and self._use_streaming():
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

