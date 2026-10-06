"""FailoverClient (ADR 061): a failing primary degrades loudly to the fallback, once per switch.

Both sides are scripted doubles of the ``LLMClient`` surface; the clock is injected, so cooldown
and recovery are exact.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from dmbot.llm.client import LLMBackendError
from dmbot.llm.failover import FailoverClient
from dmbot.orchestrator import DMBrain

_USER = [{"role": "user", "content": "Timo: Ich öffne die Tür."}]


class _Side:
    """One backend. ``fail`` is raised by ``chat``, and by ``chat_stream`` before delta ``fail_at``."""

    def __init__(self, model: str, deltas=("Die Tür ", "knarrt."), *, fail=None, fail_at=0) -> None:
        self.model = model
        self.deltas = list(deltas)
        self.fail = fail
        self.fail_at = fail_at
        self.last_stats: dict | None = None
        self.calls: list[tuple] = []
        self.streams_closed = 0
        self.aclosed = False

    async def chat(self, system, messages, *, options=None, format=None):
        self.calls.append(("chat", system, messages, options, format))
        if self.fail is not None:
            raise self.fail
        self.last_stats = {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 24576}
        return f"{self.model}: " + "".join(self.deltas)

    async def chat_stream(self, system, messages, *, options=None):
        self.calls.append(("stream", system, messages, options))
        try:
            for index, delta in enumerate(self.deltas):
                if self.fail is not None and index == self.fail_at:
                    raise self.fail
                yield delta
            if self.fail is not None and self.fail_at >= len(self.deltas):
                raise self.fail
            self.last_stats = {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 24576}
        finally:
            self.streams_closed += 1

    async def aclose(self) -> None:
        self.aclosed = True


class _Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _pair(primary: _Side, fallback: _Side | None = None, **kw):
    fallback = fallback or _Side("mistral-nemo", ("Lokale ", "Antwort."))
    clock = _Clock()
    return FailoverClient(primary, fallback, clock=clock, **kw), fallback, clock


async def _drain(agen) -> list[str]:
    return [delta async for delta in agen]


_DOWN = LLMBackendError("Claude CLI failed")


# ---- batch ------------------------------------------------------------------------------------


def test_a_healthy_primary_answers_and_nothing_is_announced():
    primary = _Side("opus")
    pair, fallback, _ = _pair(primary)
    assert pair.last_stats is None and pair.model == "opus"
    assert asyncio.run(pair.chat("s", _USER)) == "opus: Die Tür knarrt."
    assert fallback.calls == []
    assert pair.last_stats["backend"] == "claude"
    assert "backend" not in primary.last_stats  # a copy — the side's own dict is untouched
    assert not pair.degraded and not pair.degraded_event.is_set()


def test_a_stream_that_was_already_open_does_not_undo_a_degrade():
    """Narration is streaming on the primary when a classifier fails there. The stream ending
    normally proves nothing about that failure: the cooldown stays, and no ✅ is announced."""
    primary = _Side("opus")
    pair, fallback, clock = _pair(primary)

    async def go():
        stream = pair.chat_stream("s", _USER)
        first = await stream.__anext__()
        primary.fail = _DOWN
        await pair.chat("ROUTER", _USER, format={"type": "object"})  # fails over, degrades
        primary.fail = None
        rest = [delta async for delta in stream]
        return [first, *rest]

    assert asyncio.run(go()) == ["Die Tür ", "knarrt."]
    assert pair.degraded and pair.status().degraded_until == clock.now + 600
    assert [n[0] for n in pair.take_notices()] == ["⚠"]
    # After the cooldown a fresh call is what proves recovery.
    clock.now += 601
    asyncio.run(pair.chat("s", _USER))
    assert not pair.degraded and [n[0] for n in pair.take_notices()] == ["✅"]


def test_a_schema_call_does_not_move_the_narration_stats_to_the_other_side():
    """A classifier that fails over while the narration ran on the primary must not point the
    turn's stats at the fallback's slot."""
    primary = _Side("opus")
    pair, fallback, _ = _pair(primary)
    asyncio.run(pair.chat("s", _USER))  # narration on the primary
    fallback.last_stats = {"prompt_eval_count": 999, "eval_count": 1, "num_ctx": 24576}
    primary.fail = _DOWN
    asyncio.run(pair.chat("ROUTER", _USER, format={"type": "object"}))  # the router fails over
    assert pair.status().last_backend == "ollama"
    assert pair.last_stats["backend"] == "claude" and pair.last_stats["prompt_eval_count"] == 10
    asyncio.run(pair.chat("s", _USER))  # the next narration, still degraded
    assert pair.last_stats["backend"] == "ollama"


def test_a_failing_primary_hands_the_same_call_to_the_fallback_and_says_so_once():
    primary = _Side("opus", fail=_DOWN)
    pair, fallback, clock = _pair(primary)
    options, schema = {"num_predict": 80}, {"type": "object"}
    answer = asyncio.run(pair.chat("SYS", _USER, options=options, format=schema))
    assert answer == "mistral-nemo: Lokale Antwort."
    assert fallback.calls == [("chat", "SYS", _USER, options, schema)]  # the SAME call
    status = pair.status()
    assert status.degraded_until == clock.now + 600
    assert status.last_backend == "ollama" and status.last_error == "Claude CLI failed"
    assert pair.model == "mistral-nemo"
    assert pair.last_stats is None  # a schema call — it never moves the narration stats
    assert pair.degraded_event.is_set()
    notices = pair.take_notices()
    assert len(notices) == 1 and notices[0].startswith("⚠ Claude antwortet nicht")
    assert "mistral-nemo" in notices[0]
    assert not pair.degraded_event.is_set() and pair.take_notices() == []


def test_the_failure_is_logged_with_its_cause(caplog):
    pair, _, _ = _pair(_Side("opus", fail=_DOWN))
    with caplog.at_level("ERROR", logger="dmbot.llm.failover"):
        asyncio.run(pair.chat("s", _USER))
    assert len(caplog.records) == 1 and "Claude CLI failed" in caplog.records[0].getMessage()


def test_during_the_cooldown_the_primary_is_not_called_and_no_second_notice_is_queued():
    primary = _Side("opus", fail=_DOWN)
    pair, fallback, clock = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    pair.take_notices()
    clock.now += 599
    for _ in range(3):
        asyncio.run(pair.chat("s", _USER))
    assert len(primary.calls) == 1 and len(fallback.calls) == 4
    assert pair.take_notices() == []


def test_after_the_cooldown_the_primary_is_retried_and_a_recovery_is_announced_once():
    primary = _Side("opus", fail=_DOWN)
    pair, fallback, clock = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    pair.take_notices()
    clock.now += 600
    primary.fail = None
    assert asyncio.run(pair.chat("s", _USER)) == "opus: Die Tür knarrt."
    assert not pair.degraded and pair.status().last_error is None
    assert pair.take_notices() == ["✅ Claude antwortet wieder (opus)."]
    asyncio.run(pair.chat("s", _USER))
    assert pair.take_notices() == []


def test_a_failed_retry_extends_the_cooldown_and_corrects_the_announced_time_once():
    """The first notice named a time that has now passed — the table gets the new one, once,
    and the calls inside the new cooldown stay quiet."""
    primary = _Side("opus", fail=_DOWN)
    pair, _, clock = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    pair.take_notices()
    clock.now += 600
    asyncio.run(pair.chat("s", _USER))
    assert len(primary.calls) == 2
    assert pair.status().degraded_until == clock.now + 600
    assert len(pair.take_notices()) == 1
    asyncio.run(pair.chat("s", _USER))
    assert pair.take_notices() == []


def test_leaving_a_forced_fallback_clears_the_old_error():
    pair, _, _ = _pair(_Side("opus", fail=_DOWN))
    asyncio.run(pair.chat("s", _USER))
    pair.force("auto")
    status = pair.status()
    assert status.degraded_until is None and status.last_error is None


def test_a_rate_limit_reset_later_than_the_cooldown_wins():
    primary = _Side("opus", fail=LLMBackendError("rate limit", resets_at=1_000_000 + 7200))
    pair, _, clock = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    assert pair.status().degraded_until == clock.now + 7200


def test_the_cooldown_comes_from_the_constructor():
    pair, _, clock = _pair(_Side("opus", fail=_DOWN), cooldown_s=30)
    asyncio.run(pair.chat("s", _USER))
    assert pair.status().degraded_until == clock.now + 30


def test_only_a_backend_error_triggers_the_failover():
    """A bug is not an outage: anything else from the primary surfaces unchanged."""
    primary = _Side("opus", fail=ValueError("bug"))
    pair, fallback, _ = _pair(primary)
    with pytest.raises(ValueError):
        asyncio.run(pair.chat("s", _USER))
    assert fallback.calls == [] and not pair.degraded


def test_a_failing_fallback_is_not_swallowed():
    fallback = _Side("mistral-nemo", fail=httpx.ConnectError("ollama down"))
    pair, _, _ = _pair(_Side("opus", fail=_DOWN), fallback)
    with pytest.raises(httpx.ConnectError):
        asyncio.run(pair.chat("s", _USER))


# ---- streaming --------------------------------------------------------------------------------


def test_stream_fails_over_before_the_first_delta():
    primary = _Side("opus", fail=_DOWN, fail_at=0)
    pair, fallback, _ = _pair(primary)
    options = {"num_predict": 220}
    assert asyncio.run(_drain(pair.chat_stream("SYS", _USER, options=options))) == ["Lokale ", "Antwort."]
    assert fallback.calls == [("stream", "SYS", _USER, options)]
    assert primary.streams_closed == 1 and fallback.streams_closed == 1
    assert pair.degraded and pair.last_stats["backend"] == "ollama"
    assert len(pair.take_notices()) == 1


def test_stream_does_not_fail_over_once_text_is_out():
    """Spoken audio cannot be retracted: after the first delta the error goes to the
    orchestrator's own mid-stream degradation — but the pair is degraded for the next call."""
    primary = _Side("opus", ("Die Tür ", "knarrt."), fail=_DOWN, fail_at=1)
    pair, fallback, _ = _pair(primary)

    async def go():
        got = []
        with pytest.raises(LLMBackendError):
            async for delta in pair.chat_stream("s", _USER):
                got.append(delta)
        return got

    assert asyncio.run(go()) == ["Die Tür "]
    assert fallback.calls == []
    assert pair.degraded and len(pair.take_notices()) == 1
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Lokale ", "Antwort."]
    assert len(primary.calls) == 1


