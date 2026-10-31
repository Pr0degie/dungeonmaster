"""Render an ASCII-art d20 PNG for a value 1–100 (dice result thumbnails + the throw animation).

A hexagonal d20 silhouette is drawn in greyscale, the value goes in the centre triangle, and the
picture is then re-drawn as coloured ``@``-texture text on a dark background. Palettes: ``red``
(default), ``gold`` (critical success), ``green`` (fumble) and ``steel`` (the target die, "≤45").

The pipeline is three composable stages — :func:`shaded_die` (the greyscale die), :func:`transform`
(rotate/scale/move it) and :func:`ascii_pass` (blur + ASCII colouring). The throw animation moves
the *shaded* die and ASCII-fies afterwards, so the character grid stays axis-aligned.

The bot renders on demand through :mod:`dmbot.dice_images` (cache ``data/dice/``). Run this file
directly to pre-render the cache, e.g. on a new machine:

    uv run python tools/generate_dice.py                 # all palettes, 1–100 (+ steel targets)
    uv run python tools/generate_dice.py --palette gold --values 1-20
    uv run python tools/generate_dice.py --throw-pool          # animation frame pool (slow)
    uv run python tools/generate_dice.py --preview-throw 528   # one complete GIF to look at
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
import sys
import threading
import time
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import ModuleType

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 1200
CX, CY = S/2, S/2
R = S*0.46
R2 = R*0.55

MAX_VALUE = 100

_WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

# Tried in order: DejaVu (Linux, the original look), then the Windows fonts the bot box has.
BOLD_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    _WIN_FONTS / "arialbd.ttf",
)
MONO_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    _WIN_FONTS / "consolab.ttf",
    _WIN_FONTS / "consola.ttf",
)

PALETTES = {
    "red":   lambda v: (min(255, int(150 + v*0.45)), int(6 + v*0.07),  int(8 + v*0.06)),
    "gold":  lambda v: (min(255, int(170 + v*0.35)), min(255, int(110 + v*0.40)), int(15 + v*0.10)),
    "green": lambda v: (int(55 + v*0.22), min(255, int(120 + v*0.42)), int(70 + v*0.24)),
    "steel": lambda v: (int(70 + v*0.28), int(85 + v*0.32), int(110 + v*0.38)),
}
RESULT_PALETTES = ("red", "gold", "green")
PNG_SIZE = 600     # static dice pictures (2026-10-31: was 1200 px, ~290 KB; now ~42 KB)
PNG_COLOURS = 64
TARGET_PALETTE = "steel"
TARGET_PREFIX = "≤"  # Imperium Maledictum is roll-under

# Number size by glyph count (prefix included): smaller as it gets wider, to fit the triangle.
NUMBER_SIZES = {1: 0.14, 2: 0.125, 3: 0.09, 4: 0.075}
# The target die ("≤45") has one glyph more in the same triangle: it sits lower, where the point-up
# triangle is wider, so it can be bigger. PREFIXED_Y = its optical centre in R2 from CY (plain
# numbers: -0.127, slightly above the centre).
PREFIXED_SIZES = {2: 0.22, 3: 0.175, 4: 0.135}
PREFIXED_Y = 0.02

# Numbers on the other nine faces, like a real d20 seen from above (2026-10-31, Tobi: variant B).
# Each reads outward from the die's centre; the three faces touching the centre triangle get the
# bigger size. Fixed per shown value (never the value itself), so a picture is stable and cacheable.
FACE_SIZE_NEAR = 0.095
FACE_SIZE_FAR = 0.08
FACE_CLEAR = 0.72  # share of a face's inradius cleared of texture blotches behind its number


def resolve_font(candidates: tuple[Path, ...], role: str) -> str:
    """The first existing font file of ``candidates``; a clear error naming them all otherwise."""
    for path in candidates:
        if path.is_file():
            return str(path)
    tried = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"no {role} font found for the dice renderer (tried: {tried})")


@cache
def _font(role: str, size: int) -> ImageFont.FreeTypeFont:
    if role == "bold":
        return ImageFont.truetype(resolve_font(BOLD_FONT_CANDIDATES, "number (bold)"), size)
    return ImageFont.truetype(resolve_font(MONO_FONT_CANDIDATES, "mono (ASCII)"), size)


def shaded_die(number: int | None, rng: random.Random, prefix: str = "") -> Image.Image:
    """The greyscale shaded d20 with ``prefix + number`` in the centre triangle — everything
    before the blur. ``rng`` drives the face texture; the same seed gives the same die.
    ``number=None`` (and no prefix) leaves the centre triangle blank."""
    src = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(src)

    hexpts = []
    for i in range(6):
        ang = math.radians(90 + i*60)
        hexpts.append((CX + R*math.cos(ang), CY - R*math.sin(ang)))
    T, UL, LL, B, LR, UR = hexpts

    a_  = (CX, CY - R2)
    bl_ = (CX - R2*math.cos(math.radians(30)), CY + R2*math.sin(math.radians(30)))
    br_ = (CX + R2*math.cos(math.radians(30)), CY + R2*math.sin(math.radians(30)))

    centre_poly = [a_, bl_, br_]
    faces = [
        ([T, UL, a_],   215), ([T, a_, UR],   230),
        ([UL, a_, bl_], 200), ([UR, a_, br_], 205),
        (centre_poly,   250),
        ([UL, LL, bl_], 195), ([UR, LR, br_], 200),
        ([LL, bl_, B],  185), ([LR, br_, B],  190),
        ([bl_, br_, B], 210),
    ]
    for poly, val in faces:
        d.polygon(poly, fill=val)

    for poly, val in faces:
        if poly is centre_poly:
            continue
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        for _ in range(6):
            bx = rng.uniform(min(xs), max(xs))
            by = rng.uniform(min(ys), max(ys))
            br = rng.uniform(20, 55)
            d.ellipse([bx-br, by-br, bx+br, by+br], fill=rng.choice([120, 140, 160]))
    d.polygon(centre_poly, fill=250)

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(hexpts, fill=255)
    src = Image.composite(src, Image.new("L", (S, S), 0), mask)

    ed = ImageDraw.Draw(src)
    edges = [(T,UL),(UL,LL),(LL,B),(B,LR),(LR,UR),(UR,T),
             (T,a_),(a_,UL),(a_,UR),(a_,bl_),(a_,br_),(bl_,br_),
             (bl_,UL),(br_,UR),(bl_,LL),(br_,LR),(bl_,B),(br_,B)]
    for p, q in edges:
        ed.line([p, q], fill=25, width=16)

    near = {id(faces[2][0]), id(faces[3][0]), id(faces[9][0])}  # the faces touching the centre
    others = [(poly, val) for poly, val in faces if poly is not centre_poly]
    for (poly, val), face_num in zip(others, face_numbers(number)):
        _face_number(src, poly, val, face_num, FACE_SIZE_NEAR if id(poly) in near else FACE_SIZE_FAR)

    # adaptive font size: smaller + centred in triangle
    num = prefix if number is None else f"{prefix}{number}"
    if not num:
        return src
    size = (PREFIXED_SIZES if prefix else NUMBER_SIZES)[len(num)]
    fnt = _font("bold", int(S*size))
    bb = ed.textbbox((0,0), num, font=fnt, stroke_width=5)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    # optical centre of point-up triangle: slightly below centroid (cy)
    ty = CY + R2*PREFIXED_Y if prefix else CY - R2*0.127
    ed.text((CX - tw/2 - bb[0], ty - th/2 - bb[1]), num, font=fnt,
            fill=12, stroke_width=5, stroke_fill=12)
    return src


def face_numbers(number: int | None) -> list[int]:
    """The nine numbers on the faces around the centre: fixed per shown value, never the value."""
    rng = random.Random(1_000_003 * (number or 0) + 17)
    return rng.sample([n for n in range(1, MAX_VALUE + 1) if n != number], 9)


def _face_number(src: Image.Image, poly, base: int, value: int, size: float) -> None:
    """Draw ``value`` on one side face: clear its centre of blotches, then the number, turned so it
    reads outward from the die's centre (the bottom face's stands on its head, as on a real d20)."""
    (ax, ay), (bx, by), (cx_, cy_) = poly
    fx, fy = (ax + bx + cx_)/3, (ay + by + cy_)/3
    sides = [math.dist(poly[i], poly[(i + 1) % 3]) for i in range(3)]
    area = abs((bx - ax)*(cy_ - ay) - (cx_ - ax)*(by - ay)) / 2
    clear = FACE_CLEAR * 2*area / sum(sides)
    ImageDraw.Draw(src).ellipse([fx - clear, fy - clear, fx + clear, fy + clear], fill=base)
    angle = math.degrees(math.atan2(-(fx - CX), -(fy - CY)))
    fnt = _font("bold", int(S*size))
    box = S // 3
    layer = Image.new("L", (box, box), 0)
    ld = ImageDraw.Draw(layer)
    text = str(value)
    bb = ld.textbbox((0, 0), text, font=fnt, stroke_width=4)
    ld.text((box/2 - (bb[2]-bb[0])/2 - bb[0], box/2 - (bb[3]-bb[1])/2 - bb[1]), text, font=fnt,
            fill=255, stroke_width=4, stroke_fill=255)
    layer = layer.rotate(angle, resample=Image.BICUBIC)
    src.paste(Image.new("L", layer.size, 12), (round(fx - box/2), round(fy - box/2)), layer)


def ascii_pass(src: Image.Image, palette: str) -> Image.Image:
    """Blur the greyscale ``src`` and re-draw it as coloured ASCII texture (120 columns)."""
    colorize = PALETTES[palette]
    src = src.filter(ImageFilter.GaussianBlur(1.2))

    cols = 120
    cell_w, cell_h = 10, 16
    rows = int(cols * cell_w / cell_h)
    small = src.resize((cols, rows), Image.LANCZOS)

    ramp = " .,:;?*#S@@@"
    out = Image.new("RGB", (cols*cell_w, rows*cell_h), (28, 14, 38))
    od = ImageDraw.Draw(out)
    cfont = _font("mono", 15)

    px = small.load()
    for ry in range(rows):
        for rx in range(cols):
            v = px[rx, ry]
            if v < 12:
                continue
            ch = ramp[min(len(ramp)-1, int(v/255*len(ramp)))]
            if ch == ' ':
                continue
            od.text((rx*cell_w, ry*cell_h), ch, font=cfont, fill=colorize(v))
    return out


def transform(src: Image.Image, angle: float, scale: float, dx: float, dy: float) -> Image.Image:
    """``src`` rotated by ``angle`` degrees about the centre, scaled, and pasted onto a black S×S
    canvas moved ``(dx, dy)`` px from the centre (whatever leaves the canvas is cut off)."""
    rotated = src.rotate(angle, resample=Image.BICUBIC, center=(CX, CY), fillcolor=0)
    size = max(1, int(S*scale))
    scaled = rotated if size == S else rotated.resize((size, size), Image.LANCZOS)
    canvas = Image.new("L", (S, S), 0)
    canvas.paste(scaled, (round(CX - size/2 + dx), round(CY - size/2 + dy)))
    return canvas


def render(number: int, path: str | os.PathLike, seed: int = 7, palette: str = "red",
           prefix: str = "") -> None:
    if not 1 <= number <= MAX_VALUE:
        raise ValueError(f"dice value must be 1..{MAX_VALUE}, got {number}")
    # A private RNG, not random.seed(): the bot renders in a worker thread and must not reseed the
    # process-wide generator. Same seed → the same sequence, so the texture is unchanged.
    picture = ascii_pass(shaded_die(number, random.Random(seed), prefix), palette)
    # Discord shows it at ~400 px: 600 px and 64 colours look the same and are ~42 instead of ~290 KB.
    small = picture.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS)
    small.quantize(colors=PNG_COLOURS, dither=Image.Dither.NONE).save(path, optimize=True)


# --- throw animation -------------------------------------------------------------------------

THUMB = 360  # GIF frame size in px
GIF_COLOURS = 16  # per frame — the ASCII dice have few tones (16: −25 % vs 32, looks the same)
FRAME_SET_VERSION = 4  # bump when the frame plan or the die's look changes (stale pool frames)

_throw_module: ModuleType | None = None
_throw_lock = threading.Lock()


def throw_module() -> ModuleType:
    """``tools/dice_throw.py`` (simulation + frame plan), loaded by path: the bot loads this file
    by path too, so ``tools/`` is not importable as a package."""
    global _throw_module
    with _throw_lock:
        if _throw_module is None:
            name = "_dice_throw"
            spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("dice_throw.py"))
            if spec is None or spec.loader is None:
                raise ImportError("cannot load tools/dice_throw.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module  # the dataclass machinery looks its module up by name
            spec.loader.exec_module(module)
            _throw_module = module
        return _throw_module


def pool_seeds(anim_dir: Path) -> tuple[int, ...]:
    """The pool's good seeds. The ascending scan takes a few seconds (good seeds are rare), so its
    result is kept in ``<anim_dir>/seeds.json`` after the first run."""
    throw = throw_module()
    path = Path(anim_dir) / "seeds.json"
    try:
        seeds = tuple(int(s) for s in json.loads(path.read_text(encoding="utf-8")))
        if len(seeds) == throw.POOL_SIZE:
            return seeds
    except (OSError, ValueError, TypeError):
        pass
    seeds = throw.good_seeds()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".seeds.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(json.dumps(list(seeds)), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return seeds


def render_frame(frame) -> Image.Image:
    """One animation frame (a ``dice_throw.Frame``) as a THUMB×THUMB RGB picture."""
    die = shaded_die(frame.value or None, random.Random(frame.texture_seed), frame.prefix)
    moved = transform(die, frame.angle, frame.scale, frame.dx, frame.dy)
    return ascii_pass(moved, frame.palette).resize((THUMB, THUMB), Image.LANCZOS)


def gif_version() -> str:
    """Names the built GIFs: the frame plan's version plus the colour count, so a change to either
    gives new file names (and the stored copies in Discord get replaced, ADR 064)."""
    return f"{FRAME_SET_VERSION}c{GIF_COLOURS}"


def frame_set_dir(anim_dir: Path, seed: int, palette: str) -> Path:
    """Where the cached flicker frames of one (seed, palette) live."""
    return Path(anim_dir) / "frames" / f"v{FRAME_SET_VERSION}" / f"s{seed}_{palette}"


def _atomic_save(image: Image.Image, path: Path, **kwargs) -> None:
    """Save via a private temp name, then swap in: a concurrent reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp{path.suffix}")
    try:
        image.save(tmp, **kwargs)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_frame_set(seed: int, palette: str, anim_dir: Path, *, force: bool = False) -> int:
    """Render the flicker frames of (seed, palette) that aren't cached yet; returns how many were
    rendered. They don't depend on the result, so the plan's dummy value doesn't matter."""
    plan = throw_module().throw_frames(seed, 1, palette)
    folder = frame_set_dir(anim_dir, seed, palette)
    rendered = 0
    for index, frame in enumerate(plan):
        if frame.kind != "flicker":
            continue
        path = folder / f"f_{index:02d}.png"
        if path.is_file() and not force:
            continue
        _atomic_save(render_frame(frame), path)
        rendered += 1
    return rendered


