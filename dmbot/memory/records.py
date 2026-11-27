"""The records the world state is made of — combatants, NPC memories, clocks, deadlines,
facts and quests, with the constants that bound them (architecture §7, golden rule #3).

Moved out of :mod:`dmbot.memory.state` (no behaviour change); ``state`` re-exports every name
here, so existing importers keep working (ADR 034). :class:`~dmbot.memory.state.WorldState`
holds lists of these records and stays the only writer of the hard state.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Condition set on a combatant whose wounds reach 0. German (play language); the caller can pass a
# system-specific word, but this is the sensible default for IM ("kampfunfähig" → out of the fight).
DOWNED_CONDITION = "kampfunfähig"

# NPC attitude scale (ADR 044) — the fixed, code-owned axis attitude drift moves along. Stored
# tokens are English (code); the prompt renders German labels. Order matters: index distance is
# what step_attitude clamps.
ATTITUDE_SCALE = ("hostile", "wary", "neutral", "friendly", "loyal")

# Hard cap on stored memories per NPC (ADR 044) — keeps state.json and the prompt block bounded.
NPC_MEMORY_CAP = 30

# Hard cap on stored agenda steps per NPC (ADR 049) — a timeline, so plain FIFO: the newest 10
# are the useful ones, older steps age out (no importance tiers like memories).
AGENDA_LOG_CAP = 10

# -- hard facts (ADR 058) -------------------------------------------------------------------
# The recipient used when a commitment went to the party rather than to one named character.
# German (play language) — this string is rendered into the prompt block verbatim.
GROUP_HOLDER = "Gruppe"

# The closed enumeration a fact's ``kind`` may take. Items extend the existing per-character
# inventory; promises are the standing conditions an NPC gave. Quests keep their own list
# (they existed before ADR 058) and are routed there by :meth:`WorldState.record_commitment`.
FACT_KINDS = ("item", "promise")

# ``open`` = the fact holds; ``revoked`` = taken back / broken. Kept for the prompt: a revoked
# fact stops being rendered but its trace survives the round trip.
FACT_STATUSES = ("open", "revoked")

# The anti-free-text guard (golden rule #3): a fact's text is a *label*, not narration. Anything
# longer than this, or carrying a line break, is a classifier that returned prose — rejected.
FACT_TEXT_MAX = 120

# Hard cap on stored facts — keeps state.json and the prompt block bounded. Revoked facts age
# out first (they no longer render), then the oldest open ones.
FACT_CAP = 40


def _validated_fact_text(value: str) -> str | None:
    """The anti-free-text gate every fact writer passes through (golden rule #3, ADR 058 #2).

    A fact's text must be a short single-line *label* ("Zollvollmacht"), which is what the
    constrained classifier is asked for. Empty, multi-line or longer than
    :data:`FACT_TEXT_MAX` means the model returned narration instead — rejected, so prose can
    never reach hard state. Returns the stripped label, or ``None``."""
    raw = str(value or "")
    if "\n" in raw or "\r" in raw:
        return None
    text = raw.strip()
    if not text or len(text) > FACT_TEXT_MAX:
        return None
    return text


@dataclass
class AgendaStep:
    """One offscreen move an agenda NPC made toward its goal (ADR 049) — narrative-layer prose
    like :class:`NpcMemory`: the *text* is LLM-extracted, code stores/caps/serialises it, and no
    hard field is ever derived from it (golden rule #3). ``ts_ingame`` is the rendered ADR-048
    clock at extraction time ("Tag 2, 14:30") — display data, never parsed back."""

    ts_ingame: str
    text: str

    def to_dict(self) -> dict:
        d: dict = {"text": self.text}
        if self.ts_ingame:
            d["ts_ingame"] = self.ts_ingame
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgendaStep":
        return cls(
            ts_ingame=str(d.get("ts_ingame", "") or ""),
            text=str(d.get("text", "") or ""),
        )


@dataclass
class NpcMemory:
    """One thing an NPC remembers (ADR 044) — a narrative-layer entry, like the recap: the *text*
    is LLM-extracted, but code stores, caps and serialises it, and no hard field is ever derived
    from it (golden rule #3). ``believed`` covers player lies: the NPC stores what it *believes*;
    a revealed lie flips it to False (the NPC now knows it was lied to)."""

    about: list[str]        # ["party"] or ["pc:Kael"] (several possible)
    gist: str               # 1–3 German sentences
    quote: str = ""         # verbatim key quote — only for promises/lies/threats, else empty
    believed: bool = True   # False = the NPC knows by now this was a lie
    importance: int = 3     # 1–5
    source: str = "direct"  # "direct" | "gossip"
    scene: str = ""         # scene id of origin
    ts: str = ""            # ISO timestamp

    def to_dict(self) -> dict:
        d: dict = {"about": list(self.about), "gist": self.gist}
        if self.quote:
            d["quote"] = self.quote
        if not self.believed:
            d["believed"] = False
        if self.importance != 3:
            d["importance"] = self.importance
        if self.source != "direct":
            d["source"] = self.source
        if self.scene:
            d["scene"] = self.scene
        if self.ts:
            d["ts"] = self.ts
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NpcMemory":
        return cls(
            about=[str(a) for a in d.get("about", []) or []],
            gist=str(d.get("gist", "") or ""),
            quote=str(d.get("quote", "") or ""),
            believed=bool(d.get("believed", True)),
            importance=min(5, max(1, int(d.get("importance", 3) or 3))),
            source=str(d.get("source", "direct") or "direct"),
            scene=str(d.get("scene", "") or ""),
            ts=str(d.get("ts", "") or ""),
        )


@dataclass
class Combatant:
    """A character or NPC for state/damage purposes. Mutable — this is the code-owned layer.

    ``armour`` and ``toughness_bonus`` are the soak inputs the engine may subtract from damage (the
    Toughness Bonus only where the profile names a soak characteristic — not in IM, D155). For a
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
    # NPC memory (ADR 044): gossip group + what this NPC remembers. ``faction`` is authored data
    # (npcs.json statblock / manual), never LLM output; ``memories`` is the capped narrative layer.
    faction: str = ""
    memories: list[NpcMemory] = field(default_factory=list)
    # NPC agenda (ADR 049): a non-empty ``goal`` marks this NPC as an agenda NPC — it pursues
    # the goal offscreen, one extracted step per scene change. ``goal`` is human/authored data
    # (``!agenda`` / npcs.json ``goal_de``), never LLM output; ``agenda_log`` is the capped
    # narrative timeline of its offscreen moves.
    goal: str = ""
    agenda_log: list[AgendaStep] = field(default_factory=list)
    # Where an NPC was last seen in person (ADR 062). Presence = on the scene card's
    # ``npcs_here`` OR seen in that scene — so the people the DM improvises count as "here" too.
    scene: str = ""
    # Fate (ADR 063, IM p.220): ``fate_total`` from the sheet or the profile (``None`` = not set
    # up yet), ``fate_spent`` this session. Code-owned like Warp Charge; recovered per session.
    fate_total: int | None = None
    fate_spent: int = 0

    @property
    def fate_available(self) -> int:
        return max(0, (self.fate_total or 0) - self.fate_spent)

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
        if self.faction:
            d["faction"] = self.faction
        if self.memories:
            d["memories"] = [m.to_dict() for m in self.memories]
        if self.goal:
            d["goal"] = self.goal
        if self.agenda_log:
            d["agenda_log"] = [s.to_dict() for s in self.agenda_log]
        if self.scene:
            d["scene"] = self.scene
        if self.fate_total is not None:
            d["fate_total"] = self.fate_total
        if self.fate_spent:
            d["fate_spent"] = self.fate_spent
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
            faction=str(d.get("faction", "") or ""),
            memories=[NpcMemory.from_dict(m) for m in d.get("memories", []) or []],
            goal=str(d.get("goal", "") or ""),
            agenda_log=[AgendaStep.from_dict(s) for s in d.get("agenda_log", []) or []],
            scene=str(d.get("scene", "") or ""),
            fate_total=int(d["fate_total"]) if d.get("fate_total") is not None else None,
            fate_spent=int(d.get("fate_spent", 0) or 0),
        )

    def add_memory(self, memory: NpcMemory) -> None:
        """Append a memory, pruning past :data:`NPC_MEMORY_CAP` (ADR 044): the lowest-importance
        entry goes first (tie: the oldest). ``believed: False`` entries and importance 5 are
        prune-protected — a known lie or a promise must not scroll out. If *everything* is
        protected the oldest entry goes anyway (the hard cap wins, loud log)."""
        self.memories.append(memory)
        if len(self.memories) <= NPC_MEMORY_CAP:
            return
        candidates = [
            i for i, m in enumerate(self.memories) if m.believed and m.importance < 5
        ]
        if not candidates:
            log.warning(
                "NPC '%s': all %d memories prune-protected — dropping the oldest anyway",
                self.name, len(self.memories),
            )
            self.memories.pop(0)
            return
        victim = min(candidates, key=lambda i: (self.memories[i].importance, i))
        self.memories.pop(victim)

    def add_agenda_step(self, step: AgendaStep) -> None:
        """Append an offscreen agenda step (ADR 049), pruning past :data:`AGENDA_LOG_CAP`:
        plain FIFO — the log is a timeline, the oldest step simply ages out."""
        self.agenda_log.append(step)
        while len(self.agenda_log) > AGENDA_LOG_CAP:
            self.agenda_log.pop(0)


def step_attitude(npc: Combatant, proposed: str) -> str:
    """Apply an attitude *proposal* to an NPC, clamped to ±1 step on :data:`ATTITUDE_SCALE`
    (ADR 044, golden rule #3): the extractor (LLM) only proposes, this code decides. An unknown
    proposed value is a no-op + log. An off-scale/empty *current* attitude (legacy free-text
    states) anchors at ``neutral`` so old states can still drift. Returns the (new) attitude."""
    key = (proposed or "").strip().lower()
    if key not in ATTITUDE_SCALE:
        if key:
            log.info(
                "NPC '%s': attitude proposal '%s' ignored (not on the scale)", npc.name, proposed
            )
        return npc.attitude
    current = npc.attitude.strip().lower()
    cur_idx = (
        ATTITUDE_SCALE.index(current)
        if current in ATTITUDE_SCALE
        else ATTITUDE_SCALE.index("neutral")
    )
    new_idx = cur_idx + max(-1, min(1, ATTITUDE_SCALE.index(key) - cur_idx))
    npc.attitude = ATTITUDE_SCALE[new_idx]
    return npc.attitude


# Allowed clock sizes (ADR 047) — the Blades-style small/medium/long fuse. Enforced at creation
# (`!uhr neu`); from_dict stays tolerant so a hand-edited state.json degrades instead of crashing.
CLOCK_SIZES = (4, 6, 8)


@dataclass
class Clock:
    """One consequence/progress clock (ADR 047) — code-owned like every hard fact (golden rule
    #3): the LLM only *requests* a tick via ``<<UHR id>>``, code validates and applies. ``visible``
    is schema-ready for hidden GM clocks; the UI deliberately ignores it for now (ADR 047 #4)."""

    id: str
    name: str
    size: int = 6
    filled: int = 0
    visible: bool = True

    @property
    def full(self) -> bool:
        return self.filled >= self.size

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "name": self.name, "size": self.size, "filled": self.filled}
        if not self.visible:
            d["visible"] = False
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Clock":
        size = int(d.get("size", 6) or 6)
        if size < 1:  # tolerate a hand-edited file; creation enforces CLOCK_SIZES
            size = 6
        return cls(
            id=str(d.get("id", "") or ""),
            name=str(d.get("name", "") or ""),
            size=size,
            filled=min(size, max(0, int(d.get("filled", 0) or 0))),
            visible=bool(d.get("visible", True)),
        )


def slugify_clock_id(name: str, *, fallback: str = "uhr") -> str:
    """A stable, marker-safe id from a clock/deadline name: lowercase, DE transliteration,
    non-alnum → ``-``. Never starts/ends with a separator (the glued-marker strip would peel a
    trailing ``-``/``_``, ADR 043's binding). Empty input degrades to ``fallback``. Deadlines
    (ADR 048) reuse this — same shape, same marker-safety habit."""
    text = name.strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


@dataclass
class Deadline:
    """One in-game deadline (ADR 048) — code-owned like every hard fact (golden rule #3):
    created/removed by humans only (``!frist``), advanced against by the code-owned time
    counter. ``notified`` latches after the one-shot expiry note so it can never re-fire
    (persisted — a restart doesn't re-notify)."""

    id: str
    label: str
    due_minutes: int
    notified: bool = False

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "label": self.label, "due_minutes": self.due_minutes}
        if self.notified:
            d["notified"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Deadline":
        return cls(
            id=str(d.get("id", "") or ""),
            label=str(d.get("label", "") or ""),
            due_minutes=int(d.get("due_minutes", 0) or 0),
            notified=bool(d.get("notified", False)),
        )


@dataclass
class Fact:
    """One narrated commitment that became a hard fact (ADR 058): an item handed over or a
    promise given. ``text`` is a short label (never narration — see :data:`FACT_TEXT_MAX`),
    ``holder`` the character or :data:`GROUP_HOLDER` it went to, ``source`` who gave it, and
    ``at_minutes`` the in-game time it happened at, taken from the code-owned clock."""

    kind: str
    text: str
    holder: str = GROUP_HOLDER
    source: str = ""
    at_minutes: int | None = None
    status: str = "open"

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind, "text": self.text, "holder": self.holder}
        if self.source:
            d["source"] = self.source
        if self.at_minutes is not None:
            d["at_minutes"] = self.at_minutes
        if self.status != "open":
            d["status"] = self.status
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        raw_at = d.get("at_minutes")
        status = str(d.get("status", "open") or "open")
        return cls(
            kind=str(d.get("kind", "") or ""),
            text=str(d.get("text", "") or ""),
            holder=str(d.get("holder", "") or GROUP_HOLDER),
            source=str(d.get("source", "") or ""),
            at_minutes=None if raw_at is None else max(0, int(raw_at or 0)),
            status=status if status in FACT_STATUSES else "open",
        )


