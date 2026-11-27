"""The attack target picker offers only who is present (ADR 062).

Live 2026-10-25: Fridolin shot the chain-gang thug at the shrine; the picker offered Seneschal Kaad
(two scenes away), Rektalus and Sister Vall — the thug was never state. Both hits landed on Kaad,
who then stood at 0/8 and dropped out of the prompt.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dmbot.llm.roll_router import OpenRolls
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
        _roll_batch_wait_seconds=30.0,
        _send_with_retry=send,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    cog._open_rolls = OpenRolls()
    cog._roll_waits = {}
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

# -- the attacker's own line names the target (D151, 2026-11-27) --------------------------------
#
# Live 2026-11-27: "Ich greife den Torwächter an" still had to go through the picker. A line that
# names exactly one present NPC hits that NPC; anything else (nobody named, several named, an
# ambiguous word, a line that turns someone down, only a team-mate named) keeps the picker.

from dmbot.rules import combat  # noqa: E402

_HALL = [
    ("Bree Marlok", ("Bree", "Marlok", "die Marlok")),
    ("Alter Fenk", ("Fenk", "der alte Fenk")),
    ("Torwächter", ()),
]
_MATES = [("Rektalus Zerfickus", ("Rektalus",))]


def _named(text: str, candidates=None) -> list[str]:
    return combat.named_targets(text, candidates if candidates is not None else [*_HALL, *_MATES])


def test_a_line_names_the_candidate_by_name_alias_inflection_or_compound_head() -> None:
    assert _named("Ich greife den Torwächter an.") == ["Torwächter"]
    assert _named("ich trete dem wächter in die eier") == ["Torwächter"]      # head of the compound
    assert _named("Ich reiße Brees Haare aus.") == ["Bree Marlok"]            # genitive s
    assert _named("Ich schlage auf den alten Fenk ein.") == ["Alter Fenk"]
    assert _named("Ich schieße auf Bree und den Wächter.") == ["Bree Marlok", "Torwächter"]
    cult = [("Kultist", ()), ("Kettenbund-Schläger", ())]
    assert _named("Ich greife den Kultisten an.", cult) == ["Kultist"]        # weak declension
    assert _named("Ich schieße auf den Kettenbund Schläger.", cult) == ["Kettenbund-Schläger"]
    assert _named("Ich haue dem Schläger eine rein.", cult) == ["Kettenbund-Schläger"]


def test_a_line_that_names_nobody_present_names_nobody() -> None:
    assert _named("Ich greife an.") == []
    assert _named("") == []
    assert _named("Alter, ich hau jetzt einfach drauf.") == []    # "Alter" alone is not Fenk
    assert _named("Ich greife Kaad an.") == []                    # not a candidate
    assert _named("Eine Breeze weht, der Mann fenkt.") == []      # whole words only
    assert _named("Ich schlage den Tor.") == []                   # a prefix is not the head


def test_a_word_that_fits_two_candidates_names_both() -> None:
    assert _named("Ich greife Kultist an.", [("Kultist", ()), ("Kultist 2", ())]) == ["Kultist", "Kultist 2"]
    assert _named("Ich schieße auf den Soldat.", [("Sturmsoldat", ()), ("Soldat Kern", ())]) == [
        "Sturmsoldat", "Soldat Kern"]
    # ... but an article inside an alias ("die Marlok") drags nobody else in
    assert _named("Ich greife die Marlok an.", [*_HALL, ("Nonne", ("die Nonne",))]) == ["Bree Marlok"]


def test_the_choice_is_one_named_npc_or_the_picker() -> None:
    choose = lambda text: combat.choose_attack_target(text, _HALL, _MATES)  # noqa: E731
    assert choose("Ich greife den Torwächter an.").auto == "Torwächter"
    assert choose("Ich greife an.").auto is None
    assert choose("Ich schieße auf Bree und den Wächter.").auto is None
    # turning a named figure down decides nothing
    assert choose("Ich schieße nicht auf den Torwächter, sondern auf die Frau daneben.").auto is None
    assert choose("Statt Fenk nehme ich den anderen.").auto is None
    # a team-mate is never hit unasked and never sits on top of the picker
    mate = choose("Rektalus und ich greifen an.")
    assert mate.auto is None
    assert mate.order == ["Bree Marlok", "Alter Fenk", "Torwächter", "Rektalus Zerfickus"]
    both = choose("Ich schieße auf den Wächter und auf Rektalus.")
    assert both.auto is None
    assert both.order == ["Torwächter", "Bree Marlok", "Alter Fenk", "Rektalus Zerfickus"]


def _fighting_cog(state: WorldState, sent: list, narrated: list) -> DiceCog:
    cog = _cog(state, sent)
    rt = cog._rt

    async def deliver(channel, guild_id):
        narrated.append(guild_id)

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


def test_several_named_targets_keep_the_picker_with_the_named_npcs_on_top() -> None:
    sent: list = []
    asyncio.run(_fighting_cog(_state(), sent, [])._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT,
        said="Ich schieße auf den Kettenmann und Rektalus."))
    _, view = sent[0]
    assert [o.label for o in view._select.options] == ["Kettenmann", "Schwester Vall", "Rektalus"]


def test_a_lone_team_mate_is_asked_for_never_hit_by_default() -> None:
    # Before D151 a single candidate was hit unseen — with no NPC placed yet that was the team-mate.
    sent: list = []
    state = _state()
    cog = _fighting_cog(state, sent, [])
    cog._rt._scene_npcs = lambda st: []
    took_over = asyncio.run(cog._begin_attack_damage(
        _CHANNEL, attacker="Fridolin", result=_HIT, said="Ich greife den Torwächter an."))
    assert took_over
    _, view = sent[0]
    assert [o.label for o in view._select.options] == ["Rektalus"]
    assert state.find("Rektalus").wounds == 12
