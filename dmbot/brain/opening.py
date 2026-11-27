"""The opening turn of :class:`~dmbot.orchestrator.DMBrain` (``!start`` / ``!intro``): a
one-off GM-side director instruction instead of player lines, batch or streamed, with dice
suppressed.

A mixin (ADR 065): its methods are methods of the one ``DMBrain`` object — ``self`` is the
brain, all state is created in ``DMBrain.__init__`` and kept per channel in a
``ChannelSession``. The turn itself runs through
``DMBrain._run_turn``.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..llm.sanitize import _ROLE_LABELS
from .channel import _Sink, _Turn


class OpeningMixin:
    """The ``!start`` / ``!intro`` turn. Mixed into ``DMBrain``; holds no state of its own."""

    def _prepare_opening(self, channel_id: int, director_msg: str) -> tuple[str, list[str], list[dict[str, str]]]:
        """Assemble the one-off ``(user_msg, labels, history)`` for the ``!start`` opening turn.

        Unlike :meth:`_prepare_turn` this consumes no buffered player lines and adds no
        ``Spieler:`` line — the opening is a GM-side *director* instruction, not a player action.
        Crucially it clears the session's ``last_action``/``last_actions`` (an opening mid-session
        must not inherit the previous player turn's), which makes
        :meth:`_queue_markers` skip queuing any ``<<TEST>>``/``<<ORT>>``
        marker the model might emit — i.e. **no dice on a briefing** falls out of the existing
        results-only guard for free. Records ``last_turn``
        so the opening can be ``!redo``-ne like any turn, and reuses the same labels (known table
        speakers + role labels) so the anti-puppeting stop sequences still apply."""
        session = self._session(channel_id)
        labels = list(dict.fromkeys(session.known_speakers + _ROLE_LABELS))
        session.last_turn = _Turn(director_msg, labels)
        session.turn_held = False
        session.last_action = None
        session.last_actions = []
        # Replay capture (ADR 046): an opening turn re-feeds its director_msg, not player lines.
        session.replay_turn = {"lines": [], "results": [], "opening": True}
        return director_msg, labels, session.history

    async def _opening(
        self,
        channel_id: int,
        director_msg: str,
        *,
        sink: _Sink | None = None,
        is_weak: Callable[[str], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """The body of :meth:`respond_opening` (``sink=None``) and
        :meth:`respond_opening_streaming`: the one-off director turn through :meth:`_run_turn`."""
        _user_msg, _labels, history = self._prepare_opening(channel_id, director_msg)
        session = self._session(channel_id)
        return await self._run_turn(
            session, session.last_turn, history,
            sink=sink, is_weak=is_weak, num_predict=num_predict, temperature=temperature,
        )

    async def respond_opening(self, channel_id: int, director_msg: str, num_predict: int | None = None,
                              temperature: float | None = None,
                              is_weak: Callable[[str], bool] | None = None) -> str | None:
        """Run the opening-briefing turn (``!start`` / ``!intro test``, batch path): generate one GM
        turn from the ``director_msg`` instruction, append it to history, return the answer. Dice are
        suppressed (see :meth:`_prepare_opening`). ``""`` only on the rare echo-guard suppression.
        ``!intro`` passes a lower ``temperature`` (D83) so the monologue reliably follows the director
        brief instead of wandering into a short generic turn.

        ``is_weak`` (the batch-only intro guard, ADR 041 follow-up): when given and the generated
        opening reads weak (too short / a player figure skipped — the 12B model's high-variance
        failure), regenerate **once** with a firmer nudge before the turn reaches the table. Only the
        kept answer is appended to history. Streaming ``!intro`` can't use this (audio already plays),
        which is why the validated batch path is the one to prefer once synthesis is fast enough."""
        return await self._opening(
            channel_id, director_msg, is_weak=is_weak, num_predict=num_predict, temperature=temperature
        )

    async def respond_opening_streaming(
        self,
        channel_id: int,
        director_msg: str,
        *,
        on_sentence: Callable[[str], Awaitable[None]],
        should_abort: Callable[[], bool] | None = None,
        num_predict: int | None = None,
        temperature: float | None = None,
    ) -> str | None:
        """Streaming variant of :meth:`respond_opening` (the live path, ADR 017): same one-off
        director turn, spoken sentence-by-sentence via ``on_sentence``. Dice stay suppressed.
        ``!intro`` passes a lower ``temperature`` (D83) for steadier instruction-following."""
        return await self._opening(
            channel_id, director_msg, sink=_Sink(on_sentence, should_abort),
            num_predict=num_predict, temperature=temperature,
        )