@dataclass
class Quest:
    """An accepted job. ``is_mission`` marks the adventure's own objective, seeded at session
    start (ADR 058 #3) — the one quest the player panel shows as *the* goal. ``detail`` is the
    concrete description that keeps "hol das Ossarium" from being a tautology, ``given_by`` and
    ``at_minutes`` the provenance the post-turn classifier records (both optional, so a pre-058
    state.json migrates by defaulting)."""

    title: str
    status: str = "open"
    detail: str = ""
    given_by: str = ""
    at_minutes: int | None = None
    is_mission: bool = False

    def to_dict(self) -> dict:
        d: dict = {"title": self.title, "status": self.status}
        if self.detail:  # omit-when-empty: an untouched quest keeps its pre-058 shape
            d["detail"] = self.detail
        if self.given_by:
            d["given_by"] = self.given_by
        if self.at_minutes is not None:
            d["at_minutes"] = self.at_minutes
        if self.is_mission:
            d["is_mission"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Quest":
        raw_at = d.get("at_minutes")
        return cls(
            title=d["title"],
            status=str(d.get("status", "open") or "open"),
            detail=str(d.get("detail", "") or ""),
            given_by=str(d.get("given_by", "") or ""),
            at_minutes=None if raw_at is None else max(0, int(raw_at or 0)),
            is_mission=bool(d.get("is_mission", False)),
        )
