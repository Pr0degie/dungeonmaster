"""Psyker / Warp subsystem (ADR 022) — deterministic unit tests.

Covers the system-agnostic engine spine (Manifest Test, Warp Charge bookkeeping, Advantage from
Pushing, Perils/Phenomena table rolls), the profile catalog helpers, the character→numbers
resolver, the <<MANIFEST …>> marker, and the Warp Charge state round-trip. Pure + fixed-seed, so
outcomes are asserted exactly (golden rule: dice = code).
"""

from __future__ import annotations

import asyncio
import random
import types

import pytest

from dmbot.rules import engine, profile as profile_mod
from dmbot.rules.engine import TestResult as _TestResult
from dmbot.rules.characters import Character, CharacterStore, resolve_manifest_request
from dmbot.rules.marker import ManifestRequest, extract_manifests
from dmbot.memory.state import Combatant, WorldState, world_state_summary_de
from dmbot.voice.dicecog import DiceCog

_IM = profile_mod.load("imperium_maledictum")


def _result(*, roll: int, target: int, success: bool, degrees: int, critical=False, fumble=False) -> _TestResult:
    return _TestResult(
        roll=roll, target=target, success=success, degrees=degrees,
        critical=critical, fumble=fumble, auto=False, resolution="roll_under",
    )


# -- profile catalog ----------------------------------------------------------------------

def test_profile_exposes_psyker_block() -> None:
    assert _IM.psyker_enabled()
    assert _IM.psyker_test_skill() == "Psi-Meisterschaft"
    assert _IM.threshold_characteristic() == "Wil"
    assert "Smite" in _IM.power_names()


def test_power_lookup_is_case_insensitive_and_carries_stats() -> None:
    p = _IM.power("smite")
    assert p is not None and p["name"] == "Smite"
    assert p["warp_rating"] == 2 and p["difficulty"] == "Schwierig" and p["overt"] is True
    assert _IM.power("does-not-exist") is None


def test_warp_threshold_is_willpower_bonus_tens() -> None:
    assert _IM.warp_threshold(48) == 4   # Willpower 48 → Bonus 4
    assert _IM.warp_threshold(30) == 3
    assert _IM.warp_threshold(None) == 0


def test_perils_and_phenomena_tables_are_loaded() -> None:
    assert len(_IM.perils_table()) >= 18
    assert any(row.get("redirect") == "perils" for row in _IM.phenomena_table())


# -- Advantage / reverse-the-digits (IM p.189) --------------------------------------------

@pytest.mark.parametrize("face,rev", [(72, 27), (5, 50), (40, 4), (100, 100), (11, 11), (10, 1)])
def test_reverse_d100(face: int, rev: int) -> None:
    assert engine.reverse_d100(face) == rev


def test_advantage_never_worse_than_plain_roll() -> None:
    # For the same seed, a Pushed (Advantage) roll-under is never a higher face than the plain roll.
    for seed in range(50):
        plain = engine.resolve_roll_under(_IM, 50, random.Random(seed))
        adv = engine.resolve_roll_under(_IM, 50, random.Random(seed), advantage=1)
        dis = engine.resolve_roll_under(_IM, 50, random.Random(seed), advantage=-1)
        assert adv.roll <= plain.roll
        assert dis.roll >= plain.roll


# -- Warp Charge gain (IM p.163) ----------------------------------------------------------

def test_warp_charge_gain_on_success_is_warp_rating() -> None:
    r = _result(roll=20, target=45, success=True, degrees=2)
    assert engine.warp_charge_gain(r, warp_rating=3, willpower_bonus=4) == 3


def test_critical_reduces_warp_rating_by_willpower_bonus_min_one() -> None:
    r = _result(roll=22, target=45, success=True, degrees=2, critical=True)
    assert engine.warp_charge_gain(r, warp_rating=3, willpower_bonus=4) == 1  # 3-4 → min 1


def test_failure_gains_one_per_negative_sl_capped_at_rating() -> None:
    r = _result(roll=70, target=45, success=False, degrees=-2)
    assert engine.warp_charge_gain(r, warp_rating=4, willpower_bonus=4) == 2  # min(4, 2)
    r5 = _result(roll=99, target=45, success=False, degrees=-5)
    assert engine.warp_charge_gain(r5, warp_rating=3, willpower_bonus=4) == 3  # min(3, 5)


def test_fumble_doubles_and_push_adds() -> None:
    f = _result(roll=66, target=45, success=False, degrees=-2, fumble=True)
    assert engine.warp_charge_gain(f, warp_rating=3, willpower_bonus=4) == 4  # min(3,2)=2, doubled
    assert engine.warp_charge_gain(f, warp_rating=3, willpower_bonus=4, pushed=True, push_roll=3) == 7


# -- resolve_manifest ---------------------------------------------------------------------

