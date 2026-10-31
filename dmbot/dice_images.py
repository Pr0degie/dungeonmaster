"""Dice result thumbnails: the rolled value as an ASCII-art d20 PNG, rendered on demand.

Presentation only. The value and the outcome flags come from the rules engine; this module only
turns them into a picture. Nothing here feeds the DM, the world state or the replay journal.

Images are rendered by ``tools/generate_dice.py`` (loaded lazily by path, so a missing Pillow or
font can never stop the bot from starting) and cached at ``data/dice/<palette>/d_<value>.png``
(git-ignored). ``uv run python tools/generate_dice.py`` pre-renders the whole cache.

A test also gets a **target die** (steel, "≤45", ``data/dice/steel/t_<value>.png``) on its button
post, and — with ``DM_DICE_ANIMATION`` on — a **throw GIF** between click and result
(``data/dice/anim/``, see :func:`get_dice_gif_async`). The throw trajectory is picked with this
module's own cosmetic generator, never the engine's: nothing about the animation reaches the
engine, the world state or the replay journal.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import random
import threading
from pathlib import Path
from types import ModuleType

from .rules.engine import DiceRoll, TestResult

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DICE_DIR = REPO_ROOT / "data" / "dice"
ANIM_DIR = DICE_DIR / "anim"
_RENDERER_PATH = REPO_ROOT / "tools" / "generate_dice.py"

MIN_VALUE, MAX_VALUE = 1, 100
PALETTES = ("red", "gold", "green", "steel")
RESULT_PALETTES = ("red", "gold", "green")  # what a rolled die can be; steel is the target die
TARGET_PALETTE = "steel"
TARGET_PREFIX = "≤"  # Imperium Maledictum is roll-under

# Embed side-bar colour per palette, close to each palette's bright tone.
EMBED_COLOURS = {"red": 0xB4141A, "gold": 0xE6A01E, "green": 0x4FB25A, "steel": 0x7E95BA}

# Picks the throw trajectory. Cosmetic only and deliberately unseeded: it is not the engine's RNG,
# and nothing it chooses may reach the engine, the world state or the replay journal.
_THROW_RNG = random.Random()

_renderer: ModuleType | None = None
_renderer_lock = threading.Lock()


def palette_for(result: TestResult | None) -> str:
    """The palette for an engine result: critical → gold, fumble → green, anything else → red.

    Only reads the flags the engine set from the active profile (``crit`` rule, auto bands,
    ``crit_scope`` via ``scope_doubles``); it decides nothing itself. ``None`` (a roll without a
    sheet value, so no resolution) is red."""
    if result is None:
        return "red"
    if result.critical:
        return "gold"
    if result.fumble:
        return "green"
    return "red"


def image_value(value: int) -> int | None:
    """``value`` if a die image exists for it (1–100), else ``None``."""
    return value if MIN_VALUE <= value <= MAX_VALUE else None


def roll_image_value(roll: DiceRoll) -> int | None:
    """The value to show for a free ``!roll``: the total if it fits a die image, else ``None``
    (``2d10+3`` → the total; ``3d100`` above 100 or a total ≤ 0 → no thumbnail)."""
    return image_value(roll.total)


def _load_renderer() -> ModuleType:
    global _renderer
    with _renderer_lock:
        if _renderer is None:
            spec = importlib.util.spec_from_file_location("_dice_renderer", _RENDERER_PATH)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load the dice renderer from {_RENDERER_PATH}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _renderer = module
        return _renderer


def _cached_die(path: Path, value: int, palette: str, prefix: str = "") -> Path:
    """``path`` if it is cached, else render it there first (atomically)."""
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Render to a private temp name, then swap it in: two rolls of the same value at once must
    # never leave a half-written PNG in the cache.
    tmp = path.parent / f".{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp.png"
    try:
        _load_renderer().render(value, tmp, palette=palette, prefix=prefix)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def get_dice_image(value: int, palette: str = "red", *, cache_dir: Path | None = None) -> Path:
    """The cached PNG for ``value`` in ``palette``, rendered first if it isn't there yet.

    Blocking (~0.1–1 s on a miss); call it via :func:`get_dice_image_async` from the bot."""
    if image_value(value) is None:
        raise ValueError(f"no dice image for {value} (only {MIN_VALUE}..{MAX_VALUE})")
    if palette not in PALETTES:
        raise ValueError(f"unknown dice palette {palette!r} (known: {', '.join(PALETTES)})")
    return _cached_die((cache_dir or DICE_DIR) / palette / f"d_{value}.png", value, palette)


def get_target_image(value: int, *, cache_dir: Path | None = None) -> Path:
    """The cached target die for ``value`` — steel, "≤value" — rendered first if needed."""
    if image_value(value) is None:
        raise ValueError(f"no target die for {value} (only {MIN_VALUE}..{MAX_VALUE})")
    path = (cache_dir or DICE_DIR) / TARGET_PALETTE / f"t_{value}.png"
    return _cached_die(path, value, TARGET_PALETTE, TARGET_PREFIX)


async def get_dice_image_async(value: int | None, palette: str = "red") -> Path | None:
    """The die image path for a posted result, or ``None`` when there is none to show.

    Renders in a worker thread so the event loop never blocks. Fail-open: the picture is
    cosmetic, so any render problem (no Pillow, no font) is logged and the result is posted
    without it."""
    if value is None or image_value(value) is None:
        return None
    try:
        return await asyncio.to_thread(get_dice_image, value, palette)
    except Exception:  # broad on purpose: a broken thumbnail must never lose a dice result
        log.warning("dice image for %s (%s) could not be rendered — posting without it",
                    value, palette, exc_info=True)
        return None


async def get_target_image_async(value: int | None) -> Path | None:
    """The target die for a posted test, or ``None`` (no sheet value, a target outside 1–100, or
    a render problem — fail-open like :func:`get_dice_image_async`)."""
    if value is None or image_value(value) is None:
        return None
    try:
        return await asyncio.to_thread(get_target_image, value)
    except Exception:  # broad on purpose: the target die is cosmetic
        log.warning("target die for %s could not be rendered — posting without it", value, exc_info=True)
        return None


# --- throw animation ---------------------------------------------------------------------------

def throw_seeds(*, cache_dir: Path | None = None) -> tuple[int, ...]:
    """The pre-rendered pool's trajectories (good seeds), cached in ``anim/seeds.json``."""
    return _load_renderer().pool_seeds(cache_dir or ANIM_DIR)


