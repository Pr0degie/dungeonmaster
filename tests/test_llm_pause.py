"""The ``pause`` position of the failover pair (ADR 061, amendment 2026-11-13, fourth).

When Claude is out the game waits: no call of any type reaches the fallback, the player lines of
the turn Claude did not answer are kept and answered after the return, and the return is found by
a probe at a doubling interval. ``!backend ollama`` stays the deliberate way onto the local model.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from dmbot import config as config_mod
from dmbot.config import Config
from dmbot.llm import build_llm_client
from dmbot.llm.client import LLMBackendError
from dmbot.llm.fact_router import FactFailure
from dmbot.llm.failover import PAUSE_RETRY_MAX_S, FailoverClient, LLMPausedError
from dmbot.llm.npc_router import NpcFailure
from dmbot.llm.scene_router import SceneFailure
from dmbot.memory.npc_memory import request_extraction
from dmbot.memory.state import Combatant
from dmbot.orchestrator import DMBrain
from dmbot.rules import profile as profile_mod
from dmbot.voice.dmcog import DMCog

_DOWN = LLMBackendError("Claude CLI failed")
_USER = [{"role": "user", "content": "Timo: Ich öffne die Tür."}]
_SCHEMA = {"type": "object", "properties": {"ziel": {"type": "string"}}}
_PROFILE = profile_mod.load("imperium_maledictum")


class _Side:
    """One backend. ``fail`` is raised by ``chat``, and by ``chat_stream`` before delta ``fail_at``."""

    def __init__(self, model: str, deltas=("Die Tür knarrt. ", "Dahinter ist es dunkel."), *,
                 fail=None, fail_at=0) -> None:
        self.model = model
        self.deltas = list(deltas)
        self.fail = fail
        self.fail_at = fail_at
        self.last_stats: dict | None = None
        self.calls: list[dict] = []
        self.gate: asyncio.Event | None = None  # when set, ``chat`` waits for it before answering

    async def chat(self, system, messages, *, options=None, format=None):
        self.calls.append({"system": system, "messages": messages, "options": options, "format": format})
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        self.last_stats = {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 24576}
        return "".join(self.deltas)

    async def chat_stream(self, system, messages, *, options=None):
        self.calls.append({"system": system, "messages": messages, "options": options, "format": None})
        for index, delta in enumerate(self.deltas):
            if self.fail is not None and index == self.fail_at:
                raise self.fail
            yield delta
        self.last_stats = {"prompt_eval_count": 10, "eval_count": 5, "num_ctx": 24576}

    async def aclose(self) -> None:
        pass


class _Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _pair(primary: _Side | None = None, **kw):
    """A pair in the ``pause`` position with a dead Claude → (pair, claude, nemo, clock)."""
    primary = primary or _Side("opus", fail=_DOWN)
    nemo = _Side("mistral-nemo", ("Lokale ", "Antwort."))
    clock = _Clock()
    pair = FailoverClient(primary, nemo, clock=clock, on_failure="pause", **kw)
    return pair, primary, nemo, clock


def _paused(pair: FailoverClient) -> None:
    """Run one failing prose call, so the pair is paused."""
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER))


async def _noop(_sentence: str) -> None:
    return None


def _user_msg(side: _Side) -> str:
    return side.calls[-1]["messages"][-1]["content"]


# ---- the pair: nothing goes to the fallback -----------------------------------------------------


def test_a_failing_primary_pauses_the_game_and_says_so_once_in_chat_and_voice():
    pair, claude, nemo, _ = _pair()
    with pytest.raises(LLMPausedError) as caught:
        asyncio.run(pair.chat("s", _USER))
    assert caught.value.__cause__ is _DOWN and isinstance(caught.value, LLMBackendError)
    assert nemo.calls == [] and pair.paused and pair.degraded
    (notice,) = pair.take_notices()
    assert notice.startswith("⏸ Claude antwortet nicht — das Spiel pausiert.")
    assert notice.spoken == "Die Spielleitung ist gerade nicht erreichbar, das Spiel pausiert."
    assert pair.status().on_failure == "pause" and pair.status().paused_since is not None


def test_during_the_pause_calls_are_refused_without_asking_anyone():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    clock.now += 29  # one second before the first retry
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER))
    with pytest.raises(LLMPausedError):
        asyncio.run(_drain(pair.chat_stream("s", _USER)))
    assert len(claude.calls) == 1 and nemo.calls == []
    assert pair.take_notices() == []  # exactly one notice per outage


async def _drain(agen) -> list[str]:
    return [delta async for delta in agen]


def test_a_stream_that_fails_before_its_first_delta_is_paused_not_handed_over():
    pair, claude, nemo, _ = _pair()
    with pytest.raises(LLMPausedError):
        asyncio.run(_drain(pair.chat_stream("s", _USER)))
    assert nemo.calls == [] and len(pair.take_notices()) == 1


def test_a_stream_failing_after_text_is_out_behaves_as_before_and_pauses_the_pair():
    """Point 6: the mid-stream rule is the same in both positions — the backend's own error is
    re-raised to the orchestrator's degradation, and the next call does not walk into it."""
    pair, claude, nemo, _ = _pair(_Side("opus", fail=_DOWN, fail_at=1))
    got: list[str] = []

    async def go():
        async for delta in pair.chat_stream("s", _USER):
            got.append(delta)

    with pytest.raises(LLMBackendError) as caught:
        asyncio.run(go())
    assert caught.value is _DOWN and not isinstance(caught.value, LLMPausedError)
    assert got == ["Die Tür knarrt. "] and nemo.calls == []
    assert pair.paused and len(pair.take_notices()) == 1


