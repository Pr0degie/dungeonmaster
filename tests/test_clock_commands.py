"""!uhr neu/tick/zurück/weg + !uhren (ADR 047): the human-owned clock commands in the thin
ClockCog. Manual = apply immediately (the human IS the confirm), size validated against
CLOCK_SIZES, unknown ids reply an error. Stub runtime, `Cog.<cmd>.callback(cog, ctx, ...)`
(the test_flag_commands pattern)."""

from __future__ import annotations

import asyncio
import types

from dmbot.memory.state import WorldState
from dmbot.runtime import SessionRuntime
from dmbot.voice.clockcog import ClockCog


class _Ctx:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.channel = object()
        self.guild = types.SimpleNamespace(id=1)

    async def send(self, content: str = "", **kwargs) -> None:
        if content:
            self.sent.append(content)


def _runtime():
    rt = object.__new__(SessionRuntime)
    rt._brain = types.SimpleNamespace(
        add_gm_note=lambda cid, note: rt._notes.append(note),
        discard_gm_notes=lambda cid, containing: 0,
    )
    rt._notes = []
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState()}
    rt._persisted = []
    rt._persist_and_refresh = lambda ch: rt._persisted.append(ch)
    rt._panel_updates = []

    async def _panel():
        rt._panel_updates.append(True)
    rt.update_clock_panel = _panel

    async def _clear(attr):
        rt._panel_updates.append(attr)
    rt.clear_panel = _clear
    return rt


def _cog(rt) -> ClockCog:
    cog = object.__new__(ClockCog)
    cog._rt = rt
    return cog


def test_uhr_neu_creates_clock_and_echoes_id() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(ClockCog.neu.callback(_cog(rt), ctx, "Arbites-Ermittlung", 6))
    clock = rt._state[7].find_clock("arbites-ermittlung")
    assert clock is not None and clock.size == 6 and clock.filled == 0
    assert len(rt._persisted) == 1 and rt._panel_updates == [True]
    assert any("`arbites-ermittlung`" in m and "○○○○○○" in m for m in ctx.sent)


def test_uhr_neu_rejects_invalid_size() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(ClockCog.neu.callback(_cog(rt), ctx, "Alarm", 5))
    assert rt._state[7].clocks == [] and rt._persisted == []
    assert any("Ungültige Größe" in m for m in ctx.sent)


def test_uhr_tick_advances_and_reports_full() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].add_clock("Alarm", 4)
    rt._state[7].find_clock("alarm").filled = 3
    asyncio.run(ClockCog.tick.callback(_cog(rt), ctx, "alarm"))
    assert rt._state[7].find_clock("alarm").full
    assert any("VOLL" in m for m in ctx.sent)
    assert len(rt._notes) == 1  # the consequence note is queued via the shared mutator
    # a further tick on the full clock is refused with a hint, not applied
    asyncio.run(ClockCog.tick.callback(_cog(rt), ctx, "alarm"))
    assert any("bereits voll" in m for m in ctx.sent)
    assert rt._state[7].find_clock("alarm").filled == 4


def test_uhr_tick_unknown_id_replies_error() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(ClockCog.tick.callback(_cog(rt), ctx, "nope"))
    assert rt._persisted == []
    assert any("Unbekannte Uhr" in m for m in ctx.sent)


def test_uhr_zurueck_takes_a_segment_back() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].add_clock("Alarm", 4)
    rt._state[7].find_clock("alarm").filled = 2
    asyncio.run(ClockCog.zurueck.callback(_cog(rt), ctx, "alarm"))
    assert rt._state[7].find_clock("alarm").filled == 1
    assert len(rt._persisted) == 1


def test_uhr_weg_removes_clock() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].add_clock("Alarm", 4)
    asyncio.run(ClockCog.weg.callback(_cog(rt), ctx, "alarm"))
    assert rt._state[7].clocks == []
    assert len(rt._persisted) == 1
    assert any("entfernt" in m for m in ctx.sent)


def test_uhren_without_session_or_clocks() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state = {}
    asyncio.run(ClockCog.uhren.callback(_cog(rt), ctx))
    assert any("erst `!j`" in m for m in ctx.sent)
    rt2, ctx2 = _runtime(), _Ctx()
    asyncio.run(ClockCog.uhren.callback(_cog(rt2), ctx2))
    assert any("Keine Uhren" in m for m in ctx2.sent)


def test_uhren_reposts_the_panel_at_the_bottom() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].add_clock("Alarm", 4)
    asyncio.run(ClockCog.uhren.callback(_cog(rt), ctx))
    assert rt._panel_updates == ["_clock_panel", True]  # clear (re-anchor) then re-post
