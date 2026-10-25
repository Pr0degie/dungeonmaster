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
