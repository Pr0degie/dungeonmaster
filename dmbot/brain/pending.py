"""What the cogs take out of :class:`~dmbot.orchestrator.DMBrain` and put into it between
turns: the pending-marker store (ADR 051), the one-shot GM notes (ADR 047), the last action(s)
the roll router reads (ADR 014), the replay capture (ADR 046) and the history restore on join
(D41).

A mixin (ADR 065): its methods are methods of the one ``DMBrain`` object — ``self`` is the
brain, all state is created in ``DMBrain.__init__`` and kept per channel in a
``ChannelSession``. No model call and no log line in here.
"""
from __future__ import annotations

from ..rules.marker import (
    ClockTickRequest,
    ErledigtRequest,
    ManifestRequest,
    SceneRequest,
    TestRequest,
    ZeitRequest,
    empty_markers,
)


class PendingMixin:
    """The cog-facing accessors of a channel's state. Mixed into ``DMBrain``; holds no state of
    its own."""

    def take_pending(self, kind: str, channel_id: int) -> list:
        """Return and clear the queued requests of one marker-registry kind (ADR 051). The
        named ``take_pending_<kind>`` wrappers below stay the public surface — dicecog, the
        delivery handlers and dm-eval call those."""
        pending = self._session(channel_id).pending
        reqs, pending[kind] = pending[kind], []
        return reqs

    def _drop_pending(self, channel_id: int) -> None:
        """Drop every queued marker request of the channel — a redo/reset supersedes them."""
        self._session(channel_id).pending = empty_markers()

    def take_pending_tests(self, channel_id: int) -> list[TestRequest]:
        """Return and clear the dice tests the last DM turn requested (cog posts the buttons)."""
        return self.take_pending("tests", channel_id)

    def tests_narrator(self, channel_id: int) -> str | None:
        """The backend that narrated the turn whose ``<<TEST>>`` markers are pending (D140) —
        ``"claude"``, ``"ollama"`` or None (Ollama-only bot, no failover)."""
        return self._session(channel_id).tests_narrator

    def take_pending_manifests(self, channel_id: int) -> list[ManifestRequest]:
        """Return and clear the psychic Manifest requests the last DM turn made (ADR 022) — the
        cog posts a button for each that rolls the Manifest Test + bookkeeps Warp Charge."""
        return self.take_pending("manifests", channel_id)

    def take_pending_scenes(self, channel_id: int) -> list[SceneRequest]:
        """Return and clear the scene-transition requests the last DM turn made (ADR 026) — the cog
        validates the target against the adventure and posts a confirm button for the move."""
        return self.take_pending("scenes", channel_id)

    def take_pending_erledigt(self, channel_id: int) -> list[ErledigtRequest]:
        """Return and clear the scene-element flag requests the last DM turn made (ADR 043) — the
        delivery pipeline validates each id against the current scene card and confirms/applies."""
        return self.take_pending("erledigt", channel_id)

    def take_pending_uhr(self, channel_id: int) -> list[ClockTickRequest]:
        """Return and clear the clock-tick requests the last DM turn made (ADR 047) — the delivery
        pipeline validates each id against ``WorldState.clocks``, clamps to +1 per clock per turn
        and confirms/applies the tick."""
        return self.take_pending("uhr", channel_id)

    def take_pending_zeit(self, channel_id: int) -> list[ZeitRequest]:
        """Return and clear the time-advance requests the last DM turn made (ADR 048) — the
        delivery pipeline honours only the first valid one, clamps to +12h per turn and
        confirms/applies the advance."""
        return self.take_pending("zeit", channel_id)

    def add_gm_note(self, channel_id: int, note: str) -> None:
        """Queue a one-shot GM directive for the NEXT turn's user message (``[Regie] …`` line,
        ADR 047 — e.g. "clock X is full, the consequence hits now"). Code-queued only, never
        LLM-written; drained by ``_prepare_turn`` like dice results."""
        if note:
            self._session(channel_id).gm_notes.append(note)

    def discard_gm_notes(self, channel_id: int, *, containing: str) -> int:
        """Drop still-queued GM notes containing ``containing`` (ADR 047: ``!uhr zurück`` from a
        full clock must retract the not-yet-fired consequence note). Returns how many went."""
        session = self._session(channel_id)
        keep = [n for n in session.gm_notes if containing not in n]
        dropped = len(session.gm_notes) - len(keep)
        session.gm_notes = keep
        return dropped

    def last_action(self, channel_id: int) -> tuple[str, str] | None:
        """The latest player action (display-name, text) the last turn answered, or None — the
        roll-detection router (ADR 014) classifies this. None on a results-only turn."""
        return self._session(channel_id).last_action

    def last_actions(self, channel_id: int) -> list[tuple[str, str]]:
        """Every speaker's action of the turn just answered, one ``(display-name, text)`` each.

        The roll-detection router (ADR 014) walks this instead of :meth:`last_action`, so a turn
        in which two players each declared something can produce a test for both (D111).
        """
        return list(self._session(channel_id).last_actions)

    def take_replay_turn(self, channel_id: int) -> dict | None:
        """Return and clear the last turn's replay-journal fields (ADR 046): the structured
        input (``lines``/``results``/``opening``), the kept answer's ``raw`` LLM text and the
        ``markers`` it queued. ``None`` when nothing was captured (e.g. a stubbed brain path).
        The autosave merges this into the turn record; ``load_recent`` ignores the extras."""
        session = self._session(channel_id)
        turn, session.replay_turn = session.replay_turn, None
        gen, session.replay_gen = session.replay_gen, None
        if turn is None and gen is None:
            return None
        return {**(turn or {}), **(gen or {})}

    def last_user_msg(self, channel_id: int) -> str | None:
        """The user message of the most recent turn (for history autosave, D41), or None."""
        last = self._session(channel_id).last_turn
        return last.user_msg if last else None

    def restore_history(self, channel_id: int, turns: list[tuple[str, str]]) -> int:
        """Restore prior ``(user_msg, answer)`` turns into this channel's history on join — crash
        recovery (D41). Only fills an **empty** history (never clobbers a live session) and respects
        the history cap. Returns how many turns were restored. Note: ``last_turn`` is *not*
        restored, so ``!redo`` is unavailable for the restored last turn (known limitation)."""
        session = self._session(channel_id)
        if session.history:
            return 0
        history: list[dict[str, str]] = []
        for user_msg, answer in turns:
            if not answer.strip():
                continue  # marker-only/suppressed turns: don't re-teach empty answers on restore (D43)
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": answer})
        if len(history) > self._max_messages:
            history = history[len(history) - self._max_messages:]
        session.history = history
        return len(history) // 2
