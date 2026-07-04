"""!fäden + !faden neu/erledigt/weg (ADR 050): the human-owned thread commands in the thin
ChekhovCog. Manual = apply immediately (the human IS the confirm), unknown ids reply an error,
every mutation persists + refreshes the prompt block. Stub runtime,
`Cog.<cmd>.callback(cog, ctx, ...)` (the test_flag_commands pattern)."""

from __future__ import annotations

import asyncio
import types

from dmbot.memory.chekhov import ChekhovList
from dmbot.memory.state import WorldState
from dmbot.runtime import SessionRuntime
from dmbot.voice.chekhovcog import ChekhovCog


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
    rt._brain_channel = lambda ch: 7
    state = WorldState()
    state.scene_id = "bar"
    rt._state = {7: state}
    rt._chekhov_lists = {7: ChekhovList()}
    rt._chekhov_path = lambda cid: None  # never hit — save is stubbed
    rt._saved = []
    rt.save_chekhov = lambda cid: rt._saved.append(cid)
    rt._persisted = []
    rt._persist_and_refresh = lambda ch: rt._persisted.append(ch)
    return rt


def _cog(rt) -> ChekhovCog:
    cog = object.__new__(ChekhovCog)
    cog._rt = rt
    return cog


def test_faden_neu_adds_thread_with_scene_and_echoes_id() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(ChekhovCog.neu.callback(_cog(rt), ctx, "Die Münze aus der Bar", 2))
    thread = rt.chekhov_list(7).find("t1")
    assert thread is not None and thread.weight == 2 and thread.origin_scene == "bar"
    assert rt._saved == [7] and len(rt._persisted) == 1
    assert any("`t1`" in m for m in ctx.sent)


def test_faden_neu_rejects_near_duplicate() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt.chekhov_list(7).add_thread("Die Münze aus der Bar")
    asyncio.run(ChekhovCog.neu.callback(_cog(rt), ctx, "die münze aus der bar", 1))
    assert len(rt.chekhov_list(7).threads) == 1 and rt._saved == []
    assert any("ähnelt" in m for m in ctx.sent)


def test_faden_erledigt_resolves_and_unknown_id_errors() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt.chekhov_list(7).add_thread("Die Münze aus der Bar")
    asyncio.run(ChekhovCog.erledigt.callback(_cog(rt), ctx, "t1"))
    assert rt.chekhov_list(7).find("t1").status == "resolved"
    assert rt._saved == [7]
    asyncio.run(ChekhovCog.erledigt.callback(_cog(rt), ctx, "t99"))
    assert any("t99" in m for m in ctx.sent) and rt._saved == [7]  # no second persist


def test_faden_weg_removes_thread() -> None:
    rt, ctx = _runtime(), _Ctx()
    rt.chekhov_list(7).add_thread("Die Münze aus der Bar")
    asyncio.run(ChekhovCog.weg.callback(_cog(rt), ctx, "t1"))
    assert rt.chekhov_list(7).threads == [] and rt._saved == [7]


def test_faeden_lists_open_and_resolved() -> None:
    rt, ctx = _runtime(), _Ctx()
    clist = rt.chekhov_list(7)
    clist.add_thread("Die Münze aus der Bar", weight=2)
    clist.add_thread("Das Versprechen an den Wirt")
    clist.resolve("t2")
    asyncio.run(ChekhovCog.faeden.callback(_cog(rt), ctx))
    out = "\n".join(ctx.sent)
    assert "offen" in out and "`t1`" in out and "Gewicht 2" in out
    assert "Aufgelöst" in out and "`t2`" in out


def test_faeden_empty_hints_usage() -> None:
    rt, ctx = _runtime(), _Ctx()
    asyncio.run(ChekhovCog.faeden.callback(_cog(rt), ctx))
    assert any("!faden neu" in m for m in ctx.sent)
