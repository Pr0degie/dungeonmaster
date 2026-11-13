"""Every delivery path journals its turn exactly once (``TurnAnswer`` hardening, 2026-11-13).

The autosave takes the player line from the turn's own answer (``TurnAnswer.user_msg``); a path
that loses it writes nothing and logs an error. Each case drives the real delivery pipeline —
batch (``_deliver_answer``) or streaming (``_deliver_streaming``) — over a real ``DMBrain`` into
the cog's real end-of-turn tail, the way ``!dm``, ``!redo`` and ``!start`` call it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from types import SimpleNamespace

import pytest

from dmbot.memory.state import WorldState
from dmbot.orchestrator import DMBrain, build_opening_director_msg
from dmbot.runtime import _TurnTiming
from dmbot.voice.delivery import DeliveryPipeline
from dmbot.voice.dmcog import DMCog

from fakes import make_runtime

_CH = 7


class _Script:
    """Answers from a list, in order (batch and streamed)."""

    last_stats = None  # LLMClient surface (ADR 061)

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)

    async def chat(self, system, messages, options=None, format=None) -> str:
        return self.answers.pop(0)

    async def chat_stream(self, system, messages, options=None):
        answer = self.answers.pop(0)
        for i in range(0, len(answer), 9):
            yield answer[i:i + 9]

    async def aclose(self) -> None:
        pass


def _cog(brain: DMBrain, journal) -> tuple[DMCog, DeliveryPipeline]:
    async def _noop(*_a, **_kw) -> None:
        return None

    cog = object.__new__(DMCog)  # __init__ skipped (the test_subcogs pattern)
    cog._rt = make_runtime(
        brain=brain, _autosave=True, _autorecap=False, _brain_channel=lambda channel: _CH,
        _state={_CH: WorldState()}, _history_path=lambda cid: journal,
        _send_with_retry=_noop, handle_dice=_noop, close_turn=_noop,
        consistency_checker=lambda channel: None, speech_transform=lambda: None,
    )
    return cog, DeliveryPipeline(cog._rt, post_deliver=cog._post_deliver)


@pytest.mark.parametrize("delivery", ["batch", "stream"])
@pytest.mark.parametrize("kind", ["respond", "redo", "opening"])
def test_each_delivery_path_journals_its_turn_exactly_once(tmp_path, caplog, delivery, kind) -> None:
    journal = tmp_path / "history.jsonl"
    brain = DMBrain(_Script(["Ihr steht vor einer Tür.", "Die Tür schwingt auf."]))
    _cog_, pipe = _cog(brain, journal)
    channel = SimpleNamespace(id=_CH)
    director = build_opening_director_msg()

    brain.add_player_line(_CH, "Timo", "Ich öffne die Tür.")
    if kind == "redo":
        asyncio.run(brain.respond(_CH))  # the turn being redone — not delivered, not journaled
    timing = _TurnTiming(turn=1, trigger=time.monotonic(), kind="redo" if kind == "redo" else "auto")

    async def _deliver() -> None:
        if delivery == "stream":
            await pipe._deliver_streaming(
                channel, None, timing, redo=kind == "redo",
                opening=director if kind == "opening" else None,
            )
            return
        if kind == "respond":
            answer = await brain.respond(_CH)
        elif kind == "redo":
            answer = await brain.redo(_CH)
        else:
            answer = await brain.respond_opening(_CH, director)
        await pipe._deliver_answer(channel, None, answer, timing)

    with caplog.at_level(logging.ERROR):
        asyncio.run(_deliver())

    recs = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 1
    expected_user = director if kind == "opening" else "Timo: Ich öffne die Tür."
    assert recs[0]["user_msg"] == expected_user
    assert recs[0]["redo"] is (kind == "redo")
    assert "without its player line" not in caplog.text


def test_an_answer_without_its_player_line_is_logged_not_dropped_silently(tmp_path, caplog) -> None:
    journal = tmp_path / "history.jsonl"
    cog, _pipe = _cog(DMBrain(_Script([])), journal)

    with caplog.at_level(logging.ERROR):
        asyncio.run(cog._autosave_turn(SimpleNamespace(id=_CH), "Die Tür schwingt auf.", user_msg=None))
        asyncio.run(cog._autosave_turn(SimpleNamespace(id=_CH), "", user_msg=None))  # empty: quiet

    assert not journal.exists()
    assert caplog.text.count("without its player line") == 1
    assert "Die Tür schwingt auf." in caplog.text