def get_dice_gif(result: int, palette: str, seed: int, *,
                 cache_dir: Path | None = None) -> tuple[Path, float]:
    """The throw GIF for (seed, palette → result) and the seconds until the die has landed in it;
    assembled first if it isn't cached. The target isn't in it (the post shows it before the
    click). Blocking — flicker frames come from the pool, rendered on the spot (a few seconds) the
    first time a seed/palette is needed."""
    if image_value(result) is None:
        raise ValueError(f"no throw landing on {result} (only {MIN_VALUE}..{MAX_VALUE})")
    if palette not in RESULT_PALETTES:
        raise ValueError(f"unknown result palette {palette!r} (known: {', '.join(RESULT_PALETTES)})")
    renderer = _load_renderer()
    throw = renderer.throw_module()
    anim_dir = cache_dir or ANIM_DIR
    path = anim_dir / f"s{seed}_{palette}_r{result}_v{renderer.gif_version()}.gif"
    if not path.is_file():
        renderer.build_throw_gif(seed, result, palette, anim_dir, path)
    return path, throw.landed_ms(throw.throw_frames(seed, result, palette)) / 1000


def get_flight_gif(seed: int, palette: str, *, cache_dir: Path | None = None) -> tuple[Path, float]:
    """The flight-only GIF of (seed, palette) — the kind stored once in Discord (ADR 064) — and its
    play time in seconds; built first if needed (blocking, ~0.4 s from the pool)."""
    if palette not in RESULT_PALETTES:
        raise ValueError(f"unknown result palette {palette!r} (known: {', '.join(RESULT_PALETTES)})")
    renderer = _load_renderer()
    anim_dir = cache_dir or ANIM_DIR
    path = anim_dir / f"flight_v{renderer.gif_version()}_s{seed}_{palette}.gif"
    if not path.is_file():
        renderer.build_flight_gif(seed, palette, anim_dir, path)
    return path, flight_seconds(seed, palette)


def flight_seconds(seed: int, palette: str) -> float:
    """How long the flight-only GIF of (seed, palette) plays."""
    throw = _load_renderer().throw_module()
    return throw.gif_duration_ms(throw.flight_frames(seed, palette)) / 1000


def _pick_seed() -> int:
    return _THROW_RNG.choice(throw_seeds())  # cosmetic choice — see _THROW_RNG


def prepare_throw(*, cache_dir: Path | None = None) -> int:
    """Pick the throw for a posted test and render what doesn't depend on the result yet (the red
    flicker frames — nothing once the pool is rendered). Returns the seed for
    :func:`get_dice_gif_async` on the click, which then only renders the landing (~0.5 s)."""
    seed = _pick_seed()
    _load_renderer().prepare_throw(seed, cache_dir or ANIM_DIR)
    return seed


async def prepare_throw_async() -> int | None:
    """:func:`prepare_throw` in a worker thread; ``None`` if it failed (fail-open: the click then
    picks and renders on its own)."""
    try:
        return await asyncio.to_thread(prepare_throw)
    except Exception:  # broad on purpose: cosmetic
        log.warning("dice throw could not be prepared", exc_info=True)
        return None


def _throw(result: int, palette: str, seed: int | None = None) -> tuple[Path, float]:
    return get_dice_gif(result, palette, _pick_seed() if seed is None else seed)


async def get_dice_gif_async(target: int | None, result: int | None, palette: str,
                             seed: int | None = None) -> tuple[Path, float] | None:
    """The throw animation for a resolved test: ``(gif path, seconds until it has landed)``, or
    ``None`` when there is none to show (no target — a test without one isn't animated — or a
    value outside 1–100) or it failed. ``seed`` = the throw picked by
    :func:`prepare_throw_async` when the test was posted (else one is picked now).

    Runs in a worker thread. Fail-open: any problem is logged and the caller shows the static
    result instead — a broken animation must never lose a dice result."""
    if target is None or result is None or image_value(target) is None or image_value(result) is None:
        return None
    try:
        return await asyncio.to_thread(_throw, result, palette, seed)
    except Exception:  # broad on purpose: the animation is cosmetic
        log.warning("dice throw → %s (%s) could not be built — showing the result directly",
                    result, palette, exc_info=True)
        return None
