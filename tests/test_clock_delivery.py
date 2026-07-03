"""The delivery half of <<UHR>> (ADR 047): ``uhr_verdict`` (the pure clamp rule shared with
dm-eval), ``_handle_uhr`` (confirm button vs auto-apply, unknown ids, the +1-per-clock-per-turn
clamp, full clocks), the confirm callback, the runtime's ``_tick_clock``/``_untick_clock``
mutators (full → GM note queued / retracted) and the edit-in-place panel. Stub runtime (init
skipped, attrs injected) with a REAL WorldState — mirroring tests/test_flag_delivery.py."""

from __future__ import annotations

import asyncio
import logging

from dmbot.memory.state import WorldState
from dmbot.rules.marker import ClockTickRequest
from dmbot.runtime import SessionRuntime
from dmbot.voice.delivery import DeliveryPipeline, uhr_verdict


class _Channel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def send(self, content: str, view=None):
        self.sent.append((content, view))


class _Brain:
    def __init__(self, reqs: list[ClockTickRequest]) -> None:
        self._reqs = reqs
        self.notes: list[str] = []
        self.discarded: list[str] = []

    def take_pending_uhr(self, channel_id):
        reqs, self._reqs = self._reqs, []
        return reqs

    def add_gm_note(self, channel_id, note):
        self.notes.append(note)

    def discard_gm_notes(self, channel_id, *, containing):
        self.discarded.append(containing)
        before = len(self.notes)
        self.notes = [n for n in self.notes if containing not in n]
        return before - len(self.notes)


class _NoUhrBrain:
    """Deliberately WITHOUT take_pending_uhr — pins the getattr guard in _handle_uhr, which
    keeps tests/test_delivery.py's fake brain untouched (clocks need no adventure, so the
    ADR-043 adventure-guard trick doesn't apply here)."""


def _state_with_clocks() -> WorldState:
    state = WorldState()
    state.add_clock("Arbites-Ermittlung", 6)   # id: arbites-ermittlung
    alarm = state.add_clock("Alarm", 4)        # id: alarm
    alarm.filled = 4                           # already full
    return state


def _pipeline(reqs: list[ClockTickRequest], *, confirm: bool, brain=None):
    rt = object.__new__(SessionRuntime)
    rt._brain = brain if brain is not None else _Brain(reqs)
    rt._brain_channel = lambda ch: 7
    rt._state = {7: _state_with_clocks()}
    rt._flag_confirm = confirm
    rt._persisted = []
    rt._persist_and_refresh = lambda channel: rt._persisted.append(channel)
    rt._panel_updates = []

    async def _panel():
        rt._panel_updates.append(True)
    rt.update_clock_panel = _panel
    pipeline = DeliveryPipeline(rt, post_deliver=lambda *a, **k: None)
    return pipeline, rt


def _req(cid: str, parsed: bool = True) -> ClockTickRequest:
    return ClockTickRequest(clock_id=cid, raw=f"<<UHR {cid}>>", parsed=parsed)


# -- uhr_verdict (pure) ------------------------------------------------------------------------

def test_uhr_verdict_rules() -> None:
    known, full = {"arbites"}, set()
    assert uhr_verdict(_req("arbites"), known=known, full=full, seen=set()) == "ok"
    assert uhr_verdict(_req("nope"), known=known, full=full, seen=set()) == "rejected"
    assert uhr_verdict(_req("", parsed=False), known=known, full=full, seen=set()) == "rejected"
    assert uhr_verdict(_req("arbites"), known=known, full=full, seen={"arbites"}) == "rejected"  # +1 clamp
    assert uhr_verdict(_req("arbites"), known=known, full={"arbites"}, seen=set()) == "rejected"  # full
    assert uhr_verdict(_req("ARBITES"), known=known, full=full, seen=set()) == "ok"  # case-tolerant


# -- _handle_uhr -------------------------------------------------------------------------------

def test_handle_uhr_posts_confirm_view_when_confirm_on() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req("arbites-ermittlung")], confirm=True)
    asyncio.run(pipeline._handle_uhr(channel))
    assert len(channel.sent) == 1
    assert "Arbites-Ermittlung" in channel.sent[0][0] and "0/6 → 1/6" in channel.sent[0][0]
    assert channel.sent[0][1] is not None  # a ClockView rides along
    assert rt._state[7].find_clock("arbites-ermittlung").filled == 0  # NOT yet applied
    assert rt._persisted == [] and rt._panel_updates == []


def test_handle_uhr_auto_applies_when_confirm_off() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req("arbites-ermittlung")], confirm=False)
    asyncio.run(pipeline._handle_uhr(channel))
    assert channel.sent == []  # no button
    assert rt._state[7].find_clock("arbites-ermittlung").filled == 1
    assert len(rt._persisted) == 1 and len(rt._panel_updates) == 1


