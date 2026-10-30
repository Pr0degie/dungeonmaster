"""Dice throw animation: the screen-space pinball simulation and the GIF frame plan.

Pure Python, no Pillow — the renderer (``tools/generate_dice.py``) turns the plan into pictures.
The whole frame is the box; depth ``z`` only controls the die's size. :func:`simulate` is a tuned
prototype ported verbatim (constants included) — change nothing without asking Tobi.

Cosmetic only: nothing here touches the rules engine's RNG, and nothing it picks feeds the DM,
the world state or the replay journal.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from functools import lru_cache

FRAME = 600          # half frame size in source px (canvas is S=1200)
DIE   = 590          # ~half die size at scale 1


def scale_of(z):
    p = 1.0 / (1.0 + 3.3*z)
    return max(0.18, p)


def simulate(seed: int):
    rng = random.Random(seed)
    x, dy, z = 0.0, 0.0, 0.0           # x, dy in screen px (dy + = down), z depth 0..1
    vx = rng.uniform(600, 900) * rng.choice((-1, 1))
    vy = -rng.uniform(700, 1000)       # thrown upward
    vz = rng.uniform(2.8, 3.6)
    angle, w = 0.0, rng.uniform(500, 900) * rng.choice((-1, 1))
    dt = 1/60
    states, events = [], []
    hits = 0
    for step in range(int(5.6/dt)):
        t = step*dt
        homeward = hits >= 7 or t > 2.4
        G = 1500 if homeward else 600                  # weak gravity while pinballing
        vy += G*dt
        if homeward:
            vz -= 1.3*dt
            vx -= x * 3.0 * dt
        x += vx*dt; dy += vy*dt; z += vz*dt
        z = min(z, 1.0)
        if z <= 0 and hits: z = 0.0; vz = 0.0
        if 0 < hits and not homeward:
            vz *= (1 - 0.5*dt)                         # hover deep
        s = scale_of(max(z, 0.0))
        e = FRAME - DIE*s - 8                          # box half-extent, both axes
        def kick():
            nonlocal w, vx, vy, vz
            w = -w*0.8 + rng.uniform(-220, 220)
            if not homeward:  # noqa: B023 — kick() runs within the same step
                vx += rng.uniform(-260, 260)           # random next target:
                vy += rng.uniform(-260, 260)           # any edge, any corner
                vz += rng.uniform(-0.25, 0.25)
        r = (lambda: rng.uniform(0.90, 0.96)) if not homeward else (lambda: rng.uniform(0.45, 0.58))
        if x < -e: x = -e; vx = -vx*r(); hits += 1; events.append(('L', step)); kick()
        if x >  e: x =  e; vx = -vx*r(); hits += 1; events.append(('R', step)); kick()
        if dy < -e: dy = -e; vy = -vy*r(); hits += 1; events.append(('top', step)); kick()
        if dy >  e:
            dy = e; hits += 1
            if abs(vy) > 160:
                vy = -vy*r(); events.append(('bottom', step)); kick()
            else:
                vy = 0.0
        if step % 8 == 0:
            states.append((x, dy, z, angle))
        if homeward and z < 0.04 and abs(vx) < 70 and abs(vy) < 120 and dy > e - 20:
            states.append((x, dy, z, angle)); break
    return states, events


# --- the seed pool ---------------------------------------------------------------------------

POOL_SIZE = 25
MAX_STATES = 32
_SCAN_LIMIT = 100_000  # a safety stop for the ascending scan; good seeds are far denser than this


def good_seed(seed: int) -> bool:
    """A seed worth showing: it hits all four edges, ends near the front (``z < 0.08``) and near
    the middle (``|x| < 90``), and stays short (at most :data:`MAX_STATES` sim frames)."""
    states, events = simulate(seed)
    sides = {side for side, _ in events}
    if not {"L", "R", "top", "bottom"} <= sides:
        return False
    x, _, z, _ = states[-1]
    return z < 0.08 and abs(x) < 90 and len(states) <= MAX_STATES


@lru_cache(maxsize=1)
def good_seeds(count: int = POOL_SIZE) -> tuple[int, ...]:
    """The first ``count`` good seeds, scanning ascending from 0 — the pre-rendered pool."""
    found: list[int] = []
    seed = 0
    while len(found) < count and seed < _SCAN_LIMIT:
        if good_seed(seed):
            found.append(seed)
        seed += 1
    return tuple(found)


# --- the frame plan --------------------------------------------------------------------------

TEXTURE_SEED = 7      # the static dice images' texture; the final frames match it

# Tuned at the table (2026-10-30), against the spec's opening still + 82 ms: the post already shows
# the target die before the click, so the GIF starts mid-throw, and the flight plays faster.
FLICKER_MS = 60
SLIDE_IN = ((0.6, 130), (0.3, 180), (0.1, 250))
SETTLE_MS = 340
HOLD_MS = 2600


@dataclass(frozen=True)
class Frame:
    """One GIF frame: where the shaded die sits, what it shows, and for how long.

    ``kind``: ``flicker`` frames show a random value in the result palette and depend on neither
    target nor result (the cached pool frames); ``final`` frames show the rolled value; a
    ``blank`` frame (value 0) shows the die without a number."""
    kind: str
    angle: float
    scale: float
    dx: float
    dy: float
    value: int
    palette: str
    prefix: str
    duration_ms: int
    texture_seed: int


def throw_frames(seed: int, result: int, palette: str) -> list[Frame]:
    """The whole GIF for one throw: the pinball (numbers flicker), the slide back to the front,
    the settle on ``result``. It starts mid-throw — the posted target die is the picture before
    it, so the first sim state (the die still at rest) is left out. Same arguments → the same plan
    (the flicker values come from a seed-derived generator, so the pool frames are reproducible)."""
    states, _ = simulate(seed)
    flick = random.Random(seed * 7919 + 1)
    frames: list[Frame] = []
    for i, (x, dy, z, angle) in enumerate(states):
        value = flick.randint(1, 100)  # drawn for every state, so the flicker values never shift
        if i == 0:
            continue
        frames.append(Frame("flicker", angle, scale_of(max(z, 0.0)), x, dy, value, palette, "",
                            FLICKER_MS, TEXTURE_SEED + 1 + i))
    lx, ldy, lz, langle = states[-1]
    for k, (t, ms) in enumerate(SLIDE_IN):
        frames.append(Frame("flicker", langle*t*0.3, 1 - (1 - scale_of(lz))*t, lx*t, ldy*t,
                            flick.randint(1, 100), palette, "", ms, TEXTURE_SEED + 1 + len(states) + k))
    for ms in (SETTLE_MS, HOLD_MS):
        frames.append(Frame("final", 0.0, 1.0, 0.0, 0.0, result, palette, "", ms, TEXTURE_SEED))
    return frames


def gif_duration_ms(frames: list[Frame]) -> int:
    """Total play time of ``frames`` as a GIF stores it (centiseconds, so 82 ms plays as 80 ms)."""
    return sum(f.duration_ms // 10 * 10 for f in frames)


def landed_ms(frames: list[Frame]) -> int:
    """Play time until the die shows its result (the first ``final`` frame appears)."""
    first_final = next(i for i, f in enumerate(frames) if f.kind == "final")
    return gif_duration_ms(frames[:first_final])


def flight_frames(seed: int, palette: str) -> list[Frame]:
    """The flight alone, for the pre-uploaded GIFs (ADR 064): the flicker frames of
    :func:`throw_frames`, the last one with a blank face — the die has slid back to the front and
    the result picture replaces it. No landing, so one GIF per (seed, palette) serves every
    result. Flicker frame ``i`` here is flicker frame ``i`` of :func:`throw_frames` (same cache)."""
    frames = [f for f in throw_frames(seed, 1, palette) if f.kind == "flicker"]
    frames[-1] = replace(frames[-1], kind="blank", value=0)
    return frames
