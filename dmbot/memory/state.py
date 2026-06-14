"""World state — the 'hard facts' half of memory (architecture §7, golden rule #3).

Per-channel mutable game state in ``data/sessions/<channel_id>/state.json``: the party's current
wounds / conditions / inventory, the NPCs in play, open quests, location, in-game time, and the
stored session recap. Advanced **deterministically by code** (e.g. HP after damage) — never
written from LLM free text. The one narrative field is ``recap``, produced by the wrap-up
summariser (LLM) but *stored* by code (memory split, golden rule #3).

Design (ADR 015 — "split"): the player **sheets** (characteristics, skills, ``max_wounds``,
aliases) stay in the read-only ``characters.json`` — the source transferred once from the sheets
(ADR 004). This ``state.json`` is the code-owned **mutable layer**, seeded once from that sheet on
the first join. Code only ever writes ``state.json``, so the sheet stays pristine and a session
resets by deleting ``state.json``.

Pure data + pure functions, unit-tested without Discord or the LLM. Combat *math* lives in
:mod:`dmbot.rules.engine`; this module only applies the resulting number and persists it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..rules.characters import CharacterStore

# Condition set on a combatant whose wounds reach 0. German (play language); the caller can pass a
# system-specific word, but this is the sensible default for IM ("kampfunfähig" → out of the fight).
DOWNED_CONDITION = "kampfunfähig"


@dataclass
class Combatant:
    """A character or NPC for state/damage purposes. Mutable — this is the code-owned layer.

    ``armour`` and ``toughness_bonus`` are the soak inputs the engine subtracts from damage. For a
    **player** they're derived from the sheet at damage time (TB = tens of Toughness), so a PC entry
    usually leaves ``toughness_bonus=0`` here; an **NPC** carries its own soak values directly.
    """

    name: str
    wounds: int
    max_wounds: int
    conditions: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    armour: int = 0
    toughness_bonus: int = 0
    is_npc: bool = False
    attitude: str = ""  # NPCs only (§7): "hostile" | "neutral" | … ; empty for PCs
    # Psyker resource (ADR 022): accumulated Warp Charge and the powers being Sustained. Mutable +
    # code-owned, like wounds — advanced by the Manifest/Purgation flow, never by LLM free text.
    warp_charge: int = 0
    sustained_powers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "wounds": self.wounds, "max_wounds": self.max_wounds}
        if self.conditions:
            d["conditions"] = list(self.conditions)
        if self.inventory:
            d["inventory"] = list(self.inventory)
        if self.armour:
            d["armour"] = self.armour
        if self.toughness_bonus:
            d["toughness_bonus"] = self.toughness_bonus
        if self.attitude:
            d["attitude"] = self.attitude
        if self.warp_charge:
            d["warp_charge"] = self.warp_charge
        if self.sustained_powers:
            d["sustained_powers"] = list(self.sustained_powers)
        return d

    @classmethod
    def from_dict(cls, d: dict, *, is_npc: bool = False) -> "Combatant":
        max_w = int(d.get("max_wounds", d.get("wounds", 0)) or 0)
        return cls(
            name=d["name"],
            wounds=int(d.get("wounds", max_w) if d.get("wounds") is not None else max_w),
            max_wounds=max_w,
            conditions=list(d.get("conditions", []) or []),
            inventory=list(d.get("inventory", []) or []),
            armour=int(d.get("armour", 0) or 0),
            toughness_bonus=int(d.get("toughness_bonus", 0) or 0),
            is_npc=is_npc,
            attitude=str(d.get("attitude", "") or ""),
            warp_charge=int(d.get("warp_charge", 0) or 0),
            sustained_powers=list(d.get("sustained_powers", []) or []),
        )


@dataclass
class Quest:
    title: str
    status: str = "open"

    def to_dict(self) -> dict:
        return {"title": self.title, "status": self.status}

    @classmethod
    def from_dict(cls, d: dict) -> "Quest":
        return cls(title=d["title"], status=str(d.get("status", "open") or "open"))


@dataclass
class WorldState:
    """The mutable world state for one session (one voice channel). Serialises to ``state.json``."""

    system: str = ""
    session_id: str = ""
    characters: list[Combatant] = field(default_factory=list)
    npcs: list[Combatant] = field(default_factory=list)
    quests: list[Quest] = field(default_factory=list)
    location: str = ""
    time_ingame: str = ""
    recap: str = ""
    # Scene pointer into the loaded adventure compendium (Phase 10a, ADR 019) — the code-owned
    # "where are we in the plot" the prompt's scene card is selected by. Empty = no adventure.
    scene_id: str = ""

    # -- (de)serialisation ----------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "system": self.system,
            "characters": [c.to_dict() for c in self.characters],
            "npcs": [n.to_dict() for n in self.npcs],
            "quests": [q.to_dict() for q in self.quests],
            "location": self.location,
            "time_ingame": self.time_ingame,
            "recap": self.recap,
            "scene_id": self.scene_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorldState":
        return cls(
            system=str(d.get("system", "") or ""),
            session_id=str(d.get("session_id", "") or ""),
            characters=[Combatant.from_dict(c) for c in d.get("characters", []) or []],
            npcs=[Combatant.from_dict(n, is_npc=True) for n in d.get("npcs", []) or []],
            quests=[Quest.from_dict(q) for q in d.get("quests", []) or []],
            location=str(d.get("location", "") or ""),
            time_ingame=str(d.get("time_ingame", "") or ""),
            recap=str(d.get("recap", "") or ""),
            scene_id=str(d.get("scene_id", "") or ""),
        )

    @classmethod
    def load(cls, path: Path) -> "WorldState | None":
        """Load state from ``path``; ``None`` if it doesn't exist yet (the caller then seeds it)."""
        if not path.is_file():
            return None
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        """Write atomically (temp + ``os.replace``) so a crash mid-write can't corrupt the file —
        the gate is 'an HP change survives a restart', so this file must always be readable."""
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)  # atomic on Windows + POSIX
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @classmethod
    def seed_from_store(
        cls, store: "CharacterStore", *, system: str = "", session_id: str = ""
    ) -> "WorldState":
        """Build a fresh state from the read-only sheet (the once-only transfer, ADR 004): copy each
        character's current/max wounds, conditions and inventory into the mutable layer."""
        chars = [
            Combatant(
                name=c.name,
                wounds=c.wounds if c.wounds is not None else (c.max_wounds or 0),
                max_wounds=c.max_wounds if c.max_wounds is not None else (c.wounds or 0),
                conditions=list(c.conditions),
                inventory=list(c.inventory),
            )
            for c in store.characters()
        ]
        return cls(system=system, session_id=session_id, characters=chars)

    # -- lookup ---------------------------------------------------------------------------

    def find(self, name: str | None) -> Combatant | None:
        """Find a combatant (character first, then NPC) by name, case-insensitively."""
        if not name:
            return None
        key = name.strip().lower()
        for c in self.characters:
            if c.name.lower() == key:
                return c
        for n in self.npcs:
            if n.name.lower() == key:
                return n
        return None

    # -- deterministic advancement (golden rule #3) ---------------------------------------

    def apply_damage(
        self, name: str, amount: int, *, downed_condition: str = DOWNED_CONDITION
    ) -> Combatant | None:
        """Subtract ``amount`` wounds (already soaked — the engine did the math), clamped at 0. At 0
        the combatant gains the downed condition. Returns the updated combatant, or ``None`` if the
        name is unknown."""
        c = self.find(name)
        if c is None:
            return None
        c.wounds = max(0, c.wounds - max(0, amount))
        if c.wounds == 0 and downed_condition and downed_condition not in c.conditions:
            c.conditions.append(downed_condition)
        return c

    def heal(
        self, name: str, amount: int, *, downed_condition: str = DOWNED_CONDITION
    ) -> Combatant | None:
        """Restore ``amount`` wounds, clamped at ``max_wounds``. Rising above 0 clears the downed
        condition. Returns the updated combatant, or ``None`` if unknown."""
        c = self.find(name)
        if c is None:
            return None
        c.wounds = min(c.max_wounds, c.wounds + max(0, amount))
        if c.wounds > 0 and downed_condition in c.conditions:
            c.conditions.remove(downed_condition)
        return c

    def add_condition(self, name: str, condition: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and condition and condition not in c.conditions:
            c.conditions.append(condition)
        return c

    def remove_condition(self, name: str, condition: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and condition in c.conditions:
            c.conditions.remove(condition)
        return c

    def add_or_update_npc(
        self,
        name: str,
        *,
        wounds: int | None = None,
        max_wounds: int | None = None,
        toughness_bonus: int = 0,
        armour: int = 0,
        attitude: str = "hostile",
    ) -> Combatant:
        """Register an NPC (an enemy the party can damage) or update an existing one."""
        existing = next((n for n in self.npcs if n.name.lower() == name.strip().lower()), None)
        max_w = max_wounds if max_wounds is not None else (wounds if wounds is not None else 10)
        if existing is None:
            npc = Combatant(
                name=name.strip(),
                wounds=wounds if wounds is not None else max_w,
                max_wounds=max_w,
                toughness_bonus=toughness_bonus,
                armour=armour,
                is_npc=True,
                attitude=attitude,
            )
            self.npcs.append(npc)
            return npc
        if wounds is not None:
            existing.wounds = wounds
        if max_wounds is not None:
            existing.max_wounds = max_wounds
        if toughness_bonus:
            existing.toughness_bonus = toughness_bonus
        if armour:
            existing.armour = armour
        if attitude:
            existing.attitude = attitude
        return existing

    # -- psyker / Warp Charge (ADR 022) ---------------------------------------------------

    def set_warp_charge(self, name: str, value: int) -> Combatant | None:
        """Set a combatant's Warp Charge to ``value`` (clamped ≥ 0). Returns the combatant or
        ``None`` if unknown. The engine computes the new total; this only stores it."""
        c = self.find(name)
        if c is not None:
            c.warp_charge = max(0, int(value))
        return c

    def reset_warp_charge(self, name: str) -> Combatant | None:
        """Reset Warp Charge to 0 and drop all Sustained powers — what Perils of the Warp does."""
        c = self.find(name)
        if c is not None:
            c.warp_charge = 0
            c.sustained_powers = []
        return c

    def sustain_power(self, name: str, power: str) -> Combatant | None:
        c = self.find(name)
        if c is not None and power and power not in c.sustained_powers:
            c.sustained_powers.append(power)
        return c

    def set_location(self, location: str) -> None:
        self.location = location.strip()

    def set_time(self, time_ingame: str) -> None:
        self.time_ingame = time_ingame.strip()

    def add_quest(self, title: str, *, status: str = "open") -> Quest:
        existing = next((q for q in self.quests if q.title.lower() == title.strip().lower()), None)
        if existing is not None:
            existing.status = status
            return existing
        q = Quest(title=title.strip(), status=status)
        self.quests.append(q)
        return q

    def set_quest_status(self, title: str, status: str) -> Quest | None:
        q = next((q for q in self.quests if q.title.lower() == title.strip().lower()), None)
        if q is not None:
            q.status = status
        return q

    def set_recap(self, text: str) -> None:
        self.recap = text.strip()


def _combatant_line_de(c: Combatant) -> str:
    """'Seskin 8/11 (verwundet)' / 'Mortn 0/9 (kampfunfähig)' — compact per-combatant status."""
    tags: list[str] = []
    if c.wounds <= 0:
        pass  # the downed condition already conveys it; avoid "(0/9, kampfunfähig)" noise
    elif c.wounds < c.max_wounds:
        tags.append("verwundet")
    tags.extend(c.conditions)
    if c.warp_charge or c.sustained_powers:
        warp = f"Warp {c.warp_charge}"
        if c.sustained_powers:
            warp += f", hält: {', '.join(c.sustained_powers)}"
        tags.append(warp)
    suffix = f" ({', '.join(tags)})" if tags else ""
    head = f"{c.name} {c.wounds}/{c.max_wounds}"
    if c.is_npc and c.attitude:
        head = f"{c.name} [{c.attitude}] {c.wounds}/{c.max_wounds}"
    return head + suffix


def world_state_summary_de(state: WorldState) -> str:
    """A compact, *structured* German block for the prompt (docs/conventions.md: 'state as structured data,
    don't boil it into prose'). Only non-empty sections appear. Empty state → ''."""
    lines: list[str] = []
    if state.location:
        lines.append(f"Ort: {state.location}")
    if state.time_ingame:
        lines.append(f"Zeit: {state.time_ingame}")
    if state.characters:
        lines.append("Gruppe: " + "; ".join(_combatant_line_de(c) for c in state.characters))
    living_npcs = [n for n in state.npcs if n.wounds > 0]
    if living_npcs:
        lines.append("NSCs in der Szene: " + "; ".join(_combatant_line_de(n) for n in living_npcs))
    open_quests = [q.title for q in state.quests if q.status == "open"]
    if open_quests:
        lines.append("Offene Aufträge: " + "; ".join(open_quests))
    if not lines:
        return ""
    return "## Weltzustand (harte Fakten — verlass dich darauf, erfinde keine abweichenden Werte)\n" + "\n".join(lines)
