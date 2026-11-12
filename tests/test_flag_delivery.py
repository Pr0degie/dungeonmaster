"""The delivery half of <<ERLEDIGT>> (ADR 043): ``_handle_erledigt`` validates each request
against the CURRENT scene card, posts a FlagView per valid element (DM_FLAG_CONFIRM=1) or applies
immediately (=0), and ignores unknown/foreign/duplicate ids. Stub runtime (init skipped, attrs
injected) with a REAL Adventure + WorldState — the flag mutation itself is the real code path."""

from __future__ import annotations

import asyncio
import logging

from dmbot.memory.state import WorldState
from dmbot.rag.adventure import Adventure, Scene
from dmbot.rules.marker import ErledigtRequest
from dmbot.voice.delivery import DeliveryPipeline

from fakes import FakeBrain, make_runtime


class _Channel:
    """Records channel.send calls (content + view)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    async def send(self, content: str, view=None):
        self.sent.append((content, view))


class _Brain(FakeBrain):
    def __init__(self, reqs: list[ErledigtRequest]) -> None:
        super().__init__()
        self._reqs = reqs

    def take_pending_erledigt(self, channel_id):
        reqs, self._reqs = self._reqs, []
        return reqs


def _adventure() -> Adventure:
    return Adventure(scenes=[
        Scene(id="a", title_de="Anfang", opportunities_de=["Die Kiste öffnen."],
              secrets_de=["Bob ist der Täter."]),
        Scene(id="b", title_de="B"),
    ])


def _pipeline(reqs: list[ErledigtRequest], *, confirm: bool, brain=None):
    rt = make_runtime()
    rt._adventure = _adventure()
    rt._brain = brain if brain is not None else _Brain(reqs)
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState(scene_id="a")}
    rt._flag_confirm = confirm
    rt._persisted = []
    rt._persist_and_refresh = lambda channel: rt._persisted.append(channel)
    pipeline = DeliveryPipeline(rt, post_deliver=lambda *a, **k: None)
    return pipeline, rt


def _req(eid: str, parsed: bool = True) -> ErledigtRequest:
    return ErledigtRequest(element_id=eid, raw=f"<<ERLEDIGT {eid}>>", parsed=parsed)


def test_handle_erledigt_posts_confirm_view_when_confirm_on() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req("opp-1"), _req("geh-1")], confirm=True)
    asyncio.run(pipeline._handle_erledigt(channel))
    assert len(channel.sent) == 2  # one proposal per valid element
    assert "Die Kiste öffnen." in channel.sent[0][0] and "opp-1" in channel.sent[0][0]
    assert channel.sent[0][1] is not None  # a FlagView rides along
    assert rt._state[7].scene_flags == {}  # NOT yet applied — the human confirms
    assert rt._persisted == []


def test_handle_erledigt_auto_applies_when_confirm_off() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([_req("opp-1"), _req("geh-1")], confirm=False)
    asyncio.run(pipeline._handle_erledigt(channel))
    assert channel.sent == []  # no button
    assert rt._state[7].resolved_ids("a") == ["opp-1", "geh-1"]
    assert len(rt._persisted) == 1  # one persist+refresh after the loop, not per flag


def test_unknown_foreign_duplicate_and_resolved_ids_are_skipped(caplog) -> None:
    channel = _Channel()
    reqs = [_req("nope"), _req("", parsed=False), _req("opp-1"), _req("opp-1")]
    pipeline, rt = _pipeline(reqs, confirm=False)
    rt._state[7].mark_resolved("a", "geh-1")  # already resolved earlier
    reqs.append(_req("geh-1"))
    with caplog.at_level(logging.INFO):
        asyncio.run(pipeline._handle_erledigt(channel))
    assert rt._state[7].resolved_ids("a") == ["geh-1", "opp-1"]  # only the one new valid flag
    assert "nope" in caplog.text  # rejections are logged, never applied


def test_confirm_callback_applies_flag_and_persists() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True)

    class _Interaction:
        def __init__(self) -> None:
            self.edits: list[str] = []

        async def edit_original_response(self, content: str):
            self.edits.append(content)

    interaction = _Interaction()
    asyncio.run(pipeline._make_flag_confirm(channel, "opp-1")(interaction))
    assert rt._state[7].resolved_ids("a") == ["opp-1"]
    assert rt._persisted == [channel]
    assert "Abgehakt" in interaction.edits[0]


def test_confirm_after_scene_change_degrades_cleanly() -> None:
    channel = _Channel()
    pipeline, rt = _pipeline([], confirm=True)
    rt._state[7].scene_id = "b"  # the scene moved between proposal and click

    class _Interaction:
        def __init__(self) -> None:
            self.edits: list[str] = []

        async def edit_original_response(self, content: str):
            self.edits.append(content)

    interaction = _Interaction()
    asyncio.run(pipeline._make_flag_confirm(channel, "opp-1")(interaction))
    assert rt._state[7].scene_flags == {}  # opp-1 is foreign to scene b → nothing applied
    assert rt._persisted == []
    assert "Nicht mehr aktuell" in interaction.edits[0]


def test_handle_erledigt_without_adventure_never_touches_the_brain() -> None:
    # The adventure check comes BEFORE the brain drain: without an adventure the requests stay
    # queued (they expire on redo/reset) and nothing is posted.
    channel = _Channel()
    pipeline, rt = _pipeline([_req("opp-1")], confirm=True)
    rt._adventure = None
    asyncio.run(pipeline._handle_erledigt(channel))
    assert channel.sent == []
    assert [r.element_id for r in rt._brain._reqs] == ["opp-1"]  # not drained
