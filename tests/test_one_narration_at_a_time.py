"""One narration at a time, spoken whole, and one narration for all rolls of a turn (D152).

Live 2026-11-27, three players on Claude:

* 16:17:06 — two push-to-talk windows a second apart started two narration calls side by side.
  Both answers were spoken, sentence by sentence into each other, and the second described the
  same moment again.
* 16:11:06 — a roll narration generated while the answer before it was still playing; its first
  sentence was spoken in the middle of that answer (the bridge plays WAVs in arrival order).
* 16:22:19 / 16:22:21 — two players each had a test in the same turn. Every finished roll started
  its own narration; the two contradicted each other.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from dmbot.llm.roll_router import OpenRolls
from dmbot.runtime import _TurnTiming
from dmbot.voice.delivery import DeliveryPipeline
from dmbot.voice.dicecog import DiceCog

from fakes import FakeBrain
from test_delivery import _FakeBridge, _Recorder, _stream_runtime


# -- the rolls of one turn -----------------------------------------------------------------------

def test_the_narration_waits_until_every_roll_of_the_turn_is_in() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.posted(1)
    rolls.posted(1)
    assert rolls.finished(1) is False     # one button of the turn is still open
    assert rolls.open(1) == 1
    assert rolls.finished(1) is True      # the last one: narrate


def test_a_single_roll_is_narrated_at_once() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.posted(1)
    assert rolls.finished(1) is True


def test_a_new_turn_forgets_buttons_nobody_pressed() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.posted(1)
    rolls.posted(1)
    rolls.turn(1)                         # the next answer decided its own buttons
    rolls.posted(1)
    assert rolls.finished(1) is True


def test_a_late_roll_after_the_wait_ran_out_is_narrated_alone() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.posted(1)
    rolls.posted(1)
    assert rolls.finished(1) is False
    rolls.release(1)                      # the wait ran out, the first result was narrated
    assert rolls.finished(1) is True      # the straggler never goes below zero
    assert rolls.open(1) == 0
    assert rolls.finished(2) is True      # an unknown channel holds nothing back


# -- the dice cog: one narration for two rolls ---------------------------------------------------

def _rolling_cog(*, wait: float, narrated: list, waiting=lambda cid: True) -> DiceCog:
    async def deliver(channel, guild_id):
        narrated.append(guild_id)

    rt = SimpleNamespace(
        _brain_channel=lambda ch: 7,
        _roll_batch_wait_seconds=wait,
        _brain=SimpleNamespace(waiting_turn=waiting),
        run_and_deliver=deliver,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    cog._open_rolls = OpenRolls()
    cog._roll_waits = {}
    return cog


def test_two_rolls_of_one_turn_are_narrated_once() -> None:
    narrated: list = []
    cog = _rolling_cog(wait=30, narrated=narrated)

    async def table() -> None:
        cog._open_rolls.turn(7)
        cog._open_rolls.posted(7)
        cog._open_rolls.posted(7)
        await cog._narrate_rolls(object(), 42)   # Gellicus is done, Fridolin still rolls
        assert narrated == []
        await cog._narrate_rolls(object(), 42)   # Fridolin is done
        assert narrated == [42]
        assert cog._roll_waits == {}             # the wait is off

    asyncio.run(table())


def test_a_roll_nobody_makes_holds_the_narration_only_for_the_wait() -> None:
    narrated: list = []
    cog = _rolling_cog(wait=0.05, narrated=narrated)

    async def table() -> None:
        cog._open_rolls.turn(7)
        cog._open_rolls.posted(7)
        cog._open_rolls.posted(7)
        await cog._narrate_rolls(object(), 42)
        assert narrated == []
        await asyncio.sleep(0.2)
        assert narrated == [42]                  # told with what is there
        await cog._narrate_rolls(object(), 42)   # the straggler rolls after all
        assert narrated == [42, 42]

    asyncio.run(table())


def test_a_wait_that_runs_out_after_a_player_turn_took_the_result_stays_silent() -> None:
    narrated: list = []
    cog = _rolling_cog(wait=0.05, narrated=narrated, waiting=lambda cid: False)

    async def table() -> None:
        cog._open_rolls.turn(7)
        cog._open_rolls.posted(7)
        cog._open_rolls.posted(7)
        await cog._narrate_rolls(object(), 42)
        await asyncio.sleep(0.2)
        assert narrated == []                    # nothing un-narrated is left: no empty turn

    asyncio.run(table())


def test_with_the_wait_switched_off_every_roll_is_narrated_as_before() -> None:
    narrated: list = []
    cog = _rolling_cog(wait=0, narrated=narrated)

    async def table() -> None:
        cog._open_rolls.turn(7)
        cog._open_rolls.posted(7)
        cog._open_rolls.posted(7)
        await cog._narrate_rolls(object(), 42)
        await cog._narrate_rolls(object(), 42)

    asyncio.run(table())
    assert narrated == [42, 42]


# -- the delivery pipeline: one narration call, one voice ----------------------------------------

class _TwoTurnBrain(FakeBrain):
    """Answers turn A then turn B, three sentences each, yielding between sentences."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events
        self.calls = 0

    async def respond_streaming(self, channel_id, *, extra_text=None, on_sentence=None,
                                should_abort=None) -> str:
        tag = "AB"[self.calls]
        self.calls += 1
        self.events.append(f"start {tag}")
        for i in (1, 2, 3):
            await asyncio.sleep(0.01)
            await on_sentence(f"{tag}{i}.")
        self.events.append(f"end {tag}")
        return f"{tag}1. {tag}2. {tag}3."

    def last_user_msg(self, channel_id):
        return None