def test_three_side_calls_failing_together_are_one_outage_and_one_wait():
    """The three post-turn classifiers run side by side: their failures are one pause, the
    interval does not double for calls that began before it."""
    pair, claude, nemo, _ = _pair()

    async def go():
        return await asyncio.gather(
            *(pair.chat("s", _USER, format=_SCHEMA) for _ in range(3)), return_exceptions=True
        )

    outcomes = asyncio.run(go())
    assert all(isinstance(o, LLMPausedError) for o in outcomes)
    assert pair.retry_in() == 30 and len(pair.take_notices()) == 1 and nemo.calls == []


# ---- the return ---------------------------------------------------------------------------------


def test_the_retry_wait_doubles_up_to_the_ceiling_and_failed_probes_say_nothing():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    waits = [pair.retry_in()]
    for _ in range(5):
        clock.now += pair.retry_in()
        assert asyncio.run(pair.probe()) is False
        waits.append(pair.retry_in())
    assert waits == [30, 60, 120, 240, 300, 300] and PAUSE_RETRY_MAX_S == 300
    assert pair.take_notices() == [] and nemo.calls == []


def test_the_first_wait_comes_from_the_constructor():
    pair, *_ = _pair(pause_retry_s=10)
    _paused(pair)
    assert pair.retry_in() == 10


def test_a_reported_rate_limit_reset_beats_the_interval_and_is_named():
    pair, claude, nemo, clock = _pair(_Side("opus", fail=LLMBackendError("limit", resets_at=int(1_000_000 + 3600))))
    _paused(pair)
    assert pair.retry_in() == 3600
    assert "(Limit bis etwa " in pair.take_notices()[0]


@pytest.mark.parametrize("fmt, tier_shape", [(None, None), (_SCHEMA, dict)])
def test_the_probe_is_the_smallest_call_of_the_shape_that_failed(fmt, tier_shape):
    """A prose failure is probed with a prose call (narration tier), a schema failure with a
    schema call (aux tier) — the tier rule stays in the client, the pair names no model."""
    pair, claude, nemo, clock = _pair()
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER, format=fmt))
    clock.now += 30
    asyncio.run(pair.probe())
    probe = claude.calls[-1]
    assert probe["options"] == {"num_predict": 8}
    assert probe["messages"] == [{"role": "user", "content": "ping"}] and len(probe["system"]) < 30
    assert (probe["format"] is None) if tier_shape is None else isinstance(probe["format"], dict)
    assert nemo.calls == []


def test_a_probe_that_finds_the_primary_after_a_short_pause_asks_for_the_waiting_turn():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    clock.now += 30
    claude.fail = None
    assert asyncio.run(pair.probe()) is True
    (notice,) = pair.take_notices()
    assert notice == "▶ Claude antwortet wieder — es geht weiter."
    assert notice.spoken == "Die Spielleitung ist wieder da, es geht weiter."
    assert not pair.paused and pair.retry_in() is None and pair.on_primary


@pytest.mark.parametrize("paused_s, resumes", [(179, True), (180, False), (900, False)])
def test_after_a_long_pause_the_probe_only_announces_the_return(paused_s, resumes):
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    clock.now += paused_s
    claude.fail = None
    assert asyncio.run(pair.probe()) is resumes
    (notice,) = pair.take_notices()
    assert notice.startswith("▶ Claude antwortet wieder")
    assert ("warte ich auf eure nächste Zeile" in notice) is (not resumes)
    assert notice.spoken and not pair.paused


def test_the_own_turn_limit_comes_from_the_constructor():
    pair, claude, nemo, clock = _pair(pause_auto_turn_s=60)
    _paused(pair)
    clock.now += 60
    claude.fail = None
    assert asyncio.run(pair.probe()) is False


def test_a_call_that_gets_through_after_the_wait_ends_the_pause_itself():
    """A player turn arriving after the wait is an attempt of its own; it is being answered, so
    the notice says the game goes on — however long the pause was — and no probe follows."""
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    clock.now += 1000
    claude.fail = None
    assert asyncio.run(pair.chat("s", _USER)) == "Die Tür knarrt. Dahinter ist es dunkel."
    assert pair.take_notices() == ["▶ Claude antwortet wieder — es geht weiter."]
    asked = len(claude.calls)
    assert asyncio.run(pair.probe()) is False and len(claude.calls) == asked


def test_a_probe_error_of_any_kind_keeps_the_pause():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    claude.fail = RuntimeError("boom")
    clock.now += 30
    assert asyncio.run(pair.probe()) is False
    assert pair.paused and pair.retry_in() == 60 and "boom" in pair.status().last_error


# ---- `!backend`: the deliberate way onto the local model -----------------------------------------


