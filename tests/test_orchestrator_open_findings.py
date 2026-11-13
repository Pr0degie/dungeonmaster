"""Open findings in DMBrain, pinned as strict xfails — nothing here is fixed.

The code review of the orchestrator de-duplication (2026-11-13, ``ddaae08..9ec06b6``) found
seven faults the refactor carried over unchanged. Each test below asserts the WANTED behaviour
and fails today; ``strict=True`` turns the test red the moment a fix lands, so the mark gets
removed with it. All seven were derived from the code, none was seen live. Listed in
``progress.md`` under "Last session".

Public API only: the tests drive ``DMBrain`` the way the cogs do.
"""

from __future__ import annotations

import asyncio

import pytest

from dmbot.llm.consistency import check
from dmbot.memory.state import Combatant, WorldState
from dmbot.orchestrator import DMBrain, build_opening_director_msg
from dmbot.rules import profile as profile_mod

_IM = profile_mod.load("imperium_maledictum")


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

    async def aclose(self) -> None:
        pass


def _contents(brain: DMBrain, ch: int) -> list[str]:
    return [m["content"] for m in brain.history_messages(ch)]


# ---- compaction vs. a concurrent turn ------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "clear_history swaps in a fresh list once the compaction has emptied the history; a turn "
    "still in flight holds the old list and appends its pair there — lost from both the recap "
    "and the history (code review 2026-11-13, finding 2)"))
def test_a_turn_still_in_flight_survives_the_compaction_wipe() -> None:
    ch = 1

    async def compaction_finishes_meanwhile() -> str:
        # The dice turn's LLM call is still out when the auto-compaction summarizes the
        # history (the first turn) and clears it.
        assert await brain.summarize(ch) == "Recap."
        brain.clear_history(ch)
        return "Die Tür springt auf."

    brain = DMBrain(_Script(["Ihr steht vor einer Tür.", compaction_finishes_meanwhile, "Recap."]))
    brain.add_player_line(ch, "Timo", "Wir schleichen vor.")
    asyncio.run(brain.respond(ch))
    brain.add_test_result(ch, "Timo: Erfolg")
    assert asyncio.run(brain.respond(ch)) == "Die Tür springt auf."  # spoken at the table

    # The recap never saw the dice turn, so the history has to keep it.
    assert brain.history_len(ch) == 2
    assert _contents(brain, ch)[-1] == "Die Tür springt auf."


@pytest.mark.xfail(strict=True, reason=(
    "compact_consumed counts from the head, but at the history cap _append_turn trims the head "
    "when the concurrent turn lands — clear_history then deletes that turn too (code review "
    "2026-11-13, finding 3)"))
def test_a_turn_appended_during_summarize_survives_at_the_history_cap() -> None:
    ch = 1

    async def dice_turn_lands_meanwhile() -> str:
        # While the recap call is out, a dice consequence turn runs to completion.
        brain.add_test_result(ch, "Timo: Erfolg")
        assert await brain.respond(ch) == "Die Tür springt auf."
        return "Recap."

    brain = DMBrain(
        _Script([
            "Ihr steht vor einer Tür.", "Der Gang dahinter liegt im Dunkeln.",
            dice_turn_lands_meanwhile, "Die Tür springt auf.",
        ]),
        max_history_turns=2,
    )
    for line in ("Wir schleichen vor.", "Ich leuchte in den Gang."):
        brain.add_player_line(ch, "Timo", line)
        asyncio.run(brain.respond(ch))
    assert brain.history_len(ch) == 4  # at the cap

    assert asyncio.run(brain.summarize(ch)) == "Recap."
    brain.clear_history(ch)

    # Same promise as below the cap (test_autorecap, Finding #4): the turn that was never
    # summarized stays.
    assert brain.history_len(ch) == 2
    assert _contents(brain, ch)[-1] == "Die Tür springt auf."


# ---- redo ----------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "redo drops the last history pair on a role check alone; after a turn that was never "
    "stored (echo-suppressed, or the LLM call failed) that pair is the turn BEFORE the one "
    "being redone (code review 2026-11-13, finding 1)"))
