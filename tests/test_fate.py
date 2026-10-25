"""Fate points (IM Core Rulebook p.220, ADR 063).

Every character begins with 3 Fate. Spending one rerolls a failed Test (the second result stands);
spent Fate recovers at the start of each session. Burning Fate is out of scope. The resource is
code-owned like Warp Charge (golden rule #3); the model never writes it.

Live 2026-10-25: 0 of 9 tests succeeded in one run and the table asked whether it was them —
Fridolin's sheet listed 3 Fate the bot did not know about.
"""

from __future__ import annotations

from dmbot.memory.state import Combatant, WorldState, world_state_summary_de
from dmbot.rules.characters import Character, CharacterStore
from dmbot.rules.profile import SystemProfile, load

_IM = load("imperium_maledictum")
_BARE = SystemProfile.from_dict({"name": "x", "dice": "1d100", "resolution": "roll_under"})


def test_the_im_profile_grants_three_fate_and_a_bare_profile_none() -> None:
    assert _IM.fate_enabled() and _IM.fate_start() == 3
    assert not _BARE.fate_enabled() and _BARE.fate_start() == 0


def test_the_sheet_fate_total_is_read_and_tolerates_strings_and_absence() -> None:
    assert Character.from_dict({"name": "F", "fate_total": "3", "fate_current": "2"}).fate_total == 3
    assert Character.from_dict({"name": "F", "fate": 2}).fate_total == 2
    assert Character.from_dict({"name": "R"}).fate_total is None
    assert Character.from_dict({"name": "R", "fate_total": "viel"}).fate_total is None


def _state() -> WorldState:
    store = CharacterStore.from_dict({"characters": [
        {"name": "Fridolin", "wounds": 10, "max_wounds": 10, "fate_total": "2"},
        {"name": "Rektalus", "wounds": 12, "max_wounds": 12},
    ]})
    return WorldState.seed_from_store(store)


def test_a_session_start_fills_unset_fate_from_the_profile_and_recovers_spent_fate() -> None:
    s = _state()
    s.start_fate_session(default=3)
    assert [(c.name, c.fate_total, c.fate_available) for c in s.characters] == [
        ("Fridolin", 2, 2), ("Rektalus", 3, 3)]
    assert s.spend_fate("Rektalus") and s.find("Rektalus").fate_available == 2
    s.start_fate_session(default=3)
    assert s.find("Rektalus").fate_available == 3     # spent Fate recovers each session


def test_spending_stops_at_zero_and_never_touches_npcs_or_strangers() -> None:
    s = _state()
    s.start_fate_session(default=3)
    assert s.spend_fate("fridolin") and s.spend_fate("Fridolin")
    assert not s.spend_fate("Fridolin")                # 2 of 2 spent
    assert s.find("Fridolin").fate_available == 0
    s.add_or_update_npc("Kettenmann", wounds=10)
    assert not s.spend_fate("Kettenmann") and not s.spend_fate("Niemand")


def test_fate_round_trips_through_the_saved_state() -> None:
    s = _state()
    s.start_fate_session(default=3)
    s.spend_fate("Rektalus")
    again = WorldState.from_dict(s.to_dict())
    assert (again.find("Rektalus").fate_total, again.find("Rektalus").fate_available) == (3, 2)
    assert Combatant.from_dict({"name": "Alt", "wounds": 5, "max_wounds": 5}).fate_total is None


def test_the_prompt_shows_the_remaining_fate() -> None:
    s = _state()
    before = world_state_summary_de(s)
    assert "Rektalus 12/12;" in before or before.rstrip().endswith("Rektalus 12/12")  # unset → not shown
    s.start_fate_session(default=3)
    s.spend_fate("Rektalus")
    out = world_state_summary_de(s)
    assert "Fridolin 10/10 (Schicksal 2/2)" in out and "Rektalus 12/12 (Schicksal 2/3)" in out


# --- the choice under a failed test --------------------------------------------------------------

import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from dmbot.discord_ui.fate import FateView  # noqa: E402
from dmbot.voice.dicecog import DiceCog  # noqa: E402


class _Seq:
    def __init__(self, *values: int) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


class _Msg:
    def __init__(self) -> None:
        self.content = ""

    async def edit(self, *, content=None, view=None) -> None:
        if content is not None:
            self.content = content


def _cog(rng):
    s = _state()
    s.start_fate_session(default=3)
    fed: list[str] = []
    narrated: list[int] = []

    async def run_and_deliver(channel, guild_id):
        narrated.append(1)

    rt = SimpleNamespace(
        _profile=_IM, _rng=rng, _state={7: s}, _brain_channel=lambda ch: 7,
        _brain=SimpleNamespace(add_test_result=lambda cid, line: fed.append(line)),
        _persist_and_refresh=lambda ch: None, run_and_deliver=run_and_deliver,
    )
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    return cog, s, fed, narrated


def _decide(cog, spend: bool):
    resolved = SimpleNamespace(target=40, difficulty="Herausfordernd")
    first, line = cog._roll_test(resolved, "Heimlichkeit", "Rektalus")
    msg = _Msg()
    decide = cog._make_fate_decision(object(), None, msg, resolved, "Heimlichkeit", "Rektalus",
                                     first, line)
    asyncio.run(decide(None, spend))
    return first, msg


def test_spending_fate_rerolls_and_the_second_result_stands() -> None:
    cog, s, fed, narrated = _cog(_Seq(75, 12))        # first roll fails, reroll succeeds
    first, msg = _decide(cog, True)
    assert not first.success
    assert s.find("Rektalus").fate_available == 2
    assert len(fed) == 1 and "Schicksalspunkt" in fed[0] and "dieses Ergebnis gilt" in fed[0]
    assert "12 — Erfolg" in fed[0]
    assert "75" in msg.content and "12" in msg.content  # the channel keeps both rolls
    assert narrated == [1]                             # one narration for the whole test


def test_keeping_the_failure_spends_nothing_and_narrates_it() -> None:
    cog, s, fed, narrated = _cog(_Seq(75))
    _decide(cog, False)
    assert s.find("Rektalus").fate_available == 3
    assert len(fed) == 1 and "75 — Fehlschlag" in fed[0] and narrated == [1]


def test_only_a_character_with_fate_left_gets_the_choice() -> None:
    cog, s, _, _ = _cog(_Seq())
    assert cog._fate_holder(object(), "Rektalus") is not None
    for _ in range(3):
        s.spend_fate("Rektalus")
    assert cog._fate_holder(object(), "Rektalus") is None
    s.add_or_update_npc("Kettenmann", wounds=10)
    assert cog._fate_holder(object(), "Kettenmann") is None and cog._fate_holder(object(), None) is None


def test_the_view_counts_only_the_first_decision() -> None:
    decisions: list[bool] = []

    async def on_decide(interaction, spend):
        decisions.append(spend)

    class _Response:
        async def edit_message(self, **kw):
            return None

    async def scenario():
        view = FateView(2, on_decide, timeout=5)
        await view.on_timeout()                                   # nobody clicked in time
        await view._on_spend(SimpleNamespace(response=_Response()))  # a late click
        return view

    view = asyncio.run(scenario())
    assert decisions == [False]
    assert "noch 2" in view._spend_btn.label