def test_backend_ollama_puts_the_session_on_the_local_model_in_the_pause_position():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    pair.force("fallback")
    assert asyncio.run(pair.chat("s", _USER)) == "Lokale Antwort."
    assert asyncio.run(_drain(pair.chat_stream("s", _USER))) == ["Lokale ", "Antwort."]
    assert pair.retry_in() is None and pair.take_notices() == []  # pinned: no probing, no notice
    pair.force("auto")
    assert not pair.paused
    with pytest.raises(LLMPausedError):  # back on the switch: Claude is asked, and still out
        asyncio.run(pair.chat("s", _USER))
    assert len(nemo.calls) == 2


def test_the_fallback_position_knows_no_pause():
    claude, nemo = _Side("opus", fail=_DOWN), _Side("mistral-nemo", ("Lokale ", "Antwort."))
    pair = FailoverClient(claude, nemo)  # the constructor's default is the old way
    assert asyncio.run(pair.chat("s", _USER)) == "Lokale Antwort."
    assert pair.on_failure == "fallback" and not pair.paused and pair.retry_in() is None
    assert asyncio.run(pair.probe()) is False and len(claude.calls) == 1
    (notice,) = pair.take_notices()
    assert notice.startswith("⚠") and getattr(notice, "spoken", "") == ""


def test_an_unknown_position_is_rejected():
    with pytest.raises(ValueError, match="on_failure"):
        FailoverClient(_Side("opus"), _Side("mistral-nemo"), on_failure="nemo")


# ---- every call type, through its real caller ---------------------------------------------------


async def _narration_streamed(brain: DMBrain):
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    return await brain.respond_streaming(1, on_sentence=_noop)


async def _narration_batch(brain: DMBrain):
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    return await brain.respond(1)


async def _roll_router(brain: DMBrain):
    return await brain.classify_test(action="Ich schleiche.", character="Timo", skills=["Heimlichkeit"])


async def _scene(brain: DMBrain):
    return await brain.classify_scene_move(turn_text="Wir gehen zum Schrein.", exits={"schrein": "Schrein"})


async def _fact(brain: DMBrain):
    return await brain.classify_commitment(answer_text="Er reicht euch den Schlüssel.")


async def _presence(brain: DMBrain):
    return await brain.classify_present_npcs(answer_text="Ein Hafenarbeiter tritt vor.", party=("Timo",))


async def _recap(brain: DMBrain):
    return await brain.summarize(1)


async def _npc_memory(brain: DMBrain):
    return await request_extraction(
        brain.client,
        turns=[{"role": "user", "content": "Timo: Wer bist du?"},
               {"role": "assistant", "content": "Grubb mustert euch misstrauisch."}],
        npcs=[Combatant(name="Grubb", wounds=10, max_wounds=10, is_npc=True)],
        scene_id="dock",
    )


async def _rules(brain: DMBrain):
    return await brain.answer_rules("Wie funktioniert Deckung?", "Cover grants armour.", system_name="IM")


# What each caller makes of the paused backend today — nothing here was changed for the side
# calls: the routers fail open on their own, recap / NPC memory / !rules raise to a caller that
# catches (auto-recap, the runtime's extraction wrapper, the cog).
_CALLS = {
    "narration, streamed": (_narration_streamed, lambda out: out is None),
    "narration, batch": (_narration_batch, lambda out: out is None),
    "roll router": (_roll_router, lambda out: out is None),
    "scene classifier": (_scene, lambda out: out.failure is SceneFailure.CALL_FAILED),
    "fact classifier": (_fact, lambda out: out.failure is FactFailure.CALL_FAILED),
    "presence classifier": (_presence, lambda out: out.failure is NpcFailure.CALL_FAILED),
    "recap": (_recap, lambda out: isinstance(out, LLMPausedError)),
    "npc memory": (_npc_memory, lambda out: isinstance(out, LLMPausedError)),
    "!rules": (_rules, lambda out: isinstance(out, LLMPausedError)),
}


async def _outcome(call, brain: DMBrain):
    try:
        return await call(brain)
    except LLMPausedError as exc:
        return exc


@pytest.mark.parametrize("name", list(_CALLS))
def test_no_call_type_lands_on_the_fallback(name):
    """Once as the call that starts the pause, once as a call made during it."""
    call, expected = _CALLS[name]
    pair, claude, nemo, _ = _pair()
    brain = DMBrain(pair, profile=_PROFILE)
    brain.restore_history(1, [("Timo: Hallo.", "Die Halle ist leer.")])  # something to recap
    first = asyncio.run(_outcome(call, brain))
    asked = len(claude.calls)
    second = asyncio.run(_outcome(call, brain))
    assert expected(first), first
    assert expected(second), second
    assert asked == 1 and len(claude.calls) == 1  # the second call did not even start the CLI
    assert nemo.calls == []
    assert len(pair.take_notices()) == 1


# ---- the player lines of the unanswered turn ----------------------------------------------------