def test_stream_failing_after_its_last_delta_is_also_past_the_point_of_failover():
    primary = _Side("opus", ("Alles gesagt.",), fail=_DOWN, fail_at=1)
    pair, fallback, _ = _pair(primary)
    with pytest.raises(LLMBackendError):
        asyncio.run(_drain(pair.chat_stream("s", _USER)))
    assert fallback.calls == []


def test_a_healthy_stream_comes_from_the_primary():
    primary = _Side("opus")
    pair, fallback, _ = _pair(primary)
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Die Tür ", "knarrt."]
    assert fallback.calls == [] and pair.last_stats["backend"] == "claude"
    assert not pair.degraded_event.is_set()


def test_closing_the_stream_early_closes_the_backend_stream_and_is_no_failure():
    primary = _Side("opus", ("Eins. ", "Zwei. ", "Drei."))
    pair, fallback, _ = _pair(primary)

    async def go():
        agen = pair.chat_stream("s", _USER)
        first = await agen.__anext__()
        await agen.aclose()
        return first

    assert asyncio.run(go()) == "Eins. "
    assert primary.streams_closed == 1
    assert fallback.calls == [] and not pair.degraded
    assert pair.status().last_backend == "claude"


def test_while_degraded_a_stream_goes_straight_to_the_fallback_and_recovers_on_a_first_delta():
    primary = _Side("opus", fail=_DOWN)
    pair, fallback, clock = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    pair.take_notices()
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Lokale ", "Antwort."]
    assert len(primary.calls) == 1
    clock.now += 600
    primary.fail = None
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Die Tür ", "knarrt."]
    assert not pair.degraded
    assert pair.take_notices() == ["✅ Claude antwortet wieder (opus)."]


