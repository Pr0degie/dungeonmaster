"""Open findings in DMBrain and its turn path, pinned as strict xfails until fixed.

The code review of the orchestrator de-duplication (2026-11-13, ``ddaae08..9ec06b6``) found
seven faults the refactor carried over unchanged; the live run of the same night (01:48–02:16)
added two more, at the bottom of this file. Each test asserts the WANTED behaviour and fails
until fixed; ``strict=True`` turns the test red the moment a fix lands, so the mark gets
removed with it — a test without the mark is a fixed finding.

Seen live: review finding 3 (turn 20 of that run, 02:05:49 — the history stood exactly at its
cap when the auto-recap began, and the turn that landed during the summary is in neither the
recap nor the history) and the two live-run findings. The other six review findings were
derived from the code and have not been seen live. All are listed in ``progress.md`` under
"Open questions".

Public API only — the tests drive ``DMBrain`` the way the cogs do. The journal test also calls
the cog's autosave, the way the delivery pipeline does after playback.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from dmbot.llm.consistency import check
from dmbot.memory.state import Combatant, WorldState
from dmbot.orchestrator import DMBrain, build_opening_director_msg
from dmbot.rules import profile as profile_mod
from dmbot.voice.dmcog import DMCog

from fakes import make_runtime

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

    async def chat_stream(self, system, messages, options=None):
        answer = await self.chat(system, messages, options)
        for i in range(0, len(answer), 9):
            yield answer[i:i + 9]

    async def aclose(self) -> None:
        pass


def _contents(brain: DMBrain, ch: int) -> list[str]:
    return [m["content"] for m in brain.history_messages(ch)]


# ---- compaction vs. a concurrent turn ------------------------------------------------------

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


# ---- live run 2026-11-13 -------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "the replay capture (lines/results/raw/markers, ADR 046) is one slot per channel that the "
    "autosave reads after playback; a turn that starts while the previous one is still being "
    "spoken overwrites it, so the previous turn's journal record carries the next turn's "
    "fields and the next turn's record has none — live 2026-11-13: 13 of 22 records (2026-10-31: "
    "6 of 21)"))
def test_a_turn_started_during_playback_leaves_the_previous_turns_replay_fields(tmp_path) -> None:
    ch = 7
    journal = tmp_path / "history.jsonl"
    brain = DMBrain(_Script(["Die Tür schwingt auf.", "Dahinter liegt ein dunkler Gang."]))
    cog = object.__new__(DMCog)  # __init__ skipped (the test_subcogs pattern)
    cog._rt = make_runtime(
        _autosave=True, _brain_channel=lambda channel: ch, _brain=brain,
        _state={ch: WorldState()}, _history_path=lambda cid: journal,
    )
    channel = SimpleNamespace(id=ch)

    brain.add_player_line(ch, "Timo", "Ich öffne die Tür.")
    first = asyncio.run(brain.respond(ch))
    first_user = brain.last_user_msg(ch)  # snapshotted at generation end, as delivery does (D43)
    # The first answer is still being spoken when the player declares the next action.
    brain.add_player_line(ch, "Timo", "Ich gehe hinein.")
    second = asyncio.run(brain.respond(ch))
    second_user = brain.last_user_msg(ch)
    # Each turn is autosaved when its own playback ends.
    asyncio.run(cog._autosave_turn(channel, first, user_msg=first_user))
    asyncio.run(cog._autosave_turn(channel, second, user_msg=second_user))

    recs = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [(r["user_msg"], r["answer"]) for r in recs] == [
        ("Timo: Ich öffne die Tür.", "Die Tür schwingt auf."),
        ("Timo: Ich gehe hinein.", "Dahinter liegt ein dunkler Gang."),
    ]  # the pairs themselves are right (D43)

    assert (recs[0].get("lines"), recs[0].get("raw")) == (
        [["Timo", "Ich öffne die Tür."]], "Die Tür schwingt auf.")
    assert (recs[1].get("lines"), recs[1].get("raw")) == (
        [["Timo", "Ich gehe hinein."]], "Dahinter liegt ein dunkler Gang.")


@pytest.mark.xfail(strict=True, reason=(
    "_SENTENCE_END accepts ” ’ » after the terminator but not the German closing quote “ (nor «), "
    "so _trim_to_last_sentence takes a complete final sentence ending on ?“ .“ or !“ for a "
    "dangling fragment and drops it — not spoken, not posted, not stored, with no output cut "
    "involved; live 2026-11-13: 5 of 22 answers (turn 20, 02:05:49), 15 of 136 earlier in the log"))
def test_a_final_sentence_ending_on_the_german_closing_quote_is_spoken_and_stored() -> None:
    ch = 1
    last = "Wessen Namen soll ich neben deinen schreiben?“"
    raw = f"Bree legt den Federkiel quer über die Seite. „Na dann“, sagt sie leise, „ich höre. {last}"
    brain = DMBrain(_Script([raw]))
    brain.add_player_line(ch, "Timo", "Ich erzähle ihr, wer mich schickt.")
    spoken: list[str] = []

    async def on_sentence(sentence: str) -> None:
        spoken.append(sentence)

    answer = asyncio.run(brain.respond_streaming(ch, on_sentence=on_sentence))

    assert answer.endswith(last)           # what is posted
    assert spoken[-1].endswith(last)       # what is spoken
    assert _contents(brain, ch)[-1].endswith(last)  # what is stored