@pytest.mark.parametrize("streamed", [False, True])
def test_the_unanswered_turn_is_answered_once_claude_is_back(streamed):
    pair, claude, nemo, clock = _pair()
    brain = DMBrain(pair)

    async def turn():
        if streamed:
            return await brain.respond_streaming(1, on_sentence=_noop)
        return await brain.respond(1)

    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    assert asyncio.run(turn()) is None
    assert brain.turn_held(1) and brain.pending_count(1) == 1
    assert brain.history_len(1) == 0  # no empty answer in history, nothing to redo
    assert brain.last_user_msg(1) is None and brain.last_action(1) is None

    brain.add_player_line(1, "Mara", "Ich halte Wache.")  # said during the pause
    clock.now += 30
    claude.fail = None
    answer = asyncio.run(turn())
    assert answer == "Die Tür knarrt. Dahinter ist es dunkel."
    assert _user_msg(claude) == "Timo: Ich öffne die Tür.\nMara: Ich halte Wache."
    assert not brain.turn_held(1) and brain.pending_count(1) == 0
    assert brain.history_len(1) == 2 and nemo.calls == []


def test_only_the_failed_turn_is_exempt_from_the_line_cap():
    """The failed turn's lines (already capped once) stay whole; what is said after it goes
    through the normal 8-line cap — also when a second turn fails during the pause."""
    pair, claude, nemo, clock = _pair()
    brain = DMBrain(pair)
    for i in range(10):
        brain.add_player_line(1, "Timo", f"a{i}")
    assert asyncio.run(brain.respond(1)) is None           # the failed turn: a2..a9
    for i in range(10):
        brain.add_player_line(1, "Timo", f"b{i}")
    assert asyncio.run(brain.respond(1)) is None           # a second attempt in the pause
    assert len(claude.calls) == 1 and brain.pending_count(1) == 16
    brain.add_player_line(1, "Timo", "c0")
    clock.now += 30
    claude.fail = None
    assert asyncio.run(brain.respond(1)) is not None
    said = [line.removeprefix("Timo: ") for line in _user_msg(claude).splitlines()]
    assert said == [f"a{i}" for i in range(2, 10)] + [f"b{i}" for i in range(3, 10)] + ["c0"]


def test_dice_results_and_gm_notes_of_the_failed_turn_come_back_in_order():
    pair, claude, nemo, clock = _pair()
    brain = DMBrain(pair)
    brain.add_test_result(1, "Timo: Erfolg, 2 Erfolgsgrade")
    brain.add_gm_note(1, "Die Uhr ist voll.")
    assert asyncio.run(brain.respond(1)) is None            # a results-only turn (after a roll)
    brain.add_test_result(1, "Mara: Fehlschlag")
    brain.add_gm_note(1, "Es wird dunkel.")
    clock.now += 30
    claude.fail = None
    assert asyncio.run(brain.respond(1)) is not None
    lines = _user_msg(claude).splitlines()
    assert lines[:4] == [
        "[Würfel] Timo: Erfolg, 2 Erfolgsgrade", "[Würfel] Mara: Fehlschlag",
        "[Regie] Die Uhr ist voll.", "[Regie] Es wird dunkel.",
    ]


def test_a_held_turn_leaves_the_played_turn_as_the_one_to_redo_and_to_roll_for():
    pair, claude, nemo, clock = _pair(_Side("opus"))
    brain = DMBrain(pair)
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    asyncio.run(brain.respond(1))
    claude.fail = _DOWN
    brain.add_player_line(1, "Mara", "Ich halte Wache.")
    assert asyncio.run(brain.respond(1)) is None
    assert brain.last_user_msg(1) == "Timo: Ich öffne die Tür."
    assert brain.last_action(1) == ("Timo", "Ich öffne die Tür.")
    assert brain.history_len(1) == 2


def test_a_redo_during_the_pause_keeps_the_previous_answer():
    pair, claude, nemo, clock = _pair(_Side("opus"))
    brain = DMBrain(pair)
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    first = asyncio.run(brain.respond(1))
    claude.fail = _DOWN
    assert asyncio.run(brain.redo(1)) is None
    assert brain.turn_held(1) and brain.history_len(1) == 2
    assert brain.history_messages(1)[1]["content"] == first
    clock.now += 30
    claude.fail = None
    claude.deltas = ["Die Tür ist verschlossen."]
    assert asyncio.run(brain.redo(1)) == "Die Tür ist verschlossen."
    assert brain.history_len(1) == 2 and nemo.calls == []


def test_two_turns_in_flight_when_claude_fails_both_keep_their_lines():
    """A network outage can take the client up to two minutes to report; the table speaks again
    meanwhile. Both turns fail, neither may overwrite what the other put aside."""
    pair, claude, nemo, clock = _pair()
    brain = DMBrain(pair)

    async def go():
        claude.gate = asyncio.Event()
        brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        first = asyncio.create_task(brain.respond(1))
        await asyncio.sleep(0.01)
        brain.add_player_line(1, "Mara", "Ich halte Wache.")
        second = asyncio.create_task(brain.respond(1))
        await asyncio.sleep(0.01)
        claude.gate.set()
        return await asyncio.gather(first, second)

    assert asyncio.run(go()) == [None, None]
    assert len(claude.calls) == 2 and nemo.calls == [] and len(pair.take_notices()) == 1
    assert brain.pending_count(1) == 2 and pair.retry_in() == 30
    assert brain.last_user_msg(1) is None  # neither failed turn is left for `!redo`
    claude.gate = None
    clock.now += 30
    claude.fail = None
    assert asyncio.run(brain.respond(1)) is not None
    assert _user_msg(claude).splitlines() == ["Timo: Ich öffne die Tür.", "Mara: Ich halte Wache."]


