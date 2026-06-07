"""Rules engine — deterministic dice + roll-under resolution (golden rule #2, ADR 005).

The engine takes an explicit RNG, so these assert exact outcomes: dice parsing, success/failure
boundaries, success-level (tens-difference), criticals/fumbles on doubles, and the auto-success/
auto-fail bands. No Discord, no LLM.
"""

from __future__ import annotations

import random

import pytest

from dmbot.rules import engine
from dmbot.rules.profile import SystemProfile

# A minimal IM-shaped profile so the engine tests don't depend on the data file.
_IM = SystemProfile.from_dict(
    {
        "name": "test",
        "dice": "1d100",
        "resolution": "roll_under",
        "degrees": "tens_difference",
        "crit": "doubles",
        "auto_success_max": 5,
        "auto_fail_min": 96,
    }
)


class _Seq:
    """An RNG stub that returns queued ``randint`` values, so a roll is fully determined."""

    def __init__(self, *values: int) -> None:
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        return self._values.pop(0)


# -- dice parsing ---------------------------------------------------------------------------

def test_roll_parses_count_sides_and_modifier() -> None:
    r = engine.roll("2d10+3", random.Random(0))
    assert len(r.dice) == 2 and all(1 <= d <= 10 for d in r.dice)
    assert r.modifier == 3 and r.total == sum(r.dice) + 3


def test_roll_defaults_count_to_one_and_handles_d5() -> None:
    assert all(1 <= engine.roll("d100", random.Random(i)).total <= 100 for i in range(5))
    assert all(1 <= engine.roll("1d5", random.Random(i)).total <= 5 for i in range(20))


def test_roll_is_deterministic_for_a_seed() -> None:
    assert engine.roll("1d100", random.Random(42)).total == engine.roll("1d100", random.Random(42)).total


def test_roll_constant_and_bad_notation() -> None:
    assert engine.roll("5").total == 5
    with pytest.raises(engine.DiceError):
        engine.roll("nonsense")


# -- roll-under resolution ------------------------------------------------------------------

def test_success_with_positive_sl() -> None:
    r = engine.resolve_test(_IM, 45, _Seq(23))  # 23 <= 45 → success; SL = 4 − 2 = 2
    assert r.success and r.degrees == 2 and not r.critical and not r.fumble and not r.auto


def test_failure_with_zero_sl() -> None:
    r = engine.resolve_test(_IM, 45, _Seq(47))  # 47 > 45 → fail; SL = 4 − 4 = 0
    assert not r.success and r.degrees == 0 and not r.fumble


def test_double_on_success_is_a_critical() -> None:
    r = engine.resolve_test(_IM, 45, _Seq(11))  # success + double → critical; SL = 4 − 1 = 3
    assert r.success and r.critical and not r.fumble and r.degrees == 3


def test_double_on_failure_is_a_fumble() -> None:
    r = engine.resolve_test(_IM, 20, _Seq(33))  # 33 > 20 fail + double → fumble; SL = 2 − 3 = −1
    assert not r.success and r.fumble and not r.critical and r.degrees == -1


def test_auto_success_band_overrides_a_miss() -> None:
    r = engine.resolve_test(_IM, 1, _Seq(3))  # 3 > 1 would fail, but 3 ≤ 5 → forced success
    assert r.success and r.auto


def test_auto_fail_band_overrides_a_hit() -> None:
    r = engine.resolve_test(_IM, 99, _Seq(98))  # 98 ≤ 99 would pass, but 98 ≥ 96 → forced fail
    assert not r.success and r.auto


def test_hundred_is_a_double_and_renders_as_00() -> None:
    r = engine.resolve_test(_IM, 50, _Seq(100))  # 100 > 50 fail, double, auto-fail band
    assert not r.success and r.fumble and r.auto
    assert "00" in engine.describe_result_de(r, skill="Wahrnehmung", character="Tobi")


def test_unknown_resolution_raises() -> None:
    pool = SystemProfile.from_dict({"name": "x", "dice": "5d6", "resolution": "pool"})
    with pytest.raises(NotImplementedError):
        engine.resolve_test(pool, 10, _Seq(3))
