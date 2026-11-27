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
    assert [o.label for o in view._select.options] == ["Schwester Vall", "Kettenmann", "Rektalus"]
    assert narrated == []                                    # the pick narrates
    assert state.find("Kettenmann").wounds == 10


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