class _SlowBridge(_FakeBridge):
    async def speak(self, wav: str, *, guild_id=None) -> bool:
        await asyncio.sleep(0.02)     # playback takes time: room for another turn to cut in
        return await super().speak(wav, guild_id=guild_id)


def test_two_turns_at_once_are_generated_and_spoken_one_after_the_other() -> None:
    rec = _Recorder()
    events: list[str] = []
    rt = _stream_runtime(_TwoTurnBrain(events), _SlowBridge(rec), prebuffer=1, transform=None)

    async def _post_deliver(channel, answer, timing, *, saved_user_msg=None, redo=False) -> None:
        return None

    pipe = DeliveryPipeline(rt, post_deliver=_post_deliver)
    pipe._synthesize = rec.synthesize
    channel = SimpleNamespace(id=1)

    async def both() -> None:
        first = _TurnTiming(turn=1, trigger=time.monotonic())
        second = _TurnTiming(turn=2, trigger=time.monotonic())
        await asyncio.gather(pipe._deliver_streaming(channel, None, first),
                             pipe._deliver_streaming(channel, None, second))

    asyncio.run(both())
    assert events == ["start A", "end A", "start B", "end B"]            # never two calls at once
    assert rec.play_order == ["A1.", "A2.", "A3.", "B1.", "B2.", "B3."]  # each answer spoken whole


def test_a_batch_answer_is_spoken_after_the_answer_before_it_and_frees_its_place_when_it_fails() -> None:
    rt = _stream_runtime(FakeBrain(), _FakeBridge(_Recorder()), prebuffer=1, transform=None)

    async def _post_deliver(channel, answer, timing, *, saved_user_msg=None, redo=False) -> None:
        return None

    pipe = DeliveryPipeline(rt, post_deliver=_post_deliver)
    said: list[str] = []

    async def speak(text: str, pause: float, *, fail: bool = False) -> bool:
        said.append(f"{text} an")
        await asyncio.sleep(pause)
        if fail:
            raise RuntimeError("bridge down")
        said.append(f"{text} aus")
        return True

    async def table() -> None:
        first = asyncio.create_task(pipe._speak_in_order(lambda: speak("A", 0.03)))
        await asyncio.sleep(0)                       # A holds the first place
        second = asyncio.create_task(pipe._speak_in_order(lambda: speak("B", 0.0, fail=True)))
        third = asyncio.create_task(pipe._speak_in_order(lambda: speak("C", 0.0)))
        results = await asyncio.gather(first, second, third, return_exceptions=True)
        assert results[0] is True and isinstance(results[1], RuntimeError) and results[2] is True

    asyncio.run(table())
    assert said == ["A an", "A aus", "B an", "C an", "C aus"]    # B failed, C still spoke


# -- review follow-up: buttons still being decided, results an answer did not take along ----------

from test_marker_vs_router import _CH, _Table  # noqa: E402


