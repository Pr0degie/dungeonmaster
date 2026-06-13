"""Fill the official Imperium Maledictum character sheet from a characters.json — OFFLINE tool.

    uv run python tools/fill_character_sheet.py data/sessions/<id>/characters.json
    uv run python tools/fill_character_sheet.py tools/example_garran_vex.json --out data/pdfs

The bought sheet PDF (``data/pdfs/Imperium Maledictum Character sheet.pdf``) carries **no form
fields and no extractable text** (fully graphical, a raster page), so every value is placed as a
real **AcroForm text field** (PyMuPDF widget) over the printed box/line. The output is therefore
**editable in any PDF reader** — the auto-filled values are just defaults the player can overtype.
**Every fillable area is a field**, even the ones we have no data for (all skill rows, weapon/armour
tables, talents, influence, psychic powers, critical wounds, …) and the open blocks (goals,
connections, notes, combat notes) as multi-line fields — so a sheet can be completed entirely by
typing.

Positions are in **100-dpi pixels** (the page rendered at 100 dpi), converted to PDF points via the
0.72 factor (``PX``). Each row's writing-line y was read off the rendered raster by pixel analysis;
a field's box is built a few px above its line so text sits *on* the line. If a value sits slightly
off after a sheet revision, nudge the pixel numbers and re-run.

Two input shapes, both work:
- **Mechanical party file** (``data/sessions/<id>/characters.json``): the nine characteristics,
  trained skills, wounds, inventory. Fills the mechanical fields; the rest stay empty + editable.
- **Rich example** (``tools/example_garran_vex.json``): adds origin/faction/concept, age/eyes/…,
  goals/connections/notes, talents[], weapons[], armour[], equipment[], fate/corruption/xp — every
  optional, filled when present.

Output PDFs are derivatives of the bought sheet → they live under git-ignored ``data/`` and are
never committed (public repo), like the PDFs themselves. (The example *JSON* is own flavour text and
is committed; only its rendered PDF is not.)
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
_MULTILINE = 1 << 12  # PDF Tx field flag: multi-line

# A field box runs from a few px above the writing line to just below it (so text sits on the line).
_BOX_TOP, _BOX_BOTTOM = -14, 2

RANGED_WEAPONS = {"lasgewehr", "laspistole", "autopistole", "stubber"}


def _field(page: fitz.Page, name: str, left_px: float, line_px: float, width_px: float,
           value: str, *, size: int = SIZE, align: int = LEFT, center: bool = False) -> None:
    """One editable single-line text field over the box at (left/center, line)."""
    x0 = (left_px - width_px / 2) if center else left_px
    rect = fitz.Rect(x0 * PX, (line_px + _BOX_TOP) * PX,
                     (x0 + width_px) * PX, (line_px + _BOX_BOTTOM) * PX)
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = name
    w.rect = rect
    w.text_fontsize = size
    w.text_color = INK
    w.fill_color = None
    w.border_color = None
    w.text_align = align
    w.field_value = "" if value is None else str(value)
    page.add_widget(w)


def _multiline(page: fitz.Page, name: str, box_px: tuple[float, float, float, float],
               value: str, *, size: int = 9) -> None:
    """One editable multi-line text field spanning an open block (goals/notes/…)."""
    x0, y0, x1, y1 = box_px
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = name
    w.rect = fitz.Rect(x0 * PX, y0 * PX, x1 * PX, y1 * PX)
    w.field_flags = _MULTILINE
    w.text_fontsize = size
    w.text_color = INK
    w.fill_color = None
    w.border_color = None
    w.text_align = LEFT
    w.field_value = "" if value is None else str(value)
    page.add_widget(w)


def _grid(page: fitz.Page, prefix: str, rows_y: list[float], cols: list[dict],
          data: list[dict], *, size: int = 9) -> None:
    """Place an editable field per (row, column). ``cols`` items: {key,x,w,align,center}.
    ``data[r][key]`` pre-fills row r (missing → empty, still editable)."""
    for r, y in enumerate(rows_y):
        row = data[r] if r < len(data) else {}
        for c in cols:
            _field(page, f"{prefix}_{r}_{c['key']}", c["x"], y, c["w"],
                   row.get(c["key"], ""), size=size,
                   align=c.get("align", LEFT), center=c.get("center", False))


def _bonus(value: int) -> int:
    return value // 10


# ---- page-1 layout ------------------------------------------------------------------------------
CHAR_COLS = {"WS": 125, "BS": 159, "Str": 191, "Tgh": 226, "Ag": 262, "Int": 296,
             "Per": 331, "Wil": 367, "Fel": 400}
ID_FIELDS = {  # name: (left_px, line_px, width_px, size, source_key)
    "name":          (48, 149, 250, 11, "name"),
    "origin":        (306, 88, 120, 10, "origin"),
    "faction":       (440, 88, 110, 10, "faction"),
    "role":          (561, 88, 120, 8, "concept"),
    "patron":        (696, 88, 100, 10, "patron"),
    "age":           (308, 124, 70, 9, "age"),
    "eyes":          (392, 124, 70, 9, "eyes"),
    "hair":          (473, 124, 70, 9, "hair"),
    "height":        (560, 124, 70, 9, "height"),
    "weight":        (645, 124, 70, 9, "weight"),
    "handedness":    (728, 124, 100, 9, "handedness"),
    "distinguishing": (306, 154, 360, 9, "distinguishing"),
    "xp_total":      (715, 154, 28, 8, "xp_total"),
    "xp_spent":      (758, 154, 28, 8, "xp_spent"),
}
# all 20 skill rows: (sheet_id, line_y, adv_x, tot_x, german_or_None, gov_or_None).
# The skill grid's row separators sit every 20 px (…368, 388, 408…); a cell's center is the rule
# midpoint and our box baseline = center + 6, so row i (0-based) = 384 + 20*i. Both columns share
# the same row y. Getting the start/step exactly right stops the drift down the table.
_SKILL_ROWS = [
    ("Athletics", 384, 225, 260, "Athletik", "Str"), ("Awareness", 404, 225, 260, "Wahrnehmung", "Per"),
    ("Dexterity", 424, 225, 260, None, None),
    ("Discipline", 444, 225, 260, "Disziplin (Psi)", "Wil"),
    ("Fortitude", 464, 225, 260, None, None), ("Intuition", 484, 225, 260, None, None),
    ("Linguistics", 504, 225, 260, None, None), ("Logic", 524, 225, 260, None, None),
    ("Lore", 544, 225, 260, "Wissen", "Int"), ("Medicae", 564, 225, 260, "Medizin", "Int"),
    ("Melee", 384, 488, 526, "Nahkampf", "WS"), ("Navigation", 404, 488, 526, None, None),
    ("Presence", 424, 488, 526, "Einschüchtern", "Fel"), ("Piloting", 444, 488, 526, None, None),
    ("PsychicMastery", 464, 488, 526, "Psi-Meisterschaft", "Wil"), ("Ranged", 484, 488, 526, "Fernkampf", "BS"),
    ("Rapport", 504, 488, 526, "Überreden", "Fel"), ("Reflexes", 524, 488, 526, None, None),
    ("Stealth", 544, 488, 526, "Heimlichkeit", "Ag"), ("Tech", 564, 488, 526, "Technologie", "Int"),
]
_SPEC_ROWS = [384, 404, 424, 444, 464, 484, 504, 524, 544]  # same grid as the skill rows
_SPEC_COLS = [{"key": "spec", "x": 562, "w": 125}, {"key": "skill", "x": 688, "w": 55},
              {"key": "adv", "x": 752, "w": 24, "center": True, "align": CENTER},
              {"key": "tot", "x": 788, "w": 26, "center": True, "align": CENTER}]
_INFLU_ROWS = [628, 647, 667, 687, 708, 728, 748, 768]
_INFLU_COLS = [{"key": "faction", "x": 308, "w": 150},
               {"key": "infl", "x": 462, "w": 24, "center": True, "align": CENTER},
               {"key": "contacts", "x": 505, "w": 300}]
_TALENT_ROWS = [834, 854, 873, 894, 914, 934, 953, 974, 995, 1014]
_TALENT_COLS = [{"key": "name", "x": 308, "w": 150}, {"key": "effect", "x": 462, "w": 345}]

# ---- page-2 layout ------------------------------------------------------------------------------
_CRIT_ROWS = [116, 136, 156, 176, 197]
_CRIT_COLS = [{"key": "loc", "x": 345, "w": 55}, {"key": "eff", "x": 408, "w": 395}]
_WEAP_ROWS = [280, 300, 320, 340, 360]
_WEAP_COLS = [{"key": "name", "x": 50, "w": 135}, {"key": "spec", "x": 190, "w": 110},
              {"key": "test", "x": 313, "w": 34, "center": True, "align": CENTER},
              {"key": "damage", "x": 368, "w": 50, "center": True, "align": CENTER},
              {"key": "range", "x": 420, "w": 40, "center": True, "align": CENTER},
              {"key": "mag", "x": 475, "w": 35, "center": True, "align": CENTER},
              {"key": "enc", "x": 525, "w": 32, "center": True, "align": CENTER},
              {"key": "traits", "x": 575, "w": 230}]
_ARM_ROWS = [443, 463, 482, 502, 522]
_ARM_COLS = [{"key": "name", "x": 45, "w": 120}, {"key": "locations", "x": 190, "w": 108},
             {"key": "armour", "x": 315, "w": 36, "center": True, "align": CENTER},
             {"key": "enc", "x": 358, "w": 34, "center": True, "align": CENTER},
             {"key": "traits", "x": 405, "w": 250}]
# hit-location armour boxes (right table): D10 row → armour value
_HITLOC = [("Head", 421), ("Left Arm", 441), ("Right Arm", 461),
           ("Left Leg", 481), ("Right Leg", 501), ("Body", 521)]
_HITLOC_X = 790
_EQUIP_COLS_X = [440, 565, 690]      # three equipment columns
_EQUIP_Y0, _EQUIP_DY, _EQUIP_ROWS = 591, 21.0, 9
_PSY_ROWS = [874, 894, 914, 934, 954, 974, 994, 1014]
_PSY_COLS = [{"key": "name", "x": 45, "w": 130},
             {"key": "wr", "x": 205, "w": 28, "center": True, "align": CENTER},
             {"key": "difficulty", "x": 258, "w": 50, "center": True, "align": CENTER},
             {"key": "range", "x": 315, "w": 40, "center": True, "align": CENTER},
             {"key": "target", "x": 368, "w": 45, "center": True, "align": CENTER},
             {"key": "duration", "x": 432, "w": 55, "center": True, "align": CENTER},
             {"key": "effect", "x": 492, "w": 315}]


def _weapons_from(char: dict, weapons_table: dict, default_damage: str) -> list[dict]:
    """Explicit char['weapons'] if given, else derive a single main-weapon row from inventory[0]."""
    if char.get("weapons"):
        return [dict(w) for w in char["weapons"]]
    inv = [str(i) for i in (char.get("inventory") or [])]
    if not inv:
        return []
    w = inv[0]
    is_ranged = w.lower() in RANGED_WEAPONS
    skills = char.get("skills") or {}
    test = skills.get("Fernkampf" if is_ranged else "Nahkampf")
    return [{"name": w, "test": "" if test is None else str(test),
             "damage": weapons_table.get(w, default_damage).replace("d", "W")}]


def _psy_rows_from(char: dict, psyker_profile: dict) -> list[dict]:
    """Build the psychic-powers grid rows from char['known_powers'] × the profile's psyker catalog
    (ADR 022/023). Each power's stats (Warp Rating, Difficulty, Range, Target, Duration, effect)
    come from the catalog; an Overt power gets a trailing '*'. Unknown powers still print by name."""
    catalog = (psyker_profile or {}).get("powers", {}) or {}
    rows = []
    for name in (char.get("known_powers") or []):
        s = catalog.get(name) or {}
        rows.append({
            "name": str(name) + ("*" if s.get("overt") else ""),
            "wr": str(s.get("warp_rating", "")),
            "difficulty": str(s.get("difficulty", "")),
            "range": str(s.get("range", "")),
            "target": str(s.get("target", "")),
            "duration": str(s.get("duration", "")),
            "effect": str(s.get("effect", "")),
        })
    return rows


def fill_sheet(char: dict, weapons_table: dict, default_damage: str, out_path: Path,
               profile: dict | None = None) -> None:
    profile = profile or {}
    doc = fitz.open(SHEET)
    p1, p2 = doc[0], doc[1]
    chars = {k: int(v) for k, v in (char.get("characteristics") or {}).items()}
    skills = {k: int(v) for k, v in (char.get("skills") or {}).items()}

    # --- page 1: identity (patron defaults to Halikarn for this campaign) --------------------
    for fname, (lx, ly, w, sz, key) in ID_FIELDS.items():
        val = char.get(key, "")
        if fname == "patron" and not val:
            val = "Halikarn"
        if fname == "role":
            val = str(val)[:40]
        _field(p1, fname, lx, ly, w, val, size=sz)
    _field(p1, "fate_current", 462, 260, 28, str(char.get("fate_current", "")),
           align=CENTER, center=True)
    _field(p1, "fate_total", 523, 260, 28, str(char.get("fate_total", "")),
           align=CENTER, center=True)
    _field(p1, "corruption_total", 597, 260, 28, str(char.get("corruption", "")),
           align=CENTER, center=True)

    # --- page 1: characteristics (we only store finals → starting == current) ---------------
    for key, cx in CHAR_COLS.items():
        v = chars.get(key)
        if v is None:
            continue
        _field(p1, f"char_start_{key}", cx, 260, 30, str(v), align=CENTER, center=True)
        _field(p1, f"char_curr_{key}", cx, 298, 30, str(v), align=CENTER, center=True)

    # --- page 1: every skill row editable; trained ones pre-filled --------------------------
    for sid, y, adv_x, tot_x, german, gov in _SKILL_ROWS:
        value = skills.get(german) if german else None
        adv = (max(0, value - chars.get(gov, value)) // 5) if value is not None else None
        _field(p1, f"skill_adv_{sid}", adv_x, y, 24, "" if not adv else str(adv),
               size=9, align=CENTER, center=True)
        _field(p1, f"skill_tot_{sid}", tot_x, y, 28, "" if value is None else str(value),
               size=9, align=CENTER, center=True)

    # --- page 1: specialisations / influence / talents --------------------------------------
    _grid(p1, "spec", _SPEC_ROWS, _SPEC_COLS, [])
    _grid(p1, "influence", _INFLU_ROWS, _INFLU_COLS, [])
    _grid(p1, "talent", _TALENT_ROWS, _TALENT_COLS,
          [{"name": t.get("name", ""), "effect": t.get("effect", "")}
           for t in (char.get("talents") or [])])

    # --- page 1: open blocks (multi-line) ----------------------------------------------------
    _multiline(p1, "goals", (45, 605, 280, 685), char.get("goals", ""))
    _multiline(p1, "connections", (45, 712, 280, 790), char.get("connections", ""))
    _multiline(p1, "notes", (45, 815, 280, 985), char.get("notes", ""))
    _multiline(p1, "divination", (45, 1008, 280, 1052), char.get("divination", ""))

    # --- page 2: initiative + wounds ---------------------------------------------------------
    if "Per" in chars and "Ag" in chars:
        _field(p2, "initiative", 95, 122, 40, str(_bonus(chars["Per"]) + _bonus(chars["Ag"])),
               align=CENTER, center=True)
    # Quick-reference boxes under Initiative for the three combat-reaction skills (not a derived
    # stat — optional). Fill from explicit fields if given, else leave blank + editable.
    for cx, key in ((70, "init_melee"), (108, "init_ranged"), (150, "init_reflexes")):
        _field(p2, key, cx, 178, 32, str(char.get(key, "")), align=CENTER, center=True)
    wounds = char.get("max_wounds") or char.get("wounds")
    if wounds is not None:
        _field(p2, "wounds_current", 212, 124, 30, str(wounds), align=CENTER, center=True)
        _field(p2, "wounds_max", 290, 124, 30, str(wounds), align=CENTER, center=True)

    # --- page 2: critical wounds / weapons / armour ------------------------------------------
    _grid(p2, "crit", _CRIT_ROWS, _CRIT_COLS, [])
    _grid(p2, "weapon", _WEAP_ROWS, _WEAP_COLS,
          _weapons_from(char, weapons_table, default_damage), size=9)
    _grid(p2, "armour", _ARM_ROWS, _ARM_COLS,
          [dict(a) for a in (char.get("armour") or [])], size=9)
    hit = char.get("hit_location_armour") or {}
    for loc, y in _HITLOC:
        _field(p2, f"hitloc_{loc.replace(' ', '')}", _HITLOC_X, y, 28,
               str(hit.get(loc, "")), size=9, align=CENTER, center=True)

    # --- page 2: combat notes (open) + equipment (3 columns) ---------------------------------
    _multiline(p2, "combat_notes", (45, 600, 422, 790), char.get("combat_notes", ""))
    equip = [str(i) for i in (char.get("equipment") or list(char.get("inventory") or [])[1:])]
    # The bought sheet has no dedicated augmetics box → list implants in the middle equipment
    # column (left column = gear, middle = "Augmetik: …"). Names match the profile catalog (ADR 023).
    augmetics = [str(a) for a in (char.get("augmetics") or [])]
    aug_col = (["Augmetik:"] + augmetics) if augmetics else []
    for col, ex in enumerate(_EQUIP_COLS_X):
        items = equip if col == 0 else (aug_col if col == 1 else [])
        for r in range(_EQUIP_ROWS):
            val = items[r] if r < len(items) else ""
            _field(p2, f"equip_{col}_{r}", ex, _EQUIP_Y0 + r * _EQUIP_DY, 150, val, size=9)
    _field(p2, "enc_current", 720, 756, 30, str(char.get("encumbrance_current", "")),
           align=CENTER, center=True)
    _field(p2, "enc_max", 778, 756, 30, str(char.get("encumbrance_max", "")),
           align=CENTER, center=True)

    # --- page 2: psychic powers + warp charge ------------------------------------------------
    # Fill the psychic-powers table from known_powers × the profile catalog; Warp Threshold =
    # Willpower Bonus (ADR 022). A non-psyker leaves these empty + editable, as before.
    _grid(p2, "psy", _PSY_ROWS, _PSY_COLS, _psy_rows_from(char, profile.get("psyker") or {}), size=8)
    threshold = _bonus(chars["Wil"]) if (char.get("psyker") and "Wil" in chars) else ""
    _field(p2, "warp_current", 720, 1012, 30, "0" if char.get("psyker") else "",
           align=CENTER, center=True)
    _field(p2, "warp_threshold", 785, 1012, 30, str(threshold), align=CENTER, center=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill IM character sheets from a characters.json.")
    parser.add_argument("characters", type=Path, help="characters.json (party file or example)")
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
        name = str(char.get("name", "unbenannt")).replace(" ", "_")
        out = out_dir / f"{name}.pdf"
        fill_sheet(char, weapons, default_damage, out, profile)
        print(f"[OK] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
