"""Opening briefing (`!start`): the GM-side director turn that introduces the adventure hook.

First-session complaint: `!join` never narrated the mission ("hat am Anfang nicht gesagt, was
abgeht"). `!start` runs a normal DM turn driven by a *director* instruction so the briefing is
spoken via the existing generate→speak path. Two decidable, deterministic properties are pinned
here (the audio/Discord half is verified manually per the phase gate):

- the director instruction reads as a GM/director message (not a player action) and forbids a
  dice test on the briefing;
- the opening turn produces an answer through the same `_build_request` path AND suppresses dice —
  a `<<TEST>>` the model emits on the opening must NOT queue a button (no roll on a briefing).
"""

from __future__ import annotations

import asyncio

from dmbot.orchestrator import DMBrain, build_opening_director_msg
from dmbot.rules import profile as profile_mod

_IM = profile_mod.load("imperium_maledictum")


def test_director_msg_is_a_gm_instruction_not_a_player_line() -> None:
    msg = build_opening_director_msg()
    # framed as a director instruction, not as something a player says
    assert msg.startswith("[Regie]")
    # it must hold the model to opening the session and forbid a dice test on the briefing
    assert "Probe" in msg  # "Verlange keine Probe." — no skill test on the opening
    lowered = msg.lower()
    assert "auftrag" in lowered or "eröffne" in lowered  # points at the opening/mission


class _CaptureClient:
    """Captures the messages/options DMBrain forwards and returns a canned opening answer that
    also carries a stray <<TEST>> marker — to prove the opening turn never queues a dice button."""

    def __init__(self) -> None:
        self.last_user_content: str | None = None

    async def chat(self, system, messages, options=None) -> str:
        self.last_user_content = messages[-1]["content"]
        # the model tries to request a roll on the briefing — must be suppressed by the opening path
        return "Inquisitor Halikarn mustert euch kalt. <<TEST Wahrnehmung für Mortn>>"

    async def aclose(self) -> None:
        pass


def test_opening_turn_runs_and_suppresses_dice() -> None:
    client = _CaptureClient()
    brain = DMBrain(client, profile=_IM)
    ch = 1
    brain.set_known_speakers(ch, ["Mortn", "Seskin"])

    answer = asyncio.run(brain.respond_opening(ch, build_opening_director_msg()))

    # the briefing came back through the normal request path, with the marker stripped from speech
    assert answer == "Inquisitor Halikarn mustert euch kalt."
    assert "<<" not in answer
    # NO dice button for a briefing — the opening turn must not queue a pending test
    assert brain.take_pending_tests(ch) == []
    # the director instruction was the turn's user message (not a buffered "Spieler:" line)
    assert client.last_user_content == build_opening_director_msg()
    # and it landed in history so the thread continues / is redo-able
    assert brain._history[ch][-1]["content"] == answer


def test_opening_turn_stored_for_redo() -> None:
    class _Seq:
        def __init__(self) -> None:
            self.n = 0

        async def chat(self, system, messages, options=None) -> str:
            self.n += 1
            return f"Auftakt {self.n}"

        async def aclose(self) -> None:
            pass

    brain = DMBrain(_Seq())
    ch = 5
    assert asyncio.run(brain.respond_opening(ch, build_opening_director_msg())) == "Auftakt 1"
    # the opening is a normal turn → !redo can re-roll it with the same director input
    assert asyncio.run(brain.redo(ch)) == "Auftakt 2"
    assert brain._history[ch][-2]["content"] == build_opening_director_msg()