def test_a_turn_cut_off_mid_stream_counts_as_answered_and_is_not_repeated():
    """Point 6 through the brain: what was said stays, the history notes the break, the lines
    are consumed — and nothing of it goes to the local model."""
    pair, claude, nemo, _ = _pair(_Side("opus", fail=_DOWN, fail_at=1))
    brain = DMBrain(pair)
    brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
    answer = asyncio.run(brain.respond_streaming(1, on_sentence=_noop))
    assert answer == "Die Tür knarrt."
    assert brain.history_messages(1)[1]["content"].endswith("[Antwort unterbrochen]")
    assert brain.pending_count(1) == 0 and not brain.turn_held(1)
    assert nemo.calls == [] and pair.paused and len(pair.take_notices()) == 1


# ---- the watcher: notices in chat and voice, the probe, the own turn -----------------------------


class _Channel:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.guild = types.SimpleNamespace(id=7)

    async def send(self, content: str = "", **kwargs) -> None:
        self.sent.append(content)


def _cog(pair):
    cog = object.__new__(DMCog)
    channel, spoken, turns = _Channel(), [], []

    async def speak(text, guild_id, **kwargs):
        spoken.append((text, guild_id))

    async def run_and_deliver(ch, guild_id, *, kind="roll"):
        turns.append((ch, guild_id, kind))

    cog._rt = types.SimpleNamespace(
        _brain=DMBrain(pair), _text_channel=channel, _brain_channel=lambda ch: 1,
        speak=speak, speech_transform=lambda: None,
    )
    cog._delivery = types.SimpleNamespace(_run_and_deliver=run_and_deliver)
    return cog, channel, spoken, turns


async def _until(condition, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.005)


def _watch(pair, claude, cog, channel):
    """Claude fails a player turn, stays out for a few probes, then answers again."""

    async def go():
        watcher = asyncio.create_task(cog._watch_backend(pair))
        cog._rt._brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        assert await cog._rt._brain.respond(1) is None  # the turn is kept
        await _until(lambda: len(claude.calls) >= 3)  # the failing call + two failed probes
        during = list(channel.sent)
        claude.fail = None
        await _until(lambda: len(channel.sent) >= 2)
        await asyncio.sleep(0.05)
        watcher.cancel()
        return during

    return asyncio.run(go())


def test_the_watcher_announces_once_each_way_and_answers_the_waiting_turn():
    pair, claude, nemo, _ = _pair(pause_retry_s=0.01)
    cog, channel, spoken, turns = _cog(pair)
    during = _watch(pair, claude, cog, channel)
    assert len(during) == 1 and during[0].startswith("⏸")           # failed probes say nothing
    assert len(channel.sent) == 2 and channel.sent[1] == "▶ Claude antwortet wieder — es geht weiter."
    assert spoken == [
        ("Die Spielleitung ist gerade nicht erreichbar, das Spiel pausiert.", 7),
        ("Die Spielleitung ist wieder da, es geht weiter.", 7),
    ]
    assert turns == [(channel, 7, "resume")] and nemo.calls == []


def test_after_a_long_pause_the_watcher_announces_the_return_and_runs_no_turn():
    pair, claude, nemo, _ = _pair(pause_retry_s=0.01, pause_auto_turn_s=0)  # every pause is "long"
    cog, channel, spoken, turns = _cog(pair)
    _watch(pair, claude, cog, channel)
    assert len(channel.sent) == 2 and "warte ich auf eure nächste Zeile" in channel.sent[1]
    assert spoken[1] == ("Die Spielleitung ist wieder da und wartet auf eure nächste Ansage.", 7)
    assert turns == []


def test_backend_command_shows_the_position_the_pause_and_the_emergency_grip():
    pair, claude, nemo, _ = _pair()
    cog, *_ = _cog(pair)

    def backend(arg: str = "") -> str:
        ctx = _Channel()
        asyncio.run(DMCog.backend.callback(cog, ctx, arg=arg))
        (text,) = ctx.sent
        return text

    assert "auto (bei Ausfall: Pause)" in backend() and "kein Ausfall" in backend()
    _paused(pair)
    text = backend()
    assert "⏸ claude ausgefallen, Spiel pausiert seit " in text and "nächster Versuch " in text
    assert "Claude CLI failed" in text
    text = backend("ollama")
    assert "fest auf ollama" in text and "ollama erzählt, solange `!backend ollama` gilt" in text
    assert "kein Ausfall" in backend("auto")  # back on the switch; the next call asks Claude again


