"""Damage of a manifested psychic power (ADR 022 amendment) — deterministic unit tests.

A damaging power's numbers live in the profile as a structured ``damage`` block on the power
(never parsed from the German effect text); ``combat.resolve_power_damage`` turns that block, the
psyker's sheet and the Manifest SL into wounds against one target, honouring "ignores armour".
Pure + fixed-seed (golden rule #2: dice = code), so every number is asserted exactly.
"""

from __future__ import annotations

import random
import types

from dmbot.rules import combat, engine, profile as profile_mod
from dmbot.rules.characters import Character, CharacterStore, augmetic_armour

_IM = profile_mod.load("imperium_maledictum")

# Willpower 45 → Willpower Bonus 4; Toughness 38 → Toughness Bonus 3.
_STORE = CharacterStore([
    Character.from_dict({"name": "Fridolin", "characteristics": {"Wil": 45, "Tgh": 38}}),
    Character.from_dict({
        "name": "Vask", "characteristics": {"Tgh": 45}, "augmetics": ["Augmetischer Arm"],
    }),
])
_PSYKER = _STORE.get("Fridolin")
# The improvised NPC of the 2026-11-27 run, with armour on top to show what Smite ignores.
_WAECHTER = types.SimpleNamespace(is_npc=True, toughness_bonus=3, armour=2)


def _smite(success_level: int, target=_WAECHTER, target_sheet=None):
    return combat.resolve_power_damage(
        _IM, _STORE, power="Smite", psyker_sheet=_PSYKER,
        target=target, target_sheet=target_sheet,
        success_level=success_level, rng=random.Random(7),
    )


# -- profile accessor ---------------------------------------------------------------------

def test_power_damage_reads_the_structured_block() -> None:
    dmg = _IM.power_damage("smite")
    assert dmg == {
        "base": "2", "bonus_characteristic": "Wil", "bonus_mode": "tens", "add_sl": True,
        "ignores": ("armour",), "targets": "one",
    }


def test_power_damage_none_for_non_damaging_or_unknown_power() -> None:
    assert _IM.power_damage("Jinx") is None
    assert _IM.power_damage("does-not-exist") is None
    assert _IM.power_damage(None) is None


def test_only_powers_that_deal_damage_on_manifest_carry_the_block() -> None:
    damaging = {name for name in _IM.power_names() if _IM.power_damage(name)}
    assert damaging == {"Smite", "Nova", "Bio-Lightning", "Force Bolt"}
    assert _IM.power_damage("Nova")["targets"] == "area"
    assert _IM.power_damage("Bio-Lightning")["targets"] == "area"
    assert _IM.power_damage("Force Bolt")["ignores"] == ()


# -- Smite: 2 + Willpower Bonus + SL, ignores armour ----------------------------------------

def test_smite_at_sl_0_ignores_armour_but_counts_toughness_bonus() -> None:
    out = _smite(0)
    assert out is not None and out.power == "Smite"
    assert out.bonus == 4                                   # Willpower Bonus of Wil 45
    assert out.damage.weapon_roll.total == 2 + 4
    assert out.toughness_bonus == 3 and out.armour == 0 and out.augmetic_armour == 0
    assert out.soak == 3
    assert out.damage.applied == 2 + 4 + 0 - 3
    assert out.ignored == ("armour",) and out.targets == "one"


def test_smite_at_sl_3_adds_the_success_levels() -> None:
    out = _smite(3)
    assert out.damage.success_level == 3
    assert out.damage.applied == 2 + 4 + 3 - 3


def test_smite_ignores_a_pcs_augmetic_armour_too() -> None:
    vask = _STORE.get("Vask")
    assert augmetic_armour(_IM, vask) == 1
    target = types.SimpleNamespace(is_npc=False, toughness_bonus=0, armour=2)
    out = _smite(1, target=target, target_sheet=vask)
    assert out.toughness_bonus == 4 and out.armour == 0 and out.augmetic_armour == 0
    assert out.damage.applied == 2 + 4 + 1 - 4


def test_power_that_respects_armour_soaks_like_an_attack() -> None:
    out = combat.resolve_power_damage(
        _IM, _STORE, power="Force Bolt", psyker_sheet=_PSYKER,
        target=_WAECHTER, target_sheet=None, success_level=1, rng=random.Random(7),
    )
    assert out.armour == 2 and out.toughness_bonus == 3 and out.soak == 5
    assert out.damage.applied == 6 + 4 + 1 - 5


def test_negative_soak_result_floors_at_zero() -> None:
    tough = types.SimpleNamespace(is_npc=True, toughness_bonus=99, armour=0)
    assert _smite(0, target=tough).damage.applied == 0


def test_psyker_without_sheet_adds_no_bonus() -> None:
    out = combat.resolve_power_damage(
        _IM, _STORE, power="Smite", psyker_sheet=None,
        target=_WAECHTER, target_sheet=None, success_level=0, rng=random.Random(7),
    )
    assert out.bonus == 0 and out.damage.weapon_roll.total == 2
    assert out.damage.applied == 0                          # 2 − 3 Toughness Bonus, floored


# -- nothing to resolve -------------------------------------------------------------------

def test_non_damaging_power_returns_none() -> None:
    assert combat.resolve_power_damage(
        _IM, _STORE, power="Jinx", psyker_sheet=_PSYKER,
        target=_WAECHTER, target_sheet=None, success_level=2, rng=random.Random(7),
    ) is None


def test_no_profile_or_unknown_power_returns_none() -> None:
    for prof, power in ((None, "Smite"), (_IM, "does-not-exist")):
        assert combat.resolve_power_damage(
            prof, _STORE, power=power, psyker_sheet=_PSYKER,
            target=_WAECHTER, target_sheet=None, success_level=2, rng=random.Random(7),
        ) is None


# -- system-agnostic shape: dice in the base, everything ignored -----------------------------

def test_dice_base_rolls_through_the_injected_rng_and_can_ignore_all_soak() -> None:
    prof = profile_mod.SystemProfile.from_dict({
        "name": "other", "dice": "1d100", "resolution": "roll_under",
        "psyker": {"powers": {"Leech": {"damage": {
            "base": "1d10", "bonus": {"characteristic": "Wil", "mode": "value"},
            "add_sl": False, "ignores": ["armour", "toughness_bonus"],
        }}}},
    })
    expected = engine.roll("1d10", random.Random(11)).total + 45   # mode "value": the full Wil
    out = combat.resolve_power_damage(
        prof, _STORE, power="leech", psyker_sheet=_PSYKER,
        target=_WAECHTER, target_sheet=None, success_level=4, rng=random.Random(11),
    )
    assert out.power == "Leech" and out.targets == "one"
    assert out.damage.weapon_roll.total == expected
    assert out.damage.success_level == 0                    # add_sl false → SL not added
    assert out.soak == 0 and out.damage.applied == expected
