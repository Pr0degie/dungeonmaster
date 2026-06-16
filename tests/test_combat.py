"""Pure combat arithmetic (dmbot/rules/combat.py) — deterministic unit tests.

Covers the soak/Toughness-Bonus lookup, the attack soak+damage roll, augmetic armour in soak,
the 0-floor on applied wounds, and the Warp-consequence chain (no-trigger / containment-success /
containment-failure / immediate-Perils). All pure + fixed-seed (golden rule #2: dice = code), so
the numbers are asserted exactly and prove the move out of the cog is arithmetic-faithful.
"""

from __future__ import annotations

import random
import types

from dmbot.rules import combat, engine, profile as profile_mod
from dmbot.rules.characters import Character, CharacterStore, augmetic_armour

_IM = profile_mod.load("imperium_maledictum")


# -- toughness_bonus ----------------------------------------------------------------------

def test_toughness_bonus_tens_mode() -> None:
    store = CharacterStore([Character.from_dict({"name": "Vask", "characteristics": {"Tgh": 45}})])
    assert combat.toughness_bonus(_IM, store, store.get("Vask")) == 4  # tens of 45


def test_toughness_bonus_none_profile_is_zero() -> None:
    store = CharacterStore([Character.from_dict({"name": "Vask", "characteristics": {"Tgh": 45}})])
    assert combat.toughness_bonus(None, store, store.get("Vask")) == 0


def test_toughness_bonus_none_character_is_zero() -> None:
    store = CharacterStore([Character.from_dict({"name": "Vask", "characteristics": {"Tgh": 45}})])
    assert combat.toughness_bonus(_IM, store, None) == 0


def test_toughness_bonus_missing_characteristic_is_zero() -> None:
    store = CharacterStore([Character.from_dict({"name": "NoTgh", "characteristics": {"Wil": 40}})])
    assert combat.toughness_bonus(_IM, store, store.get("NoTgh")) == 0


def test_toughness_bonus_tolerates_trailing_space_in_sheet_key() -> None:
    # A sheet whose Toughness key drifted to "Tgh " (trailing space) must still soak correctly:
    # the store's skill_value strips + lower-cases, so it resolves to 45 → bonus 4 (finding #9).
    store = CharacterStore([Character.from_dict({"name": "Drift", "characteristics": {"Tgh ": 45}})])
    assert combat.toughness_bonus(_IM, store, store.get("Drift")) == 4


# -- resolve_attack: NPC path -------------------------------------------------------------

def test_resolve_attack_npc_soak_and_applied_match_engine_directly() -> None:
    # NPC carries its own Toughness Bonus + armour; soak = 3 + 2 = 5, no augmetic.
    target = types.SimpleNamespace(is_npc=True, toughness_bonus=3, armour=2)
    out = combat.resolve_attack(
        _IM, None, target=target, target_sheet=None,
        notation="1d10+5", success_level=2, rng=random.Random(7),
    )
    assert out.toughness_bonus == 3 and out.armour == 2 and out.augmetic_armour == 0
    assert out.soak == 5
    # Same seed + same soak through the engine directly → identical applied wounds (move is faithful).
    roll = engine.roll_damage("1d10+5", random.Random(7))
    expected = engine.resolve_damage(roll, 2, 5)
    assert out.damage.applied == expected.applied


# -- resolve_attack: PC path with augmetic armour ----------------------------------------

def test_resolve_attack_pc_includes_augmetic_armour_in_soak() -> None:
    # Mirror test_augmetics "Augmetischer Arm" (+1 armour effect): it must lift the PC's soak.
    store = CharacterStore([
        Character.from_dict({
            "name": "Vask", "characteristics": {"Tgh": 45}, "augmetics": ["Augmetischer Arm"],
        })
    ])
    sheet = store.get("Vask")
    target = types.SimpleNamespace(is_npc=False, toughness_bonus=0, armour=2)
    out = combat.resolve_attack(
        _IM, store, target=target, target_sheet=sheet,
        notation="1d10+5", success_level=2, rng=random.Random(7),
    )
    assert out.augmetic_armour == augmetic_armour(_IM, sheet) == 1
    assert out.toughness_bonus == 4  # tens of 45
    assert out.soak == 4 + 2 + 1  # tb + target armour + augmetic armour


# -- soak floors applied at 0 -------------------------------------------------------------

def test_resolve_attack_huge_soak_floors_applied_at_zero() -> None:
    target = types.SimpleNamespace(is_npc=True, toughness_bonus=999, armour=0)
    out = combat.resolve_attack(
        _IM, None, target=target, target_sheet=None,
        notation="1d10+5", success_level=2, rng=random.Random(7),
    )
    assert out.soak == 999
    assert out.damage.applied == 0


# -- resolve_warp_consequences ------------------------------------------------------------

def test_warp_consequences_no_trigger_returns_empty() -> None:
    consq = combat.resolve_warp_consequences(
        _IM, immediate_perils=False, over_threshold=False,
        warp_charge=2, threshold=4, contain_base=30, character="Mortn", rng=random.Random(0),
    )
    assert consq.lines == []
    assert consq.reset_charge is False


def test_warp_consequences_containment_success_holds_energy() -> None:
    # Seed 1: the Challenging containment Test (Disziplin (Psi) 30, +0 modifier → Ziel 30) SUCCEEDS.
    consq = combat.resolve_warp_consequences(
        _IM, immediate_perils=False, over_threshold=True,
        warp_charge=6, threshold=4, contain_base=30, character="Mortn", rng=random.Random(1),
    )
    assert any("Warp-Energie" in ln and "Overt" in ln for ln in consq.lines)
    assert consq.reset_charge is False


def test_warp_consequences_containment_failure_triggers_perils() -> None:
    # Seed 0: the containment Test FAILS → Perils of the Warp erupt and Warp Charge resets.
    consq = combat.resolve_warp_consequences(
        _IM, immediate_perils=False, over_threshold=True,
        warp_charge=6, threshold=4, contain_base=30, character="Mortn", rng=random.Random(0),
    )
    assert any("Perils of the Warp" in ln for ln in consq.lines)
    assert not any("Warp-Energie" in ln for ln in consq.lines)  # no containment-hold line
    assert consq.reset_charge is True


def test_warp_consequences_immediate_perils_skips_containment() -> None:
    # immediate_perils (a Push-Fumble) goes straight to Perils — no containment Test rolled.
    consq = combat.resolve_warp_consequences(
        _IM, immediate_perils=True, over_threshold=False,
        warp_charge=0, threshold=4, contain_base=30, character="Mortn", rng=random.Random(0),
    )
    assert any("Perils of the Warp" in ln for ln in consq.lines)
    assert not any("Warp-Kontrolle" in ln for ln in consq.lines)  # containment was skipped
    assert consq.reset_charge is True
