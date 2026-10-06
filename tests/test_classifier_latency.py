"""The ``[classifier]`` log line: every side call reports its wall time in ms and its verdict —
the measurement for "how long until the dice button" (ADR 061, the Phase 11 evening)."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from dmbot.orchestrator import DMBrain
from dmbot.rules import profile as profile_mod


class _Chat:
    """An ``LLMClient`` double whose ``chat`` answers ``reply`` (or raises it) after ``delay`` s."""

    model = "fake"
    last_stats = None

    def __init__(self, reply, delay: float = 0.0) -> None:
        self.reply, self.delay = reply, delay

    async def chat(self, system, messages, *, options=None, format=None):
        await asyncio.sleep(self.delay)
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[classifier]")]


def _brain(reply, delay: float = 0.0) -> DMBrain:
    return DMBrain(_Chat(reply, delay), profile=profile_mod.load("imperium_maledictum"))


def test_the_roll_router_logs_its_latency_and_verdict(caplog):
    brain = _brain(json.dumps(
        {"needs_test": True, "skill": "Heimlichkeit", "difficulty": "Herausfordernd"}), delay=0.05)
    with caplog.at_level(logging.INFO, logger="dmbot.orchestrator"):
        req = asyncio.run(brain.classify_test(
            action="Ich schleiche.", character="Tobi", skills=["Heimlichkeit", "Athletik"]))
    assert req is not None
    (line,) = _lines(caplog)
    match = re.fullmatch(r"\[classifier\] roll (\d+)ms → Heimlichkeit \(Herausfordernd\)", line)
    assert match and int(match.group(1)) >= 40  # the call's real wall time, in ms


def test_no_test_and_a_failed_call_are_logged_too(caplog):
    with caplog.at_level(logging.INFO, logger="dmbot.orchestrator"):
        asyncio.run(_brain(json.dumps({"needs_test": False})).classify_test(
            action="Ich sage hallo.", character="Tobi", skills=["Heimlichkeit"]))
        asyncio.run(_brain(RuntimeError("down")).classify_test(
            action="Ich schleiche.", character="Tobi", skills=["Heimlichkeit"]))
    first, second = _lines(caplog)
    assert re.fullmatch(r"\[classifier\] roll \d+ms → no test", first)
    assert re.fullmatch(r"\[classifier\] roll \d+ms → failed", second)


def test_the_scene_and_fact_classifiers_log_one_line_each(caplog):
    brain = _brain("kein json")
    with caplog.at_level(logging.INFO, logger="dmbot.orchestrator"):
        asyncio.run(brain.classify_scene_move(
            turn_text="Wir gehen zum Schrein.", exits={"schrein": "Schrein"}))
        asyncio.run(brain.classify_commitment(answer_text="Er reicht euch den Schlüssel."))
    scene, fact = _lines(caplog)
    assert re.fullmatch(r"\[classifier\] scene \d+ms → \S.*", scene)
    assert re.fullmatch(r"\[classifier\] fact \d+ms → \S.*", fact)