def prepare_throw(seed: int, anim_dir: Path) -> None:
    """Render what a throw needs before its result is known — the red flicker frames (the usual
    palette; a no-op once the pool is rendered). The click then only renders the landing."""
    ensure_frame_set(seed, "red", anim_dir)


def build_throw_gif(seed: int, result: int, palette: str, anim_dir: Path, out: Path) -> int:
    """Assemble the throw GIF of one roll at ``out``: the cached flicker frames (rendered first if
    missing), then the settle on ``result``. Returns its play time in ms."""
    if not 1 <= result <= MAX_VALUE:
        raise ValueError(f"dice value must be 1..{MAX_VALUE}, got {result}")
    if palette not in RESULT_PALETTES:
        raise ValueError(f"unknown result palette {palette!r} (known: {', '.join(RESULT_PALETTES)})")
    throw = throw_module()
    plan = throw.throw_frames(seed, result, palette)
    ensure_frame_set(seed, palette, anim_dir)
    folder = frame_set_dir(anim_dir, seed, palette)
    images: list[Image.Image] = []
    rendered: dict = {}  # settle + hold are the same picture — render it once
    for index, frame in enumerate(plan):
        if frame.kind == "flicker":
            with Image.open(folder / f"f_{index:02d}.png") as cached:
                images.append(cached.convert("RGB"))
            continue
        picture = replace(frame, duration_ms=0)  # same picture, whatever its duration
        if picture not in rendered:
            rendered[picture] = render_frame(frame)
        images.append(rendered[picture])
    frames = [im.quantize(colors=GIF_COLOURS) for im in images]
    # Pillow merges identical neighbours (settle + hold) into one frame with the durations added.
    _atomic_save(frames[0], Path(out), save_all=True, append_images=frames[1:],
                 duration=[f.duration_ms for f in plan], loop=0, optimize=True)
    return throw.gif_duration_ms(plan)