def test_a_turn_command_during_the_pause_gets_a_reaction_not_a_second_chat_line():
    reactions: list[str] = []
    sent: list[str] = []

    async def add_reaction(emoji):
        reactions.append(emoji)

    async def send(text):
        sent.append(text)

    ctx = types.SimpleNamespace(message=types.SimpleNamespace(add_reaction=add_reaction), send=send)
    cog = object.__new__(DMCog)
    held = [True]
    cog._rt = types.SimpleNamespace(_brain=types.SimpleNamespace(turn_held=lambda cid: held[0]))
    asyncio.run(cog._nothing_answered(ctx, 1, "(Nichts zu beantworten.)"))
    assert reactions == ["⏸"] and sent == []
    held[0] = False
    asyncio.run(cog._nothing_answered(ctx, 1, "(Nichts zu beantworten.)"))
    assert sent == ["(Nichts zu beantworten.)"]


# ---- the switch ---------------------------------------------------------------------------------

_ENV = ("DM_LLM_BACKEND", "DM_LLM_ON_FAILURE", "DM_LLM_PAUSE_RETRY_S", "DM_LLM_PAUSE_AUTO_TURN_S",
        "DM_LLM_FAILOVER_COOLDOWN_S", "ANTHROPIC_API_KEY")


def _load(monkeypatch, **env) -> Config:
    monkeypatch.setattr(config_mod, "load_dotenv", lambda: None)
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DISCORD_TOKEN_DMBOT", "token")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Config.load()


def test_the_switch_defaults_to_pause_with_the_documented_times(monkeypatch):
    config = _load(monkeypatch)
    assert config.llm_on_failure == "pause"
    assert (config.llm_pause_retry_s, config.llm_pause_auto_turn_s) == (30, 180)


def test_an_unknown_position_is_a_boot_error_not_a_silent_default(monkeypatch):
    with pytest.raises(RuntimeError, match="DM_LLM_ON_FAILURE"):
        _load(monkeypatch, DM_LLM_ON_FAILURE="nemo")


@pytest.mark.parametrize("position", ["pause", "fallback"])
def test_the_switch_reaches_the_pair(monkeypatch, position):
    """The knob is wired (lesson unwired-knobs): what `.env` says is what the pair does."""
    client = build_llm_client(_load(
        monkeypatch, DM_LLM_BACKEND="claude", DM_LLM_ON_FAILURE=f" {position.upper()} ",
        DM_LLM_PAUSE_RETRY_S="12", DM_LLM_PAUSE_AUTO_TURN_S="99",
    ))
    assert client.on_failure == position == client.status().on_failure
    assert (client._pause_retry_s, client._pause_auto_turn_s) == (12, 99)
    asyncio.run(client.aclose())


# ---- from the review of this round ---------------------------------------------------------------


class _Scripted(_Side):
    """A primary whose ``chat`` runs one scripted step per call (an async function that answers
    or raises), so two calls in flight can end in a chosen order."""

    def __init__(self, *steps) -> None:
        super().__init__("opus")
        self.steps = list(steps)

    async def chat(self, system, messages, *, options=None, format=None):
        self.calls.append({"system": system, "messages": messages, "options": options, "format": format})
        return await self.steps.pop(0)()


async def _down():
    raise _DOWN


async def _ok():
    return "Die Tür knarrt."


def _after(gate: asyncio.Event, step):
    async def run():
        await gate.wait()
        return await step()

    return run


def _scripted_pair(*steps, **kw):
    claude = _Scripted(*steps)
    pair, _, nemo, clock = _pair(claude, **kw)
    return pair, claude, nemo, clock


def test_an_outage_of_one_tier_is_not_ended_by_the_other_tier_answering():
    """Haiku out, Opus fine: a narration that got through used to announce ▶, its classifiers
    then ⏸ again — every turn, with the wait reset to 30 s each time. Only the shape that
    failed is an attempt and ends the pause."""
    pair, claude, nemo, clock = _pair()
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER, format=_SCHEMA))   # a classifier starts the pause
    pair.take_notices()
    clock.now += 30
    claude.fail = None                                        # "Opus" would answer
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER))
    with pytest.raises(LLMPausedError):
        asyncio.run(_drain(pair.chat_stream("s", _USER)))
    assert len(claude.calls) == 1 and nemo.calls == [] and pair.paused
    assert pair.take_notices() == []
    assert asyncio.run(pair.chat("s", _USER, format=_SCHEMA))  # the tier that failed answers
    assert not pair.paused and len(pair.take_notices()) == 1


def test_with_the_primary_pinned_the_other_tier_answers_but_does_not_end_the_pause():
    pair, claude, nemo, clock = _pair()
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER, format=_SCHEMA))
    pair.force("primary")                                     # clears the pause …
    with pytest.raises(LLMPausedError):
        asyncio.run(pair.chat("s", _USER, format=_SCHEMA))   # … and Haiku is still out
    pair.take_notices()
    claude.fail = None
    assert asyncio.run(pair.chat("s", _USER))                 # pinned: every call is tried
    assert pair.paused and pair.take_notices() == []