# ---- !backend modes -----------------------------------------------------------------------------


def test_forcing_the_fallback_skips_the_primary_and_auto_restores_it():
    primary = _Side("opus")
    pair, fallback, _ = _pair(primary)
    pair.force("fallback")
    assert asyncio.run(pair.chat("s", _USER)).startswith("mistral-nemo")
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Lokale ", "Antwort."]
    assert primary.calls == [] and pair.status().mode == "fallback"
    assert pair.take_notices() == []  # the operator chose it — nothing to announce
    pair.force("auto")
    assert asyncio.run(pair.chat("s", _USER)).startswith("opus")


def test_forcing_the_primary_ends_a_running_cooldown_but_keeps_the_safety_net():
    primary = _Side("opus", fail=_DOWN)
    pair, fallback, _ = _pair(primary)
    asyncio.run(pair.chat("s", _USER))
    pair.take_notices()
    pair.force("primary")
    assert not pair.degraded
    assert asyncio.run(pair.chat("s", _USER)).startswith("mistral-nemo")  # still down → still answered
    assert len(primary.calls) == 2  # …but it WAS tried, cooldown or not
    asyncio.run(pair.chat("s", _USER))
    assert len(primary.calls) == 3


def test_an_unknown_mode_is_rejected():
    pair, _, _ = _pair(_Side("opus"))
    with pytest.raises(ValueError):
        pair.force("gemini")


def test_aclose_closes_both_sides():
    primary = _Side("opus")
    pair, fallback, _ = _pair(primary)
    asyncio.run(pair.aclose())
    assert primary.aclosed and fallback.aclosed


# ---- through the brain --------------------------------------------------------------------------


def test_a_streamed_dm_turn_survives_a_dead_primary():
    """The seam end to end: the brain drives the pair like any client, the table gets the
    fallback's answer, and the turn's stats say who answered."""
    primary = _Side("opus", fail=_DOWN, fail_at=0)
    fallback = _Side("mistral-nemo", ("Du öffnest die Tür. ", "Es ist dunkel."))
    pair, _, _ = _pair(primary, fallback)
    brain = DMBrain(pair)
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    spoken: list[str] = []

    async def on_sentence(sentence):
        spoken.append(sentence)

    answer = asyncio.run(brain.respond_streaming(1, on_sentence=on_sentence))
    assert answer == "Du öffnest die Tür. Es ist dunkel."
    assert spoken and brain.last_llm_stats["backend"] == "ollama"
    assert brain.client is pair and len(pair.take_notices()) == 1