def build_flight_gif(seed: int, palette: str, anim_dir: Path, out: Path) -> int:
    """The flight-only GIF of (seed, palette) at ``out`` — the pre-uploaded kind (ADR 064): the
    cached flicker frames, the last one with a blank face. Plays once (no loop), so it rests on
    the blank die until the result picture replaces it. Returns its play time in ms."""
    if palette not in RESULT_PALETTES:
        raise ValueError(f"unknown result palette {palette!r} (known: {', '.join(RESULT_PALETTES)})")
    throw = throw_module()
    plan = throw.flight_frames(seed, palette)
    ensure_frame_set(seed, palette, anim_dir)
    folder = frame_set_dir(anim_dir, seed, palette)
    images: list[Image.Image] = []
    for index, frame in enumerate(plan):
        if frame.kind == "flicker":
            with Image.open(folder / f"f_{index:02d}.png") as cached:
                images.append(cached.convert("RGB"))
        else:
            images.append(render_frame(frame))
    frames = [im.quantize(colors=GIF_COLOURS) for im in images]
    _atomic_save(frames[0], Path(out), save_all=True, append_images=frames[1:],
                 duration=[f.duration_ms for f in plan], optimize=True)  # no loop: plays once
    return throw.gif_duration_ms(plan)


# --- CLI -------------------------------------------------------------------------------------