def test_redo_after_a_suppressed_turn_keeps_the_turn_before_it() -> None:
    ch = 1
    brain = DMBrain(_Script([
        "Ihr steht vor einer Tür.",
        "Ich sehe mich um.", "Ich sehe mich um.",  # the echo and its retry: suppressed
        "Staub liegt auf dem Boden.",
    ]))
    brain.add_player_line(ch, "Timo", "Wir schleichen vor.")
    asyncio.run(brain.respond(ch))
    brain.add_player_line(ch, "Timo", "Ich sehe mich um.")
    assert asyncio.run(brain.respond(ch)) == ""  # suppressed, nothing stored
    assert brain.history_len(ch) == 2

    assert asyncio.run(brain.redo(ch)) == "Staub liegt auf dem Boden."

    assert _contents(brain, ch) == [
        "Timo: Wir schleichen vor.", "Ihr steht vor einer Tür.",
        "Timo: Ich sehe mich um.", "Staub liegt auf dem Boden.",
    ]


# ---- opening -------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "_prepare_opening leaves last_action/last_actions as the previous player turn set them; an "
    "opening mid-session therefore queues the briefing's <<TEST>> and hands the roll router "
    "the old action again (code review 2026-11-13, finding 4)"))
def test_an_opening_after_a_player_turn_requests_no_dice() -> None:
    ch = 1
    brain = DMBrain(
        _Script([
            "Die Tür schwingt auf.",
            "Inquisitor Halikarn mustert euch kalt. <<TEST Wahrnehmung für Mortn>>",
        ]),
        profile=_IM,
    )
    brain.set_known_speakers(ch, ["Mortn", "Seskin"])
    brain.add_player_line(ch, "Mortn", "Ich öffne die Tür.")
    asyncio.run(brain.respond(ch))

    answer = asyncio.run(brain.respond_opening(ch, build_opening_director_msg()))
    assert answer == "Inquisitor Halikarn mustert euch kalt."

    assert brain.take_pending_tests(ch) == []  # no dice on a briefing
    assert brain.last_actions(ch) == []        # nothing for the roll router to classify again


@pytest.mark.xfail(strict=True, reason=(
    "the intro guard's retry has no marker hygiene: the discarded weak opening's <<UHR>> stays "
    "queued next to the kept answer's markers (code review 2026-11-13, finding 6)"))
def test_a_discarded_weak_opening_leaves_no_markers_behind() -> None:
    ch = 1
    kept = "Inquisitor Halikarn mustert euch kalt und lässt die Stille im Raum wirken."
    brain = DMBrain(_Script(["Es ist kalt. <<UHR alarm>>", kept]), profile=_IM)

    answer = asyncio.run(brain.respond_opening(
        ch, build_opening_director_msg(), is_weak=lambda text: len(text) < 40,
    ))
    assert answer == kept  # the weak first opening was discarded

    assert brain.take_pending_uhr(ch) == []


# ---- consistency guard ---------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "a discarded consistency retry restores the first answer's markers only for the kinds it "
    "had queued; what the retry queued under any other kind survives (code review 2026-11-13, "
    "finding 5)"))
def test_a_discarded_consistency_retry_leaves_no_markers_behind() -> None:
    ch = 1
    state = WorldState(
        npcs=[Combatant(name="Grendel", wounds=0, max_wounds=10, is_npc=True)], characters=[],
    )
    first = "Grendel sagt: Zieh! <<TEST Kampf für Timo>>"  # a dead NPC speaks: violation
    brain = DMBrain(_Script([first, "<<UHR alarm>>"]), profile=_IM)  # the retry: marker-only
    brain.add_player_line(ch, "Timo", "Ich sehe mich um.")

    answer = asyncio.run(brain.respond(ch, check=lambda text: check(text, state, None)))
    assert answer == "Grendel sagt: Zieh!"  # empty retry discarded, first answer kept (fail-open)
    assert len(brain.take_pending_tests(ch)) == 1  # the kept answer's test is back

    assert brain.take_pending_uhr(ch) == []


# ---- echo guard ----------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "a batch turn whose echo retry comes back empty is stored as a (user, '') pair, while the "
    "same streamed turn is suppressed and stores nothing (code review 2026-11-13, finding 7)"))
def test_an_empty_echo_retry_stores_no_empty_turn() -> None:
    ch = 1
    brain = DMBrain(_Script(["Ich sehe mich um.", ""]))  # the echo, then an empty retry
    brain.add_player_line(ch, "Timo", "Ich sehe mich um.")

    assert asyncio.run(brain.respond(ch)) == ""  # content-less to the cog

    assert brain.history_len(ch) == 0
