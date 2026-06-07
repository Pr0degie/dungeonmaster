"""Generic dice + resolution engine (ADR 005) — the deterministic heart of the project.

Golden rule #2: dice (RNG) **and** their resolution (success, degrees, crit, damage) are
computed here, never by the LLM. The engine is system-agnostic: it takes a numeric target
and a :class:`~dmbot.rules.profile.SystemProfile` and applies the profile's resolution kind.
Imperium Maledictum (1d100 roll-under, SL = tens-difference) is the first profile; other
systems are other profiles plugged into ``RESOLVERS``.

Everything is pure and takes an explicit ``rng: random.Random`` (default a module-level
``Random``), so tests seed it and assert exact outcomes. The cog resolves the *target*
(skill value + difficulty modifier) before calling in — the engine never reads characters.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .profile import SystemProfile

_DICE_RE = re.compile(r"^\s*(\d*)\s*[dD]\s*(\d+)\s*([+-]\s*\d+)?\s*$")
_INT_RE = re.compile(r"^\s*([+-]?\d+)\s*$")

_default_rng = random.Random()


class DiceError(ValueError):
    """Unparseable dice notation."""


@dataclass(frozen=True, slots=True)
class DiceRoll:
    """The outcome of a dice expression like ``2d10+3``."""

    total: int
    dice: tuple[int, ...]
    modifier: int
    notation: str


def roll(notation: str, rng: random.Random | None = None) -> DiceRoll:
    """Roll a dice expression: ``XdY``, ``dY``, with an optional ``+N``/``-N`` modifier, or a
    bare integer constant. ``1d5`` is a flat 1–5 die (distribution-equal to ceil(d10/2))."""
    rng = rng or _default_rng
    m = _DICE_RE.match(notation)
    if m:
        count = int(m.group(1)) if m.group(1) else 1
        sides = int(m.group(2))
        modifier = int(m.group(3).replace(" ", "")) if m.group(3) else 0
        if count < 1 or sides < 1:
            raise DiceError(f"invalid dice notation: {notation!r}")
        dice = tuple(rng.randint(1, sides) for _ in range(count))
        return DiceRoll(total=sum(dice) + modifier, dice=dice, modifier=modifier, notation=notation)
    m = _INT_RE.match(notation)
    if m:  # a constant (e.g. damage "+2" or a fixed value)
        value = int(m.group(1))
        return DiceRoll(total=value, dice=(), modifier=value, notation=notation)
    raise DiceError(f"unparseable dice notation: {notation!r}")


def roll_damage(notation: str, rng: random.Random | None = None) -> DiceRoll:
    """Roll a damage expression (same parser as :func:`roll`; named for call-site clarity)."""
    return roll(notation, rng)


@dataclass(frozen=True, slots=True)
class TestResult:
    """The resolved outcome of a skill test under a profile."""

    roll: int           # the d100 face, 1..100 (100 is the percentile "00")
    target: int         # the effective target (skill value ± difficulty)
    success: bool
    degrees: int        # success levels (SL): + on success, − on failure (tens-difference)
    critical: bool      # a successful double (11, 22, … 00) — a critical success
    fumble: bool        # a failed double — a fumble
    auto: bool          # decided by the auto-success/auto-fail band, overriding the comparison
    resolution: str     # the profile resolution kind that produced this


def _tens(n: int) -> int:
    """Tens digit for SL: 1..99 → 0..9, 100 → 10 (percentile "00")."""
    return n // 10


def _is_double(face: int) -> bool:
    """d100 doubles: 11, 22, … 99, and 100 (the "00" double)."""
    return face == 100 or (1 <= face <= 99 and face % 11 == 0)


def resolve_roll_under(profile: SystemProfile, target: int, rng: random.Random | None = None) -> TestResult:
    """1d100 roll-under (IM): success if roll ≤ target; SL = tens(target) − tens(roll);
    a double on a success is a critical, on a failure a fumble; the 01–05 / 96–00 bands
    force success/failure regardless of the target."""
    rng = rng or _default_rng
    face = rng.randint(1, 100)
    success = face <= target
    auto = False
    if profile.auto_success_max and face <= profile.auto_success_max:
        success, auto = True, True
    elif profile.auto_fail_min and face >= profile.auto_fail_min:
        success, auto = False, True
    degrees = _tens(target) - _tens(face) if profile.degrees == "tens_difference" else 0
    double = profile.crit == "doubles" and _is_double(face)
    return TestResult(
        roll=face, target=target, success=success, degrees=degrees,
        critical=double and success, fumble=double and not success,
        auto=auto, resolution="roll_under",
    )


# Resolution registry — other systems (roll-over vs DC, pools, sum_vs_target) plug in here.
RESOLVERS = {
    "roll_under": resolve_roll_under,
}


def resolve_test(profile: SystemProfile, target: int, rng: random.Random | None = None) -> TestResult:
    """Roll and resolve a test under ``profile`` against the already-resolved ``target``."""
    resolver = RESOLVERS.get(profile.resolution)
    if resolver is None:
        raise NotImplementedError(
            f"resolution {profile.resolution!r} is not implemented yet "
            f"(known: {', '.join(sorted(RESOLVERS))})"
        )
    return resolver(profile, target, rng)


def _face_str(face: int) -> str:
    """Show the d100 face the table way: 100 as '00'."""
    return "00" if face == 100 else f"{face:02d}"


def describe_result_de(
    result: TestResult, *, skill: str, character: str | None = None, difficulty: str | None = None
) -> str:
    """A German one-line summary, in the GM-rolls-for-the-player style the table asked for
    (open item K): "🎲 Tobi auf Wahrnehmung (Ziel 35): 23 — Erfolg, 1 EG." Feeds back into the
    DM context so the model narrates the consequence."""
    who = character or "Wurf"
    diff = f", {difficulty}" if difficulty else ""
    head = f"🎲 {who} auf {skill}{diff} (Ziel {result.target}): {_face_str(result.roll)}"
    if result.critical:
        verdict = f"kritischer Erfolg, {result.degrees} EG"
    elif result.fumble:
        verdict = f"Patzer, {abs(result.degrees)} EG Fehlschlag"
    elif result.success:
        verdict = f"Erfolg, {result.degrees} EG"
    else:
        verdict = f"Fehlschlag, {abs(result.degrees)} EG"
    if result.auto:
        verdict += " (automatisch)"
    return f"{head} — {verdict}."
