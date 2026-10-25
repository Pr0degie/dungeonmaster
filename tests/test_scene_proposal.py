"""A pending ``<<ORT>>`` proposal is retired when the scene moves anyway (2026-10-25, second run).

Live: Opus proposed "Wechseln?" for the shrine and five seconds later the scene classifier moved
there itself and posted its own "Szene gewechselt … ↩". The proposal kept its "Wechseln" button,
the table did not know what to press ("Komisch, dass da wechseln steht, ich will ja, dass der
automatisch wechselt"). Now the move edits the proposal and drops its buttons.
"""

from __future__ import annotations

import asyncio
import types

from dmbot.discord_ui.scene import retire_scene_proposal


class _Msg:
    def __init__(self) -> None:
        self.edits: list[dict] = []

    async def edit(self, **kw) -> None:
        self.edits.append(kw)


def _scene(sid: str, title: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=sid, title_de=title, part=1)


def test_a_move_to_the_proposed_scene_closes_the_proposal() -> None:
    msg = _Msg()
    proposals = {7: (msg, "schrein")}
    asyncio.run(retire_scene_proposal(proposals, 7, _scene("schrein", "Schrein der Aschenheiligen")))
    assert proposals == {}
    assert msg.edits and msg.edits[0]["view"] is None
    assert "Schrein der Aschenheiligen" in msg.edits[0]["content"]
    assert "Wechseln" not in msg.edits[0]["content"]


def test_a_move_elsewhere_marks_the_proposal_stale() -> None:
    msg = _Msg()
    proposals = {7: (msg, "schrein")}
    asyncio.run(retire_scene_proposal(proposals, 7, _scene("docks", "Die Docks")))
    assert msg.edits[0]["view"] is None
    assert "nicht mehr aktuell" in msg.edits[0]["content"].lower()


def test_no_proposal_is_a_no_op_and_a_failed_edit_is_swallowed() -> None:
    asyncio.run(retire_scene_proposal({}, 7, _scene("schrein", "Schrein")))

    class _Broken:
        async def edit(self, **kw) -> None:
            raise RuntimeError("message gone")

    proposals = {7: (_Broken(), "schrein")}
    asyncio.run(retire_scene_proposal(proposals, 7, _scene("schrein", "Schrein")))
    assert proposals == {}
