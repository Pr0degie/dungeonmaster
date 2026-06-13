"""``resolve_test`` resolver dispatch — golden rule #2: a genuine error inside a resolver must
propagate, never be swallowed by a silent re-roll that would consume a second d100 and mask the
real bug. ``advantage`` is forwarded by inspecting the resolver's *signature*, not by catching a
``TypeError`` from the call.

No Discord, no LLM — the engine takes an explicit RNG, so these assert exact draw counts.
"""

from __future__ import annotations

import inspect

import pytest

from dmbot.rules import engine
from dmbot.rules.profile import SystemProfile

# A minimal IM-shaped profile; ``resolution`` is overridden per test to pick a registered resolver.
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


class _CountingRng:
    """An RNG stub that returns a fixed value and counts how many times ``randint`` was drawn,
    so a re-roll (a second draw) is observable."""

    def __init__(self, value: int = 23) -> None:
        self.value = value
        self.draws = 0

    def randint(self, a: int, b: int) -> int:
        self.draws += 1
        return self.value


def _with_resolver(name: str, resolver):
    """Register ``resolver`` under ``name`` in RESOLVERS and return a profile that selects it.
    The caller restores RESOLVERS via the ``_restore_resolvers`` fixture."""
    engine.RESOLVERS[name] = resolver
    return SystemProfile.from_dict(
        {"name": "test", "dice": "1d100", "resolution": name, "degrees": "tens_difference"}
    )


@pytest.fixture(autouse=True)
def _restore_resolvers():
    """Snapshot RESOLVERS and the signature cache so a test's temporary resolver can't leak."""
    saved = dict(engine.RESOLVERS)
    engine._accepts_advantage.cache_clear()
    yield
    engine.RESOLVERS.clear()
    engine.RESOLVERS.update(saved)
    engine._accepts_advantage.cache_clear()


# (a) A genuine TypeError raised *inside* a resolver must propagate — not be swallowed and retried,
#     and the rng must be drawn at most once (no second d100 from a hidden re-roll).
def test_internal_typeerror_propagates_and_rng_drawn_once():
    def broken(profile, target, rng=None, *, advantage=0):
        rng.randint(1, 100)            # draw once, like a real resolver
        raise TypeError("genuine bug inside the resolver")

    profile = _with_resolver("broken", broken)
    rng = _CountingRng()
    with pytest.raises(TypeError, match="genuine bug"):
        engine.resolve_test(profile, 50, rng, advantage=1)
    assert rng.draws == 1, "resolver must not be retried — that would consume a second d100"


# (b) A resolver without an ``advantage`` parameter is still called correctly (no keyword passed),
#     and the genuine result comes back even though advantage was requested.
def test_resolver_without_advantage_param_is_called_plain():
    seen = {}

    def no_adv(profile, target, rng=None):  # note: no ``advantage`` kwarg accepted
        seen["target"] = target
        return engine.TestResult(
            roll=23, target=target, success=True, degrees=0,
            critical=False, fumble=False, auto=False, resolution="no_adv",
        )

    profile = _with_resolver("no_adv", no_adv)
    rng = _CountingRng()
    result = engine.resolve_test(profile, 50, rng, advantage=2)  # advantage requested but unsupported
    assert seen["target"] == 50
    assert result.success and result.target == 50


def test_resolver_with_var_kwargs_receives_advantage():
    seen = {}

    def via_kwargs(profile, target, rng=None, **kw):  # accepts advantage via **kwargs
        seen["advantage"] = kw.get("advantage")
        return engine.TestResult(
            roll=23, target=target, success=True, degrees=0,
            critical=False, fumble=False, auto=False, resolution="via_kwargs",
        )

    profile = _with_resolver("via_kwargs", via_kwargs)
    engine.resolve_test(profile, 50, _CountingRng(), advantage=3)
    assert seen["advantage"] == 3


def test_accepts_advantage_signature_detection():
    """The dispatch decision is made from the signature, never from a trial call."""
    assert engine._accepts_advantage(engine.resolve_roll_under) is True

    def named(profile, target, rng=None, *, advantage=0):
        ...

    def plain(profile, target, rng=None):
        ...

    def kwargs(profile, target, rng=None, **kw):
        ...

    assert engine._accepts_advantage(named) is True
    assert engine._accepts_advantage(plain) is False
    assert engine._accepts_advantage(kwargs) is True


# (c) resolve_roll_under still applies advantage exactly as before: a single net Advantage (+1)
#     reverses the d100 face when that helps (lower is better), routed through resolve_test.
def test_roll_under_advantage_still_applied_via_resolve_test():
    # face 72 with Advantage(+1) reverses to 27 and takes the better (lower) → 27 ≤ target 50 = success.
    seq = _SingleValueRng(72)
    result = engine.resolve_test(_IM, 50, seq, advantage=1)
    assert result.roll == 27, "advantage must reverse 72→27 and keep the lower face"
    assert result.success is True

    # Without advantage the face is left untouched (72 > 50 → failure), confirming the path differs.
    plain = engine.resolve_test(_IM, 50, _SingleValueRng(72), advantage=0)
    assert plain.roll == 72 and plain.success is False


class _SingleValueRng:
    """Returns the same face on every draw — enough for roll-under + its reverse compare."""

    def __init__(self, value: int) -> None:
        self.value = value

    def randint(self, a: int, b: int) -> int:
        return self.value


def test_resolve_roll_under_signature_unchanged():
    """Guard the public contract: resolve_test keeps its (profile, target, rng, *, advantage) shape."""
    params = list(inspect.signature(engine.resolve_test).parameters)
    assert params == ["profile", "target", "rng", "advantage"]
