"""!erledigt / !offen + the element listing in !ort (ADR 043): the manual override for scene-
element flags. The human IS the confirm — no button, apply immediately. Stub runtime with a REAL
Adventure + WorldState, `Cog.<cmd>.callback(cog, ctx, ...)` (the test_subcogs pattern)."""

from __future__ import annotations

import asyncio
import types

from dmbot.memory.state import WorldState
from dmbot.rag.adventure import Adventure, Scene
from dmbot.runtime import SessionRuntime
from dmbot.voice.scenecog import SceneCog


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
    rt._adventure = Adventure(scenes=[
        Scene(id="a", title_de="Anfang", part=1,
              opportunities_de=["Die Kiste öffnen."], secrets_de=["Bob ist der Täter."]),
    ])
    rt._brain_channel = lambda ch: 7
    rt._state = {7: WorldState(scene_id="a")}
    rt._persisted = []
    rt._persist_and_refresh = lambda ch: rt._persisted.append(ch)
    return rt


def _cog(rt) -> SceneCog:
    cog = object.__new__(SceneCog)
    cog._rt = rt
    return cog


def test_erledigt_sets_flag_and_persists() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(SceneCog.erledigt.callback(_cog(rt), ctx, "opp-1"))
    assert rt._state[7].resolved_ids("a") == ["opp-1"]
    assert len(rt._persisted) == 1
    assert any("Abgehakt" in m and "Die Kiste öffnen." in m for m in ctx.sent)


def test_offen_reopens_flag() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].mark_resolved("a", "geh-1")
    asyncio.run(SceneCog.offen.callback(_cog(rt), ctx, "geh-1"))
    assert rt._state[7].resolved_ids("a") == []
    assert len(rt._persisted) == 1
    assert any("Wieder offen" in m for m in ctx.sent)


def test_erledigt_unknown_id_replies_error_and_does_not_persist() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(SceneCog.erledigt.callback(_cog(rt), ctx, "nope"))
    assert rt._state[7].scene_flags == {} and rt._persisted == []
    assert any("Unbekanntes Element" in m for m in ctx.sent)


def test_erledigt_without_adventure_reports_missing() -> None:
    rt = types.SimpleNamespace(_adventure=None)
    ctx = _Ctx()
    asyncio.run(SceneCog.erledigt.callback(_cog(rt), ctx, "opp-1"))
    assert any("Kein Abenteuer geladen" in m for m in ctx.sent)


def test_erledigt_empty_arg_lists_the_ids() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(SceneCog.erledigt.callback(_cog(rt), ctx, ""))
    assert rt._state[7].scene_flags == {}  # nothing flagged
    assert any("opp-1" in m and "geh-1" in m for m in ctx.sent)  # usage lists the current ids


def test_ort_noarg_lists_element_ids_with_state() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt._state[7].mark_resolved("a", "opp-1")
    asyncio.run(SceneCog.ort.callback(_cog(rt), ctx, ""))
    joined = "\n".join(ctx.sent)
    assert "`opp-1` ✅" in joined and "`geh-1` ⬜" in joined
    assert "!erledigt" in joined  # the hint how to toggle
