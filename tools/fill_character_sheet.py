"""Fill the official Imperium Maledictum character sheet from a characters.json — OFFLINE tool.

    uv run python tools/fill_character_sheet.py data/sessions/<id>/characters.json
    uv run python tools/fill_character_sheet.py party.json --out data/sessions/<id>/sheets

The bought sheet PDF (``data/pdfs/Imperium Maledictum Character sheet.pdf``) carries **no form
fields and no extractable text** (fully graphical), so values are stamped by coordinate overlay
(PyMuPDF ``insert_text``). The COORDS table below was calibrated by rendering the pages at
100 dpi and reading positions off the image — pixel values there divide by 72/100 into PDF
points, hence the 0.72 factor. If a value sits slightly off after a sheet revision, nudge the
pixel numbers and re-run.

Filled per character: name, origin/concept/patron, the nine characteristics (starting + current
incl. origin boni — we only store finals, so both rows show them), skill advances + totals
(advances are reconstructed as (value − governing characteristic) / 5), initiative, max wounds,
the main weapon row (test value + damage from the active system profile) and the inventory into
the equipment grid. Everything else stays blank for handwriting.

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

# ---- calibrated positions (in 100-dpi pixels; converted via PX below) ---------------------------
CHAR_COLS = {"WS": 125, "BS": 159, "Str": 191, "Tgh": 226, "Ag": 262, "Int": 296,
             "Per": 331, "Wil": 367, "Fel": 400}
P1 = {
    "name": (48, 149),
    "origin": (306, 88),
    "role": (561, 88),          # we stamp the free-text concept here
    "patron": (696, 88),
    "char_row_starting": 260,
    "char_row_current": 298,
}
# skill rows: (page-1 label row y, adv-column x, total-column x) per sheet skill
_LEFT = (225, 260)   # adv x, total x of the left skill block
_MID = (488, 526)    # … of the middle block
P1_SKILLS = {
    # sheet skill: (y, (adv_x, total_x), german skill, governing characteristic)
    "Athletics":  (381, _LEFT, "Athletik", "Str"),
    "Awareness":  (400, _LEFT, "Wahrnehmung", "Per"),
    "Lore":       (537, _LEFT, "Wissen", "Int"),
    "Medicae":    (557, _LEFT, "Medizin", "Int"),
    "Melee":      (381, _MID, "Nahkampf", "WS"),
    "Presence":   (420, _MID, "Einschüchtern", "Fel"),
    "Ranged":     (478, _MID, "Fernkampf", "BS"),
    "Rapport":    (498, _MID, "Überreden", "Fel"),
    "Stealth":    (537, _MID, "Heimlichkeit", "Ag"),
    "Tech":       (557, _MID, "Technologie", "Int"),
}
P2 = {
    "initiative": (95, 122),
    "wounds_current": (212, 124),
    "wounds_max": (290, 124),
    "weapon_name": (50, 288),
    "weapon_test": (313, 288),
    "weapon_damage": (368, 288),
    "equip_x": 440,
    "equip_y0": 593,
    "equip_dy": 21.2,
    "equip_max": 9,
}

RANGED_WEAPONS = {"lasgewehr", "laspistole", "autopistole", "stubber"}


def _put(page: fitz.Page, x_px: float, y_px: float, text: str, *, size: int = SIZE,
         center: bool = False) -> None:
    x = x_px * PX
    if center:
        x -= fitz.get_text_length(text, fontname="helv", fontsize=size) / 2
    page.insert_text((x, y_px * PX), text, fontname="helv", fontsize=size, color=INK)


def _bonus(value: int) -> int:
    return value // 10


def fill_sheet(char: dict, weapons: dict, default_damage: str, out_path: Path) -> None:
    doc = fitz.open(SHEET)
    p1, p2 = doc[0], doc[1]
    chars: dict[str, int] = {k: int(v) for k, v in (char.get("characteristics") or {}).items()}
    skills: dict[str, int] = {k: int(v) for k, v in (char.get("skills") or {}).items()}

    # --- page 1: identity ------------------------------------------------------------------
    _put(p1, *P1["name"], char.get("name", ""), size=11)
    if char.get("origin"):
        _put(p1, *P1["origin"], str(char["origin"]))
    if char.get("concept"):
        _put(p1, *P1["role"], str(char["concept"])[:30], size=8)
    _put(p1, *P1["patron"], "Halikarn")

    # --- page 1: characteristics (we only store finals → starting == current) ---------------
    for key, x in CHAR_COLS.items():
        v = chars.get(key)
        if v is None:
            continue
        _put(p1, x, P1["char_row_starting"], str(v), center=True)
        _put(p1, x, P1["char_row_current"], str(v), center=True)

    # --- page 1: skills (advances reconstructed from value − characteristic) ----------------
    for _sheet_skill, (y, (adv_x, tot_x), german, gov) in P1_SKILLS.items():
        value = skills.get(german)
        if value is None:
            continue
        adv = max(0, value - chars.get(gov, value)) // 5
        if adv:
            _put(p1, adv_x, y, str(adv), size=9, center=True)
        _put(p1, tot_x, y, str(value), size=9, center=True)

    # --- page 2: initiative + wounds ---------------------------------------------------------
    if "Per" in chars and "Ag" in chars:
        _put(p2, *P2["initiative"], str(_bonus(chars["Per"]) + _bonus(chars["Ag"])))
    wounds = char.get("max_wounds") or char.get("wounds")
    if wounds is not None:
        _put(p2, *P2["wounds_current"], str(wounds), center=True)
        _put(p2, *P2["wounds_max"], str(wounds), center=True)

    # --- page 2: main weapon row -------------------------------------------------------------
    inventory = [str(i) for i in (char.get("inventory") or [])]
    weapon = inventory[0] if inventory else None
    if weapon:
        is_ranged = weapon.lower() in RANGED_WEAPONS
        test_skill = "Fernkampf" if is_ranged else "Nahkampf"
        damage = weapons.get(weapon, default_damage).replace("d", "W")
        _put(p2, *P2["weapon_name"], weapon, size=9)
        if skills.get(test_skill) is not None:
            _put(p2, *P2["weapon_test"], str(skills[test_skill]), size=9, center=True)
        _put(p2, *P2["weapon_damage"], damage, size=9, center=True)

    # --- page 2: equipment grid (rest of the inventory) --------------------------------------
    for i, item in enumerate(inventory[1:P2["equip_max"] + 1]):
        _put(p2, P2["equip_x"], P2["equip_y0"] + i * P2["equip_dy"], item, size=9)

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