def test_resolve_manifest_bookkeeps_charge_against_threshold() -> None:
    rng = random.Random(1)
    res = engine.resolve_manifest(
        _IM, test_target=45, power="Smite", warp_rating=2,
        current_charge=3, willpower_bonus=4, threshold=4, rng=rng,
    )
    # the new total is the old charge plus whatever the rules awarded for this test
    expected_gain = engine.warp_charge_gain(res.test, 2, 4)
    assert res.charge_gained == expected_gain
    assert res.warp_charge == 3 + expected_gain
    assert res.over_threshold == (res.warp_charge > 4)


def test_push_fumble_flags_immediate_perils() -> None:
    # Find a seed whose Pushed Manifest Test fumbles, and assert the immediate-Perils flag.
    for seed in range(2000):
        rng = random.Random(seed)
        res = engine.resolve_manifest(
            _IM, test_target=20, power="Smite", warp_rating=2,
            current_charge=0, willpower_bonus=4, pushed=True, rng=rng,
        )
        if res.test.fumble:
            assert res.immediate_perils is True
            break
    else:
        pytest.fail("no fumble found across seeds — adjust the search")


# -- Perils / Phenomena tables ------------------------------------------------------------

def test_perils_bonus_pushes_into_higher_bands() -> None:
    # over_by 20 → +200 to the d100 → always the open-ended top band (corruption 5).
    out = engine.resolve_perils(_IM, over_by=20, rng=random.Random(0))
    assert out.total > 200 and out.name == "Auge des Schreckens" and out.corruption == 5


def test_perils_low_roll_lands_in_first_band_with_corruption() -> None:
    out = engine.resolve_perils(_IM, over_by=1, rng=random.Random(3))
    assert out.table == "perils" and out.corruption >= 1 and out.effect


def test_phenomena_high_total_redirects_to_perils() -> None:
    # shed 15 → +150 → total ≥ 151 → the 126+ row redirects onto the Perils table.
    out = engine.resolve_phenomena(_IM, shed=15, rng=random.Random(0))
    assert out.table == "perils"


def test_lookup_band_edges() -> None:
    table = [{"min": 11, "max": 40, "name": "a"}, {"min": 41, "name": "b"}]
    assert engine._lookup_band(table, 5)["name"] == "a"    # below the floor clamps to first
    assert engine._lookup_band(table, 40)["name"] == "a"
    assert engine._lookup_band(table, 999)["name"] == "b"  # open-ended top


# -- character → numbers resolver ---------------------------------------------------------

def _mortn() -> CharacterStore:
    return CharacterStore([
        Character.from_dict({
            "name": "Mortn",
            "characteristics": {"Wil": 48, "Int": 52},
            "skills": {"Psi-Meisterschaft": 45},
            "psyker": True,
            "known_powers": ["Smite", "Seal Wounds"],
        })
    ])


def test_resolve_manifest_request_computes_target_threshold_and_rating() -> None:
    store = _mortn()
    rm = resolve_manifest_request(_IM, store, power="Smite", target_name="Mortn")
    assert rm is not None
    assert rm.warp_rating == 2
    assert rm.modifier == -10              # Smite is Difficult (Schwierig)
    assert rm.base == 45 and rm.target == 35
    assert rm.willpower_bonus == 4 and rm.threshold == 4


def test_containment_target_derives_from_discipline_not_mastery() -> None:
    # Finding #1: the Warp-containment Test rolls against Disziplin (Psi), not Psi-Meisterschaft.
    store = CharacterStore([
        Character.from_dict({
            "name": "Vael",
            "characteristics": {"Wil": 40},
            "skills": {"Psi-Meisterschaft": 60, "Disziplin (Psi)": 30},
            "psyker": True,
            "known_powers": ["Smite"],
        })
    ])
    rm = resolve_manifest_request(_IM, store, power="Smite", target_name="Vael")
    assert rm is not None
    # Manifest still rolls against Psi-Meisterschaft 60 (Smite is Schwierig -10 → 50)...
    assert rm.base == 60 and rm.target == 50
    # ...but the containment base comes from Disziplin (Psi) 30, not 60.
    assert rm.contain_base == 30
    # The containment target dicecog builds (Herausfordernd modifier is +0) therefore derives from 30.
    contain_target = (rm.contain_base or 0) + (_IM.difficulty_modifier("Herausfordernd") or 0)
    assert contain_target == 30


def test_resolve_manifest_request_unknown_power_is_none() -> None:
    assert resolve_manifest_request(_IM, _mortn(), power="Fireball", target_name="Mortn") is None


def test_resolve_manifest_request_without_skill_has_no_target() -> None:
    store = CharacterStore([
        Character.from_dict({"name": "Lay", "characteristics": {"Wil": 30}, "psyker": True})
    ])
    rm = resolve_manifest_request(_IM, store, power="Smite", target_name="Lay")
    assert rm is not None and rm.target is None and rm.threshold == 3


# -- <<MANIFEST …>> marker ----------------------------------------------------------------

def test_extract_manifest_basic() -> None:
    clean, reqs = extract_manifests("Mortn greift an. <<MANIFEST Smite für Mortn>>", _IM)
    assert "<<" not in clean and reqs[0].power == "Smite"
    assert reqs[0].target_name == "Mortn" and reqs[0].pushed is False