def test_unknown_full_duplicate_and_unparsed_are_rejected(caplog) -> None:
    channel = _Channel()
    reqs = [_req("nope"), _req("", parsed=False), _req("alarm"),  # unknown / garbled / full
            _req("arbites-ermittlung"), _req("arbites-ermittlung")]  # duplicate → +1 clamp
    pipeline, rt = _pipeline(reqs, confirm=False)
    with caplog.at_level(logging.INFO):
        asyncio.run(pipeline._handle_uhr(channel))
    assert rt._state[7].find_clock("arbites-ermittlung").filled == 1  # exactly ONE tick
    assert rt._state[7].find_clock("alarm").filled == 4               # untouched
    assert "nope" in caplog.text  # rejections are logged, never applied


def test_confirm_callback_ticks_persists_and_updates_panel() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True)

    class _Interaction:
        def __init__(self) -> None:
            self.edits: list[str] = []

        async def edit_original_response(self, content: str):
            self.edits.append(content)

    interaction = _Interaction()
    asyncio.run(pipeline._make_uhr_confirm(channel, "arbites-ermittlung")(interaction))
    assert rt._state[7].find_clock("arbites-ermittlung").filled == 1
    assert rt._persisted == [channel] and rt._panel_updates == [True]
    assert "1/6" in interaction.edits[0]


def test_confirm_callback_degrades_when_clock_gone_or_full() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True)
    rt._state[7].remove_clock("arbites-ermittlung")

    class _Interaction:
        def __init__(self) -> None:
            self.edits: list[str] = []

        async def edit_original_response(self, content: str):
            self.edits.append(content)

    interaction = _Interaction()
    asyncio.run(pipeline._make_uhr_confirm(channel, "arbites-ermittlung")(interaction))
    assert rt._persisted == []
    assert "Nicht mehr aktuell" in interaction.edits[0]


def test_handle_uhr_without_take_pending_uhr_is_a_noop() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True, brain=_NoUhrBrain())
    asyncio.run(pipeline._handle_uhr(channel))  # would raise AttributeError without the guard
    assert channel.sent == []


# -- runtime mutators (_tick_clock / _untick_clock) ----------------------------------------------

def _runtime():
    rt = object.__new__(SessionRuntime)
    rt._brain = _Brain([])
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState()}
    rt._state[7].add_clock("Alarm", 4)
    return rt


def test_tick_clock_queues_gm_note_exactly_on_fill() -> None:
    rt = _runtime()
    for _ in range(3):
        assert rt._tick_clock(object(), "alarm") is not None
    assert rt._brain.notes == []  # not full yet — no note
    clock = rt._tick_clock(object(), "alarm")
    assert clock is not None and clock.full
    assert len(rt._brain.notes) == 1 and "„Alarm“" in rt._brain.notes[0]
    assert rt._tick_clock(object(), "alarm") is None  # full → not tickable


def test_untick_from_full_retracts_the_queued_note() -> None:
    rt = _runtime()
    for _ in range(4):
        rt._tick_clock(object(), "alarm")
    assert len(rt._brain.notes) == 1
    clock = rt._untick_clock(object(), "alarm")
    assert clock is not None and clock.filled == 3
    assert rt._brain.notes == []  # the accidental fill never fires


# -- panel (edit-in-place, pause-panel pattern) ---------------------------------------------------

class _PanelMsg:
    def __init__(self) -> None:
        self.contents: list[str] = []

    async def edit(self, content: str):
        self.contents.append(content)

    async def delete(self):
        pass


class _PanelChannel:
    def __init__(self) -> None:
        self.posted: list[str] = []

    async def send(self, content: str):
        self.posted.append(content)
        return _PanelMsg()


def _panel_runtime():
    rt = object.__new__(SessionRuntime)
    rt._active_vc_id = 7
    rt._state = {7: WorldState()}
    rt._text_channel = _PanelChannel()
    rt._clock_panel = None
    return rt


def test_update_clock_panel_posts_then_edits_in_place() -> None:
    rt = _panel_runtime()
    rt._state[7].add_clock("Alarm", 4)
    asyncio.run(rt.update_clock_panel())
    assert len(rt._text_channel.posted) == 1 and rt._clock_panel is not None
    rt._state[7].tick_clock("alarm")
    asyncio.run(rt.update_clock_panel())
    assert len(rt._text_channel.posted) == 1  # edited, not re-posted (no spam)
    assert rt._clock_panel.contents and "◉○○○" in rt._clock_panel.contents[-1]


def test_update_clock_panel_removes_panel_when_no_clocks() -> None:
    rt = _panel_runtime()
    rt._state[7].add_clock("Alarm", 4)
    asyncio.run(rt.update_clock_panel())
    rt._state[7].remove_clock("alarm")
    asyncio.run(rt.update_clock_panel())
    assert rt._clock_panel is None  # cleared via clear_panel
