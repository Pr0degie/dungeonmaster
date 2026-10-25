"""Render an ASCII-art d20 PNG for a value 1–100 (dice result thumbnails).

A hexagonal d20 silhouette is drawn in greyscale, the value goes in the centre triangle, and the
picture is then re-drawn as coloured ``@``-texture text on a dark background. Three palettes:
``red`` (default), ``gold`` (critical success) and ``green`` (fumble).

The bot renders on demand through :mod:`dmbot.dice_images` (cache ``data/dice/<palette>/``).
Run this file directly to pre-render the cache, e.g. on a new machine:

    uv run python tools/generate_dice.py                 # all palettes, 1–100
    uv run python tools/generate_dice.py --palette gold --values 1-20
"""

from __future__ import annotations

import argparse
import math
import os
import random
from pathlib import Path

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
}


def resolve_font(candidates: tuple[Path, ...], role: str) -> str:
    """The first existing font file of ``candidates``; a clear error naming them all otherwise."""
    for path in candidates:
        if path.is_file():
            return str(path)
    tried = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"no {role} font found for the dice renderer (tried: {tried})")


def render(number: int, path: str | os.PathLike, seed: int = 7, palette: str = "red") -> None:
    if not 1 <= number <= MAX_VALUE:
        raise ValueError(f"dice value must be 1..{MAX_VALUE}, got {number}")
    colorize = PALETTES[palette]
    font_bold = resolve_font(BOLD_FONT_CANDIDATES, "number (bold)")
    font_mono = resolve_font(MONO_FONT_CANDIDATES, "mono (ASCII)")
    # A private RNG, not random.seed(): the bot renders in a worker thread and must not reseed the
    # process-wide generator. Same seed → the same sequence, so the texture is unchanged.
    rng = random.Random(seed)
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

    # adaptive font size: smaller + centred in triangle
    num = str(number)
    size = {1: 0.14, 2: 0.125, 3: 0.09}[len(num)]
    fnt = ImageFont.truetype(font_bold, int(S*size))
    bb = ed.textbbox((0,0), num, font=fnt, stroke_width=5)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    # optical centre of point-up triangle: slightly below centroid (cy)
    ty = CY - R2*0.127
    ed.text((CX - tw/2 - bb[0], ty - th/2 - bb[1]), num, font=fnt,
            fill=12, stroke_width=5, stroke_fill=12)

    src = src.filter(ImageFilter.GaussianBlur(1.2))

    cols = 120
    cell_w, cell_h = 10, 16
    rows = int(cols * cell_w / cell_h)
    small = src.resize((cols, rows), Image.LANCZOS)

    ramp = " .,:;?*#S@@@"
    out = Image.new("RGB", (cols*cell_w, rows*cell_h), (28, 14, 38))
    od = ImageDraw.Draw(out)
    cfont = ImageFont.truetype(font_mono, 15)

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

    out.save(path)


def _parse_values(spec: str) -> range:
    lo, _, hi = spec.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def main(argv: list[str] | None = None) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Pre-render the dice thumbnail cache.")
    parser.add_argument("--out", type=Path, default=repo_root / "data" / "dice",
                        help="cache root; files land in <out>/<palette>/d_<n>.png")
    parser.add_argument("--palette", choices=[*PALETTES, "all"], default="all")
    parser.add_argument("--values", default=f"1-{MAX_VALUE}", help="e.g. 1-100 or 20")
    parser.add_argument("--force", action="store_true", help="re-render files that already exist")
    args = parser.parse_args(argv)
    palettes = list(PALETTES) if args.palette == "all" else [args.palette]
    for palette in palettes:
        folder = args.out / palette
        folder.mkdir(parents=True, exist_ok=True)
        rendered = 0
        for n in _parse_values(args.values):
            target = folder / f"d_{n}.png"
            if target.exists() and not args.force:
                continue
            render(n, target, seed=7, palette=palette)
            rendered += 1
        print(f"{palette}: {rendered} rendered -> {folder}")


if __name__ == "__main__":
    main()
