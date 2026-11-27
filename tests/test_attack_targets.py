"""The attack target picker offers only who is present (ADR 062).

Live 2026-10-25: Fridolin shot the chain-gang thug at the shrine; the picker offered Seneschal Kaad
(two scenes away), Rektalus and Sister Vall — the thug was never state. Both hits landed on Kaad,
who then stood at 0/8 and dropped out of the prompt.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dmbot.memory.state import Combatant, WorldState
from dmbot.rules import engine
from dmbot.rules.profile import load
from dmbot.voice.dicecog import DiceCog


def _cog(state: WorldState, sent: list) -> DiceCog:
    async def send(channel, content, view=None):
        sent.append((content, view))

    rt = SimpleNamespace(
        _brain_channel=lambda ch: 7,
        _state={7: state},
        _characters=SimpleNamespace(get=lambda name: None),
        _profile=load("imperium_maledictum"),
        _scene_npcs=lambda st: st.present_npcs("schrein", ["Schwester Vall"]),
        _adventure=None,
        _send_with_retry=send,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    return cog


def _state() -> WorldState:
    state = WorldState(session_id="7", scene_id="schrein")
    state.characters = [Combatant(name="Fridolin", wounds=10, max_wounds=10),
                        Combatant(name="Rektalus", wounds=12, max_wounds=12)]
    state.add_or_update_npc("Seneschall Kaad", wounds=8)       # zollhaus, not here
    state.add_or_update_npc("Schwester Vall", wounds=7)        # on the shrine card
    state.place_npc("Kettenmann", "schrein", wounds=10, toughness_bonus=3)
    return state


def test_the_picker_offers_present_npcs_then_the_party_never_npcs_elsewhere() -> None:
    sent: list = []
    hit = engine.TestResult(roll=10, target=33, success=True, degrees=2, critical=False,
                            fumble=False, auto=False, resolution="roll_under")
    took_over = asyncio.run(_cog(_state(), sent)._begin_attack_damage(
        object(), attacker="Fridolin", result=hit))
    assert took_over
    _, view = sent[0]
    options = [o.label for o in view._select.options]
    assert options == ["Schwester Vall", "Kettenmann", "Rektalus"]
    assert "Seneschall Kaad" not in options


# -- the attacker's own line names the target (2026-11-27) --------------------------------------
#
# Live 2026-11-27: "Ich greife den Torwächter an" still had to go through the picker. A line that
# names exactly one present NPC hits that NPC; anything else (nobody named, several named, only a
# team-mate named) keeps the picker, with the named ones on top.

from dmbot.rules import combat  # noqa: E402

_HALL = [
    ("Bree Marlok", ("Bree", "Marlok", "die Marlok")),
    ("Alter Fenk", ("Fenk", "der alte Fenk")),
    ("Torwächter", ()),
    ("Rektalus Zerfickus", ("Rektalus",)),
]


def test_a_line_names_the_candidate_by_name_alias_genitive_or_compound_head() -> None:
    named = lambda text: combat.named_targets(text, _HALL)  # noqa: E731
    assert named("Ich greife den Torwächter an.") == ["Torwächter"]
    assert named("ich trete dem wächter in die eier") == ["Torwächter"]      # head of the compound
    assert named("Ich reiße Brees Haare aus.") == ["Bree Marlok"]            # genitive s
    assert named("Ich schlage auf den alten Fenk ein, also der alte Fenk.") == ["Alter Fenk"]
    assert named("Ich schieße auf Bree und den Wächter.") == ["Bree Marlok", "Torwächter"]


def test_a_line_that_names_nobody_present_names_nobody() -> None:
    named = lambda text: combat.named_targets(text, _HALL)  # noqa: E731
    assert named("Ich greife an.") == []
    assert named("") == []
    assert named("Alter, ich hau jetzt einfach drauf.") == []    # "Alter" alone is not Fenk
    assert named("Ich greife Kaad an.") == []                    # not a candidate
    assert named("Eine Breeze weht, der Mann fenkt.") == []      # whole words only
    assert named("Ich schlage den Tor.") == []                   # a prefix is not the head


def _fighting_cog(state: WorldState, sent: list, narrated: list) -> DiceCog:
    cog = _cog(state, sent)
    rt = cog._rt

    async def deliver(channel, guild_id):
        narrated.append(guild_id)

    rt._scene_npcs = lambda st: st.present_npcs("schrein", ["Schwester Vall"])
    rt._adventure = SimpleNamespace(
        npc=lambda name: SimpleNamespace(aliases=("Vall", "Schwester Vall"))
        if name == "Schwester Vall" else None)
    rt._rng = __import__("random").Random(3)
    rt._persist_and_refresh = lambda channel: None
    rt._brain = SimpleNamespace(add_test_result=lambda cid, line: None)
    rt.run_and_deliver = deliver
    return cog


_HIT = engine.TestResult(roll=10, target=33, success=True, degrees=2, critical=False,
                         fumble=False, auto=False, resolution="roll_under")
_CHANNEL = SimpleNamespace(guild=None)


def test_a_line_naming_one_present_npc_hits_it_without_the_picker() -> None:
    sent: list = []
    narrated: list = []
    state = _state()
    took_over = asyncio.run(_fighting_cog(state, sent, narrated)._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT, said="Ich schieße auf den Kettenmann."))
    assert took_over
    assert [view for _, view in sent] == [None]          # the damage line, no picker
    assert "Kettenmann" in sent[0][0]
    assert state.find("Kettenmann").wounds < 10
    assert state.find("Schwester Vall").wounds == 7
    assert narrated == [None]                            # narrated once


def test_several_named_targets_keep_the_picker_with_them_on_top() -> None:
    sent: list = []
    asyncio.run(_fighting_cog(_state(), sent, [])._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT,
        said="Ich schieße auf den Kettenmann und auf Vall."))
    _, view = sent[0]
    assert [o.label for o in view._select.options] == ["Schwester Vall", "Kettenmann", "Rektalus"]
    sent.clear()
    asyncio.run(_fighting_cog(_state(), sent, [])._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT, said="Ich schieße auf den Kettenmann und Rektalus."))
    _, view = sent[0]
    assert [o.label for o in view._select.options] == ["Kettenmann", "Rektalus", "Schwester Vall"]


def test_a_team_mate_named_alone_is_never_hit_without_the_picker() -> None:
    sent: list = []
    state = _state()
    asyncio.run(_fighting_cog(state, sent, [])._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT, said="Rektalus und ich greifen an."))
    _, view = sent[0]
    assert view is not None
    assert [o.label for o in view._select.options] == ["Rektalus", "Schwester Vall", "Kettenmann"]
    assert state.find("Rektalus").wounds == 12
