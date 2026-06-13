"""Fill the official Imperium Maledictum character sheet from a characters.json — OFFLINE tool.

    uv run python tools/fill_character_sheet.py data/sessions/<id>/characters.json
    uv run python tools/fill_character_sheet.py party.json --out data/sessions/<id>/sheets

The bought sheet PDF (``data/pdfs/Imperium Maledictum Character sheet.pdf``) carries **no form
fields and no extractable text** (fully graphical, a raster page), so every value is placed as a
real **AcroForm text field** (PyMuPDF widget) positioned over the printed box/line. That means the
output is **editable in any PDF reader** — the auto-filled values are just the defaults, the player
can click any field and type. Blank single-line identity fields are added empty so the sheet can be
completed by typing rather than by hand.

Positions are in **100-dpi pixels** (the page rendered at 100 dpi), converted to PDF points via the
0.72 factor (``PX``). The writing-line y of each row was read off the rendered raster by pixel
analysis; a field's rect is built a few px above its line so the text sits *on* the line. If a value
sits slightly off after a sheet revision, nudge the pixel numbers and re-run.

Filled per character: name, origin/concept/patron, the nine characteristics (starting + current
incl. origin boni — we only store finals, so both rows show them), skill advances + totals
(advances reconstructed as (value − governing characteristic) / 5), initiative, max wounds, the
main weapon row (test value + damage from the active system profile) and the inventory into the
equipment grid. Everything else stays as an empty editable field or printed line for handwriting.

Output PDFs are derivatives of the bought sheet → they live under git-ignored ``data/`` and are
never committed (public repo), like the PDFs themselves.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

SHEET = Path("data/pdfs/Imperium Maledictum Character sheet.pdf")
PROFILE = Path("data/systems/imperium_maledictum.json")

PX = 72 / 100  # 100-dpi render pixels → PDF points

INK = (0.13, 0.15, 0.25)  # dark blue-black "pen"
SIZE = 10

LEFT = fitz.TEXT_ALIGN_LEFT
CENTER = fitz.TEXT_ALIGN_CENTER

# A text field's box: from a few px above the writing line down to just below it, so the value sits
# on the line. _BOX_TOP/_BOX_BOTTOM are offsets in px from the line y.
_BOX_TOP = -14
_BOX_BOTTOM = 2

# ---- calibrated positions (in 100-dpi pixels; line y read off the raster) -----------------------
CHAR_COLS = {"WS": 125, "BS": 159, "Str": 191, "Tgh": 226, "Ag": 262, "Int": 296,
             "Per": 331, "Wil": 367, "Fel": 400}
P1 = {
    "name": (48, 149),
    "origin": (306, 88),
    "faction": (440, 88),       # blank, editable
    "role": (561, 88),          # we stamp the free-text concept here
    "patron": (696, 88),
    "char_row_starting": 260,
    "char_row_current": 298,
}
# blank single-line identity fields (age row, line y ≈ 124) → empty editable fields, left-aligned
P1_BLANKS = {
    # field_name: (left_px, line_px, width_px)
    "age":          (308, 124, 70),
    "eyes":         (392, 124, 70),
    "hair":         (473, 124, 70),
    "height":       (560, 124, 70),
    "weight":       (645, 124, 70),
    "handedness":   (728, 124, 100),
    "distinguishing": (306, 169, 360),   # "DISTINGUISHING FEATURES" line
}
# skill rows: (page-1 label row y, (adv-column x, total-column x), german skill, gov characteristic)
_LEFT_BLK = (225, 260)   # adv x, total x of the left skill block
_MID_BLK = (488, 526)    # … of the middle block
P1_SKILLS = {
    "Athletics":  (381, _LEFT_BLK, "Athletik", "Str"),
    "Awareness":  (400, _LEFT_BLK, "Wahrnehmung", "Per"),
    "Lore":       (537, _LEFT_BLK, "Wissen", "Int"),
    "Medicae":    (557, _LEFT_BLK, "Medizin", "Int"),
    "Melee":      (381, _MID_BLK, "Nahkampf", "WS"),
    "Presence":   (420, _MID_BLK, "Einschüchtern", "Fel"),
    "Ranged":     (478, _MID_BLK, "Fernkampf", "BS"),
    "Rapport":    (498, _MID_BLK, "Überreden", "Fel"),
    "Stealth":    (537, _MID_BLK, "Heimlichkeit", "Ag"),
    "Tech":       (557, _MID_BLK, "Technologie", "Int"),
}
P2 = {
    "initiative": (95, 122),
    "wounds_current": (212, 124),
    "wounds_max": (290, 124),
    "weapon_name": (50, 280),       # was 288 → 8 px below the line; the row line is at y≈280
    "weapon_test": (313, 280),
    "weapon_damage": (368, 280),
    "equip_x": 440,
    "equip_y0": 591,                # equipment writing lines: 591, 612, 633, … (21 px apart)
    "equip_dy": 21.0,
    "equip_max": 9,
}

RANGED_WEAPONS = {"lasgewehr", "laspistole", "autopistole", "stubber"}


def _field(page: fitz.Page, name: str, left_px: float, line_px: float, width_px: float,
           value: str, *, size: int = SIZE, align: int = LEFT, center: bool = False) -> None:
    """Add an editable AcroForm text field over the box at (left/center, line). Transparent fill +
    no border, so the printed sheet shows through; ``value`` is the editable default."""
    x0 = (left_px - width_px / 2) if center else left_px
    rect = fitz.Rect(x0 * PX, (line_px + _BOX_TOP) * PX,
                     (x0 + width_px) * PX, (line_px + _BOX_BOTTOM) * PX)
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = name
    w.rect = rect
    w.text_fontsize = size
    w.text_color = INK
    w.fill_color = None      # transparent → the sheet graphic shows through
    w.border_color = None
    w.text_align = align
    w.field_value = value or ""
    page.add_widget(w)


def _bonus(value: int) -> int:
    return value // 10


def fill_sheet(char: dict, weapons: dict, default_damage: str, out_path: Path) -> None:
    doc = fitz.open(SHEET)
    doc.set_metadata({})  # ensure a clean /AcroForm gets written
    p1, p2 = doc[0], doc[1]
    chars: dict[str, int] = {k: int(v) for k, v in (char.get("characteristics") or {}).items()}
    skills: dict[str, int] = {k: int(v) for k, v in (char.get("skills") or {}).items()}

    # --- page 1: identity ------------------------------------------------------------------
    x, y = P1["name"]
    _field(p1, "name", x, y, 250, char.get("name", ""), size=11)
    x, y = P1["origin"]
    _field(p1, "origin", x, y, 120, str(char.get("origin", "")))
    x, y = P1["faction"]
    _field(p1, "faction", x, y, 110, "")        # blank, editable
    x, y = P1["role"]
    _field(p1, "role", x, y, 120, str(char.get("concept", ""))[:40], size=8)
    x, y = P1["patron"]
    _field(p1, "patron", x, y, 100, "Halikarn")
    for fname, (lx, ly, w) in P1_BLANKS.items():
        _field(p1, fname, lx, ly, w, "", size=9)

    # --- page 1: characteristics (we only store finals → starting == current) ---------------
    for key, cx in CHAR_COLS.items():
        v = chars.get(key)
        if v is None:
            continue
        _field(p1, f"char_start_{key}", cx, P1["char_row_starting"], 30, str(v),
               align=CENTER, center=True)
        _field(p1, f"char_curr_{key}", cx, P1["char_row_current"], 30, str(v),
               align=CENTER, center=True)

    # --- page 1: skills (advances reconstructed from value − characteristic) ----------------
    for sheet_skill, (y, (adv_x, tot_x), german, gov) in P1_SKILLS.items():
        value = skills.get(german)
        if value is None:
            continue
        adv = max(0, value - chars.get(gov, value)) // 5
        if adv:
            _field(p1, f"skill_adv_{sheet_skill}", adv_x, y, 24, str(adv),
                   size=9, align=CENTER, center=True)
        _field(p1, f"skill_tot_{sheet_skill}", tot_x, y, 28, str(value),
               size=9, align=CENTER, center=True)

    # --- page 2: initiative + wounds ---------------------------------------------------------
    if "Per" in chars and "Ag" in chars:
        x, y = P2["initiative"]
        _field(p2, "initiative", x, y, 40, str(_bonus(chars["Per"]) + _bonus(chars["Ag"])),
               align=CENTER, center=True)
    wounds = char.get("max_wounds") or char.get("wounds")
    if wounds is not None:
        x, y = P2["wounds_current"]
        _field(p2, "wounds_current", x, y, 30, str(wounds), align=CENTER, center=True)
        x, y = P2["wounds_max"]
        _field(p2, "wounds_max", x, y, 30, str(wounds), align=CENTER, center=True)

    # --- page 2: main weapon row -------------------------------------------------------------
    inventory = [str(i) for i in (char.get("inventory") or [])]
    weapon = inventory[0] if inventory else None
    if weapon:
        is_ranged = weapon.lower() in RANGED_WEAPONS
        test_skill = "Fernkampf" if is_ranged else "Nahkampf"
        damage = weapons.get(weapon, default_damage).replace("d", "W")
        x, y = P2["weapon_name"]
        _field(p2, "weapon_name", x, y, 150, weapon, size=9)
        if skills.get(test_skill) is not None:
            x, y = P2["weapon_test"]
            _field(p2, "weapon_test", x, y, 34, str(skills[test_skill]), size=9,
                   align=CENTER, center=True)
        x, y = P2["weapon_damage"]
        _field(p2, "weapon_damage", x, y, 55, damage, size=9, align=CENTER, center=True)

    # --- page 2: equipment grid (rest of the inventory) --------------------------------------
    for i, item in enumerate(inventory[1:P2["equip_max"] + 1]):
        _field(p2, f"equip_{i}", P2["equip_x"], P2["equip_y0"] + i * P2["equip_dy"], 150,
               item, size=9)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill IM character sheets from a characters.json.")
    parser.add_argument("characters", type=Path, help="characters.json (party file or form output)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output dir (default: sheets/ beside the input file)")
    args = parser.parse_args()
    if not SHEET.is_file():
        print(f"[!!] sheet PDF not found: {SHEET}")
        return 1
    data = json.loads(args.characters.read_text(encoding="utf-8"))
    chars = data.get("characters", [data] if "name" in data else [])
    if not chars:
        print("[!!] no characters found in the input")
        return 1
    profile = json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.is_file() else {}
    weapons = (profile.get("combat") or {}).get("weapons", {})
    default_damage = (profile.get("combat") or {}).get("default_damage", "1d10")
    out_dir = args.out or (args.characters.parent / "sheets")
    for char in chars:
        # raw dicts from the party file carry the full schema; form blocks are the same shape
        name = str(char.get("name", "unbenannt")).replace(" ", "_")
        out = out_dir / f"{name}.pdf"
        fill_sheet(char, weapons, default_damage, out)
        print(f"[OK] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
