"""The delivery half of <<ZEIT>> (ADR 048): ``zeit_verdict`` (the pure first-only + 12h-clamp
rule shared with dm-eval), ``_handle_zeit`` (confirm button vs auto-apply, rejections), the
confirm callback and the runtime's ``_advance_time`` mutator (expiry → GM note, persist +
panel). Stub runtime (init skipped, attrs injected) with a REAL WorldState — mirroring
tests/test_clock_delivery.py."""

from __future__ import annotations

import asyncio
import logging

from dmbot.memory.state import WorldState
from dmbot.rules.marker import ZeitRequest
from dmbot.runtime import SessionRuntime
from dmbot.voice.delivery import DeliveryPipeline, zeit_verdict


class _Channel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def send(self, content: str, view=None):
        self.sent.append((content, view))


class _Brain:
    def __init__(self, reqs: list[ZeitRequest]) -> None:
        self._reqs = reqs
        self.notes: list[str] = []

    def take_pending_zeit(self, channel_id):
        reqs, self._reqs = self._reqs, []
        return reqs

    def add_gm_note(self, channel_id, note):
        self.notes.append(note)


class _NoZeitBrain:
    """Deliberately WITHOUT take_pending_zeit — pins the getattr guard in _handle_zeit
    (keeps tests/test_delivery.py's fake brain untouched, the ADR-047 pattern)."""


def _pipeline(reqs: list[ZeitRequest], *, confirm: bool, brain=None):
    rt = object.__new__(SessionRuntime)
    rt._brain = brain if brain is not None else _Brain(reqs)
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState()}
    rt._flag_confirm = confirm
    rt._persisted = []
    rt._persist_and_refresh = lambda channel: rt._persisted.append(channel)
    rt._panel_updates = []

    async def _panel():
        rt._panel_updates.append(True)
    rt.update_clock_panel = _panel
    pipeline = DeliveryPipeline(rt, post_deliver=lambda *a, **k: None)
    return pipeline, rt


def _req(minutes: int | None, raw: str = "") -> ZeitRequest:
    return ZeitRequest(minutes=minutes, raw=raw or f"<<ZEIT +{minutes}m>>",
                       parsed=minutes is not None)


# -- zeit_verdict (pure) ---------------------------------------------------------------------------

def test_zeit_verdict_rules() -> None:
    assert zeit_verdict(_req(30), seen=False) == ("ok", 30)
    assert zeit_verdict(_req(720), seen=False) == ("ok", 720)
    assert zeit_verdict(_req(2000), seen=False) == ("ok", 720)   # clamped to +12h
    assert zeit_verdict(_req(30), seen=True) == ("rejected", 0)  # first-only per turn
    assert zeit_verdict(_req(None), seen=False) == ("rejected", 0)  # unparseable


# -- _handle_zeit ----------------------------------------------------------------------------------

def test_handle_zeit_posts_confirm_view_when_confirm_on() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req(240)], confirm=True)
    asyncio.run(pipeline._handle_zeit(channel))
    assert len(channel.sent) == 1
    assert "+4 Std" in channel.sent[0][0]
    assert channel.sent[0][1] is not None  # a ZeitView rides along
    assert rt._state[7].time_minutes == 480  # NOT yet applied
    assert rt._persisted == [] and rt._panel_updates == []


def test_handle_zeit_auto_applies_when_confirm_off() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req(90)], confirm=False)
    asyncio.run(pipeline._handle_zeit(channel))
    assert channel.sent == []  # no button
    assert rt._state[7].time_minutes == 480 + 90
    assert len(rt._persisted) == 1 and len(rt._panel_updates) == 1


def test_only_the_first_valid_request_is_honoured_and_oversize_is_clamped(caplog) -> None:
    channel = _Channel()
    reqs = [_req(None, raw="<<ZEIT bald>>"), _req(20 * 60), _req(30)]  # garbled / 20h / surplus
    pipeline, rt = _pipeline(reqs, confirm=False)
    with caplog.at_level(logging.INFO):
        asyncio.run(pipeline._handle_zeit(channel))
    assert rt._state[7].time_minutes == 480 + 720  # ONE advance, clamped to 12h
    assert "geklemmt" in caplog.text and "abgelehnt" in caplog.text


def test_confirm_callback_advances_persists_and_updates_panel() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True)

    class _Interaction:
        def __init__(self) -> None:
            self.edits: list[str] = []

        async def edit_original_response(self, content: str):
            self.edits.append(content)

    interaction = _Interaction()
    asyncio.run(pipeline._make_zeit_confirm(channel, 240)(interaction))
    assert rt._state[7].time_minutes == 480 + 240
    assert rt._persisted == [channel] and rt._panel_updates == [True]
    assert "Tag 1, 12:00" in interaction.edits[0]


def test_handle_zeit_without_take_pending_zeit_is_a_noop() -> None:
    channel = _Channel()
    pipeline, _rt = _pipeline([], confirm=True, brain=_NoZeitBrain())
    asyncio.run(pipeline._handle_zeit(channel))  # would raise AttributeError without the guard
    assert channel.sent == []


# -- runtime mutator (_advance_time) ----------------------------------------------------------------

def _runtime():
    rt = object.__new__(SessionRuntime)
    rt._brain = _Brain([])
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState()}
    rt._persisted = []
    rt._persist_and_refresh = lambda channel: rt._persisted.append(channel)
    rt._panel_updates = []

    async def _panel():
        rt._panel_updates.append(True)
    rt.update_clock_panel = _panel
    return rt


def test_advance_time_queues_expiry_note_exactly_once() -> None:
    rt = _runtime()
    rt._state[7].add_deadline("Der Zug nach Hive Sibellus", 60)
    assert asyncio.run(rt._advance_time(object(), 30)) == 30
    assert rt._brain.notes == []  # not due yet
    asyncio.run(rt._advance_time(object(), 60))
    assert len(rt._brain.notes) == 1 and "„Der Zug nach Hive Sibellus“" in rt._brain.notes[0]
    asyncio.run(rt._advance_time(object(), 999))
    assert len(rt._brain.notes) == 1  # latched — fires exactly once
    assert len(rt._persisted) == 3 and len(rt._panel_updates) == 3


def test_advance_time_rejects_nonpositive_and_missing_session() -> None:
    rt = _runtime()
    assert asyncio.run(rt._advance_time(object(), 0)) == 0
    assert asyncio.run(rt._advance_time(object(), -5)) == 0
    rt._state = {}
    assert asyncio.run(rt._advance_time(object(), 30)) == 0
    assert rt._persisted == []


def test_advance_scene_time_uses_the_config_default() -> None:
    rt = _runtime()
    rt._scene_time_advance = 30
    assert asyncio.run(rt.advance_scene_time(object())) == 30
    assert rt._state[7].time_minutes == 480 + 30
    rt._scene_time_advance = 0  # DM_SCENE_TIME_ADVANCE=0 → off
    assert asyncio.run(rt.advance_scene_time(object())) == 0
    assert rt._state[7].time_minutes == 480 + 30
