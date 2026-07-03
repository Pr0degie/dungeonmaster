"""Discord commands for the DM turn pipeline: !dm/!redo/!start, streaming+batch delivery, TTS speak,
auto-recap, !wrap, !say/!voice/!voices. Scenes (!ort/!szenen/!ortmodus) and !lore moved to their own
thin cogs (SceneCog/LoreCog, ADR 039); the automatic <<ORT>> marker drain lives in the delivery
pipeline (ADR 035). Shared state lives on SessionRuntime (dmbot/runtime.py); cross-cog flow goes
through its hooks (ADR 029). Bot replies are German; logs English.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from discord.ext import commands

from ..orchestrator import build_intro_director_msg, build_opening_director_msg
from ..llm.intro_guard import is_weak_intro
from ..tts.textsplit import has_speakable_content, strip_speech_punctuation
from ..memory import history as history_store
from .delivery import DeliveryPipeline
from ..runtime import SessionRuntime, _TurnTiming

log = logging.getLogger(__name__)


class DMCog(commands.Cog):
    def __init__(self, bot: commands.Bot, runtime: SessionRuntime) -> None:
        self.bot = bot
        self._rt = runtime
        # The answer→audio delivery pipeline (TTS speak, batch + streaming, scene-marker drain, the
        # per-turn [latency] line) lives in its own module for context-leanness (ADR 035); the
        # post-turn tail (autosave / mic re-anchor / auto-recap) stays here, injected as a callback.
        self._delivery = DeliveryPipeline(runtime, post_deliver=self._post_deliver)
        runtime.run_and_deliver = self._delivery._run_and_deliver  # hook: DiceCog roll callbacks narrate consequence
        runtime.auto_dm_turn = self._delivery._auto_dm_turn        # hook: VoiceCog mic release runs a DM turn
        runtime.speak = self._delivery._speak                      # hook: LoreCog !lore tts reads the compendium aloud

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

    async def _post_deliver(self, channel, answer: str, timing: _TurnTiming, *,
                            saved_user_msg: str | None, redo: bool) -> None:
        """The shared end-of-turn tail of both delivery paths, run *after* the answer is spoken and
        the dice/scene tasks have been awaited: autosave the turn, re-anchor the mic button below the
        new messages, and run the off-hot-path rolling auto-recap (D56). Identical for the batch and
        streaming paths — one source of truth. Runs entirely after `/speak` returned, so it never
        adds turn latency. NOTE: the preceding `timing.end`/`log_line()`/`_await_dice_scene` step is
        deliberately kept per-path (batch awaits dice/scene in a `finally` so the 🎲 still posts if
        speak raised; streaming runs it after the pipeline cleanup) — that placement must not merge."""
        await self._autosave_turn(channel, answer, user_msg=saved_user_msg, redo=redo)
        # Keep the mic button reachable: move it back to the bottom after the message + speech.
        if self._rt._push_to_talk and self._rt._sink is not None:
            await self._rt.reanchor_mic(channel)
        # Rolling auto-recap (D56): if this turn's prompt neared the num_ctx cap, compact the history
        # now — off the hot path (the turn is fully delivered above), so it never adds turn latency.
        await self._maybe_compact(channel, timing)

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
        timing = self._delivery._begin_turn(channel_id)
        if not self._rt.deliver_seamless() and self._delivery._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._delivery._deliver_streaming(
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
        await self._delivery._deliver_answer(ctx.channel, guild_id, answer, timing)

    @commands.command(name="redo", aliases=["r"])
    async def redo(self, ctx: commands.Context) -> None:
        """Re-run the last DM turn with the same input — for when the DM misunderstood. Alias: !r"""
        if self._rt._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        channel_id = self._rt._active_vc_id if self._rt._active_vc_id is not None else ctx.channel.id
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._delivery._begin_turn(channel_id, kind="redo")
        if not self._rt.deliver_seamless() and self._delivery._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._delivery._deliver_streaming(ctx.channel, guild_id, timing, redo=True)
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
        await self._delivery._deliver_answer(ctx.channel, guild_id, answer, timing)

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
        timing = self._delivery._begin_turn(cid)
        if not self._rt.deliver_seamless() and self._delivery._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._delivery._deliver_streaming(
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
        await self._delivery._deliver_answer(ctx.channel, guild_id, answer, timing)

    def _speech_status_text(self) -> str:
        """Current spoken-delivery setting as a short `**mode** + **punct**` string with a per-mode
        note (the puffer depth, or the nahtlos synth-wait warning)."""
        if self._rt._speech_mode == "nahtlos":
            note = " ⏳ wartet auf die volle Synthese vor dem ersten Ton (auf CPU langsam)"
        elif self._rt._speech_mode == "puffer":
            note = f" (Vorlauf: {self._rt._speech_prebuffer} Sätze)"
        else:
            note = ""
        return f"**{self._rt._speech_mode}** + **{self._rt._speech_punct}**{note}"

    @commands.command(name="sprechmodus", aliases=["sprache", "voicemode"])
    async def sprechmodus(self, ctx: commands.Context, *, args: str = "") -> None:
        """`!sprechmodus` — global spoken-delivery mode for EVERY DM turn (ADR 033). Axes, each set
        by a word (give any combination, any order); bare `!sprechmodus` just shows the current:
          • delivery — `stream` (sentence-by-sentence: fast start, small gaps) | `puffer`
            (stream, but synthesise a few sentences ahead before the first plays: smoother, modest
            start delay) | `nahtlos` (synth all → one continuous track: gapless, but waits for the
            WHOLE turn — only snappy on a GPU, see ADR 002);
          • intonation — `flach` (strip ALL punctuation: no XTTS babble, flatter) |
            `intoniert` (keep `.,!?;:-` for sentence/question prosody, but XTTS may babble, D55);
          • a number sets the `puffer` head-start depth (sentences pre-synthesised), e.g.
            `!sprechmodus puffer 4`.
        Takes effect on the next turn. `!intro test` stays a fixed nahtlos+flach comparison anchor.
        Bare `!sprechmodus` (or an unknown word) prints the full how-to + the current setting; a
        successful change just confirms the new setting."""
        changed, unknown = False, []
        for w in args.lower().split():
            if w in ("stream", "puffer", "nahtlos"):
                self._rt._speech_mode = w
                changed = True
            elif w in ("flach", "intoniert"):
                self._rt._speech_punct = w
                changed = True
            elif w.isdigit():
                self._rt._speech_prebuffer = max(1, min(20, int(w)))
                changed = True
            else:
                unknown.append(w)
        # A clean change → just confirm. Bare call or an unknown word → the full how-to + current.
        if changed and not unknown:
            await ctx.send(f"🔊 Sprechmodus jetzt: {self._speech_status_text()}")
            return
        n = self._rt._speech_prebuffer
        lines = [
            "🔊 **Sprechmodus** — wie alle DM-Antworten gesprochen werden (wirkt ab dem nächsten Zug).",
            f"Aktuell: {self._speech_status_text()}",
            "",
            "**Lieferart** — wie abgespielt wird:",
            "• `stream` — Satz für Satz; schnellster Start, kleine Lücken",
            f"• `puffer` — erst {n} Sätze vorladen, dann los; glatter, kurze Startverzögerung",
            "• `nahtlos` — alles am Stück; keine Lücken, wartet aber auf die volle Synthese (auf CPU langsam)",
            "",
            "**Betonung** — wie es klingt:",
            "• `flach` — ohne Satzzeichen; sicher gegen Verhaspler, etwas monoton",
            "• `intoniert` — mit `.,!?` für Satz-/Fragebetonung (kann selten verhaspeln)",
            "",
            "**Ändern:** `!sprechmodus <wert> …` (mehrere auf einmal); eine **Zahl** setzt die Puffertiefe.",
            "Beispiele: `!sprechmodus nahtlos` · `!sprechmodus puffer 4` · `!sprechmodus stream intoniert`",
        ]
        if unknown:
            lines.insert(0, f"❓ Unbekannt: {', '.join(unknown)} — geänderte Werte sind übernommen.")
        await ctx.send("\n".join(lines))

    @commands.command(name="intro", aliases=["einleitung", "eroeffnung"])
    async def intro(self, ctx: commands.Context, *, mode: str = "") -> None:
        """`!intro` — the DM speaks a full opening *monologue* for the campaign (ADR 031): where the
        party is, how they got here, what's going on + their mission, and a personal beat for each
        player character (drawn from each sheet's flavour). Unlike the short `!start` briefing it
        embeds a character roster into the director instruction and runs on a larger length budget
        (DM_INTRO_NUM_PREDICT). The scene pointer is moved deterministically (golden rule #3), dice
        are suppressed. `!start` stays the quick briefing.

        Two delivery modes (same generated monologue), to pick by feel — the trade-off is forced by
        XTTS being slower than realtime, so you can't have an instant start AND gapless playback:
        - **`!intro`** (default) — **streamed**, punctuation-free (`strip_speech_punctuation`, no XTTS
          babble): starts speaking after the first sentence, but synthesis can't keep up with playback
          so there are small inter-sentence gaps. **Fast start, minor gaps.**
        - **`!intro test`** — synthesise every sentence, **join them into ONE continuous track** and
          play it once (`_deliver_intro_chunked`): sounds like one read-aloud text with no gaps, but
          the first sound waits for the whole monologue to synthesise. **Gapless, slow start.**"""
        if self._rt._paused:
            await ctx.send("⏸ Pausiert — mit **Esc** oder dem ⏸-Knopf fortsetzen.")
            return
        cid = self._rt._brain_channel(ctx.channel)
        # Mirror the turn-producing guards: a session must be active (state seeded on !join).
        if self._rt._active_vc_id is None or cid not in self._rt._state:
            await ctx.send("Keine aktive Sitzung — erst `!j`.")
            return
        # Point the scene pointer at the start scene if it isn't set yet (deterministic, golden rule
        # #3 — code moves the pointer, not the model), so the prompt's "## Aktuelle Szene" is the
        # opening scene. A loaded session keeps its saved pointer — the intro never resets progress.
        if self._rt._adventure is not None and not self._rt._state[cid].scene_id:
            moved = self._rt._set_scene(self._rt._state[cid], self._rt._adventure.start_scene)
            if moved is not None:
                self._rt._persist_and_refresh(ctx.channel)
        roster = self._rt._characters.intro_roster_de() if self._rt._characters else ""
        director_msg = build_intro_director_msg(roster)
        np = self._rt._intro_num_predict
        tmp = self._rt._intro_temperature  # lower, fixed !intro temperature (D83) — steadier monologue
        guild_id = ctx.guild.id if ctx.guild else None
        timing = self._delivery._begin_turn(cid)
        # B-variant: batch-generate, then read smaller chunks out one after another (see helper).
        if mode.strip().lower() == "test":
            await self._deliver_intro_chunked(ctx, cid, guild_id, director_msg, np, tmp, timing)
            return
        if not self._rt.deliver_seamless() and self._delivery._use_streaming():
            timing.streamed = True
            try:
                async with ctx.typing():
                    answer = await self._delivery._deliver_streaming(
                        ctx.channel, guild_id, timing, opening=director_msg, opening_num_predict=np,
                        opening_temperature=tmp,
                    )
            except Exception:
                log.exception("intro monologue failed (stream)")
                await ctx.send("(Der Spielleiter schweigt — Fehler beim Auftakt, siehe Log.)")
                return
            if answer is None:
                await ctx.send("(Kein Auftakt — siehe Log.)")
            return
        try:
            async with ctx.typing():
                answer = await self._rt._brain.respond_opening(cid, director_msg, num_predict=np, temperature=tmp)
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("intro monologue failed")
            await ctx.send("(Der Spielleiter schweigt — Fehler beim Auftakt, siehe Log.)")
            return
        if answer is None:
            await ctx.send("(Kein Auftakt — siehe Log.)")
            return
        await self._delivery._deliver_answer(ctx.channel, guild_id, answer, timing)

    async def _deliver_intro_chunked(self, ctx: commands.Context, cid: int, guild_id: int | None,
                                     director_msg: str, np: int, tmp: float | None,
                                     timing: _TurnTiming) -> None:
        """`!intro test` delivery (ADR 031): generate the whole monologue in one batch (same
        `respond_opening` path, dice suppressed), post it once, then synthesise each sentence
        **separately and punctuation-free** (`strip_speech_punctuation`, since XTTS babbles on
        punctuation, D55) and **join the per-sentence WAVs into ONE continuous track** played in a
        single bridge call — so the chunked speech sounds like one read-aloud text with natural
        sentence pacing (a short `_INTRO_SENTENCE_PAUSE_S` silence between sentences) and **no**
        inter-sentence gaps. Trade-off: the first audio waits for the whole monologue to synthesise
        (XTTS ~0.5x realtime) — the price of gapless playback. The posted chat text keeps its
        punctuation (readable, D38). A pause during synthesis aborts cleanly. No dice button / scene
        proposal (an opening turn never queues either)."""
        # The batch path can validate the opening before it's spoken: if it comes out weak (too
        # short / a figure skipped — the 12B model's high-variance failure, ADR 041), regenerate
        # once. Streaming !intro can't (audio already plays), so this is the path to prefer.
        roster_names = self._rt._characters.character_names() if self._rt._characters else []
        try:
            async with ctx.typing():
                answer = await self._rt._brain.respond_opening(
                    cid, director_msg, num_predict=np, temperature=tmp,
                    is_weak=lambda t: is_weak_intro(t, roster_names),
                )
                timing.llm_done = time.monotonic()
                timing.take_llm_stats(self._rt._brain.last_llm_stats)
        except Exception:
            log.exception("intro monologue failed (chunked test)")
            await ctx.send("(Der Spielleiter schweigt — Fehler beim Auftakt, siehe Log.)")
            return
        if not answer or not has_speakable_content(answer):
            await ctx.send("(Kein Auftakt — siehe Log.)")
            return
        log.info("🎭 %s", answer)
        await self._rt._send_with_retry(ctx.channel, answer)
        if self._rt._tts_enabled:
            # `!intro test` = explicit one-off "seamless + punctuation-free", independent of the
            # global !sprechmodus, as the known-good comparison anchor.
            await self._delivery._speak_seamless(answer, guild_id, timing, transform=strip_speech_punctuation)
            timing.end = time.monotonic()
            timing.log_line()
        if self._rt._push_to_talk and self._rt._sink is not None:
            await self._rt.reanchor_mic(ctx.channel)
        await self._autosave_turn(ctx.channel, answer)

    @commands.command(name="wrap", aliases=["wrapup"])
    async def wrap(self, ctx: commands.Context, *, _arg: str = "") -> None:
        """`!wrap up` / `!wrapup` — generate & store the session recap (D14). It's re-injected at the
        front of the next session so the story carries over. Non-destructive: play can continue."""
        cid = self._rt._brain_channel(ctx.channel)
        await ctx.send("📜 Ich fasse die Sitzung zusammen …")
        # NPC memory (ADR 044), catch-all for the last scene: the scene-change trigger never fires
        # for the scene the session ends in, so mine it here BEFORE the recap (awaited — wrap-up is
        # not latency-critical, and the extractor is best-effort/no-raise by contract).
        state = self._rt._state.get(cid)
        if state is not None:
            await self._rt.extract_npc_memories(ctx.channel, state.scene_id)
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
            # NPC-memory window (ADR 044): the mark counted from the old history head; after the
            # compaction only the turns appended during the summarize await remain, so restart the
            # window at 0. Overlap (extracted-but-unconsumed turns) is deduped at apply.
            self._rt._npc_mem_marks.pop(cid, None)
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
        if await self._delivery._speak(text, ctx.guild.id if ctx.guild else None):
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
