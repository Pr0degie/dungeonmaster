"""A manifested damaging power books its damage in code (D153).

Live 2026-11-27, 16:34: Fridolin's Smite succeeded, the narration had the bolt throw the gate
guard against a cage — and the state kept him at 10/10 wounds. Damage is code (golden rules #2
and #3); the power's numbers come from the profile's ``damage`` block (ADR 022 amendment), the
target from the psyker's own line or the picker, exactly as for a weapon hit (D151).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dmbot.rules import engine

from test_attack_targets import _fighting_cog, _state

_CHANNEL = SimpleNamespace(guild=None)


def _manifest(*, success: bool, degrees: int = 2):
    test = engine.TestResult(roll=5 if success else 95, target=41, success=success, degrees=degrees,
                             critical=False, fumble=False, auto=False, resolution="roll_under")
    return SimpleNamespace(test=test)


def _finish(cog, *, power: str, result, said: str) -> None:
    resolved = SimpleNamespace(power=power, character=None, target=41)
    asyncio.run(cog._finish_manifest(_CHANNEL, None, ["🌀 …"], resolved=resolved, result=result,
                                     who="Fridolin", said=said))


def test_a_smite_that_names_its_target_costs_it_wounds() -> None:
    sent: list = []
    narrated: list = []
    state = _state()
    cog = _fighting_cog(state, sent, narrated)
    _finish(cog, power="Smite", result=_manifest(success=True, degrees=2),
            said="Ich schleudere einen Blitz auf den Kettenmann.")
    # Smite: 2 + Willpower Bonus (no sheet here: 0) + 2 SL = 4, armour ignored, Toughness Bonus 3 counts
    assert state.find("Kettenmann").wounds == 9
    assert [view for _, view in sent] == [None]              # the damage line, no picker
    assert "Kettenmann" in sent[0][0] and "Smite" in sent[0][0]
    assert narrated == [None]                                # one narration, after the damage


def test_a_smite_without_a_named_target_asks_who_is_hit() -> None:
    sent: list = []
    narrated: list = []
    state = _state()
    cog = _fighting_cog(state, sent, narrated)
    _finish(cog, power="Smite", result=_manifest(success=True),
            said="Ich will mit meinen psionischen Kräften angreifen.")
    text, view = sent[0]
    assert "wen trifft es" in text
    assert [o.label for o in view._select.options] == [
        "Schwester Vall", "Kettenmann", "Rektalus", "Niemand davon — nur erzählen"]
    assert narrated == []                                    # the pick narrates
    assert state.find("Kettenmann").wounds == 10
    # "nobody": the bolt hit a door — narrated, nothing booked
    asyncio.run(view._on_pick(None, "Niemand davon — nur erzählen"))
    assert narrated == [None]
    assert state.find("Kettenmann").wounds == 10 and state.find("Rektalus").wounds == 12


def test_a_lone_npc_is_not_hit_by_a_power_aimed_elsewhere() -> None:
    sent: list = []
    narrated: list = []
    state = _state()
    state.characters = [c for c in state.characters if c.name == "Fridolin"]   # a solo psyker
    cog = _fighting_cog(state, sent, narrated)
    cog._rt._scene_npcs = lambda st: [st.find("Kettenmann")]
    _finish(cog, power="Force Bolt", result=_manifest(success=True),
            said="Ich schleudere einen Force Bolt gegen die Tür.")
    _, view = sent[0]
    assert view is not None                                  # asked, not assumed
    assert state.find("Kettenmann").wounds == 10


def test_without_an_npc_in_the_scene_the_power_is_only_narrated() -> None:
    # an enemy the state does not know: never offer the team-mates instead
    sent: list = []
    narrated: list = []
    state = _state()
    cog = _fighting_cog(state, sent, narrated)
    cog._rt._scene_npcs = lambda st: []
    _finish(cog, power="Smite", result=_manifest(success=True), said="Ich greife den Kultisten an.")
    assert sent == [] and narrated == [None]
    assert state.find("Rektalus").wounds == 12


def test_a_target_that_left_the_state_is_said_not_silently_dropped() -> None:
    sent: list = []
    narrated: list = []
    cog = _fighting_cog(_state(), sent, narrated)
    resolved = SimpleNamespace(power="Smite", character=None, target=41)
    asyncio.run(cog._apply_power_damage(_CHANNEL, psyker="Fridolin", resolved=resolved,
                                        result=_manifest(success=True), target_name="Verschwunden"))
    assert "kein Schaden gebucht" in sent[0][0]
    assert narrated == [None]


def test_bio_lightning_books_its_primary_target() -> None:
    sent: list = []
    state = _state()
    _finish(_fighting_cog(state, sent, []), power="Bio-Lightning",
            result=_manifest(success=True, degrees=3), said="Der Blitz trifft den Kettenmann.")
    # 4 + 0 + 3 SL = 7, armour 0, Toughness Bonus 3 → 4 wounds
    assert state.find("Kettenmann").wounds == 6


def test_a_failed_manifest_and_a_power_without_damage_are_only_narrated() -> None:
    for power, result in (("Smite", _manifest(success=False)),
                          ("Psychic Static", _manifest(success=True)),
                          ("Nova", _manifest(success=True))):      # area: the GM's call
        sent: list = []
        narrated: list = []
        state = _state()
        _finish(_fighting_cog(state, sent, narrated), power=power, result=result,
                said="Ich ziele auf den Kettenmann.")
        assert sent == [], power
        assert narrated == [None], power
        assert state.find("Kettenmann").wounds == 10, power
