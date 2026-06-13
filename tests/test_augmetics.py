"""Augmetik / Implantate subsystem (ADR 023) — deterministic unit tests.

Covers the profile catalog + limit helpers, the armour/characteristic summation, the
``resolve_target`` characteristic hook (e.g. Augur-Array +5 Perception lifting a Wahrnehmung
Test), the ``Character`` round-trip, and the soak effect of augmetic armour in the damage engine.
All pure + fixed-seed where dice are involved.
"""

from __future__ import annotations

import random

from dmbot.rules import engine, profile as profile_mod
from dmbot.rules.characters import (
    Character, CharacterStore, augmetic_armour, augmetic_bonus, resolve_target,
)

_IM = profile_mod.load("imperium_maledictum")


def _store(char_dict: dict) -> CharacterStore:
    return CharacterStore([Character.from_dict(char_dict)])


# -- profile catalog ----------------------------------------------------------------------

def test_profile_exposes_augmetics() -> None:
    assert _IM.augmetics_enabled()
    assert "Augur-Array" in _IM.augmetic_names()
    arm = _IM.augmetic("augmetischer arm")  # case-insensitive
    assert arm is not None and arm["name"] == "Augmetischer Arm"
    assert any(e["type"] == "armour" and e["value"] == 1 for e in arm["effects"])


def test_augmetic_limit_is_toughness_bonus() -> None:
    assert _IM.augmetic_limit(45) == 4
    assert _IM.augmetic_limit(52) == 5
    assert _IM.augmetic_limit(None) == 0


def test_unknown_augmetic_is_none() -> None:
    assert _IM.augmetic("Plasma-Herz 9000") is None


# -- summation helpers --------------------------------------------------------------------

def test_augmetic_armour_sums_armour_effects() -> None:
    char = Character.from_dict({"name": "Vask", "augmetics": ["Augmetischer Arm", "Augmetisches Bein"]})
    assert augmetic_armour(_IM, char) == 2  # +1 each
    plain = Character.from_dict({"name": "Plain"})
    assert augmetic_armour(_IM, plain) == 0


def test_augmetic_bonus_matches_characteristic_and_listed_skill() -> None:
    char = Character.from_dict({"name": "Mortn", "augmetics": ["Augur-Array"]})
    assert augmetic_bonus(_IM, char, characteristic="Per") == 5         # the characteristic itself
    assert augmetic_bonus(_IM, char, characteristic="Wahrnehmung") == 5  # the listed governed skill
    assert augmetic_bonus(_IM, char, characteristic="Nahkampf") == 0     # unrelated → no bonus


def test_augmetic_bonus_is_zero_without_augmetics() -> None:
    char = Character.from_dict({"name": "Plain"})
    assert augmetic_bonus(_IM, char, characteristic="Per") == 0


# -- resolve_target hook ------------------------------------------------------------------

def test_resolve_target_adds_augmetic_characteristic_bonus() -> None:
    store = _store({"name": "Mortn", "skills": {"Wahrnehmung": 40}, "augmetics": ["Augur-Array"]})
    rt = resolve_target(_IM, store, skill="Wahrnehmung", target_name="Mortn", difficulty="Routine")
    # base 40 + 5 (Augur-Array) = 45, + 20 (Routine) = 65
    assert rt.base == 45 and rt.target == 65


def test_resolve_target_unaffected_without_augmetics() -> None:
    store = _store({"name": "Seskin", "skills": {"Wahrnehmung": 48}})
    rt = resolve_target(_IM, store, skill="Wahrnehmung", target_name="Seskin", difficulty="Routine")
    assert rt.base == 48 and rt.target == 68


# -- Character round-trip -----------------------------------------------------------------

def test_character_augmetics_round_trip() -> None:
    c = Character.from_dict({"name": "Vask", "augmetics": ["Augmetischer Arm"]})
    assert c.augmetics == ("Augmetischer Arm",)
    blank = Character.from_dict({"name": "X"})
    assert blank.augmetics == ()


# -- soak in the damage engine ------------------------------------------------------------

def test_augmetic_armour_reduces_applied_damage() -> None:
    # Same weapon roll + SL + base soak, but the augmetic adds +1 armour → 1 less wound applied.
    roll = engine.roll_damage("1d10+5", random.Random(4))
    base = engine.resolve_damage(roll, success_level=2, soak=4)
    with_arm = engine.resolve_damage(roll, success_level=2, soak=4 + augmetic_armour(
        _IM, Character.from_dict({"name": "Vask", "augmetics": ["Augmetischer Arm"]})))
    assert with_arm.applied == base.applied - 1