def test_extract_manifest_push_and_multiword_power() -> None:
    _clean, reqs = extract_manifests("<<MANIFEST Seal Wounds für Mortn push>>", _IM)
    assert reqs[0].power == "Seal Wounds" and reqs[0].target_name == "Mortn" and reqs[0].pushed is True


def test_extract_manifest_empty_is_unparsed() -> None:
    _clean, reqs = extract_manifests("<<MANIFEST für Mortn>>", _IM)
    assert reqs[0].parsed is False and reqs[0].target_name == "Mortn"


# -- Warp Charge in the mutable state -----------------------------------------------------

def test_combatant_warp_charge_round_trips() -> None:
    c = Combatant(name="Mortn", wounds=9, max_wounds=9, warp_charge=3, sustained_powers=["Soulsight"])
    back = Combatant.from_dict(c.to_dict())
    assert back.warp_charge == 3 and back.sustained_powers == ["Soulsight"]


def test_world_state_warp_helpers_and_summary() -> None:
    state = WorldState(characters=[Combatant(name="Mortn", wounds=9, max_wounds=9)])
    state.set_warp_charge("Mortn", 5)
    state.sustain_power("Mortn", "Soulsight")
    assert "Warp 5" in world_state_summary_de(state)
    state.reset_warp_charge("Mortn")  # Perils resets charge to 0 and drops sustained powers
    m = state.find("Mortn")
    assert m.warp_charge == 0 and m.sustained_powers == []


# -- not-in-state party psyker warns instead of silently dropping Warp Charge (finding #2) --

class _FakeMessage:
    def __init__(self) -> None:
        self.content = None

    async def edit(self, *, content=None, view=None) -> None:
        self.content = content


class _FakeInteraction:
    def __init__(self) -> None:
        self.message = _FakeMessage()


def _fake_runtime(*, store: CharacterStore, state: WorldState | None):
    """A minimal stand-in for SessionRuntime exposing only what _make_manifest_roll touches."""
    rt = types.SimpleNamespace()
    rt._profile = _IM
    rt._rng = random.Random(7)
    rt._characters = store
    rt._state = {1: state} if state is not None else {}
    rt._brain_channel = lambda channel: 1
    rt._brain = types.SimpleNamespace(add_test_result=lambda cid, ln: None)
    rt._persist_and_refresh = lambda channel: None

    async def _send_with_retry(channel, content=None, *, view=None):
        return None

    async def _run_and_deliver(channel, guild_id):
        return None

    rt._send_with_retry = _send_with_retry
    rt.run_and_deliver = _run_and_deliver
    return rt


def test_manifest_warns_when_party_psyker_not_in_world_state() -> None:
    # Mortn is a known party psyker (in the store) but absent from this session's WorldState — the
    # in-combat Warp-Charge path can't run, so the GM must be warned rather than lose the resource.
    store = CharacterStore([
        Character.from_dict({
            "name": "Mortn",
            "characteristics": {"Wil": 48},
            "skills": {"Psi-Meisterschaft": 45, "Disziplin (Psi)": 30},
            "psyker": True,
            "known_powers": ["Smite"],
        })
    ])
    state = WorldState(characters=[])  # encounter has no Mortn
    rt = _fake_runtime(store=store, state=state)
    cog = DiceCog.__new__(DiceCog)  # skip __init__ (needs a real bot); set only what we use
    cog._rt = rt
    cog._warp_untracked_warned = set()

    resolved = resolve_manifest_request(_IM, store, power="Smite", target_name="Mortn")
    assert resolved is not None and resolved.target is not None
    req = ManifestRequest(power="Smite", target_name="Mortn")
    channel = types.SimpleNamespace(guild=None)
    roll = cog._make_manifest_roll(channel, req, resolved)
    interaction = _FakeInteraction()
    asyncio.run(roll(interaction))

    assert "Warp-Aufladung wird nicht verfolgt" in interaction.message.content
    assert "Mortn" in interaction.message.content


def test_manifest_warning_is_one_time_per_psyker() -> None:
    # The warning must not spam the channel: the second Manifest in the same channel stays silent.
    store = CharacterStore([
        Character.from_dict({
            "name": "Mortn",
            "characteristics": {"Wil": 48},
            "skills": {"Psi-Meisterschaft": 45, "Disziplin (Psi)": 30},
            "psyker": True,
            "known_powers": ["Smite"],
        })
    ])
    rt = _fake_runtime(store=store, state=WorldState(characters=[]))
    cog = DiceCog.__new__(DiceCog)
    cog._rt = rt
    cog._warp_untracked_warned = set()

    resolved = resolve_manifest_request(_IM, store, power="Smite", target_name="Mortn")
    req = ManifestRequest(power="Smite", target_name="Mortn")
    channel = types.SimpleNamespace(guild=None)
    roll = cog._make_manifest_roll(channel, req, resolved)

    first = _FakeInteraction()
    asyncio.run(roll(first))
    assert "Warp-Aufladung wird nicht verfolgt" in first.message.content
    second = _FakeInteraction()
    asyncio.run(roll(second))
    assert "Warp-Aufladung wird nicht verfolgt" not in second.message.content
