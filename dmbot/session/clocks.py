"""Consequence clocks (ADR 047) and in-game time (ADR 048/059) for
:class:`~dmbot.runtime.SessionRuntime`: tick/untick a clock, advance the session's clock by a
scene change or a narrated turn.

A mixin (ADR 065): its methods are methods of the one ``SessionRuntime`` object — ``self`` is
the runtime, all state is created in its ``__init__``. The clock *panel* lives in
``session/panels.py``.
"""
from __future__ import annotations

import logging

from ..memory.gametime import deadline_note_de
from ..memory.state import Clock, clock_full_note_de

log = logging.getLogger(__name__)


class ClocksMixin:
    """Clock mutators and time advances. Mixed into ``SessionRuntime``; holds no state of its own."""

    # ----- Consequence clocks (ADR 047) -----------------------------------------------------

    @property
    def clocks_enabled(self) -> bool:
        """``DM_CLOCKS`` — the one place the switch is read."""
        return self._clocks

    def _tick_clock(self, channel, clock_id: str) -> Clock | None:
        """Deterministically advance a clock one segment (golden rule #3) — the single mutator
        shared by ``!uhr tick`` and the ``<<UHR>>`` confirm/auto path. Rejects unknown ids and
        already-full clocks (returns ``None``). A fresh fill queues the one-shot ``[Regie]``
        consequence note for the next DM turn (ADR 047 #8). The caller persists + refreshes the
        prompt + updates the panel."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        clock = state.tick_clock(clock_id)
        if clock is None:
            return None
        if clock.full:
            self._brain.add_gm_note(cid, clock_full_note_de(clock))
            log.info("⌛ Uhr '%s' (%s) ist voll — Konsequenz-Hinweis für den nächsten Turn "
                     "eingereiht", clock.name, clock.id)
        return clock

    def _untick_clock(self, channel, clock_id: str) -> Clock | None:
        """Take one segment back (``!uhr zurück``). Unticking a *full* clock retracts a
        still-queued consequence note — an accidental fill must not fire (ADR 047 #8)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None:
            return None
        clock = state.find_clock(clock_id)
        if clock is None:
            return None
        if clock.full and self._brain.discard_gm_notes(cid, containing=f"„{clock.name}“"):
            log.info("⏱ Uhr '%s': eingereihter Konsequenz-Hinweis zurückgezogen", clock.name)
        return state.untick_clock(clock_id)

    # ----- In-game time + deadlines (ADR 048) -----------------------------------------------

    async def _advance_time(self, channel, minutes: int) -> int:
        """Deterministically advance the in-game clock (golden rule #3) — the single mutator
        shared by ``!zeit``, the ``<<ZEIT>>`` confirm/auto path and the scene-change default
        advance. Queues the one-shot ``[Regie]`` note for each newly expired deadline
        (ADR 048 #8), persists, refreshes the prompt and the pressure panel. Returns the
        applied minutes (0 = no session or a non-positive amount)."""
        cid = self._brain_channel(channel)
        state = self._state.get(cid)
        if state is None or minutes <= 0:
            return 0
        expired = state.advance_time(minutes)
        for dl in expired:
            self._brain.add_gm_note(cid, deadline_note_de(dl.label))
            log.info("⏳ Frist '%s' (%s) verstrichen — Konsequenz-Hinweis für den nächsten "
                     "Turn eingereiht", dl.label, dl.id)
        self._persist_and_refresh(channel)
        await self.update_clock_panel()
        await self.update_player_panel()  # the panel shows the clock + the deadline (D107)
        return minutes

    async def advance_scene_time(self, channel) -> int:
        """The default time cost of a *real* scene change (ADR 048 #10 / ADR 059 #2, the larger of
        the two increments) — called by every move path after a successful move to a different
        scene. ``DM_SCENE_TIME_ADVANCE=0`` disables it. Returns the applied minutes."""
        return await self._advance_time(channel, self._scene_time_advance)

    async def advance_turn_time(self, channel) -> int:
        """The per-turn heartbeat of the in-game clock (ADR 059 #2).

        Small and unconditional: a clock moved only by the ``<<ZEIT>>`` marker stands still when
        the model emits none. The marker keeps its job (deliberate jumps, ADR 059 #3) — an
        accelerator on a clock that already runs. ``DM_TURN_TIME_ADVANCE=0`` disables it."""
        return await self._advance_time(channel, self._turn_time_advance)
