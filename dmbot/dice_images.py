"""Dice result thumbnails: the rolled value as an ASCII-art d20 PNG, rendered on demand.

Presentation only. The value and the outcome flags come from the rules engine; this module only
turns them into a picture. Nothing here feeds the DM, the world state or the replay journal.

Images are rendered by ``tools/generate_dice.py`` (loaded lazily by path, so a missing Pillow or
font can never stop the bot from starting) and cached at ``data/dice/<palette>/d_<value>.png``
(git-ignored). ``uv run python tools/generate_dice.py`` pre-renders the whole cache.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import threading
from pathlib import Path
from types import ModuleType

from .rules.engine import DiceRoll, TestResult

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DICE_DIR = REPO_ROOT / "data" / "dice"
_RENDERER_PATH = REPO_ROOT / "tools" / "generate_dice.py"

MIN_VALUE, MAX_VALUE = 1, 100
PALETTES = ("red", "gold", "green")

# Embed side-bar colour per palette, close to each palette's bright tone.
EMBED_COLOURS = {"red": 0xB4141A, "gold": 0xE6A01E, "green": 0x4FB25A}

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


def get_dice_image(value: int, palette: str = "red", *, cache_dir: Path | None = None) -> Path:
    """The cached PNG for ``value`` in ``palette``, rendered first if it isn't there yet.

    Blocking (~0.1–1 s on a miss); call it via :func:`get_dice_image_async` from the bot."""
    if image_value(value) is None:
        raise ValueError(f"no dice image for {value} (only {MIN_VALUE}..{MAX_VALUE})")
    if palette not in PALETTES:
        raise ValueError(f"unknown dice palette {palette!r} (known: {', '.join(PALETTES)})")
    folder = (cache_dir or DICE_DIR) / palette
    path = folder / f"d_{value}.png"
    if path.is_file():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    # Render to a private temp name, then swap it in: two rolls of the same value at once must
    # never leave a half-written PNG in the cache.
    tmp = folder / f".d_{value}.{os.getpid()}.{threading.get_ident()}.tmp.png"
    try:
        _load_renderer().render(value, tmp, palette=palette)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


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