def _parse_values(spec: str) -> range:
    lo, _, hi = spec.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def _throw_pool(anim_dir: Path, palettes: list[str], force: bool) -> None:
    seeds = pool_seeds(anim_dir)
    total = len(seeds) * len(palettes)
    done = 0
    started = time.monotonic()
    for palette in palettes:
        for seed in seeds:
            rendered = ensure_frame_set(seed, palette, anim_dir, force=force)
            done += 1
            elapsed = time.monotonic() - started
            print(f"[{done}/{total}] s{seed} {palette}: {rendered} frames rendered "
                  f"({elapsed/60:.1f} min so far)", flush=True)
    print(f"throw pool ready -> {anim_dir / 'frames'}")


def main(argv: list[str] | None = None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Pre-render the dice thumbnail cache.")
    parser.add_argument("--out", type=Path, default=repo_root / "data" / "dice",
                        help="cache root; dice land in <out>/<palette>/d_<n>.png, "
                             "target dice in <out>/steel/t_<n>.png, animation in <out>/anim/")
    parser.add_argument("--palette", choices=[*PALETTES, "all"], default="all")
    parser.add_argument("--values", default=f"1-{MAX_VALUE}", help="e.g. 1-100 or 20")
    parser.add_argument("--force", action="store_true", help="re-render files that already exist")
    parser.add_argument("--throw-pool", action="store_true",
                        help="render the animation frame pool (25 seeds × red/gold/green; slow)")
    parser.add_argument("--preview-throw", type=int, metavar="SEED",
                        help="write one complete throw GIF (result 23, red) to look at")
    args = parser.parse_args(argv)
    anim_dir = args.out / "anim"

    if args.preview_throw is not None:
        seed = args.preview_throw
        if not throw_module().good_seed(seed):
            print(f"note: seed {seed} is not in the good-seed pool (it fails the filter)")
        out = anim_dir / f"preview_s{seed}.gif"
        ms = build_throw_gif(seed, 23, "red", anim_dir, out)
        print(f"preview: {out.resolve()} ({ms/1000:.2f} s, {out.stat().st_size/1024:.0f} KiB)")
        return
    if args.throw_pool:
        palettes = list(RESULT_PALETTES) if args.palette == "all" else [args.palette]
        if not set(palettes) <= set(RESULT_PALETTES):
            parser.error(f"--throw-pool palettes: {', '.join(RESULT_PALETTES)}")
        _throw_pool(anim_dir, palettes, args.force)
        return

    palettes = list(PALETTES) if args.palette == "all" else [args.palette]
    for palette in palettes:
        folder = args.out / palette
        folder.mkdir(parents=True, exist_ok=True)
        target_die = palette == TARGET_PALETTE  # steel = the "≤n" target die
        rendered = 0
        for n in _parse_values(args.values):
            target = folder / (f"t_{n}.png" if target_die else f"d_{n}.png")
            if target.exists() and not args.force:
                continue
            render(n, target, seed=7, palette=palette, prefix=TARGET_PREFIX if target_die else "")
            rendered += 1
        print(f"{palette}: {rendered} rendered -> {folder}")


if __name__ == "__main__":
    main()