def test_a_probe_that_fails_after_a_call_ended_the_pause_announces_nothing():
    """The turn and the watcher's probe are both in flight at retry time; the turn ends the
    pause, the probe then times out. That is no second outage."""
    outcome = {}

    async def go():
        gate = asyncio.Event()
        pair, claude, nemo, clock = _scripted_pair(_down, _after(gate, _down), _ok)
        with pytest.raises(LLMPausedError):
            await pair.chat("s", _USER)
        clock.now += 30
        probe = asyncio.create_task(pair.probe())
        await asyncio.sleep(0.01)                             # the probe is in flight
        assert await pair.chat("s", _USER) == "Die Tür knarrt."
        gate.set()
        outcome.update(probe=await probe, pair=pair, nemo=nemo)

    asyncio.run(go())
    pair = outcome["pair"]
    assert outcome["probe"] is False and not pair.paused and pair.on_primary
    assert [n[0] for n in pair.take_notices()] == ["⏸", "▶"] and outcome["nemo"].calls == []


def _two_turns(first_to_end: str):
    """Timo's turn (A) and Mara's turn (B) are both in flight; A fails, B fails or answers."""
    state = {}

    async def go(b_step):
        gate_a, gate_b = asyncio.Event(), asyncio.Event()
        pair, claude, nemo, clock = _scripted_pair(_after(gate_a, _down), _after(gate_b, b_step), _ok)
        brain = DMBrain(pair)
        brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        turn_a = asyncio.create_task(brain.respond(1))
        await asyncio.sleep(0.01)
        brain.add_player_line(1, "Mara", "Ich halte Wache.")
        turn_b = asyncio.create_task(brain.respond(1))
        await asyncio.sleep(0.01)
        for gate in ((gate_a, gate_b) if first_to_end == "a" else (gate_b, gate_a)):
            gate.set()
            await asyncio.sleep(0.01)
        state.update(a=await turn_a, b=await turn_b, brain=brain, pair=pair, claude=claude, clock=clock)

    return state, go


def test_a_later_turn_that_is_answered_stays_the_one_to_redo_and_to_roll_for():
    """A fails and is kept while B is still open on the primary and then answers: the session
    must describe B, not what was current before A."""
    state, go = _two_turns("a")
    asyncio.run(go(_ok))
    brain = state["brain"]
    assert state["a"] is None and state["b"] == "Die Tür knarrt."
    assert brain.last_user_msg(1) == "Mara: Ich halte Wache."
    assert brain.last_action(1) == ("Mara", "Ich halte Wache.")
    assert brain.pending_count(1) == 1 and brain.history_len(1) == 2  # Timo's line still waits


@pytest.mark.parametrize("first_to_fail", ["a", "b"])
def test_turns_in_flight_are_answered_in_the_order_they_were_said(first_to_fail):
    state, go = _two_turns(first_to_fail)
    asyncio.run(go(_down))
    brain, claude, clock = state["brain"], state["claude"], state["clock"]
    assert state["a"] is None and state["b"] is None and brain.pending_count(1) == 2
    clock.now += 30
    assert asyncio.run(brain.respond(1)) == "Die Tür knarrt."
    assert _user_msg(claude).splitlines() == ["Timo: Ich öffne die Tür.", "Mara: Ich halte Wache."]


def test_an_attempt_that_fails_after_the_wait_keeps_the_first_turn_and_caps_its_own_lines():
    pair, claude, nemo, clock = _pair()
    brain = DMBrain(pair)
    brain.add_player_line(1, "Timo", "a0")
    assert asyncio.run(brain.respond(1)) is None            # the turn the backend failed on
    for i in range(10):
        brain.add_player_line(1, "Timo", f"b{i}")
    clock.now += 30
    assert asyncio.run(brain.respond(1)) is None            # a real attempt, and it fails too
    assert len(claude.calls) == 2 and pair.retry_in() == 60
    clock.now += 60
    claude.fail = None
    assert asyncio.run(brain.respond(1)) is not None
    said = [line.removeprefix("Timo: ") for line in _user_msg(claude).splitlines()]
    assert said == ["a0"] + [f"b{i}" for i in range(2, 10)]


def test_turn_held_is_not_wiped_by_a_turn_that_starts_afterwards():
    """The cog reads it after its own awaits; a voice turn starting in between must not turn
    the ⏸ reaction into "(Nichts zu beantworten.)"."""
    seen = {}

    async def go():
        gate = asyncio.Event()
        pair, claude, nemo, clock = _scripted_pair(_down, _after(gate, _ok))
        brain = DMBrain(pair)
        brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        assert await brain.respond(1) is None and brain.turn_held(1)
        clock.now += 30
        brain.add_player_line(1, "Mara", "Ich halte Wache.")
        later = asyncio.create_task(brain.respond(1))
        await asyncio.sleep(0.01)
        seen["while_in_flight"] = brain.turn_held(1)
        gate.set()
        await later
        seen["after"] = brain.turn_held(1)

    asyncio.run(go())
    assert seen == {"while_in_flight": True, "after": False}


def test_a_side_call_that_ends_a_long_pause_carries_the_waiting_text_as_an_alternative():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    pair.take_notices()
    clock.now += 1000
    claude.fail = None
    asyncio.run(pair.chat("s", _USER))
    (notice,) = pair.take_notices()
    assert notice == "▶ Claude antwortet wieder — es geht weiter."
    assert "warte ich auf eure nächste Zeile" in notice.if_waiting and notice.if_waiting.spoken
    assert pair.take_resume() is False  # long: no own turn