def test_a_roll_finished_while_the_buttons_are_still_decided_is_not_the_last() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.deciding(1, True)
    rolls.posted(1)                       # the marker's button; the router still classifies
    assert rolls.finished(1) is False     # pressed at once — the second button is not out yet
    rolls.posted(1)
    rolls.deciding(1, False)
    assert rolls.finished(1) is True


def test_a_button_that_could_not_be_posted_holds_nothing_back() -> None:
    rolls = OpenRolls()
    rolls.turn(1)
    rolls.posted(1)
    rolls.posted(1)
    rolls.withdrawn(1)                    # Discord refused the second button
    assert rolls.finished(1) is True


def test_a_quick_click_before_the_second_button_is_narrated_once_with_both() -> None:
    # Live pattern 2026-11-27: marker button 16:21:50, router button 16:21:56 — six seconds apart.
    t = _Table(backend="claude")
    narrated: list = []

    async def deliver(channel, guild_id):
        narrated.append(guild_id)

    t.rt.run_and_deliver = deliver
    t.rt._roll_batch_wait_seconds = 30.0

    async def table() -> None:
        t.cog._open_rolls.turn(1)
        t.cog._open_rolls.deciding(1, True)       # _handle_dice is between the two buttons
        t.cog._open_rolls.posted(1)
        t.rt._brain.add_test_result(1, "🎲 Gellicus …")
        await t.cog._narrate_rolls(_CH, None)     # Gellicus clicks at once
        assert narrated == []
        t.cog._open_rolls.posted(1)               # Fridolin's button appears
        t.cog._open_rolls.deciding(1, False)
        t.rt._brain.add_test_result(1, "🎲 Fridolin …")
        await t.cog._narrate_rolls(_CH, None)
        assert narrated == [None]

    asyncio.run(table())


def test_a_lone_roll_pressed_while_the_buttons_are_decided_is_narrated_when_they_are() -> None:
    t = _Table(backend="claude")
    narrated: list = []

    async def deliver(channel, guild_id):
        narrated.append(guild_id)

    t.rt.run_and_deliver = deliver
    t.rt._roll_batch_wait_seconds = 30.0

    async def table() -> None:
        # the answer's only button is out and pressed while _handle_dice still runs the router
        t.cog._open_rolls.turn(1)
        t.cog._open_rolls.deciding(1, True)
        t.cog._open_rolls.posted(1)
        t.rt._brain.add_test_result(1, "🎲 Gellicus …")
        await t.cog._narrate_rolls(_CH, None)
        assert narrated == [] and 1 in t.cog._roll_waits
        # ... and _handle_dice ends without a second button
        t.cog._open_rolls.deciding(1, False)
        t.cog._start_roll_wait(_CH, None, 1, 0.0)
        await asyncio.sleep(0.05)
        assert narrated == [None]

    asyncio.run(table())


def test_an_answer_that_did_not_take_a_finished_roll_along_keeps_its_wait() -> None:
    t = _Table(backend="claude")
    narrated: list = []

    async def deliver(channel, guild_id):
        narrated.append(guild_id)

    t.rt.run_and_deliver = deliver
    t.rt._roll_batch_wait_seconds = 30.0

    async def table() -> None:
        t.cog._open_rolls.turn(1)
        t.cog._open_rolls.posted(1)
        t.cog._open_rolls.posted(1)
        t.rt._brain.add_test_result(1, "🎲 Gellicus …")   # finished and fed, waits for Fridolin
        await t.cog._narrate_rolls(_CH, None)
        assert 1 in t.cog._roll_waits
        # an answer whose narration call started before that roll is delivered now
        await t.cog._handle_dice(_CH)
        assert 1 in t.cog._roll_waits                      # the result is still to be narrated
        assert t.cog._open_rolls.open(1) == 1
        t.cog._cancel_all_roll_waits()                     # !leave: nothing fires afterwards
        assert t.cog._roll_waits == {}

    asyncio.run(table())
    assert narrated == []


def test_the_wait_for_the_turn_before_is_not_counted_as_generation_time() -> None:
    timing = _TurnTiming(turn=2, trigger=100.0)
    timing.wait_ms = 400
    timing.queued_ms = 9000
    timing.llm_done = 117.4
    assert timing.respond_ms() == 8000
