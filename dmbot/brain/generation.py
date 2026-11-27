"""One answer of :class:`~dmbot.orchestrator.DMBrain` through the guards — the generation
path every turn kind (respond, redo, opening) shares: one batch or streamed LLM call, the echo
guard (D43/ADR 018, W4), the intro guard (ADR 041 follow-up), the consistency guard (ADR 045)
and the history entry.

A mixin (ADR 065): its methods are methods of the one ``DMBrain`` object — ``self`` is the
brain, all state is created in ``DMBrain.__init__`` and kept per channel in a
``ChannelSession``.

``_build_request`` stays in orchestrator.py: ``dmbot/tools/text_replay.py`` rebinds
``orchestrator.load_system_prompt``, and only a function defined in that module sees the
rebind. ``_queue_markers`` and ``_append_turn`` stay there as well; the methods here reach all
three through ``self``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from ..llm.consistency import Violation, retry_nudge_de
from ..llm.cut_report import caller_reports_cut
from ..llm.echo_guard import _ECHO_NUDGE, _REPEAT_NUDGE, is_echo, is_self_repetition
from ..llm.failover import LLMPausedError
from ..llm.intro_guard import INTRO_RETRY_NUDGE
from ..llm.stream_assembler import StreamAssembler, finalize_answer_trimmed
from ..rules.marker import empty_markers
from ..tts.textsplit import has_speakable_content
from .channel import ChannelSession, TurnAnswer, _Attempt, _Sink, _Turn

log = logging.getLogger(__name__)


class GenerationMixin:
    """The generation path of a turn. Mixed into ``DMBrain``; holds no state of its own."""

    async def _apply_consistency(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history: list[dict[str, str]],
        answer: str,
        check: Callable[[str], list[Violation]] | None,
    ) -> str:
        """The consistency guard (ADR 045): check the answer against the world state and, on a
        violation, regenerate **once** with a concrete German correction appended (the echo/intro
        nudge mechanism). Strictly fail-open — a guard error, an empty retry or a still-violating
        retry all deliver an answer anyway; the guard never blocks the session. Max one retry.

        Marker hygiene: markers the discarded first answer queued must not survive it — snapshot
        + clear the pending queues before the retry (whose own :meth:`_guarded_answer` re-queues
        its markers) and restore the snapshot only if the retry is discarded (mirrors ``redo``)."""
        if check is None or not answer:
            return answer
        try:
            violations = check(answer)
        except Exception:
            log.exception("consistency guard raised — delivering unchecked (fail-open)")
            return answer
        if not violations:
            return answer
        found = ",".join(f"{v.kind}:{v.npc}" for v in violations)
        log.warning("[consistency] violated (%s) — regenerating once", found)
        snapshot, session.pending = session.pending, empty_markers()
        nudged = f"{user_msg}\n{retry_nudge_de(violations)}"
        try:
            retry, _errored = await self._guarded_answer(session, nudged, labels, history)
        except LLMPausedError:
            retry = None  # the backend paused between the two calls — fail-open like an empty retry
        if not retry:
            # Kind by kind, and only where the first answer had queued something: a kind it left
            # empty keeps whatever the discarded retry queued (unchanged behaviour).
            for kind, reqs in snapshot.items():
                if reqs:
                    session.pending[kind] = reqs
            log.warning("[consistency] retry came back empty — keeping the first answer (fail-open)")
            return answer
        try:
            still = check(retry)
        except Exception:
            still = []
        retry_ok = not still
        if not retry_ok:
            log.warning("[consistency] retry still violates (%s) — delivering anyway (fail-open)",
                        ",".join(f"{v.kind}:{v.npc}" for v in still))
        log.info("[consistency] regenerated=1 violations=%s retry_ok=%s", found, retry_ok)
        return retry

    async def _chat_once(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, dict[str, list]]:
        """One non-streaming LLM call for ``user_msg`` on top of ``history_prefix`` → (sanitised
        answer, ``{kind: parsed requests}`` keyed by the marker registry, ADR 051). The raw
        building block of :meth:`_guarded_answer`: a batch turn's first attempt, and the
        echo-guard retry of every turn, streamed ones included."""
        system, messages, options = self._build_request(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature)
        with caller_reports_cut():  # the ✂ line is written below, with the dropped characters
            raw = await self._client.chat(system, messages, options=options)
        # narration call's token counts (for [latency]).
        self.last_llm_stats = self._client.last_stats
        # Debug aid (lands in debug.log only — 🪵 is filtered off the console + terminal mirror):
        # the raw LLM output BEFORE marker-stripping, so we can see whether the model emitted a
        # <<TEST …>> marker at all (the prime suspect when the dice-marker flow doesn't fire).
        log.info("🪵 LLM roh: %s", raw.replace("\n", " ⏎ "))
        # Replay capture (ADR 046): the raw text with markers intact. Each call overwrites, so
        # after an echo-guard/consistency retry the KEPT answer's raw is what the autosave gets.
        session.replay_gen = {"raw": raw}
        answer, markers, dropped = finalize_answer_trimmed(raw, labels, self._profile)
        self._log_cut(dropped)
        return answer, markers

    @staticmethod
    def _answer_problem(answer: str, user_msg: str, prev_answer: str) -> tuple[str, str] | None:
        """``(log label, retry nudge)`` when the answer parrots a player line (D43/ADR 018) or
        re-narrates the DM's own previous answer (W4/ADR 019); ``None`` when the answer is fine."""
        if not answer:
            return None
        if is_echo(answer, user_msg):
            return "parrots a player line", _ECHO_NUDGE
        if is_self_repetition(answer, prev_answer):
            return "re-narrates the previous answer", _REPEAT_NUDGE
        return None

    @staticmethod
    def _prev_answer(history_prefix: list[dict[str, str]]) -> str:
        """The DM's most recent stored answer (for the self-repetition check), or ''."""
        if history_prefix and history_prefix[-1].get("role") == "assistant":
            return history_prefix[-1].get("content", "")
        return ""

    async def _stream_once(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        sink: _Sink,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> _Attempt:
        """One streamed LLM call — the streaming counterpart of :meth:`_chat_once`. Drives
        ``chat_stream`` through a :class:`StreamAssembler` and speaks sentences via the sink as
        they're ready. Degrades on a mid-stream error — keeps what was spoken, flags the attempt
        ``errored``, never raises out of a half-spoken turn."""
        system, messages, options = self._build_request(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature)
        assembler = StreamAssembler(labels, self._profile)
        errored = False
        spoke_any = False
        agen = self._client.chat_stream(system, messages, options=options)
        with caller_reports_cut():  # the ✂ line is written below, with the dropped characters
            try:
                async for delta in agen:
                    for sentence in assembler.feed(delta):
                        if has_speakable_content(sentence):  # skip a lone "."/quote/backtick (don't synth it)
                            await sink.on_sentence(sentence)
                            spoke_any = True
                    if assembler.stopped:
                        break  # a mid-text speaker label — abort the stream, keep the narration
                    if sink.should_abort is not None and sink.should_abort():
                        break  # paused (ADR 013): stop emitting; resume won't replay
            except LLMPausedError:
                # Raised only before the first delta (the failover's rule): nothing was said, so
                # this is no half-spoken turn to keep — the caller puts the turn aside.
                raise
            except Exception:
                log.exception("streaming turn failed mid-generation — keeping the partial answer")
                errored = True
            finally:
                await agen.aclose()  # closes the httpx stream (the client-side stop)
        self.last_llm_stats = self._client.last_stats
        log.info("🪵 LLM roh (stream): %s", assembler.raw.replace("\n", " ⏎ "))
        # Replay capture (ADR 046) — an echo-guard retry overwrites this via _chat_once, so the
        # kept answer's raw wins (batch-path parity).
        session.replay_gen = {"raw": assembler.raw}
        result = assembler.finish()
        self._log_cut(result.dropped)
        return _Attempt(result.answer, result.markers, list(result.remaining), spoke_any, errored)

    def _log_cut(self, dropped: int) -> None:
        """The ✂ line of a turn the backend reported as cut at its output cap or spoken budget,
        naming how many characters of the dangling last sentence fell away (0: the answer ended
        on a sentence end anyway). Written here, not in the client, because only
        ``finalize_answer_trimmed`` knows the count (ADR 061, amendment 2026-11-13, second).
        Ollama reports no cut, so no line there (progress.md, open point)."""
        stats = self.last_llm_stats or {}
        if not stats.get("truncated"):
            return
        log.warning(
            "✂ Antwort an der Ausgabegrenze abgeschnitten (%s/%s Tokens), %d Zeichen am Ende weggefallen",
            stats.get("cut_tokens", "?"), stats.get("cap") or "?", dropped,
        )

    async def _guarded_answer(
        self,
        session: ChannelSession,
        user_msg: str,
        labels: list[str],
        history_prefix: list[dict[str, str]],
        *,
        sink: _Sink | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str | None, bool]:
        """One DM answer for ``user_msg`` behind the echo guard (D43/ADR 018 + W4) — the single
        generation path of every turn. ``sink=None`` asks the LLM in one batch call
        (:meth:`_chat_once`); with a sink the first attempt streams (:meth:`_stream_once`).

        If the answer merely parrots a player line or re-narrates the DM's own previous answer,
        retry once with a corrective nudge — always a plain batch call, the corrective rare path.
        If the retry misfires again the turn is suppressed: nothing spoken, nothing stored
        (degenerate turns in history self-reinforce). A streamed attempt is
        only retried while nothing was spoken — an echo/repetition is held back by the assembler's
        last-sentence rule for short answers; a half-spoken or errored turn is never retried.

        Speaks what a streamed turn still holds back and queues the kept answer's markers.
        Returns ``(answer, errored)``: ``answer`` is ``None`` for a suppressed turn, ``errored``
        says the stream broke mid-generation."""
        streaming = sink is not None
        prev = self._prev_answer(history_prefix)
        if sink is None:
            attempt = _Attempt(*await self._chat_once(session, user_msg, labels, history_prefix, num_predict=num_predict, temperature=temperature))
        else:
            attempt = await self._stream_once(session, user_msg, labels, history_prefix, sink, num_predict=num_predict, temperature=temperature)
            prev = self._prev_answer(history_prefix)  # the streamed path has always read it after the stream
        answer, markers, remaining = attempt.answer, attempt.markers, attempt.remaining
        suppressed = False
        problem = None if (attempt.errored or attempt.spoke_any) else self._answer_problem(answer, user_msg, prev)
        if problem is not None:
            label, nudge = problem
            log.warning("echo guard%s: answer %s (%r) — retrying once", " (stream)" if streaming else "", label, answer)
            nudged = f"{user_msg}\n{nudge}"
            try:
                answer, markers = await self._chat_once(session, nudged, labels, history_prefix, num_predict=num_predict, temperature=temperature)
            except LLMPausedError:
                raise  # nothing was spoken (a retry only happens then) — the turn is put aside, not suppressed
            except Exception:
                if not streaming:
                    raise  # a batch turn has always let a failed retry propagate
                log.exception("echo-guard retry failed — suppressing the turn")
                answer, markers = "", empty_markers()
            if self._answer_problem(answer, user_msg, prev) is not None:
                log.warning("echo guard: the retry misfired again — suppressing the turn")
                if not streaming:
                    # Kept deviation: a suppressed batch turn leaves here, before _queue_markers,
                    # so its replay capture has no "markers" key, while a suppressed streamed
                    # turn goes on and records empty markers. Why: aligning the two would change
                    # what the replay journal (ADR 046) records, and this split changes nothing.
                    return None, False
                answer, markers = "", empty_markers()
            suppressed = streaming and not answer
            remaining = [answer] if answer else []
        elif attempt.spoke_any and not attempt.errored and is_self_repetition(answer, prev):
            # A long repetition streams sentence-by-sentence before finish() can judge it — too
            # late to retract audio. Keep history parity (stored == spoken) but flag it loudly
            # for the tuning loop (W4 visibility).
            log.warning("echo guard: streamed answer re-narrated the previous one (already spoken)")
        if sink is not None:
            for sentence in remaining:
                if sink.should_abort is not None and sink.should_abort():
                    break
                if has_speakable_content(sentence):
                    await sink.on_sentence(sentence)
        self._queue_markers(session, markers)
        return (None if suppressed else answer), attempt.errored

    async def _run_turn(
        self,
        session: ChannelSession,
        turn: _Turn,
        history: list[dict[str, str]],
        *,
        sink: _Sink | None = None,
        check: Callable[[str], list[Violation]] | None = None,
        is_weak: Callable[[str], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """The turn core, shared by the batch and the streaming path of every turn kind
        (respond, redo, opening): the guarded answer (:meth:`_guarded_answer`), the two
        regenerate-once guards a batch turn can carry — the intro guard (``is_weak``, ADR 041
        follow-up) and the consistency guard (``check``, ADR 045) — and the history entry, whose
        user message ``turn.stored`` then points at (``!redo``).
        Returns the answer for the table as a :class:`TurnAnswer` carrying ``turn.user_msg`` —
        ``""`` when the echo guard suppressed the turn (D43): content-less to the cog, the pair
        stays out of history.

        ``check`` and ``is_weak`` are for batch turns only: a streamed answer is already spoken
        when they could judge it, so the streaming entry points never pass them."""
        user_msg, labels = turn.user_msg, turn.labels
        answer, errored = await self._guarded_answer(
            session, user_msg, labels, history,
            sink=sink, num_predict=num_predict, temperature=temperature,
        )
        if answer and is_weak is not None and is_weak(answer):
            log.warning("intro guard: opening came out weak — regenerating once")
            nudged = f"{user_msg}\n{INTRO_RETRY_NUDGE}"
            try:
                retry, _errored = await self._guarded_answer(
                    session, nudged, labels, history, num_predict=num_predict, temperature=temperature
                )
            except LLMPausedError:
                retry = None  # the backend paused between the two calls — the first opening stands
            if retry:
                answer = retry  # keep the retry even if still weak — never speak less than we had
        if answer is None:
            return TurnAnswer("", user_msg)
        answer = await self._apply_consistency(session, user_msg, labels, history, answer, check)
        stored = answer
        if errored and stored:
            stored = f"{stored} … [Antwort unterbrochen]"  # noted in history; never spoken
        turn.stored = self._append_turn(history, user_msg, stored)
        return TurnAnswer(answer, user_msg)