def test_a_short_pause_asks_for_the_waiting_turn_exactly_once_however_it_ended():
    pair, claude, nemo, clock = _pair()
    _paused(pair)
    clock.now += 30
    claude.fail = None
    asyncio.run(pair.chat("s", _USER))
    (_, notice) = pair.take_notices()
    assert notice.if_waiting is None
    assert pair.take_resume() is True and pair.take_resume() is False


def _held_then_side_call(paused_s: float):
    """A player turn is kept; `!rules` is what reaches Claude first after the wait."""
    pair, claude, nemo, clock = _pair()
    cog, channel, spoken, turns = _cog(pair)
    brain = cog._rt._brain

    async def go():
        watcher = asyncio.create_task(cog._watch_backend(pair))
        brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        assert await brain.respond(1) is None
        await _until(lambda: len(channel.sent) == 1)   # ⏸ is out; the watcher now sleeps 30 s
        clock.now += paused_s
        claude.fail = None
        assert await brain.answer_rules("Deckung?", "Cover grants armour.", system_name="IM")
        await _until(lambda: len(channel.sent) == 2)
        await asyncio.sleep(0.05)
        watcher.cancel()

    asyncio.run(go())
    return channel, turns, brain


def test_a_side_call_ending_a_short_pause_still_gets_the_kept_turn_answered():
    channel, turns, brain = _held_then_side_call(30)
    assert channel.sent[1] == "▶ Claude antwortet wieder — es geht weiter."
    assert turns == [(channel, 7, "resume")]


def test_a_side_call_ending_a_long_pause_says_that_the_bot_waits():
    channel, turns, brain = _held_then_side_call(500)
    assert "warte ich auf eure nächste Zeile" in channel.sent[1]
    assert turns == [] and brain.pending_count(1) == 1


def test_the_watcher_starts_no_turn_when_nothing_is_waiting():
    """The outage hit a side call: after the return there is no turn to answer."""
    pair, claude, nemo, _ = _pair(pause_retry_s=0.01)
    cog, channel, spoken, turns = _cog(pair)

    async def go():
        watcher = asyncio.create_task(cog._watch_backend(pair))
        with pytest.raises(LLMPausedError):
            await pair.chat("s", _USER)
        await _until(lambda: len(channel.sent) == 1)
        claude.fail = None
        await _until(lambda: len(channel.sent) == 2)
        await asyncio.sleep(0.05)
        watcher.cancel()

    asyncio.run(go())
    assert channel.sent[1].startswith("▶") and turns == []


def test_a_second_outage_is_announced_while_the_resumed_turn_is_still_running():
    """The resumed turn runs as its own task; the watcher keeps posting and probing."""
    pair, claude, nemo, _ = _pair(pause_retry_s=0.01)
    cog, channel, spoken, turns = _cog(pair)
    seen = {}

    async def go():
        turn_gate = asyncio.Event()

        async def slow_turn(ch, guild_id, *, kind="roll"):
            turns.append(kind)
            await turn_gate.wait()

        cog._delivery = types.SimpleNamespace(_run_and_deliver=slow_turn)
        watcher = asyncio.create_task(cog._watch_backend(pair))
        cog._rt._brain.add_player_line(1, "Timo", "Ich öffne die Tür.")
        assert await cog._rt._brain.respond(1) is None
        await _until(lambda: len(channel.sent) == 1)
        claude.fail = None
        await _until(lambda: turns == ["resume"])       # ▶ is out, the turn has started
        claude.fail = _DOWN
        with pytest.raises(LLMPausedError):
            await pair.chat("s", _USER)
        await _until(lambda: len(channel.sent) == 3)
        seen["sent_while_turn_runs"] = [line[0] for line in channel.sent]
        turn_gate.set()
        await asyncio.sleep(0.02)
        watcher.cancel()

    asyncio.run(go())
    assert seen["sent_while_turn_runs"] == ["⏸", "▶", "⏸"]


@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_retry_wait_below_one_second_is_a_boot_error(monkeypatch, value):
    """0 would double to 0 forever — the watcher would start one CLI after another."""
    with pytest.raises(RuntimeError, match="DM_LLM_PAUSE_RETRY_S"):
        _load(monkeypatch, DM_LLM_PAUSE_RETRY_S=value)
    with pytest.raises(ValueError, match="pause_retry_s"):
        FailoverClient(_Side("opus"), _Side("mistral-nemo"), on_failure="pause", pause_retry_s=float(value))


def test_a_negative_own_turn_limit_is_a_boot_error(monkeypatch):
    with pytest.raises(RuntimeError, match="DM_LLM_PAUSE_AUTO_TURN_S"):
        _load(monkeypatch, DM_LLM_PAUSE_AUTO_TURN_S="-1")
    assert _load(monkeypatch, DM_LLM_PAUSE_AUTO_TURN_S="0").llm_pause_auto_turn_s == 0


def test_config_and_pair_know_the_same_positions():
    from dmbot.llm.failover import ON_FAILURE

    assert set(config_mod.LLM_ON_FAILURE) == set(ON_FAILURE)
