"""System profile loader (ADR 005) — the real IM profile loads + the difficulty ladder maps."""

from __future__ import annotations

import pytest

from dmbot.rules import profile as profile_mod
from dmbot.rules.profile import ProfileError, SystemProfile


def test_imperium_maledictum_profile_loads() -> None:
    p = profile_mod.load("imperium_maledictum")
    assert p.name == "imperium_maledictum"
    assert p.dice == "1d100" and p.resolution == "roll_under"
    assert p.degrees == "tens_difference"
    assert p.auto_success_max == 5 and p.auto_fail_min == 96


def test_difficulty_ladder_matches_the_rulebook() -> None:
    # Values verified against the IM Core Rulebook Difficulty Table (p.188).
    p = profile_mod.load("imperium_maledictum")
    assert p.difficulty_modifier("Sehr leicht") == 60
    assert p.difficulty_modifier("Routine") == 20
    assert p.difficulty_modifier("Schwer") == -20
    assert p.difficulty_modifier("Sehr schwer") == -30
    assert p.difficulty_modifier(None) == 0                # default (Herausfordernd / Challenging +0)


def test_difficulty_lookup_case_and_aliases() -> None:
    p = profile_mod.load("imperium_maledictum")
    assert p.difficulty_modifier("schwer") == -20          # case-insensitive
    assert p.difficulty_modifier("hart") == -20            # German alias → "Schwer"
    assert p.difficulty_modifier("hard") == -20            # English (rulebook) alias → "Schwer"
    assert p.difficulty_modifier("easy") == 40             # English alias → "Leicht"
    assert p.difficulty_modifier("Banane") is None         # unknown word


def test_canonical_difficulty_resolves_aliases() -> None:
    p = profile_mod.load("imperium_maledictum")
    assert p.canonical_difficulty("hart") == "Schwer"
    assert p.canonical_difficulty("normal") == "Herausfordernd"
    assert p.canonical_difficulty("very hard") == "Sehr schwer"


def test_missing_required_key_raises() -> None:
    with pytest.raises(ProfileError):
        SystemProfile.from_dict({"name": "x", "dice": "1d100"})  # no resolution


def test_non_integer_ladder_raises() -> None:
    with pytest.raises(ProfileError):
        SystemProfile.from_dict(
            {"name": "x", "dice": "1d100", "resolution": "roll_under",
             "difficulty_ladder": {"Leicht": "viel"}}
        )


def test_load_unknown_profile_raises() -> None:
    with pytest.raises(ProfileError):
        profile_mod.load("does_not_exist")
