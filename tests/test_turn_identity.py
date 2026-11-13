"""Turns are recognised by the stored object, not by counters or text (code review of
``e4cb0a2..fdf64c6``, 2026-11-13).

``summarize`` remembers the very messages it folded into the recap and ``clear_history``
deletes exactly those; ``last_turn`` holds a reference to the user message it stored, so
``!redo`` drops that pair and no other; the turn core hands the player line back with the
answer, so the autosave never reads the mutable ``last_turn``.

Public API only, plus the cog's autosave the way the delivery pipeline calls it.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from dmbot.memory.state import WorldState
from dmbot.orchestrator import DMBrain
from dmbot.voice.dmcog import DMCog

from fakes import make_runtime


class _Script:
    """Answers from a list, in order. An entry may be an async callable: it runs inside the
    LLM call — the moment something else can happen while the model is 'thinking' — and
    returns the answer."""

    last_stats = None  # LLMClient surface (ADR 061)

    def __init__(self, answers: list) -> None:
        self.answers = list(answers)

    async def chat(self, system, messages, options=None, format=None) -> str:
        answer = self.answers.pop(0)
        if callable(answer):
            answer = await answer()
        return answer

    async def chat_stream(self, system, messages, options=None):
        answer = await self.chat(system, messages, options)
        for i in range(0, len(answer), 9):
            yield answer[i:i + 9]

    async def aclose(self) -> None:
        pass


def _contents(brain: DMBrain, ch: int) -> list[str]:
    return [m["content"] for m in brain.history_messages(ch)]


def test_a_turn_in_flight_during_the_auto_recap_is_journaled_with_its_own_player_line(tmp_path) -> None:
    ch = 7
    journal = tmp_path / "history.jsonl"

    async def compaction_finishes_meanwhile() -> str:
        # The first turn's pair is summarized and cleared while the dice turn's call is out.
        assert await brain.summarize(ch) == "Recap."
        brain.clear_history(ch)
        return "Die Tür springt auf."

    brain = DMBrain(_Script(["Ihr steht vor einer Tür.", compaction_finishes_meanwhile, "Recap."]))
    cog = object.__new__(DMCog)  # __init__ skipped (the test_subcogs pattern)
    cog._rt = make_runtime(
        _autosave=True, _brain_channel=lambda channel: ch, _brain=brain,
        _state={ch: WorldState()}, _history_path=lambda cid: journal,
    )
    brain.add_player_line(ch, "Timo", "Wir schleichen vor.")
    asyncio.run(brain.respond(ch))
    brain.add_test_result(ch, "Timo: Erfolg")
    answer = asyncio.run(brain.respond(ch))

    # What the delivery pipeline hands the autosave: the player line the answer carries.
    asyncio.run(cog._autosave_turn(SimpleNamespace(id=ch), answer, user_msg=answer.user_msg))

    recs = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 1
    assert recs[0]["user_msg"].startswith("[Würfel] Timo: Erfolg")
    assert recs[0]["answer"] == "Die Tür springt auf."


def test_redo_after_two_identical_player_lines_keeps_the_first_turn() -> None:
    ch = 1
    line = "Ich sehe mich weiter im Raum um."
    brain = DMBrain(_Script([
        "Staub liegt auf dem Boden.",
        line, line,  # the echo and its retry: the second turn is suppressed, nothing stored
        "In der Ecke glimmt ein Servoschädel.",
    ]))
    for _ in range(2):
        brain.add_player_line(ch, "Timo", line)
        asyncio.run(brain.respond(ch))
    assert brain.history_len(ch) == 2

    assert asyncio.run(brain.redo(ch)) == "In der Ecke glimmt ein Servoschädel."

    assert _contents(brain, ch) == [
        f"Timo: {line}", "Staub liegt auf dem Boden.",
        f"Timo: {line}", "In der Ecke glimmt ein Servoschädel.",
    ]


def test_a_redo_during_the_auto_recap_survives_the_compaction() -> None:
    ch = 1

    async def redo_lands_meanwhile() -> str:
        assert await brain.redo(ch) == "Der Gang dahinter ist eingestürzt."
        return "Recap."

    brain = DMBrain(_Script([
        "Ihr steht vor einer Tür.", "Der Gang dahinter liegt im Dunkeln.",
        redo_lands_meanwhile, "Der Gang dahinter ist eingestürzt.",
    ]))
    for line in ("Wir schleichen vor.", "Ich leuchte in den Gang."):
        brain.add_player_line(ch, "Timo", line)
        asyncio.run(brain.respond(ch))

    assert asyncio.run(brain.summarize(ch)) == "Recap."
    brain.clear_history(ch)

    # The recap saw the superseded answer, never the redone one — that pair stays, and so
    # does !redo for it.
    assert _contents(brain, ch) == ["Timo: Ich leuchte in den Gang.", "Der Gang dahinter ist eingestürzt."]
    assert brain.last_user_msg(ch) == "Timo: Ich leuchte in den Gang."


def test_a_wrap_up_during_the_auto_recap_does_not_widen_what_the_compaction_deletes() -> None:
    ch = 1

    async def dice_turn_and_wrap_up_meanwhile() -> str:
        brain.add_test_result(ch, "Timo: Erfolg")
        assert await brain.respond(ch) == "Die Tür springt auf."
        assert await brain.summarize(ch) == "Recap mit Tür."  # !wrap up, no _compacting guard
        return "Recap."

    brain = DMBrain(_Script([
        "Ihr steht vor einer Tür.", dice_turn_and_wrap_up_meanwhile,
        "Die Tür springt auf.", "Recap mit Tür.",
    ]))
    brain.add_player_line(ch, "Timo", "Wir schleichen vor.")
    asyncio.run(brain.respond(ch))

    assert asyncio.run(brain.summarize(ch)) == "Recap."  # the auto-recap
    brain.clear_history(ch)

    # The auto-recap never saw the dice turn.
    user, answer = _contents(brain, ch)
    assert user.startswith("[Würfel] Timo: Erfolg") and answer == "Die Tür springt auf."


def test_redo_after_the_recap_absorbed_the_turn_has_nothing_to_redo() -> None:
    ch = 1
    brain = DMBrain(_Script(["Ihr steht vor einer Tür.", "Recap."]))
    brain.add_player_line(ch, "Timo", "Wir schleichen vor.")
    asyncio.run(brain.respond(ch))

    assert asyncio.run(brain.summarize(ch)) == "Recap."
    brain.clear_history(ch)

    assert asyncio.run(brain.redo(ch)) is None
    assert brain.history_len(ch) == 0
